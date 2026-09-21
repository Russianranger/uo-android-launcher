import json
import os
from pathlib import Path
import signal
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from client_health import ClientHealth, MAX_LOG_BYTES, RenderProgress, prepare_render_progress, PROGRESS_SIZE


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

    def test_progress_rejects_partial_rows_and_keeps_failure_evidence(self):
        path=self.root/'progress.bin'
        prepare_render_progress(path)
        reader=RenderProgress(path)
        self.assertEqual(reader.snapshot()['availability'],'not_initialized_or_unknown')
        data=bytearray(PROGRESS_SIZE)
        struct.pack_into('<8s4i',data,0,b'UORTRC02',2,272,16,64)
        struct.pack_into('<6i3q2i',data,32,8,1,5,3,42,0,2,7,1,3,-2146233079)
        path.write_bytes(data)
        row=reader.snapshot()['threads'][0]
        self.assertTrue(row['writer_overlap_seen'] and row['draw_failure_seen'])
        self.assertEqual((row['stage'],row['exited_draw_lists']),('draw_list_exit',1))
        # Odd sequence means the writer did not finish the record.
        struct.pack_into('<i',data,32,9);path.write_bytes(data)
        result=reader.snapshot()
        self.assertEqual(result['threads'],[])
        self.assertEqual(result['busy_slots'],1)
        path.write_bytes(data[:80])
        self.assertEqual(reader.snapshot()['availability'],'invalid_record')

    def test_progress_creates_a_new_inode_and_never_follows_links(self):
        path=self.root/'progress.bin'
        prepare_render_progress(path)
        with path.open('r+b') as old:
            prepare_render_progress(path)
            old.write(b'old client still writing');old.flush()
            self.assertEqual(path.read_bytes(),bytes(PROGRESS_SIZE))
        path.unlink();target=self.root/'target';target.write_text('keep')
        path.symlink_to(target)
        with self.assertRaises(ValueError):prepare_render_progress(path)
        self.assertEqual(RenderProgress(path).snapshot()['availability'],'unavailable')
        self.assertEqual(target.read_text(),'keep')

    def test_unavailable_progress_does_not_disable_process_health(self):
        observer=ClientHealth(os.getpid(),self.root,render_progress=self.root/'absent')
        observer.sample()
        row=json.loads((self.root/'client-health.log').read_text())
        self.assertEqual(row['availability'],'available')
        self.assertEqual(row['render_progress']['availability'],'unavailable')
        self.assertFalse(observer.disabled)
