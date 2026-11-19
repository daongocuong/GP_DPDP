"""Small controller tests; no benchmark or simulator rollout is launched."""
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
import ctypes
from ctypes import wintypes

from dpdp_v3_supervisor import DecisionTraceMonitor, select_timeout_reason


def marker(event, index=1, **extra):
    value = dict(schema='dpdp-smoke-decision-v1', event=event, algorithm='gp',
                 partition='train', decision_index=index, simulation_seconds=123)
    value.update(extra)
    return (json.dumps(value)+'\n').encode('utf-8')


class TraceProtocolTests(unittest.TestCase):
    def test_start_end_counts_only_guarded_end(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/'trace.jsonl'
            p.write_bytes(marker('START') + marker('END', decision_elapsed_seconds=.2, status='completed'))
            monitor = DecisionTraceMonitor(p, 20, 'train', 'gp')
            self.assertIsNone(monitor.poll(1))
            self.assertEqual(monitor.completed, 1)
            monitor.finish()

    def test_decision_deadline_and_timeout_record_fields(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/'trace.jsonl'; p.write_bytes(marker('START'))
            monitor = DecisionTraceMonitor(p, 2, 'train', 'gp')
            self.assertIsNone(monitor.poll(10))
            event = monitor.poll(12.1)
            self.assertEqual(event['kind'], 'DECISION_TIMEOUT')
            self.assertEqual(event['decision_index'], 1)
            self.assertEqual(event['simulation_seconds'], 123)
            self.assertEqual(event['completed_decisions'], 0)
            self.assertEqual(event['timeout_type'], 'decision_hard_timeout')

    def test_progress_marker_counters_are_validated_and_retained(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/'trace.jsonl'
            p.write_bytes(marker('START') + marker('PROGRESS', candidate_count=5000,
                feasible_count=900, rejected_count=4100, groups_total=14,
                groups_processed=3, decision_elapsed_seconds=4.2))
            monitor = DecisionTraceMonitor(p, 20, 'train', 'gp')
            self.assertIsNone(monitor.poll(10))
            self.assertEqual(monitor.pending['progress'], dict(candidate_count=5000,
                feasible_count=900, rejected_count=4100, groups_total=14, groups_processed=3))
            p.write_bytes(p.read_bytes() + marker('PROGRESS', candidate_count=4000,
                feasible_count=900, rejected_count=3100, groups_total=14,
                groups_processed=3, decision_elapsed_seconds=4.4))
            with self.assertRaisesRegex(ValueError, 'nonmonotonic'):
                monitor.poll(10.1)

    def test_late_end_is_timeout_not_completed_decision(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/'trace.jsonl'
            p.write_bytes(marker('START') + marker('END', decision_elapsed_seconds=2.1,
                                                   status='completed'))
            monitor = DecisionTraceMonitor(p, 2, 'train', 'gp')
            event = monitor.poll(10)
            self.assertEqual(event['kind'], 'DECISION_TIMEOUT')
            self.assertEqual(monitor.completed, 0)

    def test_duplicate_or_out_of_order_markers_fail_closed(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/'trace.jsonl'
            p.write_bytes(marker('START') + marker('START'))
            with self.assertRaisesRegex(ValueError, 'duplicate/out-of-order START'):
                DecisionTraceMonitor(p, 20).poll(1)
            p.write_bytes(marker('END'))
            with self.assertRaisesRegex(ValueError, 'orphan/duplicate END'):
                DecisionTraceMonitor(p, 20).poll(1)

    def test_marker_metadata_and_truncated_line_fail_closed(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/'trace.jsonl'; p.write_bytes(marker('START', algorithm='vnsme'))
            with self.assertRaisesRegex(ValueError, 'algorithm mismatch'):
                DecisionTraceMonitor(p, 20, 'train', 'gp').poll(1)
            p.write_bytes(marker('START').rstrip())
            monitor = DecisionTraceMonitor(p, 20)
            self.assertIsNone(monitor.poll(1))
            with self.assertRaisesRegex(ValueError, 'truncated final'):
                monitor.finish()

    def test_stage_deadline_has_priority_when_deadlines_tie(self):
        self.assertEqual(select_timeout_reason(True, True), 'stage_wall_timeout')
        self.assertEqual(select_timeout_reason(False, True), 'decision_hard_timeout')
        self.assertIsNone(select_timeout_reason(False, False))


@unittest.skipUnless(os.name == 'nt', 'Windows Job Object integration test')
class WindowsStageControllerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from dpdp_v3_supervisor import supervise
        cls.supervise = staticmethod(supervise)
        cls.root = tempfile.TemporaryDirectory()
        cls.path = Path(cls.root.name)

    @classmethod
    def tearDownClass(cls):
        cls.root.cleanup()

    def launch(self, name, source, stage=4, decision=.3):
        trace = self.path/f'{name}.jsonl'; trace.touch()
        return self.supervise([sys.executable, '-c', source],
            self.path/name, stage, interval=.02, gap_limit=1,
            decision_trace=trace, decision_timeout=decision, partition='train', algorithm='gp'), trace

    def test_decision_timeout_is_durable_and_kills_worker(self):
        code = ("import json,time,pathlib; p=pathlib.Path(%r); "
                "p.open('a').write(json.dumps(dict(schema='dpdp-smoke-decision-v1',event='START',"
                "algorithm='gp',partition='train',decision_index=1,simulation_seconds=42))+'\\n'); "
                "p.open('a').write(json.dumps(dict(schema='dpdp-smoke-decision-v1',event='PROGRESS',"
                "algorithm='gp',partition='train',decision_index=1,simulation_seconds=42,"
                "candidate_count=4200,feasible_count=900,rejected_count=3300,groups_total=7,"
                "groups_processed=2,decision_elapsed_seconds=.1))+'\\n'); time.sleep(30)")
        result, trace = self.launch('decision_timeout', code % str(self.path/'decision_timeout.jsonl'))
        self.assertEqual(result['state'], 'DECISION_TIMEOUT')
        self.assertFalse(result['remaining_job_processes'])
        rows = [json.loads(x) for x in trace.read_text().splitlines()]
        timeout = rows[-1]
        self.assertEqual(timeout['event'], 'TIMEOUT')
        self.assertEqual(timeout['timeout_type'], 'decision_hard_timeout')
        self.assertEqual(timeout['decision_index'], 1)
        self.assertEqual(timeout['simulation_seconds'], 42)
        self.assertEqual(timeout['completed_decisions'], 0)
        self.assertEqual((timeout['candidate_count'], timeout['feasible_count'],
                          timeout['rejected_count'], timeout['groups_total'],
                          timeout['groups_processed']), (4200, 900, 3300, 7, 2))
        self.assertGreaterEqual(timeout['elapsed_wall_seconds'], .15)

    def test_stage_timeout_is_durable_without_open_decision(self):
        result, trace = self.launch('stage_timeout', 'import time; time.sleep(30)', stage=.2)
        self.assertEqual(result['state'], 'TIMEOUT')
        self.assertFalse(result['remaining_job_processes'])
        event = json.loads(trace.read_text().splitlines()[-1])
        self.assertEqual(event['event'], 'TIMEOUT')
        self.assertEqual(event['timeout_type'], 'stage_wall_timeout')
        self.assertIsNone(event['decision_index'])
        self.assertEqual(event['completed_decisions'], 0)
        self.assertIsNone(event['candidate_count'])
        self.assertIsNone(event['groups_total'])

    def test_stage_timeout_kills_worker_descendant_in_job_object(self):
        import subprocess
        pid_path = self.path/'descendant.pid'
        trace_path = self.path/'descendant_timeout.jsonl'
        worker = ("import json,pathlib,subprocess,sys,time; "
                  "child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)']); "
                  "pathlib.Path(%r).write_text(str(child.pid)); "
                  "pathlib.Path(%r).write_text(json.dumps(dict(schema='dpdp-smoke-decision-v1',"
                  "event='START',algorithm='gp',partition='train',decision_index=1,"
                  "simulation_seconds=42))+'\\n'); time.sleep(60)" % (str(pid_path), str(trace_path)))
        result, trace = self.launch('descendant_timeout', worker, stage=.8, decision=2.0)
        self.assertEqual(result['state'], 'TIMEOUT')
        self.assertEqual(trace, trace_path)
        self.assertFalse(result['remaining_job_processes'])
        child_pid = int(pid_path.read_text(encoding='utf-8'))
        kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel32.GetExitCodeProcess.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL
        handle = kernel32.OpenProcess(0x1000, False, child_pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if handle:
            try:
                exit_code = wintypes.DWORD()
                self.assertTrue(kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)))
                self.assertNotEqual(exit_code.value, 259, 'descendant is still running after Job Object cleanup')
            finally:
                kernel32.CloseHandle(handle)

    def test_invalid_marker_fails_closed_and_kills_worker(self):
        code = ("import json,time,pathlib; p=pathlib.Path(%r); "
                "p.open('a').write(json.dumps(dict(schema='dpdp-smoke-decision-v1',event='END',"
                "algorithm='gp',partition='train',decision_index=1,simulation_seconds=42))+'\\n'); time.sleep(30)")
        result, trace = self.launch('bad_marker', code % str(self.path/'bad_marker.jsonl'))
        self.assertEqual(result['state'], 'INVALID_TRACE')
        self.assertFalse(result['remaining_job_processes'])
        event = json.loads(trace.read_text().splitlines()[-1])
        self.assertEqual(event['event'], 'TRACE_ERROR')
        self.assertIn('orphan/duplicate END', event['error'])


class DecisionCapTests(unittest.TestCase):
    def test_fifth_decision_counts_only_after_policy_and_guard(self):
        from unittest.mock import patch
        import run_dpdp_insertion as runner
        with tempfile.TemporaryDirectory() as d:
            trace = Path(d)/'trace.jsonl'
            class Fake:
                mode='gp'; stage_trace_path=trace; stage_partition='train'
                stage_started=time.perf_counter(); max_decision_points=5
                decision_times=[{}, {}, {}, {}]
                env=type('Env', (), {'now': 999})()
                policy=type('Policy', (), {'decide': lambda self, model: {'orders': {}}})()
            guard_called=[]
            with patch.object(runner, 'guard_raw_decision', side_effect=lambda model, raw: guard_called.append(True)):
                raw = runner.RunModel.routing_callback(Fake())
            rows = [json.loads(x) for x in trace.read_text().splitlines()]
            self.assertEqual([x['event'] for x in rows], ['START', 'END'])
            self.assertEqual(len(guard_called), 1)
            self.assertEqual(rows[-1]['completed_decisions'], 5)
            self.assertEqual(raw, {'orders': {}})

    def test_fifth_decision_returns_to_simulator_then_stops_outside_callback(self):
        from unittest.mock import patch
        import run_dpdp_insertion as runner
        with tempfile.TemporaryDirectory() as d:
            trace = Path(d)/'trace.jsonl'
            class FakeModel:
                mode='gp'; stage_trace_path=trace; stage_partition='train'
                stage_started=time.perf_counter(); max_decision_points=5
                decision_times=[{}, {}, {}, {}]; smoke_stop_requested=False
                policy=type('Policy', (), {'decide': lambda self, model: {'orders': {}}})()
                env=None
            model = FakeModel()
            class FakeEnvironment:
                now=2400
                stepped=False
                def peek(self): return 2400
                def step(self):
                    self.stepped=True
                    self.route = runner.RunModel.routing_callback(model)
            model.env = FakeEnvironment()
            with patch.object(runner, 'guard_raw_decision', return_value=None):
                with self.assertRaises(runner.SmokeLimitReached):
                    runner.step_simulation_event(model, time.perf_counter(), 20, 3000)
            self.assertTrue(model.env.stepped)
            self.assertEqual(model.env.route, {'orders': {}})
            self.assertTrue(model.smoke_stop_requested)
            self.assertEqual([json.loads(x)['event'] for x in trace.read_text().splitlines()],
                             ['START', 'END'])

    def test_real_routing_error_is_not_converted_to_smoke_completion(self):
        from unittest.mock import patch
        from dvrpsim.exceptions import RoutingError
        import run_dpdp_insertion as runner
        import instance35_stage as stage
        model = type('Model', (), {'env':type('Env', (), {
            'peek':lambda self:2400,
            'step':lambda self:(_ for _ in ()).throw(RoutingError('problem with routing: infeasible route'))})(),
            'smoke_stop_requested':False})()
        with self.assertRaisesRegex(RoutingError, 'infeasible route'):
            runner.step_simulation_event(model, time.perf_counter(), 20, 3000)
        events=[]
        for index in range(1,6):
            events.extend([{'event':'START','decision_index':index,'algorithm':'gp','partition':'train'},
                {'event':'END','decision_index':index,'algorithm':'gp','partition':'train',
                 'status':'completed','completed_decisions':index}])
        failed_runner=dict(status='INVALID',valid=False,partial=False,score=None,J=None,decision_count=5)
        failed_supervisor=dict(state='EXITED',exit_code=1,valid_supervision=True,remaining_job_processes=[])
        self.assertFalse(stage.is_clean_smoke(failed_supervisor, events, failed_runner))

    def test_fifth_decision_guard_error_is_not_counted_complete(self):
        from unittest.mock import patch
        import run_dpdp_insertion as runner
        with tempfile.TemporaryDirectory() as d:
            trace = Path(d)/'trace.jsonl'
            class Fake:
                mode='gp'; stage_trace_path=trace; stage_partition='train'
                stage_started=time.perf_counter(); max_decision_points=5
                decision_times=[{}, {}, {}, {}]
                env=type('Env', (), {'now': 999})()
                policy=type('Policy', (), {'decide': lambda self, model: {'orders': {}}})()
            with patch.object(runner, 'guard_raw_decision', side_effect=ValueError('infeasible')):
                with self.assertRaisesRegex(ValueError, 'infeasible'):
                    runner.RunModel.routing_callback(Fake())
            rows = [json.loads(x) for x in trace.read_text().splitlines()]
            self.assertEqual([x['event'] for x in rows], ['START', 'ERROR'])
            self.assertEqual(rows[-1]['completed_decisions'], 4)

    def test_twelfth_decision_is_guarded_then_stops_without_decision_thirteen(self):
        from unittest.mock import patch
        import run_dpdp_insertion as runner
        with tempfile.TemporaryDirectory() as d:
            trace=Path(d)/'trace.jsonl'
            class FakeModel:
                mode='gp'; stage_trace_path=trace; stage_partition='train'
                stage_started=time.perf_counter(); max_decision_points=12
                decision_times=[{} for _ in range(11)]; smoke_stop_requested=False
                policy=type('Policy',(),{'decide':lambda self,model:{'orders':{}}})()
                env=None
            model=FakeModel()
            class FakeEnvironment:
                now=6600
                def peek(self): return 6600
                def step(self): runner.RunModel.routing_callback(model)
            model.env=FakeEnvironment()
            with patch.object(runner,'guard_raw_decision',return_value=None):
                with self.assertRaises(runner.SmokeLimitReached):
                    runner.step_simulation_event(model,time.perf_counter(),20,7000)
            rows=[json.loads(x) for x in trace.read_text().splitlines()]
            self.assertEqual([r['event'] for r in rows],['START','END'])
            self.assertEqual(rows[-1]['decision_index'],12)
            self.assertEqual(rows[-1]['completed_decisions'],12)
            self.assertTrue(model.smoke_stop_requested)


class StageMetadataTests(unittest.TestCase):
    def test_gp_pilot_is_bounded_and_partial(self):
        import instance35_stage as stage
        config = stage.gp_pilot_stage_config()
        self.assertEqual(config['max_decision_points'], 8)
        self.assertEqual(config['decision_hard_timeout_seconds'], 60)
        self.assertEqual(config['stage_wall_timeout_seconds'], 300)
        self.assertEqual(config['runner_wall_guard_seconds'], 360)
        self.assertEqual(config['simulation_time_slot_seconds'], 600)
        self.assertIs(config['feasibility_profile_enabled'], True)
        self.assertIs(config['decision_progress_enabled'], False)
        self.assertIn('J and score are null', config['objective_policy'])

        extended = stage.gp_pilot_stage_config(feasibility_profile_enabled=False, decision_cap=12)
        self.assertEqual(extended['max_decision_points'], 12)
        self.assertEqual(extended['decision_hard_timeout_seconds'], 60)
        self.assertEqual(extended['stage_wall_timeout_seconds'], 360)
        self.assertEqual(extended['runner_wall_guard_seconds'], 420)
        self.assertEqual(extended['simulation_time_slot_seconds'], 600)
        self.assertIs(extended['feasibility_profile_enabled'], False)
        self.assertIs(extended['decision_progress_enabled'], True)
        self.assertGreater(extended['runner_wall_guard_seconds'], extended['stage_wall_timeout_seconds'])
        with self.assertRaisesRegex(ValueError, 'must be 8 or 12'):
            stage.gp_pilot_stage_config(decision_cap=13)

    def test_extended_pilot_requires_exact_guarded_partial_twelve(self):
        import instance35_stage as stage
        events=[]
        for index in range(1,13):
            common=dict(algorithm='gp',partition='train',decision_index=index,
                        simulation_seconds=(index-1)*600)
            events.append(dict(**common,event='START'))
            events.append(dict(**common,event='PROGRESS',
                candidate_count=5000,feasible_count=900,rejected_count=4100,
                groups_total=14,groups_processed=10))
            events.append(dict(**common,event='END',status='completed',
                completed_decisions=index,decision_elapsed_seconds=10,
                profile=dict(examined=10000,feasible=2000,rejected=8000,
                    groups_total=14,groups_processed=14)))
        outcome=dict(state='EXITED',exit_code=0,valid_supervision=True,remaining_job_processes=[])
        runner=dict(status='SMOKE_COMPLETED',partial=True,score=None,J=None,decision_count=12)
        self.assertTrue(stage.is_clean_gp_pilot(outcome,events,runner,12))
        self.assertFalse(stage.is_clean_gp_pilot(outcome,events[:-1],runner,12))
        self.assertFalse(stage.is_clean_gp_pilot(outcome,events+[dict(event='TIMEOUT')],runner,12))
        self.assertFalse(stage.is_clean_gp_pilot(outcome,events,
            dict(status='SMOKE_COMPLETED',partial=True,score=1,J=None,decision_count=12),12))

    def test_gp_pilot_can_record_and_apply_profile_off_mode(self):
        import instance35_stage as stage
        import instance35_temporal as protocol
        config = stage.gp_pilot_stage_config(feasibility_profile_enabled=False)
        self.assertIs(config['feasibility_profile_enabled'], False)
        from unittest.mock import patch
        with patch.object(sys, 'argv', ['instance35_stage.py', 'pilot', '--algorithm', 'gp',
                                        '--run-id', 'profile_off_test', '--no-feasibility-profile']), \
             patch.object(stage, 'run_gp_pilot', return_value={'status': 'test'} ) as run, \
             patch('builtins.print'):
            stage.main()
        run.assert_called_once_with('profile_off_test', False, 8)

        with tempfile.TemporaryDirectory() as directory:
            run_root = Path(directory)
            (run_root/'data'/'train').mkdir(parents=True)
            outcome = dict(state='EXITED', exit_code=0, valid_supervision=True,
                           remaining_job_processes=[])
            with patch.object(protocol, 'RUN', run_root), \
                 patch.object(stage, 'supervise', return_value=outcome) as supervise:
                stage.run_gp_pilot('profile_off_command_test', feasibility_profile_enabled=False)
            command = supervise.call_args.args[0]
            self.assertIn('--no-feasibility-profile', command)
            saved = json.loads((run_root/'pilot'/'gp'/'profile_off_command_test'/'pilot_config.json')
                               .read_text(encoding='utf-8'))
            self.assertIs(saved['feasibility_profile_enabled'], False)

            with patch.object(protocol, 'RUN', run_root), \
                 patch.object(stage, 'supervise', return_value=outcome) as supervise:
                stage.run_gp_pilot('extended_command_test', feasibility_profile_enabled=False,
                                   decision_cap=12)
            command = supervise.call_args.args[0]
            self.assertIn('--no-feasibility-profile', command)
            self.assertIn('--decision-progress', command)
            self.assertEqual(command[command.index('--max-decision-points')+1], '12')
            self.assertEqual(command[command.index('--wall-seconds')+1], '420')
            self.assertEqual(supervise.call_args.args[2], 360)
            saved = json.loads((run_root/'pilot'/'gp'/'extended_command_test'/'pilot_config.json')
                               .read_text(encoding='utf-8'))
            self.assertEqual(saved['max_decision_points'], 12)
            self.assertEqual(saved['runner_wall_guard_seconds'], 420)

            def fake_complete_supervise(command, supervisor_output, timeout, **kwargs):
                runner_dir=Path(command[command.index('--output')+1])
                runner_dir.mkdir(parents=True)
                trace=Path(kwargs['decision_trace'])
                events=[]
                for index in range(1,13):
                    sim=(index-1)*600
                    common=dict(schema='dpdp-smoke-decision-v1',algorithm='gp',
                                partition='train',decision_index=index,simulation_seconds=sim)
                    events.append(dict(**common,event='START'))
                    events.append(dict(**common,event='PROGRESS',candidate_count=5000,
                        feasible_count=900,rejected_count=4100,groups_total=14,
                        groups_processed=10,decision_elapsed_seconds=10))
                    events.append(dict(**common,event='END',status='completed',
                        completed_decisions=index,decision_elapsed_seconds=10,
                        profile=dict(examined=10000,feasible=2000,rejected=8000,
                            groups_total=14,groups_processed=14)))
                trace.write_text(''.join(json.dumps(event)+'\n' for event in events),encoding='utf-8')
                (runner_dir/'result.json').write_text(json.dumps(dict(status='SMOKE_COMPLETED',
                    partial=True,score=None,J=None,decision_count=12)),encoding='utf-8')
                return dict(state='EXITED',exit_code=0,valid_supervision=True,
                            remaining_job_processes=[],stop_event=None)
            with patch.object(protocol, 'RUN', run_root), \
                 patch.object(stage,'supervise',side_effect=fake_complete_supervise):
                result=stage.run_gp_pilot('completed_extended_fixture',False,12)
            self.assertEqual(result['status'],'PILOT_PARTIAL_COMPLETED')
            self.assertTrue(result['partial'])
            self.assertIsNone(result['J'])
            self.assertIsNone(result['score'])
            self.assertEqual(result['completed_decisions'],12)

    def test_timeout_pilot_result_is_incomplete_and_never_has_j(self):
        import instance35_stage as stage
        import instance35_temporal as protocol
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as directory:
            run_root=Path(directory)
            (run_root/'data'/'train').mkdir(parents=True)
            outcome=dict(state='DECISION_TIMEOUT',exit_code=None,valid_supervision=True,
                remaining_job_processes=[],stop_event={'timeout_type':'decision_hard_timeout'})
            def fake_supervise(command, output, timeout, **kwargs):
                trace=Path(kwargs['decision_trace'])
                trace.write_text(json.dumps(dict(schema='dpdp-smoke-decision-v1',
                    event='TIMEOUT',algorithm='gp',partition='train',decision_index=1,
                    simulation_seconds=600,elapsed_wall_seconds=60,completed_decisions=0,
                    timeout_type='decision_hard_timeout',candidate_count=5000,
                    feasible_count=900,rejected_count=4100,groups_total=12,
                    groups_processed=3))+'\n',encoding='utf-8')
                return outcome
            with patch.object(protocol,'RUN',run_root), patch.object(stage,'supervise',side_effect=fake_supervise):
                result=stage.run_gp_pilot('timeout_fixture',False,12)
            self.assertEqual(result['status'],'TIMEOUT')
            self.assertTrue(result['partial'])
            self.assertIsNone(result['J'])
            self.assertIsNone(result['score'])
            self.assertEqual(result['completed_decisions'],0)

    def test_vnsme_smoke_uses_three_distinct_timeout_layers(self):
        import instance35_stage as stage
        config = stage.applied_stage_config(algorithm='vnsme')
        self.assertEqual(config['internal_search_budget_seconds'], 10)
        self.assertEqual(config['subprocess_hard_timeout_seconds'], 18)
        self.assertEqual(config['decision_hard_timeout_seconds'], 20)
        self.assertEqual(config['stage_wall_timeout_seconds'], 120)
        self.assertEqual(config['runner_wall_guard_seconds'], 120)
        self.assertEqual(config['decision_timeout_overrides_seconds'], {})

    def test_applied_timeouts_are_distinct_from_inspection_defaults(self):
        import instance35_stage as stage
        import instance35_temporal as temporal
        inspection = temporal.inspect()
        self.assertNotIn('timeout_config', inspection)
        self.assertIn('inspection_reference_timeouts_not_applied', inspection)
        generated = stage.protocol_metadata(inspection)
        self.assertNotIn('timeout_config', generated['dataset'])
        self.assertEqual(generated['applied_stage_config']['decision_hard_timeout_seconds'], 20)

        # Older in-memory inspection payloads get relabelled when preparing new metadata.
        report = stage.protocol_metadata(dict(instance=35, timeout_config={
            'smoke_wall_seconds': 360, 'vnsme_search_seconds': 50,
            'decision_hard_seconds': 60}))
        config = report['applied_stage_config']
        self.assertNotIn('timeout_config', report['dataset'])
        self.assertEqual(report['dataset']['inspection_reference_timeouts_not_applied'], {
            'smoke_wall_seconds': 360, 'vnsme_search_seconds': 50,
            'decision_hard_seconds': 60})
        self.assertEqual(config['decision_hard_timeout_seconds'], 20)
        self.assertEqual(config['stage_wall_timeout_seconds'], 120)
        self.assertEqual(config['runner_wall_guard_seconds'], 1800)
        self.assertEqual(config['simulation_time_slot_seconds'], 600)
        self.assertEqual(config['max_decision_points'], 5)

    def test_measurement_timeout_is_bounded_and_recordable(self):
        import instance35_stage as stage
        config = stage.applied_stage_config(60)
        self.assertEqual(config['decision_hard_timeout_seconds'], 20)
        self.assertEqual(config['decision_timeout_overrides_seconds'], {'5': 60})
        self.assertEqual(config['stage_wall_timeout_seconds'], 120)
        with self.assertRaisesRegex(ValueError, 'between 20 and 60'):
            stage.applied_stage_config(60.01)

    def test_clean_smoke_requires_runner_and_supervisor_agreement(self):
        import instance35_stage as stage
        events=[]
        for index in range(1,6):
            events.extend([{'event':'START','decision_index':index,'algorithm':'gp','partition':'train'},
                {'event':'END','decision_index':index,'algorithm':'gp','partition':'train',
                 'status':'completed','completed_decisions':index}])
        outcome=dict(state='EXITED',exit_code=0,valid_supervision=True,remaining_job_processes=[])
        runner=dict(status='SMOKE_COMPLETED',valid=False,partial=True,score=None,J=None,decision_count=5)
        self.assertTrue(stage.is_clean_smoke(outcome,events,runner))
        self.assertFalse(stage.is_clean_smoke(outcome,events[:-2],runner))
        self.assertFalse(stage.is_clean_smoke(outcome,events+[events[-1]],runner))

    def test_supervisor_override_applies_only_to_decision_five(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/'trace.jsonl'
            stream = b''
            for index in range(1, 5):
                stream += marker('START', index=index)
                stream += marker('END', index=index, decision_elapsed_seconds=1, status='completed')
            stream += marker('START', index=5)
            p.write_bytes(stream)
            monitor = DecisionTraceMonitor(p, 20, 'train', 'gp', {5: 60})
            self.assertIsNone(monitor.poll(0))
            self.assertEqual(monitor.completed, 4)
            self.assertEqual(monitor.timeout_for(4), 20)
            self.assertEqual(monitor.timeout_for(5), 60)
            self.assertEqual(monitor.pending['index'], 5)
            self.assertEqual(monitor.pending['timeout_seconds'], 60)
            self.assertIsNone(monitor.poll(59.9))
            self.assertEqual(monitor.poll(60.1)['timeout_type'], 'decision_hard_timeout')


if __name__ == '__main__':
    unittest.main()
