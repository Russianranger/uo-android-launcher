from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'backend'))
import client_graphics as graphics


class GraphicsTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.client = self.root/'imported client';self.client.mkdir()
        self.assets = self.root/'runtime';self.assets.mkdir()
        self.info = {'executable':'TazUO.exe', 'architecture':'x64'}
        self.sdl = self.client/'sdl3.dll';self.sdl.write_bytes(b'original SDL')
        self.fna = self.client/'FNA3D.dll';self.fna.write_bytes(b'known FNA')
        self.source = self.assets/graphics.ASSET;self.source.write_bytes(b'updated SDL')
        for name, path in [('ORIGINAL_SDL',self.sdl),('SUPPORTED_FNA',self.fna),('FIXED_SDL',self.source)]:
            p = patch.object(graphics, name, graphics.digest(path));p.start();self.addCleanup(p.stop)

    def prepare(self, enabled=True):
        return graphics.prepare(self.client, self.info, self.assets, enabled)

    def test_upgrade_repeat_restore_and_reenable_preserve_import(self):
        unrelated = self.client/'settings.json';unrelated.write_bytes(b'{"other":"retained"}')
        backup = self.client/graphics.BACKUP
        self.assertEqual(self.prepare()['action'], 'updated_known_tazuo_5.2_pair')
        self.assertEqual(self.sdl.read_bytes(), b'updated SDL')
        self.assertEqual(backup.read_bytes(), b'original SDL')
        self.assertEqual(self.prepare()['action'], 'already_updated')
        self.assertEqual(self.prepare(False)['action'], 'restored_original')
        self.assertEqual(self.sdl.read_bytes(), b'original SDL')
        self.assertEqual(self.prepare()['action'], 'updated_known_tazuo_5.2_pair')
        self.assertEqual(backup.read_bytes(), b'original SDL')
        self.assertEqual(unrelated.read_bytes(), b'{"other":"retained"}')

    def test_unknown_newer_x86_or_missing_library_is_never_overwritten(self):
        for name, content in [('sdl3.dll',b'newer SDL'),('FNA3D.dll',b'custom FNA')]:
            path = self.client/name;original=path.read_bytes();path.write_bytes(content)
            self.assertEqual(self.prepare()['action'], 'unchanged_unrecognized_libraries')
            self.assertEqual(path.read_bytes(), content);path.write_bytes(original)
        self.info['architecture']='x86'
        self.assertEqual(self.prepare()['action'], 'unchanged_unrecognized_libraries')
        self.sdl.unlink()
        self.assertEqual(self.prepare()['active_version'], 'unrecognized')
        self.assertFalse((self.client/graphics.BACKUP).exists())

    def test_failed_update_leaves_original_and_valid_backup_available(self):
        replace = graphics.os.replace
        def interrupted(source, target):
            if target == self.sdl:raise OSError('disk full')
            return replace(source, target)
        with patch.object(graphics.os, 'replace', side_effect=interrupted):
            with self.assertRaises(OSError):self.prepare()
        self.assertEqual(self.sdl.read_bytes(), b'original SDL')
        self.assertEqual((self.client/graphics.BACKUP).read_bytes(), b'original SDL')
        self.assertFalse(list(self.client.glob('.memento-sdl-*')))
        self.source.write_bytes(b'damaged package')
        with self.assertRaisesRegex(ValueError, 'missing or damaged'):self.prepare()
        self.assertEqual(self.sdl.read_bytes(), b'original SDL')

    def test_changed_backup_and_escaping_symlink_are_rejected_without_writes(self):
        backup = self.client/graphics.BACKUP;backup.write_bytes(b'important unrelated file')
        with self.assertRaisesRegex(ValueError, 'backup has changed'):self.prepare()
        self.assertEqual(self.sdl.read_bytes(), b'original SDL')
        self.assertEqual(backup.read_bytes(), b'important unrelated file')
        backup.unlink();backup.symlink_to(self.source)
        with self.assertRaisesRegex(ValueError, 'backup has changed'):self.prepare()
        self.assertEqual(self.source.read_bytes(), b'updated SDL')

    def test_client_already_shipping_new_sdl_is_not_downgraded(self):
        self.sdl.write_bytes(b'updated SDL')
        self.assertEqual(self.prepare(False)['action'], 'unchanged_no_original_backup')
        self.assertEqual(self.sdl.read_bytes(), b'updated SDL')
