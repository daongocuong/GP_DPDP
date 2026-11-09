"""Hand-calculated oracles and negative integration tests; no simulation."""
from decimal import Decimal as D
from pathlib import Path
import ast
import re
import sys
import tempfile
from types import SimpleNamespace
import unittest

from verify_dpdp_score import ROOT, InvalidRun, aggregate_score, clock_seconds, read_orders, verify


class HandCalculatedCases(unittest.TestCase):
    # 12 km / 2 vehicles = 6; penalty for 60 seconds = 10000/60.
    # Thus 60-second-late J = 6 + 166.666... = 172.666...
    def score(self, completions, items=None):
        return aggregate_score(items or {'a': 'order'}, {'order': D(100)},
                               completions, {'V_1': D(5), 'V_2': D(7)})

    def test_on_time(self):
        for arrival in (90, 100):
            with self.subTest(arrival=arrival):
                result = self.score([('a', arrival)])
                self.assertEqual(result['total_tardiness_seconds'], D(0))
                self.assertEqual(result['total_score'], D(6))
                self.assertEqual(result['late_original_orders'], 0)

    def test_sixty_seconds_late(self):
        result = self.score([('a', 160)])
        self.assertEqual(result['total_tardiness_seconds'], D(60))
        self.assertEqual(result['late_original_orders'], 1)
        self.assertLess(abs(result['total_score'] - D('172.6666666666666666666666667')), D('1e-23'))

    def test_split_order_uses_latest_arrival_once(self):
        # arrivals 120,160; due 100 -> max arrival 160 -> 60 sec, not 20+60.
        result = self.score([('a', 120), ('b', 160)], {'a': 'order', 'b': 'order'})
        self.assertEqual(result['total_tardiness_seconds'], D(60))
        self.assertEqual(result['late_original_orders'], 1)
        self.assertLess(abs(result['total_score'] - D('172.6666666666666666666666667')), D('1e-23'))

    def test_missing_item(self):
        with self.assertRaisesRegex(InvalidRun, 'Missing, duplicate'):
            self.score([('a', 160)], {'a': 'order', 'b': 'order'})

    def test_duplicate_item(self):
        with self.assertRaisesRegex(InvalidRun, 'Missing, duplicate'):
            self.score([('a', 120), ('a', 160)])

    def test_unknown_item(self):
        with self.assertRaises(InvalidRun):
            self.score([('a', 120), ('unknown', 160)])

    def test_cross_midnight_due(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / 'orders.csv'
            p.write_text('order_id,q_standard,q_small,q_box,creation_time,committed_completion_time,pickup_id,delivery_id\n'
                         'o,1,0,0,23:00:00,01:00:00,A,B\n', encoding='utf-8')
            items, deadlines = read_orders(p)
            self.assertEqual(items['o-1']['release'], D(82800))
            self.assertEqual(deadlines['o'], D(90000))
        self.assertEqual(clock_seconds('01:00:00'), D(3600))


class ExistingLogAudit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = ROOT / 'examples/case_studies/dpdp/data'
        cls.log = ROOT / 'run_logs/dpdp_success.log'
        raw = cls.log.read_bytes()
        cls.text = raw.decode('utf-16' if raw.startswith((b'\xff\xfe', b'\xfe\xff')) else 'utf-8-sig')

    def audit(self, log):
        return verify(log, self.data / 'instance_1/50_1.csv',
                      self.data / 'instance_1/vehicle_info_5.csv', self.data / 'route_info.csv')

    def test_existing_result(self):
        result = self.audit(self.log)
        self.assertEqual((result['vehicle_num'], result['original_orders'], result['items']), (5, 50, 95))
        self.assertEqual(result['total_distance_km'], D(1057))
        self.assertEqual(result['average_distance_km'], D('211.4'))
        self.assertEqual(result['total_tardiness_seconds'], D(57558))
        self.assertEqual(result['late_original_orders'], 10)
        # Hand arithmetic: 57558/3600 * 10000 = 159883.333...; add 211.4.
        self.assertLess(abs(result['total_score'] - D('160094.7333333333333333333333')), D('1e-21'))

    def invalid_copy(self, transform, message):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'modified_fixture.log'
            path.write_text(transform(self.text), encoding='utf-8')
            with self.assertRaisesRegex(InvalidRun, message):
                self.audit(path)

    def test_missing_delivery_in_log(self):
        self.invalid_copy(lambda s: '\n'.join(l for l in s.splitlines()
                          if 'order 0003480001-1 is delivered' not in l), 'Invalid adjustment')

    def test_duplicate_delivery_in_log(self):
        self.invalid_copy(lambda s: '\n'.join(l + '\n' + l if 'order 0003480001-1 is delivered' in l else l
                          for l in s.splitlines()), 'Duplicate delivered')

    def test_wrong_adjustment_cannot_change_score(self):
        self.invalid_copy(lambda s: s.replace('0003480001-1 has been set to 8772.0',
                                              '0003480001-1 has been set to 8773.0'), 'actual arrival')

    def test_broken_leg(self):
        self.invalid_copy(lambda s: s.replace('arrived at', 'arrive_typo at', 1), 'without arrival|Invalid departure')

    def test_missing_matrix_pair(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'matrix.csv'
            path.write_text('start_factory_id,end_factory_id,distance,time\nA,B,1,1\n', encoding='utf-8')
            with self.assertRaisesRegex(InvalidRun, 'Missing OD pair'):
                verify(self.log, self.data / 'instance_1/50_1.csv',
                       self.data / 'instance_1/vehicle_info_5.csv', path)


class XingtianReferenceComparison(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Execute only the evaluator definitions from the pinned MIT snapshot.
        # Do not execute its imports/configuration (which create output folders).
        path = ROOT / 'scoring_reference/xingtian/src/utils/evaluator.py'
        tree = ast.parse(path.read_text(encoding='utf-8'))
        definitions = ast.Module(body=[node for node in tree.body
                                      if isinstance(node, (ast.ClassDef, ast.FunctionDef))], type_ignores=[])
        namespace = {'sys': sys, 'Configs': SimpleNamespace(LAMDA=10000,
                     ORDER_STATUS_TO_CODE={'COMPLETED': 3}),
                     'logger': SimpleNamespace(info=lambda *a: None, error=lambda *a: None)}
        exec(compile(definitions, str(path), 'exec'), namespace)
        cls.evaluator = namespace['Evaluator']

    def test_reference_sixty_seconds_and_split(self):
        statuses = {item: [{'state': 3, 'update_time': t, 'order_id': 'o',
                            'committed_completion_time': 100}]
                    for item, t in [('a', 120), ('b', 160)]}
        self.assertEqual(self.evaluator.calculate_total_over_time(statuses), 60)

    def test_reference_on_existing_log(self):
        data = ROOT / 'examples/case_studies/dpdp/data'
        log_path = ROOT / 'run_logs/dpdp_success.log'
        raw = log_path.read_bytes()
        text = raw.decode('utf-16' if raw.startswith((b'\xff\xfe', b'\xfe\xff')) else 'utf-8-sig')
        items, due = read_orders(data / 'instance_1/50_1.csv')
        # Reference adapter uses logged adjustment times and visited-node sequences;
        # the independent verifier instead checks actual arrivals and paired legs.
        statuses = {item: [{'state': 3, 'update_time': float(t), 'order_id': items[item]['order'],
                            'committed_completion_time': float(due[items[item]['order']])}]
                    for item, t in re.findall(r'delivery time of order (\S+) has been set to ([\d.]+)', text)}
        nodes = {f'V_{i}': [] for i in range(1, 6)}
        for line in text.splitlines():
            if m := re.search(r'(V_\d+) \| departed from (\S+) to (\S+)', line):
                if not nodes[m[1]]:
                    nodes[m[1]].append({'factory_id': m[2]})
            elif m := re.search(r'(V_\d+) \| arrived at (\S+)', line):
                nodes[m[1]].append({'factory_id': m[2]})
        from verify_dpdp_score import csv_rows
        matrix = {(r['start_factory_id'], r['end_factory_id']): float(r['distance'])
                  for r in csv_rows(data / 'route_info.csv')}
        route_map = SimpleNamespace(calculate_distance_between_factories=lambda a, b: 0 if a == b else matrix[a, b])
        history = SimpleNamespace(get_vehicle_position_history=lambda: nodes,
                                  get_order_item_status_history=lambda: statuses)
        self.assertAlmostEqual(self.evaluator.calculate_total_distance(nodes, route_map), 1057)
        self.assertEqual(self.evaluator.calculate_total_over_time(statuses), 57558)
        self.assertAlmostEqual(self.evaluator.calculate_total_score(history, route_map, 5),
                               160094.73333333333, places=8)


if __name__ == '__main__':
    unittest.main()
