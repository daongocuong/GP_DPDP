"""Protocol-locked multi-instance GP development experiment (50-order split only)."""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import random
import sys
from time import perf_counter

from dpdp_gp import Limits, canonical, initial_population, breed, validate_tree, save_tree
from dpdp_gp_fitness import INVALID_FITNESS, RolloutEvaluator, digest, source_hashes
from dpdp_dataset import validate_instance
from prepare_dpdp_data import verify_existing
from dpdp_vnsme_reference import DEFAULT_SUMMARY, FITNESS_VERSION, load_reference

ROOT = Path(__file__).resolve().parent
DEFAULT_PROTOCOL = ROOT/'protocols/dpdp_gp_split_v1.json'
DEFAULT_DATASET = ROOT/'datasets/xingtian/e4ef3a1c92d19d1d08c3ef0e2156b6fecefdbe04'
DEFAULT_BASELINES = DEFAULT_SUMMARY
PENALTY = INVALID_FITNESS


def load_locked(protocol_path, dataset_root):
    protocol_path, dataset_root = Path(protocol_path).resolve(), Path(dataset_root).resolve()
    raw = protocol_path.read_bytes()
    protocol_hash = hashlib.sha256(raw).hexdigest()
    sidecar = protocol_path.with_suffix(protocol_path.suffix+'.sha256')
    if sidecar.exists() and sidecar.read_text(encoding='utf-8').split()[0] != protocol_hash:
        raise ValueError('protocol checksum sidecar mismatch')
    protocol = json.loads(raw)
    manifest_path = (ROOT/protocol['dataset_manifest']).resolve()
    if manifest_path.parent != dataset_root.resolve():
        raise ValueError('dataset root does not match locked protocol manifest')
    manifest_hash = digest(manifest_path)
    if manifest_hash != protocol['dataset_manifest_sha256']:
        raise ValueError('source manifest hash does not match locked protocol')
    manifest_sidecar = manifest_path.with_name('source_manifest.sha256')
    if manifest_sidecar.read_text(encoding='utf-8').split()[0] != manifest_hash:
        raise ValueError('source manifest checksum sidecar mismatch')
    if protocol['source_commit'] != 'e4ef3a1c92d19d1d08c3ef0e2156b6fecefdbe04':
        raise ValueError('unexpected upstream commit')
    roles = protocol['roles']['50_orders']
    train = tuple(roles['train'])
    validation = tuple(roles['validation'])
    sealed = set(roles['final_test_sealed'])
    if train != (2, 3, 4, 5) or validation != (6,) or sealed != {7, 8}:
        raise ValueError('unexpected 50-order split')
    if sealed & (set(train) | set(validation)):
        raise ValueError('sealed instance entered train/validation')
    if protocol.get('gp_allowed_this_task') is not False:
        raise ValueError('source protocol was not locked for preparation only')
    manifest = verify_existing(dataset_root)
    return protocol, protocol_hash, manifest_hash, manifest_path, train, validation


def aggregate_training(instance_records, baseline_scores):
    """Equal weight mean of per-instance J ratios; one invalid instance invalidates tree."""
    ordered = sorted(instance_records, key=lambda item: item['instance'])
    if not ordered:
        raise ValueError('training fitness requires all train instances')
    ratios = []
    valid = len(ordered) == 4 and {x['instance'] for x in ordered} == {2, 3, 4, 5}
    for record in ordered:
        baseline = float(baseline_scores[record['instance']])
        if not math.isfinite(baseline) or baseline <= 0:
            raise ValueError('VNSME J denominator must be finite and positive')
        if (not record.get('valid') or record.get('benchmark_J') is None
                or not math.isfinite(float(record['benchmark_J'])) or float(record['benchmark_J']) < 0):
            valid = False
            ratios.append(None)
        else:
            ratios.append(float(record['benchmark_J'])/baseline)
    return dict(valid=valid, fitness=sum(ratios)/len(ratios) if valid else PENALTY,
                ratios=ratios, aggregation='arithmetic_mean_of_J_GP_over_J_VNSME',
                fitness_version=FITNESS_VERSION, normalization_policy='vnsme',
                invalid_instances=[x['instance'] for x in ordered if not x.get('valid')])


def validation_key(record, train_fitness, tree):
    if not record.get('valid') or record.get('benchmark_J') is None:
        return None
    nodes, _ = validate_tree(tree)
    return (float(record['benchmark_J'])/float(record['baseline_J']),
            train_fitness, nodes, canonical(tree))


def require_experiment_instance(instance, train_ids, validation_ids):
    if instance not in set(train_ids) | set(validation_ids):
        raise ValueError(f'instance_{instance} is sealed or outside this experiment')
    return instance


def _baseline_scores(path, expected, protocol_hash, manifest_hash, dataset_root=DEFAULT_DATASET):
    return load_reference(path, expected, protocol_hash, manifest_hash, dataset_root)


def run_experiment(output, protocol_path=DEFAULT_PROTOCOL, dataset_root=DEFAULT_DATASET,
                   baseline_summary=DEFAULT_BASELINES, population_size=6, generations=2,
                   seed=20261106, wall_seconds=30, measure_only=False):
    root = Path(output).resolve()
    root.mkdir(parents=True, exist_ok=False)
    protocol, protocol_hash, manifest_hash, manifest_path, train_ids, validation_ids = load_locked(protocol_path, dataset_root)
    baseline_scores, baseline_data = _baseline_scores(baseline_summary, (*train_ids, *validation_ids), protocol_hash, manifest_hash, dataset_root)
    benchmark = Path(dataset_root).resolve()/'benchmark'
    for instance in (*train_ids, *validation_ids):
        validate_instance(benchmark/f'instance_{instance}', benchmark)
    source_code = source_hashes()
    config = dict(population=population_size, generations=generations, seed=seed, tournament=3,
                  crossover_rate=.8, mutation_rate=.3, elitism=1, environment_seed=0,
                  train_instances=list(train_ids), validation_instances=list(validation_ids),
                  sealed_instances=[7,8], timeout_seconds=wall_seconds,
                  invalid_fitness=PENALTY, fitness='mean(J_gp/J_vnsme) over all four train instances',
                  fitness_version=FITNESS_VERSION, normalization_policy='vnsme',
                  validation_selection='valid validation ratio, then train fitness, node count, canonical tree',
                  validation_not_used_for_evolution=True, generation_measurement_only=measure_only)
    protocol_record = dict(config=config, protocol_sha256=protocol_hash, source_manifest_sha256=manifest_hash,
                           source_manifest=str(manifest_path), source_commit=protocol['source_commit'],
                           baseline_summary=str(Path(baseline_summary).resolve()),
                           baseline_summary_sha256=digest(baseline_summary),
                           baseline_scores=baseline_scores, code_hashes=source_code,
                           numeric_policy='dpdp_gp.NUMERIC_POLICY', limits=vars(Limits()))
    (root/'experiment_protocol.json').write_text(json.dumps(protocol_record, indent=2), encoding='utf-8')
    evaluator = RolloutEvaluator(root/'fitness', seed, wall_seconds, 0, dataset_root=dataset_root,
                                 protocol_sha256=protocol_hash, source_manifest_sha256=manifest_hash,
                                 protocol_path=protocol_path, source_manifest_path=manifest_path,
                                 normalization_reference_path=baseline_summary)
    rng = random.Random(seed)
    population = initial_population(rng, population_size)
    all_candidates = {}
    history = []
    started = perf_counter()
    for generation in range(generations+1):
        generation_start = perf_counter()
        scored = []
        members = []
        for tree in population:
            evaluator.verify_pins()
            per_instance = [evaluator.evaluate(tree, instance=require_experiment_instance(i, train_ids, validation_ids)) for i in train_ids]
            aggregate = aggregate_training(per_instance, baseline_scores)
            nodes, depth = validate_tree(tree)
            member = dict(tree=tree.data(), expression=tree.text(), canonical=canonical(tree),
                          nodes=nodes, depth=depth, fitness=aggregate['fitness'], valid=aggregate['valid'],
                          ratios=aggregate['ratios'], invalid_instances=aggregate['invalid_instances'],
                          instances={str(i): r for i, r in zip(train_ids, per_instance)})
            members.append(member)
            scored.append((aggregate['fitness'], tree))
            all_candidates.setdefault(canonical(tree), tree)
        generation_record = dict(generation=generation, members=members,
                                best_valid_fitness=min((m['fitness'] for m in members if m['valid']), default=None),
                                valid_tree_count=sum(m['valid'] for m in members),
                                timeout_count=sum(r['status']=='timeout' for e in evaluator.records for r in [e]
                                                  if e.get('process_started') and e.get('context',{}).get('instance') in train_ids),
                                cache_hits=sum(r['cache_hit'] for r in evaluator.records),
                                elapsed_generation_wall_seconds=perf_counter()-generation_start,
                                elapsed_total_wall_seconds=perf_counter()-started)
        history.append(generation_record)
        (root/f'generation_{generation}.json').write_text(json.dumps(generation_record, indent=2), encoding='utf-8')
        print(f"generation {generation}: best valid mean ratio={generation_record['best_valid_fitness']}, "
              f"valid={generation_record['valid_tree_count']}/{population_size}, "
              f"wall={generation_record['elapsed_generation_wall_seconds']:.3f}s", flush=True)
        if generation < generations:
            population = breed(rng, scored, population_size, config['tournament'], config['crossover_rate'],
                               config['mutation_rate'], config['elitism'])
    # A train-only probe estimates one full generation without consulting validation.
    candidates = []
    if not measure_only:
        for tree in all_candidates.values():
            evaluator.verify_pins()
            train_records = [evaluator.evaluate(tree, instance=require_experiment_instance(i, train_ids, validation_ids)) for i in train_ids]
            aggregate = aggregate_training(train_records, baseline_scores)
            if not aggregate['valid']:
                continue
            val = evaluator.evaluate(tree, instance=require_experiment_instance(validation_ids[0], train_ids, validation_ids))
            val_record = dict(val, baseline_J=baseline_scores[validation_ids[0]])
            key = validation_key(val_record, aggregate['fitness'], tree)
            candidates.append(dict(tree=tree, train=aggregate, train_records=train_records,
                                   validation=val_record, selection_key=key))
    eligible = [c for c in candidates if c['selection_key'] is not None]
    selected = min(eligible, key=lambda c: c['selection_key']) if eligible else None
    (root/'candidates.json').write_text(json.dumps([
        dict(expression=c['tree'].text(), tree=c['tree'].data(), train_fitness=c['train']['fitness'],
             train_valid=c['train']['valid'], validation={k:v for k,v in c['validation'].items() if k!='context'},
             selection_key=c['selection_key']) for c in candidates], indent=2), encoding='utf-8')
    if selected:
        save_tree(root/'selected_tree.json', selected['tree'], training=dict(
            protocol_sha256=protocol_hash, source_manifest_sha256=manifest_hash,
            train_fitness=selected['train']['fitness'], validation_ratio=selected['selection_key'][0],
            selected_by='locked validation rule; no test instances accessed', config=config,
            code_hashes=source_code))
    records = evaluator.records
    summary = dict(status='generation_measurement_only' if measure_only else ('complete' if selected else 'incomplete_no_valid_train_and_validation_tree'),
                   config=config, selected_expression=selected['tree'].text() if selected else None,
                   selected_validation_ratio=selected['selection_key'][0] if selected else None,
                   unique_generated_trees=len(all_candidates), valid_train_and_validation_candidates=len(eligible),
                   history=history, total_wall_seconds=perf_counter()-started,
                   evaluation_requests=len(records), cache_hits=sum(r['cache_hit'] for r in records),
                   actual_process_rollouts=sum(r['process_started'] for r in records),
                   rollout_statuses=dict(Counter(r['status'] for r in records if r['process_started'])),
                   timeout_count=sum(r['status']=='timeout' for r in records if r['process_started']),
                   invalid_tree_count=len({r.get('tree_sha256') for r in records if not r['valid']}),
                   records=records)
    (root/'training.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--protocol', type=Path, default=DEFAULT_PROTOCOL)
    parser.add_argument('--dataset', type=Path, default=DEFAULT_DATASET)
    parser.add_argument('--baseline-summary', type=Path, default=DEFAULT_BASELINES)
    parser.add_argument('--population', type=int, default=6)
    parser.add_argument('--generations', type=int, default=2)
    parser.add_argument('--seed', type=int, default=20261106)
    parser.add_argument('--timeout-seconds', type=float, default=30)
    parser.add_argument('--measure-generation-only', action='store_true')
    args = parser.parse_args()
    expected = ROOT/'.venv/Scripts/python.exe'
    if Path(sys.executable).resolve() != expected.resolve():
        parser.error('use repository .venv interpreter')
    if args.population < 2 or args.generations < 0 or args.timeout_seconds <= 0:
        parser.error('invalid evolution size or timeout')
    result = run_experiment(args.output, args.protocol, args.dataset, args.baseline_summary,
                            args.population, args.generations, args.seed, args.timeout_seconds,
                            args.measure_generation_only)
    print(json.dumps({k:v for k,v in result.items() if k!='records'}, indent=2))
    return 0 if result['status'] in ('complete', 'generation_measurement_only') else 2


if __name__ == '__main__':
    sys.exit(main())
