"""Locked GP evolution and fresh future-holdout evaluation for reduced instance 35."""
import csv
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import math
from pathlib import Path
import random
import shutil
import subprocess
import sys
import time

from dpdp_dataset import seconds
from dpdp_gp import (FEATURES, Limits, breed, canonical, initial_population,
                     load_tree, save_tree, tree_hash, validate_tree)
from dpdp_insertion import split_observed_orders
from instance35_reduced_experiment import ROOT, BENCHMARK, SOURCE, VEHICLES, FACTORIES, ROUTES, run_rollout

EXPERIMENT = ROOT/'gp_runs/instance35_gp_evolution_futureholdout_20261118_r03'
TRAINING_RUN_ID = 'gp_evolution_8x3_20261118_03'
CONTIGUOUS_EXPERIMENT = ROOT/'gp_runs/instance35_gp_evolution_contiguous_future_20261118_r04'
CONTIGUOUS_TRAINING_RUN_ID = 'gp_evolution_4x3_20261118_04'
REUSE_SOURCE_EXPERIMENTS = (
    ROOT/'gp_runs/instance35_gp_evolution_futureholdout_20261118_r01',
    ROOT/'gp_runs/instance35_gp_evolution_futureholdout_20261118_r02',
)
REUSE_FIXED_GP_RUN_ID = 'gp_evolution_8x3_20261118_01_g0_m00_train'
REUSE_VNSME_TRAIN_RUN_ID = 'gp_evolution_8x3_20261118_01_vnsme_train'
PRIOR_GP_TRAIN_RUNS = (
    (REUSE_SOURCE_EXPERIMENTS[0],REUSE_FIXED_GP_RUN_ID),
    (REUSE_SOURCE_EXPERIMENTS[1],'gp_evolution_8x3_20261118_02_g0_m01_train'),
    (REUSE_SOURCE_EXPERIMENTS[1],'gp_evolution_8x3_20261118_02_g0_m02_train'),
)
KNOWN_FAILED_TREE_HASHES = {
    '8d90a6d3f77c60fc38cd139e9724d0ed294635ba2773972b276003fa3348f91e':
        dict(source_experiment='gp_runs/instance35_gp_evolution_futureholdout_20261118_r02',
             run_id='gp_evolution_8x3_20261118_02_g0_m03_train',
             reason='DECISION_TIMEOUT at decision 5, simulation_seconds=2400; J=null; not retried'),
}
TRAINING_SEED = 20261118
SIMULATOR_SEED = 0
TIME_SLOT_SECONDS = 600
TRAIN_FRACTION_END = Decimal('0.108')
VALIDATION_FRACTION_START = Decimal('0.18')
VALIDATION_FRACTION_END = Decimal('0.20')
TEST_FRACTION_END = Decimal('0.25')
POPULATION_SIZE = 8
GENERATION_COUNT = 3  # G0, G1, G2; two breeding transitions.
VALIDATION_CANDIDATE_COUNT = 3
SUPERVISOR_SECONDS = 300
RUNNER_GUARD_SECONDS = 360
DECISION_SECONDS = 60
VNSME_SEARCH_SECONDS = 50
VNSME_SUBPROCESS_SECONDS = 59
SIMULATION_HORIZON_SECONDS = 604800
CONTRACT_VERSION = 'dpdp-execution-commitment-v3'


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_exclusive(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8', newline='\n') as handle:
        json.dump(value, handle, indent=2, sort_keys=True, ensure_ascii=False,
                  default=str, allow_nan=False)
        handle.write('\n')
        handle.flush()


def append_durable(path, value):
    with Path(path).open('a', encoding='utf-8', newline='\n') as handle:
        handle.write(json.dumps(value, sort_keys=True, default=str, allow_nan=False)+'\n')
        handle.flush()
        import os
        os.fsync(handle.fileno())


def _make_items(rows):
    from types import SimpleNamespace
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
    return items


def _partition_summary(name, rows, folder):
    times = [seconds(row['creation_time']) for row in rows]
    items = _make_items(rows)
    groups = split_observed_orders(items, 15)
    slacks = []
    demand = {}
    slot_counts = {}
    for row, release in zip(rows, times):
        due = seconds(row['committed_completion_time'])
        if due < release:
            due += 86400
        slacks.append(due-release)
        demand[row['demand']] = demand.get(row['demand'], 0)+1
        slot = release//TIME_SLOT_SECONDS
        slot_counts[slot] = slot_counts.get(slot, 0)+1
    slacks.sort()
    return dict(name=name, original_orders=len(rows), item_count=len(items),
        post_lot_groups_static=len(groups), vehicle_count=50,
        first_release_seconds=min(times), last_release_seconds=max(times),
        occupied_slot_count=len(slot_counts),
        occupied_original_600s_slots=sorted(slot_counts),
        orders_per_slot=dict(min=min(slot_counts.values()),
            median=__import__('statistics').median(slot_counts.values()),
            p95=sorted(slot_counts.values())[math.ceil(.95*len(slot_counts))-1],
            max=max(slot_counts.values())),
        demand_distribution=dict(sorted(demand.items(), key=lambda x: float(x[0]))),
        deadline_slack_seconds=dict(min=min(slacks), median=__import__('statistics').median(slacks),
            p95=slacks[math.ceil(.95*len(slacks))-1], max=max(slacks)),
        orders_sha256=digest(folder/'orders.csv'),
        vehicles_sha256=digest(folder/'vehicle_info_50.csv'))


def prepare(experiment_dir=EXPERIMENT):
    experiment_dir = Path(experiment_dir).resolve()
    if experiment_dir.exists():
        raise FileExistsError(f'preserving existing experiment namespace: {experiment_dir}')
    source_rows = list(csv.DictReader(SOURCE.open(encoding='utf-8-sig', newline='')))
    if len(source_rows) != 1000 or len({row['order_id'] for row in source_rows}) != 1000:
        raise ValueError('source must contain exactly 1000 unique orders')
    vehicle_rows = list(csv.DictReader(VEHICLES.open(encoding='utf-8-sig', newline='')))
    if len(vehicle_rows) != 50:
        raise ValueError('source fleet must contain exactly 50 vehicles')
    releases = [seconds(row['creation_time']) for row in source_rows]
    source_start, source_end = min(releases), max(releases)
    span = Decimal(source_end-source_start)
    boundaries = {
        'train_end_exclusive': Decimal(source_start)+span*TRAIN_FRACTION_END,
        'validation_start_inclusive': Decimal(source_start)+span*VALIDATION_FRACTION_START,
        'validation_end_exclusive': Decimal(source_start)+span*VALIDATION_FRACTION_END,
        'test_end_exclusive': Decimal(source_start)+span*TEST_FRACTION_END,
    }
    partitions = {'train': [], 'validation': [], 'test': []}
    excluded_gap = []
    outside = []
    for row, release in zip(source_rows, releases):
        t = Decimal(release)
        if t < boundaries['train_end_exclusive']:
            partitions['train'].append(row)
        elif t < boundaries['validation_start_inclusive']:
            excluded_gap.append(row)
        elif t < boundaries['validation_end_exclusive']:
            partitions['validation'].append(row)
        elif t < boundaries['test_end_exclusive']:
            partitions['test'].append(row)
        else:
            outside.append(row)
    if any(not partitions[name] for name in partitions):
        raise ValueError('locked temporal partition is empty')
    owner = {}
    for name, rows in partitions.items():
        for row in rows:
            release = seconds(row['creation_time'])
            previous = owner.setdefault(release, name)
            if previous != name:
                raise ValueError(f'release tie split across partitions at {release}')
    all_assigned = [row['order_id'] for rows in partitions.values() for row in rows]
    if len(all_assigned) != len(set(all_assigned)):
        raise ValueError('partition contains duplicate order ids')

    experiment_dir.mkdir(parents=True, exist_ok=False)
    (experiment_dir/'data').mkdir()
    (experiment_dir/'trees').mkdir()
    old_scope = ROOT/'gp_runs/instance35_reducedscope_20261118_window45_15587_r02'
    fixed_tree_source = old_scope/'trees/fixed_gp_tree.json'
    fixed_tree, fixed_payload = load_tree(fixed_tree_source)
    shutil.copyfile(fixed_tree_source, experiment_dir/'trees/fixed_gp_tree.json')
    summaries = {}
    for name, rows in partitions.items():
        folder = experiment_dir/'data'/name
        folder.mkdir()
        with (folder/'orders.csv').open('x', encoding='utf-8', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=list(source_rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        shutil.copyfile(VEHICLES, folder/'vehicle_info_50.csv')
        summaries[name] = _partition_summary(name, rows, folder)
    source_hashes = {
        'orders_1000_3': digest(SOURCE), 'vehicle_info_50': digest(VEHICLES),
        'factory_info': digest(FACTORIES), 'route_info': digest(ROUTES),
    }
    code_files = ('dpdp_dataset.py', 'dpdp_gp.py', 'dpdp_insertion.py', 'dpdp_feasibility.py',
        'dpdp_v3_supervisor.py', 'examples/case_studies/dpdp/dpdp_routing.py',
        'run_dpdp_insertion.py', 'verify_dpdp_score.py', 'src/baselines/vnsme.py',
        'third_party/vnsme/original/main_algorithm.java', 'build_vnsme.py',
        'instance35_reduced_experiment.py', 'instance35_gp_evolution.py')
    config = dict(schema='instance35-gp-evolution-future-holdout-v1',
        scope_label='REDUCED_SCOPE_EXPLORATORY_NOT_FULL_INSTANCE_35',
        source_sha256=source_hashes,
        source_revision=subprocess.check_output(['git','rev-parse','HEAD'], cwd=ROOT, text=True).strip(),
        source_window=dict(first_release_seconds=source_start, last_release_seconds=source_end,
                           release_span_seconds=source_end-source_start),
        temporal_protocol=dict(
            fractions_are_of_full_source_release_span=True,
            intervals=dict(train=f'[source_start, {boundaries["train_end_exclusive"]})',
                excluded_gap=f'[{boundaries["train_end_exclusive"]}, {boundaries["validation_start_inclusive"]})',
                validation=f'[{boundaries["validation_start_inclusive"]}, {boundaries["validation_end_exclusive"]})',
                test=f'[{boundaries["validation_end_exclusive"]}, {boundaries["test_end_exclusive"]})'),
            boundary_seconds={k:str(v) for k,v in boundaries.items()},
            train_end_fraction=str(TRAIN_FRACTION_END),
            validation_fractions=[str(VALIDATION_FRACTION_START),str(VALIDATION_FRACTION_END)],
            test_fractions=[str(VALIDATION_FRACTION_END),str(TEST_FRACTION_END)],
            release_ties='same exact release second is assigned wholly to one interval',
            gap_orders_excluded=len(excluded_gap), outside_orders_excluded=len(outside),
            partitions_are_independent_rollouts=True, reset_fleet_each_partition=True,
            carry_over_orders=False, time_slot_seconds=TIME_SLOT_SECONDS,
            note='Train reuses only the prior 0–10.8% train interval; old 10.8–18% validation/test interval is excluded. This is not a 60/20/20 split.'),
        partitions=summaries,
        execution=dict(simulator_seed=SIMULATOR_SEED,
            supervisor_wall_seconds=SUPERVISOR_SECONDS,
            runner_wall_guard_seconds=RUNNER_GUARD_SECONDS,
            decision_hard_timeout_seconds=DECISION_SECONDS,
            simulation_horizon_seconds=SIMULATION_HORIZON_SECONDS,
            dispatch_step_seconds=TIME_SLOT_SECONDS,
            vnsme_internal_search_budget_seconds=VNSME_SEARCH_SECONDS,
            vnsme_subprocess_hard_timeout_seconds=VNSME_SUBPROCESS_SECONDS,
            contract_version=CONTRACT_VERSION,
            timeout_policy='No retry. Timeout/error => incomplete, J=null. Same stage and decision hard limits for GP/VNSME; VNSME additionally has 50s cooperative internal search budget, so no equal-compute claim.'),
        tree=dict(path='trees/fixed_gp_tree.json', tree_sha256=tree_hash(fixed_tree),
                  expression=fixed_payload['expression'], source_artifact=str(fixed_tree_source.relative_to(ROOT))),
        objective='run_dpdp_insertion and independent verify_dpdp_score.py total_score; only complete valid contract receives J',
        code_sha256={name:digest(ROOT/name) for name in code_files},
        prepared_at_utc=datetime.now(timezone.utc).isoformat())
    config_bytes=json.dumps(config,sort_keys=True,separators=(',',':'),ensure_ascii=False,
                            allow_nan=False,default=str).encode()
    config['config_sha256']=hashlib.sha256(config_bytes).hexdigest()
    write_exclusive(experiment_dir/'experiment_config.json',config)
    protocol=dict(schema='instance35-gp-training-protocol-v1',
        protocol_locked_before_new_rollouts=True,
        namespace=str(experiment_dir.relative_to(ROOT)), run_id=TRAINING_RUN_ID,
        data_config_sha256=config['config_sha256'], source_sha256=source_hashes,
        partition_hashes={k:v['orders_sha256'] for k,v in summaries.items()},
        temporal_protocol=config['temporal_protocol'],
        gp=dict(population_size=POPULATION_SIZE, generation_count=GENERATION_COUNT,
            generations=['G0','G1','G2'], breeding_transitions=2,
            evolution_seed=TRAINING_SEED, simulator_seed=SIMULATOR_SEED,
            features=list(FEATURES), primitives=['+','-','*','/'],
            tree_limits=dict(max_depth=Limits().max_depth,max_nodes=Limits().max_nodes),
            operators=dict(initial_population='dpdp_gp.initial_population',
                breeding='dpdp_gp.breed',tournament=3,crossover_rate=.8,
                mutation_rate=.3,elitism=1),
            deduplication='global across G0–G2 using dpdp_gp.canonical and SHA-256 tree_hash; duplicate reuses only its completed Train fitness and cannot count as a distinct Validation candidate',
            train_eligibility='completed runner result, valid=True, contract_complete=True, matching independent J, supervisor EXITED/0, valid supervision and empty Job Object only',
            failure_policy='each tree hash is attempted at most once; timeout/error is recorded with J=null, excluded from fitness and parent/validation pools, and never retried; finish each generation after all members are attempted; proceed only when at least two distinct valid trees remain in that generation; otherwise stop incomplete',
            validation_candidate_count=VALIDATION_CANDIDATE_COUNT,
            validation_pool='up to three unique tree hashes ranked by Train J, then node count, then canonical tree; fixed before any Validation result',
            selection='minimum Validation J; ties by Train J, node count, canonical tree'),
        evaluation=dict(time_slot_seconds=TIME_SLOT_SECONDS, rollout_supervisor_wall_seconds=SUPERVISOR_SECONDS,
            runner_wall_guard_seconds=RUNNER_GUARD_SECONDS,
            decision_hard_timeout_seconds=DECISION_SECONDS,
            vnsme_internal_search_budget_seconds=VNSME_SEARCH_SECONDS,
            vnsme_subprocess_hard_timeout_seconds=VNSME_SUBPROCESS_SECONDS,
            no_retry=True, partial_j='null',
            fixed_tree_and_vnsme_train='reuse only the two listed completed supervised Train artifacts after full provenance/audit checks; fixed GP Train is G0 member 0',
            holdout='after writing selected_tree.json and selection_decision.json, run selected GP once and VNSME once on the new 20–25% temporal holdout, seed 0 and reset fleet'),
        exclusions=['Do not access the old 14.4–18% Test result or J for any scope, tree, parameter, or budget choice.',
                    'This reduced-scope study is exploratory and is not full instance 35.'],
        prior_rollout_reuse=dict(source_experiments=[str(x.relative_to(ROOT)) for x in REUSE_SOURCE_EXPERIMENTS],
            verified_gp_train_runs=[dict(experiment=str(root.relative_to(ROOT)),run_id=rid)
                                    for root,rid in PRIOR_GP_TRAIN_RUNS],
            verified_vnsme_train_run=dict(experiment=str(REUSE_SOURCE_EXPERIMENTS[0].relative_to(ROOT)),
                                          run_id=REUSE_VNSME_TRAIN_RUN_ID),
            reuse_only_if='same exact dataset/fleet hashes, seed, applied timeout values, contract, tree hash where applicable, matching independent J, complete trace, clean supervisor/Job Object, identical simulator/scorer/algorithm code hashes; controller hash may differ because run-level artifacts are independently revalidated.'),
        prior_failed_candidates=KNOWN_FAILED_TREE_HASHES,
        controller_revision='r03 fixes the post-rollout G0/M0 cache-key error and excludes timed-out/invalid trees without retry; prior incomplete controller artifacts remain preserved and are not results.')
    protocol['protocol_sha256']=hashlib.sha256(json.dumps(protocol,sort_keys=True,separators=(',',':'),
        ensure_ascii=False,allow_nan=False,default=str).encode()).hexdigest()
    write_exclusive(experiment_dir/'training_protocol.json',protocol)
    return config, protocol


def prepare_contiguous(experiment_dir=CONTIGUOUS_EXPERIMENT, run_id=CONTIGUOUS_TRAINING_RUN_ID,
                       start_fraction=Decimal('0.18'), end_fraction=Decimal('0.385'),
                       population_size=4, generation_count=3, validation_candidate_count=3):
    """Lock a fresh contiguous temporal window after the previously exposed interval."""
    experiment_dir=Path(experiment_dir).resolve()
    if experiment_dir.exists():
        raise FileExistsError(f'preserving existing experiment namespace: {experiment_dir}')
    start_fraction,end_fraction=Decimal(start_fraction),Decimal(end_fraction)
    if not (Decimal(0)<=start_fraction<end_fraction<=Decimal(1)):
        raise ValueError('invalid contiguous source-window fractions')
    if population_size<3 or generation_count<2 or validation_candidate_count<2:
        raise ValueError('training needs population>=3, generations>=2, validation candidates>=2')
    with SOURCE.open(encoding='utf-8-sig',newline='') as handle:
        source_rows=list(csv.DictReader(handle))
    if len(source_rows)!=1000 or len({r['order_id'] for r in source_rows})!=1000:
        raise ValueError('source must contain exactly 1000 unique orders')
    with VEHICLES.open(encoding='utf-8-sig',newline='') as handle:
        vehicle_rows=list(csv.DictReader(handle))
    if len(vehicle_rows)!=50:
        raise ValueError('source fleet must contain exactly 50 vehicles')
    releases=[seconds(r['creation_time']) for r in source_rows]
    source_start,source_end=min(releases),max(releases)
    span=Decimal(source_end-source_start)
    window_start=Decimal(source_start)+span*start_fraction
    window_end=Decimal(source_start)+span*end_fraction
    train_end=window_start+(window_end-window_start)*Decimal('0.60')
    validation_end=window_start+(window_end-window_start)*Decimal('0.80')
    bounds=dict(window_start_inclusive=window_start,train_end_exclusive=train_end,
        validation_end_exclusive=validation_end,window_end_exclusive=window_end)
    partitions={name:[] for name in ('train','validation','test')}
    outside=[]
    for row,release in zip(source_rows,releases):
        t=Decimal(release)
        if t<window_start or t>=window_end:
            outside.append(row)
        elif t<train_end:
            partitions['train'].append(row)
        elif t<validation_end:
            partitions['validation'].append(row)
        else:
            partitions['test'].append(row)
    if any(not partitions[name] for name in partitions):
        raise ValueError('contiguous window produced an empty partition')
    owner={}
    for name,rows in partitions.items():
        for row in rows:
            release=seconds(row['creation_time'])
            previous=owner.setdefault(release,name)
            if previous!=name:
                raise ValueError(f'release tie split across partitions at {release}')
    selected=[r['order_id'] for values in partitions.values() for r in values]
    if len(selected)!=len(set(selected)):
        raise ValueError('duplicate order ID in contiguous partitions')
    if not (100<=len(partitions['train'])<=150 and
            len(partitions['validation'])>=20 and len(partitions['test'])>=20):
        raise ValueError('selected window misses locked order-count requirements')

    experiment_dir.mkdir(parents=True,exist_ok=False)
    (experiment_dir/'data').mkdir()
    (experiment_dir/'trees').mkdir()
    fixed_tree_source=ROOT/'gp_runs/instance35_reducedscope_20261118_window45_15587_r02/trees/fixed_gp_tree.json'
    fixed_tree,fixed_payload=load_tree(fixed_tree_source)
    shutil.copyfile(fixed_tree_source,experiment_dir/'trees/fixed_gp_tree.json')
    summaries={}
    for name,rows in partitions.items():
        folder=experiment_dir/'data'/name
        folder.mkdir()
        with (folder/'orders.csv').open('x',encoding='utf-8',newline='') as handle:
            writer=csv.DictWriter(handle,fieldnames=list(source_rows[0]))
            writer.writeheader(); writer.writerows(rows)
        shutil.copyfile(VEHICLES,folder/'vehicle_info_50.csv')
        summaries[name]=_partition_summary(name,rows,folder)
    source_hashes=dict(orders_1000_3=digest(SOURCE),vehicle_info_50=digest(VEHICLES),
        factory_info=digest(FACTORIES),route_info=digest(ROUTES))
    code_files=('dpdp_dataset.py','dpdp_gp.py','dpdp_insertion.py','dpdp_feasibility.py',
        'dpdp_v3_supervisor.py','examples/case_studies/dpdp/dpdp_routing.py',
        'run_dpdp_insertion.py','verify_dpdp_score.py','src/baselines/vnsme.py',
        'third_party/vnsme/original/main_algorithm.java','build_vnsme.py',
        'instance35_reduced_experiment.py','instance35_gp_evolution.py')
    intervals=dict(train=f'[{window_start}, {train_end})',
        validation=f'[{train_end}, {validation_end})',test=f'[{validation_end}, {window_end})')
    temporal=dict(fractions_are_of_full_source_release_span=True,
        window_start_fraction=str(start_fraction),window_end_fraction=str(end_fraction),
        intervals=intervals,boundary_seconds={k:str(v) for k,v in bounds.items()},
        train_ratio='0.60',validation_ratio='0.20',test_ratio='0.20',
        release_ties='same exact creation_time is assigned wholly to one interval',
        partitions_are_independent_rollouts=True,reset_fleet_each_partition=True,
        carry_over_orders=False,time_slot_seconds=TIME_SLOT_SECONDS,
        excluded_orders_outside_window=len(outside),
        scope_selection_rule=('Start at 18% of source release span, after the historical 0-18% exposed scope. '
            'Scan end fractions in 0.5 percentage-point increments; choose the earliest with 100-150 Train '
            'orders and at least 20 orders in each later partition. Selection uses only release times/counts, '
            'before any J from this namespace.'))
    execution=dict(simulator_seed=SIMULATOR_SEED,supervisor_wall_seconds=SUPERVISOR_SECONDS,
        runner_wall_guard_seconds=RUNNER_GUARD_SECONDS,decision_hard_timeout_seconds=DECISION_SECONDS,
        simulation_horizon_seconds=SIMULATION_HORIZON_SECONDS,dispatch_step_seconds=TIME_SLOT_SECONDS,
        vnsme_internal_search_budget_seconds=VNSME_SEARCH_SECONDS,
        vnsme_subprocess_hard_timeout_seconds=VNSME_SUBPROCESS_SECONDS,
        contract_version=CONTRACT_VERSION,
        timeout_policy='No retry. Timeout/error => incomplete, J=null. GP/VNSME share stage and decision hard limits; VNSME additionally has 50s cooperative internal search, so compute is not equalized.')
    config=dict(schema='instance35-gp-evolution-contiguous-v1',
        scope_label='REDUCED_SCOPE_EXPLORATORY_NOT_FULL_INSTANCE_35',
        source_sha256=source_hashes,source_revision=subprocess.check_output(
            ['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        source_window=dict(first_release_seconds=source_start,last_release_seconds=source_end,
            release_span_seconds=source_end-source_start),temporal_protocol=temporal,
        partitions=summaries,execution=execution,
        tree=dict(path='trees/fixed_gp_tree.json',tree_sha256=tree_hash(fixed_tree),
            expression=fixed_payload['expression'],source_artifact=str(fixed_tree_source.relative_to(ROOT))),
        objective='run_dpdp_insertion and independent verify_dpdp_score.py total_score; only complete valid contract receives J',
        code_sha256={name:digest(ROOT/name) for name in code_files},
        prepared_at_utc=datetime.now(timezone.utc).isoformat())
    config['config_sha256']=hashlib.sha256(json.dumps(config,sort_keys=True,separators=(',',':'),
        ensure_ascii=False,allow_nan=False,default=str).encode()).hexdigest()
    write_exclusive(experiment_dir/'experiment_config.json',config)
    try: namespace=str(experiment_dir.relative_to(ROOT))
    except ValueError: namespace=str(experiment_dir)
    protocol=dict(schema='instance35-gp-training-protocol-v1',protocol_locked_before_new_rollouts=True,
        namespace=namespace,run_id=run_id,data_config_sha256=config['config_sha256'],
        source_sha256=source_hashes,partition_hashes={k:v['orders_sha256'] for k,v in summaries.items()},
        temporal_protocol=temporal,
        gp=dict(population_size=population_size,generation_count=generation_count,
            generations=[f'G{i}' for i in range(generation_count)],
            breeding_transitions=generation_count-1,evolution_seed=TRAINING_SEED,
            simulator_seed=SIMULATOR_SEED,features=list(FEATURES),primitives=['+','-','*','/'],
            tree_limits=dict(max_depth=Limits().max_depth,max_nodes=Limits().max_nodes),
            operators=dict(initial_population='dpdp_gp.initial_population',breeding='dpdp_gp.breed',
                tournament=3,crossover_rate=.8,mutation_rate=.3,elitism=1),
            deduplication='global across generations by canonical tree SHA-256; no duplicate counts as a new Validation candidate',
            train_eligibility='completed runner result, valid=True, complete contract, independent J match, supervisor EXITED/0, clean Job Object',
            failure_policy='each tree hash is attempted at most once; failures retain J=null, are excluded and never retried; every generation must retain at least two distinct valid trees',
            validation_candidate_count=validation_candidate_count,
            validation_pool=f'up to {validation_candidate_count} unique Train trees ranked by Train J then node count and canonical tree',
            selection='minimum independently audited Validation J; tie by Train J, node count, canonical tree'),
        evaluation=dict(time_slot_seconds=TIME_SLOT_SECONDS,rollout_supervisor_wall_seconds=SUPERVISOR_SECONDS,
            runner_wall_guard_seconds=RUNNER_GUARD_SECONDS,decision_hard_timeout_seconds=DECISION_SECONDS,
            vnsme_internal_search_budget_seconds=VNSME_SEARCH_SECONDS,
            vnsme_subprocess_hard_timeout_seconds=VNSME_SUBPROCESS_SECONDS,no_retry=True,partial_j='null',
            fixed_gp_and_vnsme_train='fresh completed Train rollouts before evolutionary selection; fixed GP is G0 member 0',
            holdout='after writing selection_decision.json, evaluate selected GP once and VNSME once on this fresh future Test; seed 0 and reset fleet'),
        prior_rollout_reuse=None,prior_failed_candidates={},
        exclusions=['No prior Train/Validation/Test rollout or J is reused. Historical [0%,18%) source interval is excluded from all three partitions.',
                    'Do not use any prior Test J to choose scope, trees, settings, or budget.',
                    'Exploratory reduced-scope result; not full instance 35.'])
    protocol['protocol_sha256']=hashlib.sha256(json.dumps(protocol,sort_keys=True,separators=(',',':'),
        ensure_ascii=False,allow_nan=False,default=str).encode()).hexdigest()
    write_exclusive(experiment_dir/'training_protocol.json',protocol)
    return config,protocol


def _read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def _complete(record):
    return (record.get('status')=='COMPLETED' and record.get('valid') is True
        and record.get('J') is not None and record.get('partial') is False
        and record.get('valid_supervision') is True
        and record.get('supervisor_state')=='EXITED'
        and record.get('supervisor_exit_code')==0
        and record.get('remaining_job_processes')==[])


def _rank_train(entry):
    return (Decimal(entry['train_J']), validate_tree(entry['tree'],Limits())[0], canonical(entry['tree']))


def _rank_validation(entry):
    return (Decimal(entry['validation_J']), Decimal(entry['train_J']),
            validate_tree(entry['tree'],Limits())[0], canonical(entry['tree']))


def _run_vnsme_train(protocol):
    return protocol.get('evaluation',{}).get('run_vnsme_train',True) is True


def _validation_candidate_count(protocol):
    gp=protocol.get('gp',{})
    evaluation=protocol.get('evaluation',{})
    return int(gp.get('validation_candidate_count',evaluation.get('validation_candidate_count',3)))


def verify_reusable_run(source_experiment, source_run_id, algorithm, partition,
                        config, expected_tree_hash=None):
    """Return a prior complete run only when all material provenance checks pass."""
    run_dir=Path(source_experiment)/'runs'/algorithm/partition/source_run_id
    try:
        stage=_read(run_dir/'stage_result.json')
        run_config=_read(run_dir/'run_config.json')
        runner_result=_read(run_dir/'runner/result.json')
        audit=_read(run_dir/'runner/independent_score.json')
        manifest=_read(run_dir/'runner/manifest.json')
        supervision=_read(run_dir/'supervisor/supervision.json')
    except (OSError,json.JSONDecodeError):
        return None
    expected=config['partitions'][partition]
    execution=config.get('execution',{})
    configured_supervisor=float(execution.get('supervisor_wall_seconds',SUPERVISOR_SECONDS))
    if not (_complete(stage)
            and run_config.get('algorithm')==algorithm
            and run_config.get('partition')==partition
            and run_config.get('experiment_config_sha256')==config.get('config_sha256')
            and run_config.get('dataset_sha256')==expected['orders_sha256']
            and run_config.get('vehicle_sha256')==expected['vehicles_sha256']
            and run_config.get('simulator_seed')==execution.get('simulator_seed',SIMULATOR_SEED)
            and run_config.get('configured_supervisor_wall_seconds',run_config.get('supervisor_wall_seconds'))==configured_supervisor
            and 0<float(run_config.get('supervisor_wall_seconds',0))<=configured_supervisor
            and run_config.get('runner_wall_guard_seconds')==execution.get('runner_wall_guard_seconds',RUNNER_GUARD_SECONDS)
            and run_config.get('decision_hard_timeout_seconds')==execution.get('decision_hard_timeout_seconds',DECISION_SECONDS)
            and run_config.get('task_deadline_utc')==execution.get('task_deadline_utc')
            and runner_result.get('status')=='COMPLETED'
            and runner_result.get('valid') is True
            and runner_result.get('contract_complete') is True
            and manifest.get('contract_version')==CONTRACT_VERSION
            and supervision.get('state')=='EXITED'
            and supervision.get('exit_code')==0
            and supervision.get('remaining_job_processes')==[]
            and str(stage.get('J'))==str(audit.get('total_score'))
            and str(runner_result.get('score',{}).get('total_score'))==str(audit.get('total_score'))):
        return None
    if algorithm=='gp' and manifest.get('gp_tree',{}).get('tree_sha256')!=expected_tree_hash:
        return None
    if algorithm=='vnsme':
        if (run_config.get('vnsme_internal_search_budget_seconds')!=execution.get('vnsme_internal_search_budget_seconds',VNSME_SEARCH_SECONDS)
                or run_config.get('vnsme_subprocess_hard_timeout_seconds')!=execution.get('vnsme_subprocess_hard_timeout_seconds',VNSME_SUBPROCESS_SECONDS)
                or run_config.get('vnsme_build_manifest_sha256')!=digest(ROOT/'third_party/vnsme/build_manifest.json')):
            return None
    for name,value in run_config.get('code_sha256',{}).items():
        # The prior controller had a post-rollout cache-key bug; its completed
        # runner and scoring code is reusable, the controller itself is not.
        if name=='instance35_gp_evolution.py':
            continue
        if digest(ROOT/name)!=value:
            return None
    return stage,run_dir


def verify_prior_failed_candidate(source_experiment, source_run_id, expected_tree_hash, config):
    """Confirm a recorded timed-out tree is excluded rather than retried."""
    run_dir=Path(source_experiment)/'runs/gp/train'/source_run_id
    try:
        stage=_read(run_dir/'stage_result.json')
        run_config=_read(run_dir/'run_config.json')
        manifest=_read(run_dir/'runner/manifest.json')
        supervision=_read(run_dir/'supervisor/supervision.json')
    except (OSError,json.JSONDecodeError):
        return None
    stop=stage.get('stop_event') or {}
    if not (stage.get('status')=='TIMEOUT' and stage.get('J') is None
            and stage.get('partial') is True and stage.get('completed_decisions')==4
            and stage.get('decision_starts')==5
            and manifest.get('gp_tree',{}).get('tree_sha256')==expected_tree_hash
            and manifest.get('contract_version')==CONTRACT_VERSION
            and run_config.get('dataset_sha256')==config['partitions']['train']['orders_sha256']
            and run_config.get('vehicle_sha256')==config['partitions']['train']['vehicles_sha256']
            and run_config.get('supervisor_wall_seconds')==SUPERVISOR_SECONDS
            and run_config.get('runner_wall_guard_seconds')==RUNNER_GUARD_SECONDS
            and run_config.get('decision_hard_timeout_seconds')==DECISION_SECONDS
            and stop.get('kind')=='DECISION_TIMEOUT' and stop.get('decision_index')==5
            and stop.get('simulation_seconds')==2400 and stop.get('timeout_type')=='decision_hard_timeout'
            and stop.get('candidate_count')==31188 and stop.get('feasible_count')==1843
            and stop.get('groups_processed')==10 and stop.get('groups_total')==54
            and not (run_dir/'runner/result.json').exists()
            and supervision.get('state')=='DECISION_TIMEOUT'
            and supervision.get('remaining_job_processes')==[]):
        return None
    for name,value in run_config.get('code_sha256',{}).items():
        if name=='instance35_gp_evolution.py':
            continue
        if digest(ROOT/name)!=value:
            return None
    return stage,run_dir


def train(experiment_dir=EXPERIMENT, run_id=TRAINING_RUN_ID,
          task_deadline_utc=None):
    experiment_dir=Path(experiment_dir).resolve()
    config=_read(experiment_dir/'experiment_config.json')
    protocol=_read(experiment_dir/'training_protocol.json')
    if protocol.get('protocol_locked_before_new_rollouts') is not True:
        raise RuntimeError('training protocol is not locked')
    protocol_deadline=protocol.get('task_deadline_utc')
    if task_deadline_utc is None:
        task_deadline_utc=protocol_deadline or '2026-11-18T11:03:00+00:00'
    elif protocol_deadline is not None and task_deadline_utc!=protocol_deadline:
        raise RuntimeError('task deadline differs from the locked training protocol')
    gp_protocol=protocol['gp']
    population_size=int(gp_protocol['population_size'])
    generation_count=int(gp_protocol['generation_count'])
    validation_candidate_count=_validation_candidate_count(protocol)
    run_vnsme_train=_run_vnsme_train(protocol)
    stage_cap=int(config.get('execution',{}).get('supervisor_wall_seconds',SUPERVISOR_SECONDS))
    prior_train_cache={}
    prior_vnsme=None
    reuse_spec=protocol.get('prior_rollout_reuse')
    if reuse_spec:
        for item in reuse_spec.get('verified_gp_train_runs',[]):
            source_root=Path(item['experiment'])
            if not source_root.is_absolute(): source_root=ROOT/source_root
            source_root=source_root.resolve(); source_run_id=item['run_id']
            manifest_path=source_root/'runs/gp/train'/source_run_id/'runner/manifest.json'
            manifest=_read(manifest_path)
            tree_digest=manifest.get('gp_tree',{}).get('tree_sha256')
            if item.get('tree_sha256') is not None and tree_digest!=item['tree_sha256']:
                raise RuntimeError(f'prior Train tree hash differs from locked reuse entry: {source_run_id}')
            reused=verify_reusable_run(source_root,source_run_id,'gp','train',config,tree_digest)
            if reused is None:
                raise RuntimeError(f'prior completed Train tree failed reuse audit: {source_run_id}')
            prior_train_cache[tree_digest]=reused
        vnsme_item=reuse_spec.get('verified_vnsme_train_run') if run_vnsme_train else None
        if vnsme_item:
            source_root=Path(vnsme_item['experiment'])
            if not source_root.is_absolute(): source_root=ROOT/source_root
            prior_vnsme=verify_reusable_run(source_root.resolve(),vnsme_item['run_id'],
                'vnsme','train',config)
            if prior_vnsme is None:
                raise RuntimeError('prior VNSME Train artifact failed reuse audit')
    fixed_tree,_=load_tree(experiment_dir/'trees/fixed_gp_tree.json')
    prior_failed={}
    for tree_digest,metadata in protocol.get('prior_failed_candidates',{}).items():
        source=Path(metadata['source_experiment'])
        if not source.is_absolute(): source=ROOT/source
        failed=verify_prior_failed_candidate(source,metadata['run_id'],tree_digest,config)
        if failed is None:
            raise RuntimeError(f'prior timeout evidence did not match locked exclusion: {metadata["run_id"]}')
        prior_failed[tree_digest]=(failed[0],failed[1],metadata)
    training_dir=experiment_dir/'training'/run_id
    training_dir.mkdir(parents=True,exist_ok=False)
    (training_dir/'trees').mkdir()
    trace=training_dir/'training_trace.jsonl'
    trace.open('x',encoding='utf-8').close()
    deadline=datetime.fromisoformat(task_deadline_utc.replace('Z','+00:00')).timestamp()
    started=time.monotonic()
    write_exclusive(training_dir/'training_config.json',dict(protocol_sha256=protocol['protocol_sha256'],
        task_deadline_utc=task_deadline_utc, population_size=population_size,
        generation_count=generation_count, validation_candidate_count=validation_candidate_count,
        supervisor_wall_seconds=stage_cap,
        decision_hard_timeout_seconds=config['execution']['decision_hard_timeout_seconds'],
        runner_wall_guard_seconds=config['execution']['runner_wall_guard_seconds']))
    train_cache={}
    unique_trees={}
    failed_tree_hashes={}
    generation_rows=[]
    validation_records=[]

    def ensure_budget(reserve_rollouts):
        remaining=deadline-time.time()
        required=stage_cap*(1+reserve_rollouts)
        if remaining < required:
            raise TimeoutError(f'task-deadline reserve insufficient: remaining={remaining:.1f}s required={required}s')

    def tree_path(generation,member,tree):
        path=training_dir/'trees'/f'g{generation}_m{member:02d}.json'
        if path.exists():
            existing,_=load_tree(path)
            if tree_hash(existing)!=tree_hash(tree):
                raise RuntimeError(f'tree artifact already exists with different content: {path}')
            return path
        save_tree(path,tree,training=dict(run_id=run_id,generation=generation,
            member=member,evolution_seed=TRAINING_SEED,scope=config['scope_label']))
        return path

    def evaluate_train(generation,member,tree,path,reserve):
        key=tree_hash(tree)
        if key in train_cache:
            prior=train_cache[key]
            append_durable(trace,dict(event='TRAIN_DUPLICATE_REUSED',generation=generation,
                member=member,tree_sha256=key,source_run_id=prior['train_run_id'],J=prior['train_J']))
            unique_trees.setdefault(key,dict(tree=tree,train_J=prior['train_J'],train_run_id=prior['train_run_id'],
                tree_path=prior['tree_path'],first_generation=prior['generation'],
                first_member=prior['member']))
            return prior
        if key in prior_train_cache:
            stage,source_dir=prior_train_cache[key]
            item=dict(train_J=stage['J'],train_run_id=stage['run_id'],
                tree_path=str(path),generation=generation,member=member)
            train_cache[key]=item
            unique_trees[key]=dict(tree=tree,train_J=stage['J'],train_run_id=stage['run_id'],
                tree_path=str(path),generation=generation,member=member)
            append_durable(trace,dict(event='TRAIN_TREE_REUSED_VERIFIED',generation=generation,
                member=member,tree_sha256=key,J=stage['J'],source_run_id=stage['run_id'],
                source_artifact=str(source_dir)))
            return item
        if key in prior_failed:
            stage,source_dir,metadata=prior_failed[key]
            failed_tree_hashes[key]=dict(run_id=stage['run_id'],status='TIMEOUT',J=None,
                source_run=str(source_dir),stop_event=stage.get('stop_event'))
            append_durable(trace,dict(event='TRAIN_TREE_EXCLUDED_PRIOR_TIMEOUT',generation=generation,
                member=member,tree_sha256=key,J=None,source_run_id=stage['run_id'],
                stop_event=stage.get('stop_event'),source_artifact=str(source_dir),
                reason=metadata['reason']))
            return None
        if key in failed_tree_hashes:
            append_durable(trace,dict(event='TRAIN_DUPLICATE_EXCLUDED_FAILED',generation=generation,
                member=member,tree_sha256=key,J=None,source_run_id=failed_tree_hashes[key]['run_id']))
            return None
        ensure_budget(reserve)
        rid=f'{run_id}_g{generation}_m{member:02d}_train'
        record=run_rollout(rid,'gp','train',tree_path=path,experiment_dir=experiment_dir)
        run_dir=experiment_dir/'runs/gp/train'/rid
        result_path=run_dir/'runner/result.json'
        manifest_path=run_dir/'runner/manifest.json'
        audit_path=run_dir/'runner/independent_score.json'
        if _complete(record) and result_path.is_file() and manifest_path.is_file() and audit_path.is_file():
            rr=_read(result_path); audit=_read(audit_path); manifest=_read(manifest_path)
            contract_ok=(rr.get('contract_complete') is True
                and str(rr.get('score',{}).get('total_score'))==str(audit.get('total_score'))
                and manifest.get('contract_version')==CONTRACT_VERSION
                and manifest.get('gp_tree',{}).get('tree_sha256')==key)
        else:
            contract_ok=False
        if not contract_ok:
            failed_tree_hashes[key]=dict(run_id=rid,status=record.get('status'),
                source_run=str(run_dir),stop_event=record.get('stop_event'),J=None)
            append_durable(trace,dict(event='TRAIN_ROLLOUT_INELIGIBLE',generation=generation,
                member=member,tree_sha256=key,status=record.get('status'),J=None,
                artifact=str(run_dir),stop_event=record.get('stop_event'),
                reason='completion, contract, independent score, tree hash, or cleanup check failed; excluded without retry'))
            return None
        item=dict(tree=tree,train_J=record['J'],train_run_id=rid,
            tree_path=str(path),generation=generation,member=member)
        train_cache[key]=item
        unique_trees[key]=item
        append_durable(trace,dict(event='TRAIN_TREE_COMPLETED',generation=generation,
            member=member,tree_sha256=key,J=record['J'],wall_seconds=record['wall_seconds'],
            completed_decisions=record['completed_decisions'],artifact=str(run_dir)))
        return item

    result=None
    try:
        fixed_tree,_=load_tree(experiment_dir/'trees/fixed_gp_tree.json')
        rng=random.Random(TRAINING_SEED)
        generation=initial_population(rng,population_size)
        if tree_hash(generation[0])!=tree_hash(fixed_tree):
            raise RuntimeError('generation-zero member zero is no longer the locked fixed tree')

        # The fixed GP run is G0/M0; any declared tree reuse keeps the seeded
        # initial population and evolution operators unchanged.
        fixed_path=tree_path(0,0,generation[0])
        fixed_reserve=(population_size*generation_count-1
            +validation_candidate_count+2+(1 if run_vnsme_train else 0))
        fixed_train=evaluate_train(0,0,generation[0],fixed_path,fixed_reserve)
        vnsme_train=None
        if run_vnsme_train:
            vnsme_train_id=f'{run_id}_vnsme_train'
            if prior_vnsme is not None:
                vnsme_train,vnsme_train_dir=prior_vnsme
                append_durable(trace,dict(event='TRAIN_BASELINE_REUSED',algorithm='vnsme',
                    run_id=vnsme_train['run_id'],J=vnsme_train['J'],source_artifact=str(vnsme_train_dir)))
            else:
                ensure_budget(population_size*generation_count-1+validation_candidate_count+2)
                vnsme_train=run_rollout(vnsme_train_id,'vnsme','train',experiment_dir=experiment_dir)
                vnsme_train_dir=experiment_dir/'runs/vnsme/train'/vnsme_train_id
                append_durable(trace,dict(event='TRAIN_BASELINE_STARTED',algorithm='vnsme',
                    run_id=vnsme_train_id,artifact=str(vnsme_train_dir)))
            if not _complete(vnsme_train):
                raise RuntimeError(f'VNSME Train incomplete; no retry: {vnsme_train_id}')
            vnsme_result=_read(vnsme_train_dir/'runner/result.json')
            vnsme_audit=_read(vnsme_train_dir/'runner/independent_score.json')
            vnsme_manifest=_read(vnsme_train_dir/'runner/manifest.json')
            if (vnsme_result.get('contract_complete') is not True
                    or str(vnsme_result.get('score',{}).get('total_score'))!=str(vnsme_audit.get('total_score'))
                    or vnsme_manifest.get('contract_version')!=CONTRACT_VERSION):
                raise RuntimeError(f'VNSME Train audit/contract mismatch: {vnsme_train_id}')
            append_durable(trace,dict(event=('TRAIN_BASELINE_REUSED' if prior_vnsme is not None else 'TRAIN_BASELINE_COMPLETED'),algorithm='vnsme',
                run_id=vnsme_train['run_id'],J=vnsme_train['J'],wall_seconds=vnsme_train['wall_seconds'],
                artifact=str(vnsme_train_dir)))
        else:
            append_durable(trace,dict(event='TRAIN_BASELINE_SKIPPED',algorithm='vnsme',
                reason='locked protocol requests VNSME only on Test'))

        all_generation_evaluated=[]
        for g in range(generation_count):
            evaluated=[]
            generation_records=[]
            for m,tree in enumerate(generation):
                path=tree_path(g,m,tree)
                reserve_rollouts=(population_size*generation_count - (g*population_size+m+1)
                    + validation_candidate_count + 2)  # future GP train, val, and two holdout runs
                fitness=evaluate_train(g,m,tree,path,reserve_rollouts)
                if fitness is None:
                    generation_records.append(dict(member=m,tree_sha256=tree_hash(tree),
                        expression=tree.text(),status='EXCLUDED',train_J=None,train_run_id=None))
                    continue
                evaluated.append((Decimal(fitness['train_J']),tree))
                generation_records.append(dict(member=m,tree_sha256=tree_hash(tree),
                    expression=tree.text(),status='COMPLETED',train_J=fitness['train_J'],
                    train_run_id=fitness['train_run_id']))
                append_durable(trace,dict(event='GENERATION_MEMBER',generation=g,member=m,
                    tree_sha256=tree_hash(tree),expression=tree.text(),train_J=fitness['train_J'],
                    source_run_id=fitness['train_run_id']))
            generation_rows.append(generation_records)
            write_exclusive(training_dir/f'generation_{g}.json',generation_rows[-1])
            if len({tree_hash(tree) for _,tree in evaluated}) < 2:
                raise RuntimeError(f'generation {g} has fewer than two distinct eligible Train trees')
            all_generation_evaluated.append(evaluated)
            if g+1<generation_count:
                generation=breed(rng,evaluated,population_size,tournament=3,
                    crossover_rate=.8,mutation_rate=.3,elitism=1,limits=Limits())

        if len(unique_trees)<2:
            raise RuntimeError(f'only {len(unique_trees)} unique completed Train trees; need at least two for selection')

        # Fresh temporal validation was fixed in the protocol before any new J.
        validation_pool=sorted(unique_trees.values(),key=_rank_train)[:validation_candidate_count]
        for index,candidate in enumerate(validation_pool):
            ensure_budget(len(validation_pool)-index-1+2)
            rid=f'{run_id}_validation_{index+1:02d}'
            rec=run_rollout(rid,'gp','validation',tree_path=candidate['tree_path'],
                            experiment_dir=experiment_dir)
            if not _complete(rec):
                append_durable(trace,dict(event='VALIDATION_INCOMPLETE',tree_sha256=tree_hash(candidate['tree']),
                    status=rec.get('status'),J=None,artifact=rec.get('runner_result_path')))
                raise RuntimeError(f'Validation incomplete; no tree selection or retry: {rid}')
            run_dir=experiment_dir/'runs/gp/validation'/rid
            rr=_read(run_dir/'runner/result.json'); audit=_read(run_dir/'runner/independent_score.json')
            if (rr.get('contract_complete') is not True
                    or str(rr.get('score',{}).get('total_score'))!=str(audit.get('total_score'))):
                raise RuntimeError(f'Validation independent J/contract mismatch: {rid}')
            record={**candidate,'validation_J':rec['J'],'validation_run_id':rid,
                    'validation_wall_seconds':rec['wall_seconds']}
            validation_records.append(record)
            append_durable(trace,dict(event='VALIDATION_COMPLETED',tree_sha256=tree_hash(candidate['tree']),
                train_J=candidate['train_J'],validation_J=rec['J'],wall_seconds=rec['wall_seconds'],
                artifact=str(run_dir)))

        selected=min(validation_records,key=_rank_validation)
        selected_path=training_dir/'selected_tree.json'
        tree_sha=tree_hash(selected['tree'])
        save_tree(selected_path,selected['tree'],training=dict(run_id=run_id,
            selection='lowest independently verified J on new temporal Validation',
            tree_sha256=tree_sha,train_J=selected['train_J'],
            validation_J=selected['validation_J'],validation_run_id=selected['validation_run_id'],
            protocol_sha256=protocol['protocol_sha256']))
        selection=dict(status='SELECTED_BEFORE_HOLDOUT',tree_sha256=tree_sha,
            expression=selected['tree'].text(),train_J=selected['train_J'],
            validation_J=selected['validation_J'],validation_run_id=selected['validation_run_id'],
            selection_rule='minimum Validation J; tie by Train J, node count, canonical tree',
            validation_candidates=[dict(tree_sha256=tree_hash(x['tree']),expression=x['tree'].text(),
                train_J=x['train_J'],validation_J=x['validation_J'],run_id=x['validation_run_id'])
                for x in validation_records],
            written_at_utc=datetime.now(timezone.utc).isoformat())
        write_exclusive(training_dir/'selection_decision.json',selection)
        append_durable(trace,dict(event='TREE_SELECTED',**selection))

        ensure_budget(1)
        gp_test_id=f'{run_id}_selected_gp_future_test'
        gp_test=run_rollout(gp_test_id,'gp','test',tree_path=selected_path,
                            experiment_dir=experiment_dir)
        if not _complete(gp_test):
            raise RuntimeError(f'new future holdout GP incomplete; no retry: {gp_test_id}')
        ensure_budget(0)
        vnsme_test_id=f'{run_id}_vnsme_future_test'
        vnsme_test=run_rollout(vnsme_test_id,'vnsme','test',experiment_dir=experiment_dir)
        if not _complete(vnsme_test):
            raise RuntimeError(f'new future holdout VNSME incomplete; no retry: {vnsme_test_id}')

        result=dict(status='COMPLETED',scope=config['scope_label'],run_id=run_id,
            protocol_sha256=protocol['protocol_sha256'],population_size=population_size,
            generation_count=generation_count,generations_completed=generation_count,
            unique_train_tree_count=len(unique_trees),
            train_trees=[dict(tree_sha256=k,expression=v['tree'].text(),J=v['train_J'],
                run_id=v['train_run_id']) for k,v in sorted(unique_trees.items())],
            excluded_train_trees=failed_tree_hashes,
            validation_tree_count=len(validation_records),selected_tree=dict(tree_sha256=tree_sha,
                expression=selected['tree'].text(),train_J=selected['train_J'],
                validation_J=selected['validation_J'],validation_run_id=selected['validation_run_id'],
                tree_path=str(selected_path)),
            train_baselines=dict(fixed_gp_train_run=train_cache[tree_hash(fixed_tree)]['train_run_id'],
                vnsme_run_id=(vnsme_train['run_id'] if vnsme_train else None),
                J=(vnsme_train['J'] if vnsme_train else None),
                omitted_per_protocol=not run_vnsme_train),
            future_holdout=dict(protocol_interval=config['temporal_protocol']['intervals']['test'],
                gp=dict(run_id=gp_test_id,J=gp_test['J'],wall_seconds=gp_test['wall_seconds']),
                vnsme=dict(run_id=vnsme_test_id,J=vnsme_test['J'],wall_seconds=vnsme_test['wall_seconds']),
                comparison_note=('same partition, seed, stage/decision hard limits and scorer; VNSME additionally has '
                    f"{config['execution']['vnsme_internal_search_budget_seconds']}s internal search budget and "
                    f"{config['execution']['vnsme_subprocess_hard_timeout_seconds']}s subprocess timeout, so computation is not equalized")),
            wall_seconds=time.monotonic()-started)
        write_exclusive(training_dir/'training_result.json',result)
        append_durable(trace,dict(event='TRAINING_COMPLETED',status='COMPLETED',
                                  wall_seconds=result['wall_seconds']))
        return result
    except BaseException as exc:
        failure=dict(status='INCOMPLETE',scope=config['scope_label'],run_id=run_id,J=None,
            partial=True,error=f'{type(exc).__name__}: {exc}',
            unique_train_tree_count=len(unique_trees),
            generations_completed=len(generation_rows),
            validation_tree_count=len(validation_records),wall_seconds=time.monotonic()-started)
        append_durable(trace,dict(event='TRAINING_INCOMPLETE',**failure))
        write_exclusive(training_dir/'training_result.json',failure)
        return failure


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('prepare','prepare-contiguous','train'))
    parser.add_argument('--experiment-dir',type=Path)
    parser.add_argument('--run-id')
    parser.add_argument('--window-start-fraction',type=Decimal,default=Decimal('0.18'))
    parser.add_argument('--window-end-fraction',type=Decimal,default=Decimal('0.385'))
    parser.add_argument('--population-size',type=int,default=4)
    parser.add_argument('--generation-count',type=int,default=3)
    parser.add_argument('--validation-candidate-count',type=int,default=3)
    parser.add_argument('--task-deadline-utc')
    args=parser.parse_args()
    if args.action=='prepare':
        config,protocol=prepare(args.experiment_dir or EXPERIMENT)
        print(json.dumps({'config':config,'protocol':protocol},indent=2,default=str))
    elif args.action=='prepare-contiguous':
        config,protocol=prepare_contiguous(args.experiment_dir or CONTIGUOUS_EXPERIMENT,
            args.run_id or CONTIGUOUS_TRAINING_RUN_ID,args.window_start_fraction,
            args.window_end_fraction,args.population_size,args.generation_count,
            args.validation_candidate_count)
        print(json.dumps({'config':config,'protocol':protocol},indent=2,default=str))
    else:
        out=train(args.experiment_dir or EXPERIMENT,args.run_id or TRAINING_RUN_ID,
            args.task_deadline_utc)
        print(json.dumps(out,indent=2,default=str))
        raise SystemExit(0 if out['status']=='COMPLETED' else 2)
