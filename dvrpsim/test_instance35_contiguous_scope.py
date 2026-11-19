import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from instance35_gp_evolution import ROOT, prepare_contiguous


class ContiguousScopeTests(unittest.TestCase):
    def test_locked_fresh_window_is_contiguous_and_meets_order_counts(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as temp:
            experiment = Path(temp)/'scope'
            config, protocol = prepare_contiguous(experiment)
            saved_config = json.loads((experiment/'experiment_config.json').read_text())
            saved_protocol = json.loads((experiment/'training_protocol.json').read_text())

            self.assertEqual(config['partitions']['train']['original_orders'], 118)
            self.assertEqual(config['partitions']['validation']['original_orders'], 22)
            self.assertEqual(config['partitions']['test']['original_orders'], 27)
            temporal = saved_config['temporal_protocol']
            self.assertEqual(temporal['train_ratio'], '0.60')
            self.assertEqual(temporal['validation_ratio'], '0.20')
            self.assertEqual(temporal['test_ratio'], '0.20')
            boundaries = temporal['boundary_seconds']
            self.assertEqual(Decimal(boundaries['window_start_inclusive']), Decimal('15587.64'))
            self.assertEqual(Decimal(boundaries['train_end_exclusive']), Decimal('26208.444'))
            self.assertEqual(Decimal(boundaries['validation_end_exclusive']), Decimal('29748.712'))
            self.assertEqual(Decimal(boundaries['window_end_exclusive']), Decimal('33288.98'))
            self.assertEqual(temporal['partitions_are_independent_rollouts'], True)
            self.assertEqual(temporal['reset_fleet_each_partition'], True)
            self.assertEqual(temporal['carry_over_orders'], False)
            self.assertEqual(saved_protocol['gp']['population_size'], 4)
            self.assertEqual(saved_protocol['gp']['generation_count'], 3)
            self.assertEqual(saved_protocol['gp']['validation_candidate_count'], 3)
            self.assertIsNone(saved_protocol['prior_rollout_reuse'])
            self.assertEqual(saved_protocol['prior_failed_candidates'], {})
            self.assertTrue(saved_protocol['protocol_locked_before_new_rollouts'])


if __name__ == '__main__':
    unittest.main()
