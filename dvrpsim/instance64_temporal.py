"""Manual, stepwise instance_64 temporal experiment. Importing this module runs no jobs."""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import csv
from decimal import Decimal
import hashlib
import json
import math
from functools import lru_cache
from pathlib import Path
import random
import re
import shutil
import subprocess
import sys
import time

from dpdp_contract import EXECUTION_CONTRACT, contract_metadata
from dpdp_dataset import rows, seconds, validate_instance
from dpdp_gp import (Limits, Node, canonical, crossover, mutate, parse_node,
                     random_tree, save_tree, tree_hash, validate_tree)
from dpdp_v3_independent_audit import audit as replay
from dpdp_vnsme_reference_v3 import runtime_fingerprint
from verify_dpdp_score import verify

ROOT = Path(__file__).resolve().parent
UPSTREAM = ROOT/'third_party/huawei-xingtian/simulator/dpdp_competition/benchmark'
RUN = ROOT/'gp_runs/instance64_temporal_60_20_20_seed42_r01'
SOURCE = UPSTREAM/'instance_64/4000_8.csv'
PINNED_SHA256 = dict(orders='7997712ca7567855d8b1513c1c2aae9b3c63a90c16ef3de1442d62e694ed4f16',
                     vehicles='25533ed72a77153346224a6606f8d82c1f431fc4fcaf20b92d821d4f881ffb53',
                     factories='ed0f987404c09c0bf562212478784f29e29ce41f52cebbb277e1e219dd9a81e4',
                     routes='26e6cc70cf96c2a73e0ce3fdd9d002715a0719c92802544aa810b669772a3550')
SPLITS = ('train', 'validation', 'test')
LIMITS = Limits(6, 63)
PENALTY = 1e15  # selection only; never reported as observed J
PROBE_ORDERS = 50
PROBE_WALL_SECONDS = 600
CONFIG = dict(schema='instance64-temporal-v1', source='Huawei Xingtian instance_64/4000_8.csv',
              source_commit='e4ef3a1c92d19d1d08c3ef0e2156b6fecefdbe04',
              run_id='instance64_temporal_60_20_20_seed42_r01',
              gp_seed=42, simulator_seed=0, workers=2, population=50,
              additional_generations=20, initial_depths=[2, 3, 4], maximum_depth=6,
              maximum_nodes=63, tournament=3, elitism=2,
              operations=dict(crossover=.70, mutation=.25, reproduction=.05),
              gp_wall_seconds=3600, baseline_wall_seconds=10800,
              vnsme_epoch_seconds=600, simulation_horizon_seconds=604800,
              decision_interval_seconds=600, invalid_fitness_penalty=PENALTY,
              time_origin='original HH:MM:SS; no shift',
              timeout_status='provisional; calibrate from train pilot before main runs',
              resume_supported=False)
TUNABLE_TIMEOUTS = frozenset({'gp_wall_seconds','baseline_wall_seconds','vnsme_epoch_seconds',
                              'simulation_horizon_seconds'})


def default_config():
    return dict(CONFIG, run_id=RUN.name)


def settings():
    value = read(RUN/'config.json')
    if {k:v for k,v in value.items() if k not in TUNABLE_TIMEOUTS} != {
            k:v for k,v in default_config().items() if k not in TUNABLE_TIMEOUTS}:
        raise ValueError('scientific config changed; create a new run identifier')
    if any(not isinstance(value.get(k),(int,float)) or not math.isfinite(value[k]) or value[k]<=0
           for k in TUNABLE_TIMEOUTS):
        raise ValueError('timeout/horizon must be positive and finite')
    return value


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8', newline='\n') as f:
        json.dump(value, f, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False, default=str)
        f.write('\n')


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def source_paths():
    return dict(orders=SOURCE, vehicles=UPSTREAM/'instance_64/vehicle_info_100.csv',
                factories=UPSTREAM/'factory_info.csv', routes=UPSTREAM/'route_info.csv')


def split_bounds(releases):
    t0, t1 = min(releases), max(releases)
    span = t1-t0
    return t0, t0+Decimal(3)*span/5, t0+Decimal(4)*span/5, t1


def split_for(release, bounds):
    return 'train' if release < bounds[1] else 'validation' if release < bounds[2] else 'test'


def due_seconds(row):
    release = seconds(row['creation_time'])
    due = seconds(row['committed_completion_time'])
    return due+86400 if due < release else due


def initial_locations():
    factories = rows(UPSTREAM/'factory_info.csv', 'factory')
    vehicles = rows(UPSTREAM/'instance_64/vehicle_info_100.csv', 'vehicle')
    rng = random.Random(0)
    return {v['car_num']: factories[rng.randint(0, len(factories)-1)]['factory_id'] for v in vehicles}


def prepare():
    if RUN.exists():
        raise ValueError(f'run directory already exists: {RUN}; never overwrite or resume')
    paths = source_paths()
    for path in paths.values():
        if not path.is_file():
            raise ValueError(f'missing Huawei CSV: {path}')
    order_rows = rows(SOURCE, 'order')
    if len(order_rows) != 4000 or len({r['order_id'] for r in order_rows}) != 4000:
        raise ValueError('instance_64 mapping requires exactly 4000 unique source records')
    vehicles = rows(paths['vehicles'], 'vehicle')
    if len(vehicles) != 100 or {r['capacity'] for r in vehicles} != {'15'}:
        raise ValueError('instance_64 vehicle count/capacity mismatch')
    releases = [seconds(r['creation_time']) for r in order_rows]
    bounds = split_bounds(releases)
    partitions = {s: [] for s in SPLITS}
    for row, release in zip(order_rows, releases):
        partitions[split_for(release, bounds)].append(row)
    if any(not part for part in partitions.values()):
        raise ValueError('empty temporal partition')
    source_hashes = {k: sha(v) for k, v in paths.items()}
    if source_hashes != PINNED_SHA256:
        raise ValueError('vendored source differs from verified pinned Huawei bytes')
    RUN.mkdir(parents=True)
    write(RUN/'config.json', default_config())
    write(RUN/'source_provenance.json', dict(status='PINNED_HASHES_VERIFIED',
         repository='huawei-noah/xingtian', commit=CONFIG['source_commit'],
         files_sha256=PINNED_SHA256,
         note='SHA-256 values were compared with raw Huawei bytes at pinned commit during preparation of r01'))
    per_split = {}
    for split, part in partitions.items():
        folder = RUN/'data'/f'instance64_{split}'
        folder.mkdir(parents=True)
        with (folder/f'{split}_orders.csv').open('x', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=list(order_rows[0]))
            writer.writeheader()
            writer.writerows(part)
        shutil.copyfile(paths['vehicles'], folder/'vehicle_info_100.csv')
        histogram = Counter(seconds(r['creation_time'])//3600 for r in part)
        slacks = sorted(due_seconds(r)-seconds(r['creation_time']) for r in part)
        items = sum(sum(int(r[k]) for k in ('q_standard','q_small','q_box')) for r in part)
        per_split[split] = dict(source_records=len(part), original_orders=len({r['order_id'] for r in part}),
                                items_after_loader=items,
                                total_demand=str(sum((Decimal(r['demand']) for r in part), Decimal(0))),
                                release_min_seconds=min(seconds(r['creation_time']) for r in part),
                                release_max_seconds=max(seconds(r['creation_time']) for r in part),
                                hourly_release_counts={str(h): histogram[h] for h in range(24)},
                                deadline_slack_seconds=dict(min=slacks[0], median=slacks[len(slacks)//2], max=slacks[-1]),
                                overnight_deadlines=sum(seconds(r['committed_completion_time']) < seconds(r['creation_time']) for r in part),
                                vehicles=100, vehicle_capacity_pallets=15,
                                orders_sha256=sha(folder/f'{split}_orders.csv'),
                                vehicles_sha256=sha(folder/'vehicle_info_100.csv'))
    if sum(v['source_records'] for v in per_split.values()) != len(order_rows):
        raise ValueError('split lost source orders')
    mapping = dict(upstream_instance='Huawei Xingtian benchmark/instance_64',
                   internal_instance_id=None, source_paths={k:str(v.resolve()) for k,v in paths.items()},
                   source_sha256=source_hashes, split_basis='observed release [minimum, maximum]',
                   boundaries_seconds=[str(x) for x in bounds],
                   intervals=['[t0,b1)', '[b1,b2)', '[b2,t1]'],
                   time_shift_seconds=0, reset_between_splits=True,
                   same_initial_locations=initial_locations(), splits=per_split)
    write(RUN/'split_manifest.json', mapping)
    save_tree(RUN/'known_tree.json', Node('feature','delta_distance_km'),
              training=dict(role='pilot diagnostic known tree'), limits=LIMITS)
    check()
    print(json.dumps({k: {x: v[x] for x in ('source_records','items_after_loader','total_demand')}
                      for k,v in per_split.items()}, indent=2))


def inputs(split):
    if split == 'train_probe':
        folder = RUN/'data/instance64_train_probe'
        return dict(orders=folder/'train_probe_orders.csv', vehicles=folder/'vehicle_info_100.csv',
                    factories=UPSTREAM/'factory_info.csv', routes=UPSTREAM/'route_info.csv')
    folder = RUN/'data'/f'instance64_{split}'
    return dict(orders=folder/f'{split}_orders.csv', vehicles=folder/'vehicle_info_100.csv',
                factories=UPSTREAM/'factory_info.csv', routes=UPSTREAM/'route_info.csv')


def check():
    settings()
    manifest = read(RUN/'split_manifest.json')
    if manifest['source_sha256'] != {k:sha(v) for k,v in source_paths().items()}:
        raise ValueError('source data changed')
    if manifest['source_sha256'] != PINNED_SHA256:
        raise ValueError('source data differs from verified pinned Huawei bytes')
    seen = set()
    release_partition = {}
    original = rows(SOURCE, 'order')
    source_by_id = {r['order_id']:r for r in original}
    for split in SPLITS:
        paths = inputs(split)
        info = manifest['splits'][split]
        if sha(paths['orders']) != info['orders_sha256'] or sha(paths['vehicles']) != info['vehicles_sha256']:
            raise ValueError(f'{split} data checksum mismatch')
        actual = validate_instance(paths['orders'].parent, UPSTREAM)
        if actual['original_orders'] != info['original_orders'] or actual['items_after_loader'] != info['items_after_loader']:
            raise ValueError(f'{split} loader item count mismatch')
        for row in rows(paths['orders'], 'order'):
            oid = row['order_id']
            if oid in seen or source_by_id.get(oid) != row:
                raise ValueError('overlap, missing or modified original order')
            seen.add(oid)
            release = seconds(row['creation_time'])
            if split_for(release, tuple(Decimal(x) for x in manifest['boundaries_seconds'])) != split:
                raise ValueError('temporal boundary mismatch')
            if release in release_partition and release_partition[release] != split:
                raise ValueError('identical release times split apart')
            release_partition[release] = split
    if seen != set(source_by_id) or len(seen) != 4000:
        raise ValueError('source order loss')
    if initial_locations() != manifest['same_initial_locations']:
        raise ValueError('initial vehicle positions changed')
    print('CHECK PASS: 4000 source orders partitioned; loader/schema/hash/fleet verified; no simulation')


@lru_cache(maxsize=1)
def code_fingerprint():
    import dpdp_gp_rollout_v3
    return dpdp_gp_rollout_v3.source_fingerprint()


def runtime_context(split, tree=None):
    paths = inputs(split)
    return dict(schema='instance64-temporal-cache-v1', split=split,
                split_manifest_sha256=sha(RUN/'split_manifest.json'),
                config_sha256=sha(RUN/'config.json'),
                source_sha256=read(RUN/'split_manifest.json')['source_sha256'],
                split_data_sha256={k:sha(v) for k,v in paths.items()},
                **({'probe_manifest_sha256':sha(RUN/'pilot/train_probe_manifest.json')}
                   if split == 'train_probe' else {}),
                initial_locations=read(RUN/'split_manifest.json')['same_initial_locations'],
                simulator_seed=0, tree_sha256=tree_hash(tree) if tree else None,
                contract=EXECUTION_CONTRACT, evaluator='instance64-temporal-v1',
                source_fingerprint=code_fingerprint(),
                python=sys.version, executable=sys.executable)


def require_clean_supervision(job, supervision):
    """Keep process failure, watchdog timeout and monitoring failure distinct."""
    log = Path(supervision)/'process.log'
    log_detail = str(log) if log.is_file() else 'unavailable'
    detail = f"state={job.get('state')}, exit_code={job.get('exit_code')}, process.log={log_detail}"
    state = job.get('state')
    if state in ('TIMEOUT', 'EPOCH_TIMEOUT'):
        raise TimeoutError(f'rollout timeout: {detail}')
    if state == 'EXITED' and job.get('exit_code') != 0:
        raise RuntimeError(f'rollout process exited nonzero: {detail}')
    if (state != 'EXITED' or not job.get('valid_supervision') or job.get('gaps')
            or job.get('remaining_job_processes')):
        raise RuntimeError(f"supervision error: {detail}, error={job.get('error')}")


def compatible_request_context(recorded, current, manifest, policy, split):
    """Permit only historical orchestration/test hashes for a completed train baseline."""
    if recorded == current:
        return True
    if policy != 'vnsme' or split != 'train' or not isinstance(recorded, dict):
        return False
    old_sources = recorded.get('source_fingerprint')
    new_sources = current.get('source_fingerprint')
    if not isinstance(old_sources, dict) or not isinstance(new_sources, dict):
        return False
    changed = {name for name in set(old_sources) | set(new_sources)
               if old_sources.get(name) != new_sources.get(name)}
    allowed = {'instance64_temporal.py', 'test_instance64_temporal.py'}
    if not changed or not changed <= allowed:
        return False
    historical = manifest.get('source_sha256', {})
    if any(not old_sources.get(name) or old_sources[name] != historical.get(name)
           for name in changed):
        return False
    normalized = dict(current, source_fingerprint=dict(new_sources))
    for name in changed:
        normalized['source_fingerprint'][name] = old_sources[name]
    return recorded == normalized


def audited(run, supervision, split, policy, tree=None):
    run, supervision = Path(run), Path(supervision)
    if split == 'train_probe':
        if not (RUN/'pilot/train_probe_manifest.json').is_file():
            raise ValueError('missing train probe provenance')
        prepare_train_probe()
    job = read(supervision/'supervision.json')
    require_clean_supervision(job, supervision)
    result, manifest = read(run/'result.json'), read(run/'manifest.json')
    if not result.get('valid') or not result.get('contract_complete') or result.get('score') is None:
        raise ValueError('incomplete/invalid rollout has no observed J')
    if manifest['policy'] != policy or manifest['contract_version'] != EXECUTION_CONTRACT:
        raise ValueError('policy/contract mismatch')
    current = runtime_context(split, tree)
    request = read(run.parent/'request.json')
    recorded_context = request.get('context')
    if (not compatible_request_context(recorded_context, current, manifest, policy, split)
            or request.get('policy') != policy or request.get('split') != split):
        raise ValueError('run request/cache context differs from current data, config or code')
    if policy == 'vnsme':
        for name in ('run_dpdp_insertion.py', 'src/baselines/vnsme.py',
                     'dpdp_contract.py', 'verify_dpdp_score.py'):
            digest = current['source_fingerprint'].get(name)
            if not digest or digest != recorded_context['source_fingerprint'].get(name):
                raise ValueError(f'VNSME, contract or scoring source provenance mismatch: {name}')
            if name != 'src/baselines/vnsme.py' and digest != manifest['source_sha256'].get(name):
                raise ValueError(f'VNSME, contract or scoring source provenance mismatch: {name}')
    if job.get('command') != request['command']:
        raise ValueError('supervised command differs from recorded request')
    cfg = settings()
    expected_wall = (PROBE_WALL_SECONDS if split == 'train_probe' else
                     cfg['baseline_wall_seconds'] if policy == 'vnsme' else cfg['gp_wall_seconds'])
    if manifest.get('wall_limit_seconds') != expected_wall or job.get('timeout_seconds') != expected_wall:
        raise ValueError('rollout/supervisor wall budget mismatch')
    if (manifest.get('safety_horizon_simulation_seconds') != cfg['simulation_horizon_seconds']
            or manifest.get('dispatch_step_seconds') != 600):
        raise ValueError('simulation settings mismatch')
    if policy == 'vnsme' and manifest.get('vnsme_epoch_limit_seconds') != cfg['vnsme_epoch_seconds']:
        raise ValueError('VNSME epoch budget mismatch')
    if policy == 'vnsme':
        from build_vnsme import hashes
        session = read(run/'vnsme/session.json')
        build = read(ROOT/'third_party/vnsme/build_manifest.json')
        if session.get('build_manifest') != build or session.get('timeout_seconds') != cfg['vnsme_epoch_seconds']:
            raise ValueError('VNSME session/build provenance mismatch')
        for folder, key in (('original','source_sha256'),('lib','library_sha256'),('build','class_sha256')):
            if hashes(ROOT/'third_party/vnsme'/folder) != build[key]:
                raise ValueError(f'VNSME {folder} hash mismatch')
    if manifest.get('contract_protocol_sha256') != contract_metadata(EXECUTION_CONTRACT)['contract_protocol_sha256']:
        raise ValueError('contract protocol checksum mismatch')
    if {k:sha(v) for k,v in inputs(split).items()} != current['split_data_sha256']:
        raise ValueError('data hash changed')
    if manifest['initial_locations'] != current['initial_locations'] or manifest['initial_location_seed'] != 0:
        raise ValueError('initial fleet mismatch')
    if manifest['data_sha256'] != {str(v.resolve().relative_to(ROOT)) if v.resolve().is_relative_to(ROOT) else str(v.resolve()):sha(v) for v in inputs(split).values()}:
        raise ValueError('runner input hash mismatch')
    runtime_fingerprint(manifest)
    if tree and manifest.get('gp_tree',{}).get('tree_sha256') != tree_hash(tree):
        raise ValueError('tree mismatch')
    independent = replay(run, {k:str(v) for k,v in inputs(split).items()}, policy=policy)
    if independent['status'] != 'PASS':
        raise ValueError(f'independent replay {independent}')
    score = verify(run/'simulation.log', inputs(split)['orders'], inputs(split)['vehicles'], inputs(split)['routes'])
    if not score['valid'] or any(str(score[k]) != str(result['score'][k]) for k in
                                  ('total_score','total_distance_km','total_tardiness_seconds')):
        raise ValueError('independent score mismatch')
    expected = (read(RUN/'pilot/train_probe_manifest.json') if split == 'train_probe' else
                read(RUN/'split_manifest.json')['splits'][split])
    if result['completed_original_orders'] != expected['original_orders'] or result['completed_items'] != expected['items_after_loader']:
        raise ValueError('unfinished original order or item')
    value = float(score['total_score'])
    if not math.isfinite(value) or value < 0 or (policy == 'vnsme' and value <= 0):
        raise ValueError('invalid J or denominator')
    return dict(valid=True, J=str(score['total_score']), score=score,
                completed_original_orders=result['completed_original_orders'], unfinished_original_orders=0,
                completed_items=result['completed_items'], wall_seconds=result['total_wall_seconds'],
                decision_wall_seconds_total=result['decision_wall_seconds_total'],
                independent_audit=independent, supervisor_status='PASS',
                run_directory=str(run), supervision_directory=str(supervision),
                result_sha256=sha(run/'result.json'), manifest_sha256=sha(run/'manifest.json'))


def invoke(split, policy, output, tree=None):
    from dpdp_v3_supervisor import supervise
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    model = output/'model.json'
    if tree is not None:
        save_tree(model, tree, limits=LIMITS)
    cfg = settings()
    wall = (PROBE_WALL_SECONDS if split == 'train_probe' else
            cfg['baseline_wall_seconds'] if policy == 'vnsme' else cfg['gp_wall_seconds'])
    cmd = [sys.executable, '-B', str(ROOT/'run_dpdp_insertion.py'), '--policy', policy,
           '--contract-version', EXECUTION_CONTRACT, '--instance-directory', str(inputs(split)['orders'].parent),
           '--data-directory', str(UPSTREAM), '--seed', '0', '--wall-seconds', str(wall),
           '--max-simulation-seconds', str(cfg['simulation_horizon_seconds']),
           '--output', str(output/'run')]
    if policy == 'vnsme':
        cmd += ['--vnsme-epoch-seconds', str(cfg['vnsme_epoch_seconds'])]
    else:
        cmd += ['--tree', str(model)]
    write(output/'request.json', dict(split=split, policy=policy, command=cmd,
                                     context=runtime_context(split, tree)))
    started = time.perf_counter()
    error = None
    try:
        supervise(cmd, output/'supervision', wall,
                  epoch_root=output/'run/vnsme/epochs' if policy == 'vnsme' else None)
        result = audited(output/'run', output/'supervision', split, policy, tree)
    except Exception as exc:
        error = f'{type(exc).__name__}: {exc}'
        job_file = output/'supervision/supervision.json'
        if job_file.is_file() and 'state=' not in error:
            try:
                require_clean_supervision(read(job_file), output/'supervision')
            except (RuntimeError, TimeoutError) as diagnostic:
                error += f'; {diagnostic}'
        log = output/'supervision/process.log'
        if log.is_file() and str(log) not in error:
            error += f'; process.log={log}'
        result = dict(valid=False, J=None, invalid_reason=error,
                      wall_seconds=time.perf_counter()-started,
                      run_directory=str(output/'run'), supervision_directory=str(output/'supervision'))
    write(output/'audit.json', result)
    if error:
        raise ValueError(error)
    return result


def baseline(split):
    check()
    result = invoke(split, 'vnsme', RUN/'baseline'/split)
    print(f'BASELINE {split} audited J={result["J"]}')


def baseline_score(split):
    location = RUN/'baseline'/split
    if split == 'train' and not (location/'audit.json').is_file():
        location = RUN/'pilot/baseline'
    path = location/'audit.json'
    if not path.is_file():
        raise ValueError(f'missing {split} baseline; run baseline --split {split} manually first')
    result = read(path)
    if not result.get('valid') or result.get('independent_audit',{}).get('status') != 'PASS':
        raise ValueError(f'invalid {split} baseline')
    fresh = audited(location/'run', location/'supervision', split, 'vnsme')
    if json.loads(json.dumps(fresh, default=str)) != result or not 0 < float(fresh['J']) < math.inf:
        raise ValueError('baseline J/provenance changed or nonpositive')
    return float(fresh['J'])


def prepare_train_probe():
    """Create a deterministic 50-order diagnostic subset from the pinned train split."""
    manifest_path = RUN/'pilot/train_probe_manifest.json'
    source = inputs('train')['orders']
    train_rows = rows(source, 'order')
    selected = sorted(train_rows, key=lambda r:(seconds(r['creation_time']), r['order_id']))[:PROBE_ORDERS]
    selected_ids = {r['order_id'] for r in selected}
    part = [r for r in train_rows if r['order_id'] in selected_ids]
    paths = inputs('train_probe')
    if not manifest_path.exists():
        if paths['orders'].exists() or paths['vehicles'].exists():
            raise ValueError('incomplete train probe preparation')
        paths['orders'].parent.mkdir(parents=True, exist_ok=False)
        with paths['orders'].open('x', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=list(train_rows[0]))
            writer.writeheader()
            writer.writerows(part)
        shutil.copyfile(inputs('train')['vehicles'], paths['vehicles'])
        write(manifest_path, dict(source_train_sha256=sha(source),
             selected_order_ids=sorted(selected_ids), source_records=len(part),
             original_orders=len(selected_ids),
             items_after_loader=sum(sum(int(r[k]) for k in ('q_standard','q_small','q_box')) for r in part),
             orders_sha256=sha(paths['orders']), vehicles_sha256=sha(paths['vehicles'])))
    record = read(manifest_path)
    if (record['source_train_sha256'] != sha(source) or record['selected_order_ids'] != sorted(selected_ids)
            or record['source_records'] != len(part) or record['original_orders'] != PROBE_ORDERS
            or record['orders_sha256'] != sha(paths['orders'])
            or record['vehicles_sha256'] != sha(paths['vehicles'])
            or rows(paths['orders'], 'order') != part):
        raise ValueError('train probe provenance or contents changed')
    actual = validate_instance(paths['orders'].parent, UPSTREAM)
    if (actual['original_orders'] != record['original_orders']
            or actual['items_after_loader'] != record['items_after_loader']):
        raise ValueError('train probe loader counts changed')
    return record


def pilot():
    check()
    base_J = baseline_score('train')
    probe = prepare_train_probe()
    tree = Node('feature','delta_distance_km')
    gp = invoke('train_probe', 'gp', RUN/'pilot'/'train_probe', tree)
    write(RUN/'pilot'/'train_probe_summary.json', dict(status='DIAGNOSTIC_ONLY',
          baseline_train_J=str(base_J), probe_orders=probe['original_orders'],
          probe_J=gp['J'], probe_wall_seconds=gp['wall_seconds'],
          probe_decision_wall_seconds=gp['decision_wall_seconds_total'],
          probe_peak_job_memory_bytes=read(RUN/'pilot/train_probe/supervision/supervision.json').get('peak_job_memory_bytes'),
          upper_bound_evaluations=CONFIG['population']*(CONFIG['additional_generations']+1),
          workers=CONFIG['workers'],
          note='Probe J is not a train fitness or replacement for full-train GP timing.'))
    print('TRAIN PROBE PASS: review train_probe_summary.json before scheduling full training')


def initial_population():
    rng = random.Random(CONFIG['gp_seed'])
    population = []
    fallback = 0
    for index in range(CONFIG['population']):
        target = CONFIG['initial_depths'][index % 3]
        full = index % 2 == 0
        for attempt in range(100):
            tree = random_tree(rng, target, full=full)
            try:
                _, depth = validate_tree(tree, LIMITS)
                if depth == target:
                    break
            except ValueError:
                pass
        else:
            tree = random_tree(rng, target, full=True)
            fallback += 1
        population.append(tree)
    return rng, population, fallback


def breed(rng, evaluated):
    ranked = sorted(evaluated, key=lambda x:(not x['valid'], x['fitness'], x['nodes'], x['hash']))
    def select():
        return min((rng.choice(ranked) for _ in range(CONFIG['tournament'])),
                   key=lambda x:(not x['valid'], x['fitness'], x['nodes'], x['hash']))['tree']
    new = [x['tree'] for x in ranked[:CONFIG['elitism']]]
    fallback = 0
    while len(new) < CONFIG['population']:
        parent = select()
        draw = rng.random()
        if draw < .70:
            child = crossover(rng, parent, select(), LIMITS)
        elif draw < .95:
            child = mutate(rng, parent, LIMITS)
        else:
            child = parent
        validate_tree(child, LIMITS)
        fallback += child is parent and draw < .95
        new.append(child)
    return new, fallback


def train():
    started = time.perf_counter()
    check()
    denominator = baseline_score('train')  # fail before creating training directory or launching anything
    out = RUN/'training'
    out.mkdir(parents=True, exist_ok=False)
    write(out/'config_snapshot.json', dict(config=settings(), baseline_train_J=denominator,
                                           baseline_audit_sha256=sha(RUN/'baseline/train/audit.json'),
                                           manifest_sha256=sha(RUN/'split_manifest.json')))
    rng, population, initial_fallback = initial_population()
    cache = {}
    candidates = {}
    request_count = hits = 0
    for generation in range(CONFIG['additional_generations']+1):
        members = []
        tasks = []
        for index, tree in enumerate(population):
            h = tree_hash(tree)
            context = runtime_context('train', tree)
            key = hashlib.sha256(json.dumps(context,sort_keys=True).encode()).hexdigest()
            request_count += 1
            if key in cache:
                hits += 1
                prior = cache[key]
                fresh = audited(prior['run_directory'], prior['supervision_directory'], 'train', 'gp', tree)
                if fresh['J'] != prior['J']:
                    raise ValueError('cache hit rescore changed')
                members.append((index,tree,h,key,fresh,True))
            else:
                tasks.append((index,tree,h,key))
        def evaluate(task):
            index,tree,h,key = task
            folder = out/'evaluations'/f'g{generation:02d}_i{index:02d}_{h[:12]}'
            try:
                result = invoke('train','gp',folder,tree)
            except ValueError:
                result = read(folder/'audit.json')
            return index,tree,h,key,result,False
        with ThreadPoolExecutor(max_workers=CONFIG['workers']) as pool:
            members.extend(pool.map(evaluate, tasks))
        evaluated = []
        for index,tree,h,key,result,hit in sorted(members):
            valid = bool(result.get('valid'))
            if valid:
                cache[key] = result
            nodes,depth = validate_tree(tree,LIMITS)
            evaluated.append(dict(index=index, tree=tree, hash=h, nodes=nodes, depth=depth,
                                  fitness=float(result['J'])/denominator if valid else PENALTY,
                                  valid=valid, observed_J=result.get('J'),
                                  invalid_reason=result.get('invalid_reason'), cache_hit=hit,
                                  run_directory=result.get('run_directory')))
        valid_rows = [x for x in evaluated if x['valid']]
        best = min(valid_rows, key=lambda x:(x['fitness'],x['nodes'],x['hash'])) if valid_rows else None
        if best:
            candidates.setdefault(best['hash'], dict(first_generation=generation,
                                tree=best['tree'].data(), expression=best['tree'].text(),
                                tree_sha256=best['hash'], nodes=best['nodes'], train_J=best['observed_J'],
                                train_fitness=best['fitness'],
                                train_run_directory=best['run_directory']))
        record = dict(generation=generation, population_size=len(evaluated),
                      valid_count=len(valid_rows), best_tree_sha256=best['hash'] if best else None,
                      fallback_initial=initial_fallback if generation==0 else 0,
                      requests=request_count, cache_hits=hits,
                      members=[{k:v for k,v in x.items() if k!='tree'} | {'tree':x['tree'].data()} for x in evaluated])
        write(out/'generations'/f'g{generation:02d}.json', record)
        print(f'G{generation}: valid={len(valid_rows)}/50 requests={request_count} cache_hits={hits}',flush=True)
        if not best:
            raise ValueError(f'G{generation} has no valid tree; training incomplete')
        if generation < CONFIG['additional_generations']:
            population,fallback = breed(rng,evaluated)
            write(out/'generations'/f'g{generation:02d}_breed.json',dict(fallback_to_parent=fallback,
                  next_population_hashes=[tree_hash(tree) for tree in population]))
    write(out/'candidates.json', list(candidates.values()))
    write(out/'complete.json', dict(status='COMPLETE', generations=21,
                                    evaluation_requests=request_count, cache_hits=hits,
                                    new_rollouts=request_count-hits, candidates=len(candidates),
                                    offline_training_wall_seconds=time.perf_counter()-started))


def validation():
    check()
    if read(RUN/'training/complete.json').get('status') != 'COMPLETE':
        raise ValueError('training is incomplete')
    baseline_score('validation')
    candidates = read(RUN/'training/candidates.json')
    if not 1 <= len(candidates) <= 21:
        raise ValueError('candidate set invalid')
    out = RUN/'validation'
    out.mkdir(parents=True, exist_ok=False)
    results = []
    for index, candidate in enumerate(candidates):
        tree = parse_node(candidate['tree'])
        try:
            result = invoke('validation','gp',out/f'candidate_{index:02d}_{tree_hash(tree)[:12]}',tree)
        except ValueError:
            result = read(out/f'candidate_{index:02d}_{tree_hash(tree)[:12]}'/'audit.json')
        results.append(dict(candidate=candidate, result=result))
        print(f'validation candidate {index+1}/{len(candidates)} valid={result["valid"]}',flush=True)
    write(out/'results.json', results)
    valid = [x for x in results if x['result']['valid']]
    if not valid:
        raise ValueError('all validation candidates invalid; no tree selected')
    winner = select_candidate(valid)
    tree = parse_node(winner['candidate']['tree'])
    save_tree(RUN/'final_tree.json',tree,training=dict(selection_split='validation',
              validation_J=winner['result']['J'], train_J=winner['candidate']['train_J'],
              candidate_set_sha256=sha(out/'results.json')),limits=LIMITS)
    write(out/'selection.json',dict(status='LOCKED', tree_sha256=tree_hash(tree),
                                   validation_J=winner['result']['J'], nodes=winner['candidate']['nodes'],
                                   selected_train_run_directory=winner['candidate']['train_run_directory'],
                                   selected_run_directory=winner['result']['run_directory'],
                                   selected_supervision_directory=winner['result']['supervision_directory'],
                                   final_tree_file_sha256=sha(RUN/'final_tree.json')))


def select_candidate(valid_rows):
    """Selection reads audited validation J, nodes and hash only."""
    eligible = [x for x in valid_rows if x['result'].get('valid')]
    if not eligible:
        raise ValueError('no valid validation candidate')
    return min(eligible,key=lambda x:(float(x['result']['J']),x['candidate']['nodes'],
                                      x['candidate']['tree_sha256']))


def final_test():
    check()
    baseline_score('test')
    selection = read(RUN/'validation/selection.json')
    if selection['status'] != 'LOCKED' or selection['final_tree_file_sha256'] != sha(RUN/'final_tree.json'):
        raise ValueError('final tree not locked or changed')
    from dpdp_gp import load_tree
    tree,_ = load_tree(RUN/'final_tree.json')
    if tree_hash(tree) != selection['tree_sha256']:
        raise ValueError('final tree hash mismatch')
    result = invoke('test','gp',RUN/'final_test',tree)
    print(f'FINAL TEST audited J={result["J"]}')


def reaudit():
    check()
    required = [RUN/'baseline'/split/'audit.json' for split in SPLITS]
    required += [RUN/'training/complete.json', RUN/'validation/selection.json', RUN/'final_test/audit.json']
    if any(not path.is_file() for path in required):
        raise ValueError('final re-audit requires all three baselines, complete training, selection and final test')
    for split in SPLITS:
        location = RUN/'baseline'/split
        if location.exists():
            fresh = audited(location/'run',location/'supervision',split,'vnsme')
            if fresh['J'] != read(location/'audit.json')['J']:
                raise ValueError(f'{split} baseline rescore changed')
    from dpdp_gp import load_tree
    if (RUN/'training/complete.json').exists():
        for path in (RUN/'training/evaluations').glob('*/audit.json'):
            old=read(path)
            if not old.get('valid'):
                continue
            tree,_=load_tree(path.parent/'model.json')
            fresh=audited(path.parent/'run',path.parent/'supervision','train','gp',tree)
            if fresh['J'] != old['J']:
                raise ValueError(f'training rescore changed: {path}')
    for path in (RUN/'validation').glob('candidate_*/audit.json'):
        old=read(path)
        if not old.get('valid'):
            continue
        tree,_=load_tree(path.parent/'model.json')
        fresh=audited(path.parent/'run',path.parent/'supervision','validation','gp',tree)
        if fresh['J'] != old['J']:
            raise ValueError(f'validation rescore changed: {path}')
    for split, location in [('test',RUN/'final_test')]:
        if location.exists():
            tree,_=load_tree(RUN/'final_tree.json')
            fresh=audited(location/'run',location/'supervision',split,'gp',tree)
            if fresh['J'] != read(location/'audit.json')['J']:
                raise ValueError('final test rescore changed')
    print('REAUDIT PASS for existing valid baseline, train, validation and test artifacts')


def report():
    manifest = read(RUN/'split_manifest.json')
    lines = ['# Instance 64 temporal experiment', '',
             'Same Huawei instance, independent resets per temporal split; no continuous-day operation.', '',
             '| Split | Method | J | Distance / vehicle (km) | Tardiness (s) | Penalty | Completed/unfinished original orders | Rollout wall (s) | Online decision wall (s) | Audit |',
             '|---|---|---:|---:|---:|---:|---|---:|---:|---|']
    selection = read(RUN/'validation/selection.json') if (RUN/'validation/selection.json').exists() else {}
    candidates = read(RUN/'training/candidates.json') if (RUN/'training/candidates.json').exists() else []
    train_best = min(candidates,key=lambda x:(x['train_fitness'],x['nodes'],x['tree_sha256'])) if candidates else None
    gp_train_run = selection.get('selected_train_run_directory') if selection else None
    if not gp_train_run and train_best:
        gp_train_run = train_best['train_run_directory']
    gp_locations = dict(train=Path(gp_train_run).parent/'audit.json' if gp_train_run else None,
                        validation=Path(selection['selected_run_directory']).parent/'audit.json'
                        if selection else None, test=RUN/'final_test/audit.json')
    for split in SPLITS:
        for label, location in [('VNSME',RUN/'baseline'/split/'audit.json'), ('GP',gp_locations[split])]:
            data = read(location) if location and location.exists() else {}
            score = data.get('score') or {}
            j = data['J'] if data.get('valid') else 'INVALID' if data else 'NOT RUN'
            audit_status = data.get('independent_audit',{}).get('status','INVALID' if data else 'NOT RUN')
            lines.append(f"| {split} | {label} | {j} | {score.get('average_distance_km','')} | {score.get('total_tardiness_seconds','')} | {score.get('tardiness_penalty','')} | {data.get('completed_original_orders','')}/{data.get('unfinished_original_orders','')} | {data.get('wall_seconds','')} | {data.get('decision_wall_seconds_total','')} | {audit_status} |")
    training = read(RUN/'training/complete.json') if (RUN/'training/complete.json').exists() else {}
    lines += ['', 'J = total_distance_km / 100 + total_tardiness_seconds × 10000 / 3600.',
              'Training uses J_train / positive audited VNSME J_train. Selection uses validation J only.',
              f"GP offline training wall seconds: {training.get('offline_training_wall_seconds','NOT RUN')}.",
              f"Train evaluation requests/cache hits/new rollouts: {training.get('evaluation_requests','NOT RUN')}/{training.get('cache_hits','NOT RUN')}/{training.get('new_rollouts','NOT RUN')}.",
              'Scope: another temporal interval of the same instance_64 with reset state.', '',
              f"Split manifest SHA-256: {sha(RUN/'split_manifest.json')}",
              f"Source orders: {manifest['source_sha256']['orders']}"]
    (RUN/'REPORT.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(RUN/'REPORT.md')


def main(argv=None):
    global RUN
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run-id',default=CONFIG['run_id'],
                   help='new identifier for a fresh, non-resumed attempt')
    sub=p.add_subparsers(dest='action',required=True)
    for name in ('prepare','check','pilot','train','validation','test','audit','report'):
        sub.add_parser(name)
    b=sub.add_parser('baseline')
    b.add_argument('--split',choices=SPLITS,required=True)
    args=p.parse_args(argv)
    if not re.fullmatch(r'instance64_temporal_60_20_20_seed42_r[0-9]{2,}',args.run_id):
        p.error('--run-id must match instance64_temporal_60_20_20_seed42_rNN')
    RUN = ROOT/'gp_runs'/args.run_id
    if Path(sys.executable).resolve() != (ROOT/'.venv/Scripts/python.exe').resolve():
        p.error('use ./.venv/Scripts/python.exe from dvrpsim')
    actions=dict(prepare=prepare,check=check,pilot=pilot,train=train,
                 validation=validation,test=final_test,audit=reaudit,report=report)
    if args.action == 'baseline':
        baseline(args.split)
    else:
        actions[args.action]()


if __name__=='__main__':
    raise SystemExit(main())
