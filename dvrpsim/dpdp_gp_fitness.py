"""Fitness is independently checked final benchmark J, never a tree ranking.

Rollouts run in fresh processes with a hard process deadline. Invalid outcomes
have benchmark_J=None and a separate fixed penalty fitness, not a valid score.
"""
import csv
import hashlib
import importlib.metadata
import json
import math
from pathlib import Path
import subprocess
import sys
from time import perf_counter

from dpdp_gp import canonical, save_tree, tree_hash, TreeError, NUMERIC_POLICY, Limits
from verify_dpdp_score import verify
from dpdp_dataset import resolve_inputs

ROOT = Path(__file__).resolve().parent
DATA = ROOT/'examples/case_studies/dpdp/data'
INVALID_FITNESS = 1e15


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def source_hashes():
    return {str(p.relative_to(ROOT)): digest(p) for p in sorted(ROOT.rglob('*.py'))
            if not any(x in p.parts for x in ('.git', '.venv', '__pycache__', 'baseline_runs', 'gp_runs',
                                            'vnsme_runs', 'migration_runs', 'third_party'))}


def discover_instances():
    inventory = {}
    for folder in sorted(DATA.glob('instance_*')):
        orders = sorted(p for p in folder.glob('*.csv') if not p.name.startswith('vehicle_info'))
        vehicles = sorted(folder.glob('vehicle_info_*.csv'))
        if len(orders) != 1 or len(vehicles) != 1:
            raise ValueError(f'ambiguous instance directory: {folder}')
        with orders[0].open(encoding='utf-8-sig', newline='') as handle:
            rows = list(csv.DictReader(handle))
        with vehicles[0].open(encoding='utf-8-sig', newline='') as handle:
            cars = list(csv.DictReader(handle))
        inventory[int(folder.name.split('_')[1])] = dict(
            orders=str(orders[0]), vehicles=str(vehicles[0]), original_orders=len(rows),
            items=sum(sum(int(r[k]) for k in ('q_standard', 'q_small', 'q_box')) for r in rows),
            vehicle_num=len(cars))
    return inventory


def cache_key(tree, context):
    raw = json.dumps(dict(tree=json.loads(canonical(tree)), context=context),
                     sort_keys=True, separators=(',', ':'), allow_nan=False)
    return hashlib.sha256(raw.encode()).hexdigest()


def assess_result(result, independent):
    if not result.get('valid') or result.get('score') is None or not independent or not independent.get('valid'):
        raise ValueError('invalid/incomplete rollout, no benchmark fitness')
    if result['completed_items'] != independent['items'] or result['completed_original_orders'] != independent['original_orders']:
        raise ValueError('completion counts disagree with independent scorer')
    for key in ('total_distance_km', 'total_tardiness_seconds', 'total_score'):
        if str(result['score'][key]) != str(independent[key]):
            raise ValueError('runner score disagrees with independent scorer')
    fitness = float(independent['total_score'])
    if not math.isfinite(fitness):
        raise ValueError('nonfinite benchmark fitness')
    return fitness


class RolloutEvaluator:
    def __init__(self, directory, evolution_seed, wall_seconds=10, environment_seed=0,
                 dataset_root=None, protocol_sha256=None, source_manifest_sha256=None,
                 protocol_path=None, source_manifest_path=None, normalization_reference_path=None):
        self.directory = Path(directory).resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        for name in ('cache', 'models', 'rollouts'):
            (self.directory/name).mkdir(exist_ok=True)
        self.evolution_seed, self.wall_seconds, self.environment_seed = evolution_seed, wall_seconds, environment_seed
        self.dataset_root = Path(dataset_root).resolve() if dataset_root else None
        self.protocol_sha256 = protocol_sha256
        self.source_manifest_sha256 = source_manifest_sha256
        self.protocol_path = Path(protocol_path).resolve() if protocol_path else None
        self.source_manifest_path = Path(source_manifest_path).resolve() if source_manifest_path else None
        self.normalization_reference_path = Path(normalization_reference_path).resolve() if normalization_reference_path else None
        self.normalization_reference_sha256 = digest(self.normalization_reference_path) if self.normalization_reference_path else None
        self.records = []

    def verify_pins(self):
        if self.normalization_reference_path is not None and digest(self.normalization_reference_path) != self.normalization_reference_sha256:
            raise ValueError('VNSME normalization reference changed during experiment')
        if self.protocol_path is not None and digest(self.protocol_path) != self.protocol_sha256:
            raise ValueError('locked protocol changed during experiment')
        if self.source_manifest_path is not None and digest(self.source_manifest_path) != self.source_manifest_sha256:
            raise ValueError('source manifest changed during experiment')

    def inputs(self, instance):
        if self.dataset_root is None:
            entry = discover_instances()[instance]
            return dict(directory=None, data_directory=DATA,
                        orders=Path(entry['orders']), vehicles=Path(entry['vehicles']),
                        factories=DATA/'factory_info.csv', routes=DATA/'route_info.csv')
        benchmark = self.dataset_root/'benchmark'
        return resolve_inputs(instance_directory=benchmark/f'instance_{instance}', data_directory=benchmark)

    def context(self, instance):
        paths = self.inputs(instance)
        files = [paths['orders'], paths['vehicles'], paths['factories'], paths['routes']]
        return dict(version='gp-final-j-v2', instance=instance, initial_location_seed=self.environment_seed,
                    normalization_reference_sha256=self.normalization_reference_sha256,
                    evolution_seed=self.evolution_seed, deterministic_policy=True, wall_seconds=self.wall_seconds,
                    simulation_horizon=7*86400, dispatch=600, docking=1800, loading=240, unloading=240,
                    lambda_=10000, numeric_policy=NUMERIC_POLICY, limits=vars(Limits()),
                    protocol_sha256=self.protocol_sha256, source_manifest_sha256=self.source_manifest_sha256,
                    sources=source_hashes(), data={str(p.resolve()): digest(p) for p in files},
                    python=sys.version, executable=sys.executable,
                    packages={n: importlib.metadata.version(n) for n in ('dvrpsim', 'simpy')})

    def evaluate(self, tree, instance=1, force=False):
        started = perf_counter()
        try:
            self.verify_pins()
            context = self.context(instance)
            key = cache_key(tree, context)
        except (TreeError, ValueError) as exc:
            record = dict(valid=False, benchmark_J=None, fitness=INVALID_FITNESS, status='tree_error',
                          error=str(exc), cache_hit=False, process_started=False,
                          instance=instance, request_wall_seconds=perf_counter()-started)
            self.records.append(record)
            return record
        path = self.directory/'cache'/f'{key}.json'
        if path.exists() and not force:
            record = json.loads(path.read_text(encoding='utf-8'))
            if record['cache_key'] != key or record['context'] != context:
                raise ValueError('cache provenance mismatch')
            if record.get('log_sha256') and digest(Path(record['run_directory'])/'simulation.log') != record['log_sha256']:
                raise ValueError('cached log changed')
            record = {**record, 'cache_hit': True, 'process_started': False,
                      'instance': instance, 'request_wall_seconds': perf_counter()-started}
            self.records.append(record)
            return record
        model_path = self.directory/'models'/f'{key}.json'
        if not model_path.exists():
            save_tree(model_path, tree, training={'evaluation_context': context})
        run = self.directory/'rollouts'/f'{key}_{len(self.records):04d}'
        paths = self.inputs(instance)
        command = [sys.executable, '-B', str(ROOT/'run_dpdp_insertion.py'), '--policy', 'gp',
                   '--tree', str(model_path)]
        if paths['directory'] is None:
            command += ['--instance', str(instance)]
        else:
            command += ['--instance-directory', str(paths['directory']),
                        '--data-directory', str(paths['factories'].parent)]
        command += ['--seed', str(self.environment_seed), '--wall-seconds', str(self.wall_seconds),
                    '--output', str(run)]
        record = dict(cache_key=key, tree_sha256=tree_hash(tree), expression=tree.text(), context=context,
                      run_directory=str(run), valid=False, benchmark_J=None, fitness=INVALID_FITNESS,
                      cache_hit=False, process_started=True, status='invalid', error=None)
        process_start = perf_counter()
        try:
            process = subprocess.run(command, cwd=ROOT, capture_output=True, encoding='utf-8',
                                     errors='replace', timeout=self.wall_seconds)
            result_path = run/'result.json'
            result = json.loads(result_path.read_text(encoding='utf-8')) if result_path.exists() else None
            record['return_code'] = process.returncode
            if process.returncode or result is None or not result.get('valid'):
                message = result.get('error') if result else process.stderr[-2000:]
                record['error'] = message
                record['status'] = ('tree_error' if any(word in str(message) for word in ('TreeError', 'nonfinite'))
                                    else 'timeout' if 'wall-time' in str(message) else 'invalid')
            else:
                independent = verify(run/'simulation.log', paths['orders'], paths['vehicles'], paths['routes'])
                fitness = assess_result(result, independent)
                with (run/'independent_fitness.json').open('x', encoding='utf-8') as handle:
                    json.dump(independent, handle, indent=2, default=str)
                record.update(valid=True, status='complete', fitness=fitness, benchmark_J=str(independent['total_score']),
                              score={k: str(independent[k]) for k in ('total_distance_km', 'total_tardiness_seconds', 'total_score')},
                              completed_items=result['completed_items'], completed_original_orders=result['completed_original_orders'],
                              gp_evaluation=result['gp_evaluation'])
        except subprocess.TimeoutExpired:
            record.update(status='timeout', error='hard process deadline exceeded; no valid benchmark score')
        except (ValueError, OSError) as exc:
            record.update(status='invalid', error=str(exc))
        record.update(process_wall_seconds=perf_counter()-process_start,
                      request_wall_seconds=perf_counter()-started, instance=instance)
        if (run/'simulation.log').exists():
            record['log_sha256'] = digest(run/'simulation.log')
        if path.exists():
            original = json.loads(path.read_text(encoding='utf-8'))
            if force and (original['valid'] != record['valid'] or original['benchmark_J'] != record['benchmark_J']
                          or original.get('log_sha256') != record.get('log_sha256')):
                raise ValueError('forced repeat was not deterministic')
        else:
            with path.open('x', encoding='utf-8') as handle:
                json.dump(record, handle, indent=2)
        self.records.append(record)
        return record
