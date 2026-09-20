"""Reproduce FNA paint reentrancy with actual .NET 10/FNA/SDL/Wine libraries.

Exercises synchronous SDL exposure during Draw, not the Thor's exact trigger
or ARM64/Box64/Turnip. The production environment must prevent nested draws.
"""
import os
from pathlib import Path
import subprocess
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
import uo_client_runner as runner

root=Path(sys.argv[1]).resolve()
runner.SESSION=root/'session';runner.SESSION.mkdir(exist_ok=True)
runner.LOGS=root/'logs';runner.LOGS.mkdir(exist_ok=True)
wine_root=root.parent/'dotnet-wine'
supervisor=runner.Supervisor({'mode':'client','renderer':'turnip','resolution':'1280x720','display_fps':60})
# The host uses Mesa Vulkan instead of Android's Turnip library. Keep the
# production game environment, including the FNA policy and managed loader.
supervisor.env.update(WINEPREFIX=str(wine_root/'prefix'),DISPLAY=os.environ['DISPLAY'],
                      XAUTHORITY=os.environ.get('XAUTHORITY',''))
for key in ('VK_ICD_FILENAMES','VK_DRIVER_FILES','MESA_VK_WSI_DEBUG'):
    supervisor.env.pop(key,None)
env=supervisor.client_environment()
assert env['FNA_WIN32_IGNORE_WM_PAINT']=='1'
assert 'DOTNET_STARTUP_HOOKS' not in env
env['DOTNET_HOST_TRACEFILE']=env['COREHOST_TRACEFILE']='Z:'+str(root/'logs/host.log').replace('/','\\')
env['FNA_PLATFORM_BACKEND']='SDL3'
wine=wine_root/'wine/bin/wine'
try:
    for name,policy,expected,marker in (
        ('immediate','0',23,'FNA_PAINT_REENTRANCY_REPRODUCED'),
        ('queued',env['FNA_WIN32_IGNORE_WM_PAINT'],0,'FNA_PAINT_SERIALIZED_OK')):
        with (runner.LOGS/(name+'.log')).open('wb') as output:
            result=subprocess.run(['timeout','90',str(wine),str(root/'app/PaintProbe.exe')],
                cwd=root/'app',env=dict(env,FNA_WIN32_IGNORE_WM_PAINT=policy),
                stdout=output,stderr=subprocess.STDOUT)
        log=(runner.LOGS/(name+'.log')).read_text(errors='replace')
        print(log,flush=True)
        assert result.returncode==expected and marker in log,(name,result.returncode,log[-8000:])
    print('Verified: real FNA reproduces list mutation on nested paint; production policy serializes 64 exposures',flush=True)
finally:
    subprocess.run([str(wine_root/'wine/bin/wineserver'),'-k'],env=env,timeout=15,check=False)
