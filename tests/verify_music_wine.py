from pathlib import Path
import subprocess
import sys
work=Path(sys.argv[1]).resolve();wine=Path(sys.argv[2]).resolve()
def windows(path):return 'Z:'+str(path).replace('/','\\')
try:
    result=subprocess.run([str(wine),str(work/'probe/MusicProbe.exe'),windows(work/'original'),windows(work/'patched')],
        stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,errors='replace',timeout=120)
    print(result.stdout,flush=True)
    assert result.returncode==0 and 'MUSIC_CACHE_OK actual_assembly=true' in result.stdout
finally:
    subprocess.run([str(wine.with_name('wineserver')),'-k'],timeout=15,check=False)
    subprocess.run([str(wine.with_name('wineserver')),'-w'],timeout=15,check=False)
