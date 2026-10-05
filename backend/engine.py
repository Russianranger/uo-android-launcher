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
import tempfile
import threading
import time
import uuid
import zipfile
from uo_content import (REPOSITORY, confined, extract_zip, inspect_client,
                        install_dotnet, local_client_settings, swap_directory, sync_directory, write_json)
from world_archives import SAVE_FOLDERS, extract_save_data, inspect_save_data
from backup_catalog import backup_file, backup_files, delete_backup
import server_settings
import realm_sources


class Engine:
    def __init__(self, work=Path('/work')):
        self.work = Path(work)
        self.world = self.work/'server'
        self.client = self.work/'client/current'
        self.server_source = self.work/'server-source'
        self.process = None
        self.jobs = []
        self.pool = ThreadPoolExecutor(max_workers=1)
        self.lock = threading.RLock()
        for name in ('run','logs','incoming','exports','backups','client'):
            (self.work/name).mkdir(parents=True, exist_ok=True)
        for live in (self.world, self.server_source, self.client, self.work/'client/dotnet'):
            previous = live.with_name(live.name+'.previous')
            if not live.exists() and previous.exists():
                os.replace(previous, live)
        for flag in ('world-command.json','world-command.done','world-command.error'):
            (self.work/'run'/flag).unlink(missing_ok=True)

    def running(self):
        return self.process is not None and self.process.poll() is None

    def ready(self):
        if not self.running():
            return False
        try:
            with socket.socket() as probe:
                probe.settimeout(.15)
                return probe.connect_ex(('127.0.0.1',2593)) == 0
        except OSError:
            return False

    def state(self):
        with self.lock:
            build = self.world/'memento-build.json'
            client = self.client/'memento-client.json'
            return {'running':self.running(), 'ready':self.ready(), 'compiled':(self.world/'WorldLinux.exe').is_file(),
                    'mono_ready':bool(shutil.which('mcs') and shutil.which('mono')),
                    'build':json.loads(build.read_text()) if build.exists() else None,
                    'server_source':realm_sources.source_info(self.server_source),
                    'client':json.loads(client.read_text()) if client.exists() else None,
                    'jobs':[dict(j) for j in self.jobs[-15:]], 'free_bytes':shutil.disk_usage(self.work).free}

    def submit(self, operation, args):
        allowed = {'prepare_runtime','pull_compile','import_server_zip','compile_server','import_client_zip','prepare_dotnet','server_start',
                   'server_stop','server_save','backup_world','restore_world','save_backup',
                   'delete_backup','prune_backups','settings_save','settings_undo'}
        if operation not in allowed:
            raise ValueError('Unknown operation')
        with self.lock:
            if any(j['status'] in ('queued','running') for j in self.jobs):
                raise ValueError('Wait for the current task to finish')
            job = {'id':uuid.uuid4().hex,'operation':operation,'status':'queued','message':'Queued','started_at':time.time()}
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
        selected = realm_sources.selection(args, self.selected_server_source() if 'source' not in args else None)
        repository, ref = selected['repository'], selected['ref']
        # Each repository gets its own cache; changing the selection cannot
        # silently keep fetching the origin from a previous clone.
        import hashlib
        source = self.work/'sources'/('git-'+hashlib.sha256(repository.encode()).hexdigest()[:24])
        source.parent.mkdir(exist_ok=True)
        if not (source/'.git').is_dir():
            if source.exists(): raise ValueError('Source cache exists without Git metadata')
            try:
                self.command(['git','clone','--no-checkout','--no-tags','--',repository,str(source)])
            except BaseException:
                shutil.rmtree(source,ignore_errors=True)
                raise
        origin = subprocess.check_output(['git','-C',str(source),'config','--get','remote.origin.url'],text=True,timeout=60).strip()
        if realm_sources.repository_url(origin) != repository:
            raise ValueError('Source cache origin does not match the selected repository')
        self.command(['git','-C',str(source),'fetch','--depth','1','origin',ref])
        revision = subprocess.check_output(['git','-C',str(source),'rev-parse','FETCH_HEAD'],text=True,timeout=60).strip()
        if not re.fullmatch(r'[a-f0-9]{40}|[a-f0-9]{64}',revision):
            raise ValueError('Git did not return a supported source commit')
        selected.update(revision=revision, imported_at=time.time())
        export = self.work/'source-export'
        prepared = self.work/'source-staging'
        shutil.rmtree(export,ignore_errors=True)
        shutil.rmtree(prepared,ignore_errors=True)
        export.mkdir()
        archive = self.work/'incoming/source.zip'
        self.command(['git','-C',str(source),'archive','--format=zip','--output='+str(archive),revision])
        try:
            extract_zip(archive,export)
            prepared.mkdir()
            shutil.move(str(realm_sources.inspect_server(export)),prepared/'World')
            write_json(prepared/realm_sources.SOURCE_MARKER, selected)
            result = self._compile_server(prepared, selected, activate_source=True)
        finally:
            archive.unlink(missing_ok=True)
            shutil.rmtree(export,ignore_errors=True)
            shutil.rmtree(prepared,ignore_errors=True)
        return result

    def selected_server_source(self):
        selected = realm_sources.source_info(self.server_source)
        if selected: return selected
        build = self.world/'memento-build.json'
        if build.is_file():
            info = json.loads(build.read_text())
            if info.get('source') == 'zip': return info
            if info.get('repository'):
                return dict(info, source=realm_sources.source_kind(info['repository']))
        # Before source selection existed, this clone was the only persistent
        # source record. Read its actual origin rather than guessing a default.
        legacy = self.work/'source'
        if (legacy/'.git').is_dir():
            origin = subprocess.check_output(['git','-C',str(legacy),'config','--get','remote.origin.url'],text=True,timeout=60).strip()
            repository = realm_sources.repository_url(origin)
            return {'repository':repository, 'source':realm_sources.source_kind(repository), 'ref':'main'}
        return None

    def import_server_zip(self, args):
        self.require_stopped()
        archive = confined(self.work/'incoming',args['file'])
        export, prepared = self.work/'source-export', self.work/'source-staging'
        shutil.rmtree(export,ignore_errors=True)
        shutil.rmtree(prepared,ignore_errors=True)
        try:
            digest = realm_sources.sha256_file(archive)
            extract_zip(archive,export)
            world = realm_sources.inspect_server(export)
            prepared.mkdir()
            shutil.move(str(world),prepared/'World')
            metadata = {'format':1, 'source':'zip', 'archive_sha256':digest, 'imported_at':time.time()}
            write_json(prepared/realm_sources.SOURCE_MARKER,metadata)
            swap_directory(prepared,self.server_source)
        finally:
            archive.unlink(missing_ok=True)
            shutil.rmtree(export,ignore_errors=True)
            shutil.rmtree(prepared,ignore_errors=True)
        return {'message':'Server ZIP imported. Prepare Mono if needed, then compile the imported server.', 'server_source':metadata}

    def compile_server(self, _):
        self.require_stopped()
        if not shutil.which('mcs'): raise ValueError('Prepare the Mono compiler first')
        metadata = realm_sources.source_info(self.server_source)
        if metadata is None: raise ValueError('Import a server ZIP or pull a server source first')
        return self._compile_server(self.server_source,metadata)

    def _compile_server(self, prepared, metadata, activate_source=False):
        staging = self.work/'server-staging'
        shutil.rmtree(staging,ignore_errors=True)
        activated = False
        try:
            source_world = realm_sources.inspect_server(prepared)
            shutil.copytree(source_world,staging)
            defaults = (staging/server_settings.SETTINGS).read_text()
            settings_added = []
            if self.world.exists():
                # Preserve all current mutable trees, including custom settings
                # and scripts, and compile those against the new server core.
                for name in ('Saves','Info','Data','Backups'):
                    old = self.world/name
                    if old.is_symlink() or (old.exists() and not old.is_dir()):
                        raise ValueError(name+' must be a real folder before updating the server')
                    if name in ('Saves','Backups'):
                        # Missing save folders are empty too. Never resurrect
                        # the account/world defaults from another source.
                        shutil.rmtree(staging/name,ignore_errors=True)
                        (staging/name).mkdir()
                    if old.is_dir():
                        rebuild_assets = name=='Data' and (self.client/'memento-client.json').is_file()
                        ignore = (lambda folder,names: ['Files'] if Path(folder)==old and 'Files' in names else []) if rebuild_assets else None
                        shutil.copytree(old,staging/name,dirs_exist_ok=True,symlinks=True,ignore=ignore)
                settings_path = confined(staging,server_settings.SETTINGS)
                settings, settings_added = realm_sources.add_missing_settings(settings_path.read_text(), defaults)
                if settings_added: settings_path.write_text(settings)
            scripts = realm_sources.compile_server(staging,self.command)
            write_json(staging/'memento-build.json',dict(metadata,built_at=time.time(),scripts_checked=scripts,settings_added=settings_added))
            self.link_assets(staging)
            if self.world.exists(): self.backup_world({'reason':'Before server update'})
            swap_directory(staging,self.world)
            activated = True
            if activate_source: swap_directory(prepared,self.server_source)
        except BaseException:
            # A source activation failure must also roll the live deployment
            # back. swap_directory itself restores a failed directory rename.
            if activated:
                shutil.rmtree(self.world,ignore_errors=True)
                previous = self.world.with_name(self.world.name+'.previous')
                if previous.exists(): os.replace(previous,self.world)
            raise
        finally:
            shutil.rmtree(staging,ignore_errors=True)
        description = metadata.get('revision','')[:12] or 'imported ZIP '+metadata['archive_sha256'][:12]
        return {'message':'Memento compiled from '+description+'. Core and '+str(scripts)+' scripts checked; ready to start.',
                'server_source':metadata}

    def link_assets(self, world=None):
        world = self.world if world is None else Path(world)
        marker=self.client/'memento-client.json'
        if not marker.is_file() or not world.exists():
            return
        info=json.loads(marker.read_text())
        source=confined(self.client,info['assets'])
        destination=world/'Data/Files'
        destination.parent.mkdir(parents=True,exist_ok=True)
        if destination.is_symlink():
            destination.unlink()
        elif destination.exists():
            saved=destination.with_name('Files.before-client-import-'+str(time.time_ns()))
            os.replace(destination,saved)
        # Wine is case-insensitive; Mono on Linux is not. Expose lowercase
        # asset names to Memento without renaming the imported client files.
        destination.mkdir()
        for asset in source.iterdir():
            if asset.is_file():
                (destination/asset.name.lower()).symlink_to(asset)

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

    def backup_world(self,args):
        self.require_stopped()
        if not self.world.is_dir():
            raise ValueError('No world is installed')
        target=self.work/'exports'/('memento-world-'+str(time.time_ns())+'.zip')
        fd, name = tempfile.mkstemp(prefix='.creating-', dir=target.parent)
        os.close(fd)
        temporary = Path(name)
        try:
            with zipfile.ZipFile(temporary,'w',zipfile.ZIP_DEFLATED,compresslevel=1) as z:
                for name in SAVE_FOLDERS:
                    root=self.world/name
                    if root.is_symlink() or (root.exists() and not root.is_dir()):
                        raise ValueError(name+' must be a real folder before exporting save data')
                    # Keep empty/missing folders so an unplayed world also round-trips.
                    z.writestr(name+'/',b'')
                    if not root.is_dir(): continue
                    for folder,dirs,files in os.walk(root,followlinks=False):
                        dirs[:]=[d for d in dirs if not (Path(folder)/d).is_symlink()]
                        if Path(folder)!=root:
                            z.write(folder,str(Path(folder).relative_to(self.world))+'/')
                        for file in files:
                            p=Path(folder)/file
                            if not p.is_symlink() and p.is_file(): z.write(p,str(p.relative_to(self.world)))
            with temporary.open('rb') as source: os.fsync(source.fileno())
            os.replace(temporary,target)
            sync_directory(target.parent)
            write_json(self.work/'backups'/('metadata-'+target.name+'.json'),
                       {'reason':args.get('reason','Manual backup'),'created_at':time.time()})
        finally:
            temporary.unlink(missing_ok=True)
        return {'message':'Info, Saves and Backups export ready','file':str(target.relative_to(self.work))}

    def save_backup(self,_):
        # A live world cannot be archived while Mono is writing it. The native
        # session guard keeps client/setup actions out of this save/stop flow.
        self.server_stop({})
        result=self.backup_world({'reason':'Save & export'})
        result['message']='World saved and server stopped. Save-data ZIP is ready to export.'
        return result

    def backup_preview(self,args):
        source=backup_file(self.work,args.get('name'))
        info=inspect_save_data(source,self.work/'restore-staging')
        info.pop('member_paths')
        return dict(info,name=source.name,bytes=source.stat().st_size,backup=source.name)

    def preview_world(self,args):
        source=confined(self.work/'incoming',args['file'])
        info=inspect_save_data(source,self.work/'restore-staging')
        info.pop('member_paths')
        return dict(info,name=source.name,bytes=source.stat().st_size,file=source.name)

    def delete_backup(self,args):
        delete_backup(self.work,args.get('name'))
        return {'message':'App backup deleted. Copies exported outside the app are unchanged.'}

    def prune_backups(self,args):
        keep=args.get('keep')
        if type(keep) is not int or not 1<=keep<=1000: raise ValueError('Keep at least one backup')
        old=backup_files(self.work)[keep:]
        if 'names' in args and args['names']!=[path.name for path in old]:
            raise ValueError('The backup list changed. Refresh it before removing older copies.')
        for path in old: delete_backup(self.work,path.name)
        return {'message':str(len(old))+' older app backups removed. The newest '+str(keep)+' were kept.'}

    def settings_read(self,_):
        info,_,_=server_settings.read(self.world,self.work/'backups/settings-last-change.json')
        info['running']=self.running()
        return info

    def settings_save(self,args):
        self.require_stopped()
        return server_settings.save(self.work,self.world,args)

    def settings_undo(self,args):
        self.require_stopped()
        return server_settings.undo(self.work,self.world,args)

    def restore_world(self,args):
        self.require_stopped()
        if not self.world.is_dir(): raise ValueError('Compile Memento before restoring a world')
        existing=bool(args.get('backup'))
        source=backup_file(self.work,args['backup']) if existing else confined(self.work/'incoming',args['file'])
        staging=self.work/'restore-staging'
        deployment=self.work/'restore-deployment'
        shutil.rmtree(staging,ignore_errors=True)
        shutil.rmtree(deployment,ignore_errors=True)
        try:
            imported=extract_save_data(source,staging)
            backup=self.backup_world({'reason':'Before restore'})
            # Swap a complete deployment, so interruption cannot mix old/new save trees.
            shutil.copytree(self.world,deployment,symlinks=True)
            for name in SAVE_FOLDERS:
                if (staging/name).exists():
                    shutil.rmtree(deployment/name,ignore_errors=True)
                    shutil.move(staging/name,deployment/name)
            swap_directory(deployment,self.world)
            message='Save data imported (Info, Saves and Backups only). Previous world backup: '+backup['file']
            if imported['legacy']: message+=' (Legacy Data content was skipped.)'
            return {'message':message}
        finally:
            shutil.rmtree(staging,ignore_errors=True)
            shutil.rmtree(deployment,ignore_errors=True)
            if not existing: source.unlink(missing_ok=True)


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
                elif op in ('backup_preview','preview_world','settings_read'): result=getattr(engine,op)(args)
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
