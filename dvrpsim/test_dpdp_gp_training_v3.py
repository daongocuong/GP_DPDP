"""Focused protocol, cache, isolation and selection tests for GP v3."""
import json
from pathlib import Path
import tempfile
import unittest

from dpdp_contract import EXECUTION_CONTRACT
from dpdp_gp import Node
from dpdp_gp_rollout_v3 import (INVALID_FITNESS, assess_rollout, build_runner_command,
                               cache_key, verify_cache_provenance)
from dpdp_gp_training_v3 import (DEFAULT_PROTOCOL, SealedAccessTracker,
                                 aggregate_training, choose_candidate,
                                 evaluate_training_tree, require_experiment_ids,
                                 select_with_validation,
                                 validate_protocol_document, validate_reference_summary,
                                 validation_selection_key, write_generation)
from dpdp_vnsme_reference_v3 import FITNESS_VERSION


class FakeEvaluator:
    def __init__(self, records):
        self.lookup = records
        self.calls = []

    def evaluate(self, tree, instance):
        self.calls.append(instance)
        return dict(self.lookup[instance])


class GPTrainingV3Tests(unittest.TestCase):
    def test_development_protocol_is_read_and_frozen(self):
        protocol = json.loads(DEFAULT_PROTOCOL.read_text(encoding='utf-8'))
        validate_protocol_document(protocol)
        self.assertFalse(protocol['official_training_enabled'])
        self.assertEqual(protocol['smoke']['train_instances_subset'], [2, 3])
        self.assertEqual(protocol['smoke']['validation_instances'], [])
        self.assertNotEqual(protocol['split_protocol_sha256'],
                            protocol['source_manifest_sha256'])
        changed = dict(protocol, official_training_enabled=True)
        with self.assertRaisesRegex(ValueError, 'disable official'):
            validate_protocol_document(changed)
        changed = json.loads(json.dumps(protocol))
        changed['smoke']['train_instances_subset'] = [2, 7]
        with self.assertRaisesRegex(ValueError, 'settings differ'):
            validate_protocol_document(changed)

    def test_mixed_or_v2_reference_rejected(self):
        base = dict(valid=True, fitness_version=FITNESS_VERSION,
                    contract_version=EXECUTION_CONTRACT,
                    records=[dict(instance=i, role='validation' if i == 6 else 'train')
                             for i in (2, 3, 4, 5, 6)])
        scores = {i: 1. for i in (2, 3, 4, 5, 6)}
        self.assertTrue(validate_reference_summary(base, scores))
        with self.assertRaisesRegex(ValueError, 'v2 or invalid'):
            validate_reference_summary(dict(base, fitness_version='gp-fitness-vnsme-v2'), scores)
        with self.assertRaisesRegex(ValueError, 'ID set'):
            validate_reference_summary(dict(base, records=base['records'][:-1]), scores)

    def test_sealed_instance_allowlist_rejects_before_rollout(self):
        tracker = SealedAccessTracker()
        self.assertEqual(require_experiment_ids([2, 3], tracker, rollout=True), (2, 3))
        with self.assertRaises(PermissionError):
            require_experiment_ids([7], tracker, rollout=True)
        self.assertEqual(tracker.report()['rollout_ids'], [2, 3])
        self.assertEqual(tracker.report()['rejected_ids'], [7])
        self.assertFalse(tracker.report()['os_level_file_open_tracing'])

    def test_fitness_is_equal_weight_ratio_and_minimized(self):
        records = [dict(instance=2, valid=True, benchmark_J='10'),
                   dict(instance=3, valid=True, benchmark_J='12')]
        result = aggregate_training(records, {2: 5, 3: 3}, [2, 3])
        self.assertTrue(result['valid'])
        self.assertEqual(result['ratios'], [2.0, 4.0])
        self.assertEqual(result['fitness'], 3.0)
        self.assertEqual(result['optimization'], 'minimize')
        invalid = aggregate_training([dict(instance=2, valid=True, benchmark_J='1'),
                                      dict(instance=3, valid=False, benchmark_J='999')],
                                     {2: 1, 3: 1}, [2, 3])
        self.assertFalse(invalid['valid'])
        self.assertIsNone(invalid['ratios'][1])
        self.assertEqual(invalid['fitness'], INVALID_FITNESS)

    def test_training_population_never_receives_validation_ids(self):
        tree = Node('const', 1)
        fake = FakeEvaluator({2: dict(instance=2, valid=True, benchmark_J='10'),
                              3: dict(instance=3, valid=True, benchmark_J='20'),
                              6: dict(instance=6, valid=True, benchmark_J='1')})
        rows, aggregate = evaluate_training_tree(tree, [2, 3], fake,
                                                  {2: 10, 3: 10, 6: 10})
        self.assertEqual(fake.calls, [2, 3])
        self.assertTrue(aggregate['valid'])
        self.assertEqual([r['instance'] for r in rows], [2, 3])

    def test_validation_selection_priority_and_determinism(self):
        small = Node('const', 1)
        large = Node('+', args=(Node('const', 1), Node('const', 2)))
        key_small = validation_selection_key(dict(valid=True, benchmark_J='90'), 100, .8, small)
        key_large = validation_selection_key(dict(valid=True, benchmark_J='90'), 100, .8, large)
        self.assertLess(key_small, key_large)
        better_validation = validation_selection_key(dict(valid=True, benchmark_J='80'), 100, .99, large)
        self.assertLess(better_validation, key_small)
        candidates = [dict(name='large', selection_key=key_large),
                      dict(name='small', selection_key=key_small)]
        self.assertEqual(choose_candidate(candidates)['name'], 'small')
        self.assertEqual(choose_candidate(list(reversed(candidates)))['name'], 'small')
        self.assertIsNone(choose_candidate([dict(selection_key=None)]))

    def test_validation_is_consulted_only_after_full_training_fitness(self):
        tree = Node('const', 1)
        fake = FakeEvaluator({2: dict(instance=2, valid=True, benchmark_J='10'),
                              3: dict(instance=3, valid=True, benchmark_J='20'),
                              6: dict(instance=6, valid=True, benchmark_J='15')})
        selected, candidates = select_with_validation(
            [tree], [2, 3], 6, fake, {2: 10, 3: 10, 6: 10})
        self.assertEqual(fake.calls, [2, 3, 6])
        self.assertIsNotNone(selected)
        self.assertEqual(selected['selection_key'][0], 1.5)
        self.assertTrue(candidates[0]['train']['valid'])

    def test_cache_key_and_entry_reject_context_mismatch_or_invalid_score(self):
        tree = Node('const', 2)
        context = dict(namespace='gp-fitness-vnsme-v3', contract=EXECUTION_CONTRACT,
                       instance=2, source='abc', seed=0, timeout=20)
        key = cache_key(tree, context)
        entry = dict(cache_key=key, context=context, valid=True, benchmark_J='12')
        self.assertTrue(verify_cache_provenance(entry, key, context))
        with self.assertRaisesRegex(ValueError, 'provenance'):
            verify_cache_provenance(entry, key, dict(context, source='changed'))
        with self.assertRaisesRegex(ValueError, 'invalid entry'):
            verify_cache_provenance(dict(entry, valid=False), key, context)
        self.assertNotEqual(key, cache_key(tree, dict(context, simulator_seed=1)))

    def test_runner_command_pins_v3_contract_explicitly(self):
        command = build_runner_command('tree.json',
            dict(input_paths=dict(orders='data/instance_2/orders.csv',
                                  factories='data/factory_info.csv')),
            'run', 0, 20)
        self.assertIn('--contract-version', command)
        self.assertEqual(command[command.index('--contract-version')+1], EXECUTION_CONTRACT)
        self.assertEqual(command[command.index('--policy')+1], 'gp')

    def test_v2_contract_or_unverified_score_cannot_be_assessed(self):
        with self.assertRaisesRegex(ValueError, 'policy/contract mismatch'):
            assess_rollout(dict(total_score='4'),
                           dict(policy='gp', contract_version='dpdp-accepted-route-v2'),
                           Node('const', 1), 'missing-tree.json', {})

    def test_generation_snapshot_is_written_as_a_distinct_artifact(self):
        with tempfile.TemporaryDirectory() as temp:
            record = dict(generation=0, status='running', valid_tree_count=1,
                          fitness_scope='development_subset_not_official')
            path = write_generation(temp, record)
            self.assertEqual(json.loads(path.read_text(encoding='utf-8')), record)
            updated = dict(record, rng_state_after_generation=[1, 2, 3])
            write_generation(temp, updated)
            self.assertEqual(json.loads(path.read_text(encoding='utf-8')),
                             updated)


if __name__ == '__main__':
    unittest.main()
