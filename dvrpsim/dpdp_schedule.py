"""Fixed-route FCFS forecast from a live local DPDP snapshot, no simulation.

No new requests/routing, dwell constraints or diversion. Requires the DPDP
service definition: dock approach + unload + load, with one port held throughout.
Output rows retain full current-visit times even for an in-progress service.
Equal-arrival future events use model vehicle order; see audit for limits.
"""
import heapq


def predict_fixed_routes(model):
    now = model.env.now
    vehicles = list(model.vehicles)
    rows = {v.id: [] for v in vehicles}
    ports = {loc.id: [now] * loc.resource.capacity for loc in model.locations}
    queue = []
    serial = 0

    def duration(visit):
        return (model.private_data['docking_time'] +
                sum(o.quantity * model.private_data['unloading_time'] for o in visit.delivery_list) +
                sum(o.quantity * model.private_data['loading_time'] for o in visit.pickup_list))

    def record(vehicle, visit, arrival, start):
        leave = start + duration(visit)
        rows[vehicle.id].append(dict(factory=visit.location.id, arrival=arrival, start=start,
                                    waiting=start-arrival, docking=model.private_data['docking_time'],
                                    unloading=sum(o.quantity * model.private_data['unloading_time'] for o in visit.delivery_list),
                                    loading=sum(o.quantity * model.private_data['loading_time'] for o in visit.pickup_list),
                                    leave=leave, completion={o.id: arrival for o in visit.delivery_list}))
        return leave

    def enqueue(vehicle, index, arrival):
        nonlocal serial
        serial += 1
        heapq.heappush(queue, (max(now, arrival), arrival, serial, vehicle, index))

    def next_visit(vehicle, index, factory, departure):
        route = vehicle.next_visits
        if index < len(route):
            dest = route[index].location.id
            travel = 0 if factory == dest else model.private_data['travel_times'][(factory, dest)]
            enqueue(vehicle, index, departure + travel)

    # Reserve ports for actual ongoing services before scheduling waiters.
    for v in vehicles:
        if not v.is_at_location:
            continue
        cur = v.current_visit
        if cur.service_start_time is not None and cur.service_finish_time is None:
            leave = record(v, cur, cur.arrival_time, cur.service_start_time)
            if leave < now:
                raise ValueError(f'{v.id}: inconsistent service snapshot')
            port = ports[cur.location.id]
            if not port:
                raise ValueError('No ports')
            # Initialized slots are all now; consume one per occupied port.
            try:
                port[port.index(now)] = leave
            except ValueError as exc:
                raise ValueError('Too many ongoing services for dock capacity') from exc
            next_visit(v, 0, cur.location.id, leave)
    for p in ports.values():
        heapq.heapify(p)
    for v in vehicles:
        if v.is_at_location:
            cur = v.current_visit
            if cur.service_start_time is None:
                enqueue(v, -1, cur.arrival_time)
            elif cur.service_finish_time is not None:
                next_visit(v, 0, cur.location.id, now)
        elif v.has_next_visit:
            previous = v.previous_visit
            dest = v.next_visits[0].location.id
            origin = previous.location.id
            travel = 0 if origin == dest else model.private_data['travel_times'][(origin, dest)]
            enqueue(v, 0, previous.departure_time + travel)
    while queue:
        _, arrival, _, v, index = heapq.heappop(queue)
        visit = v.current_visit if index == -1 else v.next_visits[index]
        port = ports[visit.location.id]
        start = max(arrival, heapq.heappop(port))
        leave = record(v, visit, arrival, start)
        heapq.heappush(port, leave)
        next_visit(v, index + 1, visit.location.id, leave)
    return rows
