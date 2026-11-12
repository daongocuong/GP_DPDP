"""Bounded Windows-only watchdog tests; never launch a benchmark."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

@unittest.skipUnless(os.name == 'nt', 'Windows Job Object test')
class WindowsSupervisorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from dpdp_v3_supervisor import supervise, process_identity
        cls.supervise = staticmethod(supervise)
        cls.identity = staticmethod(process_identity)
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.java = shutil.which('java'); javac = shutil.which('javac')
        if not cls.java or not javac: raise unittest.SkipTest('JDK required for process-tree probe')
        (cls.root/'SleepProbe.java').write_text('public class SleepProbe { public static void main(String[] a) throws Exception { System.out.println("started"); Thread.sleep(30000); } }', encoding='utf-8')
        subprocess.run([javac, str(cls.root/'SleepProbe.java')], check=True, capture_output=True, timeout=15)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def java_parent(self):
        code = 'import subprocess,time; subprocess.Popen(%r); time.sleep(30)' % [self.java, '-cp', str(self.root), 'SleepProbe']
        return [sys.executable, '-c', code]

    def test_timeout_kills_real_java_descendant(self):
        r = self.supervise(self.java_parent(), self.root/'timeout', 2, .1, 1)
        self.assertEqual(r['state'], 'TIMEOUT')
        self.assertFalse(r['valid_supervision'])
        observed = [p for s in r['samples'] for p in s['processes'] if p['name'].lower() == 'java.exe']
        self.assertTrue(observed, 'Java descendant must have actually been sampled')
        self.assertFalse(r['remaining_job_processes'])
        for p in observed:
            try: current = self.identity(p['pid'])
            except OSError: continue
            self.assertNotEqual(current['creation_filetime_100ns'], p['creation_filetime_100ns'])

    def test_monitor_gap_fails_closed_and_kills_descendants(self):
        r = self.supervise(self.java_parent(), self.root/'gap', 5, .1, .4, test_stall=1)
        self.assertEqual(r['state'], 'MONITORING_GAP')
        self.assertFalse(r['valid_supervision'])
        self.assertTrue(r['gaps'])
        self.assertFalse(r['remaining_job_processes'])

    def test_epoch_deadline_stops_whole_job(self):
        epoch = self.root/'epochs'/'00000'; epoch.mkdir(parents=True)
        code = ("import json,time,pathlib; p=pathlib.Path(%r); "
                "p.write_text(json.dumps(dict(deadline_monotonic=time.monotonic()+.5,identity={'pid':0}))); time.sleep(30)") % str(epoch/'invocation_start.json')
        r = self.supervise([sys.executable, '-c', code], self.root/'epoch_timeout', 5, .1, 1,
                           epoch_root=self.root/'epochs')
        self.assertEqual(r['state'], 'EPOCH_TIMEOUT')
        self.assertEqual(r['epoch'], '00000')
        self.assertFalse(r['remaining_job_processes'])

    def test_normal_exit(self):
        r = self.supervise([sys.executable, '-c', 'print(42)'], self.root/'ok', 5, .1, 1)
        self.assertTrue(r['valid_supervision'])
        self.assertEqual(r['exit_code'], 0)
        self.assertIn('42', (self.root/'ok'/'process.log').read_text())

    def test_adapter_traces_real_java_epoch_timeout(self):
        sys.path.insert(0, str(Path(__file__).resolve().parent/'src'))
        from baselines.vnsme import JavaSession
        session = object.__new__(JavaSession)
        session.command = [self.java, '-cp', str(self.root), 'SleepProbe']
        session.directory = self.root
        epoch = self.root/'traced'; epoch.mkdir()
        with self.assertRaises(subprocess.TimeoutExpired): session._invoke_traced(epoch, .5)
        start = json.loads((epoch/'invocation_start.json').read_text())
        end = json.loads((epoch/'invocation_process_end.json').read_text())
        self.assertEqual(start['pid'], end['pid'])
        self.assertEqual(start['pid'], start['identity']['pid'])
        self.assertTrue(end['timed_out'])
        self.assertGreaterEqual(end['elapsed_seconds'], .5)
        self.assertIn('started', (epoch/'java_stdout_live.txt').read_text())

if __name__ == '__main__': unittest.main()
