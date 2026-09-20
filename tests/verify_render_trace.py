"""Exercise injected IL and exception evidence; this is not a Thor reproduction."""
import os
from pathlib import Path
import re
import subprocess
import sys

app, helper = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
command = sys.argv[3:]
wine = any('wine' in Path(x).name for x in command)
helper_path = 'Z:' + str(helper).replace('/', '\\') if wine else str(helper)
env = dict(os.environ, DOTNET_STARTUP_HOOKS=helper_path, MEMENTO_RENDER_TRACE='1')
for scenario in ('normal', 'same-thread', 'other-thread', 'untracked-write', 'unchanged-versions', 'other-exception', 'overflow'):
    result = subprocess.run(command + [str(app), scenario], env=env, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, timeout=90)
    output = result.stdout
    print(output, flush=True)
    assert result.returncode == 0 and 'RENDER_PROBE_OK ' + scenario in output, (scenario, result.returncode)
    assert 'RENDER_TRACE_ACTIVE' in output
    assert 'RENDER_TRACE_UNAVAILABLE' not in output
    failures = [line for line in output.splitlines() if line.startswith('RENDER_ENUMERATOR_FAILURE ')]
    if scenario in ('normal', 'overflow', 'other-exception'):
        assert not failures, scenario
    else:
        assert len(failures) == 1, scenario
        data = dict(re.findall(r'(\w+)=([^ ]+)', failures[0]))
        assert data['begin_version'] == data['enumerator_version'] and data['same_list'] == 'True'
        assert data['begin_readers'] == data['current_readers'] == '1'
        assert data['begin_thread'] == data['failure_thread']
        if scenario == 'unchanged-versions':
            assert data['current_version'] == data['enumerator_version']
        else:
            assert data['current_version'] != data['enumerator_version']
        if scenario in ('same-thread', 'other-thread'):
            assert data['begin_fill'] != data['current_fill']
            assert output.count('RENDER_WRITE_DURING_READ') == 1, 'finally must remove reader before the next fill'
            assert (data['last_writer_thread'] == data['begin_thread']) == (scenario == 'same-thread')
        else:
            assert data['begin_fill'] == data['current_fill']
            assert 'RENDER_WRITE_DURING_READ' not in output
# A disabled helper preserves original behavior and adds no trace output.
result = subprocess.run(command + [str(app), 'same-thread'], env=dict(env, MEMENTO_RENDER_TRACE='0'),
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=90)
assert result.returncode == 0 and 'RENDER_PROBE_OK' in result.stdout
assert 'RENDER_TRACE_' not in result.stdout and 'RENDER_ENUMERATOR_' not in result.stdout
print('RENDER_TRACE_VERIFIED: mutation attribution, unchanged versions, cross-thread writes, rethrow, finally and disabled mode')
