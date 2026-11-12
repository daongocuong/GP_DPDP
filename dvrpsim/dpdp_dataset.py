"""Resolve and validate unmodified DPDP CSV inputs; no simulator execution."""
import csv
from decimal import Decimal
import math
from pathlib import Path
import random
import re
import sys
from dpdp_sealed import require_development_path

ROOT = Path(__file__).resolve().parent
CASE = ROOT/'examples/case_studies/dpdp'
SCHEMAS = {
    'factory': ['factory_id', 'longitude', 'latitude', 'port_num'],
    'route': ['route_code', 'start_factory_id', 'end_factory_id', 'distance', 'time'],
    'vehicle': ['car_num', 'capacity', 'operation_time', 'gps_id'],
    'order': ['order_id', 'q_standard', 'q_small', 'q_box', 'demand', 'creation_time',
              'committed_completion_time', 'load_time', 'unload_time', 'pickup_id', 'delivery_id'],
}


class DatasetError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise DatasetError(message)


def rows(path, kind):
    require_development_path(path)
    with Path(path).open(encoding='utf-8-sig', newline='') as handle:
        reader = csv.DictReader(handle)
        require(reader.fieldnames == SCHEMAS[kind], f'{path}: incorrect positional {kind} schema')
        result = list(reader)
    require(bool(result), f'{path}: empty CSV')
    require(all(None not in r and all(v is not None and v != '' for v in r.values()) for r in result),
            f'{path}: missing/extra cells')
    return result


def seconds(value):
    require(bool(re.fullmatch(r'\d{2}:\d{2}:\d{2}', value)), f'invalid time {value}')
    h, m, s = map(int, value.split(':'))
    require(0 <= h < 24 and 0 <= m < 60 and 0 <= s < 60, f'invalid time {value}')
    return h*3600+m*60+s


def positive_int(value, label, allow_zero=False):
    require(bool(re.fullmatch(r'\d+', value)), f'{label}: not an integer: {value}')
    number = int(value)
    require(number >= 0 if allow_zero else number > 0, f'{label}: invalid count {value}')
    return number


def resolve_inputs(instance=None, instance_directory=None, data_directory=None):
    if instance_directory is not None:
        if instance is not None:
            raise DatasetError('choose instance number or explicit directory')
        folder = Path(instance_directory).resolve()
    else:
        selected = 1 if instance is None else instance
        folder = (CASE/f'data/instance_{selected}').resolve()
    require_development_path(folder)
    require(folder.is_dir(), f'instance directory not found: {folder}')
    orders = sorted(p for p in folder.glob('*.csv') if not p.name.startswith('vehicle_info_'))
    vehicles = sorted(folder.glob('vehicle_info_*.csv'))
    require(len(orders) == 1 and len(vehicles) == 1, f'{folder}: expected exactly one order and one vehicle CSV')
    common = Path(data_directory).resolve() if data_directory else folder.parent
    factories, routes = common/'factory_info.csv', common/'route_info.csv'
    require(factories.is_file() and routes.is_file(), f'missing common matrices under {common}')
    match = re.fullmatch(r'instance_(\d+)', folder.name)
    return dict(instance=int(match[1]) if match else folder.name, directory=folder,
                orders=orders[0], vehicles=vehicles[0], factories=factories, routes=routes)


def validate_common(factories_path, routes_path):
    factories = rows(factories_path, 'factory')
    ids = [r['factory_id'] for r in factories]
    require(len(set(ids)) == len(ids), 'duplicate factory ID')
    for r in factories:
        positive_int(r['port_num'], 'ports')
        require(math.isfinite(float(r['longitude'])) and -180 <= float(r['longitude']) <= 180, 'invalid longitude')
        require(math.isfinite(float(r['latitude'])) and -90 <= float(r['latitude']) <= 90, 'invalid latitude')
    route_rows = rows(routes_path, 'route')
    pairs, codes = {}, set()
    factory_ids = set(ids)
    for r in route_rows:
        key = r['start_factory_id'], r['end_factory_id']
        require(set(key) <= factory_ids, f'unknown route factory: {key}')
        require(key not in pairs and r['route_code'] not in codes, 'duplicate OD/route ID')
        d = Decimal(r['distance'])
        require(d.is_finite() and d >= 0, 'invalid route distance')
        t = positive_int(r['time'], 'travel time', allow_zero=True)
        if key[0] == key[1]:
            require(d == 0 and t == 0, 'nonzero diagonal route')
        pairs[key] = (float(d), t)
        codes.add(r['route_code'])
    require(all((a,b) in pairs for a in ids for b in ids if a != b), 'incomplete directed route matrix')
    return factories, pairs


def validate_instance(folder, common_directory=None):
    paths = resolve_inputs(instance_directory=folder, data_directory=common_directory)
    factories, pairs = validate_common(paths['factories'], paths['routes'])
    factory_ids = {r['factory_id'] for r in factories}
    cars = rows(paths['vehicles'], 'vehicle')
    require(len({r['car_num'] for r in cars}) == len(cars), 'duplicate vehicle ID')
    capacities = {positive_int(r['capacity'], 'capacity') for r in cars}
    require(len(capacities) == 1, 'local DPDP guard requires homogeneous capacities')
    capacity = next(iter(capacities))
    for r in cars:
        positive_int(r['operation_time'], 'operation time')
    orders = rows(paths['orders'], 'order')
    require(len({r['order_id'] for r in orders}) == len(orders), 'duplicate order ID')
    expected, original_demands, release_times, due_times = {}, [], [], []
    for r in orders:
        require(r['pickup_id'] in factory_ids and r['delivery_id'] in factory_ids, f'unknown factory in order {r["order_id"]}')
        counts = [positive_int(r[k], k, allow_zero=True) for k in ('q_standard', 'q_small', 'q_box')]
        require(sum(counts) > 0, f'empty order {r["order_id"]}')
        quantities = [Decimal(1)]*counts[0] + [Decimal('.5')]*counts[1] + [Decimal('.25')]*counts[2]
        demand = sum(quantities)
        require(Decimal(r['demand']) == demand, f'order demand mismatch: {r["order_id"]}')
        require(all(0 < q <= capacity for q in quantities), 'indivisible item exceeds vehicle capacity')
        # The current loader derives duration from quantity; verify the input
        # duration columns agree, without editing or substituting their values.
        require(Decimal(r['load_time']) == demand*240 and Decimal(r['unload_time']) == demand*240,
                f'CSV/loader loading-duration mismatch: {r["order_id"]}')
        release, due = seconds(r['creation_time']), seconds(r['committed_completion_time'])
        if due < release:
            due += 86400
        require(due >= release, 'deadline preceding release after next-day conversion')
        release_times.append(release)
        due_times.append(due)
        original_demands.append(demand)
        for i, quantity in enumerate(quantities, 1):
            expected[f'{r["order_id"]}-{i}'] = dict(original_id=r['order_id'], quantity=float(quantity),
                release_date=release, due_date=due, pickup_location=r['pickup_id'], delivery_location=r['delivery_id'])
    if str(CASE) not in sys.path:
        sys.path.insert(0, str(CASE))
    from dpdp_problemdata import read_dpdp_problem
    state = random.getstate()
    try:
        loaded = read_dpdp_problem(str(paths['factories']), str(paths['routes']), str(paths['vehicles']), str(paths['orders']))
    finally:
        random.setstate(state)
    require(set(loaded['orders']) == set(expected), 'loader item-ID set mismatch')
    for item, wanted in expected.items():
        require(all(loaded['orders'][item][key] == value for key, value in wanted.items()), f'loader item mismatch: {item}')
    require(set(loaded['vehicles']) == {r['car_num'] for r in cars}, 'loader vehicle mismatch')
    require(set(loaded['locations']) == factory_ids, 'loader factory mismatch')
    require(all(loaded['distances'][k] == v[0] and loaded['travel_times'][k] == v[1] for k,v in pairs.items()), 'loader route mismatch')
    return dict(original_orders=len(orders), items_after_loader=len(loaded['orders']), vehicles=len(cars),
                factories=len(factories), route_pairs=len(pairs), capacity=capacity,
                oversized_original_orders=sum(d > capacity for d in original_demands),
                min_release_seconds=min(release_times), max_release_seconds=max(release_times),
                min_due_seconds=min(due_times), max_due_seconds=max(due_times),
                schema_valid=True, ids_valid=True, item_quantities_valid=True,
                time_fields_valid=True, duration_columns_match_loader=True, loader_verified=True)
