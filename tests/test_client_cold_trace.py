import base64
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
import client_atlas_uploads as atlas
import client_cold_trace as cold
import client_frame_budget as frame
import client_cold_resources as resources
import client_graphics as graphics
from test_client_render_trace import delta

def sha(data):return hashlib.sha256(data).hexdigest()

class ColdTraceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/'client';self.root.mkdir()
        self.assets=Path(self.temp.name)/'assets';self.assets.mkdir()
        self.session=Path(self.temp.name)/'session';self.session.mkdir()
        self.info={'executable':'TazUO.exe'}
        self.base=b'atlas fna';self.legacy=b'diagnostic fna';self.diagnostic=b'resource fna';self.original=b'original fna'
        for module,name,data in ((atlas,'FNA_PATCHED',self.base),(atlas,'FNA_ORIGINAL',self.original),(cold,'PATCHED',self.legacy)):
            mock=patch.object(module,name,sha(data));mock.start();self.addCleanup(mock.stop)
        (self.root/'FNA.dll').write_bytes(self.base)
        (self.root/'SDL3.dll').write_bytes(b'original sdl')
        mock=patch.object(graphics,'ORIGINAL_SDL',sha(b'original sdl'));mock.start();self.addCleanup(mock.stop)
        (self.root/('FNA.dll'+atlas.BACKUP_SUFFIX)).write_bytes(self.original)
        (self.assets/frame.HELPER).write_bytes(b'helper')
        (self.assets/cold.LIBRARY).write_bytes(b'observer')
        (self.assets/'vulkan-trace-bundle.json').write_text(json.dumps({'format':1,'revision':2,'sha256':sha(b'observer')}))
        (self.assets/cold.PATCH).write_bytes(base64.b64encode(delta(self.legacy)))
        self.variants=[];self.bases={};self.outputs={}
        for index,name in enumerate(('TazUO.dll','ClassicUO.Assets.dll','ClassicUO.IO.dll','ClassicUO.Renderer.dll','FNA.dll')):
            base=self.legacy if name=='FNA.dll' else ('base '+name).encode()
            output=self.diagnostic if name=='FNA.dll' else ('resource '+name).encode()
            patch_name='resource-'+str(index)+'.b64'
            self.variants.append((name,sha(base),sha(output),patch_name))
            self.bases[name]=self.base if name=='FNA.dll' else base;self.outputs[name]=output
            if name!='FNA.dll':(self.root/name).write_bytes(base)
            (self.assets/patch_name).write_bytes(base64.b64encode(delta(output)))
        mock=patch.object(resources,'VARIANTS',tuple(self.variants));mock.start();self.addCleanup(mock.stop)
    def prepare(self,requested=True,eligible=True):return cold.prepare(self.root,self.info,self.assets,self.session,requested,eligible)
    def test_activation_restoration_and_repeated_option_changes(self):
        report=self.prepare();self.assertTrue(report['active'])
        self.assertEqual(report['revision'],3);self.assertEqual(report['native_revision'],2)
        self.assertEqual((self.root/'FNA.dll').read_bytes(),self.diagnostic)
        layer=json.loads((self.session/'vulkan-trace/memento-cold-trace.json').read_text())
        self.assertEqual(layer['layer']['library_path'],str(self.assets/cold.LIBRARY))
        self.assertTrue(cold.restore(self.root,self.info));self.assertFalse(cold.restore(self.root,self.info))
        self.assertEqual((self.root/'FNA.dll').read_bytes(),self.base)
        self.assertFalse(self.prepare(False)['active']);self.assertTrue(self.prepare()['active'])
        cold.restore(self.root,self.info);self.assertFalse(self.prepare(eligible=False)['active'])
        self.assertEqual((self.root/('FNA.dll'+atlas.BACKUP_SUFFIX)).read_bytes(),self.original)
    def test_unknown_clients_disabled_option_and_symlinks(self):
        (self.root/'FNA.dll').write_bytes(b'custom')
        self.assertFalse(cold.restore(self.root,self.info));self.assertFalse(self.prepare()['active'])
        self.assertEqual((self.root/'FNA.dll').read_bytes(),b'custom')
        (self.root/'FNA.dll').unlink();(self.root/'FNA.dll').symlink_to(self.root/('FNA.dll'+atlas.BACKUP_SUFFIX))
        with self.assertRaisesRegex(ValueError,'symbolic'):cold.restore(self.root,self.info)
    def test_corrupt_delta_or_observer_never_modifies_the_client(self):
        (self.assets/cold.PATCH).write_bytes(base64.b64encode(delta(b'wrong output')))
        with self.assertRaisesRegex(ValueError,'checksum'):self.prepare()
        self.assertEqual((self.root/'FNA.dll').read_bytes(),self.base)
        (self.assets/cold.LIBRARY).write_bytes(b'changed observer')
        with self.assertRaisesRegex(ValueError,'verification'):self.prepare()
    def test_original_backups_are_required_for_restore(self):
        self.prepare();(self.root/('FNA.dll'+atlas.BACKUP_SUFFIX)).write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'Original atlas'):cold.restore(self.root,self.info)
        self.assertEqual((self.root/'FNA.dll').read_bytes(),self.diagnostic)
    def test_invalid_option_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'Invalid'):self.prepare('true')
    def test_legacy_016_diagnostic_upgrade_and_partial_restore(self):
        (self.root/'FNA.dll').write_bytes(self.legacy)
        (self.root/('FNA.dll'+cold.BACKUP_SUFFIX)).write_bytes(self.base)
        self.assertTrue(cold.restore(self.root,self.info));self.assertEqual((self.root/'FNA.dll').read_bytes(),self.base)
        self.prepare()
        name,base,output,_=self.variants[0]
        (self.root/name).write_bytes(self.bases[name])
        self.assertTrue(cold.restore(self.root,self.info))
        for name,base in self.bases.items():self.assertEqual((self.root/name).read_bytes(),base)
        self.assertFalse(cold.restore(self.root,self.info))
    def test_restore_preflights_all_backups_before_modifying_any_component(self):
        self.prepare();name,base,output,_=self.variants[1]
        resources.backup_name(self.root/name,base).write_bytes(b'changed backup')
        with self.assertRaisesRegex(ValueError,'backup'):cold.restore(self.root,self.info)
        for name,output in self.outputs.items():self.assertEqual((self.root/name).read_bytes(),output)
    def test_corrupt_resource_delta_or_unknown_library_does_not_modify_any_component(self):
        (self.assets/self.variants[-2][3]).write_bytes(base64.b64encode(delta(b'wrong')))
        with self.assertRaisesRegex(ValueError,'checksum'):self.prepare()
        for name,base in self.bases.items():self.assertEqual((self.root/name).read_bytes(),base)
        (self.root/'ClassicUO.Assets.dll').write_bytes(b'custom assets')
        self.assertEqual(self.prepare()['action'],'unsupported')
        self.assertEqual((self.root/'ClassicUO.Assets.dll').read_bytes(),b'custom assets')
    def test_interrupted_activation_is_repaired_on_next_launch(self):
        real=cold.trace.atomic_write
        def interrupted(path,data,expected):
            real(path,data,expected)
            if path.name=='ClassicUO.Assets.dll':raise OSError('simulated process interruption')
        with patch.object(cold.trace,'atomic_write',side_effect=interrupted):
            with self.assertRaisesRegex(OSError,'interruption'):self.prepare()
        self.assertTrue(cold.restore(self.root,self.info))
        for name,base in self.bases.items():self.assertEqual((self.root/name).read_bytes(),base)
        self.assertTrue(self.prepare()['active'])
    def test_earlier_observer_manifest_is_rejected_before_mutation(self):
        (self.assets/'vulkan-trace-bundle.json').write_text(json.dumps({'format':1,'revision':1,'sha256':sha(b'observer')}))
        with self.assertRaisesRegex(ValueError,'verification'):self.prepare()
        for name,base in self.bases.items():self.assertEqual((self.root/name).read_bytes(),base)
    def test_updated_sdl_cannot_activate_the_cold_resource_observer(self):
        (self.root/'SDL3.dll').write_bytes(b'updated sdl')
        self.assertEqual(self.prepare()['action'],'unsupported')
        for name,base in self.bases.items():self.assertEqual((self.root/name).read_bytes(),base)

if __name__=='__main__':unittest.main()
