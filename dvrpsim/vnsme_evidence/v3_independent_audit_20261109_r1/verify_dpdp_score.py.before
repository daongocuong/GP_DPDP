"""Independently audit a completed local DPDP log; never import the simulator.

Only standard-library modules are used. CLI prints JSON, writes no files and
returns 1 for invalid inputs. See DPDP_SCORING_AUDIT.md for source definitions.
"""
import argparse
from collections import Counter
import csv
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parent
REFERENCE_COMMIT = 'e4ef3a1c92d19d1d08c3ef0e2156b6fecefdbe04'
VERIFIER_VERSION = '1.0.0'
LIMITATIONS = [
    'Scores the recorded local trajectory; does not prove identical dynamics to Xingtian.',
    'Initial vehicle positions are inferred from first departures, not a run manifest.',
    'No full capacity, LIFO, conditional splitting or locked-route feasibility audit.',
    'Historical source/configuration identity is not cryptographically bound to this log.',
    'Only the numeric elapsed-seconds column is used; wall-clock run date is unknown.',
]


class InvalidRun(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise InvalidRun(message)


def number(value):
    result = Decimal(str(value))
    require(result.is_finite() and result >= 0, f'Invalid nonnegative number: {value}')
    return result


def clock_seconds(value):
    parts = value.split(':')
    require(len(parts) == 3, f'Invalid clock: {value}')
    h, m, s = map(int, parts)
    require(0 <= h < 24 and 0 <= m < 60 and 0 <= s < 60, f'Invalid clock: {value}')
    return Decimal(h * 3600 + m * 60 + s)


def csv_rows(path):
    with Path(path).open(encoding='utf-8-sig', newline='') as handle:
        return list(csv.DictReader(handle))


def read_orders(path):
    items, deadlines = {}, {}
    for row in csv_rows(path):
        order = row['order_id']
        require(order not in deadlines, f'Duplicate original order: {order}')
        release = clock_seconds(row['creation_time'])
        due = clock_seconds(row['committed_completion_time'])
        if due < release:
            due += 86400
        deadlines[order] = due
        counts = [int(row[k]) for k in ('q_standard', 'q_small', 'q_box')]
        require(all(n >= 0 for n in counts) and sum(counts) > 0, f'Invalid item counts: {order}')
        for i in range(sum(counts)):
            items[f'{order}-{i + 1}'] = dict(order=order, release=release,
                                           pickup=row['pickup_id'], delivery=row['delivery_id'])
    require(bool(items), 'Empty orders input')
    return items, deadlines


def aggregate_score(item_to_order, deadlines, completions, distances):
    """Completions are (item_id, arrival_seconds); reject duplicates, never hide them."""
    require(bool(distances), 'No vehicles')
    counts = Counter(item for item, _ in completions)
    expected = Counter(item_to_order.keys())
    require(counts == expected,
            f'Missing, duplicate or unknown delivery items: {dict(counts - expected)}; '
            f'missing: {list((expected - counts).elements())}')
    require(set(item_to_order.values()) == set(deadlines), 'Original-order mapping mismatch')
    latest = {}
    for item, time in completions:
        order = item_to_order[item]
        latest[order] = max(latest.get(order, Decimal(0)), number(time))
    tardiness = {order: max(Decimal(0), latest[order] - number(due))
                 for order, due in deadlines.items()}
    total_distance = sum((number(d) for d in distances.values()), Decimal(0))
    average = total_distance / len(distances)
    total_tardiness = sum(tardiness.values(), Decimal(0))
    penalty = total_tardiness * 10000 / 3600
    return dict(vehicle_num=len(distances), original_orders=len(deadlines), items=len(item_to_order),
                total_distance_km=total_distance, average_distance_km=average,
                total_tardiness_seconds=total_tardiness,
                late_original_orders=sum(t > 0 for t in tardiness.values()),
                tardiness_penalty=penalty, total_score=average + penalty,
                distance_by_vehicle_km=distances, tardiness_by_original_order_seconds=tardiness)


def verify(log_path, orders_path, vehicles_path, matrix_path):
    items, deadlines = read_orders(orders_path)
    vehicle_rows = csv_rows(vehicles_path)
    vehicle_ids = [row['car_num'] for row in vehicle_rows]
    require(len(set(vehicle_ids)) == len(vehicle_ids) and bool(vehicle_ids), 'Invalid vehicle IDs')
    matrix = {}
    for row in csv_rows(matrix_path):
        key = (row['start_factory_id'], row['end_factory_id'])
        value = (number(row['distance']), number(row['time']))
        require(key not in matrix or matrix[key] == value, f'Conflicting OD pair: {key}')
        matrix[key] = value
    raw = Path(log_path).read_bytes()
    log = raw.decode('utf-16' if raw.startswith((b'\xff\xfe', b'\xfe\xff')) else 'utf-8-sig')
    require(not re.search(r'ERROR|WARNING|Traceback|could not finish simulation', log), 'Log reports failure/warning')
    events = {kind: {} for kind in ('requested', 'picked up', 'delivered', 'adjusted')}
    distances = {vehicle: Decimal(0) for vehicle in vehicle_ids}
    at, pending = {}, {}
    completions, starts, finishes = [], [], []
    last_time = Decimal(0)
    depart_count = arrival_count = 0
    pattern = re.compile(r'^INFO\s*:\s*([\d.]+)\s*\|\s*[\d:]+\s*\|\s*(?:(V_\d+)\s*\|\s*)?(.*)$')
    for line_num, line in enumerate(log.splitlines(), 1):
        match = pattern.fullmatch(line)
        if not match:
            require(not re.match(r'^INFO\s*:\s*[\d.]+\s*\|', line), f'Malformed event at line {line_num}')
            continue
        time, vehicle, message = number(match[1]), match[2], match[3]
        require(time >= last_time, f'Nonmonotonic time at line {line_num}')
        last_time = time
        if vehicle:
            require(vehicle in distances, f'Unknown vehicle at line {line_num}: {vehicle}')
        if message == 'START':
            starts.append(time)
        elif message == 'FINISH':
            finishes.append(time)
        elif m := re.fullmatch(r'departed from (\S+) to (\S+)', message):
            require(vehicle is not None and vehicle not in pending, f'Invalid departure at line {line_num}')
            origin, dest = m.groups()
            if vehicle in at:
                require(at[vehicle][0] == origin, f'Discontinuous route at line {line_num}')
            require(origin == dest or (origin, dest) in matrix, f'Missing OD pair: {origin}, {dest}')
            distance, travel = (Decimal(0), Decimal(0)) if origin == dest else matrix[(origin, dest)]
            distances[vehicle] += distance
            pending[vehicle] = (dest, time + travel)
            at.pop(vehicle, None)
            depart_count += 1
        elif m := re.fullmatch(r'arrived at (\S+)', message):
            require(vehicle in pending, f'Arrival without departure at line {line_num}')
            require(pending.pop(vehicle) == (m[1], time), f'Arrival/OD travel-time mismatch at line {line_num}')
            at[vehicle] = (m[1], time)
            arrival_count += 1
        elif m := re.fullmatch(r'order (\S+) is (requested|picked up|delivered)(?: \((\S+) -> (\S+)\))?', message):
            item, kind, pickup, delivery = m.groups()
            require(item in items, f'Unknown item: {item}')
            require(item not in events[kind], f'Duplicate {kind}: {item}')
            spec = items[item]
            events[kind][item] = (time, vehicle)
            if kind == 'requested':
                require(vehicle is None and time == spec['release'], f'Request time mismatch: {item}')
                require((pickup, delivery) == (spec['pickup'], spec['delivery']), f'Request OD mismatch: {item}')
            else:
                require(vehicle in at and vehicle not in pending, f'Item event without arrival: {item}')
                location = spec['pickup'] if kind == 'picked up' else spec['delivery']
                require(at[vehicle][0] == location, f'Wrong service factory: {item}')
                if kind == 'picked up':
                    require(item in events['requested'] and events['requested'][item][0] <= time,
                            f'Pickup before request: {item}')
                else:
                    require(item in events['picked up'] and events['picked up'][item][0] <= at[vehicle][1],
                            f'Delivery arrival before pickup: {item}')
                    require(events['picked up'][item][1] == vehicle, f'Pickup/delivery vehicle mismatch: {item}')
                    completions.append((item, at[vehicle][1]))
        elif m := re.fullmatch(r'delivery time of order (\S+) has been set to ([\d.]+)', message):
            item, adjusted = m.groups()
            require(item in events['delivered'] and item not in events['adjusted'], f'Invalid adjustment: {item}')
            require(vehicle in at and events['delivered'][item][1] == vehicle, f'Adjustment vehicle mismatch: {item}')
            require(number(adjusted) == at[vehicle][1], f'Adjustment not equal to actual arrival: {item}')
            events['adjusted'][item] = (time, vehicle)
    require(starts == [Decimal(0)] and len(finishes) == 1 and finishes[0] == last_time, 'Invalid START/FINISH')
    require(not pending and depart_count == arrival_count, 'Unfinished vehicle legs')
    for kind, values in events.items():
        require(set(values) == set(items), f'Missing {kind} events: {sorted(set(items) - set(values))}')
    result = aggregate_score({item: spec['order'] for item, spec in items.items()}, deadlines, completions, distances)
    result.update(valid=True, finish_seconds=finishes[0], verified_legs=depart_count,
                  completion_definition='arrival at delivery factory, before queue/docking/unloading',
                  assumptions_and_limits=LIMITATIONS)
    return result


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    data = ROOT / 'examples/case_studies/dpdp/data'
    parser.add_argument('log', nargs='?', type=Path, default=ROOT / 'run_logs/dpdp_success.log')
    parser.add_argument('--orders', type=Path, default=data / 'instance_1/50_1.csv')
    parser.add_argument('--vehicles', type=Path, default=data / 'instance_1/vehicle_info_5.csv')
    parser.add_argument('--matrix', type=Path, default=data / 'route_info.csv')
    args = parser.parse_args()
    try:
        result = verify(args.log, args.orders, args.vehicles, args.matrix)
        result.update(verifier_version=VERIFIER_VERSION, reference_commit=REFERENCE_COMMIT,
                      python_executable=sys.executable, python_version=sys.version,
                      verifier_sha256=sha256(__file__),
                      input_sha256={str(p.resolve()): sha256(p) for p in (args.log, args.orders, args.vehicles, args.matrix)})
    except (ValueError, InvalidOperation, OSError, KeyError) as exc:
        print(json.dumps(dict(valid=False, error=str(exc)), indent=2))
        return 1
    # Decimal strings retain exact input precision, including repeating-score precision.
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == '__main__':
    sys.exit(main())
