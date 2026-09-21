import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
import client_prefix

VALID = b'WINE REGISTRY Version 2\n;; All keys relative to Machine\n\n#arch=win64\n\n[Software] 1\n"Keep"="private-value"\n'


class PrefixRecoveryTests(unittest.TestCase):
    def setUp(self):
        folder=tempfile.TemporaryDirectory();self.addCleanup(folder.cleanup)
        self.prefix=Path(folder.name)
        for name in client_prefix.HIVES:(self.prefix/name).write_bytes(VALID)

    def test_damaged_system_is_quarantined_without_removing_healthy_user_hives_or_files(self):
        system=self.prefix/'system.reg';bad=b'\0'*4096;system.write_bytes(bad)
        drive=self.prefix/'drive_c/users/root/Documents/keep.txt';drive.parent.mkdir(parents=True);drive.write_text('keep')
        report=client_prefix.recover(self.prefix)
        self.assertEqual(report['actions'],{'system.reg':'regenerate_with_wineboot'})
        self.assertFalse(system.exists())
        self.assertEqual((self.prefix/'user.reg').read_bytes(),VALID)
        self.assertEqual((self.prefix/'userdef.reg').read_bytes(),VALID)
        self.assertEqual(drive.read_text(),'keep')
        copies=list(self.prefix.glob('.memento-registry-recovery/*/system.reg'))
        self.assertEqual(len(copies),1);self.assertEqual(copies[0].read_bytes(),bad)
        self.assertNotIn('private-value',json.dumps(report))
        # Another interruption after quarantine must resume from missing state.
        again=client_prefix.recover(self.prefix)
        self.assertEqual(again['actions']['system.reg'],'regenerate_with_wineboot')
        self.assertEqual(list(self.prefix.glob('.memento-registry-recovery/*/system.reg')),copies)

    def test_checkpoint_restores_only_damaged_or_missing_hives(self):
        client_prefix.checkpoint(self.prefix)
        (self.prefix/'system.reg').write_bytes(b'bad header\n')
        (self.prefix/'userdef.reg').unlink()
        current=VALID.replace(b'private-value',b'current-preference')
        (self.prefix/'user.reg').write_bytes(current)
        report=client_prefix.recover(self.prefix)
        self.assertEqual(report['actions'],{'system.reg':'restored_checkpoint','userdef.reg':'restored_checkpoint'})
        self.assertEqual((self.prefix/'system.reg').read_bytes(),VALID)
        self.assertEqual((self.prefix/'userdef.reg').read_bytes(),VALID)
        self.assertEqual((self.prefix/'user.reg').read_bytes(),current)

    def test_invalid_backups_are_skipped_and_cannot_poison_a_valid_checkpoint(self):
        client_prefix.checkpoint(self.prefix)
        for bad in (b'',b'garbage\n',VALID.replace(b'win64',b'win32'),VALID[:-2],VALID+b'\0'):
            with self.subTest(bad=bad):
                (self.prefix/'system.reg').write_bytes(bad)
                with self.assertRaisesRegex(RuntimeError,'repair is incomplete'):client_prefix.checkpoint(self.prefix)
                self.assertEqual((self.prefix/client_prefix.CHECKPOINT/'system.reg').read_bytes(),VALID)
        (self.prefix/client_prefix.CHECKPOINT/'system.reg').write_bytes(b'\0')
        self.assertEqual(client_prefix.recover(self.prefix)['actions']['system.reg'],'regenerate_with_wineboot')

    def test_missing_fresh_hives_initialize_and_healthy_prefix_needs_no_recovery(self):
        self.assertEqual(client_prefix.recover(self.prefix)['actions'],{})
        for name in client_prefix.HIVES:(self.prefix/name).unlink()
        self.assertTrue(all(value=='regenerate_with_wineboot' for value in client_prefix.recover(self.prefix)['actions'].values()))
        self.assertFalse((self.prefix/'.memento-registry-recovery').exists())

    def test_unsafe_recovery_paths_fail_before_moving_any_hive(self):
        with tempfile.TemporaryDirectory() as d:
            outside=Path(d);(outside/'system.reg').write_bytes(VALID)
            (self.prefix/'system.reg').write_bytes(b'\0')
            (self.prefix/client_prefix.CHECKPOINT).symlink_to(outside,target_is_directory=True)
            with self.assertRaises(ValueError):client_prefix.recover(self.prefix)
            self.assertEqual((self.prefix/'system.reg').read_bytes(),b'\0')
            self.assertEqual((outside/'system.reg').read_bytes(),VALID)

    def test_failed_restore_keeps_quarantined_original_and_valid_backup(self):
        client_prefix.checkpoint(self.prefix)
        (self.prefix/'system.reg').write_bytes(b'\0')
        with patch.object(client_prefix,'atomic_copy',side_effect=OSError('disk failure')):
            with self.assertRaises(OSError):client_prefix.recover(self.prefix)
        self.assertEqual(next(self.prefix.glob('.memento-registry-recovery/*/system.reg')).read_bytes(),b'\0')
        self.assertEqual((self.prefix/client_prefix.CHECKPOINT/'system.reg').read_bytes(),VALID)
        client_prefix.recover(self.prefix)
        self.assertEqual((self.prefix/'system.reg').read_bytes(),VALID)
