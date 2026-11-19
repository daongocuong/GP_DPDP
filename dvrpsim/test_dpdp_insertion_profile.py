import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from dpdp_insertion import Candidate, Group, InsertionPolicy, Snapshot
import dpdp_insertion as insertion_module
from run_dpdp_insertion import insertion_profile_payload
from test_dpdp_insertion import make, order, ranked_policy


class InsertionProfileTests(unittest.TestCase):
    def test_trace_payload_labels_overlapping_validator_timers(self):
        payload = insertion_profile_payload(dict(
            feasibility_validator_total_seconds=.7,
            feasibility_initial_vehicle_scan_seconds=.1,
            feasibility_vehicle_route_scan_seconds=.4,
            feasibility_global_checks_seconds=.2,
            feasibility_capacity_check_seconds=.08,
            feasibility_lifo_check_seconds=.03,
            feasibility_pickup_delivery_seconds=.25))
        timing = payload['feasibility_timing']
        self.assertEqual(set(timing['top_level_phase_seconds']), {
            'initial_vehicle_scan', 'vehicle_route_scan', 'global_checks'})
        self.assertAlmostEqual(sum(timing['top_level_phase_seconds'].values()),
                               timing['validator_total_seconds'])
        self.assertEqual(set(timing['nested_check_seconds']), {
            'capacity', 'lifo', 'pickup_delivery_operations_inclusive'})
        self.assertIn('overlaps validator_total_seconds', timing['nested_timer_semantics'])
        self.assertIn('Do not add nested timers', timing['nested_timer_semantics'])

    def test_disabled_feasibility_profile_is_explicit_and_has_no_fake_zero_timers(self):
        payload = insertion_profile_payload(dict(
            feasibility_profile_enabled=False,
            examined=10,
            feasible=4))
        self.assertIs(payload['feasibility_profile_enabled'], False)
        self.assertNotIn('feasibility_timing', payload)

    def test_decision_keeps_candidate_order_and_records_counts_and_times(self):
        route1 = SimpleNamespace(current=None, future=(SimpleNamespace(factory='P', pickups=('i',), deliveries=()),))
        route2 = SimpleNamespace(current=None, future=(SimpleNamespace(factory='Q', pickups=('i',), deliveries=()),))
        group = Group('o', 0, ('i',), 'P', 'D', 10, 0)
        snapshot = SimpleNamespace(
            now=0, plans={'v': SimpleNamespace(current=None, future=())},
            objects={'i': SimpleNamespace(is_accepted=True)}, items={'i': object()},
            fleet={'v': SimpleNamespace(capacity=10)}, delivered=set(),
            admitted=lambda plans: set(), check=lambda plans, admitted, profile=None: None,
            metrics=lambda plans, admitted: {'distance': 0})
        candidates = [Candidate('v', 0, 1, {'v': route1}, {'rank': 2}, {}),
                      Candidate('v', 1, 2, {'v': route2}, {'rank': 1}, {})]

        def enumerate_candidates(snap, plans, item_group, admitted, before, stats,
                                 profile_feasibility=True):
            for candidate in candidates:
                stats['examined'] += 1
                stats['feasible'] = stats.get('feasible', 0) + 1
                yield candidate

        policy = InsertionPolicy(lambda features, fleet_size: features['rank'])
        with patch('dpdp_insertion.Snapshot.observe', return_value=snapshot), \
             patch('dpdp_insertion.split_observed_orders', return_value=[group]), \
             patch('dpdp_insertion.candidates', side_effect=enumerate_candidates):
            decision = policy.decide(SimpleNamespace(log=SimpleNamespace(info=lambda message: None)))

        self.assertEqual(decision['vehicles']['v']['next_visits'][0]['location'], 'Q')
        profile = policy.decisions[0]
        self.assertEqual((profile['examined'], profile['feasible'], profile['scored']), (2, 2, 2))
        self.assertEqual((profile['groups_total'], profile['groups_processed']), (1, 1))
        self.assertGreaterEqual(profile['gp_scoring_seconds'], 0)
        self.assertGreaterEqual(profile['wall_seconds'], profile['gp_scoring_seconds'])

    def test_feasibility_timing_does_not_change_candidate_order_or_routing_output(self):
        def run(with_validator_profile):
            model = make(2)
            order(model, 'a', pickup='P', delivery='Q')
            order(model, 'b', pickup='R', delivery='S')
            policy = ranked_policy()
            visited = []
            checked = []
            real_check = Snapshot.check
            real_candidates = insertion_module.candidates

            def check(snapshot, plans, admitted, profile=None):
                checked.append(tuple((vehicle, tuple((visit.factory, visit.pickups, visit.deliveries)
                    for visit in plan.future)) for vehicle, plan in plans.items()))
                if with_validator_profile:
                    return real_check(snapshot, plans, admitted, profile=profile)
                return real_check(snapshot, plans, admitted)

            def candidates(*args, **kwargs):
                for candidate in real_candidates(*args, **kwargs):
                    visited.append(candidate.tie_key)
                    yield candidate

            with patch.object(Snapshot, 'check', check), \
                 patch.object(insertion_module, 'candidates', candidates):
                decision = policy.decide(model)
            stats = policy.decisions[0]
            return (decision, visited, checked, stats['chosen'],
                    (stats['examined'], stats['feasible'], stats['rejected']))

        profiled = run(True)
        unprofiled = run(False)
        self.assertEqual(profiled, unprofiled)

    def test_metrics_profile_separates_schedule_prediction(self):
        snapshot = Snapshot(now=0, objects={}, items={}, demands={}, delivered=set(), fleet={},
                            plans={}, view=SimpleNamespace(private_data={'distances': {}}), origin={})
        profile = {}
        with patch.object(snapshot, 'forecast', return_value={}):
            result = snapshot.metrics({}, set(), profile=profile)
        self.assertEqual(result['distance'], 0)
        self.assertIn('schedule_prediction_seconds', profile)
        self.assertIn('metric_accounting_seconds', profile)


if __name__ == '__main__':
    unittest.main()
