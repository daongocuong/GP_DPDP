"""Regression and audit tests for GP candidate policy, feature evaluation, and sign-flip behavior."""
import unittest
from decimal import Decimal

from dpdp_gp import Node, TreeRanker, parse_node
from dpdp_insertion import FEATURE_UNITS


class PolicyAuditTests(unittest.TestCase):
    def test_c10_negative_distance_sign_flip_reproduction(self):
        """Reproduce the exact C10 instance 3 finding where negative delta_distance inverted tardiness sign."""
        # C10 Tree: (((delta_tardiness_seconds / delta_distance_km) - min_residual_capacity) + delta_tardiness_seconds)
        tree = Node('+', args=(
            Node('-', args=(
                Node('/', args=(Node('feature', 'delta_tardiness_seconds'), Node('feature', 'delta_distance_km'))),
                Node('feature', 'min_residual_capacity')
            )),
            Node('feature', 'delta_tardiness_seconds')
        ))
        ranker = TreeRanker(tree)

        # Candidate 1 (Chosen in C10 rollout): large tardiness, slightly negative distance
        cand_c10 = {
            'delta_distance_km': -0.1,
            'delta_tardiness_seconds': 5978.0,
            'delta_waiting_seconds': 0.0,
            'new_order_slack_seconds': 3901.0,
            'min_residual_capacity': 12.5,
        }
        score_c10 = ranker(cand_c10)
        # Expected: (5978 / -0.1) - 12.5 + 5978 = -59780 - 12.5 + 5978 = -53814.5
        self.assertAlmostEqual(score_c10, -53814.5, places=1)

        # Candidate 2 (Optimal / Delta J choice): zero tardiness, positive distance
        cand_opt = {
            'delta_distance_km': 1.2,
            'delta_tardiness_seconds': 0.0,
            'delta_waiting_seconds': 0.0,
            'new_order_slack_seconds': 8569.0,
            'min_residual_capacity': 13.0,
        }
        score_opt = ranker(cand_opt)
        # Expected: (0 / 1.2) - 13.0 + 0 = -13.0
        self.assertAlmostEqual(score_opt, -13.0, places=1)

        # Minimization selects the smaller score:
        # -53814.5 < -13.0, so the tree anomalously prefers the tardy candidate!
        self.assertLess(score_c10, score_opt)

    def test_delta_j_ranking_avoids_sign_flip(self):
        """Verify that Delta J metric key properly penalizes tardiness regardless of negative distance."""
        k_vehicles = 5
        def delta_j(feat):
            return feat['delta_distance_km'] / k_vehicles + (10000.0 / 3600.0) * feat['delta_tardiness_seconds']

        cand_c10 = {'delta_distance_km': -0.1, 'delta_tardiness_seconds': 5978.0}
        cand_opt = {'delta_distance_km': 1.2, 'delta_tardiness_seconds': 0.0}

        dj_c10 = delta_j(cand_c10)
        dj_opt = delta_j(cand_opt)

        self.assertGreater(dj_c10, dj_opt)
        self.assertAlmostEqual(dj_opt, 0.24, places=2)
        self.assertAlmostEqual(dj_c10, 16605.535, places=1)

    def test_tie_break_determinism(self):
        """Verify deterministic candidate tie-breaking order."""
        # Key is (score, vehicle, pickup_index, delivery_index)
        cand_a = (10.0, 'V_1', 1, 3)
        cand_b = (10.0, 'V_2', 0, 1)
        cand_c = (10.0, 'V_1', 1, 4)

        ranked = sorted([cand_c, cand_b, cand_a])
        self.assertEqual(ranked, [cand_a, cand_c, cand_b])


if __name__ == '__main__':
    unittest.main()
