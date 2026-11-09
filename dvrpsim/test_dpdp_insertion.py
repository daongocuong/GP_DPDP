from collections import Counter
from dataclasses import replace
import unittest
from unittest.mock import patch
import contextlib
import io
import json
from pathlib import Path
import tempfile

from dpdp_audit_fixtures import QuietModel, build
from dpdp_insertion import (Group, Snapshot, InsertionPolicy, candidates,
                            split_observed_orders)
from dpdp_feasibility import Infeasible
from dvrpsim import Location, Order, Visit, VehicleLoading
from dpdp_main import DPDPVehicle


def make(count=1):
    m = QuietModel()
    m.log.info = lambda *args: None
    m.private_data = dict(docking_time=1800, loading_time=240, unloading_time=240,
                          distances={}, travel_times={})
    names = ['H1', 'H2', 'P', 'Q', 'R', 'S', 'X', 'Y']
    for a in names:
        loc = Location(a)
        loc.resource = m.create_resource(capacity=1)
        m.add_location(loc)
        for b in names:
            m.private_data['distances'][a, b] = 0 if a == b else 1
            m.private_data['travel_times'][a, b] = 0 if a == b else 20
    for i in range(count):
        v = DPDPVehicle(f'V_{i+1}')
        v.capacity, v.loading_rule = 15, VehicleLoading.LIFO
        v.initial_location = m.get_location_by_id('H1')
        m.add_vehicle(v)
    m.on_simulation_start()
    return m


def order(m, id='a', original=None, quantity=1, pickup='P', delivery='Q', due=10000, release=0):
    o = Order(id, original_id=id if original is None else original)
    o.quantity, o.due_date, o.release_date = quantity, due, release
    o.pickup_location, o.delivery_location = m.get_location_by_id(pickup), m.get_location_by_id(delivery)
    o.pickup_duration = o.delivery_duration = 240*quantity
    m._add_order(o)
    return o


def visit(m, factory, pickups=(), deliveries=()):
    v = Visit()
    v.location = m.get_location_by_id(factory)
    v.pickup_list = [m.get_order_by_id(i) for i in pickups]
    v.delivery_list = [m.get_order_by_id(i) for i in deliveries]
    return v


def ranked_policy():
    from dpdp_gp import Node, TreeRanker
    return InsertionPolicy(TreeRanker(Node('feature', 'delta_distance_km')))


def enumerate_for(m, group):
    s = Snapshot.observe(m)
    admitted = s.admitted(s.plans)
    stats = dict(examined=0, rejected=0, forecasted=0, reasons=Counter(), examples={})
    return list(candidates(s, s.plans, group, admitted, s.metrics(s.plans, admitted), stats)), stats


class InsertionTests(unittest.TestCase):
    def test_pair_positions_include_nonadjacent_valid_insertion(self):
        m = make()
        order(m, 'a')
        order(m, 'b', pickup='R', delivery='S')
        order(m, 'c', pickup='X', delivery='Y')
        v = next(iter(m.vehicles))
        v.next_visits = [visit(m, 'P', ['a']), visit(m, 'R', ['b']),
                         visit(m, 'S', deliveries=['b']), visit(m, 'Q', deliveries=['a'])]
        group = Group('c', 0, ('c',), 'X', 'Y', 10000, 0)
        found, stats = enumerate_for(m, group)
        self.assertTrue(any(c.pickup_index == 1 and c.delivery_index == 4 for c in found))
        self.assertTrue(all(c.pickup_index >= 1 for c in found))
        self.assertEqual(stats['examined'], 10)  # suffix gaps: 4+3+2+1.
        self.assertGreater(stats['rejected'], 0)
        original = ['a', 'b', 'b', 'a']
        for candidate in found:
            old = [i for node in candidate.plans[v.id].future for i in node.deliveries+node.pickups if i != 'c']
            self.assertEqual(old, original)

    def test_lifo_and_overload_rejected_before_forecast(self):
        for quantity, reason in [(1, 'LIFO'), (15, 'CAPACITY')]:
            with self.subTest(quantity=quantity):
                m = make()
                order(m, 'a', quantity=quantity)
                order(m, 'b')
                v = next(iter(m.vehicles))
                v.next_visits = [visit(m, 'P', ['a']), visit(m, 'Q', deliveries=['a'])]
                group = Group('b', 0, ('b',), 'P', 'Q', 10000, 0)
                with patch.object(Snapshot, 'forecast', autospec=True, side_effect=Snapshot.forecast) as forecast:
                    found, stats = enumerate_for(m, group)
                    self.assertEqual(forecast.call_count, stats['forecasted']+1)
                self.assertGreater(stats['reasons'][reason], 0)
                self.assertEqual(stats['forecasted'], len(found))
                self.assertEqual(stats['examined'], stats['forecasted']+stats['rejected'])

    def test_single_fit_order_all_items_one_vehicle(self):
        m = make(2)
        order(m, 'a-1', original='a', quantity=7.5)
        order(m, 'a-2', original='a', quantity=7.5)
        raw = ranked_policy().decide(m)
        routes = [r['next_visits'] for r in raw['vehicles'].values()]
        self.assertEqual(sum(bool(r) for r in routes), 1)
        chosen = next(r for r in routes if r)
        self.assertEqual(chosen[0]['pickup_list'], ['a-1', 'a-2'])
        self.assertEqual(chosen[1]['delivery_list'], ['a-2', 'a-1'])

    def test_only_oversized_order_splits_incremental_full_demand(self):
        m = make(2)
        for i in range(2):
            order(m, f'a-{i}', original='a', quantity=10)
        policy = ranked_policy()
        raw = policy.decide(m)
        self.assertEqual(len(policy.decisions[0]['chosen']), 2)
        self.assertEqual(set(raw['orders']), {'a-0', 'a-1'})
        m._enforce_decision(raw)
        m.env.run()
        self.assertTrue(all(o.is_delivered for o in m.orders))

    def test_oversized_indivisible_item_fails_explicitly(self):
        m = make()
        order(m, quantity=16)
        with self.assertRaisesRegex(ValueError, 'indivisible item'):
            ranked_policy().decide(m)

    def test_edd_release_id_and_group_partition_deterministic(self):
        m = make()
        for id, due, release in [('c', 300, 0), ('b', 200, 5), ('a', 200, 5), ('z', 200, 0)]:
            order(m, id, original=id, due=due, release=release)
        groups = split_observed_orders(m.orders, 15)
        self.assertEqual([g.order for g in groups], ['z', 'a', 'b', 'c'])
        self.assertEqual(groups, split_observed_orders(reversed(list(m.orders)), 15))

    def test_stable_vehicle_and_position_tie_break(self):
        outputs = []
        for _ in range(2):
            m = make(2)
            order(m)
            p = ranked_policy()
            p.decide(m)
            outputs.append(p.decisions[0]['chosen'])
        self.assertEqual(outputs[0], outputs[1])
        self.assertEqual(outputs[0][0]['vehicle'], 'V_1')
        self.assertEqual((outputs[0][0]['pickup_index'], outputs[0][0]['delivery_index']), (0, 1))

    def test_no_candidate_retains_open_request_then_retries(self):
        m = make()
        order(m)
        policy = ranked_policy()
        real = Snapshot.check
        def blocked(snapshot, plans, admitted):
            if 'a' in admitted:
                raise Infeasible('TEST_BLOCKED', 'V_1', 'a', 'test')
            return real(snapshot, plans, admitted)
        with patch.object(Snapshot, 'check', blocked):
            raw = policy.decide(m)
        self.assertEqual(raw['orders'], {})
        self.assertEqual(raw['vehicles']['V_1']['next_visits'], [])
        self.assertEqual(len(policy.decisions[0]['deferred']), 1)
        self.assertTrue(m.get_order_by_id('a').is_open)
        self.assertEqual(set(policy.decide(m)['orders']), {'a'})

    def test_moving_and_serving_commitments_preserved(self):
        for cut in (5, 100):
            with self.subTest(cut=cut):
                m = build()
                m.log.info = lambda *args: None
                for a in m.locations:
                    for b in m.locations:
                        m.private_data['distances'][a.id, b.id] = 0 if a == b else 1
                        m.private_data['travel_times'].setdefault((a.id, b.id), 0 if a == b else 20)
                m.env.run(until=cut)
                order(m, 'new', original='new')
                v = next(iter(m.vehicles))
                current = v.current_visit
                oldfirst = v.next_visit.location.id
                raw = ranked_policy().decide(m)
                self.assertIsNone(raw['vehicles'][v.id]['current_visit'])
                self.assertEqual(raw['vehicles'][v.id]['next_visits'][0]['location'], oldfirst)
                self.assertIs(v.current_visit, current)

    def test_features_include_other_vehicle_dock_queue(self):
        m = make(2)
        a = order(m, 'a')
        order(m, 'b')
        v1, v2 = list(m.vehicles)
        v2.current_visit.location = m.get_location_by_id('H2')
        m.private_data['travel_times']['H1', 'P'] = 10
        m.private_data['travel_times']['H2', 'P'] = 20
        v2.next_visits = [visit(m, 'P', ['a']), visit(m, 'Q', deliveries=['a'])]
        found, _ = enumerate_for(m, Group('b', 0, ('b',), 'P', 'Q', 10000, 0))
        c = next(c for c in found if c.vehicle == 'V_1')
        self.assertEqual(c.features['delta_waiting_seconds'], 2030)
        self.assertEqual(c.metrics['rows']['V_2'][0]['waiting'], 2030)
        self.assertEqual(c.features['new_order_slack_seconds'], 7930)
        self.assertEqual(c.features['min_residual_capacity'], 14)
        self.assertEqual(c.features['delta_distance_km'], 2)

    def test_tardiness_feature_counts_original_order_once_and_accepts_late(self):
        m = make()
        order(m, 'a-1', original='a', due=1000)
        order(m, 'a-2', original='a', due=1000)
        m.private_data['travel_times']['H1', 'P'] = 10
        found, stats = enumerate_for(m, Group('a', 0, ('a-1', 'a-2'), 'P', 'Q', 1000, 0))
        self.assertEqual(stats['rejected'], 0)
        self.assertEqual(len(found), 1)
        # Pickup leaves 10+1800+480=2290; Q arrival=2310; one order late 1310.
        self.assertEqual(found[0].features['delta_tardiness_seconds'], 1310)
        self.assertEqual(found[0].features['new_order_slack_seconds'], -1310)
        self.assertEqual(found[0].features['min_residual_capacity'], 13)

    def test_selected_fixed_plan_forecast_matches_physical_execution(self):
        m = make(2)
        order(m, 'a', due=1000)
        order(m, 'b', pickup='R', delivery='S', due=500)
        raw = ranked_policy().decide(m)
        m._enforce_decision(raw)
        snap = Snapshot.observe(m)
        predicted = snap.metrics(snap.plans, snap.admitted(snap.plans))['completion']
        m.env.run()
        for o in m.orders:
            self.assertEqual(o.delivery_time, predicted[o.id])

    def test_no_future_information_reads_or_live_mutation(self):
        m = make()
        order(m)
        m.private_data['orders'] = {'unreleased': 'must never be read'}
        before = tuple(next(iter(m.vehicles)).next_visits)
        raw = ranked_policy().decide(m)
        self.assertEqual(set(raw['orders']), {'a'})
        self.assertEqual(tuple(next(iter(m.vehicles)).next_visits), before)

    def test_incremental_guard_extension_rejects_inconsistent_total(self):
        m = make()
        order(m)
        s = Snapshot.observe(m)
        s.demands['a'] = 0
        with self.assertRaisesRegex(Infeasible, 'ORDER_DEMAND'):
            s.check({'V_1': replace(s.plans['V_1'], future=(
                __import__('dpdp_feasibility').Visit('P', pickups=('a',)),
                __import__('dpdp_feasibility').Visit('Q', deliveries=('a',))))}, {'a'})


class RunnerTests(unittest.TestCase):
    def test_incomplete_run_has_no_score(self):
        import run_dpdp_insertion
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / 'run'
            with patch('sys.argv', ['run', '--policy', 'gp', '--tree', str(Path(__file__).resolve().parent/'gp_runs/multinstance_50_20261105/main/selected_tree.json'), '--output', str(out),
                                    '--max-simulation-seconds', '0']), contextlib.redirect_stdout(io.StringIO()):
                status = run_dpdp_insertion.main()
            result = json.loads((out/'result.json').read_text(encoding='utf-8'))
            self.assertEqual(status, 1)
            self.assertFalse(result['valid'])
            self.assertIsNone(result['score'])
            self.assertIn('safety horizon', result['error'])

    def test_existing_output_directory_is_never_overwritten(self):
        import run_dpdp_insertion
        with tempfile.TemporaryDirectory() as d:
            sentinel = Path(d) / 'keep.txt'
            sentinel.write_text('preserved', encoding='utf-8')
            with patch('sys.argv', ['run', '--policy', 'gp', '--tree', str(Path(__file__).resolve().parent/'gp_runs/multinstance_50_20261105/main/selected_tree.json'), '--output', d]):
                with self.assertRaises(FileExistsError):
                    run_dpdp_insertion.main()
            self.assertEqual(sentinel.read_text(encoding='utf-8'), 'preserved')


if __name__ == '__main__':
    unittest.main()
