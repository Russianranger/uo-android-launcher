from pathlib import Path
import json
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from engine import Engine
from backup_catalog import backup_file, backup_files


class BackupManagementTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.engine = Engine(Path(self.temp.name)); self.addCleanup(self.engine.pool.shutdown)
        for name in ('Info', 'Saves', 'Backups'): (self.engine.world / name).mkdir(parents=True)
        (self.engine.world / 'Saves/character.bin').write_bytes(b'character one')
        (self.engine.world / 'WorldLinux.exe').write_bytes(b'unchanged server')

    def backup(self, reason='Manual backup'):
        return self.engine.work / self.engine.backup_world({'reason': reason})['file']

    def test_inventory_and_metadata_survive_runtime_restart(self):
        archive = self.backup('Before restore')
        second = Engine(self.engine.work); self.addCleanup(second.pool.shutdown)
        self.assertFalse(second.jobs)
        self.assertEqual(backup_files(second.work), [archive])
        metadata = json.loads((second.work / ('backups/metadata-' + archive.name + '.json')).read_text())
        self.assertEqual(metadata['reason'], 'Before restore')
        preview = second.backup_preview({'name': archive.name})
        self.assertEqual(preview['folders'], ['Info', 'Saves', 'Backups'])
        self.assertEqual(preview['files'], 1); self.assertEqual(preview['unpacked_bytes'], 13)

    def test_saved_archive_restore_keeps_original_archive_and_creates_pre_restore_copy(self):
        archive = self.backup()
        (self.engine.world / 'Saves/character.bin').write_bytes(b'character two')
        self.engine.restore_world({'backup': archive.name})
        self.assertEqual((self.engine.world / 'Saves/character.bin').read_bytes(), b'character one')
        self.assertTrue(archive.exists()); self.assertEqual(len(backup_files(self.engine.work)), 2)
        self.assertEqual((self.engine.world / 'WorldLinux.exe').read_bytes(), b'unchanged server')
        latest = backup_files(self.engine.work)[0]
        with zipfile.ZipFile(latest) as z: self.assertEqual(z.read('Saves/character.bin'), b'character two')

    def test_prune_keeps_newest_and_never_touches_world_logs_incoming_or_external_copy(self):
        first = self.backup(); second = self.backup(); third = self.backup()
        external = self.engine.work / 'external.zip'; shutil.copy2(first, external)
        log = self.engine.work / 'exports/logs.zip'; log.write_bytes(b'logs')
        (self.engine.work / ('backups/exported-' + first.name + '.json')).write_text('{}')
        self.engine.prune_backups({'keep': 2})
        self.assertEqual(set(backup_files(self.engine.work)), {second, third})
        self.assertFalse((self.engine.work / ('backups/exported-' + first.name + '.json')).exists())
        self.assertTrue(external.exists()); self.assertTrue(log.exists())
        self.assertEqual((self.engine.world / 'Saves/character.bin').read_bytes(), b'character one')
        for keep in (0, -1, True, '2'):
            with self.assertRaises(ValueError): self.engine.prune_backups({'keep': keep})

    def test_preview_and_delete_refuse_paths_links_and_unsafe_archive_members(self):
        archive = self.backup(); link = archive.parent / 'memento-world-99.zip'; link.symlink_to(archive)
        for name in ('../Saves/character.bin', 'logs.zip', link.name):
            with self.subTest(name=name), self.assertRaises(ValueError): backup_file(self.engine.work, name)
        self.assertNotIn(link, backup_files(self.engine.work))
        unsafe = self.engine.work / 'incoming/unsafe.zip'
        with zipfile.ZipFile(unsafe, 'w') as z: z.writestr('Saves/../../escape', b'bad')
        with self.assertRaises(ValueError): self.engine.preview_world({'file': unsafe.name})
        self.assertFalse((self.engine.work / 'restore-staging').exists())

    def test_save_export_waits_for_successful_save_before_archiving(self):
        events=[]
        with patch.object(self.engine, 'server_stop', side_effect=lambda _:events.append('save')):
            self.engine.save_backup({}); self.assertEqual(events, ['save'])
        previous = backup_files(self.engine.work)
        with patch.object(self.engine, 'server_stop', side_effect=RuntimeError('save acknowledgement failed')):
            with self.assertRaisesRegex(RuntimeError, 'acknowledgement'): self.engine.save_backup({})
        self.assertEqual(backup_files(self.engine.work), previous)

    def test_failed_zip_creation_leaves_no_partial_backup_in_inventory(self):
        with patch('engine.zipfile.ZipFile.write', side_effect=OSError('disk full')):
            with self.assertRaisesRegex(OSError, 'disk full'): self.backup()
        self.assertEqual(backup_files(self.engine.work), [])
        self.assertEqual(list((self.engine.work / 'exports').iterdir()), [])


if __name__ == '__main__': unittest.main()
