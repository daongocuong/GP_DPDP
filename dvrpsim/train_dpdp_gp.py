"""Frozen small pilot: instance_1 training only; instance_17 never selects trees."""
import argparse
from collections import Counter
import json
from pathlib import Path
import random
import sys
from time import perf_counter

from dpdp_gp import (Node, Limits, canonical, initial_population, breed, validate_tree, save_tree)
from dpdp_gp_fitness import RolloutEvaluator, discover_instances, source_hashes

DEFAULT_CONFIG = dict(population=6, generations=2, seed=20261105, tournament=3,
                      crossover_rate=.8, mutation_rate=.3, elitism=1,
                      train_instances=[1], validation_instances=[], test_instances=[],
                      frozen_descriptive_comparison_instances=[1, 17],
                      environment_seed=0, train_wall_seconds=10, comparison_wall_seconds=60)


def train(directory, config=None):
    config = dict(DEFAULT_CONFIG if config is None else config)
    root = Path(directory).resolve()
    root.mkdir(parents=True, exist_ok=False)
    inventory = discover_instances()
    if set(config['train_instances']) != {1}:
        raise ValueError('this pilot trains only on instance_1')
    protocol = dict(config=config, inventory=inventory, sources=source_hashes(), limits=vars(Limits()),
                    statement='Two local instances only. No independent train/validation/test protocol. '
                              'Select on instance_1 only; freeze tree before descriptive instance_17 evaluation.')
    with (root/'protocol.json').open('x', encoding='utf-8') as handle:
        json.dump(protocol, handle, indent=2)
    evaluator = RolloutEvaluator(root/'fitness', config['seed'], config['train_wall_seconds'])
    start = perf_counter()
    # Smoke BEFORE evolution: real ranking calls, independently scored completion,
    # a cache hit, and a forced fresh repeat with identical log hash.
    smoke_tree = Node('+', args=(Node('feature', 'delta_distance_km'), Node('feature', 'delta_tardiness_seconds')))
    smoke = evaluator.evaluate(smoke_tree)
    cached = evaluator.evaluate(smoke_tree)
    repeated = evaluator.evaluate(smoke_tree, force=True)
    if not smoke['valid'] or not cached['cache_hit'] or not repeated['valid'] or smoke['gp_evaluation']['evaluations'] <= 0:
        raise ValueError('smoke failed; inspect retained rollout artifacts')
    with (root/'smoke.json').open('x', encoding='utf-8') as handle:
        json.dump(dict(first=smoke, cached=cached, repeated=repeated), handle, indent=2)
    rng = random.Random(config['seed'])
    population = initial_population(rng, config['population'])
    history = []
    best = None
    for generation in range(config['generations']+1):
        evaluated, members = [], []
        for tree in population:
            outcome = evaluator.evaluate(tree)
            evaluated.append((outcome['fitness'], tree))
            members.append(dict(tree=tree.data(), expression=tree.text(), fitness=outcome['fitness'],
                                benchmark_J=outcome['benchmark_J'], valid=outcome['valid'],
                                status=outcome['status'], cache_hit=outcome['cache_hit'],
                                run_directory=outcome.get('run_directory')))
            key = (outcome['fitness'], validate_tree(tree)[0], canonical(tree))
            if outcome['valid'] and (best is None or key < best[0]):
                best = key, tree, outcome
        history.append(dict(generation=generation, members=members, best_training_fitness=best[0][0] if best else None,
                            cache_hits=sum(m['cache_hit'] for m in members),
                            invalid=sum(not m['valid'] for m in members), elapsed_wall_seconds=perf_counter()-start))
        # New files per generation survive interruption; never overwrite a prior run.
        with (root/f'generation_{generation}.json').open('x', encoding='utf-8') as handle:
            json.dump(history[-1], handle, indent=2)
        print(f'generation {generation}: best={history[-1]["best_training_fitness"]}, invalid={history[-1]["invalid"]}', flush=True)
        if generation < config['generations']:
            population = breed(rng, evaluated, config['population'], config['tournament'],
                               config['crossover_rate'], config['mutation_rate'], config['elitism'])
    if best is None:
        raise ValueError('no valid tree; no best model exported')
    _, tree, outcome = best
    save_tree(root/'best_tree.json', tree, training=dict(config=config, sources=protocol['sources'],
              fitness=outcome['fitness'], benchmark_J=outcome['benchmark_J'], instance=1,
              selected_before_instance_17_evaluation=True))
    summary = dict(config=config, best_expression=tree.text(), best_training_fitness=outcome['fitness'],
                   history=history, total_wall_seconds=perf_counter()-start,
                   evaluation_requests=len(evaluator.records), cache_hits=sum(r['cache_hit'] for r in evaluator.records),
                   process_rollouts=sum(r['process_started'] for r in evaluator.records),
                   statuses=dict(Counter(r['status'] for r in evaluator.records if r['process_started'])),
                   unique_invalid_trees=len({r.get('tree_sha256') for r in evaluator.records if not r['valid']}),
                   numeric_tree_error_requests=sum(r['status']=='tree_error' for r in evaluator.records),
                   requests=evaluator.records)
    with (root/'training.json').open('x', encoding='utf-8') as handle:
        json.dump(summary, handle, indent=2)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    expected = Path(__file__).resolve().parent/'.venv/Scripts/python.exe'
    if Path(sys.executable).resolve() != expected.resolve():
        parser.error('use repository .venv interpreter')
    result = train(args.output)
    print(json.dumps({k: v for k, v in result.items() if k not in ('history', 'requests')}, indent=2))


if __name__ == '__main__':
    main()
