"""Tiny real DPDPVehicle simulations, no disk logger, no routing callbacks.

Only test infrastructure overrides logging/model init. Travel/service/port/order
execution use the repository's DPDPVehicle and Model unchanged.
"""
import sys
from pathlib import Path
from types import SimpleNamespace

CASE = Path(__file__).resolve().parent / 'examples/case_studies/dpdp'
if str(CASE) not in sys.path:
    sys.path.insert(0, str(CASE))
from dpdp_main import DPDPModel, DPDPVehicle
from dpdp_routing import calculate_earliest_departure_times, get_dpdp_state
from dvrpsim import Location, Order, Visit, VehicleLoading


class QuietModel(DPDPModel):
    def _init_logger(self):
        # Never construct DefaultLoggingCallback: its file handler truncates dvrp.log.
        self.physical_deliveries = {}
        self.log = SimpleNamespace(**{name: lambda *a, **k: None for name in (
            'on_simulation_start', 'on_departure', 'on_arrival', 'on_service_request',
            'on_service_start', 'on_service_finish', 'on_order_pickup', 'on_order_delivery',
            'custom', 'on_order_acceptance', 'on_departure_postponement')})

    def init(self):
        pass

    def on_order_delivery(self, order):
        self.physical_deliveries[order.id] = self.env.now
        super().on_order_delivery(order)


def build(vehicle_count=1, arrivals=None, ports=1):
    """Every vehicle goes D -> P -> Q; distinct item, quantity 1.

    P approach=1800, load=240; Q approach=1800, unload=240.
    D->P is arrival parameter (default 10); P->Q is 20 seconds.
    Q has vehicle_count ports so it never causes the pickup-queue fixtures to wait.
    """
    arrivals = arrivals or [10 * (i+1) for i in range(vehicle_count)]
    m = QuietModel()
    m.private_data = dict(docking_time=1800, loading_time=240, unloading_time=240,
                          distances={}, travel_times={})
    for name, cap in [('D', vehicle_count), ('P', ports), ('Q', vehicle_count)]:
        loc = Location(name)
        loc.resource = m.create_resource(capacity=cap)
        m.add_location(loc)
    for i, arrival in enumerate(arrivals):
        # Distinct depot needed for distinct travel times on the same OD matrix.
        depot = Location(f'D{i}')
        depot.resource = m.create_resource(capacity=1)
        m.add_location(depot)
        m.private_data['travel_times'][depot.id, 'P'] = arrival
        m.private_data['travel_times']['P', 'Q'] = 20
        v = DPDPVehicle(f'V_{i+1}')
        v.capacity = 15
        v.initial_location = depot
        v.loading_rule = VehicleLoading.LIFO
        m.add_vehicle(v)
        o = Order(f'o{i+1}-1', original_id=f'o{i+1}')
        o.quantity = 1
        o.pickup_location = m.get_location_by_id('P')
        o.delivery_location = m.get_location_by_id('Q')
        o.pickup_duration = o.delivery_duration = 240
        o.due_date = 2000
        m._add_order(o)
        o.accept()
        for factory, pickup, delivery in [('P', [o], []), ('Q', [], [o])]:
            visit = Visit()
            visit.location = m.get_location_by_id(factory)
            visit.pickup_list, visit.delivery_list = pickup, delivery
            v.next_visits.append(visit)
    m.on_simulation_start()
    for v in m.vehicles:
        v.run()
    return m


def observed_rows(model):
    rows = {}
    for v in model.vehicles:
        visits = v.previous_visits + ([v.current_visit] if v.current_visit else [])
        result = []
        for visit in visits:
            if visit.location.id not in ('P', 'Q'):
                continue
            result.append(dict(factory=visit.location.id, arrival=visit.arrival_time,
                               start=visit.service_start_time, waiting=visit.waiting_time,
                               docking=1800, loading=sum(o.pickup_duration for o in visit.pickup_list),
                               unloading=sum(o.delivery_duration for o in visit.delivery_list),
                               leave=visit.service_finish_time,
                               completion={o.id: o.delivery_time for o in visit.delivery_list}))
        rows[v.id] = result
    return rows


def build_mixed():
    m = build()
    v = next(iter(m.vehicles))
    carried = Order('carried', original_id='previous')
    carried.quantity = 1
    carried.pickup_location = v.initial_location
    carried.delivery_location = m.get_location_by_id('P')
    carried.pickup_duration = carried.delivery_duration = 240
    carried.due_date = 5
    m._add_order(carried)
    carried.accept()
    carried.pickup(v)
    v.carrying_orders.append(carried)
    v.next_visits[0].delivery_list = [carried]
    return m


def hand_rows(count, arrivals, ports=1):
    """Literal arithmetic oracle for these fixtures, separate from predictor."""
    # Expected pickup start times are intentionally explicit for audit review.
    expected_starts = {(1, 1): [10], (2, 1): [10, 2050],
                       (3, 1): [10, 2050, 4090], (3, 2): [10, 20, 2050],
                       (2, 2): [10, 10]}[count, ports]
    rows = {}
    for i, start in enumerate(expected_starts):
        leave = start + 1800 + 240
        delivery_arrival = leave + 20
        rows[f'V_{i+1}'] = [
            dict(factory='P', arrival=arrivals[i], start=start, waiting=start-arrivals[i],
                 docking=1800, loading=240, unloading=0, leave=leave, completion={}),
            dict(factory='Q', arrival=delivery_arrival, start=delivery_arrival, waiting=0,
                 docking=1800, loading=0, unloading=240, leave=delivery_arrival+2040,
                 completion={f'o{i+1}-1': delivery_arrival})]
    return rows


def validate_live_snapshot(model):
    """Test adapter only: snapshot a fixed complete plan, including current work."""
    from dpdp_feasibility import Item as FItem, Visit as FVisit, VehicleState, Plan, validate

    def visit(v, arrival=None):
        return FVisit(v.location.id, tuple(o.id for o in v.delivery_list),
                      tuple(o.id for o in v.pickup_list), arrival)

    its = {o.id: FItem(o.original_id, o.quantity, o.pickup_location.id,
                       o.delivery_location.id, o.due_date) for o in model.orders}
    delivered = {o.id for o in model.orders if o.is_delivered}
    info = {v['id']: v for v in get_dpdp_state(model)['vehicle_info']}
    fleet, plans = {}, {}
    for v in model.vehicles:
        current = visit(v.current_visit) if v.is_at_location else None
        route = [visit(node) for node in v.next_visits]
        destination = None
        if v.is_on_the_way:
            arrival = info[v.id]['destination']['arrive_time']
            route[0] = visit(v.next_visit, arrival)
            destination = route[0]
        fleet[v.id] = VehicleState(v.capacity, tuple(o.id for o in v.carrying_orders),
                                    current, bool(current and v.current_visit.service_start_time is not None), destination)
        plans[v.id] = Plan(current, tuple(route))
    return validate(its, fleet, plans, delivered)


def timing_evidence():
    from dpdp_schedule import predict_fixed_routes
    fixtures = [
        ('single', 1, 0, 1, [10]), ('two_one_port', 2, 0, 1, [10, 20]),
        ('three_current', 3, 100, 1, [10, 20, 30]),
        ('driving', 1, 5, 1, [10]), ('serving', 1, 100, 1, [10]),
        ('three_two_ports', 3, 100, 2, [10, 20, 30]),
        ('simultaneous_one_port', 2, 0, 1, [10, 10]),
        ('simultaneous_two_ports', 2, 0, 2, [10, 10]),
    ]
    results = []
    for name, count, cut, ports, arrivals in fixtures:
        m = build(count, arrivals, ports)
        if cut:
            m.env.run(until=cut)
        prediction = predict_fixed_routes(m)
        expected = hand_rows(count, arrivals, ports)
        validate_live_snapshot(m)
        m.env.run()
        actual = observed_rows(m)
        differences = [abs(prediction[v][i][k]-actual[v][i][k])
                       for v in actual for i in range(len(actual[v]))
                       for k in ('arrival', 'start', 'waiting', 'docking', 'loading', 'unloading', 'leave')]
        if prediction != expected or actual != expected:
            raise AssertionError(name)
        results.append(dict(fixture=name, snapshot_seconds=cut, hand=expected,
                            prediction=prediction, simulator=actual,
                            max_absolute_error_seconds=max(differences),
                            physical_delivery_seconds=m.physical_deliveries))
    m = build_mixed()
    m.env.run(until=2200)
    prediction = predict_fixed_routes(m)
    validate_live_snapshot(m)
    m.env.run()
    actual = observed_rows(m)
    if prediction != actual:
        raise AssertionError('mixed')
    results.append(dict(fixture='mixed_partial_service', snapshot_seconds=2200,
                        prediction=prediction, simulator=actual,
                        max_absolute_error_seconds=0, physical_delivery_seconds=m.physical_deliveries,
                        hand_calculation='P: arrival/start=10, unload ends=2050, leave=2290; Q: arrival/start=2310, leave=4350'))
    return results


if __name__ == '__main__':
    import json
    print(json.dumps(timing_evidence(), indent=2))
