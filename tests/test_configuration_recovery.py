"""Interrupted TazUO writes must not block a previously configured installation."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from uo_content import (local_client_settings, checkpoint_client_settings, viewport_settings,
                        write_json, inspect_client)
from test_memento import client_fixture


class RecoveryTests(unittest.TestCase):
    def test_post_reset_files_restore_newest_valid_backup_and_keep_damaged_bytes(self):
        for damaged in (b'', b'\0' * 128, b'{"password":', b'[]', b'null', b'\xff'):
            with self.subTest(damaged=damaged), tempfile.TemporaryDirectory() as d:
                root = Path(d); exe = client_fixture(root); info = inspect_client(root)
                path = exe.parent / 'settings.json'; path.write_bytes(damaged)
                original = path.with_name(path.name + '.before-memento')
                original.write_text('{"password":"old"}'); os.utime(original, ns=(1, 1))
                pacing = path.with_name(path.name + '.before-memento-pacing')
                pacing.write_text('{"password":"private-new","plugins":["keep.dll"],"profilespath":"Data/Profiles"}')
                checkpoint = path.with_name(path.name + '.memento-last-good')
                checkpoint.write_bytes(b'\0')  # Even a newer invalid backup must be skipped.
                report = local_client_settings(root, info)
                saved = json.loads(path.read_text())
                self.assertEqual(saved['password'], 'private-new')
                self.assertEqual(saved['plugins'], ['keep.dll'])
                self.assertEqual(saved['ultimaonlinedirectory'], 'D:\\Game files')
                self.assertEqual(report['settings_recovery'], '.before-memento-pacing')
                self.assertNotIn('private-new', json.dumps(report))
                copies = list(path.parent.glob('settings.json.interrupted-*'))
                self.assertEqual(len(copies), 1); self.assertEqual(copies[0].read_bytes(), damaged)
                self.assertEqual(json.loads(checkpoint.read_text()), saved)
                self.assertEqual(json.loads(original.read_text()), {'password':'old'})
                local_client_settings(root, info)
                self.assertEqual(list(path.parent.glob('settings.json.interrupted-*')), copies)

    def test_missing_settings_recover_backup_and_valid_settings_win_over_newer_backup(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); exe = client_fixture(root); info = inspect_client(root)
            path = exe.parent / 'settings.json'; backup = path.with_name(path.name + '.before-memento')
            backup.write_text('{"password":"backup"}')
            local_client_settings(root, info)
            self.assertEqual(json.loads(path.read_text())['password'], 'backup')
            path.write_text('{"password":"current"}')
            backup.write_text('{"password":"stale"}')
            self.assertIsNone(local_client_settings(root, info)['settings_recovery'])
            self.assertEqual(json.loads(path.read_text())['password'], 'current')

    def test_no_valid_backup_keeps_original_and_reports_actionable_error(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); exe = client_fixture(root); info = inspect_client(root)
            path = exe.parent / 'settings.json'; path.write_bytes(b'\0' * 5)
            with self.assertRaisesRegex(ValueError, 'settings.json is damaged.*no valid recovery backup'):
                local_client_settings(root, info)
            self.assertEqual(path.read_bytes(), b'\0' * 5)
            self.assertFalse(list(path.parent.glob('settings.json.memento-last-good')))

    def test_checkpoint_preserves_valid_game_preferences_and_rejects_damaged_exit_write(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); exe = client_fixture(root); info = inspect_client(root)
            path = exe.parent / 'settings.json'; path.write_text('{"password":"keep","fps":30}')
            checkpoint_client_settings(root, info)
            path.write_bytes(b'')
            with self.assertRaises(ValueError): checkpoint_client_settings(root, info)
            report = local_client_settings(root, info)
            self.assertEqual(report['settings_recovery'], '.memento-last-good')
            self.assertEqual(json.loads(path.read_text())['password'], 'keep')

    def test_profile_recovery_preserves_custom_options_gumps_and_viewport(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); exe = client_fixture(root); info = inspect_client(root)
            local_client_settings(root, info)
            path = exe.parent / 'Data/Profiles/account/realm/character/profile.json'
            path.parent.mkdir(parents=True); path.write_bytes(b'\0')
            path.with_name(path.name + '.before-memento-layout').write_text('{"sound":false,"custom":"keep"}')
            gumps = path.parent / 'gumps.xml'; gumps.write_text('<private-gumps/>')
            report = viewport_settings(root, info); saved = json.loads(path.read_text())
            self.assertFalse(saved['sound']); self.assertEqual(saved['custom'], 'keep')
            self.assertEqual(saved['game_window_size'], {'X':1098,'Y':720})
            self.assertEqual(report['profiles_recovered'], 1)
            self.assertNotIn('account', json.dumps(report))
            self.assertEqual(gumps.read_text(), '<private-gumps/>')

    def test_backup_symlink_cannot_escape_import_and_stale_temp_symlink_is_not_followed(self):
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as other:
            root = Path(d); exe = client_fixture(root); info = inspect_client(root)
            path = exe.parent / 'settings.json'; path.write_bytes(b'')
            outside = Path(other) / 'private.json'; outside.write_text('{"password":"outside"}')
            backup = path.with_name(path.name + '.before-memento'); backup.symlink_to(outside)
            with self.assertRaisesRegex(ValueError, 'escapes workspace'): local_client_settings(root, info)
            self.assertEqual(path.read_bytes(), b'')
            path.with_name(path.name + '.new').symlink_to(outside)
            write_json(path, {'safe':True})
            self.assertEqual(json.loads(outside.read_text()), {'password':'outside'})

    def test_failed_atomic_replace_keeps_previous_file_and_cleans_temp(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'settings.json'; path.write_text('{"old":true}')
            with patch('uo_content.os.replace', side_effect=OSError('simulated interrupted write')):
                with self.assertRaises(OSError): write_json(path, {'new':True})
            self.assertEqual(json.loads(path.read_text()), {'old':True})
            self.assertEqual(list(Path(d).iterdir()), [path])
