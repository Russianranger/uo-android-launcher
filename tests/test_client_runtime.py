import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
import client_runtime


class RuntimeIdentityTests(unittest.TestCase):
    def test_wrong_architecture_and_legacy_marker_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'etc').mkdir()
            marker=root/'etc/memento-client-runtime.json'
            marker.write_text(json.dumps({'format':2,'runtime':client_runtime.RUNTIME_ID,'architecture':'arm64'}))
            wine=root/'opt/wine/bin/wine';wine.parent.mkdir(parents=True)
            header=bytearray(64);header[:5]=b'\x7fELF\x02';header[18:20]=struct.pack('<H',62)
            wine.write_bytes(header)
            with self.assertRaisesRegex(RuntimeError,'not native ARM64'):client_runtime.inspect(root)
            marker.write_text(json.dumps({'format':1,'runtime':'client-1.0','architecture':'arm64'}))
            with self.assertRaisesRegex(RuntimeError,'Install the FEX'):client_runtime.inspect(root)

    def test_native_runtime_records_real_binary_hashes(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'etc').mkdir()
            (root/'etc/memento-client-runtime.json').write_text(json.dumps(
                {'format':2,'runtime':client_runtime.RUNTIME_ID,'architecture':'arm64'}))
            elf=bytearray(64);elf[:5]=b'\x7fELF\x02';elf[18:20]=struct.pack('<H',183)
            pe=bytearray(134);pe[:2]=b'MZ';pe[60:64]=struct.pack('<I',128)
            pe[128:134]=b'PE\0\0'+struct.pack('<H',0xa641)
            for name in ('bin/wine','bin/wineserver','lib/wine/aarch64-windows/libarm64ecfex.dll','lib/wine/aarch64-windows/libwow64fex.dll'):
                path=root/'opt/wine'/name;path.parent.mkdir(parents=True,exist_ok=True)
                path.write_bytes(pe if name.endswith('.dll') else elf)
            before=client_runtime.inspect(root)
            self.assertEqual(len(before['binaries']),4)
            (root/'opt/wine/bin/wine').write_bytes(elf+b'changed')
            after=client_runtime.inspect(root)
            self.assertNotEqual(before['binaries']['bin/wine'],after['binaries']['bin/wine'])
