import json
from pathlib import Path
import shutil
import socket
import stat
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from engine import Engine
from world_archives import SAVE_FOLDERS


class SaveDataTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.engine = Engine(Path(self.temp.name))
        self.addCleanup(self.engine.pool.shutdown)
        self.world = self.engine.world
        for name in SAVE_FOLDERS:
            (self.world / name).mkdir(parents=True)
        (self.world / 'Saves/Accounts').mkdir()
        (self.world / 'Saves/Accounts/accounts.xml').write_text('original accounts')
        (self.world / 'Info/Settings.cs').write_text('original settings')
        (self.world / 'Backups/old-save.bin').write_bytes(b'previous save')
        (self.world / 'Data/Files').mkdir(parents=True)
        (self.world / 'Data/game.cfg').write_text('installed game data')
        (self.world / 'Source').mkdir()
        (self.world / 'Source/server.cs').write_text('installed source')
        (self.world / 'WorldLinux.exe').write_bytes(b'installed executable')
        self.asset = self.engine.client / 'tiledata.mul'
        self.asset.parent.mkdir(parents=True, exist_ok=True)
        self.asset.write_bytes(b'client asset')
        (self.world / 'Data/Files/tiledata.mul').symlink_to(self.asset)
        (self.engine.client / 'memento-client.json').write_text(json.dumps({'assets': '.'}))

    def archive(self, entries, legacy=False):
        archive = self.engine.work / 'incoming/restore.zip'
        with zipfile.ZipFile(archive, 'w') as z:
            if legacy:
                z.writestr('memento-backup.json', json.dumps({'format': 1, 'kind': 'world'}))
            for name, value in entries:
                z.writestr(name, value)
        return archive

    def assert_deployment_preserved(self):
        self.assertEqual((self.world / 'Data/game.cfg').read_text(), 'installed game data')
        self.assertEqual((self.world / 'Source/server.cs').read_text(), 'installed source')
        self.assertEqual((self.world / 'WorldLinux.exe').read_bytes(), b'installed executable')
        alias = self.world / 'Data/Files/tiledata.mul'
        self.assertTrue(alias.is_symlink())
        self.assertEqual(alias.readlink(), self.asset)
        self.assertEqual(alias.read_bytes(), b'client asset')
        self.assertEqual([p.name for p in (self.world / 'Data').iterdir()].count('Files'), 1)
        self.assertFalse(list((self.world / 'Data').glob('Files.before-client-import-*')))

    def test_export_contains_exactly_three_trees_and_restore_replaces_only_those(self):
        (self.world / 'Saves/empty/nested').mkdir(parents=True)
        (self.world / 'Info/ignored-link').symlink_to(self.asset)
        backup = self.engine.backup_world({})
        exported = self.engine.work / backup['file']
        with zipfile.ZipFile(exported) as z:
            self.assertEqual({Path(n).parts[0] for n in z.namelist()}, set(SAVE_FOLDERS))
            self.assertIn('Saves/empty/nested/', z.namelist())
            self.assertNotIn('Info/ignored-link', z.namelist())
        (self.world / 'Saves/Accounts/accounts.xml').write_text('new accounts')
        (self.world / 'Info/Settings.cs').write_text('new settings')
        (self.world / 'Backups/new-save.bin').write_bytes(b'new save')
        shutil.copy2(exported, self.engine.work / 'incoming/restore.zip')
        result = self.engine.restore_world({'file': 'restore.zip'})
        self.assertEqual((self.world / 'Saves/Accounts/accounts.xml').read_text(), 'original accounts')
        self.assertEqual((self.world / 'Info/Settings.cs').read_text(), 'original settings')
        self.assertFalse((self.world / 'Backups/new-save.bin').exists())
        self.assertTrue((self.world / 'Saves/empty/nested').is_dir())
        self.assert_deployment_preserved()
        self.assertIn('Previous world backup', result['message'])
        previous = next(p for p in (self.engine.work / 'exports').glob('*.zip') if p != exported)
        with zipfile.ZipFile(previous) as z:
            self.assertEqual(z.read('Saves/Accounts/accounts.xml'), b'new accounts')

    def test_empty_world_round_trip_preserves_empty_folders(self):
        for name in SAVE_FOLDERS:
            shutil.rmtree(self.world / name)
        exported = self.engine.work / self.engine.backup_world({})['file']
        with zipfile.ZipFile(exported) as z:
            self.assertEqual(set(z.namelist()), {name + '/' for name in SAVE_FOLDERS})
        shutil.copy2(exported, self.engine.work / 'incoming/restore.zip')
        self.engine.restore_world({'file': 'restore.zip'})
        for name in SAVE_FOLDERS:
            self.assertTrue((self.world / name).is_dir())
            self.assertEqual(list((self.world / name).iterdir()), [])
        self.assert_deployment_preserved()

    def test_legacy_archive_skips_data_without_extracting_it(self):
        self.archive([('Saves/Accounts/accounts.xml', 'legacy accounts'),
                      ('Info/Settings.cs', 'legacy settings'),
                      ('Data/game.cfg', 'obsolete game data'),
                      ('Data/Files/map0.mul', 'unused assets')], legacy=True)
        opened = []
        original = zipfile.ZipFile.open
        def track_open(z, name, *args, **kwargs):
            opened.append(name.filename if isinstance(name, zipfile.ZipInfo) else name)
            return original(z, name, *args, **kwargs)
        with patch.object(zipfile.ZipFile, 'open', track_open):
            result = self.engine.restore_world({'file': 'restore.zip'})
        self.assertEqual((self.world / 'Saves/Accounts/accounts.xml').read_text(), 'legacy accounts')
        self.assertEqual((self.world / 'Info/Settings.cs').read_text(), 'legacy settings')
        self.assertEqual((self.world / 'Backups/old-save.bin').read_bytes(), b'previous save')
        self.assertFalse(any(name.startswith('Data/') for name in opened))
        self.assertIn('Legacy Data content was skipped', result['message'])
        self.assert_deployment_preserved()

    def test_plain_wrapped_zip_accepts_case_normalized_folders(self):
        self.archive([('My world/', ''), ('My world/saves/Accounts/accounts.xml', 'external accounts'),
                      ('My world/info/Settings.cs', 'external settings'), ('My world/backups/', '')])
        self.engine.restore_world({'file': 'restore.zip'})
        self.assertEqual((self.world / 'Saves/Accounts/accounts.xml').read_text(), 'external accounts')
        self.assertEqual((self.world / 'Info/Settings.cs').read_text(), 'external settings')
        self.assertEqual(list((self.world / 'Backups').iterdir()), [])
        self.assert_deployment_preserved()

    def test_unexpected_or_ambiguous_zip_never_modifies_world(self):
        cases = {
            'data': [('Saves/new.bin', ''), ('Data/game.cfg', '')],
            'source': [('Saves/new.bin', ''), ('Source/server.cs', '')],
            'mixed_wrapper': [('Saves/new.bin', ''), ('World/Info/a', '')],
            'two_wrappers': [('World/Inner/Saves/a', '')],
            'file_folder': [('Saves', '')],
            'missing_saves': [('Info/a', '')],
            'case_conflict': [('Saves/a', ''), ('saves/b', '')],
            'duplicate': [('Saves/a', ''), ('Saves/./a', '')],
            'traversal': [('Saves/new.bin', ''), ('Saves/../../escape', '')],
            'absolute': [('Saves/new.bin', ''), ('/outside', '')],
            'metadata': [('Saves/new.bin', ''), ('memento-backup.json', '[]')],
        }
        for name, entries in cases.items():
            with self.subTest(name=name):
                self.archive(entries)
                with self.assertRaises(ValueError):
                    self.engine.restore_world({'file': 'restore.zip'})
                self.assertEqual((self.world / 'Saves/Accounts/accounts.xml').read_text(), 'original accounts')
                self.assertFalse((self.world / 'Saves/new.bin').exists())
                self.assertFalse(list((self.engine.work / 'exports').glob('*.zip')))
                self.assertFalse((self.engine.work / 'restore-staging').exists())
                self.assert_deployment_preserved()

    def test_links_in_legacy_ignored_data_are_still_rejected(self):
        link = zipfile.ZipInfo('Data/link')
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        self.archive([('Saves/new.bin', ''), (link, '/outside')], legacy=True)
        with self.assertRaisesRegex(ValueError, 'Links'):
            self.engine.restore_world({'file': 'restore.zip'})
        self.assertFalse((self.world / 'Saves/new.bin').exists())
        self.assertFalse(list((self.engine.work / 'exports').glob('*.zip')))

    def test_failed_activation_preserves_world_and_pre_restore_backup(self):
        self.archive([('Saves/Accounts/accounts.xml', 'replacement')])
        with patch('engine.swap_directory', side_effect=OSError('activation failure')):
            with self.assertRaisesRegex(OSError, 'activation failure'):
                self.engine.restore_world({'file': 'restore.zip'})
        self.assertEqual((self.world / 'Saves/Accounts/accounts.xml').read_text(), 'original accounts')
        self.assertEqual(len(list((self.engine.work / 'exports').glob('*.zip'))), 1)
        self.assertFalse((self.engine.work / 'restore-deployment').exists())
        self.assert_deployment_preserved()

    def test_export_refuses_symlinked_save_root_and_cleans_partial_archive(self):
        shutil.rmtree(self.world / 'Saves')
        (self.world / 'Saves').symlink_to(self.engine.client)
        with self.assertRaisesRegex(ValueError, 'Saves must be a real folder'):
            self.engine.backup_world({})
        self.assertFalse(list((self.engine.work / 'exports').glob('*.zip')))


class ServerReadinessTests(unittest.TestCase):
    def test_running_process_is_ready_only_after_listener_is_available(self):
        with tempfile.TemporaryDirectory() as folder, socket.socket() as listener:
            engine = Engine(Path(folder))
            self.addCleanup(engine.pool.shutdown)
            engine.process = Mock()
            engine.process.poll.return_value = None
            listener.bind(('127.0.0.1', 0))
            address = listener.getsockname()
            real_socket = socket.socket
            class RedirectProbe(real_socket):
                def connect_ex(self, requested):
                    if requested != ('127.0.0.1', 2593):
                        raise AssertionError('Unexpected server readiness address')
                    return super().connect_ex(address)
            with patch('engine.socket.socket', RedirectProbe):
                state = engine.state()
                self.assertTrue(state['running'])
                self.assertFalse(state['ready'])
                listener.listen(4)
                self.assertTrue(engine.state()['ready'])
                engine.process.poll.return_value = 0
                self.assertFalse(engine.state()['ready'])


if __name__ == '__main__':
    unittest.main()
