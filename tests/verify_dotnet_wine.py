"""Wine 10 / .NET 10.0.8 regression using the launcher's real DLL policies.

Runs on an x86-64 CI host. It verifies the Wine loader defect, not ARM64 Box64,
Android display, graphics, or TazUO gameplay.
"""
import os
from pathlib import Path
import signal
import subprocess
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
import uo_client_runner as runner

root=Path(sys.argv[1]).resolve()
runner.SESSION=root/'session';runner.SESSION.mkdir(exist_ok=True)
runner.LOGS=root/'logs';runner.LOGS.mkdir(exist_ok=True)
supervisor=runner.Supervisor({'renderer':'software','resolution':'800x600','display_fps':30})
supervisor.env.update(WINEPREFIX=str(root/'prefix'),DISPLAY=os.environ['DISPLAY'],
                      XAUTHORITY=os.environ.get('XAUTHORITY',''),WINEDEBUG='-all,err+all')
wine=root/'wine/bin/wine';server=root/'wine/bin/wineserver'


def run(args,env,log,timeout=90):
    with (runner.LOGS/log).open('wb') as output:
        process=subprocess.Popen([str(wine)]+args,env=env,stdin=subprocess.DEVNULL,
                                 stdout=output,stderr=subprocess.STDOUT,start_new_session=True)
        try:return process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid,signal.SIGKILL);process.wait()
            return 124


def stop():
    subprocess.run([str(server),'-k'],env=supervisor.env,check=False,timeout=15,
                   stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)


try:
    # Mono installation stays disabled during setup, as it is on the device.
    assert run(['wineboot','-u'],supervisor.setup_environment(),'setup.log',180)==0
    assert run(['reg','add',r'HKLM\Software\Microsoft\Windows NT\CurrentVersion\AeDebug',
                '/v','Debugger','/t','REG_SZ','/d','disabled-debugger','/f'],
               supervisor.env,'debugger.log')==0
    app=str(root/'app/ManagedProbe.exe')
    # Negative control: reproduce 0.1.1's actual Wine error before testing the fix.
    code=run([app],supervisor.setup_environment(),'disabled-loader.log',45)
    stop()
    negative=(runner.LOGS/'disabled-loader.log').read_text(errors='replace')
    assert code!=0 and 'mscoree.dll not found' in negative and 'System.Runtime.dll' in negative, negative[-8000:]
    print('Reproduced: disabled mscoree prevents System.Runtime.dll from loading',flush=True)
    # Use the production launch environment with the builtin managed loader.
    env=supervisor.dotnet_environment('probe-host.log')
    env['DOTNET_HOST_TRACEFILE']=env['COREHOST_TRACEFILE']='Z:'+str(runner.LOGS/'probe-host.log').replace('/','\\')
    code=run([app],env,'enabled-loader.log')
    positive=(runner.LOGS/'enabled-loader.log').read_text(errors='replace')
    assert code==0 and 'MEMENTO_MANAGED_OK .NET 10.0.8 System.Runtime' in positive, positive[-8000:]
    assert 'install_mono' not in positive
    print('Fixed: bundled .NET 10.0.8 loads System.Runtime and executes managed code',flush=True)
finally:stop()
