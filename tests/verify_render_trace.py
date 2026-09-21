"""Exercise injected IL and exception evidence; this is not a Thor reproduction."""
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'backend'))
from client_health import ClientHealth, RenderProgress, prepare_render_progress

app, helper = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
command = sys.argv[3:]
wine = any('wine' in Path(x).name for x in command)
helper_path = 'Z:' + str(helper).replace('/', '\\') if wine else str(helper)
env = dict(os.environ, DOTNET_STARTUP_HOOKS=helper_path, MEMENTO_RENDER_TRACE='1')
for scenario in ('normal', 'same-thread', 'other-thread', 'untracked-write', 'unchanged-versions', 'other-exception', 'overflow', 'no-format'):
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
        assert output.index('RENDER_FAILURE_ENTER') < output.index('RENDER_ENUMERATOR_FAILURE')
        if scenario in ('unchanged-versions', 'no-format'):
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

# Read a real Windows/.NET mapping from the Linux observer while the draw is
# blocked. No managed timer/thread has to run to report the frozen boundary.
with tempfile.TemporaryDirectory() as temp:
    root = Path(temp)
    progress, release = root/'progress.bin', root/'release'
    def guest(path):return 'Z:' + str(path).replace('/', '\\') if wine else str(path)
    prepare_render_progress(progress)
    observer = RenderProgress(progress)
    process = subprocess.Popen(command + [str(app), 'blocked-draw'],
        env=dict(env, MEMENTO_RENDER_PROGRESS=guest(progress), RENDER_PROBE_RELEASE=guest(release)),
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        deadline = time.monotonic() + 45
        while True:
            data = observer.snapshot()
            if any(row['stage'] == 'drawing_list' for row in data.get('threads', [])):break
            if process.poll() is not None or time.monotonic() > deadline:
                raise AssertionError(('blocked draw did not publish progress', data))
            time.sleep(.05)
        row = data['threads'][0]
        assert row['list_count'] == 3 and row['readers'] == 1 and row['exited_draw_lists'] == 0, data
        health = ClientHealth(process.pid, root, interval=0, render_progress=progress)
        health.sample()
        time.sleep(.15)
        frozen = observer.snapshot()['threads'][0]
        assert frozen['boundary_events'] == row['boundary_events'] and frozen['unchanged_seconds'] >= .1
        release.touch()
        output, _ = process.communicate(timeout=30)
        assert process.returncode == 0 and 'RENDER_PROBE_OK blocked-draw' in output, output
        finished = observer.snapshot()['threads'][0]
        assert finished['stage'] == 'draw_list_exit' and finished['exited_draw_lists'] == 2 and finished['readers'] == 0, finished
        assert '"render_progress"' in (root/'client-health.log').read_text()
        print('RENDER_PROGRESS_FROZEN_DRAW_OK', data, finished, flush=True)
    finally:
        release.touch()
        if process.poll() is None:process.kill();process.communicate(timeout=10)

    # Failure flags survive finally and a subsequent successful draw.
    prepare_render_progress(progress)
    result = subprocess.run(command + [str(app), 'same-thread'], env=dict(env, MEMENTO_RENDER_PROGRESS=guest(progress)),
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=90)
    assert result.returncode == 0, result.stdout
    row = RenderProgress(progress).snapshot()['threads'][0]
    assert row['writer_overlap_seen'] and row['draw_failure_seen'] and row['readers'] == 0, row
    print('RENDER_PROGRESS_STICKY_FAILURE_OK', row, flush=True)
    prepare_render_progress(progress)
    result = subprocess.run(command + [str(app), 'other-thread'], env=dict(env, MEMENTO_RENDER_PROGRESS=guest(progress)),
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=90)
    assert result.returncode == 0, result.stdout
    rows = RenderProgress(progress).snapshot()['threads']
    assert len(rows) == 2 and len({row['managed_thread'] for row in rows}) == 2, rows
    assert sum(row['writer_overlap_seen'] for row in rows) == sum(row['draw_failure_seen'] for row in rows) == 1, rows
    assert not any(row['writer_overlap_seen'] and row['draw_failure_seen'] for row in rows), rows
    print('RENDER_PROGRESS_CROSS_THREAD_OK', rows, flush=True)
    progress.unlink()
    result = subprocess.run(command + [str(app), 'normal'], env=dict(env, MEMENTO_RENDER_PROGRESS=guest(progress)),
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=90)
    assert result.returncode == 0 and 'progress=False' in result.stdout, result.stdout

print('RENDER_TRACE_VERIFIED: mutation attribution, cross-thread writes, rethrow identity, no stack formatting, blocked draw observation, finally and disabled mode')
