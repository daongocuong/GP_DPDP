"""Bounded reduced-scope GP/VNSME experiment for a fixed temporal window of instance 35.

The namespace and split are fixed before any objective is observed. A runner is
complete only after the simulator, execution contract, supervisor and independent
score audit all pass. Partial runs always record J=null.
"""
import argparse
import csv
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import math
from pathlib import Path
import shutil
import statistics
import subprocess
import sys
import time
import traceback
from types import SimpleNamespace

from dpdp_dataset import seconds
from dpdp_gp import load_tree
from dpdp_insertion import split_observed_orders
from dpdp_v3_supervisor import supervise

ROOT = Path(__file__).resolve().parent
BENCHMARK = ROOT/'third_party/huawei-xingtian/simulator/dpdp_competition/benchmark'
SOURCE = BENCHMARK/'instance_35'/'1000_3.csv'
VEHICLES = BENCHMARK/'instance_35'/'vehicle_info_50.csv'
FACTORIES = BENCHMARK/'factory_info.csv'
ROUTES = BENCHMARK/'route_info.csv'
FIXED_TREE_SOURCE = ROOT/'gp_runs/instance35_temporal_60_20_20_seed0_r01/pilot/gp/gp_perf_pilot_20261118_03/known_tree.json'
EXPERIMENT = ROOT/'gp_runs/instance35_reducedscope_20261118_window45_22495_r01'
WINDOW_FRACTION = Decimal('0.26')
TRAIN_RATIO = Decimal('0.60')
VALIDATION_CUMULATIVE_RATIO = Decimal('0.80')
SIMULATOR_SEED = 0
SLOT_SECONDS = 600
SUPERVISOR_WALL_SECONDS = 1800
RUNNER_WALL_GUARD_SECONDS = 1860
DECISION_HARD_SECONDS = 60
VNSME_SEARCH_BUDGET_SECONDS = 50
VNSME_SUBPROCESS_HARD_SECONDS = 59
SIMULATION_HORIZON_SECONDS = 604800
CONTRACT = 'dpdp-execution-commitment-v3'
USED_SOURCE_FILES = (
    'instance35_reduced_experiment.py', 'run_dpdp_insertion.py',
    'dpdp_dataset.py', 'dpdp_insertion.py', 'dpdp_feasibility.py',
    'dpdp_v3_supervisor.py', 'examples/case_studies/dpdp/dpdp_routing.py',
    'src/baselines/vnsme.py', 'third_party/vnsme/original/main_algorithm.java',
    'build_vnsme.py', 'verify_dpdp_score.py', 'instance35_gp_evolution.py',
)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_new(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8', newline='\n') as handle:
        json.dump(value, handle, indent=2, sort_keys=True, ensure_ascii=False, default=str,
                  allow_nan=False)
        handle.write('\n')
        handle.flush()


def _items_and_groups(rows):
    items = []
    for row in rows:
        release = seconds(row['creation_time'])
        due = seconds(row['committed_completion_time'])
        if due < release:
            due += 86400
        for quantity, column in ((1.0, 'q_standard'), (.5, 'q_small'), (.25, 'q_box')):
            for item_no in range(int(row[column])):
                items.append(SimpleNamespace(
                    id=f"{row['order_id']}-{quantity}-{item_no}",
                    original_id=row['order_id'], quantity=quantity,
                    pickup_location=SimpleNamespace(id=row['pickup_id']),
                    delivery_location=SimpleNamespace(id=row['delivery_id']),
                    due_date=due, release_date=release))
    groups = split_observed_orders(items, 15)
    return items, groups


def _partition_rows(all_rows, window_fraction=None):
    if window_fraction is None:
        window_fraction = WINDOW_FRACTION
    window_fraction = Decimal(window_fraction)
    if not window_fraction.is_finite() or not Decimal('0') < window_fraction <= Decimal('1'):
        raise ValueError('window fraction must be finite and in (0, 1]')
    releases = [seconds(row['creation_time']) for row in all_rows]
    source_start, source_end = min(releases), max(releases)
    window_start = Decimal(source_start)
    window_end = window_start + Decimal(source_end-source_start)*window_fraction
    train_boundary = window_start + (window_end-window_start)*TRAIN_RATIO
    validation_boundary = window_start + (window_end-window_start)*VALIDATION_CUMULATIVE_RATIO
    partitions = {'train': [], 'validation': [], 'test': []}
    for row, release in zip(all_rows, releases):
        t = Decimal(release)
        if t < window_start or t > window_end:
            continue
        name = 'train' if t < train_boundary else 'validation' if t < validation_boundary else 'test'
        partitions[name].append(row)
    if any(not rows for rows in partitions.values()):
        raise ValueError('fixed reduced temporal window produced an empty partition')
    release_owners = {}
    for name, rows in partitions.items():
        for row in rows:
            release = seconds(row['creation_time'])
            previous = release_owners.setdefault(release, name)
            if previous != name:
                raise ValueError(f'release tie split across partitions at {release}')
    selected = sum(map(len, partitions.values()))
    if selected != sum(1 for t in releases if Decimal(source_start) <= Decimal(t) <= window_end):
        raise ValueError('partition lost or duplicated selected source rows')
    return partitions, dict(source_start=window_start, window_end=window_end,
        train_validation_boundary=train_boundary, validation_test_boundary=validation_boundary,
        source_end=Decimal(source_end), source_release_span=Decimal(source_end-source_start))


def _partition_summary(name, rows, folder):
    times = [seconds(row['creation_time']) for row in rows]
    items, groups = _items_and_groups(rows)
    slack = []
    demand = {}
    for row, release in zip(rows, times):
        due = seconds(row['committed_completion_time'])
        if due < release:
            due += 86400
        slack.append(due-release)
        key = row['demand']
        demand[key] = demand.get(key, 0)+1
    slack.sort()
    return dict(name=name, original_orders=len(rows), item_count=len(items),
        post_lot_groups_static=len(groups), vehicle_count=50,
        first_release_seconds=min(times), last_release_seconds=max(times),
        occupied_original_600s_slots=sorted({t//SLOT_SECONDS for t in times}),
        occupied_slot_count=len({t//SLOT_SECONDS for t in times}),
        demand_distribution=dict(sorted(demand.items(), key=lambda pair: float(pair[0]))),
        deadline_slack_seconds=dict(min=min(slack), median=statistics.median(slack),
            p95=slack[math.ceil(.95*len(slack))-1], max=max(slack)),
        orders_sha256=sha(folder/'orders.csv'), vehicles_sha256=sha(folder/'vehicle_info_50.csv'))


def prepare(experiment_dir=EXPERIMENT, window_fraction=None):
    experiment_dir = Path(experiment_dir).resolve()
    if window_fraction is None:
        window_fraction = WINDOW_FRACTION
    window_fraction = Decimal(window_fraction)
    if experiment_dir.exists():
        raise FileExistsError(f'preserving existing reduced experiment: {experiment_dir}')
    for path in (SOURCE, VEHICLES, FACTORIES, ROUTES, FIXED_TREE_SOURCE):
        if not path.is_file():
            raise FileNotFoundError(path)
    source_rows = list(csv.DictReader(SOURCE.open(encoding='utf-8-sig', newline='')))
    if len(source_rows) != 1000 or len({row['order_id'] for row in source_rows}) != 1000:
        raise ValueError('instance35/1000_3.csv must contain 1000 unique orders')
    vehicle_rows = list(csv.DictReader(VEHICLES.open(encoding='utf-8-sig', newline='')))
    if len(vehicle_rows) != 50:
        raise ValueError('instance35 vehicle CSV must contain exactly 50 vehicles')
    tree, tree_payload = load_tree(FIXED_TREE_SOURCE)
    del tree
    partitions, bounds = _partition_rows(source_rows, window_fraction)
    experiment_dir.mkdir(parents=True, exist_ok=False)
    (experiment_dir/'data').mkdir()
    (experiment_dir/'trees').mkdir()
    shutil.copyfile(FIXED_TREE_SOURCE, experiment_dir/'trees'/'fixed_gp_tree.json')
    summaries = {}
    for name, part in partitions.items():
        folder = experiment_dir/'data'/name
        folder.mkdir()
        with (folder/'orders.csv').open('x', encoding='utf-8', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=list(source_rows[0]))
            writer.writeheader()
            writer.writerows(part)
        shutil.copyfile(VEHICLES, folder/'vehicle_info_50.csv')
        summaries[name] = _partition_summary(name, part, folder)
    source_hashes = {label: sha(path) for label, path in (
        ('orders_1000_3', SOURCE), ('vehicles_50', VEHICLES),
        ('factory_info', FACTORIES), ('route_info', ROUTES))}
    config = dict(schema='instance35-reduced-scope-temporal-v1',
        scope_label='REDUCED_SCOPE_EXPERIMENT_NOT_FULL_INSTANCE_35',
        selection_rule=f'first {window_fraction*100}% of source release-time span; fixed before any J in this namespace, selected using order counts and predeclared runtime feasibility',
        source_order_count=1000, selected_order_count=sum(x['original_orders'] for x in summaries.values()),
        source_window=dict(start_seconds=str(bounds['source_start']),
            end_seconds=str(bounds['window_end']), end_inclusive=True,
            source_first_release_seconds=str(bounds['source_start']),
            source_last_release_seconds=str(bounds['source_end']),
            source_release_span_seconds=str(bounds['source_release_span']),
            fraction_of_source_release_span=str(window_fraction)),
        split=dict(train_ratio=str(TRAIN_RATIO), validation_ratio='0.20', test_ratio='0.20',
            train_validation_boundary_seconds=str(bounds['train_validation_boundary']),
            validation_test_boundary_seconds=str(bounds['validation_test_boundary']),
            intervals='train: [window_start,b1); validation: [b1,b2); test: [b2,window_end]',
            release_ties='all rows with identical release seconds are assigned to the same interval',
            time_shift_seconds=0, time_slot_seconds=SLOT_SECONDS,
            partitions_are_independent_rollouts=True, reset_fleet_each_partition=True,
            carry_over_orders=False),
        partitions=summaries, source_sha256=source_hashes,
        tree=dict(path='trees/fixed_gp_tree.json', source_run=str(FIXED_TREE_SOURCE.relative_to(ROOT)),
            sha256=sha(experiment_dir/'trees'/'fixed_gp_tree.json'), expression=tree_payload['expression']),
        execution=dict(simulator_seed=SIMULATOR_SEED, contract_version=CONTRACT,
            supervisor_wall_seconds=SUPERVISOR_WALL_SECONDS,
            decision_hard_timeout_seconds=DECISION_HARD_SECONDS,
            runner_wall_guard_seconds=RUNNER_WALL_GUARD_SECONDS,
            simulation_horizon_seconds=SIMULATION_HORIZON_SECONDS,
            gp_feasibility_profile=False,
            gp_progress_trace=True,
            vnsme_internal_search_budget_seconds=VNSME_SEARCH_BUDGET_SECONDS,
            vnsme_subprocess_hard_timeout_seconds=VNSME_SUBPROCESS_HARD_SECONDS,
            stopping_comparison='same seed, partition, full-completion contract, 60s decision supervisor hard limit and 1800s stage wall limit; VNSME additionally has a 50s cooperative internal search budget; no claim of identical internal compute budget'),
        objective='runner verify_dpdp_score independent benchmark total_score; result J set only on complete valid run',
        source_revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        prepared_at_utc=datetime.now(timezone.utc).isoformat())
    canonical = json.dumps(config, sort_keys=True, separators=(',', ':'), ensure_ascii=False,
                           allow_nan=False, default=str).encode('utf-8')
    config['config_sha256'] = hashlib.sha256(canonical).hexdigest()
    config_path = experiment_dir/'experiment_config.json'
    write_new(config_path, config)
    return config


def _trace_matches_result(events, result):
    if not isinstance(result, dict) or not isinstance(events, list):
        return False
    expected_index = 1
    pending = None
    for event in events:
        kind = event.get('event')
        if kind == 'START':
            if pending is not None or event.get('decision_index') != expected_index:
                return False
            pending = expected_index
        elif kind == 'PROGRESS':
            if pending is None or event.get('decision_index') != pending:
                return False
        elif kind == 'END':
            if (pending is None or event.get('decision_index') != pending
                    or event.get('status') != 'completed'):
                return False
            expected_index += 1
            pending = None
        else:
            return False
    return pending is None and result.get('decision_count') == expected_index - 1


def _valid_completion(outcome, result, independent, events):
    score = result.get('score') if isinstance(result, dict) else None
    return (outcome.get('state') == 'EXITED' and outcome.get('exit_code') == 0
        and outcome.get('valid_supervision') is True
        and outcome.get('remaining_job_processes') == []
        and result is not None and result.get('status') == 'COMPLETED'
        and result.get('valid') is True and result.get('contract_complete') is True
        and _trace_matches_result(events, result)
        and isinstance(score, dict) and score.get('total_score') is not None
        and independent is not None
        and str(score['total_score']) == str(independent['total_score']))


def run_rollout(run_id, algorithm, partition, tree_path=None, experiment_dir=EXPERIMENT):
    if algorithm not in ('gp', 'vnsme') or partition not in ('train', 'validation', 'test'):
        raise ValueError('unsupported algorithm or partition')
    if sys.platform != 'win32':
        raise RuntimeError('native Windows Job Object supervision is mandatory')
    if Path(sys.executable).resolve() != (ROOT/'.venv/Scripts/python.exe').resolve():
        raise RuntimeError('use the repository .venv/Scripts/python.exe')
    experiment_dir = Path(experiment_dir).resolve()
    config = json.loads((experiment_dir/'experiment_config.json').read_text(encoding='utf-8'))
    execution = config.get('execution', {})
    configured_supervisor_wall_seconds = float(execution.get('supervisor_wall_seconds', SUPERVISOR_WALL_SECONDS))
    task_deadline_utc = execution.get('task_deadline_utc')
    task_deadline_timestamp = None
    if task_deadline_utc is not None:
        task_deadline = datetime.fromisoformat(task_deadline_utc.replace('Z', '+00:00'))
        if task_deadline.tzinfo is None:
            raise ValueError('task deadline must include a UTC offset')
        task_deadline_timestamp = task_deadline.timestamp()
        remaining = task_deadline_timestamp - time.time()
        if remaining <= 0:
            raise TimeoutError('absolute task deadline reached before rollout')
        supervisor_wall_seconds = min(configured_supervisor_wall_seconds, remaining)
    else:
        supervisor_wall_seconds = configured_supervisor_wall_seconds
    runner_wall_guard_seconds = int(execution.get('runner_wall_guard_seconds', RUNNER_WALL_GUARD_SECONDS))
    decision_hard_seconds = int(execution.get('decision_hard_timeout_seconds', DECISION_HARD_SECONDS))
    dispatch_step_seconds = int(execution.get('dispatch_step_seconds', 600))
    simulation_horizon_seconds = int(execution.get('simulation_horizon_seconds', SIMULATION_HORIZON_SECONDS))
    if dispatch_step_seconds != 600:
        raise ValueError('this runner build is configured for a 600-second simulation dispatch slot')
    vnsme_search_budget_seconds = int(execution.get(
        'vnsme_internal_search_budget_seconds', VNSME_SEARCH_BUDGET_SECONDS))
    vnsme_subprocess_hard_seconds = int(execution.get(
        'vnsme_subprocess_hard_timeout_seconds', VNSME_SUBPROCESS_HARD_SECONDS))
    input_dir = experiment_dir/'data'/partition
    if not input_dir.is_dir():
        raise FileNotFoundError(input_dir)
    if algorithm == 'gp':
        tree_path = Path(tree_path or experiment_dir/'trees'/'fixed_gp_tree.json').resolve()
        load_tree(tree_path)
    output = experiment_dir/'runs'/algorithm/partition/run_id
    if output.exists():
        raise FileExistsError(f'preserving existing run artifact: {output}')
    runner_dir, supervisor_dir = output/'runner', output/'supervisor'
    stage_trace = output/'stage_trace.jsonl'
    run_config = dict(run_id=run_id, algorithm=algorithm, partition=partition,
        experiment_config_sha256=config['config_sha256'],
        dataset_sha256=config['partitions'][partition]['orders_sha256'],
        vehicle_sha256=config['partitions'][partition]['vehicles_sha256'],
        simulator_seed=SIMULATOR_SEED, tree_sha256=sha(tree_path) if algorithm == 'gp' else None,
        code_sha256={name: sha(ROOT/name) for name in USED_SOURCE_FILES},
        vnsme_build_manifest_sha256=(sha(ROOT/'third_party/vnsme/build_manifest.json')
            if algorithm == 'vnsme' else None),
        supervisor_wall_seconds=supervisor_wall_seconds,
        decision_hard_timeout_seconds=decision_hard_seconds,
        dispatch_step_seconds=dispatch_step_seconds,
        runner_wall_guard_seconds=runner_wall_guard_seconds,
        simulation_horizon_seconds=simulation_horizon_seconds,
        vnsme_internal_search_budget_seconds=(vnsme_search_budget_seconds if algorithm == 'vnsme' else None),
        vnsme_subprocess_hard_timeout_seconds=(vnsme_subprocess_hard_seconds if algorithm == 'vnsme' else None),
        configured_supervisor_wall_seconds=configured_supervisor_wall_seconds,
        task_deadline_utc=task_deadline_utc,
        stage_trace=str(stage_trace.resolve()))
    command = [str(ROOT/'.venv/Scripts/python.exe'), '-B', str(ROOT/'run_dpdp_insertion.py'),
        '--policy', algorithm, '--contract-version', CONTRACT,
        '--instance-directory', str(input_dir.resolve()), '--data-directory', str(BENCHMARK.resolve()),
        '--seed', str(SIMULATOR_SEED), '--wall-seconds', str(runner_wall_guard_seconds),
        '--max-simulation-seconds', str(simulation_horizon_seconds),
        '--output', str(runner_dir.resolve()), '--stage-trace', str(stage_trace.resolve()),
        '--stage-partition', partition]
    if algorithm == 'gp':
        command += ['--tree', str(tree_path), '--no-feasibility-profile', '--decision-progress']
    else:
        command += ['--vnsme-search-budget-seconds', str(vnsme_search_budget_seconds),
                    '--vnsme-epoch-seconds', str(vnsme_subprocess_hard_seconds)]
    started = time.monotonic()
    if task_deadline_timestamp is not None:
        remaining = task_deadline_timestamp - time.time()
        if remaining <= 0:
            raise TimeoutError('absolute task deadline reached before rollout launch')
        supervisor_wall_seconds = min(configured_supervisor_wall_seconds, remaining)
        run_config['supervisor_wall_seconds'] = supervisor_wall_seconds
    output.mkdir(parents=True, exist_ok=False)
    stage_trace.open('x', encoding='utf-8').close()
    write_new(output/'run_config.json', run_config)
    supervisor_error = None
    try:
        outcome = supervise(command, supervisor_dir, supervisor_wall_seconds,
            interval=.05, gap_limit=3, decision_trace=stage_trace,
            decision_timeout=decision_hard_seconds, partition=partition,
            algorithm=algorithm, stage_started_monotonic=started)
    except BaseException as exc:
        outcome = dict(state='SUPERVISOR_ERROR', exit_code=None, valid_supervision=False,
                       remaining_job_processes=None, stop_event=None)
        supervisor_error = f'{type(exc).__name__}: {exc}'
    events = []
    for line_no, line in enumerate(stage_trace.read_text(encoding='utf-8').splitlines(), 1):
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            events.append(dict(event='TRACE_PARSE_ERROR', line=line_no))
    runner_result_path = runner_dir/'result.json'
    runner_result = None
    if runner_result_path.is_file():
        try:
            runner_result = json.loads(runner_result_path.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError):
            pass
    independent = None
    audit_error = None
    if (runner_result is not None and runner_result.get('valid') is True
            and runner_result.get('status') == 'COMPLETED'
            and (runner_dir/'simulation.log').is_file()):
        try:
            from verify_dpdp_score import verify
            independent = verify(runner_dir/'simulation.log', input_dir/'orders.csv',
                                 input_dir/'vehicle_info_50.csv', ROUTES)
            write_new(runner_dir/'independent_score.json', independent)
        except BaseException as exc:
            audit_error = f'{type(exc).__name__}: {exc}'
    complete = _valid_completion(outcome, runner_result, independent, events)
    timeout = outcome.get('state') in ('TIMEOUT', 'DECISION_TIMEOUT') or any(
        row.get('event') == 'TIMEOUT' for row in events)
    status = 'COMPLETED' if complete else 'TIMEOUT' if timeout else 'INVALID' if outcome.get('state') == 'EXITED' else 'ERROR'
    end_events = [row for row in events if row.get('event') == 'END' and row.get('status') == 'completed']
    start_events = [row for row in events if row.get('event') == 'START']
    record = dict(run_id=run_id, algorithm=algorithm, partition=partition,
        status=status, valid=complete, partial=not complete, incomplete=not complete,
        J=str(independent['total_score']) if complete else None,
        score={k:str(independent[k]) for k in ('total_distance_km','total_tardiness_seconds','total_score')} if complete else None,
        runner_result_present=runner_result is not None,
        runner_error=(runner_result.get('error') if runner_result else None),
        independent_audit_error=audit_error,
        decision_starts=len(start_events), completed_decisions=len(end_events),
        final_simulation_seconds=(end_events[-1].get('simulation_seconds') if end_events else
            next((row.get('simulation_seconds') for row in reversed(events)
                  if row.get('simulation_seconds') is not None), None)),
        supervisor_state=outcome.get('state'), supervisor_exit_code=outcome.get('exit_code'),
        valid_supervision=outcome.get('valid_supervision'),
        remaining_job_processes=outcome.get('remaining_job_processes'),
        stop_event=outcome.get('stop_event'), supervisor_error=supervisor_error,
        supervisor_elapsed_seconds=(json.loads((supervisor_dir/'supervision.json').read_text(encoding='utf-8')).get('elapsed_seconds')
            if (supervisor_dir/'supervision.json').is_file() else None),
        runner_result_path=str(runner_result_path), stage_trace_path=str(stage_trace),
        wall_seconds=time.monotonic()-started,
        completion_rule='COMPLETED only with valid runner result, completed execution contract, supervisor EXITED/0/clean Job Object and matching independent J')
    write_new(output/'stage_result.json', record)
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    prepare_cmd = sub.add_parser('prepare')
    prepare_cmd.add_argument('--experiment-dir', type=Path, default=EXPERIMENT)
    prepare_cmd.add_argument('--window-fraction', type=Decimal, default=WINDOW_FRACTION)
    run = sub.add_parser('run')
    run.add_argument('--algorithm', choices=('gp','vnsme'), required=True)
    run.add_argument('--partition', choices=('train','validation','test'), required=True)
    run.add_argument('--run-id', required=True)
    run.add_argument('--tree', type=Path)
    run.add_argument('--experiment-dir', type=Path, default=EXPERIMENT)
    args = parser.parse_args()
    if args.action == 'prepare':
        result = prepare(args.experiment_dir, args.window_fraction)
    else:
        result = run_rollout(args.run_id, args.algorithm, args.partition,
                             args.tree, args.experiment_dir)
    print(json.dumps(result, indent=2, default=str))


if __name__ == '__main__':
    main()
