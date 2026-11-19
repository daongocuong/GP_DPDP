"""Population-50 official GP-DPDP run, with evaluation-fingerprint cache import and exact checkpoints.

The locked GP/simulator sources remain untouched. This module changes only orchestration
for the population-size sensitivity run and records its own hash in the new protocol.
"""
import argparse
import csv
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import math
import os
from pathlib import Path
import random
import statistics
import time

import dpdp_gp
import gp_dpdp_100_feasibility as exp
from dpdp_contract import EXECUTION_CONTRACT
from dpdp_gp import crossover, mutate, tree_hash, validate_tree


ROOT = exp.ROOT
OLD_RUN = ROOT/'gp_runs/dpdp_100_orders_pop10_feasibility_seed42_r01'
RUN_BASENAME = 'dpdp_100_orders_pop50_g10_seed42'
POPULATION_SIZE = 50
GENERATIONS = 10
GP_SEED = 42
SIMULATOR_SEED = 0
FEATURES = list(exp.FEATURES)
PRIMITIVES = list(dpdp_gp.PRIMITIVES)
LIMITS = exp.LIMITS
CHECKPOINT_SCHEMA = 'dpdp-gp-100-pop50-checkpoint-v1'
EVALUATION_SCHEMA = 'dpdp-rollout-evaluation-fingerprint-v1'
EVOLUTION_SCHEMA = 'dpdp-gp-evolution-fingerprint-v1'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def digest_json(value):
    return hashlib.sha256(exp.canonical_json(value).encode('utf-8')).hexdigest()


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def tupleize(value):
    return tuple(tupleize(item) for item in value) if isinstance(value, list) else value


def choose_run_directory(requested=None):
    base = Path(requested).resolve() if requested else ROOT/'gp_runs'/f'{RUN_BASENAME}_r01'
    if not base.exists():
        return base
    stem = base.name.rsplit('_r', 1)[0]
    revision = 2
    while True:
        candidate = base.with_name(f'{stem}_r{revision:02d}')
        if not candidate.exists():
            return candidate
        revision += 1


def current_source_hashes():
    return {name: exp.sha(ROOT/name) for name in exp.SOURCE_FILES}


def evaluation_payload(config, manifest, policy, partition):
    info = manifest['partitions'][partition]
    source = config['source']['source_sha256']
    return dict(
        schema=EVALUATION_SCHEMA,
        policy=policy,
        partition=partition,
        instance_id=config['dataset']['instance_id'],
        source_commit=config['dataset']['source_commit'],
        original_order_sha256=config['dataset']['source_order_sha256'],
        partition_order_sha256=info['orders_sha256'],
        vehicle_sha256=info['vehicles_sha256'],
        route_sha256=manifest['source']['route_sha256'],
        factory_sha256=manifest['source']['factory_sha256'],
        simulator_seed=config['evaluation']['simulator_seed'],
        time_slot_seconds=config['evaluation']['time_slot_seconds'],
        decision_timeout_seconds=config['evaluation']['decision_timeout_seconds'],
        rollout_timeout_seconds=config['evaluation']['rollout_timeout_seconds'],
        runner_wall_guard_seconds=config['evaluation']['runner_wall_guard_seconds'],
        simulation_horizon_seconds=config['evaluation']['simulation_horizon_seconds'],
        execution_contract=EXECUTION_CONTRACT,
        features=list(config['gp']['features']),
        primitives=list(config['gp']['primitives']),
        numeric_policy=dpdp_gp.NUMERIC_POLICY,
        objective='raw independently verified total_score J; minimize',
        no_partial_or_invalid_J=True,
        source_sha256=source,
    )


def evaluation_fingerprints(config, manifest):
    return {
        f'{policy}:{partition}': digest_json(evaluation_payload(config, manifest, policy, partition))
        for policy, partition in (
            ('gp', 'train'), ('gp', 'validation'), ('gp', 'test'), ('vnsme', 'test')
        )
    }


def evolution_fingerprint(config, fingerprints):
    return digest_json(dict(
        schema=EVOLUTION_SCHEMA,
        population_size=config['gp']['population_size'],
        evaluated_generations=config['gp']['evaluated_generations'],
        generation_labels=config['gp']['generation_labels'],
        seed=config['gp']['seed'],
        elitism=config['gp']['elitism'],
        tournament_size=config['gp']['tournament_size'],
        crossover_probability=config['gp']['crossover_probability'],
        mutation_probability=config['gp']['mutation_probability'],
        initial_depths=config['gp']['initial_depths'],
        maximum_depth=config['gp']['maximum_depth'],
        maximum_nodes=config['gp']['maximum_nodes'],
        initialization=config['gp']['initialization'],
        fitness=config['gp']['fitness'],
        evaluation_fingerprints=fingerprints,
    ))


def find_tree_file(run_dir, tree):
    path = exp._tree_artifact_path(run_dir, tree)
    return path


def tree_record(run_dir, generation, member, tree, create=True):
    digest = tree_hash(tree)
    path = find_tree_file(run_dir, tree)
    if path is None and create:
        target = Path(run_dir)/'trees'/f'evolved_g{generation:02d}_m{member:02d}_{digest[:12]}.json'
        if target.exists():
            prior, _ = exp.load_tree(target)
            if tree_hash(prior) != digest:
                raise ValueError(f'tree artifact path collision: {target}')
        else:
            exp.save_tree(target, tree, training=dict(
                generation=generation, member=member,
                protocol_sha256=exp.read_json(Path(run_dir)/'protocol.json')['protocol_sha256'],
                origin='deterministic GP breeding'), limits=LIMITS)
        path = target
    if path is None:
        raise ValueError(f'missing tree artifact for {digest}')
    nodes, depth = validate_tree(tree, LIMITS)
    return dict(generation=generation, member=member, tree_sha256=digest,
                expression=tree.text(), depth=depth, nodes=nodes,
                tree_path=str(Path(path).resolve()))


def old_tree_index(old_run):
    result = {}
    for path in (Path(old_run)/'trees').glob('*.json'):
        try:
            tree, _ = exp.load_tree(path)
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        result.setdefault(tree_hash(tree), (tree, path))
    return result


def check_imported_entry(summary, runner_result, run_config, digest, old_protocol, old_manifest):
    train = old_manifest['partitions']['train']
    score = runner_result.get('score') or {}
    checks = dict(
        cache_protocol=run_config.get('protocol_sha256') == old_protocol['protocol_sha256']
                      == summary.get('protocol_sha256'),
        tree_hash=summary.get('tree_sha256') == digest,
        completed=summary.get('status') == 'COMPLETED' and summary.get('valid') is True
                  and summary.get('J') is not None,
        train_policy=summary.get('partition') == 'train' and summary.get('policy') == 'gp',
        feasibility=summary.get('feasibility_status') == 'PASS',
        independent_score=summary.get('independent_score_matches_runner') is True
                          and score.get('total_score') == summary.get('J')
                          and (summary.get('independent_score') or {}).get('total_score') == summary.get('J'),
        no_timeout=summary.get('timeout_status') is None,
        full_partition=summary.get('completed_orders') == 55
                       and summary.get('completed_items') == 91
                       and runner_result.get('original_orders') == 55
                       and runner_result.get('completed_items') == 91,
        runner_contract=runner_result.get('status') == 'COMPLETED'
                        and runner_result.get('valid') is True
                        and runner_result.get('partial') is False
                        and runner_result.get('contract_complete') is True
                        and score.get('valid') is True,
        partition_data=run_config.get('orders_sha256') == train['orders_sha256']
                       and run_config.get('vehicles_sha256') == train['vehicles_sha256'],
        evaluation_limits=run_config.get('simulator_seed') == SIMULATOR_SEED
                          and run_config.get('decision_timeout_seconds') == 600
                          and run_config.get('rollout_timeout_seconds') == 3600
                          and run_config.get('runner_wall_guard_seconds') == 3660,
        source_fingerprint=run_config.get('source_sha256') == old_protocol['source_sha256'],
    )
    return checks


def verify_reference(old_run=OLD_RUN):
    old_run = Path(old_run).resolve()
    old_config, old_manifest, _, old_protocol = exp.verify_locked_run(old_run)
    new_source = current_source_hashes()
    if new_source != old_protocol['source_sha256']:
        raise ValueError('current pinned simulator/GP sources differ from population-10 reference')
    old_cache = exp.read_json(old_run/'cache'/'train.json')
    if old_cache.get('protocol_sha256') != old_protocol['protocol_sha256']:
        raise ValueError('reference Train cache protocol mismatch')
    tree_index = old_tree_index(old_run)
    imported = []
    rejected = []
    for digest, entry in old_cache.get('entries', {}).items():
        try:
            summary_path = Path(entry['summary_path'])
            summary = exp.read_json(summary_path)
            runner_result_path = Path(summary['runner_result_path'])
            runner_result = exp.read_json(runner_result_path)
            run_config = exp.read_json(summary_path.parent/'run_config.json')
            checks = check_imported_entry(summary, runner_result, run_config,
                                          digest, old_protocol, old_manifest)
            artifact_ok = digest in tree_index
            source_files_ok = summary_path.is_file() and runner_result_path.is_file()
            passed = all(checks.values()) and artifact_ok and source_files_ok
            if passed:
                imported.append(dict(
                    tree_sha256=digest, J=summary['J'], status='COMPLETED',
                    source_summary_path=str(summary_path.resolve()),
                    source_summary_sha256=sha(summary_path),
                    source_runner_result_path=str(runner_result_path.resolve()),
                    source_runner_result_sha256=sha(runner_result_path),
                    source_protocol_sha256=old_protocol['protocol_sha256'],
                    source_run_id=summary.get('run_id'),
                    historical_rollout_wall_seconds=summary['actual_wall_seconds'],
                    verification_checks=checks,
                ))
            else:
                rejected.append(dict(tree_sha256=digest, verification_checks=checks,
                                     tree_artifact_found=artifact_ok,
                                     source_files_found=source_files_ok))
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            rejected.append(dict(tree_sha256=digest, error=f'{type(exc).__name__}: {exc}'))
    if len(imported) != 68:
        raise ValueError(f'expected 68 verified reference Train entries; got {len(imported)}, rejected {len(rejected)}')

    baseline_dir = old_run/'rollouts'/'test'/'vnsme'
    baseline_summary_path = baseline_dir/'rollout_summary.json'
    baseline_summary = exp.read_json(baseline_summary_path)
    baseline_runner_path = Path(baseline_summary['runner_result_path'])
    baseline_runner = exp.read_json(baseline_runner_path)
    baseline_run_config = exp.read_json(baseline_dir/'run_config.json')
    baseline_score = baseline_runner.get('score') or {}
    test_partition = old_manifest['partitions']['test']
    baseline_checks = dict(
        completed=baseline_summary.get('status') == 'COMPLETED' and baseline_summary.get('valid') is True,
        metrics=baseline_summary.get('J') == '32.82'
                and baseline_score.get('total_distance_km') == '164.1'
                and baseline_score.get('total_tardiness_seconds') == '0'
                and baseline_score.get('late_original_orders') == 0,
        feasibility=baseline_summary.get('feasibility_status') == 'PASS'
                    and baseline_summary.get('independent_score_matches_runner') is True,
        complete_test=baseline_summary.get('completed_orders') == 25
                      and baseline_summary.get('completed_items') == 34
                      and baseline_runner.get('contract_complete') is True,
        partition=baseline_run_config.get('partition') == 'test'
                  and baseline_run_config.get('orders_sha256') == test_partition['orders_sha256']
                  and baseline_run_config.get('vehicles_sha256') == test_partition['vehicles_sha256'],
        seed_limits=baseline_run_config.get('simulator_seed') == 0
                    and baseline_run_config.get('decision_timeout_seconds') == 600
                    and baseline_run_config.get('rollout_timeout_seconds') == 3600
                    and baseline_run_config.get('runner_wall_guard_seconds') == 3660,
        source=baseline_run_config.get('source_sha256') == old_protocol['source_sha256']
               and baseline_summary.get('protocol_sha256') == old_protocol['protocol_sha256'],
        vnsme_budget='--vnsme-epoch-seconds' in baseline_run_config.get('command', [])
                      and baseline_run_config['command'][
                          baseline_run_config['command'].index('--vnsme-epoch-seconds')+1] == '600',
        no_vnsme_training=baseline_summary.get('policy') == 'vnsme'
                          and baseline_summary.get('partition') == 'test',
    )
    baseline_status = 'REUSED_VERIFIED' if all(baseline_checks.values()) else 'UNRESOLVED'
    baseline = dict(
        baseline_status=baseline_status,
        source_run_directory=str(old_run),
        source_run_id=baseline_summary.get('run_id'),
        source_protocol_sha256=old_protocol['protocol_sha256'],
        source_summary_path=str(baseline_summary_path.resolve()),
        source_summary_sha256=sha(baseline_summary_path),
        source_runner_result_path=str(baseline_runner_path.resolve()),
        source_runner_result_sha256=sha(baseline_runner_path),
        score=dict(J=baseline_summary['J'], distance_km=baseline_score['total_distance_km'],
                   tardiness_seconds=baseline_score['total_tardiness_seconds'],
                   late_orders=baseline_score['late_original_orders'],
                   actual_wall_seconds=baseline_summary['actual_wall_seconds'],
                   decision_count=baseline_summary['decision_count'],
                   completed_orders=baseline_summary['completed_orders'],
                   completed_items=baseline_summary['completed_items'],
                   feasibility=baseline_summary['feasibility_status'],
                   independent_score_matches_runner=baseline_summary['independent_score_matches_runner']),
        verification_checks=baseline_checks,
    )
    return old_config, old_manifest, old_protocol, imported, rejected, baseline, baseline_summary_path


def build_new_config(old_config, run_dir):
    config = deepcopy(old_config)
    config['schema'] = 'dpdp-gp-100-pop50-official-v1'
    config['gp']['population_size'] = POPULATION_SIZE
    config['gp']['evaluated_generations'] = GENERATIONS
    config['gp']['generation_labels'] = [f'G{i}' for i in range(GENERATIONS)]
    config['gp']['breeding_transitions'] = GENERATIONS-1
    config['gp']['seed'] = GP_SEED
    config['evaluation']['simulator_seed'] = SIMULATOR_SEED
    config['run_namespace'] = str(run_dir.relative_to(ROOT))
    config['frozen_at_utc'] = utc_now()
    return config


def save_g0(run_dir, config):
    rng, population, detail_rows = exp.initial_population(
        seed=GP_SEED, size=POPULATION_SIZE, depths=tuple(config['gp']['initial_depths']),
        limits=LIMITS)
    members = []
    for i, (tree, details) in enumerate(zip(population, detail_rows)):
        nodes, depth = validate_tree(tree, LIMITS)
        row = dict(details)
        row.update(member=i, canonical=exp.canonical(tree),
                   canonical_sha256=tree_hash(tree), nodes=nodes, depth=depth,
                   expression=tree.text())
        members.append(row)
        exp.save_tree(Path(run_dir)/'trees'/f'g0_m{i:02d}.json', tree,
            training=dict(generation=0, member=i, gp_seed=GP_SEED,
                          initialization='ramped full/grow'), limits=LIMITS)
    hashes = [m['canonical_sha256'] for m in members]
    duplicates = [dict(member=i, first_member=hashes.index(digest), tree_sha256=digest)
                  for i, digest in enumerate(hashes) if hashes.index(digest) != i]
    manifest = dict(schema='dpdp-gp-100-pop50-g0-v1',
        population_size=POPULATION_SIZE, gp_seed=GP_SEED,
        initialization='ramped full/grow; target depth cycles 2,3,4',
        initial_depths=list(config['gp']['initial_depths']),
        maximum_depth=config['gp']['maximum_depth'],
        maximum_nodes=config['gp']['maximum_nodes'],
        distinct_tree_hash_count=len(set(hashes)),
        duplicate_members=duplicates,
        members=members,
        gp_random_state=rng.getstate())
    exp.write_new(Path(run_dir)/'g0_population_manifest.json', manifest)
    return rng, population, manifest


def baseline_runner_config_matches_new(config, old_config):
    fields = ('simulator_seed','time_slot_seconds','decision_timeout_seconds',
              'rollout_timeout_seconds','runner_wall_guard_seconds','simulation_horizon_seconds')
    return all(config['evaluation'][f] == old_config['evaluation'][f] for f in fields)


def prepare_run(requested=None, old_run=OLD_RUN):
    old_run = Path(old_run).resolve()
    old_config, old_manifest, old_protocol, imported, rejected, baseline, _ = verify_reference(old_run)
    run_dir = choose_run_directory(requested)
    if not baseline_runner_config_matches_new(old_config, old_config):
        raise ValueError('reference evaluation config changed unexpectedly')
    run_dir.mkdir(parents=True, exist_ok=False)
    (run_dir/'trees').mkdir()
    (run_dir/'data').mkdir()
    (run_dir/'cache').mkdir()
    training_dir = run_dir/'official_training'
    training_dir.mkdir()
    for split in exp.SPLITS:
        source = old_run/'data'/split
        target = run_dir/'data'/split
        target.mkdir()
        for name in ('orders.csv','vehicle_info_5.csv'):
            (target/name).write_bytes((source/name).read_bytes())
    (run_dir/'temporal_split_manifest.json').write_bytes((old_run/'temporal_split_manifest.json').read_bytes())

    config = build_new_config(old_config, run_dir)
    # Freeze and verify that population size is the sole GP hyperparameter change.
    for key in old_config['gp']:
        if key != 'population_size' and config['gp'][key] != old_config['gp'][key]:
            raise ValueError(f'unexpected GP setting change: {key}')
    if config['gp']['population_size'] != POPULATION_SIZE:
        raise ValueError('population-size invariant failed')
    if config['evaluation']['simulator_seed'] != SIMULATOR_SEED:
        raise ValueError('simulator-seed invariant failed')
    exp.write_new(run_dir/'experiment_config.json', config)
    (run_dir/'protocol.sha256').write_text('', encoding='ascii')  # replaced before any rollout
    rng, population, g0 = save_g0(run_dir, config)

    manifest = exp.read_json(run_dir/'temporal_split_manifest.json')
    fingerprints = evaluation_fingerprints(config, manifest)
    old_eval = evaluation_fingerprints(old_config, old_manifest)
    if fingerprints != old_eval:
        raise ValueError('rollout evaluation fingerprints changed from population-10 reference')
    evolution_fp = evolution_fingerprint(config, fingerprints)

    baseline['rollout_evaluation_fingerprint'] = fingerprints['vnsme:test']
    baseline['reuse_evidence'] = dict(
        source_code_sha256_match=True,
        test_partition_sha256_match=True,
        vehicle_sha256_match=True,
        simulator_seed_and_timeouts_match=True,
        objective_and_independent_score_match=True,
        vnsme_epoch_budget_seconds=600,
    )
    exp.write_new(run_dir/'baseline_reference.json', baseline)

    imported_rows = []
    for item in imported:
        imported_rows.append(dict(
            tree_sha256=item['tree_sha256'], J=item['J'],
            source_summary_path=item['source_summary_path'],
            source_summary_sha256=item['source_summary_sha256'],
            source_runner_result_path=item['source_runner_result_path'],
            source_runner_result_sha256=item['source_runner_result_sha256'],
            source_protocol_sha256=item['source_protocol_sha256'],
            source_run_id=item['source_run_id'],
            historical_rollout_wall_seconds=item['historical_rollout_wall_seconds'],
            wrapper_summary_path=str(Path('cache')/'imported_train'/item['tree_sha256']/'rollout_summary.json'),
            evaluation_fingerprint=fingerprints['gp:train'],
            verification_checks=item['verification_checks'],
        ))
    import_manifest = dict(
        schema='dpdp-gp-cross-run-cache-import-v1',
        source_run_directory=str(old_run),
        source_protocol_sha256=old_protocol['protocol_sha256'],
        source_cache_sha256=exp.sha(old_run/'cache'/'train.json'),
        source_evaluation_fingerprint=old_eval['gp:train'],
        new_evaluation_fingerprint=fingerprints['gp:train'],
        evolution_fingerprint=evolution_fp,
        imported_entry_count=len(imported_rows),
        rejected_entries=rejected,
        entries=imported_rows,
    )
    exp.write_new(run_dir/'imported_cache_manifest.json', import_manifest)

    code_hashes = old_protocol['source_sha256']
    if code_hashes != current_source_hashes():
        raise ValueError('pinned source hashes changed during preflight')
    config_sha = digest_json(config)
    split_sha = exp.sha(run_dir/'temporal_split_manifest.json')
    g0_sha = exp.sha(run_dir/'g0_population_manifest.json')
    baseline_sha = exp.sha(run_dir/'baseline_reference.json')
    import_sha = exp.sha(run_dir/'imported_cache_manifest.json')
    protocol_payload = dict(
        schema='dpdp-gp-100-pop50-official-protocol-v1',
        config_sha256=config_sha,
        temporal_split_manifest_sha256=split_sha,
        g0_population_manifest_sha256=g0_sha,
        source_sha256=code_hashes,
        source_manifest_sha256=old_protocol['source_manifest_sha256'],
        orchestration_source_sha256=sha(__file__),
        evolution_fingerprint=evolution_fp,
        evaluation_fingerprints=fingerprints,
        baseline_reference_sha256=baseline_sha,
        imported_cache_manifest_sha256=import_sha,
        initialization_population=[dict(member=row['member'],
                                         canonical_sha256=row['canonical_sha256'])
                                   for row in g0['members']],
        cache=dict(scope='new run-local cache; imported source read-only',
                   imported_source_protocol_sha256=old_protocol['protocol_sha256'],
                   imported_entries=len(imported_rows),
                   reuse_requires_matching_evaluation_fingerprint_and_tree_hash=True,
                   timeout_tree_retry=False),
        trainer=dict(population_size=POPULATION_SIZE,
                     evaluated_generations=GENERATIONS,
                     total_member_positions=POPULATION_SIZE*GENERATIONS,
                     elite_reuse_requests=GENERATIONS-1,
                     max_new_train_rollouts_without_cache_hits=POPULATION_SIZE*GENERATIONS-(GENERATIONS-1)),
        protocol_locked_before_rollout=True,
    )
    protocol_sha = digest_json(protocol_payload)
    protocol = dict(protocol_payload, protocol_sha256=protocol_sha)
    exp.write_new(run_dir/'protocol.json', protocol)
    (run_dir/'protocol.sha256').write_text(protocol_sha+'\n', encoding='ascii')

    entries = {}
    for item in imported_rows:
        source = exp.read_json(item['source_summary_path'])
        wrapper = dict(source)
        wrapper['origin_protocol_sha256'] = source['protocol_sha256']
        wrapper['protocol_sha256'] = protocol_sha
        wrapper['run_id'] = f"cross_run_import_{item['tree_sha256'][:12]}"
        wrapper['cache_origin'] = 'cross_run_verified'
        wrapper['evaluation_fingerprint'] = fingerprints['gp:train']
        wrapper['import_provenance'] = dict(
            source_run_directory=str(old_run),
            source_summary_path=item['source_summary_path'],
            source_summary_sha256=item['source_summary_sha256'],
            source_runner_result_sha256=item['source_runner_result_sha256'],
            source_protocol_sha256=item['source_protocol_sha256'])
        wrapper_path = run_dir/item['wrapper_summary_path']
        exp.write_new(wrapper_path, wrapper)
        entries[item['tree_sha256']] = dict(
            status='COMPLETED', J=item['J'], summary_path=str(wrapper_path.resolve()),
            protocol_sha256=protocol_sha, evaluation_fingerprint=fingerprints['gp:train'],
            cache_origin='cross_run_verified',
            source_protocol_sha256=item['source_protocol_sha256'])
    exp.write_new(run_dir/'cache'/'train.json',
                  dict(protocol_sha256=protocol_sha, entries=entries,
                       evaluation_fingerprint=fingerprints['gp:train'],
                       imported_entry_count=len(entries)))
    (training_dir/'training_trace.jsonl').open('x', encoding='utf-8').close()
    custom = verify_new_run(run_dir)
    return dict(run_directory=str(run_dir), protocol_sha256=custom['protocol']['protocol_sha256'],
                g0_members=50, distinct_g0_hashes=g0['distinct_tree_hash_count'],
                imported_cache_entries=len(entries), baseline_status=baseline['baseline_status'])


def verify_new_run(run_dir):
    run_dir = Path(run_dir).resolve()
    config, manifest, g0, protocol = exp.verify_locked_run(run_dir)
    if protocol.get('schema') != 'dpdp-gp-100-pop50-official-protocol-v1':
        raise ValueError('wrong population-50 protocol schema')
    if protocol.get('orchestration_source_sha256') != sha(__file__):
        raise ValueError('population-50 orchestration source changed after lock')
    if config['gp']['population_size'] != POPULATION_SIZE:
        raise ValueError('population-size mismatch')
    if config['gp']['evaluated_generations'] != GENERATIONS:
        raise ValueError('generation count mismatch')
    if len(g0['members']) != POPULATION_SIZE:
        raise ValueError('G0 member count mismatch')
    if exp.sha(run_dir/'baseline_reference.json') != protocol['baseline_reference_sha256']:
        raise ValueError('baseline reference changed after lock')
    if exp.sha(run_dir/'imported_cache_manifest.json') != protocol['imported_cache_manifest_sha256']:
        raise ValueError('cache import manifest changed after lock')
    current_fps = evaluation_fingerprints(config, manifest)
    if current_fps != protocol['evaluation_fingerprints']:
        raise ValueError('rollout evaluation fingerprint changed')
    if evolution_fingerprint(config, current_fps) != protocol['evolution_fingerprint']:
        raise ValueError('evolution fingerprint changed')
    cache = exp.read_json(run_dir/'cache'/'train.json')
    if cache.get('protocol_sha256') != protocol['protocol_sha256']:
        raise ValueError('run-local Train cache protocol mismatch')
    if cache.get('evaluation_fingerprint') != current_fps['gp:train']:
        raise ValueError('run-local Train cache evaluation fingerprint mismatch')
    return dict(config=config, manifest=manifest, g0=g0, protocol=protocol,
                evaluation_fingerprints=current_fps)


def key(entry):
    return entry[0], validate_tree(entry[1], LIMITS)[0], exp.canonical(entry[1])


def breed_with_trace(rng, evaluated, size=POPULATION_SIZE, tournament=3,
                     crossover_rate=.8, mutation_rate=.3, elitism=1):
    ranked = sorted(evaluated, key=key)
    trace = []
    def select():
        samples = [rng.choice(ranked) for _ in range(tournament)]
        winner = min(samples, key=key)
        return winner[1], dict(tournament_tree_hashes=[tree_hash(row[1]) for row in samples],
                               selected_tree_hash=tree_hash(winner[1]))
    next_generation = [tree for _, tree in ranked[:elitism]]
    for index, tree in enumerate(next_generation):
        trace.append(dict(child_member=index, operator='ELITE',
                          parent_hashes=[tree_hash(tree)],
                          child_tree_sha256=tree_hash(tree),
                          crossover=False, mutation=False))
    while len(next_generation) < size:
        member = len(next_generation)
        parent1, select1 = select()
        cross_draw = rng.random()
        parent2 = None
        select2 = None
        did_cross = cross_draw < crossover_rate
        child = parent1
        if did_cross:
            parent2, select2 = select()
            child = crossover(rng, parent1, parent2, LIMITS)
        mutate_draw = rng.random()
        did_mutate = mutate_draw < mutation_rate
        if did_mutate:
            child = mutate(rng, child, LIMITS)
        validate_tree(child, LIMITS)
        row = dict(child_member=member, operator='VARIATION',
                   parent_hashes=[tree_hash(parent1)] + ([tree_hash(parent2)] if parent2 else []),
                   child_tree_sha256=tree_hash(child),
                   parent1_tournament=select1, parent2_tournament=select2,
                   crossover_probability=crossover_rate, crossover_draw=cross_draw,
                   crossover=did_cross, mutation_probability=mutation_rate,
                   mutation_draw=mutate_draw, mutation=did_mutate)
        trace.append(row)
        next_generation.append(child)
    return next_generation, trace


def verify_breed_trace(rng, evaluated):
    state = rng.getstate()
    control = random.Random()
    control.setstate(state)
    expected = exp.breed(control, evaluated, POPULATION_SIZE, tournament=3,
                         crossover_rate=.8, mutation_rate=.3, elitism=1,
                         limits=LIMITS)
    observed, trace = breed_with_trace(rng, evaluated)
    if ([tree_hash(x) for x in expected] != [tree_hash(x) for x in observed]
            or control.getstate() != rng.getstate()):
        raise AssertionError('traced breeding diverged from the pinned GP breed implementation')
    return observed, trace


def save_tree_artifact(run_dir, generation, member, tree):
    return tree_record(run_dir, generation, member, tree, create=True)


def ensure_trace_event(path, event):
    key_tuple = (event.get('event'), event.get('generation'), event.get('member'))
    path = Path(path)
    if path.exists():
        for line in path.read_text(encoding='utf-8').splitlines():
            if not line.strip():
                continue
            prior = json.loads(line)
            prior_key = (prior.get('event'), prior.get('generation'), prior.get('member'))
            if prior_key == key_tuple:
                if prior.get('tree_sha256') != event.get('tree_sha256'):
                    raise ValueError(f'training trace conflict at {key_tuple}')
                return
    with path.open('a', encoding='utf-8', newline='\n') as handle:
        handle.write(json.dumps(event, sort_keys=True, ensure_ascii=False, allow_nan=False)+'\n')
        handle.flush()
        os.fsync(handle.fileno())


def write_if_same(path, value):
    path = Path(path)
    if path.exists():
        if exp.read_json(path) != value:
            raise ValueError(f'preserving conflicting artifact: {path}')
    else:
        exp.write_new(path, value)


def cache_origin_for(state, digest, existing_entry, local_summary_exists):
    imported = set(state.get('imported_tree_hashes', []))
    used = set(state.get('used_imported_tree_hashes', []))
    if existing_entry:
        if digest in imported and digest not in used:
            return 'cross_run_verified'
        return 'within_run'
    if local_summary_exists:
        return 'within_run_recovered'
    return 'new_rollout'


def persist_checkpoint(run_dir, state, session_started, generation_started):
    run_dir = Path(run_dir)
    cache_path = Path(state['train_cache_path'])
    trace_path = Path(state['training_trace_path'])
    state['train_cache_sha256'] = sha(cache_path)
    state['training_trace_sha256'] = sha(trace_path)
    state['elapsed_wall_seconds'] = state.get('elapsed_wall_seconds', 0.0) + (
        time.monotonic()-session_started)
    state['generation_elapsed_seconds'] = state.get('generation_elapsed_seconds', 0.0) + (
        time.monotonic()-generation_started)
    state['_session_elapsed_mark'] = time.monotonic()
    state['_generation_elapsed_mark'] = time.monotonic()
    exp.write_replace(run_dir/'official_training'/'resume_checkpoint.json', state)


def generation_statistics(generation, rows, lineage, elapsed):
    valid = [r for r in rows if r.get('status') == 'COMPLETED' and r.get('valid') is True
             and r.get('train_J') is not None]
    values = [Decimal(r['train_J']) for r in valid]
    hashes = [r['tree_sha256'] for r in rows]
    distinct_fitness = {Decimal(r['train_J']) for r in valid}
    if values:
        best = min(values); worst=max(values); med=statistics.median(values)
        mean=sum(values, Decimal(0))/Decimal(len(values))
        best_count=sum(1 for v in values if v==best)
    else:
        best=worst=med=mean=None; best_count=0
    return dict(
        generation=generation, label=f'G{generation}', population_size=POPULATION_SIZE,
        valid_count=len(valid), invalid_count=POPULATION_SIZE-len(valid),
        timeout_count=sum(1 for r in rows if r.get('status')=='TIMEOUT'),
        best_J=str(best) if best is not None else None,
        mean_J=str(mean) if mean is not None else None,
        median_J=str(med) if med is not None else None,
        worst_J=str(worst) if worst is not None else None,
        standard_deviation_J=statistics.pstdev([float(v) for v in values]) if len(values)>1 else 0.0,
        distinct_genotype_count=len(set(hashes)),
        distinct_fitness_count=len(distinct_fitness),
        members_with_best_fitness=best_count,
        cross_run_cache_hits=sum(1 for r in rows if r.get('cache_origin')=='cross_run_verified'),
        within_run_cache_hits=sum(1 for r in rows if r.get('cache_origin') in ('within_run','within_run_recovered')),
        new_rollout_count=sum(1 for r in rows if r.get('cache_origin')=='new_rollout'),
        actual_rollout_wall_seconds=sum(float(r.get('new_rollout_wall_seconds') or 0) for r in rows),
        generation_elapsed_wall_seconds=elapsed,
        lineage=lineage,
        members=rows,
    )


def maybe_reconcile_cache(run_dir, state):
    """Accept only one durable uncheckpointed result for the next member, if present."""
    cache = exp._load_cache(run_dir, 'train', state['protocol_sha256'])['entries']
    allowed = set(state.get('imported_tree_hashes', [])) | set(state.get('fitness_by_tree_hash', {}))
    extra = set(cache)-allowed
    generation=state['generation']; member=state['next_member']
    if not extra:
        return
    if member >= POPULATION_SIZE or len(extra)!=1:
        raise ValueError('Train cache differs from checkpoint beyond one pending member')
    population = [exp.load_tree(run_dir/r['tree_path'])[0] for r in state['population']]
    expected=tree_hash(population[member])
    if extra != {expected}:
        raise ValueError('uncheckpointed cache entry is not the pending member tree')
    entry=cache[expected]
    summary=exp.read_json(entry['summary_path'])
    if summary.get('protocol_sha256')!=state['protocol_sha256'] or summary.get('tree_sha256')!=expected:
        raise ValueError('pending cached summary provenance mismatch')


def validate_checkpoint(run_dir, state):
    checked=verify_new_run(run_dir)
    if state.get('schema')!=CHECKPOINT_SCHEMA:
        raise ValueError('unsupported population-50 checkpoint schema')
    if state.get('run_directory')!=str(Path(run_dir).resolve()):
        raise ValueError('checkpoint belongs to another run')
    if state.get('protocol_sha256')!=checked['protocol']['protocol_sha256']:
        raise ValueError('checkpoint protocol mismatch')
    if state.get('orchestration_source_sha256')!=sha(__file__):
        raise ValueError('checkpoint helper source changed')
    rng=random.Random(); rng.setstate(tupleize(state['gp_random_state']))
    if not 0<=int(state['generation'])<GENERATIONS:
        if state.get('phase') not in ('VALIDATION','GP_TEST','COMPLETE','FAILED'):
            raise ValueError('checkpoint generation out of range')
    if state.get('phase')=='TRAIN':
        if len(state['population'])!=POPULATION_SIZE:
            raise ValueError('checkpoint population size mismatch')
        for row in state['population']:
            tree,_=exp.load_tree(Path(run_dir)/row['tree_path'])
            if tree_hash(tree)!=row['tree_sha256']:
                raise ValueError('checkpoint tree artifact hash mismatch')
    maybe_reconcile_cache(run_dir,state)
    return checked


@contextmanager
def active_lock(run_dir):
    path=Path(run_dir)/'official_training'/'active_run.lock'
    payload=dict(pid=os.getpid(),started_utc=utc_now(),runner_sha256=sha(__file__))
    while True:
        try:
            with path.open('x',encoding='utf-8') as handle:
                json.dump(payload,handle,sort_keys=True)
                handle.flush(); os.fsync(handle.fileno())
            break
        except FileExistsError:
            try:
                prior=json.loads(path.read_text(encoding='utf-8'))
                pid=int(prior['pid'])
            except Exception:
                raise RuntimeError(f'cannot verify existing active-run lock: {path}')
            alive=True
            try:
                os.kill(pid,0)
            except ProcessLookupError:
                alive=False
            except PermissionError:
                alive=True
            if alive:
                raise RuntimeError(f'run already active under pid {pid}')
            path.unlink()
    try:
        yield
    finally:
        try:
            if path.exists() and json.loads(path.read_text(encoding='utf-8')).get('pid')==os.getpid():
                path.unlink()
        except OSError:
            pass


def run_training(run_dir, resume=False):
    run_dir=Path(run_dir).resolve()
    checkpoint_path=run_dir/'official_training'/'resume_checkpoint.json'
    if not checkpoint_path.is_file():
        raise FileNotFoundError(f'missing checkpoint: {checkpoint_path}')
    with active_lock(run_dir):
        state=exp.read_json(checkpoint_path)
        validate_checkpoint(run_dir,state)
        if state['phase']=='COMPLETE':
            print('Run already COMPLETED; no rollout launched.',flush=True)
            return exp.read_json(run_dir/'official_training'/'training_result.json')
        session_started=time.monotonic()
        generation_started=session_started
        elapsed_base=float(state.get('elapsed_wall_seconds',0.0))
        gen_elapsed_base=float(state.get('generation_elapsed_seconds',0.0))
        if resume:
            print(f"RESUME G{state.get('generation')} M{state.get('next_member')} phase={state['phase']}",flush=True)
        else:
            print(f"START G{state.get('generation')} M{state.get('next_member')}",flush=True)
        while state['phase']=='TRAIN':
            generation=int(state['generation'])
            population_records=list(state['population'])
            population=[exp.load_tree(run_dir/r['tree_path'])[0] for r in population_records]
            member_rows=list(state['generation_member_rows'])
            start_member=int(state['next_member'])
            if start_member<POPULATION_SIZE:
                generation_started=time.monotonic()
                gen_elapsed_base=float(state.get('generation_elapsed_seconds',0.0))
            for member in range(start_member,POPULATION_SIZE):
                tree=population[member]
                saved=save_tree_artifact(run_dir,generation,member,tree)
                digest=tree_hash(tree)
                cache=exp._load_cache(run_dir,'train',state['protocol_sha256'])['entries']
                existing=cache.get(digest)
                local_summary_exists=(run_dir/'rollouts'/'train'/digest/'rollout_summary.json').is_file()
                origin=cache_origin_for(state,digest,existing,local_summary_exists)
                evaluation_started=time.monotonic()
                summary=exp.evaluate_cached(run_dir,'train',tree,
                    f'official_g{generation}_m{member:02d}_train')
                evaluation_call_wall=time.monotonic()-evaluation_started
                row=exp._member_record(generation,member,tree,summary)
                row['valid']=summary.get('valid')
                row['expression']=tree.text()
                row['tree_path']=saved['tree_path']
                row['cache_origin']=origin
                row['evaluation_call_wall_seconds']=evaluation_call_wall
                row['new_rollout_wall_seconds']=(
                    summary.get('actual_wall_seconds') if origin in ('new_rollout','within_run_recovered') else 0.0)
                row['historical_rollout_wall_seconds']=(
                    summary.get('actual_wall_seconds') if origin=='cross_run_verified' else 0.0)
                row['decision_count']=summary.get('decision_count')
                row['feasibility_status']=summary.get('feasibility_status')
                row['independent_score_matches_runner']=summary.get('independent_score_matches_runner')
                row['completed_orders']=summary.get('completed_orders')
                row['completed_items']=summary.get('completed_items')
                row['timeout_status']=summary.get('timeout_status')
                row['peak_memory_bytes']=summary.get('peak_memory_bytes')
                member_rows.append(row)
                digest=tree_hash(tree)
                state['fitness_by_tree_hash'][digest]=dict(
                    status=row['status'],valid=row['valid'],J=row['train_J'],
                    summary_path=str((run_dir/'rollouts'/'train'/digest/'rollout_summary.json').resolve()),
                    cache_origin=origin)
                if origin=='cross_run_verified':
                    state.setdefault('used_imported_tree_hashes',[]).append(digest)
                    state['cross_run_cache_hits']+=1
                    state['historical_rollout_wall_reused_seconds']+=float(summary.get('actual_wall_seconds') or 0)
                elif origin in ('within_run','within_run_recovered'):
                    state['within_run_cache_hits']+=1
                    if origin=='within_run_recovered':
                        state['recovered_rollout_artifacts']+=1
                else:
                    state['new_rollouts']+=1
                    state['actual_new_rollout_wall_seconds']+=float(summary.get('actual_wall_seconds') or 0)
                event=dict(event='TRAIN_MEMBER',**row)
                ensure_trace_event(run_dir/'official_training'/'training_trace.jsonl',event)
                state['generation_member_rows']=member_rows
                state['next_member']=member+1
                state['gp_random_state']=state['gp_random_state']
                state['elapsed_wall_seconds']=elapsed_base + (time.monotonic()-session_started)
                state['generation_elapsed_seconds']=gen_elapsed_base + (time.monotonic()-generation_started)
                cache_file=run_dir/'cache'/'train.json'
                state['train_cache_sha256']=sha(cache_file)
                state['training_trace_sha256']=sha(run_dir/'official_training'/'training_trace.jsonl')
                exp.write_replace(checkpoint_path,state)
                print(f"G{generation} M{member}: {row['status']} J={row['train_J']} origin={origin} positions={generation*POPULATION_SIZE+member+1}/500",flush=True)

            # Every member in this generation now has a persisted row.
            lineage=state['lineage_by_generation'][generation] if generation<len(state['lineage_by_generation']) else []
            gen_elapsed=gen_elapsed_base + (time.monotonic()-generation_started)
            generation_row=generation_statistics(generation,member_rows,lineage,gen_elapsed)
            generation_path=run_dir/'official_training'/f'g{generation}.json'
            write_if_same(generation_path,dict(protocol_sha256=state['protocol_sha256'],**generation_row))
            state['generation_history']=[g for g in state['generation_history'] if g.get('generation')!=generation]
            state['generation_history'].append(generation_row)
            state['generation_history'].sort(key=lambda x:x['generation'])
            ensure_trace_event(run_dir/'official_training'/'training_trace.jsonl',
                dict(event='GENERATION_COMPLETE',generation=generation,
                     best_J=generation_row['best_J'],valid_count=generation_row['valid_count'],
                     distinct_genotype_count=generation_row['distinct_genotype_count']))
            if generation_row['valid_count']==0:
                state['phase']='FAILED'
                state['failure']='no valid parent in generation'
                state['generation_member_rows']=member_rows
                exp.write_replace(checkpoint_path,state)
                raise RuntimeError(f'no valid parent in G{generation}')
            if generation==GENERATIONS-1:
                state['phase']='VALIDATION'
                state['validation_index']=0
                state['validation_records']=[]
                state['generation_member_rows']=member_rows
                state['elapsed_wall_seconds']=elapsed_base+(time.monotonic()-session_started)
                state['generation_elapsed_seconds']=gen_elapsed
                state['train_cache_sha256']=sha(run_dir/'cache'/'train.json')
                state['training_trace_sha256']=sha(run_dir/'official_training'/'training_trace.jsonl')
                exp.write_replace(checkpoint_path,state)
                print(f"G{generation}: valid={generation_row['valid_count']}/50",flush=True)
                break
            evaluated=[]
            for row in member_rows:
                if row.get('status')=='COMPLETED' and row.get('valid') is True and row.get('train_J') is not None:
                    tree=exp.load_tree(run_dir/row['tree_path'])[0]
                    evaluated.append((Decimal(row['train_J']),tree))
            rng=random.Random(); rng.setstate(tupleize(state['gp_random_state']))
            observed,lineage_next=verify_breed_trace(rng,evaluated)
            next_generation=generation+1
            next_records=[save_tree_artifact(run_dir,next_generation,i,t)
                          for i,t in enumerate(observed)]
            transition=dict(
                generation_from=generation,generation_to=next_generation,
                source_best_J=generation_row['best_J'],
                population_size=POPULATION_SIZE,
                tournament_size=3,crossover_probability=.8,mutation_probability=.3,elitism=1,
                rng_state_before_sha256=digest_json(state['gp_random_state']),
                rng_state_after=rng.getstate(),
                lineage_events=lineage_next,
                next_population=[dict(member=i,tree_sha256=tree_hash(t),
                    expression=t.text(),depth=validate_tree(t,LIMITS)[1],
                    nodes=validate_tree(t,LIMITS)[0],tree_path=next_records[i]['tree_path'])
                    for i,t in enumerate(observed)])
            exp.write_new(run_dir/'official_training'/f'breeding_g{generation}_to_g{next_generation}.json',transition)
            state['lineage_by_generation'].append(lineage_next)
            next_pop=transition['next_population']
            state['populations'].append(next_pop)
            state['population']=next_pop
            state['generation']=next_generation
            state['next_member']=0
            state['generation_member_rows']=[]
            state['gp_random_state']=rng.getstate()
            state['generation_elapsed_seconds']=0.0
            state['elapsed_wall_seconds']=elapsed_base+(time.monotonic()-session_started)
            state['train_cache_sha256']=sha(run_dir/'cache'/'train.json')
            state['training_trace_sha256']=sha(run_dir/'official_training'/'training_trace.jsonl')
            ensure_trace_event(run_dir/'official_training'/'training_trace.jsonl',
                dict(event='BREED',generation=generation,next_generation=next_generation,
                     population_size=POPULATION_SIZE,offspring_tree_hashes=[x['tree_sha256'] for x in next_pop]))
            state['training_trace_sha256']=sha(run_dir/'official_training'/'training_trace.jsonl')
            exp.write_replace(checkpoint_path,state)
            elapsed_base=state['elapsed_wall_seconds']
            gen_elapsed_base=0.0
            print(f"G{generation}: valid={generation_row['valid_count']}/50; bred G{next_generation}",flush=True)

        if state['phase']=='VALIDATION':
            self_validate_and_select(run_dir,state,checkpoint_path,session_started,elapsed_base)
            state=exp.read_json(checkpoint_path)
        if state['phase']=='GP_TEST':
            selected=exp.load_tree(run_dir/'trees'/'selected_official_tree.json')[0]
            gp_test=exp.run_rollout(run_dir,policy='gp',partition='test',tree=selected,
                                   run_id='official_selected_gp_test')
            state['gp_test']=gp_test
            ensure_trace_event(run_dir/'official_training'/'training_trace.jsonl',
                dict(event='GP_TEST',status=gp_test['status'],J=gp_test.get('J'),
                     tree_sha256=tree_hash(selected)))
            state['phase']='COMPLETE' if gp_test.get('status')=='COMPLETED' and gp_test.get('J') is not None else 'FAILED'
            if state['phase']=='FAILED':
                state['failure']='GP Test incomplete or invalid'
            state['elapsed_wall_seconds']=elapsed_base+(time.monotonic()-session_started)
            state['training_trace_sha256']=sha(run_dir/'official_training'/'training_trace.jsonl')
            exp.write_replace(checkpoint_path,state)
            if state['phase']=='FAILED':
                raise RuntimeError('selected GP Test incomplete; J remains null')
        if state['phase']=='COMPLETE':
            final=build_final_result(run_dir,state)
            write_if_same(run_dir/'official_training'/'training_result.json',final)
            write_if_same(run_dir/'official_training'/'resume_result.json',final)
            write_comparison_files(run_dir,state,final)
            report=build_report(run_dir,state,final)
            exp.write_replace(run_dir/'OFFICIAL_RESULTS_REPORT.md',dict(text=report))
            # Keep the requested Markdown report as a plain UTF-8 file.
            (run_dir/'OFFICIAL_RESULTS_REPORT.md').write_text(report,encoding='utf-8',newline='\n')
            print('Population-50 experiment COMPLETED.',flush=True)
            return final
        return state


def self_validate_and_select(run_dir,state,checkpoint_path,session_started,elapsed_base):
    run_dir=Path(run_dir)
    protocol=verify_new_run(run_dir)['protocol']
    cache=exp._load_cache(run_dir,'train',protocol['protocol_sha256'])['entries']
    actual_trees={}
    for population in state['populations']:
        for rec in population:
            tree=exp.load_tree(run_dir/rec['tree_path'])[0]
            digest=rec['tree_sha256']
            fit=state['fitness_by_tree_hash'].get(digest)
            if fit and fit.get('status')=='COMPLETED' and fit.get('valid') is True and fit.get('J') is not None:
                actual_trees.setdefault(digest,dict(tree=tree,train_J=fit['J'],
                    nodes=validate_tree(tree,LIMITS)[0],provenance=[]))
                actual_trees[digest]['provenance'].append(dict(
                    generation=rec['generation'],member=rec['member']))
    candidates=sorted(actual_trees.values(),
        key=lambda x:(Decimal(x['train_J']),x['nodes'],exp.canonical(x['tree'])))[:5]
    if not candidates:
        raise RuntimeError('no valid tree from current population history for Validation')
    candidate_manifest=[dict(rank=i+1,expression=x['tree'].text(),
        tree_sha256=tree_hash(x['tree']),train_J=x['train_J'],nodes=x['nodes'],
        population_provenance=x['provenance']) for i,x in enumerate(candidates)]
    write_if_same(run_dir/'official_training'/'validation_candidates.json',
        dict(protocol_sha256=protocol['protocol_sha256'],candidates=candidate_manifest,
             selection_basis='only trees observed in G0-G9; unique canonical hash; sort by raw Train J'))
    records=list(state.get('validation_records',[]))
    for index in range(int(state.get('validation_index',0)),len(candidates)):
        item=candidates[index]; tree=item['tree']; digest=tree_hash(tree)
        tree_record(run_dir,10,index,tree,create=True)
        summary=exp.run_rollout(run_dir,policy='gp',partition='validation',tree=tree,
                                run_id=f'official_validation_{index+1:02d}')
        runner_result=exp.read_json(summary['runner_result_path']) if summary.get('runner_result_path') else {}
        score=runner_result.get('score') or {}
        record=dict(rank=index+1,expression=tree.text(),tree_sha256=digest,
            train_J=item['train_J'],validation_J=summary.get('J'),
            status=summary.get('status'),valid=summary.get('valid'),
            feasibility_status=summary.get('feasibility_status'),
            independent_score_matches_runner=summary.get('independent_score_matches_runner'),
            actual_wall_seconds=summary.get('actual_wall_seconds'),
            distance_km=score.get('total_distance_km'),
            tardiness_seconds=score.get('total_tardiness_seconds'),
            late_original_orders=score.get('late_original_orders'),
            decision_count=summary.get('decision_count'),
            population_provenance=item['provenance'],
            summary_path=str((run_dir/'rollouts'/'validation'/digest/'rollout_summary.json').resolve()))
        records.append(record)
        state['validation_records']=records
        state['validation_index']=index+1
        state['elapsed_wall_seconds']=elapsed_base+(time.monotonic()-session_started)
        exp.write_replace(checkpoint_path,state)
        ensure_trace_event(run_dir/'official_training'/'training_trace.jsonl',
            dict(event='VALIDATION',generation=None,member=index,status=record['status'],
                 J=record['validation_J'],tree_sha256=digest))
        state['training_trace_sha256']=sha(run_dir/'official_training'/'training_trace.jsonl')
        exp.write_replace(checkpoint_path,state)
        print(f"Validation {index+1}/{len(candidates)}: {record['status']} J={record['validation_J']}",flush=True)
        if record['status']!='COMPLETED' or not record.get('valid') or record['validation_J'] is None:
            state['phase']='FAILED'; state['failure']=f'Validation candidate {index+1} invalid'
            exp.write_replace(checkpoint_path,state)
            raise RuntimeError(f'Validation candidate {index+1} invalid; no score or replacement')
    if len(records)<len(candidates):
        raise RuntimeError('Validation checkpoint does not contain all candidate results')
    selected=min(records,key=lambda x:(Decimal(x['validation_J']),Decimal(x['train_J']),
                                       validate_tree(exp.load_tree(run_dir/'trees'/'selected_candidate_tmp.json')[0],LIMITS)[0]
                                       if False else x.get('nodes',0), x['tree_sha256']))
    # Apply the protocol tie-break explicitly using stored node count and canonical tree.
    selected=min(records,key=lambda x:(Decimal(x['validation_J']),Decimal(x['train_J']),
        next(c['nodes'] for c in candidate_manifest if c['tree_sha256']==x['tree_sha256']),
        exp.canonical(exp.load_tree(tree_record(run_dir,10,x['rank']-1,
            exp.load_tree(run_dir/next(rec['tree_path'] for pop in state['populations']
              for rec in pop if rec['tree_sha256']==x['tree_sha256']))[0],create=True)['tree_path'])[0])))
    selected_tree=exp.load_tree(run_dir/next(rec['tree_path'] for pop in state['populations']
                       for rec in pop if rec['tree_sha256']==selected['tree_sha256']))[0]
    candidate_records=[dict(rank=r['rank'],tree_sha256=r['tree_sha256'],expression=r['expression'],
        train_J=r['train_J'],validation_J=r['validation_J'],nodes=next(
            c['nodes'] for c in candidate_manifest if c['tree_sha256']==r['tree_sha256']),
        provenance=r['population_provenance']) for r in records]
    decision=dict(protocol_sha256=protocol['protocol_sha256'],selection_timestamp_utc=utc_now(),
        selected_expression=selected_tree.text(),selected_tree_sha256=tree_hash(selected_tree),
        train_J=selected['train_J'],validation_J=selected['validation_J'],
        tie_break_reason='minimum Validation J; then Train J, node count, canonical tree',
        candidates=candidate_records)
    write_if_same(run_dir/'official_training'/'selection_decision.json',decision)
    selected_path=run_dir/'trees'/'selected_official_tree.json'
    if not selected_path.exists():
        exp.save_tree(selected_path,selected_tree,training=dict(
            protocol_sha256=protocol['protocol_sha256'],
            train_J=selected['train_J'],validation_J=selected['validation_J'],
            selection='Validation J, then Train J, node count, canonical'),
            limits=LIMITS)
    state['selected_tree_sha256']=tree_hash(selected_tree)
    state['phase']='GP_TEST'
    state['elapsed_wall_seconds']=elapsed_base+(time.monotonic()-session_started)
    exp.write_replace(checkpoint_path,state)
    print(f"Selected tree {state['selected_tree_sha256']} Train J={selected['train_J']} Validation J={selected['validation_J']}",flush=True)


def write_csv(path, rows, fields):
    path=Path(path)
    with path.open('w',encoding='utf-8-sig',newline='') as handle:
        writer=csv.DictWriter(handle,fieldnames=fields,extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)


def write_comparison_files(run_dir,state,final):
    generations=state['generation_history']
    all_members=[m for g in generations for m in g['members']]
    write_csv(run_dir/'evolution_history.csv',all_members,
        ['generation','member','tree_sha256','expression','depth','nodes','train_J',
         'status','valid','cache_origin','cache_hit','evaluation_call_wall_seconds',
         'new_rollout_wall_seconds','historical_rollout_wall_seconds',
         'decision_count','feasibility_status','independent_score_matches_runner',
         'completed_orders','completed_items','timeout_status','peak_memory_bytes'])
    best_rows=[]
    for g in generations:
        best_rows.append({k:g.get(k) for k in (
            'generation','valid_count','invalid_count','timeout_count','best_J','mean_J',
            'median_J','worst_J','standard_deviation_J','distinct_genotype_count',
            'distinct_fitness_count','members_with_best_fitness','cross_run_cache_hits',
            'within_run_cache_hits','new_rollout_count','actual_rollout_wall_seconds',
            'generation_elapsed_wall_seconds')})
    write_csv(run_dir/'best_fitness_by_generation.csv',best_rows,list(best_rows[0].keys()))
    trees={}
    for row in all_members:
        digest=row['tree_sha256']
        item=trees.setdefault(digest,dict(tree_sha256=digest,expression=row['expression'],
            depth=row['depth'],nodes=row['nodes'],fitness_values=[],population_provenance=[]))
        if row.get('train_J') is not None:
            item['fitness_values'].append(row['train_J'])
        item['population_provenance'].append(f"G{row['generation']}/M{row['member']}")
    all_rows=[]
    for item in trees.values():
        item['fitness_values']=sorted(set(item['fitness_values']),key=Decimal)
        item['population_provenance']=';'.join(item['population_provenance'])
        item['best_train_J']=item['fitness_values'][0] if item['fitness_values'] else None
        all_rows.append(item)
    write_csv(run_dir/'all_trees.csv',all_rows,
        ['tree_sha256','expression','depth','nodes','fitness_values','best_train_J','population_provenance'])

    oldrun=OLD_RUN
    oldresult=exp.read_json(oldrun/'official_training'/'resume_result.json')
    oldcache=exp.read_json(oldrun/'cache'/'train.json')
    oldtrain_summaries=[exp.read_json(p) for p in (oldrun/'rollouts'/'train').glob('*/rollout_summary.json')]
    oldbest=Decimal(min((m['train_J'] for g in oldresult['train_generations'] for m in g['members']),key=Decimal))
    newbest=min((Decimal(m['train_J']) for m in all_members if m.get('train_J') is not None),default=None)
    old_gp=oldresult['gp_test']; old_gp_score=exp.read_json(old_gp['runner_result_path'])['score']
    old_vnsme=state['baseline_reference']['score']
    new_gp=final['gp_test']; new_gpscore=exp.read_json(new_gp['runner_result_path'])['score']
    comparison=[
        dict(method='GP population 10',population=10,generations=10,
             best_train_J=str(oldbest),best_validation_J=oldresult['selected_validation_J'],
             test_J=old_gp['J'],test_distance_km=old_gp_score['total_distance_km'],
             test_tardiness_seconds=old_gp_score['total_tardiness_seconds'],
             test_late_orders=old_gp_score['late_original_orders'],
             distinct_train_trees=len(oldcache['entries']),
             historical_train_rollout_wall_seconds=sum(x['actual_wall_seconds'] for x in oldtrain_summaries),
             new_train_rollout_wall_seconds=0,cache_hits='historical run',
             test_wall_seconds=old_gp['actual_wall_seconds'],baseline_role='reference run'),
        dict(method='GP population 50',population=50,generations=10,
             best_train_J=str(newbest),best_validation_J=final['selected_validation_J'],
             test_J=new_gp['J'],test_distance_km=new_gpscore['total_distance_km'],
             test_tardiness_seconds=new_gpscore['total_tardiness_seconds'],
             test_late_orders=new_gpscore['late_original_orders'],
             distinct_train_trees=len(state['fitness_by_tree_hash']),
             historical_train_rollout_wall_seconds=state['historical_rollout_wall_reused_seconds'],
             new_train_rollout_wall_seconds=state['actual_new_rollout_wall_seconds'],
             cache_hits=f"cross-run {state['cross_run_cache_hits']}; within-run {state['within_run_cache_hits']}",
             test_wall_seconds=new_gp['actual_wall_seconds'],
             baseline_role='new sensitivity run'),
        dict(method='VNSME reference',population=None,generations=None,
             best_train_J=None,best_validation_J=None,test_J=old_vnsme['J'],
             test_distance_km=old_vnsme['distance_km'],
             test_tardiness_seconds=old_vnsme['tardiness_seconds'],
             test_late_orders=old_vnsme['late_orders'],distinct_train_trees=None,
             historical_train_rollout_wall_seconds=None,new_train_rollout_wall_seconds=0,
             cache_hits='REUSED_VERIFIED',test_wall_seconds=old_vnsme['actual_wall_seconds'],
             baseline_role='historical VNSME runtime; excluded from new run runtime'),
    ]
    write_csv(run_dir/'population_comparison.csv',comparison,list(comparison[0].keys()))


def build_final_result(run_dir,state):
    selected=exp.read_json(run_dir/'official_training'/'selection_decision.json')
    gp=state['gp_test']
    metrics=dict(
        total_member_positions=POPULATION_SIZE*GENERATIONS,
        generations_completed=GENERATIONS,
        population_size=POPULATION_SIZE,
        train_rollout_requests=POPULATION_SIZE*GENERATIONS,
        cross_run_cache_hits=state['cross_run_cache_hits'],
        within_run_cache_hits=state['within_run_cache_hits'],
        new_rollouts=state['new_rollouts'],
        recovered_rollout_artifacts=state['recovered_rollout_artifacts'],
        distinct_evaluated_trees=len(state['fitness_by_tree_hash']),
        historical_rollout_wall_reused_seconds=state['historical_rollout_wall_reused_seconds'],
        actual_new_rollout_wall_seconds=state['actual_new_rollout_wall_seconds'],
        elapsed_wall_seconds=state['elapsed_wall_seconds'],
    )
    return dict(status='COMPLETED',protocol_sha256=state['protocol_sha256'],
        evolution_fingerprint=verify_new_run(run_dir)['protocol']['evolution_fingerprint'],
        evaluation_fingerprints=verify_new_run(run_dir)['evaluation_fingerprints'],
        generations_completed=GENERATIONS,population_size=POPULATION_SIZE,
        train_rollout_requests=POPULATION_SIZE*GENERATIONS,
        generation_summaries=state['generation_history'],
        validation_candidates=state['validation_records'],
        selected_expression=selected['selected_expression'],
        selected_tree_sha256=selected['selected_tree_sha256'],
        selected_train_J=selected['train_J'],
        selected_validation_J=selected['validation_J'],
        selection_decision=selected,
        gp_test=gp,
        baseline_reference=state['baseline_reference'],
        baseline_status=state['baseline_reference']['baseline_status'],
        cache_statistics=metrics,
        elapsed_wall_seconds=state['elapsed_wall_seconds'],
        completed_at_utc=utc_now())


def build_report(run_dir,state,final):
    config=exp.read_json(run_dir/'experiment_config.json')
    oldresult=exp.read_json(OLD_RUN/'official_training'/'resume_result.json')
    oldselection=exp.read_json(OLD_RUN/'official_training'/'selection_decision.json')
    oldgp=oldresult['gp_test']; oldgpr=exp.read_json(oldgp['runner_result_path'])['score']
    baseline=state['baseline_reference']['score']
    gp=final['gp_test']; gpr=exp.read_json(gp['runner_result_path'])['score']
    gens=state['generation_history']
    lines=[
        '# GP–DPDP Official Experiment — Instance 9, Population 50',
        '',
        '## 1. Kết quả',
        '',
        '**Trạng thái: COMPLETED.** Đã hoàn tất G0–G9, Validation top 5, Selection và GP Test. VNSME không chạy lại; baseline VNSME đã được xác minh và reuse từ run population 10.',
        '',
        f"- Run: {run_dir.relative_to(ROOT)}",
        f"- Protocol SHA-256: {final['protocol_sha256']}",
        f"- Evolution fingerprint: {final['evolution_fingerprint']}",
        f"- Rollout evaluation fingerprints: {json.dumps(final['evaluation_fingerprints'],ensure_ascii=False,sort_keys=True)}",
        f"- Instance 9; 100 original orders; 175 items; 5 vehicles; split 55/20/25; GP seed 42; simulator seed 0.",
        '- Population 50; 10 generations (G0–G9); total 500 member positions; elitism 1; tournament 3; crossover 0.8; mutation 0.3; depth 2–5; max nodes 63.',
        '',
        '## 2. Generation history',
        '',
        '| G | Valid | Best J | Mean J | Median J | Worst J | Distinct genotypes | Distinct fitness | Cross-run hits | Within-run hits | New rollouts | New rollout wall (s) |',
        '|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|',
    ]
    for g in gens:
        lines.append(f"| G{g['generation']} | {g['valid_count']}/50 | {g['best_J']} | {g['mean_J']} | {g['median_J']} | {g['worst_J']} | {g['distinct_genotype_count']} | {g['distinct_fitness_count']} | {g['cross_run_cache_hits']} | {g['within_run_cache_hits']} | {g['new_rollout_count']} | {g['actual_rollout_wall_seconds']:.3f} |")
    lines += ['', 'Full per-member history, raw J, expression, tree hash, depth, nodes and cache origin are in official_training/g0.json … g9.json and evolution_history.csv. GP RNG state and next member are saved in official_training/resume_checkpoint.json.']
    lines += ['', '## 3. Validation top 5', '',
        '| Rank | Tree hash | Train J | Validation J | Distance km | Tardiness s | Late orders | Wall s | Feasibility / independent score |',
        '|---:|---|---:|---:|---:|---:|---:|---:|---|']
    for r in final['validation_candidates']:
        summary=exp.read_json(r['summary_path'])
        rr=exp.read_json(summary['runner_result_path']); sc=rr['score']
        lines.append(f"| {r['rank']} | {r['tree_sha256']} | {r['train_J']} | {r['validation_J']} | {sc['total_distance_km']} | {sc['total_tardiness_seconds']} | {sc['late_original_orders']} | {summary['actual_wall_seconds']:.3f} | {summary['feasibility_status']} / {summary['independent_score_matches_runner']} |")
    sel=final['selection_decision']
    lines += ['', '## 4. Selected tree', '',
        f"- Expression: {sel['selected_expression']}",
        f"- Tree SHA-256: {sel['selected_tree_sha256']}",
        f"- Depth/nodes: {exp.read_json(run_dir/'trees'/'selected_official_tree.json')['depth']}/{exp.read_json(run_dir/'trees'/'selected_official_tree.json')['nodes']}",
        f"- Train J: {sel['train_J']}",
        f"- Validation J: {sel['validation_J']}",
        f"- Tie-break: {sel['tie_break_reason']}",
        '',
        '## 5. GP Test and VNSME reference',
        '',
        '| Method | Status | Raw J | Distance km | Tardiness s | Late orders | Wall s | Decisions | Orders/items | Feasibility | Independent score |',
        '|---|---|---:|---:|---:|---:|---:|---:|---:|---|---|',
        f"| GP population 10 reference | {oldgp['status']} | {oldgp['J']} | {oldgpr['total_distance_km']} | {oldgpr['total_tardiness_seconds']} | {oldgpr['late_original_orders']} | {oldgp['actual_wall_seconds']:.3f} | {oldgp['decision_count']} | {oldgp['completed_orders']}/{oldgp['completed_items']} | {oldgp['feasibility_status']} | {oldgp['independent_score_matches_runner']} |",
        f"| GP population 50 | {gp['status']} | {gp['J']} | {gpr['total_distance_km']} | {gpr['total_tardiness_seconds']} | {gpr['late_original_orders']} | {gp['actual_wall_seconds']:.3f} | {gp['decision_count']} | {gp['completed_orders']}/{gp['completed_items']} | {gp['feasibility_status']} | {gp['independent_score_matches_runner']} |",
        f"| VNSME REUSED_VERIFIED | COMPLETED | {baseline['J']} | {baseline['distance_km']} | {baseline['tardiness_seconds']} | {baseline['late_orders']} | historical {baseline['actual_wall_seconds']:.3f} | {baseline['decision_count']} | {baseline['completed_orders']}/{baseline['completed_items']} | {baseline['feasibility']} | {baseline['independent_score_matches_runner']} |",
        '',
        f"Population-10 reference: best Train J={min((Decimal(m['train_J']) for g in oldresult['train_generations'] for m in g['members'] if m.get('train_J') is not None))}; best Validation J={oldselection['validation_J']}; Test J={oldgp['J']}; distinct valid Train trees={len(exp.read_json(OLD_RUN/'cache'/'train.json')['entries'])}; Train rollout wall={sum(exp.read_json(p)['actual_wall_seconds'] for p in (OLD_RUN/'rollouts'/'train').glob('*/rollout_summary.json')):.3f}s.",
        f"Population-50: best Train J={min(Decimal(m['train_J']) for g in gens for m in g['members'] if m.get('train_J') is not None)}; best Validation J={sel['validation_J']}; distinct evaluated trees={final['cache_statistics']['distinct_evaluated_trees']}.",
        'Hai GP run dùng cùng Test partition; kết quả là comparative sensitivity analysis, không phải holdout độc lập mới. Một GP seed không đủ để kết luận population 50 luôn tốt hơn.',
        '',
        '## 6. Cache, runtime và resume',
        '',
        f"- Imported verified Train cache entries: {len(exp.read_json(run_dir/'imported_cache_manifest.json')['entries'])}; actual cross-run hits: {state['cross_run_cache_hits']}; within-run hits: {state['within_run_cache_hits']}; new rollouts: {state['new_rollouts']}.",
        f"- Historical rollout wall được reuse (chỉ tính entry dùng): {state['historical_rollout_wall_reused_seconds']:.3f}s; actual wall của rollout mới: {state['actual_new_rollout_wall_seconds']:.3f}s.",
        f"- Population-50 orchestration elapsed wall: {state['elapsed_wall_seconds']:.3f}s. VNSME historical wall {baseline['actual_wall_seconds']:.3f}s không cộng vào elapsed của run mới.",
        '- Checkpoint được ghi sau từng member và generation; resume khôi phục current population, next generation/member, exact GP RNG state, fitness, run-local cache fingerprint và history.',
        '- Baseline VNSME: REUSED_VERIFIED; không khởi chạy Java runner.',
        '',
        '## 7. Artifact index',
        '',
        '- experiment_config.json; protocol.json; temporal_split_manifest.json',
        '- baseline_reference.json; imported_cache_manifest.json; cache/train.json',
        '- g0_population_manifest.json; trees/g0_m00.json … g0_m49.json',
        '- official_training/g0.json … g9.json; training_trace.jsonl; resume_checkpoint.json',
        '- official_training/validation_candidates.json; selection_decision.json; training_result.json; resume_result.json',
        '- trees/selected_official_tree.json; evolution_history.csv; best_fitness_by_generation.csv; all_trees.csv; population_comparison.csv',
        '- Raw Train/Validation/GP Test rollout, runner, independent score and supervisor artifacts are in the run directory.',
        '',
        f"Final result status: {final['status']}; baseline_status: {final['baseline_status']}; protocol SHA-256: {final['protocol_sha256']}.",
    ]
    return '\n'.join(lines)+'\n'


def write_comparison_outputs(run_dir,state,final):
    # Member-level history includes all positions, including duplicates.
    members=[m for g in state['generation_history'] for m in g['members']]
    write_csv(run_dir/'evolution_history.csv',members,
        ['generation','member','tree_sha256','expression','depth','nodes','train_J',
         'status','valid','cache_origin','cache_hit','evaluation_call_wall_seconds',
         'new_rollout_wall_seconds','historical_rollout_wall_seconds','decision_count',
         'feasibility_status','independent_score_matches_runner','completed_orders',
         'completed_items','timeout_status','peak_memory_bytes'])
    best_rows=[{k:g.get(k) for k in ('generation','valid_count','invalid_count',
        'timeout_count','best_J','mean_J','median_J','worst_J','standard_deviation_J',
        'distinct_genotype_count','distinct_fitness_count','members_with_best_fitness',
        'cross_run_cache_hits','within_run_cache_hits','new_rollout_count',
        'actual_rollout_wall_seconds','generation_elapsed_wall_seconds')}
        for g in state['generation_history']]
    write_csv(run_dir/'best_fitness_by_generation.csv',best_rows,list(best_rows[0]))
    grouped={}
    for m in members:
        row=grouped.setdefault(m['tree_sha256'],dict(tree_sha256=m['tree_sha256'],
            expression=m['expression'],depth=m['depth'],nodes=m['nodes'],fitness=[],
            provenance=[]))
        if m.get('train_J') is not None: row['fitness'].append(m['train_J'])
        row['provenance'].append(f"G{m['generation']}/M{m['member']}")
    all_rows=[]
    for row in grouped.values():
        row['fitness']=sorted(set(row['fitness']),key=Decimal)
        row['best_train_J']=row['fitness'][0] if row['fitness'] else None
        row['fitness']=';'.join(row['fitness'])
        row['provenance']=';'.join(row['provenance'])
        all_rows.append(row)
    write_csv(run_dir/'all_trees.csv',all_rows,
        ['tree_sha256','expression','depth','nodes','fitness','best_train_J','provenance'])

    old_result=exp.read_json(OLD_RUN/'official_training'/'resume_result.json')
    old_selection=exp.read_json(OLD_RUN/'official_training'/'selection_decision.json')
    oldgp=old_result['gp_test']; oldscore=exp.read_json(oldgp['runner_result_path'])['score']
    oldcache=exp.read_json(OLD_RUN/'cache'/'train.json')
    oldtrain=list((OLD_RUN/'rollouts'/'train').glob('*/rollout_summary.json'))
    gp=final['gp_test']; score=exp.read_json(gp['runner_result_path'])['score']
    baseline=state['baseline_reference']['score']
    pop10_best=min(Decimal(m['train_J']) for g in old_result['train_generations']
                   for m in g['members'] if m.get('train_J') is not None)
    pop50_best=min(Decimal(m['train_J']) for g in state['generation_history']
                   for m in g['members'] if m.get('train_J') is not None)
    rows=[
        dict(method='GP population 10',population=10,generations=10,best_train_J=str(pop10_best),
             best_validation_J=old_selection['validation_J'],test_J=oldgp['J'],
             test_distance_km=oldscore['total_distance_km'],
             test_tardiness_seconds=oldscore['total_tardiness_seconds'],
             test_late_orders=oldscore['late_original_orders'],distinct_train_trees=len(oldcache['entries']),
             historical_train_rollout_wall_seconds=sum(exp.read_json(p)['actual_wall_seconds'] for p in oldtrain),
             reused_historical_wall_seconds=None,new_train_rollout_wall_seconds=None,
             test_wall_seconds=oldgp['actual_wall_seconds'],baseline_role='completed reference'),
        dict(method='GP population 50',population=50,generations=10,best_train_J=str(pop50_best),
             best_validation_J=final['selected_validation_J'],test_J=gp['J'],
             test_distance_km=score['total_distance_km'],
             test_tardiness_seconds=score['total_tardiness_seconds'],
             test_late_orders=score['late_original_orders'],
             distinct_train_trees=final['cache_statistics']['distinct_evaluated_trees'],
             historical_train_rollout_wall_seconds=state['historical_rollout_wall_reused_seconds'],
             reused_historical_wall_seconds=state['historical_rollout_wall_reused_seconds'],
             new_train_rollout_wall_seconds=state['actual_new_rollout_wall_seconds'],
             test_wall_seconds=gp['actual_wall_seconds'],baseline_role='new sensitivity run'),
        dict(method='VNSME REUSED_VERIFIED',population=None,generations=None,best_train_J=None,
             best_validation_J=None,test_J=baseline['J'],test_distance_km=baseline['distance_km'],
             test_tardiness_seconds=baseline['tardiness_seconds'],test_late_orders=baseline['late_orders'],
             distinct_train_trees=None,historical_train_rollout_wall_seconds=baseline['actual_wall_seconds'],
             reused_historical_wall_seconds=baseline['actual_wall_seconds'],new_train_rollout_wall_seconds=0,
             test_wall_seconds=0,baseline_role='historical Test; not new-run runtime'),
    ]
    write_csv(run_dir/'population_comparison.csv',rows,list(rows[0]))


def build_final_result(run_dir,state):
    protocol=verify_new_run(run_dir)['protocol']
    selection=exp.read_json(run_dir/'official_training'/'selection_decision.json')
    return dict(
        status='COMPLETED',protocol_sha256=protocol['protocol_sha256'],
        evolution_fingerprint=protocol['evolution_fingerprint'],
        evaluation_fingerprints=protocol['evaluation_fingerprints'],
        instance_id=9,original_orders=100,items=175,vehicles=5,
        population_size=50,generations_completed=10,total_member_positions=500,
        train_rollout_requests=500,
        selection_decision=selection,
        selected_expression=selection['selected_expression'],
        selected_tree_sha256=selection['selected_tree_sha256'],
        selected_train_J=selection['train_J'],selected_validation_J=selection['validation_J'],
        generation_summaries=state['generation_history'],
        validation_candidates=state['validation_records'],
        gp_test=state['gp_test'],
        baseline_reference=state['baseline_reference'],
        baseline_status=state['baseline_reference']['baseline_status'],
        cache_statistics=dict(
            imported_entries=len(exp.read_json(run_dir/'imported_cache_manifest.json')['entries']),
            cross_run_hits=state['cross_run_cache_hits'],
            within_run_hits=state['within_run_cache_hits'],
            new_rollouts=state['new_rollouts'],
            recovered_rollout_artifacts=state['recovered_rollout_artifacts'],
            distinct_evaluated_trees=len(state['fitness_by_tree_hash']),
            historical_rollout_wall_reused_seconds=state['historical_rollout_wall_reused_seconds'],
            actual_new_rollout_wall_seconds=state['actual_new_rollout_wall_seconds']),
        elapsed_wall_seconds=state['elapsed_wall_seconds'],
        completed_at_utc=utc_now())


def write_final_artifacts(run_dir,state,final):
    exp.write_replace(run_dir/'official_training'/'training_result.json',final)
    exp.write_replace(run_dir/'official_training'/'resume_result.json',final)
    write_comparison_outputs(run_dir,state,final)
    (run_dir/'OFFICIAL_RESULTS_REPORT.md').write_text(build_report(run_dir,state,final),
                                                       encoding='utf-8',newline='\n')


def run_main(run_dir, resume=False):
    run_dir=Path(run_dir).resolve()
    checkpoint=run_dir/'official_training'/'resume_checkpoint.json'
    with active_lock(run_dir):
        checked=verify_new_run(run_dir)
        state=exp.read_json(checkpoint)
        if state.get('schema')!=CHECKPOINT_SCHEMA:
            raise ValueError('checkpoint schema mismatch')
        if state.get('protocol_sha256')!=checked['protocol']['protocol_sha256']:
            raise ValueError('checkpoint protocol mismatch')
        if state.get('orchestration_source_sha256')!=sha(__file__):
            raise ValueError('checkpoint source mismatch')
        if state.get('phase')=='COMPLETE':
            return exp.read_json(run_dir/'official_training'/'training_result.json')
        maybe_reconcile_cache(run_dir,state)
        session_start=time.monotonic()
        base_elapsed=float(state.get('elapsed_wall_seconds',0.0))
        while state['phase']=='TRAIN':
            generation=int(state['generation'])
            population_records=list(state['population'])
            population=[exp.load_tree(run_dir/r['tree_path'])[0] for r in population_records]
            rows=list(state['generation_member_rows'])
            member_start=int(state['next_member'])
            gen_start=time.monotonic()
            gen_base=float(state.get('generation_elapsed_seconds',0.0))
            for member in range(member_start,POPULATION_SIZE):
                tree=population[member]
                saved=save_tree_artifact(run_dir,generation,member,tree)
                digest=tree_hash(tree)
                cache=exp._load_cache(run_dir,'train',state['protocol_sha256'])['entries']
                entry=cache.get(digest)
                local_summary=(run_dir/'rollouts'/'train'/digest/'rollout_summary.json')
                origin=cache_origin_for(state,digest,entry,local_summary.is_file())
                started=time.monotonic()
                summary=exp.evaluate_cached(run_dir,'train',tree,
                    f'official_g{generation}_m{member:02d}_train')
                call_wall=time.monotonic()-started
                row=exp._member_record(generation,member,tree,summary)
                row.update(valid=summary.get('valid'),expression=tree.text(),tree_path=saved['tree_path'],
                    cache_origin=origin,evaluation_call_wall_seconds=call_wall,
                    new_rollout_wall_seconds=(summary.get('actual_wall_seconds') or 0)
                        if origin in ('new_rollout','within_run_recovered') else 0.0,
                    historical_rollout_wall_seconds=(summary.get('actual_wall_seconds') or 0)
                        if origin=='cross_run_verified' else 0.0,
                    decision_count=summary.get('decision_count'),
                    feasibility_status=summary.get('feasibility_status'),
                    independent_score_matches_runner=summary.get('independent_score_matches_runner'),
                    completed_orders=summary.get('completed_orders'),completed_items=summary.get('completed_items'),
                    timeout_status=summary.get('timeout_status'),peak_memory_bytes=summary.get('peak_memory_bytes'))
                rows.append(row)
                state['fitness_by_tree_hash'][digest]=dict(status=row['status'],valid=row['valid'],
                    J=row['train_J'],summary_path=str((run_dir/'rollouts'/'train'/digest/'rollout_summary.json').resolve()),
                    cache_origin=origin)
                if origin=='cross_run_verified':
                    used=set(state.get('used_imported_tree_hashes',[]))
                    if digest not in used:
                        used.add(digest); state['used_imported_tree_hashes']=sorted(used)
                        state['cross_run_cache_hits']+=1
                        state['historical_rollout_wall_reused_seconds']+=float(summary.get('actual_wall_seconds') or 0)
                elif origin in ('within_run','within_run_recovered'):
                    state['within_run_cache_hits']+=1
                    if origin=='within_run_recovered': state['recovered_rollout_artifacts']+=1
                else:
                    state['new_rollouts']+=1
                    state['actual_new_rollout_wall_seconds']+=float(summary.get('actual_wall_seconds') or 0)
                ensure_trace_event(run_dir/'official_training'/'training_trace.jsonl',
                    dict(event='TRAIN_MEMBER',**row))
                state['generation_member_rows']=rows
                state['next_member']=member+1
                state['elapsed_wall_seconds']=base_elapsed+(time.monotonic()-session_start)
                state['generation_elapsed_seconds']=gen_base+(time.monotonic()-gen_start)
                state['train_cache_sha256']=sha(run_dir/'cache'/'train.json')
                state['training_trace_sha256']=sha(run_dir/'official_training'/'training_trace.jsonl')
                exp.write_replace(checkpoint,state)
                gen_base=state['generation_elapsed_seconds']
                gen_start=time.monotonic()
                print(f"G{generation} M{member}: {row['status']} J={row['train_J']} source={origin} {generation*50+member+1}/500",flush=True)

            lineage=state['lineage_by_generation'][generation] if generation<len(state['lineage_by_generation']) else []
            gen_elapsed=gen_base+(time.monotonic()-gen_start)
            genrow=generation_statistics(generation,rows,lineage,gen_elapsed)
            genrow['members']=rows
            genrow['protocol_sha256']=state['protocol_sha256']
            generation_path=run_dir/'official_training'/f'g{generation}.json'
            if generation_path.exists():
                prior=exp.read_json(generation_path)
                comparable_prior=dict(prior)
                comparable_current=dict(genrow)
                comparable_prior.pop('generation_elapsed_wall_seconds',None)
                comparable_current.pop('generation_elapsed_wall_seconds',None)
                if comparable_prior!=comparable_current:
                    raise ValueError(f'conflicting generation artifact: {generation_path}')
                genrow=prior
            else:
                exp.write_new(generation_path,genrow)
            if not any(x.get('generation')==generation for x in state['generation_history']):
                state['generation_history'].append(genrow)
            state['generation_history'].sort(key=lambda x:x['generation'])
            ensure_trace_event(run_dir/'official_training'/'training_trace.jsonl',
                dict(event='GENERATION_COMPLETE',generation=generation,valid_count=genrow['valid_count'],
                     best_J=genrow['best_J'],distinct_genotype_count=genrow['distinct_genotype_count']))
            if genrow['valid_count']==0:
                state['phase']='FAILED'; state['failure']=f'no valid parent in G{generation}'
                exp.write_replace(checkpoint,state)
                raise RuntimeError(state['failure'])
            if generation==GENERATIONS-1:
                state['phase']='VALIDATION'; state['validation_index']=0; state['validation_records']=[]
                state['generation_elapsed_seconds']=gen_elapsed
                state['elapsed_wall_seconds']=base_elapsed+(time.monotonic()-session_start)
                exp.write_replace(checkpoint,state)
                print(f"G{generation}: valid={genrow['valid_count']}/50",flush=True)
                break
            evaluated=[(Decimal(r['train_J']),exp.load_tree(run_dir/r['tree_path'])[0])
                for r in rows if r.get('status')=='COMPLETED' and r.get('valid') is True and r.get('train_J') is not None]
            rng=random.Random(); rng.setstate(tupleize(state['gp_random_state']))
            nextpop,lineage_next=verify_breed_trace(rng,evaluated)
            gnext=generation+1
            next_records=[save_tree_artifact(run_dir,gnext,i,t) for i,t in enumerate(nextpop)]
            transition=dict(generation_from=generation,generation_to=gnext,population_size=50,
                elitism=1,tournament_size=3,crossover_probability=.8,mutation_probability=.3,
                rng_state_before_sha256=digest_json(state['gp_random_state']),
                rng_state_after=rng.getstate(),lineage_events=lineage_next,
                next_population=next_records)
            write_if_same(run_dir/'official_training'/f'breeding_g{generation}_to_g{gnext}.json',transition)
            state['lineage_by_generation'].append(lineage_next)
            state['populations'].append(next_records)
            state['population']=next_records
            state['generation']=gnext; state['next_member']=0; state['generation_member_rows']=[]
            state['gp_random_state']=rng.getstate(); state['generation_elapsed_seconds']=0.0
            ensure_trace_event(run_dir/'official_training'/'training_trace.jsonl',
                dict(event='BREED',generation=generation,next_generation=gnext,
                     offspring_tree_hashes=[x['tree_sha256'] for x in next_records]))
            state['elapsed_wall_seconds']=base_elapsed+(time.monotonic()-session_start)
            state['train_cache_sha256']=sha(run_dir/'cache'/'train.json')
            state['training_trace_sha256']=sha(run_dir/'official_training'/'training_trace.jsonl')
            exp.write_replace(checkpoint,state)
            print(f"G{generation}: valid={genrow['valid_count']}/50; bred G{gnext}",flush=True)

        if state['phase']=='VALIDATION':
            self_validate_and_select(run_dir,state,checkpoint,session_start,base_elapsed)
            state=exp.read_json(checkpoint)
        if state['phase']=='GP_TEST':
            tree=exp.load_tree(run_dir/'trees'/'selected_official_tree.json')[0]
            summary_path=run_dir/'rollouts'/'test'/tree_hash(tree)/'rollout_summary.json'
            if summary_path.is_file():
                summary=exp.read_json(summary_path)
                if (summary.get('protocol_sha256')!=state['protocol_sha256']
                        or summary.get('tree_sha256')!=tree_hash(tree)
                        or summary.get('partition')!='test' or summary.get('policy')!='gp'):
                    raise ValueError('existing GP Test artifact provenance mismatch')
            else:
                summary=exp.run_rollout(run_dir,policy='gp',partition='test',tree=tree,
                                        run_id='official_selected_gp_test')
            state['gp_test']=summary
            state['phase']='COMPLETE' if summary.get('status')=='COMPLETED' and summary.get('J') is not None else 'FAILED'
            if state['phase']=='FAILED': state['failure']='GP Test incomplete or invalid'
            ensure_trace_event(run_dir/'official_training'/'training_trace.jsonl',
                dict(event='GP_TEST',status=summary['status'],J=summary.get('J'),
                     tree_sha256=tree_hash(tree)))
            state['elapsed_wall_seconds']=base_elapsed+(time.monotonic()-session_start)
            state['training_trace_sha256']=sha(run_dir/'official_training'/'training_trace.jsonl')
            exp.write_replace(checkpoint,state)
            if state['phase']=='FAILED':
                raise RuntimeError('GP Test incomplete; J remains null')
        if state['phase']=='COMPLETE':
            final=build_final_result(run_dir,state)
            write_final_artifacts(run_dir,state,final)
            state['final_result_path']=str((run_dir/'official_training'/'training_result.json').resolve())
            exp.write_replace(checkpoint,state)
            print('Population-50 run COMPLETED.',flush=True)
            return final
        return state


def self_validate_and_select(run_dir,state,checkpoint,session_start,base_elapsed):
    run_dir=Path(run_dir); prot=verify_new_run(run_dir)['protocol']
    actual={}
    for pop in state['populations']:
        for rec in pop:
            tree=exp.load_tree(run_dir/rec['tree_path'])[0]; digest=rec['tree_sha256']
            fitness=state['fitness_by_tree_hash'].get(digest)
            if fitness and fitness.get('status')=='COMPLETED' and fitness.get('valid') is True and fitness.get('J') is not None:
                item=actual.setdefault(digest,dict(tree=tree,J=fitness['J'],nodes=validate_tree(tree,LIMITS)[0],provenance=[]))
                item['provenance'].append(dict(generation=rec['generation'],member=rec['member']))
    candidates=sorted(actual.values(),key=lambda x:(Decimal(x['J']),x['nodes'],exp.canonical(x['tree'])))[:5]
    if not candidates: raise RuntimeError('no valid current-population tree for Validation')
    manifest=[dict(rank=i+1,tree_sha256=tree_hash(x['tree']),expression=x['tree'].text(),
                   train_J=x['J'],nodes=x['nodes'],population_provenance=x['provenance'])
              for i,x in enumerate(candidates)]
    write_if_same(run_dir/'official_training'/'validation_candidates.json',
        dict(protocol_sha256=prot['protocol_sha256'],
             selection_basis='only observed G0-G9 trees; distinct canonical hash; sorted by raw Train J',
             candidates=manifest))
    records=list(state.get('validation_records',[]))
    for index in range(int(state.get('validation_index',0)),len(candidates)):
        item=candidates[index]; tree=item['tree']; digest=tree_hash(tree)
        tree_record(run_dir,10,index,tree,create=True)
        summary=exp.run_rollout(run_dir,policy='gp',partition='validation',tree=tree,
                                run_id=f'official_validation_{index+1:02d}')
        runner=exp.read_json(summary['runner_result_path']) if summary.get('runner_result_path') else {}
        score=runner.get('score') or {}
        record=dict(rank=index+1,tree_sha256=digest,expression=tree.text(),train_J=item['J'],
            validation_J=summary.get('J'),status=summary.get('status'),valid=summary.get('valid'),
            feasibility_status=summary.get('feasibility_status'),
            independent_score_matches_runner=summary.get('independent_score_matches_runner'),
            actual_wall_seconds=summary.get('actual_wall_seconds'),decision_count=summary.get('decision_count'),
            distance_km=score.get('total_distance_km'),tardiness_seconds=score.get('total_tardiness_seconds'),
            late_original_orders=score.get('late_original_orders'),population_provenance=item['provenance'],
            summary_path=str((run_dir/'rollouts'/'validation'/digest/'rollout_summary.json').resolve()),
            nodes=item['nodes'])
        records.append(record); state['validation_records']=records; state['validation_index']=index+1
        state['elapsed_wall_seconds']=base_elapsed+(time.monotonic()-session_start)
        ensure_trace_event(run_dir/'official_training'/'training_trace.jsonl',
            dict(event='VALIDATION',member=index,status=record['status'],J=record['validation_J'],tree_sha256=digest))
        state['training_trace_sha256']=sha(run_dir/'official_training'/'training_trace.jsonl')
        exp.write_replace(checkpoint,state)
        print(f"Validation {index+1}/5: {record['status']} J={record['validation_J']}",flush=True)
        if record['status']!='COMPLETED' or record.get('valid') is not True or record['validation_J'] is None:
            state['phase']='FAILED'; state['failure']=f'Validation candidate {index+1} invalid'
            exp.write_replace(checkpoint,state)
            raise RuntimeError(state['failure'])
    selected=min(records,key=lambda x:(Decimal(x['validation_J']),Decimal(x['train_J']),
        x['nodes'],exp.canonical(exp.load_tree(run_dir/next(rec['tree_path']
            for pop in state['populations'] for rec in pop
            if rec['tree_sha256']==x['tree_sha256']))[0])))
    selected_tree=exp.load_tree(run_dir/next(rec['tree_path'] for pop in state['populations']
        for rec in pop if rec['tree_sha256']==selected['tree_sha256']))[0]
    decision=dict(protocol_sha256=prot['protocol_sha256'],selection_timestamp_utc=utc_now(),
        selected_expression=selected_tree.text(),selected_tree_sha256=tree_hash(selected_tree),
        train_J=selected['train_J'],validation_J=selected['validation_J'],
        tie_break_reason='minimum Validation J; then Train J, node count, canonical representation',
        candidates=[dict(rank=r['rank'],tree_sha256=r['tree_sha256'],expression=r['expression'],
            train_J=r['train_J'],validation_J=r['validation_J'],nodes=r['nodes'],
            population_provenance=r['population_provenance']) for r in records])
    decision_path=run_dir/'official_training'/'selection_decision.json'
    if decision_path.exists():
        previous=exp.read_json(decision_path)
        comparable_previous=dict(previous); comparable_previous.pop('selection_timestamp_utc',None)
        comparable_decision=dict(decision); comparable_decision.pop('selection_timestamp_utc',None)
        if comparable_previous!=comparable_decision:
            raise ValueError('existing selection decision conflicts with resumed result')
        decision=previous
    else:
        exp.write_new(decision_path,decision)
    selected_path=run_dir/'trees'/'selected_official_tree.json'
    if selected_path.exists():
        prior_tree,_=exp.load_tree(selected_path)
        if tree_hash(prior_tree)!=tree_hash(selected_tree):
            raise ValueError('existing selected tree conflicts with selection decision')
    else:
        exp.save_tree(selected_path,selected_tree,
            training=dict(protocol_sha256=prot['protocol_sha256'],train_J=selected['train_J'],
                          validation_J=selected['validation_J'],selection=decision['tie_break_reason']),
            limits=LIMITS)
    state['selected_tree_sha256']=tree_hash(selected_tree); state['phase']='GP_TEST'
    state['elapsed_wall_seconds']=base_elapsed+(time.monotonic()-session_start)
    exp.write_replace(checkpoint,state)
    print(f"Selected {state['selected_tree_sha256']} Train J={selected['train_J']} Validation J={selected['validation_J']}",flush=True)


def build_final_result(run_dir,state):
    protocol=verify_new_run(run_dir)['protocol']
    selection=exp.read_json(run_dir/'official_training'/'selection_decision.json')
    return dict(status='COMPLETED',protocol_sha256=protocol['protocol_sha256'],
        evolution_fingerprint=protocol['evolution_fingerprint'],
        evaluation_fingerprints=protocol['evaluation_fingerprints'],
        instance_id=9,original_orders=100,items=175,vehicles=5,population_size=50,
        generations_completed=10,total_member_positions=500,train_rollout_requests=500,
        generation_summaries=state['generation_history'],validation_candidates=state['validation_records'],
        selection_decision=selection,selected_expression=selection['selected_expression'],
        selected_tree_sha256=selection['selected_tree_sha256'],selected_train_J=selection['train_J'],
        selected_validation_J=selection['validation_J'],gp_test=state['gp_test'],
        baseline_status=state['baseline_reference']['baseline_status'],
        baseline_reference=state['baseline_reference'],
        cache_statistics=dict(imported_entries=len(exp.read_json(run_dir/'imported_cache_manifest.json')['entries']),
            cross_run_hits=state['cross_run_cache_hits'],within_run_hits=state['within_run_cache_hits'],
            new_rollouts=state['new_rollouts'],recovered_rollout_artifacts=state['recovered_rollout_artifacts'],
            distinct_evaluated_trees=len(state['fitness_by_tree_hash']),
            historical_rollout_wall_reused_seconds=state['historical_rollout_wall_reused_seconds'],
            actual_new_rollout_wall_seconds=state['actual_new_rollout_wall_seconds']),
        elapsed_wall_seconds=state['elapsed_wall_seconds'],completed_at_utc=utc_now())


def initial_checkpoint(run_dir):
    checked=verify_new_run(run_dir)
    g0=checked['g0']; protocol=checked['protocol']
    if (Path(run_dir)/'official_training'/'resume_checkpoint.json').exists():
        raise FileExistsError('preserving existing checkpoint')
    records=[tree_record(run_dir,0,i,exp.load_tree(Path(run_dir)/'trees'/f'g0_m{i:02d}.json')[0],create=False)
             for i in range(POPULATION_SIZE)]
    state=dict(schema=CHECKPOINT_SCHEMA,run_directory=str(Path(run_dir).resolve()),
        protocol_sha256=protocol['protocol_sha256'],orchestration_source_sha256=sha(__file__),
        phase='TRAIN',generation=0,next_member=0,population=records,populations=[records],
        generation_member_rows=[],generation_history=[],lineage_by_generation=[],
        fitness_by_tree_hash={},imported_tree_hashes=[x['tree_sha256'] for x in exp.read_json(Path(run_dir)/'imported_cache_manifest.json')['entries']],
        used_imported_tree_hashes=[],cross_run_cache_hits=0,within_run_cache_hits=0,
        new_rollouts=0,recovered_rollout_artifacts=0,historical_rollout_wall_reused_seconds=0.0,
        actual_new_rollout_wall_seconds=0.0,elapsed_wall_seconds=0.0,generation_elapsed_seconds=0.0,
        training_started_at_utc=utc_now(),gp_random_state=g0['gp_random_state'],
        validation_index=0,validation_records=[],gp_test=None,selected_tree_sha256=None,
        baseline_reference=exp.read_json(Path(run_dir)/'baseline_reference.json'),
        train_cache_path=str((Path(run_dir)/'cache'/'train.json').resolve()),
        train_cache_sha256=sha(Path(run_dir)/'cache'/'train.json'),
        training_trace_path=str((Path(run_dir)/'official_training'/'training_trace.jsonl').resolve()),
        training_trace_sha256=sha(Path(run_dir)/'official_training'/'training_trace.jsonl'))
    exp.write_new(Path(run_dir)/'official_training'/'resume_checkpoint.json',state)
    return state


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('action',choices=('prepare','train','resume'))
    parser.add_argument('--run-dir',default=None)
    parser.add_argument('--old-run',default=str(OLD_RUN))
    args=parser.parse_args()
    if args.action=='prepare':
        result=prepare_run(args.run_dir,args.old_run)
        initial_checkpoint(result['run_directory'])
        print(json.dumps(result,ensure_ascii=False,indent=2))
    else:
        if not args.run_dir:
            parser.error('--run-dir is required for train/resume')
        run_dir=Path(args.run_dir).resolve()
        if args.action=='train':
            initial_checkpoint(run_dir)
            run_main(run_dir,resume=False)
        else:
            run_main(run_dir,resume=True)


if __name__=='__main__':
    main()

