"""Locked temporal 100-order GP feasibility run and guarded continuation.

The prepare and gate actions never evaluate Validation or Test.  The continue
action is the explicit, separate entry point for G1-G9, post-training
Validation, then GP/VNSME Test.
"""
import argparse
import csv
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import random
import statistics
import subprocess
import sys
import time

from dpdp_contract import EXECUTION_CONTRACT
from dpdp_dataset import rows, seconds, validate_instance
from dpdp_gp import (FEATURES, Limits, breed, canonical, load_tree, random_tree,
                     save_tree, tree_hash, validate_tree)
from dpdp_v3_supervisor import supervise

ROOT = Path(__file__).resolve().parent
BENCHMARK = ROOT/'third_party/huawei-xingtian/simulator/dpdp_competition/benchmark'
DATASET_ROOT = ROOT/'datasets/xingtian/e4ef3a1c92d19d1d08c3ef0e2156b6fecefdbe04'
SOURCE_INVENTORY = DATASET_ROOT/'source_manifest.json'
RUN = ROOT/'gp_runs/dpdp_100_orders_pop10_feasibility_seed42_r01'
TIME_SLOT_SECONDS = 600
SIMULATOR_HORIZON_SECONDS = 7*86400
RUNNER_WALL_SECONDS = 3660
LIMITS = Limits(max_depth=5, max_nodes=63)
SPLITS = ('train', 'validation', 'test')
SOURCE_FILES = (
    'gp_dpdp_100_feasibility.py', 'dpdp_gp.py', 'dpdp_dataset.py',
    'dpdp_contract.py', 'protocols/dpdp_execution_commitment_v3.json',
    'dpdp_feasibility.py', 'dpdp_schedule.py', 'dpdp_insertion.py',
    'dpdp_v3_trace.py', 'dpdp_v3_supervisor.py',
    'dpdp_v3_independent_audit.py', 'run_dpdp_insertion.py',
    'verify_dpdp_score.py', 'examples/case_studies/dpdp/dpdp_main.py',
    'examples/case_studies/dpdp/dpdp_problemdata.py',
    'examples/case_studies/dpdp/dpdp_routing.py',
    'src/baselines/vnsme.py', 'build_vnsme.py',
    'third_party/vnsme/build_manifest.json',
    'third_party/vnsme/original/main_algorithm.java',
)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical_json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=False, allow_nan=False, default=str)


def write_new(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8', newline='\n') as handle:
        json.dump(value, handle, indent=2, sort_keys=True, ensure_ascii=False,
                  allow_nan=False, default=str)
        handle.write('\n')
        handle.flush()
        os.fsync(handle.fileno())


def write_replace(path, value):
    path = Path(path)
    temp = path.with_name(path.name+'.tmp')
    with temp.open('w', encoding='utf-8', newline='\n') as handle:
        json.dump(value, handle, indent=2, sort_keys=True, ensure_ascii=False,
                  allow_nan=False, default=str)
        handle.write('\n')
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp, path)


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def item_count(order_rows):
    return sum(sum(int(row[key]) for key in ('q_standard', 'q_small', 'q_box'))
               for row in order_rows)


def inventory_100_order_instances():
    """Use pinned inventory for candidates; read only the selected original CSV."""
    inventory = read_json(SOURCE_INVENTORY)
    if (inventory.get('all_verified') is not True
            or inventory.get('commit') != 'e4ef3a1c92d19d1d08c3ef0e2156b6fecefdbe04'):
        raise ValueError('pinned Xingtian source inventory is not verified')
    records = []
    # instance_1 is not in this extracted source manifest; its original filename
    # itself declares the benchmark size (50_1.csv). No higher-ID CSV is opened.
    first = BENCHMARK/'instance_1'/'50_1.csv'
    if first.is_file():
        records.append(dict(instance_id=1, original_orders=50,
                            evidence='original benchmark filename 50_1.csv'))
    for raw_id, info in inventory['instances'].items():
        records.append(dict(instance_id=int(raw_id),
                            original_orders=int(info['original_orders']),
                            evidence='verified source_manifest.json inventory'))
    records.sort(key=lambda row: row['instance_id'])
    selected = next((row for row in records if row['original_orders'] == 100), None)
    if selected is None:
        raise ValueError('no verified original 100-order instance found')
    return selected, records


def initial_population(seed=42, size=10, depths=(2, 3, 4), limits=LIMITS):
    """Ramped full/grow initialization used by the existing instance64 runner."""
    rng = random.Random(seed)
    result, details = [], []
    for member in range(size):
        target = depths[member % len(depths)]
        full = member % 2 == 0
        attempts = 0
        tree = None
        while attempts < 100:
            attempts += 1
            candidate = random_tree(rng, target, full=full)
            try:
                nodes, actual_depth = validate_tree(candidate, limits)
            except ValueError:
                continue
            if actual_depth == target:
                tree = candidate
                break
        if tree is None:
            tree = random_tree(rng, target, full=True)
            nodes, actual_depth = validate_tree(tree, limits)
            if actual_depth != target:
                raise ValueError('full-tree fallback did not meet requested initial depth')
            fallback = True
        else:
            fallback = False
        result.append(tree)
        details.append(dict(member=member, target_depth=target, full_method=full,
                            attempts=attempts, fallback=fallback,
                            expression=tree.text(), depth=actual_depth, nodes=nodes,
                            canonical=canonical(tree), canonical_sha256=tree_hash(tree)))
    return rng, result, details


def first_unique_members(population):
    seen, selected = set(), []
    for member, tree in enumerate(population):
        digest = tree_hash(tree)
        if digest in seen:
            continue
        seen.add(digest)
        selected.append(member)
        if len(selected) == 4:
            break
    return selected


def _slot_histogram(order_rows):
    counts = {}
    for row in order_rows:
        slot = seconds(row['creation_time'])//TIME_SLOT_SECONDS
        counts[slot] = counts.get(slot, 0)+1
    return {str(slot): counts[slot] for slot in sorted(counts)}


def _release_stats(order_rows):
    releases = [seconds(row['creation_time']) for row in order_rows]
    sorted_releases = sorted(releases)
    by_second = {}
    for release in releases:
        by_second[release] = by_second.get(release, 0)+1
    slot_values = list(_slot_histogram(order_rows).values())
    percentile = lambda values, p: sorted(values)[max(0, math.ceil(p*len(values))-1)]
    peak_second, peak_count = min(by_second.items(), key=lambda item: (-item[1], item[0]))
    return dict(
        min_seconds=min(releases), max_seconds=max(releases),
        min_hhmmss=order_rows[releases.index(min(releases))]['creation_time'],
        max_hhmmss=order_rows[releases.index(max(releases))]['creation_time'],
        median_seconds=statistics.median(sorted_releases),
        p95_seconds=percentile(sorted_releases, .95),
        unique_release_seconds=len(by_second),
        orders_per_600_second_slot=_slot_histogram(order_rows),
        occupied_600_second_slots=len(slot_values),
        orders_per_occupied_slot=dict(min=min(slot_values),
            median=statistics.median(slot_values), p95=percentile(slot_values, .95),
            max=max(slot_values)),
        maximum_simultaneous_orders=peak_count,
        maximum_simultaneous_release_seconds=peak_second,
        maximum_simultaneous_release_hhmmss=order_rows[releases.index(peak_second)]['creation_time'],
    )


def split_source_orders(order_rows):
    releases = [seconds(row['creation_time']) for row in order_rows]
    start, end = min(releases), max(releases)
    span = Decimal(end-start)
    first_cut = Decimal(start)+span*Decimal('0.60')
    second_cut = Decimal(start)+span*Decimal('0.80')
    partitions = {name: [] for name in SPLITS}
    for row, release in zip(order_rows, releases):
        value = Decimal(release)
        name = 'train' if value < first_cut else 'validation' if value < second_cut else 'test'
        partitions[name].append(row)
    if any(not partitions[name] for name in SPLITS):
        raise ValueError('temporal split produced an empty partition')
    owners = {}
    for name, part in partitions.items():
        for row in part:
            release = seconds(row['creation_time'])
            prior = owners.setdefault(release, name)
            if prior != name:
                raise ValueError(f'identical release timestamps split across partitions: {release}')
    if sum(map(len, partitions.values())) != len(order_rows):
        raise ValueError('temporal split lost or duplicated original orders')
    return partitions, dict(source_start_seconds=start, source_end_seconds=end,
                            release_span_seconds=end-start,
                            train_end_exclusive=str(first_cut),
                            validation_end_exclusive=str(second_cut),
                            intervals=dict(train=f'[{start}, {first_cut})',
                                           validation=f'[{first_cut}, {second_cut})',
                                           test=f'[{second_cut}, {end}]'))


def _partition_summary(name, part, folder, loader_result):
    return dict(name=name, original_orders=len(part), items=loader_result['items_after_loader'],
                vehicles=loader_result['vehicles'], factories=loader_result['factories'],
                occupied_600_second_slots=len(_slot_histogram(part)),
                orders_per_600_second_slot=_slot_histogram(part),
                maximum_simultaneous_orders=_release_stats(part)['maximum_simultaneous_orders'],
                release_distribution=_release_stats(part),
                order_ids=[row['order_id'] for row in part],
                orders_sha256=sha(folder/'orders.csv'),
                vehicles_sha256=sha(folder/'vehicle_info_5.csv'))


def _source_paths(instance_id):
    folder = BENCHMARK/f'instance_{instance_id}'
    order_files = [path for path in folder.glob('*.csv') if not path.name.startswith('vehicle_info_')]
    vehicle_files = list(folder.glob('vehicle_info_*.csv'))
    if len(order_files) != 1 or len(vehicle_files) != 1:
        raise ValueError(f'instance_{instance_id} must be one original order file and one fleet file')
    return dict(orders=order_files[0], vehicles=vehicle_files[0],
                factories=BENCHMARK/'factory_info.csv', routes=BENCHMARK/'route_info.csv')


def prepare(run_dir=RUN):
    run_dir = Path(run_dir).resolve()
    if run_dir.exists():
        raise FileExistsError(f'preserving existing feasibility namespace: {run_dir}')
    selected, inventory = inventory_100_order_instances()
    instance_id = selected['instance_id']
    source = _source_paths(instance_id)
    order_rows = rows(source['orders'], 'order')
    if len(order_rows) != 100 or len({row['order_id'] for row in order_rows}) != 100:
        raise ValueError('selected original source must contain exactly 100 unique orders')
    source_validation = validate_instance(source['orders'].parent, BENCHMARK)
    if source_validation['original_orders'] != 100:
        raise ValueError('selected raw benchmark loader did not return 100 original orders')
    manifest_inventory = read_json(SOURCE_INVENTORY)
    source_entry = manifest_inventory['instances'][str(instance_id)]
    expected_source_file = next(row for row in source_entry['files']
                                if row['file'].endswith(source['orders'].name))
    if sha(source['orders']) != expected_source_file['sha256']:
        raise ValueError('selected raw order file differs from verified upstream source bytes')
    common_paths = (source['factories'], source['routes'])
    expected_common = manifest_inventory['common_csv_comparison']
    for path in common_paths:
        key = path.name
        if sha(path) != expected_common[key]['sha256']:
            raise ValueError(f'vendored common source differs from pinned bytes: {key}')
    partitions, bounds = split_source_orders(order_rows)

    run_dir.mkdir(parents=True, exist_ok=False)
    (run_dir/'data').mkdir()
    (run_dir/'trees').mkdir()
    (run_dir/'rollouts').mkdir()
    (run_dir/'cache').mkdir()
    partition_rows = {}
    for name, part in partitions.items():
        folder = run_dir/'data'/name
        folder.mkdir()
        with (folder/'orders.csv').open('x', encoding='utf-8', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=list(order_rows[0]))
            writer.writeheader()
            writer.writerows(part)
        (folder/'vehicle_info_5.csv').write_bytes(source['vehicles'].read_bytes())
        loaded = validate_instance(folder, BENCHMARK)
        partition_rows[name] = _partition_summary(name, part, folder, loaded)

    active_factory_ids = {row[key] for row in order_rows for key in ('pickup_id', 'delivery_id')}
    factory_rows = rows(source['factories'], 'factory')
    split_manifest = dict(
        schema='dpdp-100-temporal-split-v1',
        source=dict(repository='huawei-noah/xingtian',
                    commit=manifest_inventory['commit'],
                    benchmark_instance_id=instance_id,
                    original_order_file=str(source['orders'].resolve()),
                    original_vehicle_file=str(source['vehicles'].resolve()),
                    order_sha256=sha(source['orders']),
                    vehicle_sha256=sha(source['vehicles']),
                    factory_sha256=sha(source['factories']),
                    route_sha256=sha(source['routes']),
                    source_manifest_sha256=sha(SOURCE_INVENTORY),
                    source_not_subset=True),
        selection_rule=dict(smallest_instance_id_with_exactly_100_original_orders=True,
                            inventory_scan=inventory,
                            selected_instance_id=instance_id,
                            original_source_records=len(order_rows),
                            original_unique_orders=len({row['order_id'] for row in order_rows})),
        dimensions=dict(original_orders=len(order_rows), items=source_validation['items_after_loader'],
                        vehicles=source_validation['vehicles'], factories=source_validation['factories'],
                        active_factories=len(active_factory_ids),
                        factory_ids_in_network=len(factory_rows)),
        temporal_split=dict(basis='fraction of [minimum, maximum] original release-time span',
                            ratios=dict(train='0.60', validation='0.20', test='0.20'),
                            time_slot_seconds=TIME_SLOT_SECONDS,
                            slot_origin='00:00:00; floor(release_seconds/600)',
                            identical_release_timestamps_kept_together=True,
                            independent_rollouts=True, fleet_reset_between_partitions=True,
                            no_cross_partition_carryover=True, **bounds),
        full_instance_release_distribution=_release_stats(order_rows),
        partitions=partition_rows,
    )
    write_new(run_dir/'temporal_split_manifest.json', split_manifest)

    _, population, g0_rows = initial_population()
    for member, tree in enumerate(population):
        save_tree(run_dir/'trees'/f'g0_m{member:02d}.json', tree,
                  training=dict(generation=0, member=member, gp_seed=42,
                                target_depth=g0_rows[member]['target_depth'],
                                initialization='ramped full/grow depth 2-4'),
                  limits=LIMITS)
    unique_members = first_unique_members(population)
    if len(unique_members) < 4:
        raise ValueError(f'G0 seed produced only {len(unique_members)} unique trees; need four')
    g0_manifest = dict(schema='dpdp-100-g0-population-v1', gp_seed=42,
                       population_size=10, initial_depths=[2, 3, 4],
                       maximum_depth=LIMITS.max_depth, maximum_nodes=LIMITS.max_nodes,
                       members=g0_rows, first_four_unique_member_indices=unique_members)
    write_new(run_dir/'g0_population_manifest.json', g0_manifest)

    code_hashes = {name: sha(ROOT/name) for name in SOURCE_FILES}
    try:
        revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT,
                                           text=True, stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        revision = None
    config = dict(
        schema='dpdp-gp-100-official-feasibility-v1',
        dataset=dict(instance_id=instance_id, original_orders=100,
                     source_order_sha256=sha(source['orders']), source_commit=manifest_inventory['commit']),
        temporal_split=dict(ratios=[.60, .20, .20], basis='release-time span',
                            release_ties='keep identical timestamps together'),
        gp=dict(population_size=10, evaluated_generations=10,
                generation_labels=[f'G{i}' for i in range(10)],
                breeding_transitions=9, elitism=1, tournament_size=3,
                crossover_probability=.8, mutation_probability=.3,
                initial_depths=[2, 3, 4], maximum_depth=5, maximum_nodes=63,
                seed=42, features=list(FEATURES),
                primitives=['+', '-', '*', '/'],
                initialization='ramped full/grow; target depth cycles 2,3,4',
                fitness='raw independently verified Train total_score J; minimize',
                invalid_timeout_policy='J=null; exclude from parent and candidate pools; no retry by tree hash'),
        evaluation=dict(simulator_seed=0, time_slot_seconds=TIME_SLOT_SECONDS,
                        decision_timeout_seconds=600, rollout_timeout_seconds=3600,
                        runner_wall_guard_seconds=RUNNER_WALL_SECONDS,
                        simulation_horizon_seconds=SIMULATOR_HORIZON_SECONDS,
                        validation_top_k=5,
                        validation='after G9 only; unique valid trees sorted by Train J, node count, canonical tree; select minimum Validation J, then Train J, node count, canonical tree',
                        vnsme_scope='Test only; no VNSME Train or Validation'),
        source=dict(git_revision=revision, source_sha256=code_hashes,
                    python=sys.version, executable=str(Path(sys.executable).resolve()),
                    packages={name: importlib.metadata.version(name)
                              for name in ('dvrpsim', 'simpy')}),
        no_partial_or_invalid_J=True,
        run_namespace=str(run_dir.relative_to(ROOT)),
        frozen_at_utc=datetime.now(timezone.utc).isoformat())
    config_sha = hashlib.sha256(canonical_json(config).encode('utf-8')).hexdigest()
    write_new(run_dir/'experiment_config.json', config)
    split_sha = sha(run_dir/'temporal_split_manifest.json')
    g0_sha = sha(run_dir/'g0_population_manifest.json')
    protocol_payload = dict(schema='dpdp-gp-100-official-protocol-v1',
                            config_sha256=config_sha,
                            temporal_split_manifest_sha256=split_sha,
                            g0_population_manifest_sha256=g0_sha,
                            source_sha256=code_hashes,
                            source_manifest_sha256=sha(SOURCE_INVENTORY),
                            initialization_population=[dict(member=row['member'],
                                canonical_sha256=row['canonical_sha256']) for row in g0_rows],
                            cache=dict(scope='run-local only',
                                       reuse_requires_same_protocol_seed_source_data_and_tree=True,
                                       timeout_tree_retry=False),
                            trainer=dict(max_train_rollout_requests=100,
                                         elite_reuse_requests=9,
                                         max_new_train_rollouts_without_nonelite_cache_hits=91),
                            protocol_locked_before_rollout=True)
    protocol_sha = hashlib.sha256(canonical_json(protocol_payload).encode('utf-8')).hexdigest()
    protocol = dict(protocol_payload, protocol_sha256=protocol_sha)
    write_new(run_dir/'protocol.json', protocol)
    (run_dir/'protocol.sha256').write_text(protocol_sha+'\n', encoding='ascii')
    return dict(run_directory=str(run_dir), instance_id=instance_id,
                original_orders=len(order_rows), items=source_validation['items_after_loader'],
                vehicles=source_validation['vehicles'], factories=source_validation['factories'],
                partitions={name: dict(original_orders=info['original_orders'], items=info['items'],
                                        slots=info['occupied_600_second_slots'])
                            for name, info in partition_rows.items()},
                g0_unique_members=unique_members, protocol_sha256=protocol_sha)


def verify_locked_run(run_dir):
    run_dir = Path(run_dir).resolve()
    config = read_json(run_dir/'experiment_config.json')
    manifest = read_json(run_dir/'temporal_split_manifest.json')
    g0 = read_json(run_dir/'g0_population_manifest.json')
    protocol = read_json(run_dir/'protocol.json')
    payload = {key: value for key, value in protocol.items() if key != 'protocol_sha256'}
    expected_protocol = hashlib.sha256(canonical_json(payload).encode('utf-8')).hexdigest()
    if protocol.get('protocol_sha256') != expected_protocol:
        raise ValueError('protocol hash mismatch')
    if (run_dir/'protocol.sha256').read_text(encoding='ascii').strip() != expected_protocol:
        raise ValueError('protocol hash sidecar mismatch')
    if hashlib.sha256(canonical_json(config).encode('utf-8')).hexdigest() != protocol['config_sha256']:
        raise ValueError('experiment config changed after lock')
    if sha(run_dir/'temporal_split_manifest.json') != protocol['temporal_split_manifest_sha256']:
        raise ValueError('temporal split manifest changed after lock')
    if sha(run_dir/'g0_population_manifest.json') != protocol['g0_population_manifest_sha256']:
        raise ValueError('G0 manifest changed after lock')
    current_sources = {name: sha(ROOT/name) for name in SOURCE_FILES}
    if current_sources != protocol['source_sha256']:
        raise ValueError('source version differs from the locked experiment')
    for split in SPLITS:
        info = manifest['partitions'][split]
        folder = run_dir/'data'/split
        if (sha(folder/'orders.csv') != info['orders_sha256']
                or sha(folder/'vehicle_info_5.csv') != info['vehicles_sha256']):
            raise ValueError(f'{split} data differs from the locked split manifest')
    for row in g0['members']:
        tree, _ = load_tree(run_dir/'trees'/f"g0_m{row['member']:02d}.json")
        if tree_hash(tree) != row['canonical_sha256']:
            raise ValueError(f"G0 member {row['member']} differs from its canonical hash")
    return config, manifest, g0, protocol


def runtime_statistics(events):
    runtimes = []
    completed = 0
    attempts = 0
    for event in events:
        kind = event.get('event')
        if kind == 'START':
            attempts += 1
        if kind == 'END' and event.get('status') == 'completed':
            elapsed = event.get('decision_elapsed_seconds')
            if isinstance(elapsed, (int, float)) and math.isfinite(elapsed) and elapsed >= 0:
                runtimes.append(float(elapsed))
                completed += 1
        elif kind == 'TIMEOUT':
            elapsed = event.get('decision_elapsed_seconds')
            if isinstance(elapsed, (int, float)) and math.isfinite(elapsed) and elapsed >= 0:
                runtimes.append(float(elapsed))
    if not runtimes:
        return dict(attempts=attempts, completed=completed, mean=None, median=None,
                    p95=None, maximum=None, measured_decision_times=0)
    return dict(attempts=attempts, completed=completed,
                mean=statistics.mean(runtimes), median=statistics.median(runtimes),
                p95=sorted(runtimes)[math.ceil(.95*len(runtimes))-1],
                maximum=max(runtimes), measured_decision_times=len(runtimes))


def _read_events(path):
    if not Path(path).is_file():
        return []
    result = []
    for line in Path(path).read_text(encoding='utf-8').splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            result.append(value)
    return result


def summarize_stage(tree, policy, partition, run_dir, supervision, runner_result,
                    independent_score, independent_audit, events, protocol_sha,
                    run_id, total_wall):
    clean = (supervision.get('state') == 'EXITED' and supervision.get('exit_code') == 0
             and supervision.get('valid_supervision') is True
             and not supervision.get('gaps')
             and supervision.get('remaining_job_processes') == [])
    result_ok = (isinstance(runner_result, dict)
                 and runner_result.get('status') == 'COMPLETED'
                 and runner_result.get('valid') is True
                 and runner_result.get('contract_complete') is True
                 and runner_result.get('partial') is False)
    audit_ok = isinstance(independent_audit, dict) and independent_audit.get('status') == 'PASS'
    score_ok = (isinstance(independent_score, dict)
                and independent_score.get('valid') is True
                and isinstance(runner_result, dict)
                and isinstance(runner_result.get('score'), dict)
                and all(str(runner_result['score'].get(key)) == str(independent_score.get(key))
                        for key in ('total_score', 'total_distance_km', 'total_tardiness_seconds')))
    expected = read_json(Path(run_dir).parents[3]/'temporal_split_manifest.json')['partitions'][partition]
    counts_ok = (isinstance(runner_result, dict)
                 and runner_result.get('completed_original_orders') == expected['original_orders']
                 and runner_result.get('completed_items') == expected['items'])
    valid = clean and result_ok and audit_ok and score_ok and counts_ok
    timeout_event = next((event for event in reversed(events) if event.get('event') == 'TIMEOUT'), None)
    gp_stats = runner_result.get('gp_evaluation') if isinstance(runner_result, dict) else None
    if not isinstance(gp_stats, dict):
        gp_stats = {}
    score_payload = None
    if valid:
        score_payload = {key: str(independent_score[key]) for key in
                         ('total_score', 'total_distance_km', 'total_tardiness_seconds')}
    return dict(
        status='COMPLETED' if valid else ('TIMEOUT' if timeout_event or
            supervision.get('state') in ('TIMEOUT', 'DECISION_TIMEOUT') else 'INVALID'),
        valid=valid, J=str(independent_score['total_score']) if valid else None,
        run_id=run_id, policy=policy, partition=partition,
        expression=tree.text() if tree else None,
        tree_sha256=tree_hash(tree) if tree else None,
        protocol_sha256=protocol_sha,
        actual_wall_seconds=supervision.get('elapsed_seconds'),
        total_evaluator_wall_seconds=total_wall,
        decision_runtime=runtime_statistics(events),
        candidate_evaluations=gp_stats.get('evaluations'),
        latest_observed_candidate_count=(timeout_event.get('candidate_count')
                                         if timeout_event else None),
        feasibility_status=(independent_audit.get('status') if independent_audit else 'NOT_RUN'),
        feasibility_reason=(independent_audit.get('reason') if independent_audit else None),
        independent_score=score_payload,
        independent_score_matches_runner=score_ok if result_ok else None,
        completed_orders=(runner_result.get('completed_original_orders')
                          if isinstance(runner_result, dict) else None),
        completed_items=(runner_result.get('completed_items')
                         if isinstance(runner_result, dict) else None),
        decision_count=(runner_result.get('decision_count') if isinstance(runner_result, dict)
                        else runtime_statistics(events)['completed']),
        timeout_status=(dict(kind=timeout_event.get('timeout_type'),
                             decision_index=timeout_event.get('decision_index'),
                             simulation_seconds=timeout_event.get('simulation_seconds'),
                             elapsed_seconds=timeout_event.get('decision_elapsed_seconds'))
                        if timeout_event else None),
        peak_memory_bytes=supervision.get('peak_job_memory_bytes'),
        supervision_status=supervision.get('state'),
        supervision_exit_code=supervision.get('exit_code'),
        remaining_job_processes=supervision.get('remaining_job_processes'),
        runner_error=runner_result.get('error') if isinstance(runner_result, dict) else None,
        independent_audit=independent_audit,
        runner_result_path=str(Path(run_dir)/'result.json'),
        score_rule='J is exposed only for a clean full completion with v3 feasibility replay and matching independent total_score',
    )


def _cache_path(run_dir, partition):
    return Path(run_dir)/'cache'/f'{partition}.json'


def _load_cache(run_dir, partition, protocol_sha):
    path = _cache_path(run_dir, partition)
    if not path.exists():
        return dict(protocol_sha256=protocol_sha, entries={})
    cache = read_json(path)
    if cache.get('protocol_sha256') != protocol_sha:
        raise ValueError(f'{partition} cache protocol mismatch')
    return cache


def _tree_artifact_path(run_dir, tree):
    digest = tree_hash(tree)
    for path in (Path(run_dir)/'trees').glob('*.json'):
        try:
            prior, _ = load_tree(path)
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        if tree_hash(prior) == digest:
            return path
    return None


def run_rollout(run_dir, *, policy, partition, tree=None, run_id=None):
    run_dir = Path(run_dir).resolve()
    config, split_manifest, _, protocol = verify_locked_run(run_dir)
    if policy not in ('gp', 'vnsme') or partition not in SPLITS:
        raise ValueError('unsupported policy or partition')
    if policy == 'gp' and tree is None:
        raise ValueError('GP rollout requires a saved tree')
    if policy == 'vnsme' and tree is not None:
        raise ValueError('VNSME rollout must not carry a GP tree')
    input_dir = run_dir/'data'/partition
    tree_path = _tree_artifact_path(run_dir, tree) if tree else None
    if policy == 'gp' and tree_path is None:
        raise ValueError('tree artifact is not present in the locked run')
    key = tree_hash(tree) if tree else 'vnsme'
    if run_id is None:
        run_id = f'{policy}_{partition}_{key[:12]}'
    output = run_dir/'rollouts'/partition/key
    if output.exists():
        summary_path = output/'rollout_summary.json'
        if summary_path.is_file():
            summary = read_json(summary_path)
            if summary.get('protocol_sha256') == protocol['protocol_sha256']:
                return summary
        raise FileExistsError(f'preserving existing incomplete rollout artifact: {output}')
    output.mkdir(parents=True, exist_ok=False)
    runner_dir, supervisor_dir = output/'runner', output/'supervisor'
    stage_trace = output/'stage_trace.jsonl'
    stage_trace.open('x', encoding='utf-8').close()
    execution = config['evaluation']
    command = [sys.executable, '-B', str(ROOT/'run_dpdp_insertion.py'),
        '--policy', policy, '--contract-version', EXECUTION_CONTRACT,
        '--instance-directory', str(input_dir.resolve()),
        '--data-directory', str(BENCHMARK.resolve()),
        '--seed', str(config['evaluation']['simulator_seed']),
        '--wall-seconds', str(execution['runner_wall_guard_seconds']),
        '--max-simulation-seconds', str(execution['simulation_horizon_seconds']),
        '--output', str(runner_dir.resolve()),
        '--stage-trace', str(stage_trace.resolve()),
        '--stage-partition', partition]
    if policy == 'gp':
        command += ['--tree', str(tree_path.resolve()), '--no-feasibility-profile', '--decision-progress']
    else:
        command += ['--vnsme-epoch-seconds', '600']
    code_hashes = protocol['source_sha256']
    run_config = dict(run_id=run_id, policy=policy, partition=partition,
                      tree_sha256=tree_hash(tree) if tree else None,
                      protocol_sha256=protocol['protocol_sha256'],
                      orders_sha256=split_manifest['partitions'][partition]['orders_sha256'],
                      vehicles_sha256=split_manifest['partitions'][partition]['vehicles_sha256'],
                      simulator_seed=execution['simulator_seed'],
                      decision_timeout_seconds=execution['decision_timeout_seconds'],
                      rollout_timeout_seconds=execution['rollout_timeout_seconds'],
                      runner_wall_guard_seconds=execution['runner_wall_guard_seconds'],
                      source_sha256=code_hashes, command=command)
    write_new(output/'run_config.json', run_config)
    started = time.monotonic()
    supervision, supervisor_error = {}, None
    try:
        supervision = supervise(command, supervisor_dir,
            execution['rollout_timeout_seconds'], interval=.05, gap_limit=3,
            decision_trace=stage_trace,
            decision_timeout=execution['decision_timeout_seconds'],
            partition=partition, algorithm=policy, stage_started_monotonic=started)
    except BaseException as exc:
        supervisor_error = f'{type(exc).__name__}: {exc}'
        if (supervisor_dir/'supervision.json').is_file():
            try:
                supervision = read_json(supervisor_dir/'supervision.json')
            except (OSError, json.JSONDecodeError):
                pass
    runner_result = None
    if (runner_dir/'result.json').is_file():
        try:
            runner_result = read_json(runner_dir/'result.json')
        except (OSError, json.JSONDecodeError):
            pass
    events = _read_events(stage_trace)
    independent_score, independent_audit = None, None
    if (runner_result and runner_result.get('status') == 'COMPLETED'
            and runner_result.get('valid') is True and (runner_dir/'simulation.log').is_file()):
        try:
            from verify_dpdp_score import verify
            independent_score = verify(runner_dir/'simulation.log', input_dir/'orders.csv',
                input_dir/'vehicle_info_5.csv', BENCHMARK/'route_info.csv')
            from dpdp_v3_independent_audit import audit
            independent_audit = audit(runner_dir,
                dict(orders=str(input_dir/'orders.csv'), vehicles=str(input_dir/'vehicle_info_5.csv'),
                     routes=str(BENCHMARK/'route_info.csv')), policy=policy)
        except BaseException as exc:
            independent_audit = dict(status='UNVERIFIABLE',
                                     reason=f'{type(exc).__name__}: {exc}')
    summary = summarize_stage(tree, policy, partition, runner_dir, supervision,
        runner_result, independent_score, independent_audit, events,
        protocol['protocol_sha256'], run_id, time.monotonic()-started)
    summary['supervisor_error'] = supervisor_error
    summary['supervision_path'] = str(supervisor_dir/'supervision.json')
    summary['stage_trace_path'] = str(stage_trace)
    write_new(output/'rollout_summary.json', summary)
    return summary


def evaluate_cached(run_dir, partition, tree, run_id):
    _, _, _, protocol = verify_locked_run(run_dir)
    cache = _load_cache(run_dir, partition, protocol['protocol_sha256'])
    digest = tree_hash(tree)
    entry = cache['entries'].get(digest)
    if entry:
        path = Path(entry['summary_path'])
        if not path.is_file():
            raise ValueError('cache entry summary is missing')
        summary = read_json(path)
        if (summary.get('tree_sha256') != digest
                or summary.get('protocol_sha256') != protocol['protocol_sha256']
                or summary.get('J') != entry.get('J')
                or summary.get('status') != entry.get('status')):
            raise ValueError('cache hit provenance or score mismatch')
        return dict(summary, cache_hit=True)
    summary = run_rollout(run_dir, policy='gp', partition=partition,
                          tree=tree, run_id=run_id)
    cache['entries'][digest] = dict(status=summary['status'], J=summary['J'],
                                    summary_path=str(Path(run_dir)/'rollouts'/partition/digest/'rollout_summary.json'),
                                    protocol_sha256=protocol['protocol_sha256'])
    write_replace(_cache_path(run_dir, partition), cache)
    return dict(summary, cache_hit=False)


def _gate_record(run_dir, member, tree, summary):
    return dict(member=member, expression=tree.text(), tree_sha256=tree_hash(tree),
                depth=validate_tree(tree, LIMITS)[1], nodes=validate_tree(tree, LIMITS)[0],
                status=summary.get('status'), valid=summary.get('valid'), J=summary.get('J'),
                actual_wall_seconds=summary.get('actual_wall_seconds'),
                decision_count=summary.get('decision_count'),
                candidate_evaluations=summary.get('candidate_evaluations'),
                decision_runtime=summary.get('decision_runtime'),
                feasibility_status=summary.get('feasibility_status'),
                independent_score_matches_runner=summary.get('independent_score_matches_runner'),
                completed_orders=summary.get('completed_orders'),
                completed_items=summary.get('completed_items'),
                timeout_status=summary.get('timeout_status'),
                peak_memory_bytes=summary.get('peak_memory_bytes'),
                rollout_summary_path=str(Path(run_dir)/'rollouts/train'/tree_hash(tree)/'rollout_summary.json'))


def run_gate(run_dir=RUN):
    run_dir = Path(run_dir).resolve()
    _, _, g0, protocol = verify_locked_run(run_dir)
    gate_path = run_dir/'feasibility_gate.json'
    if gate_path.exists():
        previous = read_json(gate_path)
        if previous.get('protocol_sha256') == protocol['protocol_sha256']:
            return previous
        raise ValueError('existing gate artifact belongs to another protocol')
    population = [load_tree(run_dir/'trees'/f'g0_m{i:02d}.json')[0]
                  for i in range(10)]
    members = g0['first_four_unique_member_indices']
    records = []
    for ordinal, member in enumerate(members, 1):
        tree = population[member]
        summary = evaluate_cached(run_dir, 'train', tree,
                                  f'feasibility_g0_m{member:02d}_train')
        record = _gate_record(run_dir, member, tree, summary)
        record['gate_order'] = ordinal
        records.append(record)
        print(f"Gate {ordinal}/4 member={member} status={record['status']} "
              f"J={record['J']} wall={record['actual_wall_seconds']}", flush=True)
    runtimes = [float(row['actual_wall_seconds']) for row in records
                if isinstance(row.get('actual_wall_seconds'), (int, float))]
    valid_count = sum(row.get('valid') is True and row.get('J') is not None
                      and row.get('feasibility_status') == 'PASS'
                      and row.get('independent_score_matches_runner') is True
                      for row in records)
    mean_wall = statistics.mean(runtimes) if runtimes else None
    error_statuses = {'INVALID', 'ERROR'}
    serious_errors = [row for row in records if row.get('status') in error_statuses
                      or row.get('feasibility_status') in ('FAIL', 'UNVERIFIABLE')]
    passed = (len(records) == 4 and len({r['tree_sha256'] for r in records}) == 4
              and valid_count >= 3 and not serious_errors and mean_wall is not None
              and mean_wall <= 300)
    artifact = dict(status='GO' if passed else 'NO-GO', protocol_sha256=protocol['protocol_sha256'],
        run_directory=str(run_dir), evaluated_partition='train', validation_or_test_started=False,
        vnsme_started=False, gate_tree_count=len(records), valid_tree_count=valid_count,
        mean_actual_wall_seconds=mean_wall,
        target_mean_wall_seconds=300, serious_errors=serious_errors,
        continuation_selection_supported=True,
        selection_contract='raw Train J ascending; tournament 3; crossover .8; mutation .3; elitism 1; max depth 5',
        records=records, completed_at_utc=datetime.now(timezone.utc).isoformat())
    write_new(gate_path, artifact)
    return artifact


def _member_record(generation, member, tree, summary):
    return dict(generation=generation, member=member, expression=tree.text(),
                tree_sha256=tree_hash(tree), depth=validate_tree(tree, LIMITS)[1],
                nodes=validate_tree(tree, LIMITS)[0], status=summary.get('status'),
                train_J=summary.get('J'), cache_hit=summary.get('cache_hit', False),
                run_id=summary.get('run_id'))


def _tree_from_digest(run_dir, digest, populations):
    for population in populations:
        for tree in population:
            if tree_hash(tree) == digest:
                return tree
    for path in (Path(run_dir)/'trees').glob('*.json'):
        tree, _ = load_tree(path)
        if tree_hash(tree) == digest:
            return tree
    raise ValueError(f'missing tree artifact for {digest}')


def _selection_key(entry):
    return (Decimal(entry['validation_J']), Decimal(entry['train_J']),
            entry['nodes'], canonical(entry['tree']))


def continue_experiment(run_dir=RUN):
    """Explicitly run remaining G0, G1-G9, then Validation and GP/VNSME Test."""
    run_dir = Path(run_dir).resolve()
    config, _, g0_manifest, protocol = verify_locked_run(run_dir)
    gate = read_json(run_dir/'feasibility_gate.json')
    if (gate.get('protocol_sha256') != protocol['protocol_sha256']
            or gate.get('status') != 'GO'):
        raise RuntimeError('official continuation requires a matching GO feasibility gate')
    training_dir = run_dir/'official_training'
    if training_dir.exists():
        prior = training_dir/'training_result.json'
        if prior.is_file() and read_json(prior).get('protocol_sha256') == protocol['protocol_sha256']:
            raise FileExistsError(f'preserving prior official training artifact: {training_dir}')
        raise FileExistsError(f'preserving incomplete official training artifact: {training_dir}')
    training_dir.mkdir(parents=True, exist_ok=False)
    populations, generation_rows = [], []
    random_state, generated_population, _ = initial_population()
    population = [load_tree(run_dir/'trees'/f'g0_m{i:02d}.json')[0] for i in range(10)]
    if [tree_hash(tree) for tree in generated_population] != [tree_hash(tree) for tree in population]:
        raise ValueError('reinitialized G0 does not match locked population')
    populations.append(population)
    trace = training_dir/'training_trace.jsonl'
    trace.open('x', encoding='utf-8').close()
    start = time.monotonic()
    try:
        for generation in range(10):
            member_rows = []
            evaluated = []
            for member, tree in enumerate(population):
                summary = evaluate_cached(run_dir, 'train', tree,
                    f'official_g{generation}_m{member:02d}_train')
                row = _member_record(generation, member, tree, summary)
                member_rows.append(row)
                if row['status'] == 'COMPLETED' and row['train_J'] is not None:
                    evaluated.append((Decimal(row['train_J']), tree))
                with trace.open('a', encoding='utf-8', newline='\n') as handle:
                    handle.write(json.dumps(dict(event='TRAIN_MEMBER', **row),
                                             sort_keys=True, allow_nan=False)+'\n')
                    handle.flush(); os.fsync(handle.fileno())
            generation_artifact = dict(generation=generation, label=f'G{generation}',
                population_size=len(population), members=member_rows,
                valid_members=len(evaluated), protocol_sha256=protocol['protocol_sha256'])
            write_new(training_dir/f'g{generation}.json', generation_artifact)
            generation_rows.append(generation_artifact)
            print(f"G{generation}: valid={len(evaluated)}/10", flush=True)
            if generation < 9:
                if not evaluated:
                    raise RuntimeError(f'no valid parent in G{generation}; stop without further rollout')
                population = breed(random_state, evaluated, 10, tournament=3,
                    crossover_rate=.8, mutation_rate=.3, elitism=1, limits=LIMITS)
                populations.append(population)

        # Select up to K unique complete Train trees only after G9 is complete.
        train_cache = _load_cache(run_dir, 'train', protocol['protocol_sha256'])['entries']
        candidate_by_hash = {}
        for generation, pop in enumerate(populations):
            for tree in pop:
                digest = tree_hash(tree)
                entry = train_cache.get(digest)
                if entry and entry.get('status') == 'COMPLETED' and entry.get('J') is not None:
                    candidate_by_hash.setdefault(digest, dict(tree=tree, train_J=entry['J'],
                        nodes=validate_tree(tree, LIMITS)[0], train_summary=entry['summary_path']))
        candidates = sorted(candidate_by_hash.values(),
            key=lambda entry:(Decimal(entry['train_J']), entry['nodes'], canonical(entry['tree'])))[:5]
        if not candidates:
            raise RuntimeError('no valid unique Train tree for Validation')
        candidate_manifest = [dict(expression=item['tree'].text(),
            tree_sha256=tree_hash(item['tree']), train_J=item['train_J'], nodes=item['nodes'])
            for item in candidates]
        write_new(training_dir/'validation_candidates.json', dict(protocol_sha256=protocol['protocol_sha256'],
                                                                   candidates=candidate_manifest))
        validation_records = []
        for index, candidate in enumerate(candidates):
            summary = run_rollout(run_dir, policy='gp', partition='validation',
                tree=candidate['tree'], run_id=f'official_validation_{index+1:02d}')
            record = dict(candidate, validation_status=summary['status'],
                          validation_J=summary['J'], validation_summary=summary)
            validation_records.append(record)
            if summary['status'] != 'COMPLETED' or summary['J'] is None:
                raise RuntimeError(f"Validation candidate {index+1} invalid; no score or retry")
        eligible = [item for item in validation_records if item.get('validation_J') is not None]
        if not eligible:
            raise RuntimeError('no valid Validation candidate')
        selected = min(eligible, key=_selection_key)
        selected_tree_path = run_dir/'trees'/'selected_official_tree.json'
        save_tree(selected_tree_path, selected['tree'],
            training=dict(protocol_sha256=protocol['protocol_sha256'],
                train_J=selected['train_J'], validation_J=selected['validation_J'],
                selection='minimum independently verified Validation J; tie by Train J, node count, canonical tree'),
            limits=LIMITS)
        write_new(training_dir/'selection_decision.json', dict(protocol_sha256=protocol['protocol_sha256'],
            selected_expression=selected['tree'].text(),
            selected_tree_sha256=tree_hash(selected['tree']), train_J=selected['train_J'],
            validation_J=selected['validation_J'], candidates=[dict(
                expression=item['tree'].text(), tree_sha256=tree_hash(item['tree']),
                train_J=item['train_J'], validation_J=item['validation_J'])
                for item in validation_records]))

        gp_test = run_rollout(run_dir, policy='gp', partition='test',
            tree=selected['tree'], run_id='official_selected_gp_test')
        if gp_test['status'] != 'COMPLETED':
            raise RuntimeError('selected GP Test incomplete; no J or retry')
        vnsme_test = run_rollout(run_dir, policy='vnsme', partition='test',
            tree=None, run_id='official_vnsme_test')
        if vnsme_test['status'] != 'COMPLETED':
            raise RuntimeError('VNSME Test incomplete; no J or retry')
        result = dict(status='COMPLETED', protocol_sha256=protocol['protocol_sha256'],
            generations_completed=10, population_size=10,
            train_rollout_requests=sum(len(row['members']) for row in generation_rows),
            selected_expression=selected['tree'].text(),
            selected_tree_sha256=tree_hash(selected['tree']),
            selected_train_J=selected['train_J'], selected_validation_J=selected['validation_J'],
            gp_test=gp_test, vnsme_test=vnsme_test,
            wall_seconds=time.monotonic()-start)
        write_new(training_dir/'training_result.json', result)
        return result
    except BaseException as exc:
        failure = dict(status='INCOMPLETE', protocol_sha256=protocol['protocol_sha256'],
            generations_completed=len(generation_rows), J=None,
            error=f'{type(exc).__name__}: {exc}', wall_seconds=time.monotonic()-start)
        write_new(training_dir/'training_result.json', failure)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'gate', 'continue'))
    parser.add_argument('--run-dir', type=Path, default=RUN)
    args = parser.parse_args()
    if args.action == 'prepare':
        value = prepare(args.run_dir)
    elif args.action == 'gate':
        value = run_gate(args.run_dir)
    else:
        value = continue_experiment(args.run_dir)
    print(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False, default=str))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
