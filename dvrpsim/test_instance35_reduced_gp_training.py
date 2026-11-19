import random
import unittest
from decimal import Decimal
import time

from dpdp_gp import Limits, Node, breed, initial_population, validate_tree
from instance35_reduced_gp_training import (require_rollout_budget, result_complete,
                                            validation_rank_key)


class ReducedGPTrainingTests(unittest.TestCase):
    def test_tiny_generation_uses_existing_gp_evolution_primitives(self):
        rng = random.Random(20261118)
        generation0 = initial_population(rng, 2)
        evaluated = [(Decimal('12.5'), generation0[0]),
                     (Decimal('10.0'), generation0[1])]
        generation1 = breed(rng, evaluated, 2, tournament=2,
                            crossover_rate=.8, mutation_rate=.3, elitism=1,
                            limits=Limits())
        self.assertEqual(len(generation1), 2)
        self.assertEqual(generation1[0], generation0[1])
        for tree in generation1:
            validate_tree(tree, Limits())

    def test_validation_j_is_primary_selection_key(self):
        left = Node('feature', 'delta_distance_km')
        right = Node('+', args=(Node('feature', 'delta_distance_km'),
                                Node('feature', 'delta_tardiness_seconds')))
        a = dict(tree=left, validation_J='9.25', training_J='100')
        b = dict(tree=right, validation_J='9.3', training_J='1')
        self.assertIs(min((a, b), key=validation_rank_key), a)
        same_j = [
            dict(tree=left, validation_J='4.0', training_J='8'),
            dict(tree=right, validation_J='4.0', training_J='7'),
        ]
        self.assertIs(min(same_j, key=validation_rank_key), same_j[1])

    def test_only_clean_supervised_results_with_j_are_reusable(self):
        complete = dict(status='COMPLETED', valid=True, J='1.25', partial=False,
            valid_supervision=True, supervisor_state='EXITED', supervisor_exit_code=0,
            remaining_job_processes=[])
        self.assertTrue(result_complete(complete))
        for patch in (
            {'J': None}, {'partial': True}, {'valid_supervision': False},
            {'supervisor_exit_code': 1}, {'remaining_job_processes': [99]},
            {'status': 'TIMEOUT'},
        ):
            with self.subTest(patch=patch):
                self.assertFalse(result_complete({**complete, **patch}))

    def test_task_deadline_reserves_a_full_rollout_before_start(self):
        self.assertGreaterEqual(require_rollout_budget(time.time()+3600, 1800), 1800)
        with self.assertRaises(RuntimeError):
            require_rollout_budget(time.time()+30, 1800)


if __name__ == '__main__':
    unittest.main()
