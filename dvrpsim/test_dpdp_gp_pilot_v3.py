"""No-rollout checks for locked pilot selection, budgets and preflight."""
import copy
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from dpdp_gp import Node
from dpdp_gp_rollout_v3 import V3RolloutEvaluator, RolloutBudgetExceeded
import dpdp_gp_training_v3 as training
import train_dpdp_gp_v3 as cli

PILOT = training.ROOT/'protocols/dpdp_gp_vnsme_v3_dev_pilot_v1.json'


class FakeEvaluator:
    calls = []
    fail_train = False

    def __init__(self, *args, **kwargs):
        self.records = []
        self.process_count = 0

    def evaluate(self, tree, instance):
        self.calls.append(instance)
        row = dict(instance=instance, valid=not (self.fail_train and instance == 4),
                   benchmark_J=None if self.fail_train and instance == 4 else '1', cache_hit=True)
        self.records.append(row)
        return row


class PilotTests(unittest.TestCase):
    def setUp(self):
        self.protocol = json.loads(PILOT.read_text(encoding='utf-8'))

    def test_reviewed_protocol_rejects_drift(self):
        training.validate_protocol_document(self.protocol)
        changes = [('pilot', 'train_instances_subset', [2,3]),
                   ('pilot', 'validation_instances', [7]), ('pilot','population',6),
                   ('pilot','gp_rng_seed',1), ('pilot','max_total_wall_seconds',7200),
                   ('selection','schedule','each generation'),
                   ('selection','max_candidates',3),
                   ('cache','reuse','historical cache import')]
        for section, key, value in changes:
            changed = copy.deepcopy(self.protocol)
            changed[section][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                training.validate_protocol_document(changed)

    def _run_fake(self, fail=False):
        FakeEvaluator.calls = []
        FakeEvaluator.fail_train = fail
        snapshot = dict(protocol=self.protocol, protocol_sha256='test',
                        train_instances=[2,3,4,5], validation_instances=[6],
                        reference_path='test', reference_sha256='test',
                        split_protocol_sha256='test', source_manifest_sha256='test')
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(training, '_load_locked_inputs', return_value=(snapshot, {i:1 for i in range(2,7)}, {}, {})), \
                 patch.object(training, 'V3RolloutEvaluator', FakeEvaluator):
                result = training.run_experiment(Path(temp)/'new')
            candidates = json.loads((Path(temp)/'new/candidates.json').read_text()) if (Path(temp)/'new/candidates.json').exists() else []
            selected = (Path(temp)/'new/selected_tree.json').exists()
        return result, candidates, selected

    def test_full_evolution_precedes_terminal_validation_shortlist(self):
        result, candidates, selected = self._run_fake()
        self.assertEqual(result['status'], 'development_pilot_complete')
        self.assertEqual(len(result['generations']), 3)
        self.assertEqual([g['train_instances'] for g in result['generations']], [[2,3,4,5]]*3)
        calls = FakeEvaluator.calls
        first_validation = calls.index(6)
        self.assertGreaterEqual(first_validation, 48)
        self.assertLessEqual(calls.count(6), 2)
        self.assertTrue(all(i in (2,3,4,5) for i in calls[:first_validation]))
        self.assertEqual(len(candidates), 2)
        self.assertTrue(selected)
        self.assertFalse(result['official_training'])

    def test_failed_train_never_consults_validation_or_selects(self):
        result, _, selected = self._run_fake(fail=True)
        self.assertNotIn(6, FakeEvaluator.calls)
        self.assertFalse(selected)
        self.assertNotEqual(result['status'], 'development_pilot_complete')

    def test_preflight_cannot_construct_evaluator(self):
        with patch.object(training, '_load_locked_inputs', return_value=({}, {}, {}, {})), \
             patch.object(training, 'V3RolloutEvaluator') as evaluator:
            result = training.preflight(PILOT)
            evaluator.assert_not_called()
        self.assertEqual(result['rollout_processes_started'], 0)

    def test_worker_cannot_reopen_an_existing_attempt(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            (path/'training.json').write_text('historical bytes')
            with patch.object(training, '_load_locked_inputs') as load:
                with self.assertRaisesRegex(ValueError, 'resume is unsupported'):
                    training.run_experiment(path, PILOT, prepared_output=True)
                load.assert_not_called()
            self.assertEqual((path/'training.json').read_text(), 'historical bytes')

    def test_cli_wraps_entire_pilot_with_hard_wall_supervisor(self):
        with tempfile.TemporaryDirectory() as temp, \
             patch('dpdp_v3_supervisor.supervise', return_value=dict(valid_supervision=True,state='EXITED',exit_code=0)) as supervise, \
             patch.object(cli, 'run_experiment') as run:
            self.assertEqual(cli.main(['--protocol',str(PILOT),'--output',str(Path(temp)/'new')]),0)
            run.assert_not_called()
            command, output, timeout = supervise.call_args.args
            self.assertEqual(timeout, 3585)
            self.assertIn('--worker', command)
            self.assertEqual(output.name, 'trainer_supervision')

    def test_rollout_budget_and_wall_reject_before_start(self):
        with tempfile.TemporaryDirectory() as temp:
            evaluator = V3RolloutEvaluator(Path(temp)/'eval', dataset_root=temp,
                reference_path=PILOT, reference_sha256='test', reference_summary={}, reference_scores={},
                metadata_by_instance={2:{}}, split_protocol_sha256='test', source_manifest_sha256='test',
                gp_rng_seed=20261111, simulator_seed=0, runner_wall_seconds=120,
                supervisor_wall_seconds=125,total_wall_seconds=3600,cleanup_reserve_seconds=15,
                max_processes=0,started_monotonic=time.perf_counter())
            with patch.object(evaluator, '_context', return_value={}), \
                 patch('dpdp_v3_supervisor.supervise') as supervise:
                with self.assertRaises(RolloutBudgetExceeded):
                    evaluator.evaluate(Node('const',1),2)
                supervise.assert_not_called()
                evaluator.deadline = time.perf_counter()-1
                with self.assertRaises(RolloutBudgetExceeded):
                    evaluator.evaluate(Node('const',1),2)
                self.assertEqual(evaluator.process_count,0)


if __name__ == '__main__': unittest.main()
