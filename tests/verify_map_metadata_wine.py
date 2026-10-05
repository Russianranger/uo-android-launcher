from pathlib import Path
import os
import subprocess
import sys
from compare_map_metadata_runtime import qualify, compare

work = Path(sys.argv[1]).resolve()
wine = Path(sys.argv[2]).resolve()

def windows(path):
    return 'Z:' + str(path).replace('/', '\\')

try:
    outputs = []
    for variant in ('ordinary', 'ordinary-render', 'resource', 'resource-render'):
        for mode in (('enabled', 'disabled') if variant.startswith('resource') else ('disabled',)):
            for policy, selection in (('baseline', 'base'), ('optimized', 'patched')):
                env = dict(os.environ, MEMENTO_COLD_TRACE='1' if mode == 'enabled' else '0',
                           DOTNET_STARTUP_HOOKS=windows(work.parent/'frame-budget/Memento.FrameBudget.dll'))
                result = subprocess.run([str(wine), str(work/'probe/MapMetadataProbe.exe'),
                                         windows(work/(selection+'-'+variant)), mode, policy],
                                        env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                        text=True, errors='replace', timeout=120)
                print(result.stdout, flush=True)
                assert result.returncode == 0, (variant, mode, policy, result.returncode)
                qualify(result.stdout)
                outputs.append(result.stdout)
    compare(outputs)
finally:
    subprocess.run([str(wine.with_name('wineserver')), '-k'], timeout=15, check=False)
    subprocess.run([str(wine.with_name('wineserver')), '-w'], timeout=15, check=False)
