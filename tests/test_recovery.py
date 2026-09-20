import gzip
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock,patch

spec=importlib.util.spec_from_file_location('recovery',Path(__file__).resolve().parents[1]/'scripts/recover-preview.py')
recovery=importlib.util.module_from_spec(spec);spec.loader.exec_module(recovery)


class RecoveryTests(unittest.TestCase):
    def test_capture_retains_bytes_and_refuses_overwriting_backup(self):
        with tempfile.TemporaryDirectory() as d:
            target=Path(d)/'logs.tar.gz';adb=Mock()
            adb.archive_command.return_value=[sys.executable,'-c','import sys;sys.stdout.buffer.write(b"tar bytes\\x00\\xff")']
            recovery.capture(adb,'files/work/logs',target)
            self.assertEqual(gzip.decompress(target.read_bytes()),b'tar bytes\x00\xff')
            with self.assertRaises(FileExistsError):recovery.capture(adb,'files',target)

    def test_failed_capture_leaves_no_incomplete_backup(self):
        with tempfile.TemporaryDirectory() as d:
            target=Path(d)/'logs.tar.gz';adb=Mock()
            adb.archive_command.return_value=[sys.executable,'-c','print("partial");raise SystemExit(1)']
            with self.assertRaises(RuntimeError):recovery.capture(adb,'files',target)
            self.assertEqual(list(Path(d).iterdir()),[])

    def test_configured_destination_or_cancel_does_not_stop_or_copy_apps(self):
        adb=Mock();adb.require_fresh_recovery.side_effect=RuntimeError('Already configured')
        with self.assertRaisesRegex(RuntimeError,'configured'):recovery.migrate(adb,'unused.tar.gz')
        adb.call.assert_not_called()
        adb.require_fresh_recovery.side_effect=None
        with patch('builtins.input',return_value='cancel'):
            with self.assertRaisesRegex(RuntimeError,'cancelled'):recovery.migrate(adb,'unused.tar.gz')
        adb.call.assert_not_called()

    def test_corrupt_backup_is_rejected_before_target_write(self):
        with tempfile.TemporaryDirectory() as d:
            archive=Path(d)/'broken.gz';archive.write_bytes(b'not gzip');adb=Mock()
            with self.assertRaises(OSError):recovery.restore(adb,archive)
            adb.restore_command.assert_not_called()
