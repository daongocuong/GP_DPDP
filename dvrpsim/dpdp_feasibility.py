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
    def __init__(self, rule, vehicle='-', item='-', step='-', detail=''):
        self.rule, self.vehicle, self.item, self.step = rule, vehicle, item, step
        super().__init__(f'{rule}: vehicle={vehicle}, item={item}, step={step}: {detail}')


def validate(items, fleet, plans, delivered=frozenset(), order_demands=None):
    """Return True or raise Infeasible with rule/vehicle/item/route step.

    Destination identity and arrival are locked, not its operation lists.
    Current operations become locked when service has started. No suffix lock.
    By default, supply the full item universe of every included original order.
    For incremental oversized groups, order_demands supplies full observed
    original-order demands while items contains the admitted subset. Missing
    service is still checked for every supplied item; no partial route is hidden.
    """
    def fail(rule, vehicle='-', item='-', step='-', detail=''):
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

    def known(item, vehicle, step):
        if not isinstance(item, str) or item not in items:
            fail('UNKNOWN_ITEM', vehicle, repr(item), step, 'use whole registered item IDs')

    def batch(order, token, vehicle, item, step):
        tokens = batches.setdefault(order, set())
        tokens.add(token)
        if totals[order] <= capacity and len(tokens) > 1:
            fail('ORDER_SPLIT', vehicle, item, step, f'order {order} fits one vehicle; multiple pickup batches')

    for vehicle, state in fleet.items():
        for item in state.carrying:
            known(item, vehicle, 'initial')
            if item in owner or item in done:
                fail('INITIAL_OWNERSHIP', vehicle, item, 'initial')
            owner[item] = vehicle
            picked.add(item)
            token = 'current' if state.service_started and state.current and item in state.current.pickups else 'initial'
            batch(items[item].order, (vehicle, token), vehicle, item, 'initial')
        if sum((quantities[i] for i in state.carrying), Decimal(0)) > capacity:
            fail('CAPACITY', vehicle, step='initial', detail='initial load exceeds capacity')

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
        stack = list(state.carrying)
        visits = ([('current', plan.current)] if plan.current is not None else [])
        visits += [(f'future[{i}]', v) for i, v in enumerate(plan.future)]
        for step, visit in visits:
            # Simulator unloads every item first, in list order, then loads.
            for operation, sequence in [('delivery', visit.deliveries), ('pickup', visit.pickups)]:
                local_seen = set()
                for index, item in enumerate(sequence):
                    pos = f'{step}/{operation}[{index}]'
                    known(item, vehicle, pos)
                    if item in local_seen:
                        fail('DUPLICATE_OPERATION', vehicle, item, pos)
                    local_seen.add(item)
                    spec = items[item]
                    if step == 'current' and state.service_started:
                        if operation == 'delivery' and item in delivered:
                            continue
                        if operation == 'pickup' and (item in state.carrying or item in delivered):
                            # Already loaded during this exact committed visit.
                            continue
                    if visit.factory != (spec.delivery if operation == 'delivery' else spec.pickup):
                        fail('FACTORY', vehicle, item, pos)
                    if operation == 'delivery':
                        if item in done:
                            fail('DUPLICATE_DELIVERY', vehicle, item, pos)
                        if owner.get(item) != vehicle:
                            fail('PICKUP_BEFORE_DELIVERY_OR_WRONG_VEHICLE', vehicle, item, pos)
                        if not stack or stack[-1] != item:
                            fail('LIFO', vehicle, item, pos, f'top={stack[-1] if stack else None}')
                        stack.pop()
                        done.add(item)
                    else:
                        if item in picked or item in done:
                            fail('DUPLICATE_PICKUP', vehicle, item, pos)
                        batch(spec.order, (vehicle, step), vehicle, item, pos)
                        stack.append(item)
                        picked.add(item)
                        owner[item] = vehicle
                    load = sum((quantities[i] for i in stack), Decimal(0))
                    if load > capacity:
                        fail('CAPACITY', vehicle, item, pos, f'load={load}, capacity={capacity}')
        if stack:
            fail('UNDELIVERED_LOAD', vehicle, stack[-1], 'end')
    if done != set(items):
        fail('MISSING_SERVICE', item=next(iter(set(items) - done)), step='end')
    return True
