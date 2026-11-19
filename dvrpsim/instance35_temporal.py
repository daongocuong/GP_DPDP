"""Prepare and preflight the fixed temporal instance-35 DPDP pilot; no rollout runs here."""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import shutil
import statistics
import sys
from types import SimpleNamespace

from dpdp_dataset import rows, seconds, validate_instance
from dpdp_insertion import split_observed_orders

ROOT = Path(__file__).resolve().parent
BENCHMARK = ROOT/'third_party/huawei-xingtian/simulator/dpdp_competition/benchmark'
SOURCE_DIR = BENCHMARK/'instance_35'
RUN = ROOT/'gp_runs/instance35_temporal_60_20_20_seed0_r01'
SLOTS = 600
RATIOS = (0.60, 0.20, 0.20)
INSPECTION_REFERENCE_TIMEOUTS = dict(smoke_wall_seconds=360, rollout_wall_seconds=1800,
    vnsme_search_seconds=50, decision_hard_seconds=60)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def source_files():
    orders = SOURCE_DIR/'1000_3.csv'
    vehicles = SOURCE_DIR/'vehicle_info_50.csv'
    return orders, vehicles, BENCHMARK/'factory_info.csv', BENCHMARK/'route_info.csv'


def inspect():
    orders_path, vehicles_path, factories_path, routes_path = source_files()
    orders = rows(orders_path, 'order')
    vehicles = rows(vehicles_path, 'vehicle')
    factories = rows(factories_path, 'factory')
    releases = [seconds(r['creation_time']) for r in orders]
    lo, hi = min(releases), max(releases)
    cuts = [lo + (hi-lo)*RATIOS[0], lo + (hi-lo)*(RATIOS[0]+RATIOS[1])]
    assignments = [0 if t < cuts[0] else 1 if t < cuts[1] else 2 for t in releases]
    demand = [float(r['demand']) for r in orders]
    slack = []
    item_count = 0
    active_factories = set()
    slot_counts = {}
    for r, t, split in zip(orders, releases, assignments):
        due = seconds(r['committed_completion_time'])
        if due < t:
            due += 86400
        slack.append(due-t)
        item_count += sum(int(r[k]) for k in ('q_standard','q_small','q_box'))
        active_factories.update((r['pickup_id'], r['delivery_id']))
        slot_counts[t//SLOTS] = slot_counts.get(t//SLOTS, 0)+1
    all_factory_ids = {r['factory_id'] for r in factories}
    if not active_factories <= all_factory_ids:
        raise ValueError('orders reference unknown factory')
    slot_values = list(slot_counts.values())
    def summary(values):
        return dict(min=min(values), median=statistics.median(values),
                    p95=sorted(values)[math.ceil(.95*len(values))-1], max=max(values))
    split_rows = {}
    for index, name in enumerate(('train','validation','test')):
        selected = [r for r, a in zip(orders, assignments) if a == index]
        items = []
        for r in selected:
            release=seconds(r['creation_time']);due=seconds(r['committed_completion_time'])
            if due < release: due += 86400
            for qty, count in ((1,int(r['q_standard'])),(.5,int(r['q_small'])),(.25,int(r['q_box']))):
                for item_no in range(count):
                    items.append(SimpleNamespace(id=f"{r['order_id']}-{qty}-{item_no}",
                        original_id=r['order_id'],quantity=qty,
                        pickup_location=SimpleNamespace(id=r['pickup_id']),
                        delivery_location=SimpleNamespace(id=r['delivery_id']),
                        due_date=due,release_date=release))
        groups=split_observed_orders(items,15)
        split_rows[name] = dict(orders=len(selected),
                                start_seconds=min(seconds(r['creation_time']) for r in selected),
                                end_seconds=max(seconds(r['creation_time']) for r in selected),
                                occupied_slots=len({seconds(r['creation_time'])//SLOTS for r in selected}),
                                post_lot_groups=len(groups),
                                time_boundary_start=lo if index==0 else math.floor(cuts[index-1])+1,
                                time_boundary_end=(math.floor(cuts[index]) if index<2 else hi))
    return dict(instance=35, order_csv=orders_path.name, order_count=len(orders), item_count=item_count,
        vehicle_count=len(vehicles), network_factory_count=len(factories),
        active_factory_count=len(active_factories), first_release_seconds=lo,
        last_release_seconds=hi, release_span_seconds=hi-lo,
        total_time_slots=len(slot_counts), orders_per_occupied_slot=dict(mean=statistics.mean(slot_values),
            **summary(slot_values)), demand_distribution={str(k):demand.count(k) for k in sorted(set(demand))},
        deadline_slack_seconds=summary(slack), temporal_split=split_rows,
        split_ratios=RATIOS, time_slot_seconds=SLOTS,
        source_sha256={str(p.relative_to(ROOT)):digest(p) for p in
                       (orders_path,vehicles_path,factories_path,routes_path)},
        inspection_reference_timeouts_not_applied=INSPECTION_REFERENCE_TIMEOUTS)


def preflight():
    if sys.platform != 'win32':
        raise RuntimeError('pilot preflight requires native Windows')
    if Path(sys.executable).resolve() != (ROOT/'.venv/Scripts/python.exe').resolve():
        raise RuntimeError('use repository .venv/Scripts/python.exe')
    report = inspect()
    validated = validate_instance(SOURCE_DIR, BENCHMARK)
    if validated['original_orders'] != 1000 or report['vehicle_count'] != 50:
        raise ValueError('instance 35 source count/fleet mismatch')
    import dpdp_contract, dpdp_feasibility, dpdp_insertion, dpdp_schedule
    import dpdp_gp, dpdp_v3_supervisor, run_dpdp_insertion
    from baselines import vnsme
    report.update(status='PREFLIGHT_PASS', python=sys.version, executable=sys.executable,
        modules_imported=['dpdp_contract','dpdp_feasibility','dpdp_insertion','dpdp_schedule',
                          'dpdp_gp','dpdp_v3_supervisor','run_dpdp_insertion','baselines.vnsme'],
        loader_validation=validated)
    return report


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('action',choices=('inspect','preflight','prepare'))
    args=parser.parse_args()
    report=preflight() if args.action=='preflight' else inspect()
    if args.action=='prepare':
        if RUN.exists():
            raise FileExistsError(f'preserving existing experiment directory: {RUN}')
        RUN.mkdir(parents=True)
        (RUN/'config.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2,default=str))


if __name__=='__main__':
    main()
