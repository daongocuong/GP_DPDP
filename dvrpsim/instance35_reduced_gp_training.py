"""Small, isolated GP train/validation/test run for one prepared instance-35 scope."""
import argparse
from decimal import Decimal
from datetime import datetime, timezone
import json
from pathlib import Path
import random
import time

from dpdp_gp import (Limits, breed, canonical, initial_population, load_tree,
                     save_tree, tree_hash, validate_tree)
from instance35_reduced_experiment import EXPERIMENT, SIMULATOR_SEED, run_rollout, sha


def append_event(path, event):
    with Path(path).open('a', encoding='utf-8', newline='\n') as handle:
        handle.write(json.dumps(event, sort_keys=True, default=str, allow_nan=False)+'\n')
        handle.flush()
        import os
        os.fsync(handle.fileno())


def validation_rank_key(entry):
    tree = entry['tree']
    return (Decimal(entry['validation_J']), Decimal(entry['training_J']),
            validate_tree(tree, Limits())[0], canonical(tree))


def result_complete(record):
    return (record.get('status') == 'COMPLETED' and record.get('valid') is True
            and record.get('J') is not None and record.get('partial') is False
            and record.get('valid_supervision') is True
            and record.get('supervisor_state') == 'EXITED'
            and record.get('supervisor_exit_code') == 0
            and record.get('remaining_job_processes') == [])


def require_rollout_budget(deadline_epoch, maximum_rollout_seconds):
    remaining = float(deadline_epoch) - time.time()
    if remaining < maximum_rollout_seconds:
        raise RuntimeError(f'task wall budget reserve is {remaining:.1f}s; '
                           f'need {maximum_rollout_seconds}s before starting another rollout')
    return remaining


def _load_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def run_training(experiment_dir=EXPERIMENT,
                 run_id='mini_gp_train_20261118_01',
                 evolution_seed=20261118,
                 task_deadline_epoch=None):
    experiment_dir = Path(experiment_dir).resolve()
    config = _load_json(experiment_dir/'experiment_config.json')
    training_dir = experiment_dir/'training'/run_id
    training_dir.mkdir(parents=True, exist_ok=False)
    (training_dir/'trees').mkdir()
    trace_path = training_dir/'training_trace.jsonl'
    trace_path.open('x', encoding='utf-8').close()
    started = time.monotonic()

    gp_config = dict(schema='instance35-reduced-mini-gp-training-v1',
        scope_label=config['scope_label'], experiment_config_sha256=config['config_sha256'],
        run_id=run_id, population_size=2, generations=1, tournament=2,
        crossover_rate=0.8, mutation_rate=0.3, elitism=1,
        evolution_seed=evolution_seed, simulator_seed=SIMULATOR_SEED,
        train_partition_sha256=config['partitions']['train']['orders_sha256'],
        validation_partition_sha256=config['partitions']['validation']['orders_sha256'],
        test_partition_sha256=config['partitions']['test']['orders_sha256'],
        max_stage_wall_seconds=config['execution']['supervisor_wall_seconds'],
        max_decision_seconds=config['execution']['decision_hard_timeout_seconds'],
        task_deadline_utc=(datetime.fromtimestamp(task_deadline_epoch, timezone.utc).isoformat()
                           if task_deadline_epoch is not None else None),
        reused_train_run_id='reduced35_gp_train_fixed_20261118_01',
        selection='generation-1 candidates ranked by validation J ascending; ties by train J, node count, canonical tree',
        test_protocol='evaluate selected GP tree and VNSME independently on the same test partition; no partial J')
    gp_config['source_sha256'] = {name: sha(Path(__file__).resolve().parent/name) for name in (
        'instance35_reduced_gp_training.py', 'instance35_reduced_experiment.py',
        'dpdp_gp.py', 'run_dpdp_insertion.py', 'dpdp_insertion.py',
        'dpdp_feasibility.py', 'dpdp_v3_supervisor.py')}
    with (training_dir/'training_config.json').open('x', encoding='utf-8') as handle:
        json.dump(gp_config, handle, indent=2, sort_keys=True, default=str)
        handle.write('\n')

    fixed_tree, _ = load_tree(experiment_dir/'trees'/'fixed_gp_tree.json')
    rng = random.Random(evolution_seed)
    generation0 = initial_population(rng, gp_config['population_size'])
    if tree_hash(generation0[0]) != tree_hash(fixed_tree):
        raise ValueError('GP generation-zero seed no longer matches the fixed operational tree')
    train_results = {}
    train_artifacts = {}
    fixed_path = experiment_dir/'runs/gp/train/reduced35_gp_train_fixed_20261118_01'
    fixed_record = _load_json(fixed_path/'stage_result.json')
    fixed_run_config = _load_json(fixed_path/'run_config.json')
    if (not result_complete(fixed_record)
            or fixed_run_config.get('dataset_sha256') != config['partitions']['train']['orders_sha256']
            or fixed_run_config.get('tree_sha256') != sha(experiment_dir/'trees'/'fixed_gp_tree.json')
            or fixed_run_config.get('simulator_seed') != SIMULATOR_SEED):
        raise ValueError('fixed GP Train artifact is not reusable for this training protocol')
    train_results[tree_hash(generation0[0])] = fixed_record
    train_artifacts[tree_hash(generation0[0])] = str(fixed_path)

    def tree_file(generation, member, tree):
        path = training_dir/'trees'/f'generation_{generation}_member_{member}.json'
        save_tree(path, tree, training=dict(run_id=run_id, generation=generation,
            member=member, evolution_seed=evolution_seed, scope=config['scope_label']))
        return path

    def evaluate_train(generation, member, tree, path):
        digest = tree_hash(tree)
        if digest in train_results:
            append_event(trace_path, dict(event='TRAIN_TREE_REUSED', generation=generation,
                member=member, tree_sha256=digest, source_run=train_artifacts[digest],
                J=train_results[digest]['J'], completed_decisions=train_results[digest]['completed_decisions']))
            return train_results[digest]
        if task_deadline_epoch is not None:
            require_rollout_budget(task_deadline_epoch, config['execution']['supervisor_wall_seconds'])
        record = run_rollout(f'{run_id}_g{generation}_m{member}_train', 'gp', 'train',
                             tree_path=path, experiment_dir=experiment_dir)
        append_event(trace_path, dict(event='TRAIN_EVALUATED', generation=generation,
            member=member, tree_sha256=digest, J=record.get('J'), status=record.get('status'),
            wall_seconds=record.get('wall_seconds'), completed_decisions=record.get('completed_decisions'),
            artifact=record.get('runner_result_path')))
        if not result_complete(record):
            raise RuntimeError(f'GP training rollout incomplete at generation {generation}, member {member}; no retry')
        train_results[digest] = record
        train_artifacts[digest] = str(experiment_dir/'runs/gp/train'/f'{run_id}_g{generation}_m{member}_train')
        return record

    evaluated0 = []
    for member, tree in enumerate(generation0):
        path = tree_file(0, member, tree)
        outcome = evaluate_train(0, member, tree, path)
        evaluated0.append((Decimal(outcome['J']), tree))
    with (training_dir/'generation_0.json').open('x', encoding='utf-8') as handle:
        json.dump([dict(member=i, expression=tree.text(), tree_sha256=tree_hash(tree),
                        training_J=str(fitness), run_id=train_artifacts[tree_hash(tree)])
                   for i, (fitness, tree) in enumerate(evaluated0)], handle, indent=2)

    generation1 = breed(rng, evaluated0, gp_config['population_size'],
        gp_config['tournament'], gp_config['crossover_rate'], gp_config['mutation_rate'],
        gp_config['elitism'], Limits())
    final_candidates = []
    for member, tree in enumerate(generation1):
        path = tree_file(1, member, tree)
        train_record = evaluate_train(1, member, tree, path)
        final_candidates.append(dict(member=member, tree=tree, training_J=train_record['J'],
                                     training_run=train_artifacts[tree_hash(tree)], tree_path=path))
    with (training_dir/'generation_1.json').open('x', encoding='utf-8') as handle:
        json.dump([dict(member=c['member'], expression=c['tree'].text(),
                        tree_sha256=tree_hash(c['tree']), training_J=c['training_J'],
                        train_run=c['training_run']) for c in final_candidates], handle, indent=2)

    validated = []
    validation_cache = {}
    for candidate in final_candidates:
        digest = tree_hash(candidate['tree'])
        if digest not in validation_cache:
            if task_deadline_epoch is not None:
                require_rollout_budget(task_deadline_epoch, config['execution']['supervisor_wall_seconds'])
            record = run_rollout(f'{run_id}_g1_m{candidate["member"]}_validation',
                'gp', 'validation', tree_path=candidate['tree_path'], experiment_dir=experiment_dir)
            append_event(trace_path, dict(event='VALIDATION_EVALUATED', member=candidate['member'],
                tree_sha256=digest, J=record.get('J'), status=record.get('status'),
                wall_seconds=record.get('wall_seconds'), artifact=record.get('runner_result_path')))
            if not result_complete(record):
                raise RuntimeError('Validation rollout incomplete; no J selection and no retry')
            validation_cache[digest] = record
        validated.append({**candidate, 'validation_J': validation_cache[digest]['J'],
                          'validation_run': validation_cache[digest]['run_id']})
    selected = min(validated, key=validation_rank_key)
    selected_path = training_dir/'selected_tree.json'
    save_tree(selected_path, selected['tree'], training=dict(run_id=run_id,
        selection='lowest valid generation-1 Validation J', validation_J=selected['validation_J'],
        training_J=selected['training_J'], validation_run=selected['validation_run'],
        tree_sha256=tree_hash(selected['tree']), evolution_seed=evolution_seed))
    append_event(trace_path, dict(event='TREE_SELECTED', member=selected['member'],
        expression=selected['tree'].text(), tree_sha256=tree_hash(selected['tree']),
        validation_J=selected['validation_J'], training_J=selected['training_J']))

    if task_deadline_epoch is not None:
        require_rollout_budget(task_deadline_epoch, config['execution']['supervisor_wall_seconds'])
    gp_test = run_rollout(f'{run_id}_selected_gp_test', 'gp', 'test',
        tree_path=selected_path, experiment_dir=experiment_dir)
    append_event(trace_path, dict(event='TEST_EVALUATED', algorithm='gp', J=gp_test.get('J'),
        status=gp_test.get('status'), wall_seconds=gp_test.get('wall_seconds'),
        artifact=gp_test.get('runner_result_path')))
    if not result_complete(gp_test):
        raise RuntimeError('Selected GP Test incomplete; no retry')
    if task_deadline_epoch is not None:
        require_rollout_budget(task_deadline_epoch, config['execution']['supervisor_wall_seconds'])
    vnsme_test = run_rollout(f'{run_id}_vnsme_test', 'vnsme', 'test', experiment_dir=experiment_dir)
    append_event(trace_path, dict(event='TEST_EVALUATED', algorithm='vnsme', J=vnsme_test.get('J'),
        status=vnsme_test.get('status'), wall_seconds=vnsme_test.get('wall_seconds'),
        artifact=vnsme_test.get('runner_result_path')))
    if not result_complete(vnsme_test):
        raise RuntimeError('VNSME Test incomplete; no retry')

    result = dict(status='COMPLETED', scope=config['scope_label'], run_id=run_id,
        population_size=gp_config['population_size'], generations=gp_config['generations'],
        generation_0=[dict(tree_sha256=tree_hash(t), expression=t.text(), J=str(j)) for j,t in evaluated0],
        generation_1=[dict(tree_sha256=tree_hash(c['tree']), expression=c['tree'].text(),
                            train_J=c['training_J'], validation_J=c['validation_J'],
                            train_run=c['training_run'], validation_run=c['validation_run'])
                       for c in validated],
        selected_tree=dict(path=str(selected_path), tree_sha256=tree_hash(selected['tree']),
            expression=selected['tree'].text(), generation=1, member=selected['member'],
            selection_metric='validation J', validation_J=selected['validation_J'],
            training_J=selected['training_J']),
        test=dict(gp=dict(run_id=gp_test['run_id'], J=gp_test['J'],
                          artifact=gp_test['runner_result_path']),
                  vnsme=dict(run_id=vnsme_test['run_id'], J=vnsme_test['J'],
                             artifact=vnsme_test['runner_result_path'])),
        wall_seconds=time.monotonic()-started,
        internal_budget_note='VNSME Train/Test uses a 50s cooperative internal search budget; no equal-compute claim versus GP.')
    with (training_dir/'training_result.json').open('x', encoding='utf-8') as handle:
        json.dump(result, handle, indent=2, sort_keys=True, default=str)
        handle.write('\n')
    append_event(trace_path, dict(event='TRAINING_COMPLETED', wall_seconds=result['wall_seconds']))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--experiment-dir', type=Path, default=EXPERIMENT)
    parser.add_argument('--run-id', default='mini_gp_train_20261118_01')
    parser.add_argument('--evolution-seed', type=int, default=20261118)
    parser.add_argument('--task-deadline-utc', required=True,
                        help='absolute UTC deadline; no rollout starts unless a full stage timeout remains')
    args = parser.parse_args()
    deadline = datetime.fromisoformat(args.task_deadline_utc.replace('Z', '+00:00'))
    requested_training_dir = args.experiment_dir.resolve()/'training'/args.run_id
    if requested_training_dir.exists():
        parser.error(f'preserving existing training artifact: {requested_training_dir}')
    try:
        result = run_training(args.experiment_dir, args.run_id, args.evolution_seed,
                              deadline.timestamp())
    except BaseException as exc:
        training_dir = args.experiment_dir.resolve()/'training'/args.run_id
        error = f'{type(exc).__name__}: {exc}'
        trace = training_dir/'training_trace.jsonl'
        if trace.exists():
            append_event(trace, dict(event='TRAINING_INCOMPLETE', status='INCOMPLETE',
                                     J=None, error=error))
        result = dict(status='INCOMPLETE', run_id=args.run_id, J=None, error=error,
                      training_trace=str(trace), training_directory=str(training_dir))
        result_path = training_dir/'training_result.json'
        if training_dir.is_dir() and not result_path.exists():
            with result_path.open('x', encoding='utf-8') as handle:
                json.dump(result, handle, indent=2)
                handle.write('\n')
        print(json.dumps(result, indent=2))
        raise SystemExit(2)
    print(json.dumps(result, indent=2, default=str))


if __name__ == '__main__':
    main()
