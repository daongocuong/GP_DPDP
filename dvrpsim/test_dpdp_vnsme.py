"""Contract, safety and failure-path checks for the external Java bridge."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import run_dpdp_insertion as runner
from baselines.vnsme import JavaSession, VNSMEPolicy, VNSMEError, huawei_state, write_json
from test_dpdp_insertion import make, order, visit


def node(factory, pickups=(), deliveries=(), arrival=0):
    return dict(factory_id=factory, pickup_item_list=list(pickups), delivery_item_list=list(deliveries),
                arrive_time=arrival, leave_time=0)


def policy(output):
    p = object.__new__(VNSMEPolicy)
    p.epoch_origin = 100000
    p.vehicle_metadata = {'V_1': dict(gps_id='G_1', operation_time='24')}
    p.decisions = []
    class Session:
        def invoke(self, state, remaining):
            self.state = state
            return deepcopy(output)
    p.session = Session()
    return p


class StateTests(unittest.TestCase):
    def test_only_observed_orders_no_future_data_read(self):
        m = make()
        order(m, 'a-1', quantity=.25)
        # This future dictionary is deliberately inaccessible to the bridge.
        class Forbidden(dict):
            def __iter__(self):
                raise AssertionError('future order access')
            def values(self):
                raise AssertionError('future order access')
        m.private_data['orders'] = Forbidden(future='secret')
        s = huawei_state(m, 100000, {'V_1': dict(gps_id='G_1', operation_time='24')})
        self.assertNotIn('secret', json.dumps(s))
        item = s['unallocated_orders'][0]
        self.assertEqual((item['id'], item['type'], item['delivery_state']), ('a-1', 'BOX', 1))
        self.assertEqual(item['load_time'], 60)
        self.assertIs(type(item['load_time']), int)
        self.assertEqual(item['creation_time'], 100000)

    def test_current_service_projection_preserves_stack_and_availability(self):
        m = make()
        for i in ('a-1', 'b-1'):
            order(m, i)
        v = next(iter(m.vehicles))
        v.previous_visits.append(v.current_visit)
        v.current_visit = visit(m, 'P', ['a-1', 'b-1'])
        v.current_visit.arrival_time = 0
        v.current_visit.service_start_time = 0
        v.carrying_orders.append(m.get_order_by_id('a-1'))
        s = huawei_state(m, 100000, {'V_1': dict(gps_id='G_1', operation_time='24')})
        self.assertEqual(s['vehicle_info'][0]['carrying_items'], ['a-1', 'b-1'])
        self.assertEqual(s['vehicle_info'][0]['leave_time_at_current_factory'], 102280)
        self.assertEqual({i['id'] for i in s['ongoing_orders']}, {'a-1', 'b-1'})
        self.assertEqual(s['unallocated_orders'], [])

    def test_fractional_second_rejected_instead_of_silent_truncation(self):
        m = make()
        o = order(m, 'a-1')
        o.release_date = .5
        with self.assertRaisesRegex(VNSMEError, 'integer'):
            huawei_state(m, 100000, {'V_1': dict(gps_id='G_1', operation_time='24')})


class DecisionTests(unittest.TestCase):
    def test_delayed_unassigned_items_not_accepted(self):
        m = make()
        order(m, 'a-1')
        p = policy(dict(destinations={'V_1': None}, routes={'V_1': []}))
        raw = p.decide(m)
        self.assertEqual(raw['orders'], {})
        runner.guard_raw_decision(m, raw)

    def test_previous_acceptance_cannot_disappear(self):
        m = make()
        order(m, 'a-1').accept()
        p = policy(dict(destinations={'V_1': None}, routes={'V_1': []}))
        with self.assertRaisesRegex(VNSMEError, 'dropped'):
            p.decide(m)

    def test_locked_factory_and_eta_must_match_java_output(self):
        for factory, arrival in [('R', 100020), ('P', 100021)]:
            m = make()
            order(m, 'a-1')
            v = next(iter(m.vehicles))
            v.next_visits = [visit(m, 'P', ['a-1']), visit(m, 'Q', deliveries=['a-1'])]
            p = policy(dict(destinations={'V_1': node(factory, ['a-1'], arrival=arrival)},
                            routes={'V_1': [node('Q', deliveries=['a-1'])]}))
            with self.subTest(factory=factory), self.assertRaisesRegex(VNSMEError, 'locked'):
                p.decide(m)

    def test_guard_rejects_wrong_lifo_capacity_unknown_and_missing_delivery(self):
        cases = [('LIFO', 1, ['a-1', 'b-1']), ('CAPACITY', 1, ['b-1', 'a-1']),
                 ('MISSING_SERVICE', 1, ['b-1']), ('UNKNOWN_ITEM', 1, ['z-1'])]
        for error, quantity, deliveries in cases:
            m = make()
            order(m, 'a-1', quantity=quantity)
            order(m, 'b-1', quantity=quantity)
            if error == 'CAPACITY':
                next(iter(m.vehicles)).capacity = 1
            p = policy(dict(destinations={'V_1': node('P', ['a-1', 'b-1'])},
                            routes={'V_1': [node('Q', deliveries=deliveries)]}))
            with self.subTest(error=error), self.assertRaises((ValueError, VNSMEError)):
                runner.guard_raw_decision(m, p.decide(m))

    def test_current_visit_unchanged_on_decision(self):
        m = make()
        order(m, 'a-1')
        p = policy(dict(destinations={'V_1': node('P', ['a-1'])},
                        routes={'V_1': [node('Q', deliveries=['a-1'])]}))
        v = next(iter(m.vehicles))
        current = v.current_visit
        raw = p.decide(m)
        self.assertIsNone(raw['vehicles']['V_1']['current_visit'])
        runner.guard_raw_decision(m, raw)
        self.assertIs(v.current_visit, current)


class ProcessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.csv = self.root/'network.csv'
        self.csv.write_text('test')
        self.s = JavaSession(self.root/'run', self.csv, self.csv, timeout=5)
        self.state = dict(vehicle_info=[dict(id='V_1', update_time=100000, destination=None)],
                          ongoing_orders=[], unallocated_orders=[])

    def script(self, code):
        self.s.command = [sys.executable, '-c', code]

    def test_old_outputs_removed_missing_new_output_fails(self):
        for name in ('output_destination.json', 'output_route.json'):
            write_json(self.s.exchange/name, {'V_1': []})
        self.script("print('SUCCESS')")
        with self.assertRaisesRegex(VNSMEError, 'missing'):
            self.s.invoke(self.state)
        self.assertFalse((self.s.exchange/'output_route.json').exists())

    def test_exit_failure_has_stderr_and_epoch(self):
        self.script("import sys; print('broken', file=sys.stderr); sys.exit(9)")
        with self.assertRaisesRegex(VNSMEError, 'exit=9'):
            self.s.invoke(self.state)
        self.assertIn('broken', (self.s.directory/'epochs/00000/stderr.txt').read_text())

    def test_real_subprocess_timeout_kills_child_and_records_invalid(self):
        self.script('import time; time.sleep(5)')
        with self.assertRaisesRegex(VNSMEError, 'TimeoutExpired'):
            self.s.invoke(self.state, remaining=.1)
        record = json.loads((self.s.directory/'epochs/00000/invocation.json').read_text())
        self.assertFalse(record['valid'])
        self.assertLess(record['wall_seconds'], 4)

    def test_run_deadline_prevents_java_launch(self):
        with patch('baselines.vnsme.subprocess.run') as process:
            with self.assertRaisesRegex(VNSMEError, 'wall-time exhausted'):
                self.s.invoke(self.state, remaining=0)
            process.assert_not_called()

    def test_invalid_json_and_incomplete_vehicle_map_rejected(self):
        for dest, route in [('bad', '{}'), ('{}', '{}')]:
            with self.subTest(dest=dest):
                self.script("from pathlib import Path; p=Path('algorithm/data_interaction'); "
                    f"(p/'output_destination.json').write_text({dest!r}); "
                    f"(p/'output_route.json').write_text({route!r}); "
                    "(p/'solution.json').write_text('{\"no.\":\"0\",\"route_after\":\"\"}'); print('SUCCESS')")
                with self.assertRaises(VNSMEError):
                    self.s.invoke(self.state)

    def test_private_run_directory_refuses_reuse(self):
        with self.assertRaises(FileExistsError):
            JavaSession(self.root/'run', self.csv, self.csv)

    def test_solution_memory_progress_and_epochs_are_preserved(self):
        self.script("from pathlib import Path; import json; p=Path('algorithm/data_interaction'); "
            "s=p/'solution.json'; n=int(json.loads(s.read_text())['no.'])+1 if s.exists() else 0; "
            "s.write_text(json.dumps({'no.': str(n), 'route_after':'V_1:[]'})); "
            "(p/'output_destination.json').write_text('{\"V_1\":null}'); "
            "(p/'output_route.json').write_text('{\"V_1\":[]}'); print('SUCCESS')")
        self.s.invoke(self.state)
        self.s.invoke(self.state)
        before = json.loads((self.s.directory/'epochs/00001/solution_before.json').read_text())
        self.assertEqual(before['no.'], '0')
        self.assertEqual(self.s.records[-1]['solution_no'], 1)

    def test_stale_solution_memory_rejected_even_with_new_routes(self):
        write_json(self.s.exchange/'solution.json', {'no.': '0', 'route_after': 'V_1:[]'})
        self.script("from pathlib import Path; p=Path('algorithm/data_interaction'); "
            "(p/'output_destination.json').write_text('{\"V_1\":null}'); "
            "(p/'output_route.json').write_text('{\"V_1\":[]}'); print('SUCCESS')")
        with self.assertRaisesRegex(VNSMEError, 'stale'):
            self.s.invoke(self.state)


if __name__ == '__main__':
    unittest.main()
