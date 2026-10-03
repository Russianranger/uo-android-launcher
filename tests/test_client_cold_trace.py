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
from test_client_render_trace import delta

def sha(data):return hashlib.sha256(data).hexdigest()

class ColdTraceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/'client';self.root.mkdir()
        self.assets=Path(self.temp.name)/'assets';self.assets.mkdir()
        self.session=Path(self.temp.name)/'session';self.session.mkdir()
        self.info={'executable':'TazUO.exe'}
        self.base=b'atlas fna';self.diagnostic=b'diagnostic fna';self.original=b'original fna'
        for module,name,data in ((atlas,'FNA_PATCHED',self.base),(atlas,'FNA_ORIGINAL',self.original),(cold,'PATCHED',self.diagnostic)):
            mock=patch.object(module,name,sha(data));mock.start();self.addCleanup(mock.stop)
        (self.root/'FNA.dll').write_bytes(self.base)
        (self.root/('FNA.dll'+atlas.BACKUP_SUFFIX)).write_bytes(self.original)
        (self.assets/frame.HELPER).write_bytes(b'helper')
        (self.assets/cold.LIBRARY).write_bytes(b'observer')
        (self.assets/'vulkan-trace-bundle.json').write_text(json.dumps({'format':1,'revision':1,'sha256':sha(b'observer')}))
        (self.assets/cold.PATCH).write_bytes(base64.b64encode(delta(self.diagnostic)))
    def prepare(self,requested=True,eligible=True):return cold.prepare(self.root,self.info,self.assets,self.session,requested,eligible)
    def test_activation_restoration_and_repeated_option_changes(self):
        self.assertTrue(self.prepare()['active'])
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

if __name__=='__main__':unittest.main()
