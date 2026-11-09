import ast
from collections import Counter
import contextlib
import copy
import io
import json
import math
from pathlib import Path
import random
import tempfile
import unittest
from unittest.mock import patch

from dpdp_gp import (Node, Limits, TreeError, NumericTreeError, TreeRanker, FEATURES,
                     validate_tree, canonical, save_tree, load_tree, initial_population,
                     breed, crossover, mutate)
from dpdp_gp_fitness import (INVALID_FITNESS, ROOT, RolloutEvaluator, cache_key,
                             assess_result, discover_instances)
from dpdp_insertion import InsertionPolicy
from test_dpdp_insertion import make, order


def features(**values):
    return {**dict.fromkeys(FEATURES, 0.0), **values}


class TreeTests(unittest.TestCase):
    def test_protected_division_boundary(self):
        t = Node('/', args=(Node('feature', FEATURES[0]), Node('feature', FEATURES[1])))
        ranker = TreeRanker(t)
        for denominator in (0, 1e-10, -1e-9, 1e-9):
            self.assertEqual(ranker(features(delta_distance_km=7, delta_tardiness_seconds=denominator)), 7)
        self.assertEqual(ranker(features(delta_distance_km=7, delta_tardiness_seconds=2)), 3.5)
        self.assertEqual(ranker.stats['protected_divisions'], 4)

    def test_large_finite_inputs_saturate_without_overflow(self):
        t = Node('*', args=(Node('feature', FEATURES[0]), Node('feature', FEATURES[1])))
        ranker = TreeRanker(t)
        self.assertEqual(ranker(features(delta_distance_km=1e308, delta_tardiness_seconds=1e308)), 1e12)
        self.assertEqual(ranker.stats['saturations'], 3)

    def test_nan_inf_and_conversion_fail_invalidate_ranking(self):
        ranker = TreeRanker(Node('feature', FEATURES[0]))
        for value in (math.nan, math.inf, -math.inf, 10**1000):
            with self.subTest(value=str(value)[:30]), self.assertRaises(NumericTreeError):
                ranker(features(delta_distance_km=value))
        self.assertEqual(ranker.stats['numeric_errors'], 4)

    def test_forbidden_features_operators_and_constants(self):
        for tree in (Node('feature', 'instance_id'), Node('feature', 'vehicle_num'), Node('eval'),
                     Node('const', math.inf), Node('const', 10**1000)):
            with self.assertRaises(TreeError):
                validate_tree(tree)
        with self.assertRaises(NumericTreeError):
            TreeRanker(Node('const', 0))({**features(), 'instance_id': 17})

    def test_tree_hard_limits(self):
        tree = Node('const', 1)
        for _ in range(4):
            tree = Node('+', args=(tree, Node('const', 1)))
        self.assertEqual(validate_tree(tree), (9, 4))
        with self.assertRaises(TreeError):
            validate_tree(Node('+', args=(tree, Node('const', 1))))
        with self.assertRaises(TreeError):
            validate_tree(tree, Limits(max_depth=4, max_nodes=7))

    def test_save_load_and_tamper_detection(self):
        tree = Node('+', args=(Node('feature', FEATURES[0]), Node('const', .25)))
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/'tree.json'
            save_tree(path, tree, training={'seed': 3})
            recovered, metadata = load_tree(path)
            self.assertEqual(tree, recovered)
            self.assertEqual(TreeRanker(recovered)(features(delta_distance_km=2)), 2.25)
            self.assertEqual(metadata['training']['seed'], 3)
            metadata['tree'] = {'feature': FEATURES[0]}
            path.write_text(json.dumps(metadata), encoding='utf-8')
            with self.assertRaises(TreeError):
                load_tree(path)

    def test_seeded_population_and_breeding(self):
        outputs = []
        for _ in range(2):
            rng = random.Random(123)
            pop = initial_population(rng)
            outputs.append(([canonical(t) for t in pop], [canonical(t) for t in breed(rng, list(enumerate(pop)), 6)]))
        self.assertEqual(outputs[0], outputs[1])
        rng = random.Random(123)
        pop = initial_population(rng)
        offspring = breed(rng, list(enumerate(pop)), 6)
        self.assertEqual(offspring[0], pop[0])

    def test_variation_always_respects_limits(self):
        rng = random.Random(19)
        a, b = initial_population(rng)[:2]
        for _ in range(100):
            a = mutate(rng, crossover(rng, a, b))
            b = mutate(rng, b)
            for tree in (a, b):
                size, depth = validate_tree(tree)
                self.assertLessEqual(size, 31)
                self.assertLessEqual(depth, 4)


class IntegrationTests(unittest.TestCase):
    def test_gp_changes_only_ranking_and_sees_same_valid_candidates(self):
        import dpdp_insertion
        real = dpdp_insertion.candidates
        outputs, lists = [], []
        for scorer in (TreeRanker(Node('feature', 'delta_distance_km')), TreeRanker(Node('const', 0))):
            m = make(2)
            order(m)
            v1, v2 = list(m.vehicles)
            v2.current_visit.location = m.get_location_by_id('H2')
            m.private_data['distances']['H1', 'P'] = 100
            m.private_data['distances']['H2', 'P'] = 1
            seen = []
            def traced(*args, **kwargs):
                for c in real(*args, **kwargs):
                    seen.append((c.tie_key, c.features))
                    yield c
            with patch.object(dpdp_insertion, 'candidates', traced):
                policy = InsertionPolicy(scorer)
                policy.decide(m)
            lists.append(seen)
            outputs.append(policy.decisions[0]['chosen'][0]['vehicle'])
        self.assertEqual(lists[0], lists[1])
        self.assertEqual(outputs, ['V_2', 'V_1'])
        self.assertEqual(scorer.stats['evaluations'], len(lists[1]))

    def test_shared_generator_guard_and_forecast_unchanged(self):
        before = ast.parse((ROOT/'gp_evidence/dpdp_insertion_before.py.txt').read_text(encoding='utf-8'))
        after = ast.parse((ROOT/'dpdp_insertion.py').read_text(encoding='utf-8'))
        wanted = {'Snapshot', 'split_observed_orders', 'candidates', 'extract_features', 'min_residual'}
        b = {n.name: ast.dump(n) for n in before.body if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name in wanted}
        a = {n.name: ast.dump(n) for n in after.body if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name in wanted}
        self.assertEqual(b, a)
        initial = json.loads((ROOT/'gp_evidence/initial_state.json').read_text(encoding='utf-8'))
        from dpdp_gp_fitness import digest
        for p in ('dpdp_feasibility.py', 'dpdp_schedule.py', 'verify_dpdp_score.py'):
            self.assertEqual(digest(ROOT/p), initial['sha256'][p])

    def test_saved_tree_runner_uses_independent_final_score(self):
        import run_dpdp_insertion
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            tree = Node('+', args=(Node('feature', FEATURES[0]), Node('feature', FEATURES[1])))
            save_tree(root/'tree.json', tree)
            argv = ['run', '--policy', 'gp', '--tree', str(root/'tree.json'), '--output', str(root/'run')]
            with patch('sys.argv', argv), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(run_dpdp_insertion.main(), 0)
            result = json.loads((root/'run/result.json').read_text(encoding='utf-8'))
            self.assertTrue(result['valid'])
            self.assertGreater(result['gp_evaluation']['evaluations'], 0)
            from verify_dpdp_score import verify
            from dpdp_gp_fitness import DATA
            independent = verify(root/'run/simulation.log', DATA/'instance_1/50_1.csv',
                                 DATA/'instance_1/vehicle_info_5.csv', DATA/'route_info.csv')
            self.assertEqual(assess_result(result, independent), float(independent['total_score']))
            result['score']['total_score'] = '-9999'  # a ranking is never a fitness oracle
            with self.assertRaises(ValueError):
                assess_result(result, independent)

    def test_invalid_and_timeout_have_penalty_not_benchmark_score(self):
        import subprocess
        with tempfile.TemporaryDirectory() as d:
            evaluator = RolloutEvaluator(d, 1)
            invalid = evaluator.evaluate(Node('feature', 'future_orders'))
            self.assertEqual(invalid['fitness'], INVALID_FITNESS)
            self.assertIsNone(invalid['benchmark_J'])
            self.assertFalse(invalid['valid'])
            with patch('dpdp_gp_fitness.subprocess.run', side_effect=subprocess.TimeoutExpired('test', 10)):
                timed = evaluator.evaluate(Node('const', 1))
            self.assertEqual(timed['status'], 'timeout')
            self.assertEqual(timed['fitness'], INVALID_FITNESS)
            self.assertIsNone(timed['benchmark_J'])
        with self.assertRaises(ValueError):
            assess_result({'valid': False}, None)

    def test_cache_key_binds_all_context_and_tree(self):
        tree = Node('const', 1)
        context = dict(instance=1, seed=0, config={'wall': 10, 'dispatch': 600},
                       code={'a.py': 'hash'}, data={'orders': 'digest'}, interpreter='3.14')
        base = cache_key(tree, context)
        for key in context:
            other = copy.deepcopy(context)
            other[key] = 'changed'
            self.assertNotEqual(base, cache_key(tree, other))
        self.assertNotEqual(base, cache_key(Node('const', 2), context))
        self.assertEqual(base, cache_key(tree, copy.deepcopy(context)))

    def test_completed_rollout_cache_roundtrip_and_fresh_repeat(self):
        tree = Node('+', args=(Node('feature', FEATURES[0]), Node('feature', FEATURES[1])))
        with tempfile.TemporaryDirectory() as d:
            evaluator = RolloutEvaluator(d, 4)
            original = evaluator.evaluate(tree)
            self.assertTrue(original['valid'], original.get('error'))
            self.assertIsInstance(original['benchmark_J'], str)
            cached = evaluator.evaluate(tree)
            self.assertTrue(cached['cache_hit'])
            self.assertEqual(original['fitness'], cached['fitness'])
            repeated = evaluator.evaluate(tree, force=True)
            self.assertTrue(repeated['valid'])
            self.assertEqual(original['log_sha256'], repeated['log_sha256'])

    def test_inventory_is_real_not_fictitious_split(self):
        data = discover_instances()
        self.assertEqual(set(data), {1, 17})
        self.assertEqual((data[1]['items'], data[17]['items']), (95, 592))


if __name__ == '__main__':
    unittest.main()
