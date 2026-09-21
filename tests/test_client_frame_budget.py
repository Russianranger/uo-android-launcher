import base64
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
import client_frame_budget as frame
import client_render_trace as trace
from test_client_render_trace import delta


class FramePatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)/'client';self.root.mkdir()
        self.assets=Path(self.tmp.name)/'assets';self.assets.mkdir()
        self.states={(False,False):b'original',(False,True):b'render',(True,False):b'budget',(True,True):b'combined'}
        for module,key,data in [(trace,'ORIGINAL',b'original'),(trace,'INSTRUMENTED',b'render'),(trace,'FNA',b'fna'),(frame,'BUDGET',b'budget'),(frame,'COMBINED',b'combined')]:
            p=patch.object(module,key,hashlib.sha256(data).hexdigest());p.start();self.addCleanup(p.stop)
        for name,data in [(trace.PATCH,b'render'),(frame.PATCH,b'budget'),(frame.COMBINED_PATCH,b'combined')]:
            (self.assets/name).write_bytes(base64.b64encode(delta(data)))
        for name in [frame.HELPER,trace.HELPER]:(self.assets/name).write_bytes(b'helper')
        (self.root/'TazUO.dll').write_bytes(b'original');(self.root/'FNA.dll').write_bytes(b'fna')
        self.info={'executable':'TazUO.exe'}
    def prepare(self,enabled=True,render=False):return frame.prepare(self.root,self.info,self.assets,enabled,render)
    def test_all_toggle_combinations_and_idempotence(self):
        for before in self.states:
            self.prepare(*before)
            for after,data in self.states.items():
                result=self.prepare(*after)
                self.assertEqual((self.root/'TazUO.dll').read_bytes(),data)
                self.assertEqual(result['frame_budget']['active'],after[0]);self.assertEqual(result['render_trace']['active'],after[1])
                with patch.object(trace,'atomic_write',side_effect=AssertionError('Unnecessary rewrite')):self.prepare(*after)
                self.prepare(*before)
        for name in [frame.BACKUP,trace.BACKUP]:self.assertEqual((self.root/name).read_bytes(),b'original')
    def test_upgrade_from_old_render_patch(self):
        trace.prepare(self.root,self.info,self.assets,True)
        self.assertTrue(self.prepare(True,True)['frame_budget']['active'])
        self.prepare(False,True);self.assertEqual((self.root/'TazUO.dll').read_bytes(),b'render')
        self.prepare(False,False);self.assertEqual((self.root/'TazUO.dll').read_bytes(),b'original')
    def test_unknown_upstream_update_never_overwritten(self):
        self.prepare();(self.root/'TazUO.dll').write_bytes(b'upstream update')
        for choice in self.states:
            self.assertFalse(self.prepare(*choice)['frame_budget']['active'])
            self.assertEqual((self.root/'TazUO.dll').read_bytes(),b'upstream update')
    def test_changed_fna_restores_only_our_known_patch(self):
        self.prepare(True,True);(self.root/'FNA.dll').write_bytes(b'new fna')
        result=self.prepare(True,True)
        self.assertFalse(result['frame_budget']['active']);self.assertFalse(result['render_trace']['active'])
        self.assertEqual((self.root/'TazUO.dll').read_bytes(),b'original')
    def test_corrupt_delta_and_missing_helper_preserve_original(self):
        (self.assets/frame.HELPER).unlink()
        with self.assertRaisesRegex(ValueError,'component is missing'):self.prepare()
        (self.assets/frame.HELPER).touch();(self.assets/frame.PATCH).write_bytes(base64.b64encode(delta(b'wrong')))
        with self.assertRaisesRegex(ValueError,'output checksum'):self.prepare()
        self.assertEqual((self.root/'TazUO.dll').read_bytes(),b'original');self.assertFalse((self.root/frame.BACKUP).exists())
    def test_missing_changed_and_symlink_backups(self):
        self.prepare();(self.root/frame.BACKUP).unlink()
        with self.assertRaisesRegex(ValueError,'backup is missing'):self.prepare(False)
        (self.root/frame.BACKUP).write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'backup is missing or changed'):self.prepare(False)
        (self.root/frame.BACKUP).unlink();(self.root/frame.BACKUP).symlink_to(self.root/'TazUO.dll')
        with self.assertRaisesRegex(ValueError,'backup is missing or changed'):self.prepare(False)
    def test_atomic_failure_keeps_a_recoverable_original(self):
        replace=trace.os.replace
        def fail(src,dst):
            if dst.name=='TazUO.dll':raise OSError('storage failure')
            replace(src,dst)
        with patch.object(trace.os,'replace',side_effect=fail):
            with self.assertRaises(OSError):self.prepare()
        self.assertEqual((self.root/'TazUO.dll').read_bytes(),b'original')
        self.assertEqual((self.root/frame.BACKUP).read_bytes(),b'original')
        self.assertTrue(self.prepare()['frame_budget']['active'])
    def test_invalid_options_and_duplicate_libraries(self):
        for args in [('yes',False),(True,'yes')]:
            with self.assertRaises(ValueError):self.prepare(*args)
        (self.root/'tazuo.DLL').touch()
        with self.assertRaisesRegex(ValueError,'Duplicate'):self.prepare()
