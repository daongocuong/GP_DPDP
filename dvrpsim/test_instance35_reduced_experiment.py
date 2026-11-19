import csv
import unittest
from decimal import Decimal
from unittest.mock import patch

import instance35_reduced_experiment as experiment


class ReducedInstance35ExperimentTests(unittest.TestCase):
    def test_temporal_partition_keeps_release_ties_together(self):
        rows = [
            {'order_id': 'a', 'creation_time': '00:00:00'},
            {'order_id': 'b', 'creation_time': '00:01:00'},
            {'order_id': 'c', 'creation_time': '00:01:00'},
            {'order_id': 'd', 'creation_time': '00:01:01'},
            {'order_id': 'e', 'creation_time': '00:01:20'},
            {'order_id': 'f', 'creation_time': '00:01:40'},
        ]
        with patch.object(experiment, 'WINDOW_FRACTION', Decimal('1')):
            partitions, bounds = experiment._partition_rows(rows)
        self.assertEqual([r['order_id'] for r in partitions['train']], ['a'])
        self.assertEqual([r['order_id'] for r in partitions['validation']], ['b', 'c', 'd'])
        self.assertEqual([r['order_id'] for r in partitions['test']], ['e', 'f'])
        self.assertEqual(bounds['train_validation_boundary'], Decimal('60.0'))
        self.assertEqual(bounds['validation_test_boundary'], Decimal('80.0'))

    def test_completion_requires_clean_supervision_contract_and_matching_audit(self):
        outcome = dict(state='EXITED', exit_code=0, valid_supervision=True,
                       remaining_job_processes=[])
        result = dict(status='COMPLETED', valid=True, contract_complete=True, decision_count=1,
                      score={'total_score': '123.5'})
        audit = {'total_score': Decimal('123.5')}
        trace = [dict(event='START', decision_index=1),
                 dict(event='END', decision_index=1, status='completed')]
        self.assertTrue(experiment._valid_completion(outcome, result, audit, trace))
        for change in (
            ({'remaining_job_processes': [123]}, result, audit, trace),
            (outcome, {**result, 'contract_complete': False}, audit, trace),
            (outcome, {**result, 'score': None}, audit, trace),
            (outcome, result, {'total_score': Decimal('123.6')}, trace),
            (outcome, result, None, trace),
            (outcome, result, audit, [*trace, dict(event='TIMEOUT', decision_index=2)]),
            (outcome, result, audit, [trace[0]]),
        ):
            with self.subTest(change=change):
                self.assertFalse(experiment._valid_completion(*change))

    def test_partial_or_invalid_result_cannot_become_a_scored_completion(self):
        outcome = dict(state='TIMEOUT', exit_code=1, valid_supervision=False,
                       remaining_job_processes=[])
        partial = dict(status='SMOKE_COMPLETED', valid=False, contract_complete=False,
                       partial=True, score=None, decision_count=0)
        self.assertFalse(experiment._valid_completion(outcome, partial, None, []))

    def test_smaller_runtime_scope_has_sufficient_temporal_partitions(self):
        with experiment.SOURCE.open(encoding='utf-8-sig', newline='') as handle:
            rows = list(csv.DictReader(handle))
        parts, bounds = experiment._partition_rows(rows, Decimal('0.18'))
        self.assertEqual([len(parts[name]) for name in ('train', 'validation', 'test')],
                         [69, 34, 48])
        self.assertEqual(sum(map(len, parts.values())), 151)
        self.assertEqual(bounds['source_start'], Decimal(45))
        self.assertEqual(bounds['window_end'], Decimal('15587.64'))
        self.assertEqual(bounds['train_validation_boundary'], Decimal('9370.5840'))
        self.assertEqual(bounds['validation_test_boundary'], Decimal('12479.1120'))

    def test_experiment_uses_independent_full_rollout_limits(self):
        self.assertEqual(experiment.SLOT_SECONDS, 600)
        self.assertEqual(experiment.SUPERVISOR_WALL_SECONDS, 1800)
        self.assertEqual(experiment.RUNNER_WALL_GUARD_SECONDS, 1860)
        self.assertEqual(experiment.DECISION_HARD_SECONDS, 60)
        self.assertEqual(experiment.VNSME_SEARCH_BUDGET_SECONDS, 50)
        self.assertEqual(experiment.VNSME_SUBPROCESS_HARD_SECONDS, 59)


if __name__ == '__main__':
    unittest.main()
