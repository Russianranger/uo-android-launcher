"""Native ARM64 Wine/FEX supervisor with the existing in-app transports."""
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
import client_graphics
import client_render_trace
import client_runtime
from client_health import ClientHealth, prepare_render_progress
from uo_content import confined, write_json, local_client_settings, renderer_settings, viewport_settings, frame_settings, client_binary_report

SESSION=Path('/session')
PREFIX=Path('/prefix')
CLIENT=Path('/client')
LOGS=Path('/logs')
WINE=['/opt/wine/bin/wine']
WINESERVER=['/opt/wine/bin/wineserver']
RUNTIME_ID='fex-arm64ec-1'
PREFIX_REVISION=RUNTIME_ID
stopped=False


def windows_path(relative):
    return 'D:\\'+str(relative).replace('/','\\')


class Supervisor:
    def __init__(self,request):
        request=dict(request)
        # Old APK launch preferences are not a valid FEX diagnostic opt-in.
        if request.get('runtime_backend') != RUNTIME_ID:
            for key in ('managed_diagnostics','render_trace','sdl_graphics_fixes'):
                request[key]=False
        request['runtime_backend']=RUNTIME_ID
        self.request=request
        self.children=[]
        self.threads=[]
        self.root=Path(__file__).parent
        self.status={'runtime_backend':RUNTIME_ID,'phase':'starting','display_ready':False,'client_started':False,
                     'attempt_started_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),
                     'resolution':request['resolution'],'display_target_fps':request['display_fps']}
        self.env=dict(os.environ,DISPLAY=':8',XAUTHORITY='/session/Xauthority',WINEPREFIX='/prefix',WINEARCH='win64',
                      # Wine's IL-only DLL loader requires mscoree even with modern
                      # CoreCLR. Disable it only in the wineboot child environment.
                      WINEDEBUG='-all,err+all',WINEDLLOVERRIDES='winemenubuilder,mshtml=;mscoree=b',
                      LD_LIBRARY_PATH=str(self.root),
                      DOTNET_ROOT='E:\\',DOTNET_ROOT_X64='E:\\',DOTNET_ROOT_X86='E:\\',DOTNET_MULTILEVEL_LOOKUP='0')
        # FEX handles x86 Windows code; Wine and its Unix libraries run natively.
        # Do not inherit Box64 tuning, JIT policy or translator experiments.
        for key in list(self.env):
            if key.startswith(('BOX64_','FEX_','DOTNET_','COMPlus_')) and key not in (
                    'DOTNET_ROOT','DOTNET_ROOT_X64','DOTNET_ROOT_X86','DOTNET_MULTILEVEL_LOOKUP'):
                self.env.pop(key,None)
        self.env.pop('FNA_WIN32_IGNORE_WM_PAINT',None)
        diagnostics=request.get('managed_diagnostics',False)
        if not isinstance(diagnostics,bool):raise ValueError('Invalid managed diagnostics option')
        self.status['managed_diagnostics']=diagnostics and request.get('mode','client')=='client'
        # Do not inherit an injected startup hook into Wine setup or a normal
        # game launch. Detailed in-process instrumentation is now opt-in.
        self.env.pop('DOTNET_STARTUP_HOOKS',None)
        self.env.pop('MEMENTO_MANAGED_LOG',None)
        self.env.pop('MEMENTO_RENDER_TRACE',None)
        self.env.pop('MEMENTO_RENDER_PROGRESS',None)
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
        started=time.monotonic()
        deadline=started+timeout
        while process.poll() is None:
            if self.stopping():raise InterruptedError('Client stopped')
            if time.monotonic()>deadline:raise RuntimeError('Setup timed out. Open '+log)
            time.sleep(.2)
        if process.returncode:
            self.update(setup_exit_code=process.returncode,setup_log=log,
                        setup_seconds=round(time.monotonic()-started,2))
            if process.returncode==-signal.SIGKILL:
                raise RuntimeError('Setup was killed by SIGKILL (code -9) before the client started. Open '+log)
            raise RuntimeError('Setup exited with code '+str(process.returncode)+'. Open '+log)

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
        graphics_fixes=self.request.get('sdl_graphics_fixes',False)
        if not isinstance(graphics_fixes,bool):raise ValueError('Invalid SDL graphics fixes option')
        report['sdl_graphics']=client_graphics.prepare(CLIENT,info,self.root,
            graphics_fixes and self.request['renderer']=='turnip')
        report['render_trace']=client_render_trace.prepare(CLIENT,info,self.root,
            self.request.get('render_trace',False))
        self.update(sdl_graphics=report['sdl_graphics'],render_trace=report['render_trace'])
        renderer_settings(CLIENT,info,self.request['renderer'])
        report['pacing']=frame_settings(CLIENT,info,self.request['display_fps'])
        self.update(pacing=report['pacing'])
        report['graphics_driver']='Vulkan' if self.request['renderer']=='turnip' else 'OpenGL'
        if self.request.get('gump_space',False):
            report['layout']=viewport_settings(CLIENT,info)
        report['client_binary']=client_binary_report(CLIENT,info)
        write_json(LOGS/'client-config.json',report)

    def client_environment(self):
        env=self.dotnet_environment('client-dotnet-host.log')
        if self.status['managed_diagnostics']:
            hook=self.root/'Memento.Diagnostics.dll'
            if not hook.is_file():raise RuntimeError('Client diagnostics component is missing; reinstall the current APK')
            from log_retention import rotate
            rotate(LOGS/'client-managed.log')
            env.update(DOTNET_STARTUP_HOOKS='Z:'+str(hook).replace('/','\\'),
                       MEMENTO_MANAGED_LOG='Z:\\logs\\client-managed.log')
        if self.status.get('render_trace',{}).get('active'):
            hook=self.root/client_render_trace.HELPER
            trace_hook='Z:'+str(hook).replace('/','\\')
            existing=env.get('DOTNET_STARTUP_HOOKS')
            env['DOTNET_STARTUP_HOOKS']=trace_hook+(';' + existing if existing else '')
            env['MEMENTO_RENDER_TRACE']='1'
            progress=SESSION/'render-progress.bin'
            # This optional observer must not prevent an otherwise valid launch.
            try:
                prepare_render_progress(progress)
                env['MEMENTO_RENDER_PROGRESS']='Z:'+str(progress).replace('/','\\')
            except (OSError,ValueError):pass
        env['WINEDEBUG']='-all,err+all,trace+loaddll'
        write_json(LOGS/'client-compatibility.json',{
            'runtime_backend':RUNTIME_ID,
            'managed_diagnostics':self.status['managed_diagnostics'],
            'external_health_log':'client-health.log',
            'wine_command':WINE,
            'translator':'FEX Windows ARM64EC (upstream defaults)',
            'render_trace':self.status.get('render_trace',{}),
            'attempt_started_utc':self.status['attempt_started_utc'],
            'environment':{key:env[key] for key in ('WINEDEBUG','WINEDLLOVERRIDES','WINEARCH')},
            'validation':'ARM64 CI validation is separate from Thor gameplay validation',
        })
        return env

    def start(self):
        request=self.request
        if request['mode'] not in ('desktop','client') or request['renderer'] not in ('turnip','virgl','software') or request['resolution'] not in ('800x600','1024x768','1280x720'):
            raise ValueError('Invalid launch options')
        # If Wine setup fails, an earlier gameplay crash must not appear as this
        # attempt's current output. Preserve it in the normal bounded history.
        from log_retention import rotate
        for name in ('client-wine.log','client-managed.log','client-dotnet-host.log','client-compatibility.json','client-health.log'):
            path=LOGS/name
            rotate(path)
            path.unlink(missing_ok=True)
        self.update('starting')
        identity=client_runtime.inspect()
        write_json(LOGS/'client-runtime.json',identity)
        self.update(runtime=identity)
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
                            # Native Surface already compares captured pixels;
                            # the RFB socket is retained for input and fallback.
                            '-CompareFB','0' if request.get('presentation_mode')=='native_surface' else '2',
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
        health=ClientHealth(game.pid,LOGS,render_progress=SESSION/'render-progress.bin'
                           if env.get('MEMENTO_RENDER_PROGRESS') else None)
        started=time.monotonic()
        self.update('client_running' if request['mode']=='client' else 'wine_desktop',renderer_requested=request['renderer'],
                    compatibility='Device validation required',launcher_pid=game.pid,client_started=request['mode']=='client')
        try:
            while not self.stopping():
                if display.poll() is not None:raise RuntimeError('Embedded display exited')
                code=game.poll()
                if code is not None:
                    self.update(exit_code=code,client_seconds=round(time.monotonic()-started,2))
                    if code:raise RuntimeError('TazUO/Wine exited with code '+str(code)+'. Export logs for diagnosis.')
                    if request['mode']=='client' and time.monotonic()-started<15:
                        raise RuntimeError('TazUO closed during startup (exit code 0). Export support logs from the Journal.')
                    break
                health.sample()
                time.sleep(.5)
        finally:
            # The mapped record survives the process. Keep its final boundary
            # even when a crash happened between periodic health samples.
            health.sample(force=True)

    def stop(self):
        try:subprocess.run(WINESERVER+['-k'],env=self.env,timeout=10,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
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
