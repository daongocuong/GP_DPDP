"""Reproducible instance-2 integration comparison; never opens final tests.

VNSME is the evaluation comparator and fitness denominator.
Uses the frozen selected GP tree without retraining.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
from time import perf_counter

from dpdp_dataset import resolve_inputs
from verify_dpdp_score import verify

ROOT = Path(__file__).resolve().parent
DATA = ROOT/'datasets/xingtian/e4ef3a1c92d19d1d08c3ef0e2156b6fecefdbe04/benchmark'
TREE = ROOT/'gp_runs/multinstance_50_20261105/main/selected_tree.json'


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--tree', type=Path, default=TREE)
    parser.add_argument('--wall-seconds', type=float, default=1800)
    parser.add_argument('--vnsme-epoch-seconds', type=float, default=600)
    parser.add_argument('--java', default='java')
    args = parser.parse_args()
    import math
    if any(not math.isfinite(n) or n <= 0 for n in (args.wall_seconds, args.vnsme_epoch_seconds)):
        parser.error('timeouts must be positive and finite')
    directory = args.output.resolve()
    directory.mkdir(parents=True, exist_ok=False)
    paths = resolve_inputs(instance_directory=DATA/'instance_2')
    source_pins = {str(p.relative_to(ROOT)): digest(p) for p in [
        ROOT/'dpdp_gp_fitness.py', ROOT/'train_dpdp_gp_multinstance.py',
        ROOT/'dpdp_insertion.py', ROOT/'verify_dpdp_score.py',
        ROOT/'protocols/dpdp_gp_split_v1.json', args.tree.resolve()]}
    summary = dict(instance=2, primary_evaluation_baseline='vnsme', gp_fitness_reference='vnsme',
                   final_tests_executed=[], source_pins=source_pins, runs={}, valid=False)
    start = perf_counter()
    manifests = []
    for policy in ('gp', 'vnsme'):
        output = directory/policy
        command = [sys.executable, str(ROOT/'run_dpdp_insertion.py'), '--policy', policy,
                   '--instance-directory', str(DATA/'instance_2'), '--output', str(output),
                   '--wall-seconds', str(args.wall_seconds),
                   '--vnsme-epoch-seconds', str(args.vnsme_epoch_seconds), '--java', args.java]
        if policy == 'gp':
            command.extend(['--tree', str(args.tree.resolve())])
        with (directory/f'{policy}_process.txt').open('x', encoding='utf-8') as log:
            process = subprocess.Popen(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                                       start_new_session=(os.name != 'nt'))
            try:
                code = process.wait(timeout=args.wall_seconds+30)
            except subprocess.TimeoutExpired:
                if os.name == 'nt':
                    subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True)
                else:
                    os.killpg(process.pid, signal.SIGKILL)
                process.wait()
                code = -1
        entry = dict(command=command, returncode=code, valid=False)
        if (output/'result.json').exists():
            entry['result'] = json.loads((output/'result.json').read_text())
            if code == 0 and entry['result']['valid']:
                checked = json.loads(json.dumps(verify(output/'simulation.log', paths['orders'],
                    paths['vehicles'], paths['routes']), default=str))
                (output/'comparison_independent_score.json').write_text(json.dumps(checked, indent=2))
                entry['valid'] = all(checked[k] == entry['result']['score'][k] for k in (
                    'total_score', 'total_distance_km', 'total_tardiness_seconds')) and checked['valid']
                manifests.append(json.loads((output/'manifest.json').read_text()))
        summary['runs'][policy] = entry
    common = ('data_sha256', 'initial_locations', 'dispatch_step_seconds', 'docking_seconds',
              'loading_seconds_per_quantity', 'unloading_seconds_per_quantity', 'lambda_',
              'safety_horizon_simulation_seconds', 'wall_limit_seconds', 'initial_location_seed',
              'visit_merging', 'execution_time_in_simulation')
    summary['same_simulator_configuration'] = len(manifests) == 2 and all(
        all(m[k] == manifests[0][k] for k in common) for m in manifests)
    summary['source_pins_preserved'] = all(digest(ROOT/p) == sha for p,sha in source_pins.items())
    summary['valid'] = (all(e['valid'] for e in summary['runs'].values())
                        and summary['same_simulator_configuration'] and summary['source_pins_preserved'])
    if summary['valid']:
        summary['gp_over_vnsme_J_ratio'] = (float(summary['runs']['gp']['result']['score']['total_score']) /
                                           float(summary['runs']['vnsme']['result']['score']['total_score']))
    summary['total_wall_seconds'] = perf_counter()-start
    (directory/'comparison.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    rows = ['| Policy | Valid | J | Distance km | Tardiness s | Decision total s | Decision max s |',
            '| --- | --- | ---: | ---: | ---: | ---: | ---: |']
    for name,e in summary['runs'].items():
        r = e.get('result', {})
        s = r.get('score') or {}
        rows.append(f'| {name} | {e["valid"]} | {s.get("total_score")} | {s.get("total_distance_km")} | '
                    f'{s.get("total_tardiness_seconds")} | {r.get("decision_wall_seconds_total")} | '
                    f'{r.get("decision_wall_seconds_max")} |')
    (directory/'comparison.md').write_text('\n'.join(rows)+'\n', encoding='utf-8')
    print('\n'.join(rows))
    return 0 if summary['valid'] else 1


if __name__ == '__main__':
    sys.exit(main())
