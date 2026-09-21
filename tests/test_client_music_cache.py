import base64
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
import client_music_cache as music
from test_client_render_trace import delta

class MusicCacheTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)/'client';self.root.mkdir()
        self.assets=Path(self.tmp.name)/'assets';self.assets.mkdir()
        self.original,self.cached=b'original music library',b'cached music library'
        for key,data in (('ORIGINAL',self.original),('CACHED',self.cached)):
            p=patch.object(music,key,hashlib.sha256(data).hexdigest());p.start();self.addCleanup(p.stop)
        self.target=self.root/music.LIBRARY;self.target.write_bytes(self.original)
        (self.assets/music.PATCH).write_bytes(base64.b64encode(delta(self.cached)))
        self.metadata={'executable':'TazUO.exe'}
    def prepare(self,enabled=True):return music.prepare(self.root,self.metadata,self.assets,enabled)
    def test_apply_idempotence_restore_and_independent_render_dll(self):
        client=self.root/'TazUO.dll';client.write_bytes(b'render instrumented client')
        self.assertEqual(self.prepare()['action'],'cached_known_client')
        self.assertEqual(self.prepare()['action'],'already_cached')
        self.assertEqual((self.root/music.BACKUP).read_bytes(),self.original)
        self.assertEqual(self.prepare(False)['action'],'restored_original')
        self.assertEqual(self.target.read_bytes(),self.original)
        self.assertEqual(client.read_bytes(),b'render instrumented client')
    def test_unknown_updated_client_is_not_replaced(self):
        self.prepare();self.target.write_bytes(b'user updated assets')
        for enabled in (True,False):
            self.assertFalse(self.prepare(enabled)['active'])
            self.assertEqual(self.target.read_bytes(),b'user updated assets')
    def test_corrupt_delta_or_failed_commit_keeps_original(self):
        (self.assets/music.PATCH).write_bytes(base64.b64encode(delta(b'wrong output')))
        with self.assertRaisesRegex(ValueError,'checksum'):self.prepare()
        self.assertEqual(self.target.read_bytes(),self.original)
        self.assertFalse((self.root/music.BACKUP).exists())
        (self.assets/music.PATCH).write_bytes(base64.b64encode(delta(self.cached)))
        real=music.atomic_write
        def write(target,data,expected):
            if target==self.target:raise OSError('interrupted replacement')
            real(target,data,expected)
        with patch.object(music,'atomic_write',side_effect=write):
            with self.assertRaises(OSError):self.prepare()
        self.assertEqual(self.target.read_bytes(),self.original)
        self.assertEqual((self.root/music.BACKUP).read_bytes(),self.original)
        self.assertTrue(self.prepare()['active'])
    def test_backups_paths_and_boolean_option(self):
        (self.root/music.BACKUP).symlink_to(self.target)
        with self.assertRaises(ValueError):self.prepare()
        (self.root/music.BACKUP).unlink()
        self.prepare();(self.root/music.BACKUP).unlink()
        with self.assertRaisesRegex(ValueError,'backup'):self.prepare(False)
        with self.assertRaisesRegex(ValueError,'option'):self.prepare('false')
        (self.root/'classicuO.ASSETS.dll').touch()
        with self.assertRaisesRegex(ValueError,'Duplicate'):self.prepare()
