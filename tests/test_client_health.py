import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from client_health import ClientHealth, MAX_LOG_BYTES


class HealthTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)

    def test_samples_a_stopped_child_without_needing_managed_callbacks(self):
        # A real Linux child suspends itself; the external observer must still
        # capture it, with no debugger, managed hook or sampling thread in it.
        child=subprocess.Popen([sys.executable,'-c',
            'import os,signal;os.kill(os.getpid(),signal.SIGSTOP)'])
        try:
            _,status=os.waitpid(child.pid,os.WUNTRACED)
            self.assertTrue(os.WIFSTOPPED(status))
            observer=ClientHealth(child.pid,self.root,interval=0)
            observer.sample();observer.sample()
            rows=[json.loads(row) for row in (self.root/'client-health.log').read_text().splitlines()]
            first,last=[row['processes'][0] for row in rows]
            self.assertEqual(first['state'],'T')
            self.assertIsNone(first['cpu_delta_ticks'])
            self.assertEqual(last['cpu_delta_ticks'],0)
            self.assertEqual(last['thread_samples'][0]['state'],'T')
            os.kill(child.pid,signal.SIGCONT)
            self.assertEqual(child.wait(timeout=5),0)
        finally:
            if child.poll() is None:child.kill();child.wait()

    def test_unavailable_proc_and_full_filesystem_never_abort_the_client(self):
        observer=ClientHealth(1,self.root,proc=self.root/'missing',interval=0)
        observer.sample()
        self.assertEqual(json.loads((self.root/'client-health.log').read_text())['availability'],'unavailable_or_exited')
        with patch.object(Path,'open',side_effect=OSError('No space left')):
            observer.sample()
        self.assertTrue(observer.disabled)

    def test_rotation_and_throttling_keep_observation_bounded(self):
        path=self.root/'client-health.log'
        path.write_text('old sample\n'*(MAX_LOG_BYTES//11+1))
        observer=ClientHealth(os.getpid(),self.root,interval=60)
        observer.sample();size=path.stat().st_size;observer.sample()
        self.assertEqual(path.stat().st_size,size)
        self.assertLess(size,MAX_LOG_BYTES)
        self.assertTrue((self.root/'client-health.previous.log').exists())

    def test_reused_pid_is_not_sampled_as_the_game(self):
        observer=ClientHealth(os.getpid(),self.root)
        observer.root_start=-1
        self.assertEqual(observer.snapshot(),{'availability':'pid_reused','processes':[]})
