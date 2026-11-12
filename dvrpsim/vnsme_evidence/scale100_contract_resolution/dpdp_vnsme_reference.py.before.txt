"""Verified VNSME denominators for the locked development split; no test runs."""
import argparse
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import sys

from dpdp_dataset import resolve_inputs
from dpdp_gp_fitness import digest
from verify_dpdp_score import verify

ROOT = Path(__file__).resolve().parent
DEFAULT_SUMMARY = ROOT/'migration_runs/vnsme_reference_ready/summary.json'
FITNESS_VERSION = 'gp-fitness-vnsme-v2'
SIMULATION = dict(dispatch_step_seconds=600, docking_seconds=1800,
                  loading_seconds_per_quantity=240, unloading_seconds_per_quantity=240,
                  lambda_=10000, initial_location_seed=0, safety_horizon_simulation_seconds=7*86400,
                  visit_merging=False, execution_time_in_simulation='instantaneous, local simulator default')


def independent_score(run, dataset, instance):
    """Validate provenance and rescore trajectory, rather than trusting summary J."""
    run = Path(run)
    manifest = json.loads((run/'manifest.json').read_text(encoding='utf-8'))
    result = json.loads((run/'result.json').read_text(encoding='utf-8'))
    if manifest['policy'] != 'vnsme' or manifest['instance'] != instance:
        raise ValueError('reference rollout must be VNSME for the requested instance')
    if not result['valid'] or not result.get('score'):
        raise ValueError('reference rollout invalid or incomplete')
    if any(manifest[k] != value for k, value in SIMULATION.items()):
        raise ValueError('VNSME reference simulation settings mismatch')
    paths = resolve_inputs(instance_directory=Path(dataset)/'benchmark'/f'instance_{instance}')
    for key in ('orders', 'vehicles', 'factories', 'routes'):
        if Path(manifest['input_paths'][key]).resolve() != paths[key].resolve():
            raise ValueError('VNSME reference input path mismatch')
    if sorted(manifest['data_sha256'].values()) != sorted(digest(paths[k]) for k in ('orders','vehicles','factories','routes')):
        raise ValueError('VNSME reference input hashes mismatch')
    guards = json.loads((run/'decisions.json').read_text())['timings']
    if not guards or not all(r['guard_passed'] for r in guards):
        raise ValueError('VNSME reference lacks successful routing guards')
    score = json.loads(json.dumps(verify(run/'simulation.log', paths['orders'], paths['vehicles'], paths['routes']), default=str))
    if not score['valid'] or any(score[k] != result['score'][k] for k in (
            'total_score', 'total_distance_km', 'total_tardiness_seconds')):
        raise ValueError('VNSME reference independent scorer mismatch')
    if result['completed_items'] != score['items'] or result['completed_original_orders'] != score['original_orders']:
        raise ValueError('VNSME reference completion count mismatch')
    value = float(score['total_score'])
    if not math.isfinite(value) or value <= 0:
        raise ValueError('VNSME denominator must be finite and positive')
    return score


def load_reference(path, expected, protocol_hash, manifest_hash, dataset):
    path = Path(path)
    if not path.exists():
        raise ValueError(f'VNSME reference missing: {path}; run dpdp_vnsme_reference.py first')
    data = json.loads(path.read_text(encoding='utf-8'))
    if data.get('policy') != 'vnsme' or data.get('fitness_version') != FITNESS_VERSION:
        raise ValueError('normalization requires VNSME v2 references; legacy baseline summaries are not accepted')
    if data.get('protocol_sha256') != protocol_hash or data.get('source_manifest_sha256') != manifest_hash:
        raise ValueError('VNSME summary is not bound to locked data/protocol')
    if data.get('seed') != 0:
        raise ValueError('VNSME reference seed mismatch')
    current_build = digest(ROOT/'third_party/vnsme/build_manifest.json')
    if data.get('java_build_sha256') != current_build:
        raise ValueError('VNSME reference Java build mismatch')
    rows = data['records']
    records = {int(r['instance']): r for r in rows}
    if len(rows) != len(records) or set(records) != set(expected):
        raise ValueError('VNSME summary requires exactly all train/validation instances, without duplicates')
    scores = {}
    for instance in expected:
        row = records[instance]
        if not row.get('valid'):
            raise ValueError(f'VNSME reference instance_{instance} invalid')
        run = Path(row['run_directory'])
        for name, sha in row['artifact_sha256'].items():
            if digest(run/name) != sha:
                raise ValueError(f'VNSME reference artifact changed: {run/name}')
        if not {'simulation.log','manifest.json','result.json','decisions.json','vnsme/session.json'} <= set(row['artifact_sha256']):
            raise ValueError('VNSME reference missing required artifact pins')
        session = json.loads((run/'vnsme/session.json').read_text())
        if session['build_manifest'] != json.loads((ROOT/'third_party/vnsme/build_manifest.json').read_text()):
            raise ValueError('VNSME reference session build mismatch')
        score = independent_score(run, dataset, instance)
        if str(row['J']) != score['total_score']:
            raise ValueError('VNSME reference summary J mismatch')
        scores[instance] = score['total_score']
    return scores, data


def generate(output, protocol, dataset, wall_seconds=1800, epoch_seconds=600):
    from train_dpdp_gp_multinstance import load_locked
    _, protocol_hash, manifest_hash, _, train, validation = load_locked(protocol, dataset)
    root = Path(output).resolve()
    root.mkdir(parents=True, exist_ok=False)
    records = []
    summary = dict(policy='vnsme', fitness_version=FITNESS_VERSION, seed=0,
                   protocol_sha256=protocol_hash, source_manifest_sha256=manifest_hash,
                   java_build_sha256=digest(ROOT/'third_party/vnsme/build_manifest.json'),
                   simulation=SIMULATION, wall_seconds=wall_seconds, epoch_seconds=epoch_seconds,
                   records=records, valid=False, sealed_test_rollouts=0)
    for instance in train+validation:
        run = root/f'instance_{instance}'
        command = [sys.executable, str(ROOT/'run_dpdp_insertion.py'), '--policy', 'vnsme',
                   '--instance-directory', str(Path(dataset).resolve()/'benchmark'/f'instance_{instance}'),
                   '--output', str(run), '--wall-seconds', str(wall_seconds),
                   '--vnsme-epoch-seconds', str(epoch_seconds)]
        row = dict(instance=instance, policy='vnsme', valid=False, J=None, run_directory=str(run), command=command)
        try:
            with (root/f'instance_{instance}_process.txt').open('x', encoding='utf-8') as log:
                proc = subprocess.Popen(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                                        start_new_session=(os.name != 'nt'))
                try:
                    code = proc.wait(timeout=wall_seconds+30)
                except subprocess.TimeoutExpired:
                    if os.name == 'nt':
                        subprocess.run(['taskkill','/PID',str(proc.pid),'/T','/F'], capture_output=True)
                    else:
                        os.killpg(proc.pid, signal.SIGKILL)
                    proc.wait()
                    raise TimeoutError('VNSME reference process deadline exceeded')
            if code:
                raise ValueError(f'VNSME instance_{instance} failed, exit={code}; see {run}')
            score = independent_score(run, dataset, instance)
            (run/'reference_independent_score.json').write_text(json.dumps(score, indent=2), encoding='utf-8')
            row.update(valid=True, J=score['total_score'], D=score['total_distance_km'], T=score['total_tardiness_seconds'],
                       artifact_sha256={name: digest(run/name) for name in (
                           'simulation.log','manifest.json','result.json','decisions.json','vnsme/session.json')})
        except Exception as exc:
            row['error'] = f'{type(exc).__name__}: {exc}'
        records.append(row)
        (root/'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
        print(f'VNSME instance {instance}: valid={row["valid"]}, J={row["J"]}', flush=True)
    summary['valid'] = all(r['valid'] for r in records)
    (root/'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    return summary


def adopt(output, runs, protocol, dataset):
    """Assemble verified independent runs without repeating expensive searches."""
    from train_dpdp_gp_multinstance import load_locked
    _, ph, mh, _, train, validation = load_locked(protocol, dataset)
    expected = train+validation
    by_instance = {}
    for directory in runs:
        run = Path(directory).resolve()
        instance = json.loads((run/'manifest.json').read_text())['instance']
        if instance not in expected or instance in by_instance:
            raise ValueError('adoption requires exactly one run for each train/validation instance')
        by_instance[instance] = run
    if set(by_instance) != set(expected):
        raise ValueError('adoption missing train/validation instances')
    records = []
    for instance in expected:
        run = by_instance[instance]
        score = independent_score(run, dataset, instance)
        manifest = json.loads((run/'manifest.json').read_text())
        records.append(dict(instance=instance, policy='vnsme', valid=True,
            run_directory=str(run), J=score['total_score'], D=score['total_distance_km'], T=score['total_tardiness_seconds'],
            wall_seconds=manifest['wall_limit_seconds'], epoch_seconds=manifest['vnsme_epoch_limit_seconds'],
            artifact_sha256={name: digest(run/name) for name in (
                'simulation.log','manifest.json','result.json','decisions.json','vnsme/session.json')}))
    root = Path(output).resolve()
    root.mkdir(parents=True, exist_ok=False)
    summary = dict(policy='vnsme', fitness_version=FITNESS_VERSION, seed=0,
                   protocol_sha256=ph, source_manifest_sha256=mh, simulation=SIMULATION,
                   java_build_sha256=digest(ROOT/'third_party/vnsme/build_manifest.json'),
                   records=records, valid=False, sealed_test_rollouts=0,
                   assembly='independently_verified_existing_runs')
    path = root/'summary.json'
    path.write_text(json.dumps(summary, indent=2), encoding='utf-8')
    load_reference(path, expected, ph, mh, dataset)
    summary['valid'] = True
    path.write_text(json.dumps(summary, indent=2), encoding='utf-8')
    return summary


if __name__ == '__main__':
    from train_dpdp_gp_multinstance import DEFAULT_PROTOCOL, DEFAULT_DATASET
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=DEFAULT_SUMMARY.parent)
    parser.add_argument('--protocol', type=Path, default=DEFAULT_PROTOCOL)
    parser.add_argument('--dataset', type=Path, default=DEFAULT_DATASET)
    parser.add_argument('--adopt-runs', type=Path, nargs='+', help='assemble complete, independently verified existing VNSME runs')
    parser.add_argument('--wall-seconds', type=float, default=1800)
    parser.add_argument('--vnsme-epoch-seconds', type=float, default=600)
    args = parser.parse_args()
    if any(not math.isfinite(v) or v <= 0 for v in (args.wall_seconds, args.vnsme_epoch_seconds)):
        parser.error('timeouts must be finite and positive')
    result = (adopt(args.output, args.adopt_runs, args.protocol, args.dataset) if args.adopt_runs
              else generate(args.output, args.protocol, args.dataset, args.wall_seconds, args.vnsme_epoch_seconds))
    sys.exit(0 if result['valid'] else 1)
