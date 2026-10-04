from pathlib import Path
import os
import subprocess
import sys

work = Path(sys.argv[1]).resolve()
wine = Path(sys.argv[2]).resolve()


def windows(path):
    return 'Z:' + str(path).replace('/', '\\')


try:
    for mode in ('enabled', 'disabled'):
        env = dict(os.environ, MEMENTO_COLD_TRACE='1' if mode == 'enabled' else '0',
                   DOTNET_STARTUP_HOOKS=windows(work.parent/'frame-budget/Memento.FrameBudget.dll'))
        result = subprocess.run([str(wine), str(work/'probe/ResourceTraceProbe.exe'),
                                 windows(work/'patched'), mode], env=env, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, errors='replace', timeout=90)
        print(result.stdout, flush=True)
        assert result.returncode == 0 and 'RESOURCE_TRACE_OK mode='+mode in result.stdout
        assert 'RESOURCE_STARTUP_READS_OK mode='+mode in result.stdout
        assert 'RESOURCE_STARTUP_ASSETS_OK mode='+mode in result.stdout
        assert ('COLD_TRACE_ACTIVE revision=3' in result.stdout) == (mode == 'enabled')
finally:
    subprocess.run([str(wine.with_name('wineserver')), '-k'], timeout=15, check=False)
    subprocess.run([str(wine.with_name('wineserver')), '-w'], timeout=15, check=False)
