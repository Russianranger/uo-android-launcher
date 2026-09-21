"""Identify the actual runtime before modifying or starting an imported client."""
import hashlib
import json
from pathlib import Path
import struct

RUNTIME_ID = 'fex-arm64ec-1'


def inspect(root=Path('/')):
    marker = json.loads((root/'etc/memento-client-runtime.json').read_text())
    if (marker.get('format'),marker.get('runtime'),marker.get('architecture')) != (2,RUNTIME_ID,'arm64'):
        raise RuntimeError('Install the FEX / ARM64EC client runtime first')
    report = dict(marker, binaries={}, translation='Windows ARM64EC FEX; native ARM64 Wine Unix libraries')
    for relative in ('bin/wine','bin/wineserver','lib/wine/aarch64-windows/libarm64ecfex.dll',
                     'lib/wine/aarch64-windows/libwow64fex.dll'):
        path = root/'opt/wine'/relative
        with path.open('rb') as source:
            header = source.read(64)
            if relative.endswith('.dll'):
                if header[:2] != b'MZ': raise RuntimeError('Invalid FEX module')
                source.seek(struct.unpack_from('<I',header,60)[0]); pe = source.read(6)
                if pe[:4] != b'PE\0\0' or int.from_bytes(pe[4:6],'little') not in (0xaa64,0xa641,0xa64e):
                    raise RuntimeError('FEX module has the wrong architecture')
            elif header[:5] != b'\x7fELF\x02' or int.from_bytes(header[18:20],'little') != 183:
                raise RuntimeError('Wine is not native ARM64; reinstall the FEX runtime')
            source.seek(0)
            digest = hashlib.sha256()
            for block in iter(lambda:source.read(1024*1024),b''): digest.update(block)
        report['binaries'][relative] = digest.hexdigest()
    return report
