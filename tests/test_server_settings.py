from pathlib import Path
import json
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
import server_settings as settings
from engine import Engine

FIXTURE = Path(__file__).parent / 'fixtures/memento-settings.cs'


class ServerSettingsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.engine = Engine(Path(self.temp.name)); self.addCleanup(self.engine.pool.shutdown)
        self.file = self.engine.world / settings.SETTINGS
        self.file.parent.mkdir(parents=True); self.file.write_bytes(FIXTURE.read_bytes())
        self.original = self.file.read_bytes()

    def test_real_settings_include_sections_descriptions_arrays_and_managed_network(self):
        model = self.engine.settings_read({})
        self.assertEqual(len(model['fields']), 142)
        fields = {field['name']: field for field in model['fields']}
        self.assertEqual(fields['S_ServerSaveMinutes']['value'], 30)
        self.assertIn('10 and 240', fields['S_ServerSaveMinutes']['description'])
        self.assertEqual(fields['S_UnidentifiedItem_GuaranteedItemChecks']['value'], [0, 30, 60])
        self.assertEqual(fields['S_Address']['value'], '127.0.0.1')
        self.assertTrue(fields['S_Address']['read_only'])
        self.assertFalse(model['can_undo']); self.assertEqual(self.file.read_bytes(), self.original)

    def test_atomic_save_changes_only_selected_literals_and_undo_restores_exact_bytes(self):
        before = self.engine.settings_read({})
        changes = {'S_ServerSaveMinutes': 45.5, 'S_ServerName': 'My "realm"; // still text',
                   'S_SaveOnCharacterLogout': False, 'S_UnidentifiedItem_GuaranteedItemChecks': [5, 35, 65]}
        with patch('server_settings.validate_compile') as compile_settings:
            self.engine.settings_save({'revision': before['revision'], 'changes': changes})
            compile_settings.assert_called_once()
            after = self.engine.settings_read({}); self.assertTrue(after['can_undo'])
            values = {field['name']: field['value'] for field in after['fields']}
            for name, value in changes.items(): self.assertEqual(values[name], value)
            self.assertIn('// INDEX - USE CTRL-F', self.file.read_text())
            self.engine.settings_undo({'revision': after['revision']})
        self.assertEqual(self.file.read_bytes(), self.original)
        self.assertFalse(self.engine.settings_read({})['can_undo'])

    def test_validation_rejects_code_nonfinite_numbers_ranges_pairs_and_unknown_keys(self):
        model = self.engine.settings_read({})
        bad = [{'S_ServerSaveMinutes': 0}, {'S_ServerSaveMinutes': float('nan')},
               {'S_MinGold': 601}, {'S_MinGold': 1.5}, {'S_SaveOnCharacterLogout': 'true'},
               {'S_Port': 3000}, {'Unknown': 1}, {'S_Stables': True},
               {'S_UnidentifiedItem_GuaranteedItemChecks': [0, '30; System.Exit(1)']},
               {'S_WyrmBody': 100}, {'S_MinMerchant': 2001}, {'S_SpawnMin': 61}]
        with patch('server_settings.validate_compile') as compiler:
            for changes in bad:
                with self.subTest(changes=changes), self.assertRaises(ValueError):
                    self.engine.settings_save({'revision': model['revision'], 'changes': changes})
                self.assertEqual(self.file.read_bytes(), self.original)
            compiler.assert_not_called()

    def test_external_changes_or_running_server_block_writes(self):
        revision = self.engine.settings_read({})['revision']
        self.file.write_bytes(self.original + b'\n// External edit\n')
        with self.assertRaisesRegex(ValueError, 'Reload'):
            self.engine.settings_save({'revision': revision, 'changes': {'S_ServerSaveMinutes': 60}})
        with patch.object(self.engine, 'running', return_value=True), self.assertRaisesRegex(ValueError, 'stop'):
            self.engine.settings_save({})

    def test_failed_compilation_preserves_original_and_does_not_offer_undo(self):
        model = self.engine.settings_read({})
        with patch('server_settings.validate_compile', side_effect=ValueError('did not compile')):
            with self.assertRaisesRegex(ValueError, 'compile'):
                self.engine.settings_save({'revision': model['revision'], 'changes': {'S_ServerSaveMinutes': 60}})
        self.assertEqual(self.file.read_bytes(), self.original)
        self.assertFalse(self.engine.settings_read({})['can_undo'])

    def test_custom_overrides_and_expressions_are_preserved_and_not_misrepresented(self):
        override = self.engine.world / settings.OVERRIDES
        override.write_text('// MySettings.S_ServerName = "not active";\n'
                            'class Custom { void Initialize() { MySettings.S_ServerSaveMinutes = Compute(); } }')
        model = self.engine.settings_read({})
        fields = {field['name']: field for field in model['fields']}
        self.assertIsNone(fields['S_ServerSaveMinutes']['value'])
        self.assertTrue(fields['S_ServerSaveMinutes']['read_only'])
        self.assertFalse(fields['S_ServerName']['read_only'])
        with self.assertRaisesRegex(ValueError, 'override'):
            settings.changed(self.file.read_text(), override.read_text(), {'S_ServerSaveMinutes': 60})
        custom = self.file.read_text().replace('S_DeleteDays = 3.0', 'S_DeleteDays = Compute()')
        fields = {field['name']: field for field, _ in settings.fields(custom)}
        self.assertTrue(fields['S_DeleteDays']['read_only'])
        self.assertIn('Compute()', settings.changed(custom, '', {'S_ServerName': 'Still editable'}))

    def test_crlf_and_bom_are_retained_and_override_changes_invalidate_undo(self):
        self.file.write_bytes(b'\xef\xbb\xbf' + self.original.replace(b'\n', b'\r\n'))
        original = self.file.read_bytes(); model = self.engine.settings_read({})
        with patch('server_settings.validate_compile'):
            self.engine.settings_save({'revision': model['revision'], 'changes': {'S_ServerSaveMinutes': 60}})
            self.assertTrue(self.file.read_bytes().startswith(b'\xef\xbb\xbf'))
            self.assertEqual(self.file.read_bytes().count(b'\r\n'), original.count(b'\r\n'))
            after = self.engine.settings_read({})
            self.engine.settings_undo({'revision': after['revision']})
        self.assertEqual(self.file.read_bytes(), original)


if __name__ == '__main__': unittest.main()
