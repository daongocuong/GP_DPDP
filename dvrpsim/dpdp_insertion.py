"""Pair-insertion machinery, groups, candidates and features for GP.

No GP implementation. Never read private_data['orders'] or future requests.
No visit merging: every inserted visit incurs the simulator's full docking time.
Old visits/operations/assignments and the first announced destination stay fixed.
"""
from collections import Counter, defaultdict
from dataclasses import dataclass, replace
from decimal import Decimal
from time import perf_counter
from types import SimpleNamespace
import math

from dvrpsim import Visit as SimulatorVisit
from dpdp_feasibility import Item, Visit, VehicleState, Plan, Infeasible, validate
from dpdp_schedule import predict_fixed_routes

FEATURE_UNITS = dict(delta_distance_km='km, all vehicles',
                     delta_tardiness_seconds='seconds, original orders, all vehicles',
                     delta_waiting_seconds='vehicle-seconds, all vehicles',
                     new_order_slack_seconds='seconds, due minus latest admitted original-order arrival',
                     min_residual_capacity='standard-pallet quantity, selected vehicle remaining route')


@dataclass(frozen=True)
class Group:
    order: str
    index: int
    items: tuple
    pickup: str
    delivery: str
    due: float
    release: float


def split_observed_orders(orders, capacity):
    """EDD/release/order ID; decreasing quantity then item ID; next-fit groups.

    Fit orders remain a single batch. Items are never divided. This exact
    function is part of the future shared candidate-generation interface.
    """
    by_order = defaultdict(list)
    for o in orders:
        by_order[o.original_id].append(o)
    result = []
    for order, entries in sorted(by_order.items(), key=lambda pair: (
            min(o.due_date for o in pair[1]), min(o.release_date for o in pair[1]), pair[0])):
        entries = sorted(entries, key=lambda o: (-o.quantity, o.id))
        if len({(o.pickup_location.id, o.delivery_location.id, o.due_date, o.release_date) for o in entries}) != 1:
            raise ValueError(f'inconsistent original order {order}')
        groups, current, load = [], [], Decimal(0)
        for o in entries:
            q = Decimal(str(o.quantity))
            if not q.is_finite() or q <= 0 or q > Decimal(str(capacity)):
                raise ValueError(f'indivisible item {o.id}: quantity {q} cannot fit capacity {capacity}')
            if load + q > Decimal(str(capacity)):
                groups.append(tuple(current))
                current, load = [], Decimal(0)
            current.append(o.id)
            load += q
        if current:
            groups.append(tuple(current))
        first = entries[0]
        result.extend(Group(order, i, ids, first.pickup_location.id, first.delivery_location.id,
                            first.due_date, first.release_date) for i, ids in enumerate(groups))
    return result


@dataclass
class Snapshot:
    now: float
    objects: dict
    items: dict
    demands: dict
    delivered: set
    fleet: dict
    plans: dict
    view: object
    origin: dict

    @classmethod
    def observe(cls, model):
        # model.orders contains only requests actually released by order_provider.
        objects = {o.id: o for o in model.orders}
        items = {o.id: Item(o.original_id, o.quantity, o.pickup_location.id,
                            o.delivery_location.id, o.due_date) for o in objects.values()}
        demands = defaultdict(Decimal)
        for o in objects.values():
            demands[o.original_id] += Decimal(str(o.quantity))
        delivered = {o.id for o in objects.values() if o.is_delivered}
        original_rows = predict_fixed_routes(model)
        fleet, plans, proxies, origins = {}, {}, [], {}
        locations = {loc.id: loc for loc in model.locations}

        def convert(v, arrival=None):
            return Visit(v.location.id, tuple(o.id for o in v.delivery_list),
                         tuple(o.id for o in v.pickup_list), arrival)

        for v in model.vehicles:
            current = convert(v.current_visit) if v.is_at_location else None
            future = tuple(convert(node) for node in v.next_visits)
            destination = None
            if future:
                if v.is_at_location:
                    # Announced next-arrival ETA from the verified predictor;
                    # skip the current row when current service is unfinished.
                    index = 1 if v.current_visit.service_finish_time is None else 0
                    arrival = original_rows[v.id][index]['arrival']
                else:
                    a, b = v.previous_location.id, v.next_location.id
                    arrival = v.previous_visit.departure_time + (0 if a == b else model.private_data['travel_times'][a, b])
                future = (replace(future[0], arrival=arrival),) + future[1:]
                destination = future[0]
            fleet[v.id] = VehicleState(v.capacity, tuple(o.id for o in v.carrying_orders), current,
                                       bool(current and v.current_visit.service_start_time is not None), destination)
            plans[v.id] = Plan(current, future)
            origins[v.id] = v.current_location.id if v.is_at_location else v.previous_location.id
            proxies.append(SimpleNamespace(id=v.id, capacity=v.capacity,
                         is_at_location=v.is_at_location, current_visit=v.current_visit,
                         previous_visit=v.previous_visit, has_next_visit=bool(future), next_visits=[]))
        static = {k: model.private_data[k] for k in ('docking_time', 'loading_time', 'unloading_time',
                                                    'travel_times', 'distances')}
        view = SimpleNamespace(env=SimpleNamespace(now=model.env.now), vehicles=proxies,
                               locations=list(locations.values()), private_data=static)
        view.location_by_id = locations
        return cls(model.env.now, objects, items, dict(demands), delivered, fleet, plans, view, origins)

    def admitted(self, plans):
        ids = set(self.delivered)
        for state in self.fleet.values():
            ids.update(state.carrying)
        for plan in plans.values():
            for visit in ((plan.current,) if plan.current else ()) + plan.future:
                ids.update(visit.pickups)
                ids.update(visit.deliveries)
        return ids

    def check(self, plans, admitted):
        validate({i: self.items[i] for i in admitted}, self.fleet, plans,
                 self.delivered & admitted, order_demands=self.demands)

    def forecast(self, plans):
        proxies = []
        for base in self.view.vehicles:
            visits = []
            for node in plans[base.id].future:
                visit = SimulatorVisit()
                visit.location = self.view.location_by_id[node.factory]
                visit.pickup_list = [self.objects[i] for i in node.pickups]
                visit.delivery_list = [self.objects[i] for i in node.deliveries]
                visits.append(visit)
            proxies.append(SimpleNamespace(**{**vars(base), 'next_visits': visits, 'has_next_visit': bool(visits)}))
        return predict_fixed_routes(SimpleNamespace(**{**vars(self.view), 'vehicles': proxies}))

    def metrics(self, plans, admitted):
        rows = self.forecast(plans)
        completion = {i: self.objects[i].delivery_time for i in self.delivered & admitted}
        waiting = 0
        for schedule in rows.values():
            for row in schedule:
                completion.update(row['completion'])
                waiting += row['waiting']
        missing = admitted - set(completion)
        if missing:
            raise ValueError(f'forecast missing completion: {sorted(missing)}')
        latest, due = {}, {}
        for i in admitted:
            order = self.items[i].order
            latest[order] = max(latest.get(order, float('-inf')), completion[i])
            due[order] = self.items[i].due
        tardiness = sum(max(0, t - due[o]) for o, t in latest.items())
        distance = 0
        for vehicle, plan in plans.items():
            origin = self.origin[vehicle]
            for node in plan.future:
                distance += 0 if origin == node.factory else self.view.private_data['distances'][origin, node.factory]
                origin = node.factory
        return dict(distance=distance, tardiness=tardiness, waiting=waiting,
                    latest=latest, completion=completion, rows=rows)


def min_residual(snapshot, vehicle, plan):
    state = snapshot.fleet[vehicle]
    stack = list(state.carrying)
    def residual():
        return state.capacity - sum(snapshot.items[i].quantity for i in stack)
    result = residual()
    for is_current, visit in ([(True, plan.current)] if plan.current else []) + [(False, n) for n in plan.future]:
        for i in visit.deliveries:
            if is_current and state.service_started and i in snapshot.delivered:
                continue
            stack.remove(i)
            result = min(result, residual())
        for i in visit.pickups:
            if is_current and state.service_started and (i in state.carrying or i in snapshot.delivered):
                continue
            stack.append(i)
            result = min(result, residual())
    return result


@dataclass
class Candidate:
    vehicle: str
    pickup_index: int
    delivery_index: int
    plans: dict
    features: dict
    metrics: dict

    @property
    def tie_key(self):
        return self.vehicle, self.pickup_index, self.delivery_index


def extract_features(snapshot, before, after, group, vehicle, plan):
    return dict(delta_distance_km=after['distance']-before['distance'],
                delta_tardiness_seconds=after['tardiness']-before['tardiness'],
                delta_waiting_seconds=after['waiting']-before['waiting'],
                new_order_slack_seconds=group.due-after['latest'][group.order],
                min_residual_capacity=min_residual(snapshot, vehicle, plan))


def candidates(snapshot, plans, group, admitted, before, stats):
    """Enumerate every pair of separate pickup/delivery visits in mutable suffix.

    Every enumerated candidate is checked BEFORE forecast/scoring or enforcement.
    Rejection counters/examples refer to whole-fleet feasibility, not soft lateness.
    """
    new_ids = admitted | set(group.items)
    pickup = Visit(group.pickup, pickups=group.items)
    delivery = Visit(group.delivery, deliveries=group.items[::-1])
    for vehicle in sorted(plans):
        old = plans[vehicle].future
        start = 1 if snapshot.fleet[vehicle].destination is not None else 0
        for p in range(start, len(old)+1):
            with_pickup = old[:p] + (pickup,) + old[p:]
            for d in range(p+1, len(old)+2):
                stats['examined'] += 1
                new = replace(plans[vehicle], future=with_pickup[:d]+(delivery,)+with_pickup[d:])
                trial = {**plans, vehicle: new}
                try:
                    started = perf_counter()
                    snapshot.check(trial, new_ids)
                except Infeasible as exc:
                    stats['rejected'] += 1
                    stats['reasons'][exc.rule] += 1
                    stats['examples'].setdefault(exc.rule, str(exc))
                    continue
                finally:
                    stats['feasibility_wall_seconds'] = stats.get('feasibility_wall_seconds', 0) + perf_counter()-started
                started = perf_counter()
                after = snapshot.metrics(trial, new_ids)
                stats['forecast_wall_seconds'] = stats.get('forecast_wall_seconds', 0) + perf_counter()-started
                stats['forecasted'] += 1
                yield Candidate(vehicle, p, d, trial,
                                extract_features(snapshot, before, after, group, vehicle, new), after)


class InsertionPolicy:
    def __init__(self, score_function):
        if not callable(score_function):
            raise TypeError('GP insertion requires an explicit candidate ranker')
        self.decisions = []
        self.score_function = score_function

    def decide(self, model):
        start_time = perf_counter()
        snap = Snapshot.observe(model)
        plans = snap.plans
        admitted = snap.admitted(plans)
        snap.check(plans, admitted)
        before = snap.metrics(plans, admitted)
        stats = dict(simulation_seconds=snap.now, examined=0, rejected=0, forecasted=0,
                     reasons=Counter(), examples={}, chosen=[], deferred=[])
        groups = split_observed_orders(snap.objects.values(), next(iter(snap.fleet.values())).capacity)
        for group in groups:
            intersection = admitted & set(group.items)
            if intersection == set(group.items):
                continue
            if intersection:
                raise ValueError(f'partially assigned canonical group: {group}')
            best = None
            for candidate in candidates(snap, plans, group, admitted, before, stats):
                ranking = self.score_function(candidate.features, len(snap.fleet))
                if not math.isfinite(ranking):
                    raise ValueError('nonfinite candidate ranking; run invalid')
                key = (ranking, *candidate.tie_key)
                if best is None or key < best[0]:
                    best = key, candidate
            if best is None:
                reason = dict(order=group.order, group=group.index, items=group.items,
                              message='no feasible insertion; retain request open for next periodic routing',
                              rejection_reasons=dict(stats['reasons']))
                stats['deferred'].append(reason)
                model.log.info(f'GP_DEFER {reason}')
                continue
            key, selected = best
            plans, before = selected.plans, selected.metrics
            admitted |= set(group.items)
            stats['chosen'].append(dict(order=group.order, group=group.index,
                                        items=group.items, vehicle=selected.vehicle,
                                        pickup_index=selected.pickup_index, delivery_index=selected.delivery_index,
                                        ranking_score=key[0], features=selected.features))
        # Final gate before handing any route to Model._enforce_decision.
        snap.check(plans, admitted)
        decision = {'vehicles': {}, 'orders': {}}
        for vehicle, plan in plans.items():
            decision['vehicles'][vehicle] = dict(current_visit=None, next_visits=[
                dict(location=node.factory, pickup_list=list(node.pickups), delivery_list=list(node.deliveries))
                for node in plan.future])
        for i in sorted(admitted-snap.delivered):
            if not snap.objects[i].is_accepted:
                decision['orders'][i] = {'status': 'accepted'}
        stats.update(wall_seconds=perf_counter()-start_time, admitted_items=len(admitted),
                     observed_items=len(snap.objects), pending_items=sorted(set(snap.items)-admitted))
        self.decisions.append(stats)
        return decision
