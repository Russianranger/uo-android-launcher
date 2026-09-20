import gzip
import importlib.util
from pathlib import Path
import sys
import shutil
import socket
import tarfile
import tempfile
import unittest
from unittest.mock import Mock,patch

spec=importlib.util.spec_from_file_location('recovery',Path(__file__).resolve().parents[1]/'scripts/recover-preview.py')
recovery=importlib.util.module_from_spec(spec);spec.loader.exec_module(recovery)


class RecoveryTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('tar') and hasattr(socket,'AF_UNIX'),'Needs host tar and Unix sockets')
    def test_migration_archive_omits_stale_sockets_but_keeps_world(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'files/tmp').mkdir(parents=True)
            (root/'files/work/run').mkdir(parents=True)
            (root/'files/work/server/Saves').mkdir(parents=True)
            (root/'files/work/server/Saves/world.bin').write_bytes(b'saved world')
            (root/'files/work/run/api-token').write_text('expired session')
            try:sock=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
            except PermissionError:self.skipTest('This host disallows Unix sockets; CI exercises this case')
            with sock:
                sock.bind(str(root/'files/tmp/frames.sock'))
                adb=Mock();adb.archive_command.return_value=['tar','-C',d]+recovery.archive_args('files')[1:]
                target=recovery.capture(adb,'files',root/'backup.tar.gz')
            with tarfile.open(target) as archive:
                self.assertEqual(archive.extractfile('files/work/server/Saves/world.bin').read(),b'saved world')
                self.assertFalse(any(n.startswith(('files/tmp','files/work/run')) for n in archive.getnames()))

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
