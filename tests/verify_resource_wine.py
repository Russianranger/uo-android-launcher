from pathlib import Path
import os
import subprocess
import sys
from compare_resource_probes import compare, qualify

work = Path(sys.argv[1]).resolve()
wine = Path(sys.argv[2]).resolve()


def windows(path):
    return 'Z:' + str(path).replace('/', '\\')


try:
    outputs = {}
    for variant, mode in (('base', 'disabled'), ('patched', 'disabled'), ('patched', 'enabled')):
        env = dict(os.environ, MEMENTO_COLD_TRACE='1' if mode == 'enabled' else '0',
                   DOTNET_STARTUP_HOOKS=windows(work.parent/'frame-budget/Memento.FrameBudget.dll'))
        result = subprocess.run([str(wine), str(work/'probe/ResourceTraceProbe.exe'),
                                 windows(work/variant), mode], env=env, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, errors='replace', timeout=120)
        print(result.stdout, flush=True)
        assert result.returncode == 0, (variant, mode, result.returncode)
        qualify(result.stdout, mode)
        outputs[variant, mode] = result.stdout
    compare(outputs['base', 'disabled'], outputs['patched', 'disabled'], outputs['patched', 'enabled'])
finally:
    subprocess.run([str(wine.with_name('wineserver')), '-k'], timeout=15, check=False)
    subprocess.run([str(wine.with_name('wineserver')), '-w'], timeout=15, check=False)
