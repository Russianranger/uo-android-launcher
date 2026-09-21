"""Identify the actual runtime before modifying or starting an imported client."""
import hashlib
import json
from pathlib import Path
import struct

RUNTIME_ID = 'fex-arm64ec-1'


def pe_architecture(source):
    """Recognize linked ARM64EC PE images, whose machine field is AMD64.

    Microsoft documents the final-image header; LLVM's chpe_range_entry uses
    the low two range-address bits (1 = ARM64EC). Ordinary x64 is rejected.
    https://learn.microsoft.com/en-us/windows/arm/arm64ec
    """
    source.seek(0, 2); length = source.tell()
    def read(offset, size):
        if offset < 0 or size < 0 or offset + size > length:
            raise RuntimeError('Invalid FEX PE bounds')
        source.seek(offset); return source.read(size)
    def value(fmt, offset):
        return struct.unpack(fmt, read(offset, struct.calcsize(fmt)))[0]
    if read(0, 2) != b'MZ': raise RuntimeError('Invalid FEX module')
    pe = value('<I', 60)
    if read(pe, 4) != b'PE\0\0': raise RuntimeError('Invalid FEX PE signature')
    machine = value('<H', pe+4)
    if machine == 0xaa64: return 'arm64'
    if machine != 0x8664: raise RuntimeError('FEX module has the wrong architecture')
    optional, optional_size, count = pe+24, value('<H', pe+20), value('<H', pe+6)
    if optional_size < 200 or not 1 <= count <= 96 or value('<H', optional) != 0x20b:
        raise RuntimeError('Invalid FEX PE optional header')
    if value('<I', optional+108) <= 10:
        raise RuntimeError('FEX x64 header has no ARM64EC metadata')
    sections = read(optional+optional_size, count*40)
    def offset(rva, size):
        for start in range(0, len(sections), 40):
            address, raw_size, raw = struct.unpack_from('<III', sections, start+12)
            if address <= rva and rva+size <= address+raw_size:
                return raw+rva-address
        raise RuntimeError('FEX ARM64EC metadata is outside file sections')
    config_rva, config_size = struct.unpack('<II', read(optional+192, 8))
    if config_size < 208:
        raise RuntimeError('FEX x64 header has no ARM64EC load configuration')
    config = offset(config_rva, 208)
    if value('<I', config) < 208:
        raise RuntimeError('Incomplete FEX load configuration')
    metadata = offset(value('<Q', config+200)-value('<Q', optional+24), 12)
    version, code_map, ranges = struct.unpack('<III', read(metadata, 12))
    if version == 0 or not 1 <= ranges <= 65536:
        raise RuntimeError('Invalid FEX ARM64EC code map')
    entries = read(offset(code_map, ranges*8), ranges*8)
    for start, size in struct.iter_unpack('<II', entries):
        if start & 3 == 1 and size > 0:
            read(offset(start & ~3, 4), 4)
            return 'arm64ec'
    raise RuntimeError('FEX x64 module contains no ARM64EC code')


def inspect(root=Path('/')):
    marker = json.loads((root/'etc/memento-client-runtime.json').read_text())
    if (marker.get('format'),marker.get('runtime'),marker.get('architecture')) != (2,RUNTIME_ID,'arm64'):
        raise RuntimeError('Install the FEX / ARM64EC client runtime first')
    report = dict(marker, binaries={}, binary_architectures={}, translation='Windows ARM64EC FEX; native ARM64 Wine Unix libraries')
    for relative in ('bin/wine','bin/wineserver','lib/wine/aarch64-windows/libarm64ecfex.dll',
                     'lib/wine/aarch64-windows/libwow64fex.dll'):
        path = root/'opt/wine'/relative
        with path.open('rb') as source:
            header = source.read(64)
            if relative.endswith('.dll'):
                report['binary_architectures'][relative] = pe_architecture(source)
            elif header[:5] != b'\x7fELF\x02' or int.from_bytes(header[18:20],'little') != 183:
                raise RuntimeError('Wine is not native ARM64; reinstall the FEX runtime')
            source.seek(0)
            digest = hashlib.sha256()
            for block in iter(lambda:source.read(1024*1024),b''): digest.update(block)
        report['binaries'][relative] = digest.hexdigest()
    return report
