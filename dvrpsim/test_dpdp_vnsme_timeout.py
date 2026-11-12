"""Timeout diagnostics preserve the real failure, including failed logging."""
import itertools
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import run_dpdp_insertion  # Establish the same src import path as the runner.
from baselines.vnsme import JavaSession, VNSMEError, capture_bytes


class CaptureTests(unittest.TestCase):
    def test_bytes_text_none_and_non_utf8_bytes(self):
        self.assertEqual(capture_bytes(None), b'')
        self.assertEqual(capture_bytes('ti\u1ebfng Vi\u1ec7t'), 'ti\u1ebfng Vi\u1ec7t'.encode('utf-8'))
        self.assertEqual(capture_bytes(b'\xffraw'), b'\xffraw')


class TimeoutTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        network = self.root/'network.csv'
        network.write_text('not read by the subprocess test', encoding='utf-8')
        self.session = JavaSession(self.root/'session', network, network, timeout=5)
        self.state = dict(vehicle_info=[dict(id='V_1', update_time=100000, destination=None)],
                          ongoing_orders=[], unallocated_orders=[])

    def test_all_timeout_stream_type_combinations_keep_original_cause(self):
        values = (b'raw\xff', 'text \u0111\u1ecf', None)
        for stdout, stderr in itertools.product(values, repeat=2):
            timeout = subprocess.TimeoutExpired(['unchanged-java'], .25, output=stdout, stderr=stderr)
            with self.subTest(stdout=type(stdout).__name__, stderr=type(stderr).__name__):
                with patch('baselines.vnsme.subprocess.run', side_effect=timeout):
                    with self.assertRaises(VNSMEError) as raised:
                        self.session.invoke(self.state, remaining=.25)
                self.assertIs(raised.exception.__cause__, timeout)
                epoch = self.session.directory/'epochs'/f'{len(self.session.records)-1:05d}'
                self.assertEqual((epoch/'stdout.txt').read_bytes(), capture_bytes(stdout))
                self.assertEqual((epoch/'stderr.txt').read_bytes(), capture_bytes(stderr))
                record = json.loads((epoch/'invocation.json').read_text())
                self.assertFalse(record['valid'])
                self.assertIn('TimeoutExpired', record['error'])
                self.assertEqual(record['effective_timeout_seconds'], .25)
                self.assertEqual(record['configured_timeout_seconds'], 5)
                self.assertEqual(record['timeout_seconds'], .25)
                self.assertEqual(record['timeout_command'], ['unchanged-java'])
                self.assertEqual(record['command'], self.session.command)
                self.assertEqual(record['cwd'], str(self.session.directory))

    def test_capture_write_failure_does_not_hide_timeout_or_other_stream(self):
        timeout = subprocess.TimeoutExpired(['java'], .1, output='stdout text', stderr=b'stderr bytes')
        original = Path.write_bytes
        def failing_stdout(path, data):
            if path.name == 'stdout.txt':
                raise OSError('diagnostic disk error')
            return original(path, data)
        with patch('baselines.vnsme.subprocess.run', side_effect=timeout), patch.object(Path, 'write_bytes', failing_stdout):
            with self.assertRaises(VNSMEError) as raised:
                self.session.invoke(self.state)
        self.assertIs(raised.exception.__cause__, timeout)
        epoch = self.session.directory/'epochs/00000'
        self.assertEqual((epoch/'stderr.txt').read_bytes(), b'stderr bytes')
        record = json.loads((epoch/'invocation.json').read_text())
        self.assertIn('TimeoutExpired', record['error'])
        self.assertIn('stdout.txt', record['diagnostic_errors'][0])

    def test_invocation_write_failure_cannot_mask_primary_exception(self):
        timeout = subprocess.TimeoutExpired(['java'], .1, output='out', stderr='err')
        from baselines.vnsme import write_json
        def invocation_only(path, value):
            if path.name == 'invocation.json':
                raise OSError('cannot record invocation')
            return write_json(path, value)
        with patch('baselines.vnsme.subprocess.run', side_effect=timeout), \
             patch('baselines.vnsme.write_json', side_effect=invocation_only):
            with self.assertRaises(VNSMEError) as raised:
                self.session.invoke(self.state)
        self.assertIs(raised.exception.__cause__, timeout)
        self.assertIn('invocation.json', self.session.records[-1]['diagnostic_errors'][0])
        self.assertFalse(self.session.records[-1]['valid'])

    def test_success_without_invocation_record_is_rejected(self):
        self.session.command = [sys.executable, '-c',
            "from pathlib import Path; import json; p=Path('algorithm/data_interaction'); "
            "(p/'output_destination.json').write_text('{\"V_1\":null}'); "
            "(p/'output_route.json').write_text('{\"V_1\":[]}'); "
            "(p/'solution.json').write_text(json.dumps({'no.':'0','route_after':'V_1:[]'})); print('SUCCESS')"]
        from baselines.vnsme import write_json
        def invocation_only(path, value):
            if path.name == 'invocation.json':
                raise OSError('cannot record invocation')
            return write_json(path, value)
        with patch('baselines.vnsme.write_json', side_effect=invocation_only):
            with self.assertRaisesRegex(VNSMEError, 'Cannot record'):
                self.session.invoke(self.state)
        self.assertFalse(self.session.records[-1]['valid'])

    def test_real_timeout_after_stdout_and_stderr_is_preserved(self):
        self.session.command = [sys.executable, '-u', '-c',
            "import sys,time; print('partial stdout',flush=True); "
            "print('partial stderr',file=sys.stderr,flush=True); time.sleep(5)"]
        with self.assertRaises(VNSMEError) as raised:
            self.session.invoke(self.state, remaining=.5)
        self.assertIsInstance(raised.exception.__cause__, subprocess.TimeoutExpired)
        epoch = self.session.directory/'epochs/00000'
        self.assertIn(b'partial stdout', (epoch/'stdout.txt').read_bytes())
        self.assertIn(b'partial stderr', (epoch/'stderr.txt').read_bytes())
        self.assertFalse(json.loads((epoch/'invocation.json').read_text())['valid'])


if __name__ == '__main__':
    unittest.main()
