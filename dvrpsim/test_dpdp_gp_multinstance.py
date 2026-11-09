import tempfile
import unittest
from pathlib import Path

from dpdp_gp import Node, canonical
from dpdp_gp_fitness import cache_key
from train_dpdp_gp_multinstance import (aggregate_training, load_locked, require_experiment_instance,
                                        validation_key, DEFAULT_PROTOCOL, DEFAULT_DATASET)


class MultiInstanceProtocolTests(unittest.TestCase):
    def test_reads_locked_train_validation_and_never_authorizes_final_test(self):
        _, _, _, _, train, validation = load_locked(DEFAULT_PROTOCOL, DEFAULT_DATASET)
        self.assertEqual(train, (2, 3, 4, 5))
        self.assertEqual(validation, (6,))
        for instance in train + validation:
            self.assertEqual(require_experiment_instance(instance, train, validation), instance)
        for instance in (1, 7, 8, 15, 16, 17):
            with self.assertRaises(ValueError):
                require_experiment_instance(instance, train, validation)

    def test_equal_weight_ratio_aggregation(self):
        baselines = {2: 10, 3: 100, 4: 20, 5: 200}
        records = [dict(instance=2, valid=True, benchmark_J='20'),
                   dict(instance=3, valid=True, benchmark_J='50'),
                   dict(instance=4, valid=True, benchmark_J='20'),
                   dict(instance=5, valid=True, benchmark_J='100')]
        result = aggregate_training(records, baselines)
        self.assertTrue(result['valid'])
        self.assertEqual(result['ratios'], [2.0, .5, 1.0, .5])
        self.assertEqual(result['fitness'], 1.0)

    def test_timeout_on_one_instance_penalizes_whole_tree(self):
        records = [dict(instance=i, valid=True, benchmark_J='100') for i in (2, 3, 4)]
        records.append(dict(instance=5, valid=False, benchmark_J=None, status='timeout'))
        result = aggregate_training(records, {i:100 for i in (2,3,4,5)})
        self.assertFalse(result['valid'])
        self.assertEqual(result['fitness'], 1e15)
        self.assertEqual(result['invalid_instances'], [5])
        self.assertIsNone(result['ratios'][-1])

    def test_invalid_baseline_denominator_is_rejected(self):
        with self.assertRaises(ValueError):
            aggregate_training([dict(instance=2, valid=True, benchmark_J='1')], {2: 0})

    def test_cache_context_distinguishes_instance_and_data_path(self):
        tree = Node('const', 1)
        base = dict(instance=2, paths={'orders':'a'}, protocol='p', seed=0, timeout=30)
        key2 = cache_key(tree, base)
        self.assertNotEqual(key2, cache_key(tree, {**base, 'instance':3}))
        self.assertNotEqual(key2, cache_key(tree, {**base, 'paths':{'orders':'b'}}))

    def test_validation_selection_priority_and_tiebreaks(self):
        small = Node('const', 1)
        large = Node('+', args=(Node('const', 1), Node('const', 2)))
        a = validation_key(dict(valid=True, benchmark_J='90', baseline_J='100'), .8, large)
        b = validation_key(dict(valid=True, benchmark_J='90', baseline_J='100'), .7, small)
        self.assertLess(b, a)  # train fitness first, before size
        c = validation_key(dict(valid=True, benchmark_J='90', baseline_J='100'), .8, small)
        self.assertLess(c, a)  # fewer nodes next
        invalid = validation_key(dict(valid=False, benchmark_J=None, baseline_J='100'), .1, small)
        self.assertIsNone(invalid)


if __name__ == '__main__':
    unittest.main()
