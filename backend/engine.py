"""Local, token-authenticated Memento control service inside PRoot."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import threading
import time
import uuid
import zipfile
from uo_content import (REPOSITORY, confined, extract_zip, inspect_client,
                        install_dotnet, local_client_settings, swap_directory, write_json)


class Engine:
    def __init__(self, work=Path('/work')):
        self.work = Path(work)
        self.world = self.work/'server'
        self.client = self.work/'client/current'
        self.process = None
        self.jobs = []
        self.pool = ThreadPoolExecutor(max_workers=1)
        self.lock = threading.RLock()
        for name in ('run','logs','incoming','exports','backups','client'):
            (self.work/name).mkdir(parents=True, exist_ok=True)
        for live in (self.world, self.client, self.work/'client/dotnet'):
            previous = live.with_name(live.name+'.previous')
            if not live.exists() and previous.exists():
                os.replace(previous, live)
        for flag in ('world-command.json','world-command.done','world-command.error'):
            (self.work/'run'/flag).unlink(missing_ok=True)

    def running(self):
        return self.process is not None and self.process.poll() is None

    def state(self):
        with self.lock:
            build = self.world/'memento-build.json'
            client = self.client/'memento-client.json'
            return {'running':self.running(), 'compiled':(self.world/'WorldLinux.exe').is_file(),
                    'mono_ready':bool(shutil.which('mcs') and shutil.which('mono')),
                    'build':json.loads(build.read_text()) if build.exists() else None,
                    'client':json.loads(client.read_text()) if client.exists() else None,
                    'jobs':[dict(j) for j in self.jobs[-15:]], 'free_bytes':shutil.disk_usage(self.work).free}

    def submit(self, operation, args):
        allowed = {'prepare_runtime','pull_compile','import_client_zip','prepare_dotnet','server_start',
                   'server_stop','server_save','backup_world','restore_world'}
        if operation not in allowed:
            raise ValueError('Unknown operation')
        with self.lock:
            if any(j['status'] in ('queued','running') for j in self.jobs):
                raise ValueError('Wait for the current task to finish')
            job = {'id':uuid.uuid4().hex,'operation':operation,'status':'queued','message':'Queued'}
            self.jobs.append(job)
        def run():
            with self.lock:
                job.update(status='running',message=operation.replace('_',' '))
            try:
                result = getattr(self, operation)(args)
                with self.lock:
                    job.update(status='done',result=result,message=result.get('message','Complete'))
            except Exception as error:
                with self.lock:
                    job.update(status='error',error=str(error),message=str(error))
                with (self.work/'logs/control.log').open('a') as out:
                    out.write(operation+': '+str(error)+'\n')
        self.pool.submit(run)
        return dict(job)

    def require_stopped(self):
        if self.running():
            raise ValueError('Save and stop the server first')

    def command(self, args, cwd=None, log='build.log', timeout=1800):
        with (self.work/'logs'/log).open('ab') as out:
            out.write(('\n> '+' '.join(map(str,args))+'\n').encode())
            result = subprocess.run(args, cwd=cwd, stdout=out, stderr=subprocess.STDOUT,
                                    stdin=subprocess.DEVNULL, timeout=timeout)
        if result.returncode:
            raise RuntimeError('Command failed (code '+str(result.returncode)+'). Open '+log+' for details.')

    def prepare_runtime(self, _):
        self.require_stopped()
        if shutil.which('mcs') and shutil.which('mono'):
            return {'message':'Mono compiler and server runtime are ready'}
        os.environ['DEBIAN_FRONTEND']='noninteractive'
        self.command(['apt-get','update'],log='setup.log')
        self.command(['apt-get','install','-y','mono-devel','libgdiplus','zlib1g','git','ca-certificates'],log='setup.log')
        return {'message':'Mono compiler installed. Pull and compile Memento next.'}

    def pull_compile(self, args):
        self.require_stopped()
        if not shutil.which('mcs'):
            raise ValueError('Prepare the Mono compiler first')
        ref = args.get('ref','main').strip()
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._/-]{0,159}',ref) or '..' in ref or ref.endswith('/'):
            raise ValueError('Enter a branch, tag or commit SHA')
        source = self.work/'source'
        if not (source/'.git').is_dir():
            if source.exists():
                raise ValueError('Source folder exists without Git metadata')
            self.command(['git','clone','--no-checkout',REPOSITORY,str(source)])
        self.command(['git','-C',str(source),'fetch','--depth','1','origin',ref])
        revision = subprocess.check_output(['git','-C',str(source),'rev-parse','FETCH_HEAD'],text=True).strip()
        staging = self.work/'server-staging'
        shutil.rmtree(staging,ignore_errors=True)
        export = self.work/'source-export'
        shutil.rmtree(export,ignore_errors=True)
        export.mkdir()
        # Git archive is produced from a commit fetched from the fixed repository.
        archive = self.work/'incoming/source.zip'
        self.command(['git','-C',str(source),'archive','--format=zip','--output='+str(archive),revision])
        try:
            extract_zip(archive,export)
            if not (export/'World/Source/Tools/compile-world-linux.sh').exists():
                raise ValueError('This revision has no supported Memento Mono build layout')
            shutil.move(str(export/'World'),staging)
            if self.world.exists():
                self.backup_world({})
                # Preserve the entire mutable data/configuration trees across source upgrades.
                for name in ('Saves','Info','Data','Backups'):
                    old=self.world/name
                    if old.is_dir():
                        shutil.copytree(old,staging/name,dirs_exist_ok=True,ignore=shutil.ignore_patterns('Files') if name=='Data' else None)
            misc=staging/'Source/Scripts/System/Misc'
            shutil.copy2(Path(__file__).with_name('MementoAndroidControl.cs'),misc/'MementoAndroidControl.cs')
            for name, before, after in (
                ('ServerList.cs','public static readonly string Address = MySettings.S_Address;','public static readonly string Address = "127.0.0.1";'),
                ('ServerList.cs','public static readonly bool AutoDetect = MySettings.S_AutoDetect;','public static readonly bool AutoDetect = false;'),
                ('SocketOptions.cs','new IPEndPoint( IPAddress.Any, MySettings.S_Port )','new IPEndPoint( IPAddress.Loopback, 2593 )')):
                p=misc/name
                text=p.read_text()
                if before not in text:
                    raise ValueError('Upstream '+name+' changed; review its local-network patch before compiling')
                p.write_text(text.replace(before,after))
            tools=staging/'Source/Tools'
            self.command(['mcs','-optimize+','-unsafe','-t:exe','-out:'+str(staging/'WorldLinux.exe'),
                          '-win32icon:../System/icon.ico','-nowarn:219,414','-d:NEWTIMERS','-d:NEWPARENT','-d:MONO',
                          '-recurse:../System/*.cs','-main:Server.Core'],cwd=tools)
            write_json(staging/'memento-build.json',{'repository':REPOSITORY,'revision':revision,'ref':ref,'built_at':time.time()})
            swap_directory(staging,self.world)
            self.link_assets()
        finally:
            archive.unlink(missing_ok=True)
            shutil.rmtree(export,ignore_errors=True)
            shutil.rmtree(staging,ignore_errors=True)
        return {'message':'Memento compiled at '+revision[:12]+'. Scripts compile on first server start.'}

    def link_assets(self):
        marker=self.client/'memento-client.json'
        if not marker.is_file() or not self.world.exists():
            return
        info=json.loads(marker.read_text())
        source=confined(self.client,info['assets'])
        destination=self.world/'Data/Files'
        destination.parent.mkdir(parents=True,exist_ok=True)
        if destination.is_symlink():
            destination.unlink()
        elif destination.exists():
            saved=destination.with_name('Files.before-client-import-'+str(time.time_ns()))
            os.replace(destination,saved)
        destination.symlink_to(source,target_is_directory=True)

    def import_client_zip(self,args):
        self.require_stopped()
        archive=confined(self.work/'incoming',args['file'])
        staging=self.work/'client/import-staging'
        shutil.rmtree(staging,ignore_errors=True)
        try:
            extract_zip(archive,staging)
            info=inspect_client(staging)
            local_client_settings(staging,info)
            write_json(staging/'memento-client.json',info)
            swap_directory(staging,self.client)
            self.link_assets()
        finally:
            shutil.rmtree(staging,ignore_errors=True)
            archive.unlink(missing_ok=True)
        return {'message':'Memento client imported. Prepare .NET, then launch.','client':info}

    def prepare_dotnet(self,_):
        return install_dotnet(self.client,self.work/'client/dotnet')

    def server_start(self,_):
        if self.running():
            return {'message':'Server is already running'}
        if not (self.world/'WorldLinux.exe').is_file():
            raise ValueError('Pull and compile the server first')
        if not (self.world/'Data/Files/tiledata.mul').is_file():
            raise ValueError('Import the complete Memento client to supply the server map/data files')
        for name in ('world-command.json','world-command.done','world-command.error'):
            (self.work/'run'/name).unlink(missing_ok=True)
        with socket.socket() as probe:
            if probe.connect_ex(('127.0.0.1',2593)) == 0:
                raise ValueError('Port 2593 is already in use')
        from log_retention import rotate
        rotate(self.work/'logs/server.log')
        with (self.work/'logs/server.log').open('ab') as log:
            self.process=subprocess.Popen(['mono','--server','WorldLinux.exe'],cwd=self.world,
                                          stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        for _ in range(600):
            if not self.running():
                raise RuntimeError('Memento exited during script compilation or startup. Open server.log.')
            with socket.socket() as probe:
                probe.settimeout(.5)
                if probe.connect_ex(('127.0.0.1',2593)) == 0:
                    return {'message':'Memento is listening on 127.0.0.1:2593'}
            time.sleep(1)
        raise RuntimeError('Server is still starting after 10 minutes. Check server.log; it has not been killed.')

    def world_command(self,action):
        if not self.running():
            return {'message':'Server is stopped'}
        done,error=self.work/'run/world-command.done',self.work/'run/world-command.error'
        done.unlink(missing_ok=True);error.unlink(missing_ok=True)
        command=self.work/'run/world-command.json'
        temp=command.with_suffix('.new');temp.write_text(action);os.replace(temp,command)
        for _ in range(180):
            if error.exists():
                raise RuntimeError('World save failed: '+error.read_text()[:4096])
            if done.exists() and done.read_text()==action:
                if action=='stop':
                    self.process.wait(timeout=30)
                return {'message':'World saved'+(' and server stopped' if action=='stop' else '')}
            if not self.running():
                raise RuntimeError('Server exited before confirming the world save. Inspect server.log.')
            time.sleep(1)
        command.unlink(missing_ok=True)
        raise RuntimeError('Save acknowledgement timed out. Server remains running; check server.log.')

    def server_stop(self,_):
        return self.world_command('stop')

    def server_save(self,_):
        return self.world_command('save')

    def backup_world(self,_):
        self.require_stopped()
        if not self.world.is_dir():
            raise ValueError('No world is installed')
        target=self.work/'exports'/('memento-world-'+str(time.time_ns())+'.zip')
        with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED,compresslevel=1) as z:
            z.writestr('memento-backup.json',json.dumps({'format':1,'kind':'world','created':time.time()}))
            for name in ('Saves','Info','Data','Backups'):
                root=self.world/name
                if not root.is_dir(): continue
                for folder,dirs,files in os.walk(root,followlinks=False):
                    dirs[:]=[d for d in dirs if not (Path(folder)/d).is_symlink() and not (name=='Data' and d.startswith('Files'))]
                    for file in files:
                        p=Path(folder)/file
                        if not p.is_symlink(): z.write(p,str(p.relative_to(self.world)))
        return {'message':'World backup ready','file':str(target.relative_to(self.work))}

    def restore_world(self,args):
        self.require_stopped()
        if not self.world.is_dir(): raise ValueError('Compile Memento before restoring a world')
        source=confined(self.work/'incoming',args['file'])
        staging=self.work/'restore-staging'
        shutil.rmtree(staging,ignore_errors=True)
        try:
            extract_zip(source,staging)
            marker=json.loads((staging/'memento-backup.json').read_text())
            if marker.get('format')!=1 or marker.get('kind')!='world' or not (staging/'Saves').is_dir():
                raise ValueError('Choose an exported Memento world backup')
            if any(p.name not in ('Saves','Info','Data','Backups','memento-backup.json') for p in staging.iterdir()):
                raise ValueError('Unexpected world backup content')
            backup=self.backup_world({})
            # Swap a complete deployment, so interruption cannot mix old/new save trees.
            deployment=self.work/'restore-deployment'
            shutil.rmtree(deployment,ignore_errors=True)
            shutil.copytree(self.world,deployment,symlinks=True)
            for name in ('Saves','Info','Data','Backups'):
                if (staging/name).exists():
                    shutil.rmtree(deployment/name,ignore_errors=True)
                    shutil.move(staging/name,deployment/name)
            swap_directory(deployment,self.world)
            self.link_assets()
            return {'message':'World restored. Previous world backup: '+backup['file']}
        finally:
            shutil.rmtree(staging,ignore_errors=True)
            source.unlink(missing_ok=True)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--token-file',required=True);args=parser.parse_args()
    token=Path(args.token_file).read_text().strip()
    engine=Engine()
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*_): pass
        def do_POST(self):
            if not hmac.compare_digest(self.headers.get('Authorization',''),'Bearer '+token):
                self.send_error(403);return
            try:
                size=int(self.headers.get('Content-Length','0'))
                if size<1 or size>1024*1024: raise ValueError('Invalid request size')
                request=json.loads(self.rfile.read(size));op=request['operation'];args=request.get('args',{})
                if op=='state': result=engine.state()
                elif op=='exit':
                    if any(j['status'] in ('queued','running') for j in engine.jobs): raise ValueError('Finish the current task first')
                    engine.server_stop({});result={'message':'Runtime stopped'}
                    threading.Thread(target=self.server.shutdown,daemon=True).start()
                else: result=engine.submit(op,args)
                body={'ok':True,'result':result}
            except Exception as error: body={'ok':False,'error':str(error)}
            data=json.dumps(body).encode();self.send_response(200);self.send_header('Content-Type','application/json')
            self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
    server=ThreadingHTTPServer(('127.0.0.1',18785),Handler)
    server.serve_forever();engine.pool.shutdown();server.server_close()


if __name__=='__main__': main()
