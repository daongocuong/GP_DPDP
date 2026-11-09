import unittest
from dpdp_audit_fixtures import (build, hand_rows, observed_rows,
                                calculate_earliest_departure_times, get_dpdp_state,
                                validate_live_snapshot, build_mixed)
from dpdp_schedule import predict_fixed_routes

TOLERANCE = 1e-9  # seconds, fixed before runs; fixtures use exact integer seconds.


class ScheduleAudit(unittest.TestCase):
    def compare(self, actual, expected):
        self.assertEqual(set(actual), set(expected))
        for vehicle in expected:
            self.assertEqual(len(actual[vehicle]), len(expected[vehicle]))
            for got, want in zip(actual[vehicle], expected[vehicle]):
                self.assertEqual(got['factory'], want['factory'])
                for field in ('arrival', 'start', 'waiting', 'docking', 'loading', 'unloading', 'leave'):
                    self.assertAlmostEqual(got[field], want[field], delta=TOLERANCE,
                                           msg=f'{vehicle}/{want["factory"]}/{field}')
                self.assertEqual(got['completion'], want['completion'])

    def run_fixture(self, count, cut, arrivals=None, ports=1):
        arrivals = arrivals or [10*(i+1) for i in range(count)]
        model = build(count, arrivals, ports)
        if cut:
            model.env.run(until=cut)
        forecast = predict_fixed_routes(model)
        self.assertTrue(validate_live_snapshot(model))
        hand = hand_rows(count, arrivals, ports)
        self.compare(forecast, hand)
        model.env.run()
        self.compare(observed_rows(model), hand)
        for order in model.orders:
            # arrival-based completion intentionally differs from physical finish.
            self.assertLess(order.delivery_time, observed_rows(model)[order.pickup_vehicle.id][-1]['leave'])
        return model

    def test_single_vehicle_without_queue(self):
        self.run_fixture(1, 0)

    def test_two_vehicles_one_port(self):
        self.run_fixture(2, 0)

    def test_three_vehicles_current_factory_different_departures(self):
        self.run_fixture(3, 100)

    def test_snapshot_while_driving(self):
        m = build()
        m.env.run(until=5)
        self.assertEqual(get_dpdp_state(m)['vehicle_info'][0]['destination']['arrive_time'], 10)
        self.run_fixture(1, 5)

    def test_snapshot_while_serving(self):
        self.run_fixture(1, 100)

    def test_multiple_ports(self):
        self.run_fixture(3, 100, ports=2)

    def test_same_arrival_with_sufficient_ports(self):
        self.run_fixture(2, 0, arrivals=[10, 10], ports=2)

    def test_same_arrival_one_port_fifo(self):
        self.run_fixture(2, 0, arrivals=[10, 10], ports=1)

    def test_departure_map_distinct_vehicles(self):
        m = build(3)
        m.env.run(until=100)
        self.assertEqual(calculate_earliest_departure_times(m),
                         {'V_1': 2050, 'V_2': 4090, 'V_3': 6130})

    def test_state_next_arrival_for_each_vehicle(self):
        m = build(3)
        m.env.run(until=100)
        state = get_dpdp_state(m)['vehicle_info']
        self.assertEqual([v['leave_time_at_current_factory'] for v in state], [2050, 4090, 6130])
        self.assertEqual([v['destination']['arrive_time'] for v in state], [2070, 4110, 6150])

    def test_dock_held_for_approach_and_service(self):
        m = build()
        # Explicit hand-selected times: P arrival 10, approach ends 1810,
        # loading ends 2050; Q arrival 2070, unloading ends 4110.
        for time, p_count, q_count in [(11, 1, 0), (1809, 1, 0), (1900, 1, 0),
                                        (2060, 0, 0), (2071, 0, 1), (4000, 0, 1),
                                        (4111, 0, 0)]:
            m.env.run(until=time)
            self.assertEqual(m.get_location_by_id('P').resource.count, p_count)
            self.assertEqual(m.get_location_by_id('Q').resource.count, q_count)

    def test_mixed_unload_load_and_partial_service_snapshot(self):
        m = build_mixed()
        carried = m.get_order_by_id('carried')
        hand = {'V_1': [dict(factory='P', arrival=10, start=10, waiting=0,
                             docking=1800, unloading=240, loading=240, leave=2290,
                             completion={'carried': 10}),
                         dict(factory='Q', arrival=2310, start=2310, waiting=0,
                              docking=1800, unloading=240, loading=0, leave=4350,
                              completion={'o1-1': 2310})]}
        # At 2200 the unloading has completed, but loading/service has not.
        m.env.run(until=2200)
        self.assertEqual(m.physical_deliveries['carried'], 2050)
        self.assertTrue(validate_live_snapshot(m))
        self.compare(predict_fixed_routes(m), hand)
        m.env.run()
        self.compare(observed_rows(m), hand)
        self.assertEqual(carried.delivery_time, 10)
        self.assertEqual(carried.tardiness, 5)


if __name__ == '__main__':
    unittest.main()
