#!/usr/bin/env python3
"""Convert Docker export to the GNU tar subset supported by the Android installer."""
import hashlib
import json
import os
from pathlib import Path
import sys
import tarfile
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'backend'))
from client_runtime import pe_architecture

source, output = map(Path, sys.argv[1:])
marker = None
native = set()
fex = set()
with tarfile.open(source, 'r|') as src, tarfile.open(output, 'w:gz', format=tarfile.GNU_FORMAT) as dst:
    for member in src:
        if not (member.isfile() or member.isdir() or member.issym() or member.islnk()): continue
        name = member.name.removeprefix('./')
        if name.startswith('/') or '..' in Path(name).parts: raise ValueError('Unsafe runtime entry')
        if name.split('/')[0] in ('dev', 'proc', 'sys') and '/' in name.rstrip('/'): continue
        if name.endswith('/box64') or 'x86_64-unix' in name:
            raise ValueError('Legacy x64 runtime leaked into FEX package')
        stream = src.extractfile(member) if member.isfile() else None
        if stream and (name == 'etc/memento-client-runtime.json' or name in (
                'opt/wine/bin/wine', 'opt/wine/bin/wineserver') or name.endswith(('libarm64ecfex.dll','libwow64fex.dll'))):
            import io
            data = stream.read(); stream = io.BytesIO(data)
            if name.endswith('.json'): marker = json.loads(data)
            elif name.endswith('.dll'):
                print(name, pe_architecture(stream), flush=True)
                stream.seek(0)
                fex.add(Path(name).name)
            else:
                if data[:5] != b'\x7fELF\x02' or int.from_bytes(data[18:20], 'little') != 183:
                    raise ValueError('Wine must execute natively on ARM64')
                native.add(Path(name).name)
        member.uid = member.gid = 0
        member.uname = member.gname = 'root'
        member.mode &= 0o777
        dst.addfile(member, stream)
if native != {'wine','wineserver'} or fex != {'libarm64ecfex.dll','libwow64fex.dll'}:
    raise ValueError('Required native Wine/FEX binaries missing')
if not marker or (marker.get('format'),marker.get('runtime'),marker.get('architecture')) != (2,'fex-arm64ec-1','arm64'):
    raise ValueError('Incorrect FEX runtime marker')
digest = hashlib.file_digest(output.open('rb'), 'sha256').hexdigest()
marker.update(file=output.name,sha256=digest,bytes=output.stat().st_size,
              source_commit=os.environ.get('GITHUB_SHA','local'))
output.with_name('client-runtime-manifest.json').write_text(json.dumps(marker,indent=2)+'\n')
print(json.dumps(marker))
