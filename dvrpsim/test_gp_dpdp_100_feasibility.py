import json
from decimal import Decimal
from pathlib import Path
import random
import tempfile
import unittest

from dpdp_gp import FEATURES, Limits, Node, TreeRanker, breed, validate_tree
import gp_dpdp_100_feasibility as experiment


class GP100FeasibilityTests(unittest.TestCase):
    def test_seeded_g0_is_repeatable_and_respects_official_depth_range(self):
        _, first, first_rows = experiment.initial_population()
        _, second, second_rows = experiment.initial_population()
        self.assertEqual([experiment.canonical(t) for t in first],
                         [experiment.canonical(t) for t in second])
        self.assertEqual(first_rows, second_rows)
        self.assertEqual(len(first), 10)
        for tree in first:
            nodes, depth = validate_tree(tree, experiment.LIMITS)
            self.assertGreaterEqual(depth, 2)
            self.assertLessEqual(depth, 4)
            self.assertLessEqual(nodes, 63)
        self.assertEqual(len(experiment.first_unique_members(first)), 4)

    def test_breed_honors_passed_depth_five_limit(self):
        def full(depth):
            if depth == 0:
                return Node('const', 1)
            return Node('+', args=(full(depth-1), full(depth-1)))

        depth_five = full(5)
        self.assertEqual(validate_tree(depth_five, Limits(5, 63)), (63, 5))
        next_population = breed(random.Random(7),
            [(Decimal('1'), depth_five), (Decimal('2'), Node('feature', FEATURES[0]))],
            3, tournament=3, crossover_rate=0, mutation_rate=0, elitism=1,
            limits=Limits(5, 63))
        self.assertEqual(len(next_population), 3)
        self.assertEqual(next_population[0], depth_five)
        self.assertTrue(all(validate_tree(tree, Limits(5, 63))[1] <= 5
                            for tree in next_population))

    def test_timeout_without_runner_result_summarizes_with_null_j(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root/'temporal_split_manifest.json').write_text(json.dumps({
                'partitions': {'train': {'original_orders': 1, 'items': 1}}}),
                encoding='utf-8')
            runner = root/'rollouts'/'train'/'tree'/'runner'
            runner.mkdir(parents=True)
            tree = Node('feature', FEATURES[0])
            events = [
                {'event': 'START', 'decision_index': 1, 'simulation_seconds': 0},
                {'event': 'TIMEOUT', 'decision_index': 1,
                 'decision_elapsed_seconds': 600.1, 'timeout_type': 'decision_hard_timeout',
                 'candidate_count': 1000},
            ]
            result = experiment.summarize_stage(tree, 'gp', 'train', runner,
                {'state': 'DECISION_TIMEOUT', 'exit_code': 1,
                 'valid_supervision': False, 'remaining_job_processes': [],
                 'elapsed_seconds': 601, 'peak_job_memory_bytes': 4096},
                None, None, None, events, 'protocol-hash', 'timeout-test', 601.5)
            self.assertEqual(result['status'], 'TIMEOUT')
            self.assertIsNone(result['J'])
            self.assertIsNone(result['candidate_evaluations'])
            self.assertEqual(result['decision_runtime']['attempts'], 1)
            self.assertEqual(result['decision_runtime']['maximum'], 600.1)
            self.assertIsNone(result['completed_orders'])

    def test_fixed_tree_scoring_is_deterministic_and_feature_schema_is_locked(self):
        tree = Node('+', args=(Node('feature', FEATURES[0]),
                               Node('feature', FEATURES[1])))
        scorer = TreeRanker(tree)
        candidate = {name: float(index+1) for index, name in enumerate(FEATURES)}
        first = scorer(candidate)
        second = scorer(candidate)
        self.assertEqual(first, second)
        self.assertEqual(scorer.stats['evaluations'], 2)
        self.assertEqual(tuple(FEATURES), tuple(experiment.FEATURES))

    def test_cache_rejects_a_different_protocol_hash(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'cache'/'train.json'
            path.parent.mkdir()
            path.write_text(json.dumps({'protocol_sha256': 'old', 'entries': {}}),
                            encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'protocol mismatch'):
                experiment._load_cache(Path(temp), 'train', 'new')


if __name__ == '__main__':
    unittest.main()
