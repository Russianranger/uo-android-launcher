"""Preflight the selected PRoot mode without starting Wine or changing game files."""
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time


def probe(session=Path('/session')):
    started = time.monotonic()
    data = bytes(range(256)) * 2048
    timings = {}
    with tempfile.TemporaryDirectory(prefix='io-probe-', dir=session) as temporary:
        path = Path(temporary) / 'blocks.bin'
        path.write_bytes(data)
        begin = time.monotonic()
        with path.open('rb', buffering=0) as stream:
            for i in range(1024):
                offset = (i * 4096) % len(data)
                stream.seek(offset)
                if stream.read(4096) != data[offset:offset+4096]: raise RuntimeError('File read mismatch')
        timings['seek_read_1024'] = round(time.monotonic() - begin, 4)
        begin = time.monotonic()
        for _ in range(256):
            if path.stat().st_size != len(data): raise RuntimeError('File metadata mismatch')
        timings['stat_256'] = round(time.monotonic() - begin, 4)
        left, right = socket.socketpair()
        with left, right:
            left.settimeout(2); right.settimeout(2)
            left.sendall(b'trasc-runtime')
            received = b''
            while len(received) < 13:
                chunk = right.recv(13-len(received))
                if not chunk: raise RuntimeError('Socket closed')
                received += chunk
            if received != b'trasc-runtime': raise RuntimeError('Socket exchange failed')
        child = subprocess.run([sys.executable, '-c',
            'import hashlib,pathlib,sys;print(hashlib.sha256(pathlib.Path(sys.argv[1]).read_bytes()).hexdigest())', str(path)],
            capture_output=True, text=True, timeout=5, check=True)
        if child.stdout.strip() != hashlib.sha256(data).hexdigest(): raise RuntimeError('Child-process read failed')
    try: affinity = sorted(os.sched_getaffinity(0))
    except (OSError, AttributeError): affinity = []
    report = {'ok': True, 'seconds': round(time.monotonic()-started, 4),
              'timings_seconds': timings, 'available_cpu_ids': affinity}
    (session / 'runtime-probe.json').write_text(json.dumps(report, indent=2))
    print('TRASC runtime probe passed', flush=True)
    print(json.dumps(report), flush=True)
    return report


if __name__ == '__main__': probe()
