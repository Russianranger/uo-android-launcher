import base64
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
import client_map_metadata as cache
from test_client_render_trace import delta


def sha(data):return hashlib.sha256(data).hexdigest()


class MapMetadataTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)/'client';self.root.mkdir()
        self.assets=Path(self.tmp.name)/'assets';self.assets.mkdir()
        (self.assets/cache.frame.HELPER).write_bytes(b'chunk helper')
        self.info={'executable':'TazUO.exe'}
        self.io=b'original file reader';self.observed_io=b'0.2.19 file reader'
        (self.root/'ClassicUO.IO.dll').write_bytes(self.io)
        qualifier=patch.object(cache,'SUPPORTED_IO',(sha(self.io),sha(self.observed_io)))
        qualifier.start();self.addCleanup(qualifier.stop)
        self.base={name:('ordinary '+name).encode() for name in cache.LIBRARIES}
        self.observed={name:('0.2.19 observed '+name).encode() for name in cache.LIBRARIES}
        self.outputs={}
        rows=[]
        for index,bases in enumerate((self.base,self.observed)):
            for name,data in bases.items():
                output=(str(index)+' optimized '+name).encode()
                patch_name='cache-'+str(index)+'-'+name+'.b64'
                (self.assets/patch_name).write_bytes(base64.b64encode(delta(output)))
                rows.append((name,sha(data),sha(output),patch_name))
                self.outputs[(name,index)]=output
        mocked=patch.object(cache.variants,'VARIANTS',tuple(rows));mocked.start();self.addCleanup(mocked.stop)
        self.rows=rows
        self.install(self.base)

    def install(self,data):
        for name,content in data.items():(self.root/name).write_bytes(content)

    def prepare(self,requested=True,eligible=True):
        return cache.prepare(self.root,self.info,self.assets,requested,eligible)

    def assert_inputs(self,inputs):
        for name,data in inputs.items():self.assertEqual((self.root/name).read_bytes(),data)

    def test_normal_and_019_diagnostic_inputs_activate_restore_and_reenable(self):
        for index,inputs in enumerate((self.base,self.observed)):
            self.install(inputs)
            self.assertEqual(self.prepare()['action'],'cached_known_client')
            self.assertEqual(self.prepare()['action'],'already_active')
            for name,data in inputs.items():
                self.assertEqual((self.root/name).read_bytes(),self.outputs[(name,index)])
                self.assertEqual(cache.backup_name(self.root/name,sha(data)).read_bytes(),data)
            self.assertTrue(cache.restore(self.root,self.info))
            self.assert_inputs(inputs)
            self.assertFalse(cache.restore(self.root,self.info))
            self.assertTrue(self.prepare()['active'])
            self.assertEqual(self.prepare(False)['action'],'restored_previous')
            self.assert_inputs(inputs)
            self.assertEqual(self.prepare(False)['action'],'disabled')

    def test_disabled_smooth_loading_restores_exact_previous_inputs(self):
        self.install(self.observed);self.prepare()
        self.assertEqual(self.prepare(eligible=False)['action'],'restored_previous')
        self.assert_inputs(self.observed)
        self.assertFalse(self.prepare(eligible=False)['active'])

    def test_unknown_client_pair_is_preserved_without_partial_activation(self):
        (self.root/'ClassicUO.Assets.dll').write_bytes(b'user client update')
        before={name:(self.root/name).read_bytes() for name in cache.LIBRARIES}
        for requested in (True,False):
            self.assertFalse(self.prepare(requested)['active'])
            self.assert_inputs(before)
        self.assertFalse(any(self.root.glob('*before-memento-map*')))

    def test_unknown_io_library_prevents_activation_without_modifying_client_pair(self):
        (self.root/'ClassicUO.IO.dll').write_bytes(b'user modified file reader')
        report=self.prepare()
        self.assertFalse(report['active']);self.assertEqual(report['action'],'unsupported')
        self.assertEqual(report['io_sha256'],sha(b'user modified file reader'))
        self.assert_inputs(self.base)
        self.assertFalse(any(self.root.glob('*before-memento-map*')))
        (self.root/'ClassicUO.IO.dll').write_bytes(self.observed_io)
        self.install(self.observed)
        self.assertTrue(self.prepare()['active'])
        self.assertEqual((self.root/'ClassicUO.IO.dll').read_bytes(),self.observed_io)

    def test_every_delta_and_backup_is_checked_before_any_replacement(self):
        (self.assets/self.rows[1][3]).write_bytes(base64.b64encode(delta(b'wrong checksum')))
        with self.assertRaisesRegex(ValueError,'checksum'):self.prepare()
        self.assert_inputs(self.base)
        self.assertFalse(any(self.root.glob('*before-memento-map*')))
        (self.assets/self.rows[1][3]).write_bytes(base64.b64encode(delta(self.outputs[('ClassicUO.Assets.dll',0)])))
        self.prepare()
        cache.backup_name(self.root/'ClassicUO.Assets.dll',sha(self.base['ClassicUO.Assets.dll'])).write_bytes(b'changed')
        before={name:(self.root/name).read_bytes() for name in cache.LIBRARIES}
        with self.assertRaisesRegex(ValueError,'backup'):cache.restore(self.root,self.info)
        self.assert_inputs(before)
        with self.assertRaisesRegex(ValueError,'backup'):self.prepare()
        self.assert_inputs(before)

    def test_interrupted_activation_and_restoration_recover_idempotently(self):
        real=cache.trace.atomic_write
        second=self.root/'ClassicUO.Assets.dll'
        def fail_second(target,data,expected):
            if target==second:raise OSError('interrupted second replacement')
            real(target,data,expected)
        with patch.object(cache.trace,'atomic_write',side_effect=fail_second):
            with self.assertRaises(OSError):self.prepare()
        self.assertEqual((self.root/'TazUO.dll').read_bytes(),self.outputs[('TazUO.dll',0)])
        self.assertEqual(second.read_bytes(),self.base['ClassicUO.Assets.dll'])
        self.assertTrue(cache.restore(self.root,self.info))
        self.assert_inputs(self.base)
        self.prepare()
        with patch.object(cache.trace,'atomic_write',side_effect=fail_second):
            with self.assertRaises(OSError):cache.restore(self.root,self.info)
        self.assertEqual((self.root/'TazUO.dll').read_bytes(),self.base['TazUO.dll'])
        self.assertTrue(cache.restore(self.root,self.info))
        self.assert_inputs(self.base)
        self.assertFalse(cache.restore(self.root,self.info))

    def test_missing_backup_cannot_silently_restore_or_reactivate(self):
        self.prepare()
        cache.backup_name(self.root/'ClassicUO.Assets.dll',sha(self.base['ClassicUO.Assets.dll'])).unlink()
        before={name:(self.root/name).read_bytes() for name in cache.LIBRARIES}
        for operation in (lambda:self.prepare(),lambda:self.prepare(False),lambda:cache.restore(self.root,self.info)):
            with self.assertRaisesRegex(ValueError,'backup'):operation()
            self.assert_inputs(before)

    def test_unknown_updated_assembly_is_not_overwritten_during_outer_restore(self):
        self.prepare();(self.root/'ClassicUO.Assets.dll').write_bytes(b'user updated assembly')
        self.assertTrue(cache.restore(self.root,self.info))
        self.assertEqual((self.root/'ClassicUO.Assets.dll').read_bytes(),b'user updated assembly')
        self.assertEqual((self.root/'TazUO.dll').read_bytes(),self.base['TazUO.dll'])

    def test_library_backup_paths_duplicates_and_options(self):
        with self.assertRaisesRegex(ValueError,'option'):self.prepare('true')
        with self.assertRaisesRegex(ValueError,'option'):self.prepare(eligible=1)
        (self.root/'tazuo.DLL').write_bytes(b'duplicate')
        with self.assertRaisesRegex(ValueError,'Duplicate'):self.prepare()
        (self.root/'tazuo.DLL').unlink()
        first=self.root/'TazUO.dll';first.unlink();first.symlink_to(self.assets/cache.frame.HELPER)
        with self.assertRaisesRegex(ValueError,'symbolic'):self.prepare()
        first.unlink();first.write_bytes(self.base['TazUO.dll'])
        backup=cache.backup_name(first,sha(self.base['TazUO.dll']));backup.symlink_to(first)
        with self.assertRaisesRegex(ValueError,'backup'):self.prepare()
        self.assert_inputs(self.base)

    def test_missing_helper_prevents_any_activation(self):
        (self.assets/cache.frame.HELPER).unlink()
        with self.assertRaisesRegex(ValueError,'component is missing'):self.prepare()
        self.assert_inputs(self.base)
        self.assertFalse(any(self.root.glob('*before-memento-map*')))


if __name__=='__main__':unittest.main()
