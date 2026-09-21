from pathlib import Path
import os
import subprocess
import sys
work=Path(sys.argv[1]).resolve();wine=Path(sys.argv[2]).resolve()
def windows(path):return 'Z:'+str(path).replace('/','\\')
try:
    for mode in ['original','patched','combined']:
        env=os.environ.copy()
        env['DOTNET_STARTUP_HOOKS']=windows(work/'assets/Memento.FrameBudget.dll')
        if mode=='combined':env['DOTNET_STARTUP_HOOKS']+=';'+windows(work/'assets/Memento.RenderTrace.dll')
        result=subprocess.run([str(wine),str(work/'probe/FrameProbe.exe'),windows(work/mode),'original' if mode=='original' else 'budget'],
            env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,errors='replace',timeout=90)
        print(result.stdout,flush=True)
        assert result.returncode==0 and 'FRAME_BUDGET_OK actual_assembly=true' in result.stdout
        assert 'FRAME_BUDGET_ACTIVE revision=1' in result.stdout
finally:
    subprocess.run([str(wine.with_name('wineserver')),'-k'],timeout=15,check=False)
    subprocess.run([str(wine.with_name('wineserver')),'-w'],timeout=15,check=False)
