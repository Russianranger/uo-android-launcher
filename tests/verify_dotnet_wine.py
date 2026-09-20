"""Wine 10 / .NET 10.0.8 regression using the launcher's real DLL policies.

Runs on an x86-64 CI host. It verifies the Wine loader defect, not ARM64 Box64,
Android display, graphics, or TazUO gameplay.
"""
import json
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
    # Recreate the reported import layout, including spaces and an upgraded
    # installation whose settings contain the launcher's old, ignored key.
    runner.CLIENT=root/'client';runner.CLIENT.mkdir(exist_ok=True)
    folder=runner.CLIENT/'Ultima-Memento/Client/TazUO-Launcher/TazUO';folder.mkdir(parents=True,exist_ok=True)
    assets=runner.CLIENT/'Ultima-Memento/Client/Data Files';assets.mkdir(parents=True,exist_ok=True)
    for name in ('tiledata.mul','cliloc.enu','map0.mul'):(assets/name).write_bytes(b'fixture')
    (folder/'TazUO.exe').touch()
    info={'executable':str((folder/'TazUO.exe').relative_to(runner.CLIENT)),
          'settings':str((folder/'settings.json').relative_to(runner.CLIENT)),
          'assets':str(assets.relative_to(runner.CLIENT))}
    expected=runner.windows_path(info['assets'])
    settings=folder/'settings.json'
    settings.write_text(json.dumps({'ultimaonline':expected,'clientversion':'',
                                    'username':'private-user','password':'private-password'}))
    drive=root/'prefix/dosdevices/d:'
    if drive.is_symlink():drive.unlink()
    drive.symlink_to(runner.CLIENT)
    args=[app,runner.windows_path(info['settings'])]
    code=run(args,env,'old-settings.log')
    assert code==2 and 'MEMENTO_CONFIG_INVALID UO directory' in (runner.LOGS/'old-settings.log').read_text()
    supervisor.request.update(client=info,gump_space=True,resolution='1280x720')
    supervisor.prepare_client_configuration()
    supervisor.root=Path(__file__).resolve().parents[1]/'backend-assets'
    env=supervisor.client_environment()
    env['DOTNET_HOST_TRACEFILE']=env['COREHOST_TRACEFILE']='Z:'+str(runner.LOGS/'probe-host.log').replace('/','\\')
    env['MEMENTO_MANAGED_LOG']='Z:'+str(runner.LOGS/'client-managed.log').replace('/','\\')
    args.append(runner.windows_path((folder/'Data/Profiles/default.json').relative_to(runner.CLIENT)))
    code=run(args,env,'fixed-settings.log')
    output=(runner.LOGS/'fixed-settings.log').read_text(errors='replace')
    assert code==0 and 'MEMENTO_CONFIG_OK '+expected+' 7.0.15.1' in output, output[-8000:]
    assert 'private-' not in (runner.LOGS/'client-config.json').read_text()
    assert 'MEMENTO_LAYOUT_OK 1098x720 in 1280x720' in output
    print('Fixed: Windows .NET reads the repaired settings and finds the nested Memento data directory',flush=True)
    print('Verified: Windows .NET reads the 1098x720 world / 1280x720 window profile',flush=True)
    code=run([app,'--pathfinder-throw'],env,'pathfinder-throw.log',45)
    captured=(runner.LOGS/'client-managed.log').read_text(errors='replace')
    assert code not in (0,124), (code,captured)
    assert 'Hook active: .NET 10.0.8' in captured and 'PATHFINDER FIRST CHANCE' in captured, captured
    assert 'System.IndexOutOfRangeException' in captured and 'ClassicUO.Game.Pathfinder.CreateItemList' in captured, captured
    print('Verified: managed startup hook captures a pathfinding exception before FailFast termination',flush=True)
finally:stop()
