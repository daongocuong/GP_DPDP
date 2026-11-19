"""Independent complete-remaining-plan validator, no simulator imports.

Items are indivisible IDs. Snapshot stacks are bottom -> top. Current visits
include original lists, even completed operations; delivered and carrying state
identify completed operations there. Other visits contain only future work.
All not-yet-delivered items supplied must be served (complete-plan contract).
Unreleased/future requests must not be included. Deadlines are deliberately not
hard constraints. Homogeneous fleet only, as in this DPDP benchmark.
"""
from dataclasses import dataclass
from decimal import Decimal
import math
from time import perf_counter


@dataclass(frozen=True)
class Item:
    order: str
    quantity: float
    pickup: str
    delivery: str
    due: float = math.inf


@dataclass(frozen=True)
class Visit:
    factory: str
    deliveries: tuple = ()
    pickups: tuple = ()
    arrival: float | None = None


@dataclass(frozen=True)
class VehicleState:
    capacity: float
    carrying: tuple = ()
    current: Visit | None = None
    service_started: bool = False
    destination: Visit | None = None


@dataclass(frozen=True)
class Plan:
    current: Visit | None = None
    future: tuple = ()


class Infeasible(ValueError):
    # Ghi chú: Tạo lỗi có tên quy tắc, xe, item và bước tuyến để giải thích vì sao phương án bị loại.
    def __init__(self, rule, vehicle='-', item='-', step='-', detail=''):
        self.rule, self.vehicle, self.item, self.step = rule, vehicle, item, step
        super().__init__(f'{rule}: vehicle={vehicle}, item={item}, step={step}: {detail}')


# Ghi chú: Kiểm toàn bộ kế hoạch còn lại: sức chứa, LIFO, quyền sở hữu hàng, thứ tự phục vụ và các phần việc bị khóa.
def validate(items, fleet, plans, delivered=frozenset(), order_demands=None, profile=None):
    """Validate a plan and optionally accumulate inclusive timing diagnostics."""
    if profile is None:
        return _validate(items, fleet, plans, delivered, order_demands, None)
    started = perf_counter()
    initial_before = profile.get('feasibility_initial_vehicle_scan_seconds', 0.0)
    route_before = profile.get('feasibility_vehicle_route_scan_seconds', 0.0)
    try:
        return _validate(items, fleet, plans, delivered, order_demands, profile)
    finally:
        elapsed = perf_counter()-started
        initial = profile.get('feasibility_initial_vehicle_scan_seconds', 0.0)-initial_before
        route = profile.get('feasibility_vehicle_route_scan_seconds', 0.0)-route_before
        profile['feasibility_validator_total_seconds'] = profile.get('feasibility_validator_total_seconds', 0.0) + elapsed
        profile['feasibility_global_checks_seconds'] = profile.get('feasibility_global_checks_seconds', 0.0) + max(0.0, elapsed-initial-route)


def _validate(items, fleet, plans, delivered=frozenset(), order_demands=None, profile=None):
    """Return True or raise Infeasible with rule/vehicle/item/route step.

    Destination identity and arrival are locked, not its operation lists.
    Current operations become locked when service has started. No suffix lock.
    By default, supply the full item universe of every included original order.
    For incremental oversized groups, order_demands supplies full observed
    original-order demands while items contains the admitted subset. Missing
    service is still checked for every supplied item; no partial route is hidden.
    """
    # Ghi chú: Dừng kiểm tra ngay khi vi phạm và gắn thông tin vị trí lỗi.
    active = {'initial': None, 'route': None, 'operation': None}

    def finish_phase(name, key):
        started = active[name]
        if profile is not None and started is not None:
            profile[key] = profile.get(key, 0.0) + perf_counter()-started
        active[name] = None

    def fail(rule, vehicle='-', item='-', step='-', detail=''):
        if profile is not None:
            finish_phase('operation', 'feasibility_pickup_delivery_seconds')
            finish_phase('route', 'feasibility_vehicle_route_scan_seconds')
            finish_phase('initial', 'feasibility_initial_vehicle_scan_seconds')
        raise Infeasible(rule, vehicle, item, step, detail)

    if set(fleet) != set(plans) or not fleet:
        fail('FLEET', detail='one plan per known vehicle required')
    capacities = {Decimal(str(v.capacity)) for v in fleet.values()}
    if len(capacities) != 1 or any(not c.is_finite() or c <= 0 for c in capacities):
        fail('CAPACITY_SCHEMA', detail='positive homogeneous capacity required')
    capacity = next(iter(capacities))
    quantities, totals = {}, {}
    for item, spec in items.items():
        q = Decimal(str(spec.quantity))
        if not q.is_finite() or q <= 0:
            fail('ITEM_QUANTITY', item=item)
        quantities[item] = q
        totals[spec.order] = totals.get(spec.order, Decimal(0)) + q
    if not set(delivered) <= set(items):
        fail('UNKNOWN_DELIVERED')
    # An incremental insertion may include only some groups of an oversized
    # order. Use its full OBSERVED original demand, never the partial subtotal,
    # for the splitting rule. Existing complete-plan callers are unchanged.
    if order_demands is not None:
        for order, subtotal in totals.items():
            if order not in order_demands:
                fail('ORDER_DEMAND', detail=f'missing full demand for {order}')
            full = Decimal(str(order_demands[order]))
            if not full.is_finite() or full < subtotal:
                fail('ORDER_DEMAND', detail=f'inconsistent full demand for {order}')
            totals[order] = full
    owner, picked, done, batches = {}, set(), set(delivered), {}

    # Ghi chú: Chỉ cho phép thao tác trên ID item nguyên khối đã đăng ký.
    def known(item, vehicle, step):
        if not isinstance(item, str) or item not in items:
            fail('UNKNOWN_ITEM', vehicle, repr(item), step, 'use whole registered item IDs')

    # Ghi chú: Theo dõi các lô pickup; đơn gốc vừa một xe không được chia thành nhiều lô.
    def batch(order, token, vehicle, item, step):
        tokens = batches.setdefault(order, set())
        tokens.add(token)
        if totals[order] <= capacity and len(tokens) > 1:
            fail('ORDER_SPLIT', vehicle, item, step, f'order {order} fits one vehicle; multiple pickup batches')

    active['initial'] = perf_counter() if profile is not None else None
    for vehicle, state in fleet.items():
        for item in state.carrying:
            known(item, vehicle, 'initial')
            if item in owner or item in done:
                fail('INITIAL_OWNERSHIP', vehicle, item, 'initial')
            owner[item] = vehicle
            picked.add(item)
            token = 'current' if state.service_started and state.current and item in state.current.pickups else 'initial'
            batch(items[item].order, (vehicle, token), vehicle, item, 'initial')
        capacity_started = perf_counter() if profile is not None else None
        try:
            if sum((quantities[i] for i in state.carrying), Decimal(0)) > capacity:
                fail('CAPACITY', vehicle, step='initial', detail='initial load exceeds capacity')
        finally:
            if profile is not None:
                profile['feasibility_capacity_check_seconds'] = profile.get('feasibility_capacity_check_seconds', 0.0) + perf_counter()-capacity_started
    if profile is not None:
        finish_phase('initial', 'feasibility_initial_vehicle_scan_seconds')

    active['route'] = perf_counter() if profile is not None else None
    for vehicle, state in fleet.items():
        plan = plans[vehicle]
        if state.service_started and plan.current != state.current:
            fail('CURRENT_LOCK', vehicle, step='current', detail='service-started lists/factory cannot change')
        if state.current is not None and plan.current is None:
            fail('CURRENT_MISSING', vehicle, step='current')
        if state.current is None and plan.current is not None:
            fail('CURRENT_INVALID', vehicle, step='current')
        if state.current is not None and plan.current.factory != state.current.factory:
            fail('CURRENT_LOCATION', vehicle, step='current', detail='already at this factory')
        if state.destination is not None:
            if not plan.future or (plan.future[0].factory, plan.future[0].arrival) != (
                    state.destination.factory, state.destination.arrival):
                fail('DESTINATION_LOCK', vehicle, step='future[0]', detail='factory and committed arrival fixed')
        # Ghi chú: Mô phỏng tải trên bản sao stack: phần tử cuối là hàng được dỡ trước theo LIFO.
        stack = list(state.carrying)
        visits = ([('current', plan.current)] if plan.current is not None else [])
        visits += [(f'future[{i}]', v) for i, v in enumerate(plan.future)]
        for step, visit in visits:
            # Simulator unloads every item first, in list order, then loads.
            for operation, sequence in [('delivery', visit.deliveries), ('pickup', visit.pickups)]:
                local_seen = set()
                for index, item in enumerate(sequence):
                    active['operation'] = perf_counter() if profile is not None else None
                    pos = f'{step}/{operation}[{index}]'
                    known(item, vehicle, pos)
                    if item in local_seen:
                        fail('DUPLICATE_OPERATION', vehicle, item, pos)
                    local_seen.add(item)
                    spec = items[item]
                    if step == 'current' and state.service_started:
                        if operation == 'delivery' and item in delivered:
                            if profile is not None:
                                finish_phase('operation', 'feasibility_pickup_delivery_seconds')
                            continue
                        if operation == 'pickup' and (item in state.carrying or item in delivered):
                            # Already loaded during this exact committed visit.
                            if profile is not None:
                                finish_phase('operation', 'feasibility_pickup_delivery_seconds')
                            continue
                    if visit.factory != (spec.delivery if operation == 'delivery' else spec.pickup):
                        fail('FACTORY', vehicle, item, pos)
                    if operation == 'delivery':
                        if item in done:
                            fail('DUPLICATE_DELIVERY', vehicle, item, pos)
                        if owner.get(item) != vehicle:
                            fail('PICKUP_BEFORE_DELIVERY_OR_WRONG_VEHICLE', vehicle, item, pos)
                        lifo_started = perf_counter() if profile is not None else None
                        try:
                            if not stack or stack[-1] != item:
                                fail('LIFO', vehicle, item, pos, f'top={stack[-1] if stack else None}')
                        finally:
                            if profile is not None:
                                profile['feasibility_lifo_check_seconds'] = profile.get('feasibility_lifo_check_seconds', 0.0) + perf_counter()-lifo_started
                        stack.pop()
                        done.add(item)
                    else:
                        if item in picked or item in done:
                            fail('DUPLICATE_PICKUP', vehicle, item, pos)
                        batch(spec.order, (vehicle, step), vehicle, item, pos)
                        stack.append(item)
                        picked.add(item)
                        owner[item] = vehicle
                    # The initial load and every pickup are capacity-checked.
                    # A delivery only pops a positive-quantity item, so it
                    # cannot increase a load that was already within capacity.
                    # Re-summing the full stack after deliveries was redundant.
                    if operation == 'pickup':
                        capacity_started = perf_counter() if profile is not None else None
                        try:
                            load = sum((quantities[i] for i in stack), Decimal(0))
                            if load > capacity:
                                fail('CAPACITY', vehicle, item, pos, f'load={load}, capacity={capacity}')
                        finally:
                            if profile is not None:
                                profile['feasibility_capacity_check_seconds'] = profile.get('feasibility_capacity_check_seconds', 0.0) + perf_counter()-capacity_started
                    if profile is not None:
                        finish_phase('operation', 'feasibility_pickup_delivery_seconds')
        if stack:
            fail('UNDELIVERED_LOAD', vehicle, stack[-1], 'end')
    if profile is not None:
        finish_phase('route', 'feasibility_vehicle_route_scan_seconds')
    # Ghi chú: Kế hoạch chỉ hợp lệ khi mọi item trong phạm vi kiểm đều được giao; không được giấu hàng chưa phục vụ.
    if done != set(items):
        fail('MISSING_SERVICE', item=next(iter(set(items) - done)), step='end')
    return True
