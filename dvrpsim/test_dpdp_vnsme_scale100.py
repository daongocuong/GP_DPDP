"""Read-only saved-epoch regressions; no Java search or simulator rollout.

The chronological log reducer restores actual current visits, physical stacks,
order status and the last published suffix. Its Huawei projection must equal
the archived Java input before the failure is replayed through the real adapter.
The failed publications remain invalid; these are regression tests for honest
rejection and preservation of the complete-plan feasibility contract.
"""
from copy import deepcopy
import csv
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import re
import unittest

import run_dpdp_insertion as runner
from baselines.vnsme import VNSMEError, VNSMEPolicy, huawei_state
from dpdp_audit_fixtures import QuietModel
from dpdp_feasibility import Infeasible, Plan, Visit as PlanVisit, validate
from dpdp_insertion import Snapshot
from dpdp_main import DPDPVehicle
from dpdp_routing import transform_dpdp_decision
from dpdp_vnsme_reference import independent_score, load_reference
from dvrpsim import Location, Order, VehicleLoading, Visit
from dvrpsim.elements.order import OrderStatus


ROOT = Path(__file__).resolve().parent
SAVED = ROOT/'vnsme_runs/scale100_reference_20261109_r1'
EVIDENCE = ROOT/'vnsme_evidence/scale100_blockers_20261109_r2'
CASES = ((9, 61, ('0949430034-1', '0949430034-2')),
         (13, 22, ('0316410009-1', '0325060010-1', '0325060010-2',
                   '0325060010-3', '0325060010-4', '0325060010-5', '0325060010-6')))


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def epoch_output(directory):
    return dict(destinations=read(directory/'output_destination.json'),
                routes=read(directory/'output_route.json'))


def nodes(output, vehicle):
    first = output['destinations'][vehicle]
    return ([first] if first else []) + output['routes'][vehicle]


def restore_saved_epoch(instance, epoch):
    """Reduce recorded events into local objects; never execute simulation time.

    Only item definitions observed in saved inputs through the failing epoch
    are read. Future requests and held-out data are never opened.
    """
    run = SAVED/f'instance_{instance}'
    archive = run/'vnsme/epochs'
    initial = read(archive/'00000/vehicle_info.json')
    origin = initial[0]['update_time']
    definitions = {}
    for index in range(epoch+1):
        for filename in ('unallocated_order_items.json', 'ongoing_order_items.json'):
            for item in read(archive/f'{index:05d}'/filename):
                definitions[item['id']] = item

    model = QuietModel()
    model.private_data = dict(docking_time=1800, loading_time=240, unloading_time=240,
                              distances={}, travel_times={})
    with (run/'vnsme/benchmark/factory_info.csv').open(newline='', encoding='utf-8-sig') as handle:
        rows = csv.reader(handle)
        next(rows)
        for row in rows:
            location = Location(row[0])
            location.resource = model.create_resource(capacity=int(row[3]))
            model.add_location(location)
    with (run/'vnsme/benchmark/route_info.csv').open(newline='', encoding='utf-8-sig') as handle:
        rows = csv.reader(handle)
        next(rows)
        for row in rows:
            pair = row[1], row[2]
            model.private_data['distances'][pair] = float(row[3])
            model.private_data['travel_times'][pair] = int(row[4])
    fleet = {}
    for item in initial:
        vehicle = DPDPVehicle(item['id'])
        vehicle.capacity, vehicle.loading_rule = item['capacity'], VehicleLoading.LIFO
        vehicle.initial_location = model.get_location_by_id(item['cur_factory_id'])
        model.add_vehicle(vehicle)
        fleet[vehicle.id] = vehicle
    model.on_simulation_start()
    accepted_at = {}
    index = -1

    def visit(node):
        result = Visit()
        result.location = model.get_location_by_id(node['factory_id'])
        result.pickup_list = [model.get_order_by_id(i) for i in node['pickup_item_list']]
        result.delivery_list = [model.get_order_by_id(i) for i in node['delivery_item_list']]
        assert all(o is not None for o in result.pickup_list + result.delivery_list)
        return result

    for line in (run/'simulation.log').read_text(encoding='utf-8').splitlines():
        match = re.match(r'INFO\s*:\s*([\d.]+)\s*\|[^|]*\|\s*(.*)', line)
        if not match:
            continue
        now, event = float(match[1]), match[2]
        model.env._now = now
        if event == '<<< routing >>>':
            index += 1
            if index == epoch:
                break
            output = epoch_output(archive/f'{index:05d}')
            for vehicle in fleet.values():
                vehicle.next_visits = [visit(node) for node in nodes(output, vehicle.id)]
                for node in vehicle.next_visits:
                    for order in node.pickup_list + node.delivery_list:
                        order.status = OrderStatus.ACCEPTED
                        order.acceptance_time = now
                        accepted_at.setdefault(order.id, now)
            continue
        requested = re.match(r'order (\S+) is requested ', event)
        if requested:
            item = definitions[requested[1]]
            order = Order(item['id'], original_id=item['order_id'])
            order.quantity = item['demand']
            order.release_date = item['creation_time'] - origin
            order.due_date = item['committed_completion_time'] - origin
            order.pickup_location = model.get_location_by_id(item['pickup_factory_id'])
            order.delivery_location = model.get_location_by_id(item['delivery_factory_id'])
            order.pickup_duration, order.delivery_duration = item['load_time'], item['unload_time']
            model._add_order(order)
            continue
        vehicle_event = re.match(r'(V_\d+) \| (.*)', event)
        if not vehicle_event:
            continue
        vehicle, action = fleet[vehicle_event[1]], vehicle_event[2]
        if action.startswith('departed from '):
            a, b = re.match(r'departed from (\S+) to (\S+)', action).groups()
            assert vehicle.current_visit.location.id == a
            assert vehicle.next_visit.location.id == b
            vehicle.current_visit.departure_time = now
            vehicle.previous_visits.append(vehicle.current_visit)
            vehicle.current_visit = None
        elif action.startswith('arrived at '):
            assert vehicle.current_visit is None
            vehicle.current_visit = vehicle.next_visits.pop(0)
            assert vehicle.current_location.id == action.removeprefix('arrived at ')
            vehicle.current_visit.arrival_time = now
        elif action == 'service is started':
            vehicle.current_visit.service_start_time = now
        elif action == 'service is finished':
            vehicle.current_visit.service_finish_time = now
        elif action.startswith('order '):
            item_id, operation = re.match(r'order (\S+) is (picked up|delivered)', action).groups()
            order = model.get_order_by_id(item_id)
            if operation == 'picked up':
                order.pickup_time, order.pickup_vehicle = now, vehicle
                vehicle.carrying_orders.append(order)
            else:
                assert vehicle.carrying_orders[-1] is order, 'saved execution must obey LIFO'
                vehicle.carrying_orders.pop()
                order.delivery_time = now
        elif action.startswith('delivery time of order '):
            item_id, completion = re.match(r'delivery time of order (\S+) has been set to ([\d.]+)', action).groups()
            model.get_order_by_id(item_id).delivery_time = float(completion)
    assert index == epoch
    metadata = {row['id']: dict(gps_id=row['gps_id'], operation_time=row['operation_time']) for row in initial}
    state = dict(vehicle_info=read(archive/f'{epoch:05d}/vehicle_info.json'),
                 unallocated_orders=read(archive/f'{epoch:05d}/unallocated_order_items.json'),
                 ongoing_orders=read(archive/f'{epoch:05d}/ongoing_order_items.json'))
    return model, origin, metadata, state, epoch_output(archive/f'{epoch:05d}'), accepted_at


def archived_policy(origin, metadata, state, output):
    policy = object.__new__(VNSMEPolicy)
    policy.epoch_origin, policy.vehicle_metadata, policy.decisions = origin, metadata, []

    class ArchivedSession:
        def invoke(self, observed, remaining=None):
            # Includes the current-service projection, locked ETAs and physical
            # stacks; the adapter must see the same input as the original Java.
            if observed != state:
                raise AssertionError('restored local state differs from saved Java input')
            return deepcopy(output)

    policy.session = ArchivedSession()
    return policy


class SavedScale100EpochTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixtures = {(instance, epoch): restore_saved_epoch(instance, epoch)
                        for instance, epoch, _ in CASES}

    def test_saved_inputs_and_outputs_match_frozen_hashes(self):
        pins = read(EVIDENCE/'saved_epoch_fixture_pins.json')
        for filename, expected in pins['sha256'].items():
            with self.subTest(path=filename):
                self.assertEqual(sha(ROOT/filename), expected)

    def test_restored_local_state_exactly_matches_saved_huawei_inputs(self):
        for case, (model, origin, metadata, state, _, _) in self.fixtures.items():
            with self.subTest(case=case):
                self.assertEqual(huawei_state(model, origin, metadata), state)
                snapshot = Snapshot.observe(model)
                admitted = snapshot.admitted(snapshot.plans)
                self.assertTrue({o.id for o in model.orders if o.is_accepted} <= admitted)
                snapshot.check(snapshot.plans, admitted)

    def test_saved_failures_reject_accepted_loss_without_mutation_or_score(self):
        for instance, epoch, missing in CASES:
            model, origin, metadata, state, output, accepted_at = self.fixtures[instance, epoch]
            with self.subTest(instance=instance, epoch=epoch):
                policy = archived_policy(origin, metadata, state, output)
                before = Snapshot.observe(model)
                status = [(o.id, o.status, o.acceptance_time) for o in model.orders]
                self.assertTrue(all(i in accepted_at for i in missing))
                self.assertTrue(all(not before.objects[i].is_picked_up for i in missing))
                published = {i for v in output['destinations'] for n in nodes(output, v)
                             for i in n['pickup_item_list'] + n['delivery_item_list']}
                self.assertTrue(set(missing).isdisjoint(published))
                with self.assertRaisesRegex(VNSMEError, f'Java dropped previously accepted item {missing[0]}'):
                    policy.decide(model)
                self.assertEqual(Snapshot.observe(model).plans, before.plans)
                self.assertEqual([(o.id, o.status, o.acceptance_time) for o in model.orders], status)
                self.assertEqual(policy.decisions, [])
                result = read(SAVED/f'instance_{instance}/result.json')
                self.assertFalse(result['valid'])
                self.assertIsNone(result['score'])
                with self.assertRaisesRegex(ValueError, 'invalid or incomplete'):
                    independent_score(SAVED/f'instance_{instance}', ROOT/'unused', instance)

    def test_complete_remaining_plan_validator_also_rejects_both_publications(self):
        for case, (model, _, _, _, output, _) in self.fixtures.items():
            with self.subTest(case=case):
                snapshot = Snapshot.observe(model)
                # Convert archived output for an independent negative check;
                # this raw value is never enforced or returned by the adapter.
                raw = transform_dpdp_decision(model, output)
                with self.assertRaisesRegex(ValueError, 'accepted item missing from route'):
                    runner.guard_raw_decision(model, raw)
                plans = {}
                for vehicle, row in raw['vehicles'].items():
                    future = tuple(PlanVisit(n['location'], tuple(n['delivery_list']), tuple(n['pickup_list']))
                                   for n in row['next_visits'])
                    locked = snapshot.fleet[vehicle].destination
                    if locked:
                        future = (replace(future[0], arrival=locked.arrival),) + future[1:]
                    plans[vehicle] = Plan(snapshot.plans[vehicle].current, future)
                required = snapshot.admitted(snapshot.plans) | snapshot.admitted(plans)
                with self.assertRaises(Infeasible) as caught:
                    snapshot.check(plans, required)
                self.assertEqual(caught.exception.rule, 'MISSING_SERVICE')

    def test_unloaded_accepted_blocks_can_move_when_the_complete_plan_is_preserved(self):
        for instance, epoch, affected in CASES:
            model = self.fixtures[instance, epoch][0]
            snapshot = Snapshot.observe(model)
            moving = set(affected)
            with self.subTest(instance=instance, epoch=epoch):
                target = next(v for v, p in snapshot.plans.items()
                              if not p.future and not snapshot.fleet[v].carrying)
                self.assertIsNone(snapshot.fleet[target].destination)
                self.assertTrue(all(snapshot.objects[i].is_accepted and not snapshot.objects[i].is_picked_up
                                    for i in affected))
                sources = {v for v, p in snapshot.plans.items() for n in p.future
                           if moving & set(n.pickups + n.deliveries)}
                self.assertEqual(len(sources), 1)
                source = next(iter(sources))
                old = snapshot.plans[source]
                block = tuple(replace(n, pickups=tuple(i for i in n.pickups if i in moving),
                                      deliveries=tuple(i for i in n.deliveries if i in moving), arrival=None)
                              for n in old.future if moving & set(n.pickups + n.deliveries))
                # Keep every existing destination/current visit and all other
                # work. This isolated feasibility control changes no policy or
                # archived output; the failed publication still gets rejected.
                remaining = tuple(replace(n, pickups=tuple(i for i in n.pickups if i not in moving),
                                          deliveries=tuple(i for i in n.deliveries if i not in moving))
                                  for n in old.future)
                plans = {**snapshot.plans, source: replace(old, future=remaining),
                         target: replace(snapshot.plans[target], future=block)}
                admitted = snapshot.admitted(snapshot.plans)
                self.assertEqual(snapshot.admitted(plans), admitted)
                snapshot.check(plans, admitted)
                self.assertTrue(all(snapshot.objects[i].is_accepted for i in affected))

    def test_capacity_lifo_and_precedence_remain_enforced_on_each_restored_epoch(self):
        for case, (model, _, _, _, _, _) in self.fixtures.items():
            snapshot = Snapshot.observe(model)
            admitted = snapshot.admitted(snapshot.plans)
            items = {i: snapshot.items[i] for i in admitted}
            delivered = snapshot.delivered & admitted
            validate(items, snapshot.fleet, snapshot.plans, delivered)

            # Every archived epoch has carried load. Reducing the homogeneous
            # capacity makes that physical load exceed capacity immediately.
            fleet = {v: replace(state, capacity=.25) for v, state in snapshot.fleet.items()}
            with self.subTest(case=case, rule='CAPACITY'), self.assertRaises(Infeasible) as caught:
                validate(items, fleet, snapshot.plans, delivered)
            self.assertEqual(caught.exception.rule, 'CAPACITY')

            # Reverse one multi-item unload in a valid recorded future route.
            vehicle, index, node = next((v, k, n) for v, p in snapshot.plans.items()
                                        for k, n in enumerate(p.future) if len(n.deliveries) > 1)
            old = snapshot.plans[vehicle]
            future = old.future[:index] + (replace(node, deliveries=node.deliveries[::-1]),) + old.future[index+1:]
            plans = {**snapshot.plans, vehicle: replace(old, future=future)}
            with self.subTest(case=case, rule='LIFO'), self.assertRaises(Infeasible) as caught:
                validate(items, snapshot.fleet, plans, delivered)
            self.assertEqual(caught.exception.rule, 'LIFO')

            # Remove a not-yet-loaded accepted pickup, leaving its delivery.
            affected = next(i for p in snapshot.plans.values() for n in p.future for i in n.pickups
                            if snapshot.objects[i].is_accepted and not snapshot.objects[i].is_picked_up)
            plans = {v: replace(p, future=tuple(replace(n, pickups=tuple(i for i in n.pickups if i != affected))
                                                for n in p.future)) for v, p in snapshot.plans.items()}
            with self.subTest(case=case, rule='PRECEDENCE'), self.assertRaises(Infeasible) as caught:
                validate(items, snapshot.fleet, plans, delivered)
            self.assertEqual(caught.exception.rule, 'PICKUP_BEFORE_DELIVERY_OR_WRONG_VEHICLE')


class ImmutableReferenceTests(unittest.TestCase):
    def test_references_2_through_6_load_rescore_and_keep_pinned_artifacts_unchanged(self):
        summary = ROOT/'migration_runs/vnsme_reference_ready/summary.json'
        data = read(summary)
        protocol = ROOT/'protocols/dpdp_gp_split_v1.json'
        source_manifest = ROOT/read(protocol)['dataset_manifest']
        paths = [summary, protocol, source_manifest, ROOT/'third_party/vnsme/build_manifest.json']
        paths.extend(Path(row['run_directory'])/name for row in data['records']
                     for name in row['artifact_sha256'])
        before = {str(path): sha(path) for path in paths}
        dataset = ROOT/'datasets/xingtian/e4ef3a1c92d19d1d08c3ef0e2156b6fecefdbe04'
        scores, _ = load_reference(summary, (2, 3, 4, 5, 6), sha(protocol), sha(source_manifest), dataset)
        self.assertEqual(scores, {int(row['instance']): row['J'] for row in data['records']})
        self.assertEqual({str(path): sha(path) for path in paths}, before)


if __name__ == '__main__':
    unittest.main()
