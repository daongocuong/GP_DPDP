"""Checkpoint and exact-resume driver for the locked 100-order GP run.

This helper keeps the locked protocol and pinned trainer sources unchanged.
It checkpoints evolutionary state after each completed rollout and persists every
offspring tree before asking the pinned rollout driver to evaluate it.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import random
import shutil
import sys
from decimal import Decimal

import gp_dpdp_100_feasibility as exp


def file_sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save_checkpoint(path, value):
    exp.write_replace(path, value)


def tupleize(value):
    return tuple(tupleize(item) for item in value) if isinstance(value, list) else value


def tree_record(run_dir, generation, member, tree, *, create=True):
    digest = exp.tree_hash(tree)
    existing = exp._tree_artifact_path(run_dir, tree)
    if existing is None and create:
        target = Path(run_dir)/'trees'/f'evolved_g{generation:02d}_m{member:02d}_{digest[:12]}.json'
        if target.exists():
            prior, _ = exp.load_tree(target)
            if exp.tree_hash(prior) != digest:
                raise ValueError(f'tree path collision: {target}')
        else:
            exp.save_tree(target, tree, training=dict(
                generation=generation, member=member,
                protocol_sha256=exp.read_json(Path(run_dir)/'protocol.json')['protocol_sha256'],
                origin='deterministic GP breeding'), limits=exp.LIMITS)
        existing = target
    if existing is None:
        raise ValueError(f'no saved tree artifact for {digest}')
    nodes, depth = exp.validate_tree(tree, exp.LIMITS)
    return dict(member=member, tree_sha256=digest, expression=tree.text(),
                depth=depth, nodes=nodes, tree_path=str(Path(existing).resolve()))


def initial_checkpoint(run_dir, checkpoint_path):
    run_dir = Path(run_dir).resolve()
    config, _, g0_manifest, protocol = exp.verify_locked_run(run_dir)
    training_dir = run_dir/'official_training'
    trace_path = training_dir/'training_trace.jsonl'
    cache_path = run_dir/'cache'/'train.json'
    if not trace_path.is_file() or not cache_path.is_file():
        raise ValueError('cannot checkpoint without the saved training trace and Train cache')
    if exp.read_json(training_dir/'training_result.json').get('status') != 'INCOMPLETE':
        raise ValueError('expected the preserved incomplete official attempt')
    cache = exp._load_cache(run_dir, 'train', protocol['protocol_sha256'])
    rng, generated_g0, _ = exp.initial_population()
    g0 = [exp.load_tree(run_dir/'trees'/f'g0_m{i:02d}.json')[0] for i in range(10)]
    if [exp.tree_hash(tree) for tree in generated_g0] != [exp.tree_hash(tree) for tree in g0]:
        raise ValueError('reinitialized G0 differs from locked population')
    evaluated = []
    fitness = {}
    for member, tree in enumerate(g0):
        digest = exp.tree_hash(tree)
        entry = cache['entries'].get(digest)
        if not entry or entry.get('status') != 'COMPLETED' or entry.get('J') is None:
            raise ValueError(f'G0 member {member} lacks a completed cached Train score')
        summary_path = Path(entry['summary_path'])
        summary = exp.read_json(summary_path)
        if summary.get('protocol_sha256') != protocol['protocol_sha256']:
            raise ValueError(f'G0 member {member} cache protocol mismatch')
        evaluated.append((Decimal(entry['J']), tree))
        fitness[digest] = dict(status=entry['status'], J=entry['J'],
                               summary_path=str(summary_path.resolve()))
    g1 = exp.breed(rng, evaluated, 10, tournament=3,
                   crossover_rate=.8, mutation_rate=.3, elitism=1,
                   limits=exp.LIMITS)
    for member, tree in enumerate(g1):
        rec = tree_record(run_dir, 1, member, tree)
        rec['generation'] = 1
        rec['member'] = member
        rec['tree_path'] = str(Path(rec['tree_path']).relative_to(run_dir))
    trace_rows = []
    for line in trace_path.read_text(encoding='utf-8').splitlines():
        if line.strip():
            trace_rows.append(json.loads(line))
    g1_member0 = next((row for row in trace_rows
                       if row.get('generation') == 1 and row.get('member') == 0), None)
    if not g1_member0 or g1_member0.get('tree_sha256') != exp.tree_hash(g1[0]):
        raise ValueError('saved G1/member0 trace does not match deterministic G1')
    if g1_member0.get('status') != 'COMPLETED' or g1_member0.get('train_J') is None:
        raise ValueError('G1/member0 has no completed cached Train score')
    fitness[exp.tree_hash(g1[0])] = dict(status='COMPLETED', J=g1_member0['train_J'],
        summary_path=cache['entries'][exp.tree_hash(g1[0])]['summary_path'])
    g0_artifact = exp.read_json(training_dir/'g0.json')
    populations = [
        [dict(member=i, tree_sha256=exp.tree_hash(tree),
              tree_path=f'trees/g0_m{i:02d}.json', expression=tree.text(),
              nodes=exp.validate_tree(tree, exp.LIMITS)[0],
              depth=exp.validate_tree(tree, exp.LIMITS)[1]) for i, tree in enumerate(g0)],
        [tree_record(run_dir, 1, i, tree, create=False) for i, tree in enumerate(g1)]
    ]
    # Copy immutable pause snapshots before any later cache/trace append.
    snapshot_dir = training_dir/'pause_snapshot'
    snapshot_dir.mkdir(exist_ok=True)
    for source, name in ((cache_path, 'train_cache.json'),
                         (trace_path, 'training_trace.jsonl'),
                         (training_dir/'g0.json', 'g0.json'),
                         (training_dir/'training_result.json', 'failed_attempt_result.json')):
        target = snapshot_dir/name
        if not target.exists():
            shutil.copy2(source, target)
    state = dict(
        schema='dpdp-gp-100-resume-checkpoint-v1',
        run_directory=str(run_dir),
        protocol_sha256=protocol['protocol_sha256'],
        resume_driver_sha256=file_sha(__file__),
        phase='TRAIN',
        generation=1,
        next_member=1,
        population=populations[1],
        populations=populations,
        generation_history=[g0_artifact],
        generation_member_rows=[dict(g1_member0)],
        fitness_by_tree_hash=fitness,
        train_cache_path=str(cache_path.resolve()),
        train_cache_sha256=file_sha(cache_path),
        training_trace_path=str(trace_path.resolve()),
        training_trace_sha256=file_sha(trace_path),
        gp_random_state=rng.getstate(),
        validation_index=0,
        validation_records=[],
        test_step='',
    )
    save_checkpoint(checkpoint_path, state)
    print('Checkpoint saved: generation=G1, next_member=1; no rollout launched.', flush=True)


def ensure_trace_event(trace_path, event):
    key = (event.get('event'), event.get('generation'), event.get('member'))
    if trace_path.exists():
        for line in trace_path.read_text(encoding='utf-8').splitlines():
            if not line.strip():
                continue
            prior = json.loads(line)
            if (prior.get('event'), prior.get('generation'), prior.get('member')) == key:
                if prior.get('tree_sha256') != event.get('tree_sha256'):
                    raise ValueError(f'trace conflict at G{key[1]} member {key[2]}')
                return
    with trace_path.open('a', encoding='utf-8', newline='\n') as handle:
        handle.write(json.dumps(event, sort_keys=True, allow_nan=False)+'\n')
        handle.flush()
        os.fsync(handle.fileno())


def write_if_same(path, value):
    path = Path(path)
    if path.exists():
        prior = exp.read_json(path)
        if prior != value:
            raise ValueError(f'preserving conflicting existing artifact: {path}')
    else:
        exp.write_new(path, value)


def persist_checkpoint(path, state):
    cache_path = Path(state['train_cache_path'])
    state['train_cache_sha256'] = file_sha(cache_path)
    state['training_trace_sha256'] = file_sha(state['training_trace_path'])
    save_checkpoint(path, state)


def run_resume(run_dir, checkpoint_path):
    run_dir = Path(run_dir).resolve()
    checkpoint_path = Path(checkpoint_path).resolve()
    config, _, _, protocol = exp.verify_locked_run(run_dir)
    state = exp.read_json(checkpoint_path)
    if state.get('schema') != 'dpdp-gp-100-resume-checkpoint-v1':
        raise ValueError('unsupported resume checkpoint schema')
    if state.get('run_directory') != str(run_dir):
        raise ValueError('checkpoint belongs to a different run directory')
    if state.get('protocol_sha256') != protocol['protocol_sha256']:
        raise ValueError('checkpoint protocol mismatch')
    if state.get('resume_driver_sha256') != file_sha(__file__):
        raise ValueError('resume helper source changed after checkpoint')
    trace_path = Path(state['training_trace_path'])
    rng = random.Random()
    rng.setstate(tupleize(state['gp_random_state']))
    training_dir = run_dir/'official_training'

    while state['phase'] == 'TRAIN':
        generation = int(state['generation'])
        population_records = state['population']
        if len(population_records) != 10:
            raise ValueError(f'G{generation} checkpoint population is not size 10')
        population = [exp.load_tree(run_dir/row['tree_path'])[0]
                      for row in population_records]
        if [exp.tree_hash(t) for t in population] != [row['tree_sha256'] for row in population_records]:
            raise ValueError('checkpoint population tree hash mismatch')
        member_rows = list(state['generation_member_rows'])
        start_member = int(state['next_member'])
        for member in range(start_member, 10):
            tree = population[member]
            tree_record(run_dir, generation, member, tree)
            summary = exp.evaluate_cached(run_dir, 'train', tree,
                f'official_g{generation}_m{member:02d}_train')
            row = exp._member_record(generation, member, tree, summary)
            member_rows.append(row)
            if row['status'] == 'COMPLETED' and row['train_J'] is not None:
                state['fitness_by_tree_hash'][row['tree_sha256']] = dict(
                    status=row['status'], J=row['train_J'],
                    summary_path=str(run_dir/'rollouts'/'train'/row['tree_sha256']/'rollout_summary.json'))
            ensure_trace_event(trace_path, dict(event='TRAIN_MEMBER', **row))
            state['generation_member_rows'] = member_rows
            state['next_member'] = member+1
            persist_checkpoint(checkpoint_path, state)
            print(f"G{generation} M{member}: {row['status']} J={row['train_J']} cache={row['cache_hit']}", flush=True)
        generation_artifact = dict(generation=generation, label=f'G{generation}',
            population_size=10, members=member_rows,
            valid_members=sum(1 for row in member_rows
                              if row.get('status') == 'COMPLETED' and row.get('train_J') is not None),
            protocol_sha256=protocol['protocol_sha256'])
        write_if_same(training_dir/f'g{generation}.json', generation_artifact)
        if not any(row.get('generation') == generation for row in state['generation_history']):
            state['generation_history'].append(generation_artifact)
        print(f"G{generation}: valid={generation_artifact['valid_members']}/10", flush=True)
        if generation == 9:
            state['phase'] = 'VALIDATION'
            state['validation_index'] = 0
            state['validation_records'] = []
        else:
            evaluated = [(Decimal(row['train_J']),
                          exp.load_tree(run_dir/next(
                              p['tree_path'] for p in population_records
                              if p['tree_sha256'] == row['tree_sha256']))[0])
                         for row in member_rows
                         if row.get('status') == 'COMPLETED' and row.get('train_J') is not None]
            if not evaluated:
                state['phase'] = 'FAILED'
                persist_checkpoint(checkpoint_path, state)
                raise RuntimeError(f'no valid parent in G{generation}')
            next_population = exp.breed(rng, evaluated, 10, tournament=3,
                crossover_rate=.8, mutation_rate=.3, elitism=1, limits=exp.LIMITS)
            next_generation = generation+1
            next_records = [tree_record(run_dir, next_generation, i, tree)
                            for i, tree in enumerate(next_population)]
            state['populations'].append(next_records)
            state['population'] = next_records
            state['generation'] = next_generation
            state['next_member'] = 0
            state['generation_member_rows'] = []
        persist_checkpoint(checkpoint_path, state)

    if state['phase'] == 'VALIDATION':
        # Build unique valid Train candidates from every saved generation population.
        cache = exp._load_cache(run_dir, 'train', protocol['protocol_sha256'])['entries']
        tree_by_hash = {}
        for rows in state['populations']:
            for rec in rows:
                tree = exp.load_tree(run_dir/rec['tree_path'])[0]
                digest = rec['tree_sha256']
                entry = cache.get(digest)
                if entry and entry.get('status') == 'COMPLETED' and entry.get('J') is not None:
                    tree_by_hash.setdefault(digest, dict(tree=tree, train_J=entry['J'],
                        nodes=exp.validate_tree(tree, exp.LIMITS)[0]))
        candidates = sorted(tree_by_hash.values(),
            key=lambda item:(Decimal(item['train_J']), item['nodes'], exp.canonical(item['tree'])))[:5]
        if not candidates:
            raise RuntimeError('no valid unique Train tree for Validation')
        candidate_manifest = [dict(expression=x['tree'].text(),
            tree_sha256=exp.tree_hash(x['tree']), train_J=x['train_J'], nodes=x['nodes'])
            for x in candidates]
        write_if_same(training_dir/'validation_candidates.json',
            dict(protocol_sha256=protocol['protocol_sha256'], candidates=candidate_manifest))
        records = list(state['validation_records'])
        for index in range(int(state['validation_index']), len(candidates)):
            candidate = candidates[index]
            summary = exp.run_rollout(run_dir, policy='gp', partition='validation',
                tree=candidate['tree'], run_id=f'official_validation_{index+1:02d}')
            record = dict(tree_sha256=exp.tree_hash(candidate['tree']),
                          tree_path=str(tree_record(run_dir, 10, index, candidate['tree'])['tree_path']),
                          train_J=candidate['train_J'], nodes=candidate['nodes'],
                          validation_status=summary['status'],
                          validation_J=summary['J'], validation_summary=summary)
            records.append(record)
            state['validation_records'] = records
            state['validation_index'] = index+1
            state['population'] = state['population']
            persist_checkpoint(checkpoint_path, state)
            print(f"Validation {index+1}/{len(candidates)}: {summary['status']} J={summary['J']}", flush=True)
            if summary['status'] != 'COMPLETED' or summary['J'] is None:
                state['phase'] = 'FAILED'
                persist_checkpoint(checkpoint_path, state)
                raise RuntimeError(f'Validation candidate {index+1} invalid')
        records = [dict(r, tree=exp.load_tree(r['tree_path'])[0]) for r in records]
        eligible = [r for r in records if r.get('validation_J') is not None]
        selected = min(eligible, key=exp._selection_key)
        selected_path = run_dir/'trees'/'selected_official_tree.json'
        if selected_path.exists():
            prior, _ = exp.load_tree(selected_path)
            if exp.tree_hash(prior) != exp.tree_hash(selected['tree']):
                raise ValueError('conflicting selected tree artifact')
        else:
            exp.save_tree(selected_path, selected['tree'], training=dict(
                protocol_sha256=protocol['protocol_sha256'], train_J=selected['train_J'],
                validation_J=selected['validation_J']), limits=exp.LIMITS)
        decision = dict(protocol_sha256=protocol['protocol_sha256'],
            selected_expression=selected['tree'].text(),
            selected_tree_sha256=exp.tree_hash(selected['tree']),
            train_J=selected['train_J'], validation_J=selected['validation_J'],
            candidates=[dict(expression=r['tree'].text(),
                tree_sha256=exp.tree_hash(r['tree']), train_J=r['train_J'],
                validation_J=r['validation_J']) for r in records])
        write_if_same(training_dir/'selection_decision.json', decision)
        state['selected_tree_sha256'] = exp.tree_hash(selected['tree'])
        state['phase'] = 'TEST_GP'
        persist_checkpoint(checkpoint_path, state)

    gp_test = None
    vnsme_test = None
    if state['phase'] == 'TEST_GP':
        selected = exp.load_tree(run_dir/'trees'/'selected_official_tree.json')[0]
        gp_test = exp.run_rollout(run_dir, policy='gp', partition='test',
            tree=selected, run_id='official_selected_gp_test')
        if gp_test.get('status') != 'COMPLETED':
            raise RuntimeError('selected GP Test incomplete')
        state['phase'] = 'TEST_VNSME'
        state['gp_test'] = gp_test
        persist_checkpoint(checkpoint_path, state)
        print(f"GP Test: {gp_test['status']} J={gp_test.get('J')}", flush=True)
    if state['phase'] == 'TEST_VNSME':
        vnsme_test = exp.run_rollout(run_dir, policy='vnsme', partition='test',
            tree=None, run_id='official_vnsme_test')
        if vnsme_test.get('status') != 'COMPLETED':
            raise RuntimeError('VNSME Test incomplete')
        state['phase'] = 'COMPLETE'
        state['vnsme_test'] = vnsme_test
        persist_checkpoint(checkpoint_path, state)
        print(f"VNSME Test: {vnsme_test['status']} J={vnsme_test.get('J')}", flush=True)
    if state['phase'] == 'COMPLETE':
        result = dict(status='COMPLETED', protocol_sha256=protocol['protocol_sha256'],
            generations_completed=10, population_size=10,
            train_rollout_requests=sum(len(x) for x in state['populations']),
            selected_tree_sha256=state['selected_tree_sha256'],
            selected_expression=exp.load_tree(run_dir/'trees'/'selected_official_tree.json')[0].text(),
            train_generations=state['generation_history'],
            validation_records=state['validation_records'],
            gp_test=state['gp_test'], vnsme_test=state['vnsme_test'])
        failed = training_dir/'training_result.json'
        if failed.exists() and not (training_dir/'training_result_attempt01_incomplete.json').exists():
            shutil.copy2(failed, training_dir/'training_result_attempt01_incomplete.json')
        exp.write_replace(failed, result)
        exp.write_replace(training_dir/'resume_result.json', result)
        print('Official training, Validation and GP/VNSME Test completed.', flush=True)
        return result
    return state


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('checkpoint', 'resume'))
    parser.add_argument('--run-dir', required=True)
    parser.add_argument('--checkpoint', default=None)
    args = parser.parse_args()
    run_dir = Path(args.run_dir).resolve()
    checkpoint_path = Path(args.checkpoint).resolve() if args.checkpoint else run_dir/'official_training'/'resume_checkpoint.json'
    if args.action == 'checkpoint':
        initial_checkpoint(run_dir, checkpoint_path)
    else:
        run_resume(run_dir, checkpoint_path)


if __name__ == '__main__':
    main()

