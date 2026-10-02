import base64
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
import client_atlas_uploads as atlas
import client_frame_budget as frame
import client_render_trace as trace
from test_client_render_trace import delta


def sha(data):
    return hashlib.sha256(data).hexdigest()


class AtlasUploadPatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / 'client'
        self.root.mkdir()
        self.assets = Path(self.tmp.name) / 'assets'
        self.assets.mkdir()
        self.originals = {'FNA.dll': b'original fna',
                          'ClassicUO.Renderer.dll': b'original renderer'}
        self.patched = {'FNA.dll': b'batched fna',
                        'ClassicUO.Renderer.dll': b'batched renderer'}
        self.taz_states = {'ORIGINAL': b'original client',
                           'INSTRUMENTED': b'render client',
                           'BUDGET': b'revision 2 budget client',
                           'COMBINED': b'revision 2 combined client',
                           'LEGACY_BUDGET': b'revision 1 budget client',
                           'LEGACY_COMBINED': b'revision 1 combined client'}
        constants = [
            (atlas, 'FNA_ORIGINAL', self.originals['FNA.dll']),
            (atlas, 'RENDERER_ORIGINAL', self.originals['ClassicUO.Renderer.dll']),
            (atlas, 'FNA_PATCHED', self.patched['FNA.dll']),
            (atlas, 'RENDERER_PATCHED', self.patched['ClassicUO.Renderer.dll']),
            (atlas, 'SUPPORTED_FNA', b'native fna3d'),
            (atlas, 'ORIGINAL_SDL', b'original sdl'),
            (atlas, 'FIXED_SDL', b'fixed sdl'),
            (atlas, 'UTILITY', b'pinned padded atlas packer'),
            (trace, 'FNA', self.originals['FNA.dll']),
        ]
        for name, data in self.taz_states.items():
            constants.append((trace if name in ('ORIGINAL', 'INSTRUMENTED') else frame,
                              name, data))
        for module, constant, data in constants:
            mocked = patch.object(module, constant, sha(data))
            mocked.start()
            self.addCleanup(mocked.stop)
        self.info = {'executable': 'TazUO.exe'}
        self.reset_client()
        for name in (atlas.HELPER, frame.HELPER):
            (self.assets / name).write_bytes(b'helper fixture')
        for name, data in ((atlas.FNA_PATCH, self.patched['FNA.dll']),
                           (atlas.RENDERER_PATCH, self.patched['ClassicUO.Renderer.dll'])):
            (self.assets / name).write_bytes(base64.b64encode(delta(data)))

    def reset_client(self):
        for target in self.root.iterdir():
            target.unlink()
        for name, data in self.originals.items():
            (self.root / name).write_bytes(data)
        (self.root / 'TazUO.dll').write_bytes(self.taz_states['BUDGET'])
        (self.root / frame.BACKUP).write_bytes(self.taz_states['ORIGINAL'])
        (self.root / 'FNA3D.dll').write_bytes(b'native fna3d')
        (self.root / 'SDL3.dll').write_bytes(b'original sdl')
        (self.root / 'ClassicUO.Utility.dll').write_bytes(b'pinned padded atlas packer')

    def prepare(self, enabled=True):
        return atlas.prepare(self.root, self.info, self.assets, enabled)

    def backup(self, name):
        return self.root / (name + atlas.BACKUP_SUFFIX)

    def assert_original_pair(self):
        for name, data in self.originals.items():
            self.assertEqual((self.root / name).read_bytes(), data)

    def assert_patched_pair(self):
        for name, data in self.patched.items():
            self.assertEqual((self.root / name).read_bytes(), data)

    def assert_no_atlas_backups(self):
        self.assertEqual(list(self.root.glob('*' + atlas.BACKUP_SUFFIX)), [])

    def test_pair_patch_idempotence_and_restore_preserve_budget_client(self):
        client = (self.root / 'TazUO.dll').read_bytes()
        retained = (self.root / frame.BACKUP).read_bytes()
        report = self.prepare()
        self.assertTrue(report['active'])
        self.assertEqual(report['action'], 'batched_known_client')
        self.assert_patched_pair()
        for name, data in self.originals.items():
            self.assertEqual(self.backup(name).read_bytes(), data)
        with patch.object(trace, 'atomic_write', side_effect=AssertionError('Unnecessary rewrite')):
            self.assertEqual(self.prepare()['action'], 'already_batched')
        self.assertEqual(self.prepare(False)['action'], 'restored_original')
        self.assert_original_pair()
        with patch.object(trace, 'atomic_write', side_effect=AssertionError('Unnecessary rewrite')):
            self.assertEqual(self.prepare(False)['action'], 'unchanged_disabled')
        self.assertTrue(self.prepare()['active'])
        self.assertEqual((self.root / 'TazUO.dll').read_bytes(), client)
        self.assertEqual((self.root / frame.BACKUP).read_bytes(), retained)

    def test_known_client_variants_and_both_supported_sdl_versions(self):
        for state, client in self.taz_states.items():
            for sdl in (b'original sdl', b'fixed sdl'):
                with self.subTest(state=state, sdl=sdl):
                    self.reset_client()
                    (self.root / 'TazUO.dll').write_bytes(client)
                    (self.root / 'SDL3.dll').write_bytes(sdl)
                    self.assertTrue(self.prepare()['active'])
                    self.assert_patched_pair()
                    self.assertEqual((self.root / 'TazUO.dll').read_bytes(), client)
                    self.assertEqual((self.root / 'SDL3.dll').read_bytes(), sdl)

    def test_unknown_component_never_patches_original_pair(self):
        for name in ('TazUO.dll', 'FNA.dll', 'ClassicUO.Renderer.dll', 'FNA3D.dll', 'SDL3.dll', 'ClassicUO.Utility.dll'):
            with self.subTest(component=name):
                self.reset_client()
                unknown = b'upstream replacement ' + name.encode()
                (self.root / name).write_bytes(unknown)
                before = {p.name: p.read_bytes() for p in self.root.iterdir()}
                with patch.object(trace, 'atomic_write', side_effect=AssertionError('Unknown client rewrite')):
                    report = self.prepare()
                self.assertFalse(report['active'])
                self.assertEqual(report['action'], 'unchanged_unrecognized_client')
                self.assertEqual({p.name: p.read_bytes() for p in self.root.iterdir()}, before)
                self.assert_no_atlas_backups()

    def test_upstream_replacement_restores_only_our_remaining_halves(self):
        for name in ('TazUO.dll', 'FNA.dll', 'ClassicUO.Renderer.dll', 'FNA3D.dll', 'SDL3.dll', 'ClassicUO.Utility.dll'):
            for enabled in (True, False):
                with self.subTest(component=name, enabled=enabled):
                    self.reset_client()
                    self.prepare()
                    unknown = b'upstream replacement ' + name.encode()
                    (self.root / name).write_bytes(unknown)
                    report = self.prepare(enabled)
                    self.assertFalse(report['active'])
                    self.assertEqual(report['action'], 'restored_original')
                    self.assertEqual((self.root / name).read_bytes(), unknown)
                    for owned, data in self.originals.items():
                        if owned != name:
                            self.assertEqual((self.root / owned).read_bytes(), data)
                    if name != 'TazUO.dll':
                        self.assertEqual((self.root / 'TazUO.dll').read_bytes(), self.taz_states['BUDGET'])

    def test_patched_pair_requires_both_original_backups_before_any_write(self):
        for name in self.originals:
            for invalid in ('missing', 'corrupt', 'symlink'):
                for enabled in (True, False):
                    with self.subTest(backup=name, invalid=invalid, enabled=enabled):
                        self.reset_client()
                        self.prepare()
                        backup = self.backup(name)
                        backup.unlink()
                        if invalid == 'corrupt':
                            backup.write_bytes(b'changed backup')
                        elif invalid == 'symlink':
                            backup.symlink_to(self.root / name)
                        with patch.object(trace, 'atomic_write', side_effect=AssertionError('Pair changed before backup validation')):
                            with self.assertRaisesRegex(ValueError, 'backup is missing or changed'):
                                self.prepare(enabled)
                        self.assert_patched_pair()

    def test_original_pair_rejects_conflicting_or_symlink_backups(self):
        for name in self.originals:
            for invalid in ('corrupt', 'symlink'):
                with self.subTest(backup=name, invalid=invalid):
                    self.reset_client()
                    backup = self.backup(name)
                    if invalid == 'corrupt':
                        backup.write_bytes(b'changed backup')
                    else:
                        backup.symlink_to(self.root / name)
                    with patch.object(trace, 'atomic_write', side_effect=AssertionError('Pair changed before backup validation')):
                        with self.assertRaisesRegex(ValueError, 'backup has changed'):
                            self.prepare()
                    self.assert_original_pair()

    def test_missing_helpers_preserve_originals_and_do_not_create_backups(self):
        for name in (atlas.HELPER, frame.HELPER):
            with self.subTest(helper=name):
                helper = self.assets / name
                data = helper.read_bytes()
                helper.unlink()
                with patch.object(trace, 'atomic_write', side_effect=AssertionError('Pair changed without helper')):
                    with self.assertRaisesRegex(ValueError, 'component is missing'):
                        self.prepare()
                self.assert_original_pair()
                self.assert_no_atlas_backups()
                helper.write_bytes(data)

    def test_missing_or_invalid_second_delta_cannot_commit_first_library(self):
        for name in (atlas.FNA_PATCH, atlas.RENDERER_PATCH):
            for failure in ('missing', 'base64', 'delta', 'checksum'):
                with self.subTest(delta=name, failure=failure):
                    target = self.assets / name
                    valid = target.read_bytes()
                    if failure == 'missing':
                        target.unlink()
                    elif failure == 'base64':
                        target.write_bytes(b'!invalid base64!')
                    elif failure == 'delta':
                        target.write_bytes(base64.b64encode(b'not a delta'))
                    else:
                        target.write_bytes(base64.b64encode(delta(b'wrong output')))
                    with patch.object(trace, 'atomic_write', side_effect=AssertionError('Pair changed before both output checks')):
                        with self.assertRaises((FileNotFoundError, ValueError)):
                            self.prepare()
                    self.assert_original_pair()
                    self.assert_no_atlas_backups()
                    target.write_bytes(valid)

    def test_failed_second_library_commit_is_recoverable_by_retry_or_disable(self):
        for retry_enabled in (True, False):
            with self.subTest(retry_enabled=retry_enabled):
                self.reset_client()
                replace = trace.os.replace
                def fail(src, dst):
                    if dst.name == 'ClassicUO.Renderer.dll':
                        raise OSError('storage failure')
                    replace(src, dst)
                with patch.object(trace.os, 'replace', side_effect=fail):
                    with self.assertRaisesRegex(OSError, 'storage failure'):
                        self.prepare()
                self.assertEqual((self.root / 'FNA.dll').read_bytes(), self.patched['FNA.dll'])
                self.assertEqual((self.root / 'ClassicUO.Renderer.dll').read_bytes(), self.originals['ClassicUO.Renderer.dll'])
                for name, data in self.originals.items():
                    self.assertEqual(self.backup(name).read_bytes(), data)
                self.assertEqual(list(self.root.glob('.memento-render-*')), [])
                report = self.prepare(retry_enabled)
                self.assertEqual(report['active'], retry_enabled)
                self.assert_patched_pair() if retry_enabled else self.assert_original_pair()
                self.assertEqual((self.root / 'TazUO.dll').read_bytes(), self.taz_states['BUDGET'])

    def test_library_names_are_case_insensitive_and_retain_original_spelling(self):
        for name in ('TazUO.dll', 'FNA.dll', 'ClassicUO.Renderer.dll', 'FNA3D.dll', 'SDL3.dll', 'ClassicUO.Utility.dll'):
            (self.root / name).rename(self.root / name.swapcase())
        self.assertTrue(self.prepare()['active'])
        self.assertTrue(atlas.supported_fna(self.root, atlas.FNA_PATCHED))
        self.assertEqual(self.prepare(False)['action'], 'restored_original')
        for name, data in self.originals.items():
            self.assertFalse((self.root / name).exists())
            self.assertEqual((self.root / name.swapcase()).read_bytes(), data)
            self.assertEqual(self.backup(name.swapcase()).read_bytes(), data)

    def test_duplicate_or_symlink_libraries_rejected_without_mutation(self):
        for name in ('TazUO.dll', 'FNA.dll', 'ClassicUO.Renderer.dll', 'FNA3D.dll', 'SDL3.dll', 'ClassicUO.Utility.dll'):
            for invalid in ('duplicate', 'symlink'):
                with self.subTest(library=name, invalid=invalid):
                    self.reset_client()
                    original = (self.root / name).read_bytes()
                    if invalid == 'duplicate':
                        invalid_path = self.root / name.swapcase()
                        invalid_path.write_bytes(original)
                    else:
                        (self.root / name).unlink()
                        outside = self.assets / 'external-library.dll'
                        outside.write_bytes(original)
                        (self.root / name).symlink_to(outside)
                    with patch.object(trace, 'atomic_write', side_effect=AssertionError('Invalid library changed')):
                        with self.assertRaisesRegex(ValueError, 'Duplicate|symbolic link'):
                            self.prepare()
                    self.assert_no_atlas_backups()
                    self.assertEqual((self.root / name).read_bytes(), original)

    def test_executable_path_cannot_escape_client_root(self):
        for executable in ('../TazUO.exe', '/outside/TazUO.exe', 'C:\\client\\TazUO.exe', 'bad\0name'):
            with self.subTest(executable=executable):
                with self.assertRaisesRegex(ValueError, 'Unsafe file path'):
                    atlas.prepare(self.root, {'executable': executable}, self.assets, True)
        (self.root / 'escape').symlink_to(self.assets, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'escapes workspace'):
            atlas.prepare(self.root, {'executable': 'escape/TazUO.exe'}, self.assets, True)
        self.assert_original_pair()
        self.assert_no_atlas_backups()

    def test_supported_fna_requires_verified_retained_original_for_batched_binary(self):
        self.assertTrue(atlas.supported_fna(self.root, atlas.FNA_ORIGINAL))
        self.assertFalse(atlas.supported_fna(self.root, sha(b'unknown fna')))
        for invalid in ('missing', 'corrupt', 'symlink'):
            with self.subTest(backup=invalid):
                backup = self.backup('FNA.dll')
                backup.unlink(missing_ok=True)
                if invalid == 'corrupt':
                    backup.write_bytes(b'changed backup')
                elif invalid == 'symlink':
                    backup.symlink_to(self.root / 'FNA.dll')
                with self.assertRaisesRegex(ValueError, 'backup is missing or changed'):
                    atlas.supported_fna(self.root, atlas.FNA_PATCHED)
        backup.unlink()
        backup.write_bytes(self.originals['FNA.dll'])
        self.assertTrue(atlas.supported_fna(self.root, atlas.FNA_PATCHED))

    def test_batched_fna_keeps_existing_frame_budget_active_without_client_rewrite(self):
        self.prepare()
        with patch.object(trace, 'atomic_write', side_effect=AssertionError('Budget client rewrite')):
            report = frame.prepare(self.root, self.info, self.assets, True, False)
        self.assertTrue(report['frame_budget']['active'])
        self.assertFalse(report['render_trace']['active'])
        self.assert_patched_pair()
        self.assertEqual((self.root / 'TazUO.dll').read_bytes(), self.taz_states['BUDGET'])
        self.backup('FNA.dll').write_bytes(b'changed backup')
        with self.assertRaisesRegex(ValueError, 'backup is missing or changed'):
            frame.prepare(self.root, self.info, self.assets, True, False)
        self.assertEqual((self.root / 'TazUO.dll').read_bytes(), self.taz_states['BUDGET'])

    def test_option_must_be_boolean(self):
        for invalid in ('false', 0, 1, None):
            with self.subTest(enabled=invalid):
                with self.assertRaisesRegex(ValueError, 'option'):
                    self.prepare(invalid)
        self.assert_original_pair()
        self.assert_no_atlas_backups()
