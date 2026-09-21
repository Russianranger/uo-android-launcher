import json
import io
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
            pe[128:134]=b'PE\0\0'+struct.pack('<H',0xaa64)
            for name in ('bin/wine','bin/wineserver','lib/wine/aarch64-windows/libarm64ecfex.dll','lib/wine/aarch64-windows/libwow64fex.dll'):
                path=root/'opt/wine'/name;path.parent.mkdir(parents=True,exist_ok=True)
                path.write_bytes(pe if name.endswith('.dll') else elf)
            before=client_runtime.inspect(root)
            self.assertEqual(len(before['binaries']),4)
            (root/'opt/wine/bin/wine').write_bytes(elf+b'changed')
            after=client_runtime.inspect(root)
            self.assertNotEqual(before['binaries']['bin/wine'],after['binaries']['bin/wine'])

    def test_x64_header_requires_real_arm64ec_metadata_and_code_range(self):
        image=bytearray(4096);image[:2]=b'MZ';struct.pack_into('<I',image,60,128)
        image[128:132]=b'PE\0\0';struct.pack_into('<HH',image,132,0x8664,1)
        struct.pack_into('<H',image,148,240)
        optional=152
        struct.pack_into('<H',image,optional,0x20b)
        struct.pack_into('<Q',image,optional+24,0x180000000)
        struct.pack_into('<I',image,optional+108,16)
        struct.pack_into('<IIII',image,optional+240+8,0xe00,0x1000,0xe00,0x200)
        with self.assertRaises(RuntimeError):client_runtime.pe_architecture(io.BytesIO(image))
        struct.pack_into('<II',image,optional+192,0x1000,208)
        struct.pack_into('<I',image,0x200,208)
        struct.pack_into('<Q',image,0x200+200,0x180001100)
        struct.pack_into('<III',image,0x300,2,0x1200,1)
        struct.pack_into('<II',image,0x400,0x1301,4)
        self.assertEqual(client_runtime.pe_architecture(io.BytesIO(image)),'arm64ec')
        struct.pack_into('<I',image,0x400,0x1302)  # x64-only code map is insufficient.
        with self.assertRaises(RuntimeError):client_runtime.pe_architecture(io.BytesIO(image))
        struct.pack_into('<Q',image,0x200+200,0x180009000)
        with self.assertRaises(RuntimeError):client_runtime.pe_architecture(io.BytesIO(image))
