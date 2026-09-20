import base64
import bz2
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'backend'))
import client_render_trace as trace


def number(value):
    return (abs(value) | ((1 << 63) if value < 0 else 0)).to_bytes(8, 'little')


def delta(new):
    control = bz2.compress(number(0) + number(len(new)) + number(0))
    diff = bz2.compress(b'')
    return b'BSDIFF40' + number(len(control)) + number(len(diff)) + number(len(new)) + control + diff + bz2.compress(new)


class RenderTraceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)/'client';self.root.mkdir()
        self.assets = Path(self.tmp.name)/'assets';self.assets.mkdir()
        self.original, self.updated, self.fna = b'original client', b'instrumented client', b'original fna'
        for constant, data in (('ORIGINAL', self.original), ('INSTRUMENTED', self.updated), ('FNA', self.fna)):
            p = patch.object(trace, constant, hashlib.sha256(data).hexdigest());p.start();self.addCleanup(p.stop)
        (self.root/'TazUO.dll').write_bytes(self.original)
        (self.root/'FNA.dll').write_bytes(self.fna)
        (self.assets/trace.HELPER).write_bytes(b'helper fixture')
        (self.assets/trace.PATCH).write_bytes(base64.b64encode(delta(self.updated)))
        self.info = {'executable':'TazUO.exe'}

    def prepare(self, enabled=True):return trace.prepare(self.root, self.info, self.assets, enabled)

    def test_exact_match_patch_idempotence_and_restore(self):
        self.assertEqual(self.prepare()['action'], 'instrumented_known_client')
        self.assertEqual((self.root/trace.BACKUP).read_bytes(), self.original)
        self.assertEqual((self.root/'TazUO.dll').read_bytes(), self.updated)
        self.assertTrue(self.prepare()['active'])
        self.assertEqual(self.prepare(False)['action'], 'restored_original')
        self.assertEqual((self.root/'TazUO.dll').read_bytes(), self.original)
        self.assertTrue(self.prepare()['active'])

    def test_unknown_dll_or_fna_never_patched(self):
        for name in ('TazUO.dll', 'FNA.dll'):
            target = self.root/name;old = target.read_bytes();target.write_bytes(b'newer client')
            self.assertEqual(self.prepare()['action'], 'unchanged_unrecognized_client')
            self.assertFalse((self.root/trace.BACKUP).exists())
            target.write_bytes(old)
        self.prepare();(self.root/'FNA.dll').write_bytes(b'newer fna')
        self.assertEqual(self.prepare()['action'], 'restored_original')

    def test_missing_helper_and_corrupt_patch_preserve_original(self):
        (self.assets/trace.HELPER).unlink()
        with self.assertRaisesRegex(ValueError, 'component is missing'):self.prepare()
        (self.assets/trace.HELPER).touch()
        (self.assets/trace.PATCH).write_bytes(base64.b64encode(delta(b'wrong result')))
        with self.assertRaisesRegex(ValueError, 'output checksum'):self.prepare()
        self.assertEqual((self.root/'TazUO.dll').read_bytes(), self.original)
        self.assertFalse((self.root/trace.BACKUP).exists())

    def test_backup_conflict_and_symlink_are_rejected(self):
        (self.root/trace.BACKUP).write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'backup has changed'):self.prepare()
        (self.root/trace.BACKUP).unlink();(self.root/trace.BACKUP).symlink_to(self.root/'TazUO.dll')
        with self.assertRaisesRegex(ValueError, 'backup has changed'):self.prepare()
        (self.root/trace.BACKUP).unlink()
        (self.root/'tazuo.DLL').touch()
        with self.assertRaisesRegex(ValueError, 'Duplicate client library'):self.prepare()

    def test_failed_commit_leaves_recoverable_original(self):
        real_replace = trace.os.replace
        def replace(src, dst):
            if dst.name == 'TazUO.dll':raise OSError('storage failure')
            real_replace(src, dst)
        with patch.object(trace.os, 'replace', side_effect=replace):
            with self.assertRaises(OSError):self.prepare()
        self.assertEqual((self.root/'TazUO.dll').read_bytes(), self.original)
        self.assertEqual((self.root/trace.BACKUP).read_bytes(), self.original)
        self.assertEqual(len(list(self.root.glob('.memento-render-*'))), 0)
        self.assertTrue(self.prepare()['active'])

    def test_delta_add_copy_and_backward_seek(self):
        control = bz2.compress(b''.join(number(x) for x in (2,3,-2,2,0,0)))
        diff = bz2.compress(bytes((1,0,0,0)))
        data = b'BSDIFF40'+number(len(control))+number(len(diff))+number(7)+control+diff+bz2.compress(b'XYZ')
        self.assertEqual(trace.apply_delta(b'abcde', data), b'bbXYZab')
        for bad in (b'bad', data[:28], data[:-5], data[:24]+number(trace.LIMIT+1)+data[32:]):
            with self.assertRaises((ValueError, EOFError, OSError)):trace.apply_delta(b'abcde', bad)
        with self.assertRaises(ValueError):trace.apply_delta(b'abcde', data+b'trailing')

    def test_option_must_be_boolean(self):
        with self.assertRaisesRegex(ValueError, 'option'):self.prepare('false')
