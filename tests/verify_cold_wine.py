from pathlib import Path
import os
import subprocess
import sys
work=Path(sys.argv[1]).resolve();wine=Path(sys.argv[2]).resolve()
def windows(path):return 'Z:'+str(path).replace('/','\\')
try:
    env=dict(os.environ,MEMENTO_COLD_TRACE='1',DOTNET_STARTUP_HOOKS=windows(work.parent/'frame-budget/Memento.FrameBudget.dll'))
    result=subprocess.run([str(wine),str(work/'probe/GraphicsBoundaryProbe.exe'),windows(work/'patched'),windows(work/'shim.dll')],env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,errors='replace',timeout=90)
    print(result.stdout,flush=True)
    assert result.returncode==0 and 'GRAPHICS_BOUNDARY_OK' in result.stdout and 'COLD_TRACE_ACTIVE' in result.stdout
finally:
    subprocess.run([str(wine.with_name('wineserver')),'-k'],timeout=15,check=False)
    subprocess.run([str(wine.with_name('wineserver')),'-w'],timeout=15,check=False)
