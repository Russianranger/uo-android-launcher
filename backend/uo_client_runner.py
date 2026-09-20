"""TazUO Wine supervisor using TRASC's display, relative input and audio transports."""
import json
import os
from pathlib import Path
import secrets
import signal
import subprocess
import threading
import time
import client_audio
import client_presentation
from uo_content import confined, write_json, local_client_settings, renderer_settings, viewport_settings, client_binary_report

SESSION=Path('/session')
PREFIX=Path('/prefix')
CLIENT=Path('/client')
LOGS=Path('/logs')
WINE=['/usr/local/bin/box64','/opt/wine/bin/wine']
PREFIX_REVISION='2'
stopped=False


def windows_path(relative):
    return 'D:\\'+str(relative).replace('/','\\')


class Supervisor:
    def __init__(self,request):
        self.request=request
        self.children=[]
        self.threads=[]
        self.root=Path(__file__).parent
        self.status={'phase':'starting','display_ready':False,'resolution':request['resolution'],'display_target_fps':request['display_fps']}
        self.env=dict(os.environ,DISPLAY=':8',XAUTHORITY='/session/Xauthority',WINEPREFIX='/prefix',WINEARCH='win64',
                      # Wine's IL-only DLL loader requires mscoree even with modern
                      # CoreCLR. Disable it only in the wineboot child environment.
                      WINEDEBUG='-all,err+all',WINEDLLOVERRIDES='winemenubuilder,mshtml=;mscoree=b',
                      BOX64_DYNAREC_STRONGMEM='1',BOX64_DYNAREC_BIGBLOCK='0',BOX64_DYNAREC_SAFEFLAGS='2',
                      BOX64_DYNAREC_MISSING='0',BOX64_PATH='/opt/wine/bin',BOX64_LOG='1',
                      BOX64_LD_LIBRARY_PATH='/usr/lib/x86_64-linux-gnu:/lib/x86_64-linux-gnu:/opt/wine/lib/wine/x86_64-unix',
                      LD_LIBRARY_PATH=str(self.root),BOX64_RCFILE=str(SESSION/'box64.rc'),BOX64_MAXCPU='0',
                      DOTNET_ROOT='E:\\',DOTNET_ROOT_X64='E:\\',DOTNET_ROOT_X86='E:\\',DOTNET_MULTILEVEL_LOOKUP='0',
                      DOTNET_EnableWriteXorExecute='0')
        # The runtime's stock [wine] entry overrides MAXCPU to 64, even on an
        # eight-core handheld. Keep the conservative flags and real CPU count.
        (SESSION/'box64.rc').write_text('[wine]\nBOX64_MAXCPU=0\n[wine64]\nBOX64_MAXCPU=0\n'
                                       '[explorer.exe]\nBOX64_DYNAREC_BIGBLOCK=0\n')
        # The latest failure is a native CoreCLR access violation, not the
        # earlier managed render-list exception. Test stricter x86 memory
        # ordering without changing the imported client or its JIT/GC policy.
        compatibility=request.get('memory_compatibility',True)
        if not isinstance(compatibility,bool):raise ValueError('Invalid memory compatibility option')
        if request.get('mode','client')=='client':
            self.env.update(BOX64_DYNAREC_STRONGMEM='3' if compatibility else '1',
                            BOX64_DYNAREC_WEAKBARRIER='0' if compatibility else '1')
            self.status['memory_compatibility']=compatibility
        renderer=request['renderer']
        if renderer=='turnip':
            write_json(SESSION/'turnip-icd.json',{'file_format_version':'1.0.0','ICD':{'library_path':str(self.root/'turnip-26.0.0.so'),'api_version':'1.3.0'}})
            self.env.update(VK_ICD_FILENAMES='/session/turnip-icd.json',VK_DRIVER_FILES='/session/turnip-icd.json',
                            MESA_VK_WSI_DEBUG='sw',
                            FNA3D_FORCE_DRIVER='Vulkan',SDL_AUDIODRIVER='directsound')
            self.env['WINEDLLOVERRIDES']+=';d3d11,dxgi=b'
        else:
            self.env.update(LIBGL_ALWAYS_SOFTWARE='1',GALLIUM_DRIVER='virpipe' if renderer=='virgl' else 'llvmpipe',
                            FNA3D_FORCE_DRIVER='OpenGL',LP_NUM_THREADS='4',SDL_AUDIODRIVER='directsound')
            self.env['WINEDLLOVERRIDES']+=';d3d11,dxgi=b'

    def update(self,phase=None,**fields):
        if phase:self.status['phase']=phase
        self.status.update(fields)
        write_json(SESSION/'status.json',self.status)
        write_json(LOGS/'client-state.json',self.status)

    def stopping(self):
        return stopped or (SESSION/'stop').exists()

    def spawn(self,args,log,env=None,cwd=None):
        path=LOGS/log
        from log_retention import rotate
        rotate(path)
        process=subprocess.Popen(args,env=env or self.env,cwd=cwd or CLIENT,stdin=subprocess.DEVNULL,
                                 stdout=subprocess.PIPE,stderr=subprocess.STDOUT,start_new_session=True)
        self.children.append(process)
        def pump():
            # Drains independently of UI status; bound every continuously written log.
            out=path.open('ab');size=path.stat().st_size
            try:
                while chunk:=process.stdout.read1(16384):
                    if size+len(chunk)>8*1024**2:
                        out.close();rotate(path);out=path.open('wb');size=0
                    out.write(chunk);out.flush();size+=len(chunk)
            finally:
                out.close();process.stdout.close()
        thread=threading.Thread(target=pump,daemon=True);self.threads.append(thread);thread.start()
        return process

    def run(self,args,log='client-prefix.log',timeout=180,env=None):
        process=self.spawn(args,log,env=env)
        deadline=time.monotonic()+timeout
        while process.poll() is None:
            if self.stopping():raise InterruptedError('Client stopped')
            if time.monotonic()>deadline:raise RuntimeError('Setup timed out. Open '+log)
            time.sleep(.2)
        if process.returncode:raise RuntimeError('Setup exited with code '+str(process.returncode)+'. Open '+log)

    def prepare_prefix(self):
        marker=PREFIX/'memento-prefix-ready'
        ready=(marker.is_file() and marker.read_text()==PREFIX_REVISION
               and (PREFIX/'system.reg').is_file() and (PREFIX/'drive_c/windows/system32/kernel32.dll').is_file())
        marker.unlink(missing_ok=True)
        self.update('preparing_wine',display_ready=True,prefix_update='reuse' if ready else 'repair')
        self.run(WINE+['wineboot','-i' if ready else '-u'],timeout=240,env=self.setup_environment())
        self.run(WINE+['cmd','/d','/c','exit','0'],log='client-wine-check.log',timeout=60)
        marker.write_text(PREFIX_REVISION)

    def setup_environment(self):
        # Suppress wineboot's Mono installer without disabling the managed DLL
        # loader in the subsequent .NET preflight, TazUO or Wine desktop process.
        return dict(self.env,WINEDLLOVERRIDES=self.env['WINEDLLOVERRIDES'].replace('mscoree=b','mscoree='))

    def dotnet_environment(self,log):
        from log_retention import rotate
        rotate(LOGS/log)
        trace='Z:\\logs\\'+log
        # .NET 10 renamed COREHOST_TRACE to DOTNET_HOST_TRACE; support either.
        return dict(self.env,DOTNET_HOST_TRACE='1',DOTNET_HOST_TRACEFILE=trace,DOTNET_HOST_TRACE_VERBOSITY='3',
                    COREHOST_TRACE='1',COREHOST_TRACEFILE=trace,COREHOST_TRACE_VERBOSITY='3')

    def prepare_client_configuration(self):
        self.update('checking_client')
        if self.request.get('gump_space',False) and self.request['resolution']!='1280x720':
            raise ValueError('The 1098x720 world viewport requires a 1280x720 display')
        info=self.request['client']
        if not confined(CLIENT,info['executable']).is_file():
            raise ValueError('Imported client executable is missing')
        # Repair existing imports on APK upgrade, before opening the display.
        report=local_client_settings(CLIENT,info)
        renderer_settings(CLIENT,info,self.request['renderer'])
        report['graphics_driver']='Vulkan' if self.request['renderer']=='turnip' else 'OpenGL'
        if self.request.get('gump_space',False):
            report['layout']=viewport_settings(CLIENT,info)
        report['client_binary']=client_binary_report(CLIENT,info)
        write_json(LOGS/'client-config.json',report)

    def client_environment(self):
        env=self.dotnet_environment('client-dotnet-host.log')
        hook=self.root/'Memento.Diagnostics.dll'
        if not hook.is_file():raise RuntimeError('Client diagnostics component is missing; reinstall the current APK')
        from log_retention import rotate
        rotate(LOGS/'client-managed.log')
        env.update(DOTNET_STARTUP_HOOKS='Z:'+str(hook).replace('/','\\'),
                   MEMENTO_MANAGED_LOG='Z:\\logs\\client-managed.log')
        # Wine handles SIGSEGV before managed observers see fatal native faults.
        # Print Box64 fault PCs/registers, plus Wine's loaded module bases for
        # address attribution. Avoid rolling-call traces and native stack walks
        # on every handled fault. The normal 8 MiB log rotation still applies.
        env.update(BOX64_SHOWSEGV='1',BOX64_SHOWBT='0',WINEDEBUG='-all,err+all,trace+loaddll')
        write_json(LOGS/'client-compatibility.json',{
            'memory_compatibility':self.status.get('memory_compatibility',False),
            'environment':{key:env[key] for key in (
                'BOX64_DYNAREC_STRONGMEM','BOX64_DYNAREC_WEAKBARRIER','BOX64_DYNAREC_BIGBLOCK',
                'BOX64_DYNAREC_SAFEFLAGS','BOX64_SHOWSEGV','BOX64_SHOWBT','WINEDEBUG')},
            'validation':'Experimental mitigation; native crash cause not established',
        })
        return env

    def start(self):
        request=self.request
        if request['mode'] not in ('desktop','client') or request['renderer'] not in ('turnip','virgl','software') or request['resolution'] not in ('800x600','1024x768','1280x720'):
            raise ValueError('Invalid launch options')
        if request['mode']=='client':self.prepare_client_configuration()
        self.update('checking_libraries')
        self.run(['/usr/bin/python3','-c','import ctypes; ctypes.CDLL("libXcomposite.so.1"); print("XComposite ready")'],
                 log='client-dependencies.log',timeout=30)
        if request.get('audio',True):
            client_audio.configure_environment(self.env,SESSION)
            self.update(audio=client_audio.prepare(self.root,SESSION))
        (SESSION/'Xauthority').touch(mode=0o600)
        subprocess.run(['xauth','-f',self.env['XAUTHORITY'],'add',':8','.',secrets.token_hex(16)],check=True)
        display=self.spawn(['Xtigervnc',':8','-geometry',request['resolution'],'-depth','24','-rfbport','-1',
                            '-rfbunixpath','/session/display.sock','-rfbunixmode','0600','-SecurityTypes','None',
                            '-nolisten','tcp','-auth',self.env['XAUTHORITY'],'-AlwaysShared','-FrameRate',str(request['display_fps']),
                            '-desktop','UO Memento'],'client-display.log')
        for _ in range(150):
            if self.stopping():return
            if display.poll() is not None:raise RuntimeError('Embedded display failed. Open client-display.log')
            if (SESSION/'display.sock').exists():break
            time.sleep(.1)
        else:raise RuntimeError('Embedded display did not become ready')
        self.update(**client_presentation.start(self));self.update(**client_presentation.start_input(self))
        self.prepare_prefix()
        devices=PREFIX/'dosdevices';devices.mkdir(exist_ok=True)
        for name,target in (('d:',CLIENT),('e:',Path('/dotnet'))):
            drive=devices/name
            if drive.is_symlink():drive.unlink()
            if drive.exists():raise RuntimeError('Wine drive '+name+' is already occupied')
            drive.symlink_to(target)
        if request['mode']=='desktop':
            launch=WINE+['explorer','/desktop=Memento,'+request['resolution']]
            cwd=CLIENT
        else:
            info=request['client'];exe=confined(CLIENT,info['executable'])
            if not info['self_contained']:
                installed=json.loads(Path('/dotnet/memento-dotnet.json').read_text())
                if installed['architecture']!=info['architecture'] or installed['version'].split('.')[:2]!=info['dotnet_version'].split('.')[:2]:
                    raise RuntimeError('Prepare .NET again for the current client version/architecture')
                self.update('checking_dotnet',dotnet_version=installed['version'],client_architecture=info['architecture'])
                self.run(WINE+['E:\\dotnet.exe','--list-runtimes'],log='client-dotnet.log',timeout=90,
                         env=self.dotnet_environment('client-dotnet-check-host.log'))
                # Use the portable host explicitly so no registry/global .NET installation is required.
                dll=exe.with_suffix('.dll')
                if not dll.is_file():raise ValueError('The framework-dependent TazUO DLL is missing')
                launch=WINE+['E:\\dotnet.exe',windows_path(dll.relative_to(CLIENT))]
            else:launch=WINE+[windows_path(info['executable'])]
            cwd=exe.parent
        env=self.client_environment() if request['mode']=='client' else self.env
        game=self.spawn(launch,'client-wine.log',cwd=cwd,env=env)
        started=time.monotonic()
        self.update('client_running' if request['mode']=='client' else 'wine_desktop',renderer_requested=request['renderer'],
                    compatibility='Device validation required',launcher_pid=game.pid)
        while not self.stopping():
            if display.poll() is not None:raise RuntimeError('Embedded display exited')
            code=game.poll()
            if code is not None:
                self.update(exit_code=code,client_seconds=round(time.monotonic()-started,2))
                if code:raise RuntimeError('TazUO/Wine exited with code '+str(code)+'. Export logs for diagnosis.')
                if request['mode']=='client' and time.monotonic()-started<15:
                    raise RuntimeError('TazUO closed during startup (exit code 0). Export support logs from the Journal.')
                break
            time.sleep(.5)

    def stop(self):
        try:subprocess.run(['/usr/local/bin/box64','/opt/wine/bin/wineserver','-k'],env=self.env,timeout=10,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        except (OSError,subprocess.TimeoutExpired):pass
        for process in reversed(self.children):
            if process.poll() is None:
                try:os.killpg(process.pid,signal.SIGTERM)
                except ProcessLookupError:pass
        for process in self.children:
            try:process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                try:os.killpg(process.pid,signal.SIGKILL)
                except ProcessLookupError:pass
        for thread in self.threads:thread.join(timeout=1)
        (SESSION/'display.sock').unlink(missing_ok=True)
        self.update(display_ready=False)


def main():
    def signal_stop(*_):
        global stopped
        stopped=True
    signal.signal(signal.SIGTERM,signal_stop);signal.signal(signal.SIGINT,signal_stop)
    supervisor=Supervisor(json.loads((SESSION/'request.json').read_text()))
    try:supervisor.start();supervisor.update('stopped')
    except InterruptedError:supervisor.update('stopped')
    except Exception as error:supervisor.update('error',error=str(error));raise
    finally:supervisor.stop()


if __name__=='__main__':main()
