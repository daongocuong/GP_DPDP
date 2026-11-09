"""Baseline-only timing calibration, restricted by the locked preparation protocol."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
from time import perf_counter

from dpdp_dataset import ROOT, CASE, resolve_inputs
from lock_dpdp_protocol import load_locked_protocol, authorize_baseline
from prepare_dpdp_data import verify_existing


def write(path, value):
    with Path(path).open('x', encoding='utf-8') as handle:
        json.dump(value, handle, indent=2)


def measure(protocol_path, output, instances):
    protocol = load_locked_protocol(protocol_path)
    authorize_baseline(protocol, instances)
    dataset = (ROOT/protocol['dataset_manifest']).parent
    # Fail closed on checksum/common-CSV mismatch BEFORE any experiment.
    verify_existing(dataset)
    out = Path(output).resolve()
    out.mkdir(parents=True, exist_ok=False)
    write(out/'locked_protocol_reference.json', dict(protocol_path=str(Path(protocol_path).resolve()),
          sha256=hashlib.sha256(Path(protocol_path).read_bytes()).hexdigest(), instances=instances, policy='vnsme'))
    records = []
    for i in instances:
        folder = CASE/'data/instance_1' if i == 1 else dataset/f'benchmark/instance_{i}'
        paths = resolve_inputs(instance_directory=folder)
        run = out/f'instance_{i}_vnsme'
        limit = protocol['calibration_hard_process_deadline_seconds']
        command = [sys.executable,'-B',str(ROOT/'run_dpdp_insertion.py'),'--policy','vnsme',
                   '--instance-directory',str(folder),'--seed',str(protocol['environment_seed']),
                   '--wall-seconds',str(limit),'--output',str(run)]
        start = perf_counter()
        try:
            proc = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=limit+30)
            elapsed = perf_counter()-start
            if not (run/'result.json').exists():
                raise RuntimeError(proc.stderr[-2000:])
            result = json.loads((run/'result.json').read_text(encoding='utf-8'))
            record = dict(instance=i, policy='vnsme', valid=result['valid'] and proc.returncode == 0,
                          process_wall_seconds=elapsed, result=result, directory=str(run))
            if record['valid']:
                raw = subprocess.check_output([sys.executable,'-B',str(ROOT/'verify_dpdp_score.py'),
                    str(run/'simulation.log'),'--orders',str(paths['orders']),'--vehicles',str(paths['vehicles']),
                    '--matrix',str(paths['routes'])], cwd=ROOT, text=True)
                score = json.loads(raw)
                if not score['valid'] or score['total_score'] != result['score']['total_score']:
                    raise RuntimeError('independent CLI scorer disagrees')
                with (run/'independent_score.json').open('x', encoding='utf-8') as handle:
                    handle.write(raw)
        except subprocess.TimeoutExpired:
            record = dict(instance=i, policy='vnsme', valid=False, benchmark_J=None,
                          process_wall_seconds=perf_counter()-start,
                          error=f'hard process deadline {limit}s reached; no complete score')
        records.append(record)
        write(out/f'instance_{i}_summary.json', record)
        result = record.get('result', {})
        print(json.dumps(dict(instance=i, valid=record['valid'], wall=record['process_wall_seconds'],
              max_callback=result.get('decision_wall_seconds_max'), candidates=result.get('candidates_examined'),
              rejected=result.get('candidates_rejected'),
              score={k:result['score'][k] for k in ('total_distance_km','total_tardiness_seconds','total_score')}
                    if result.get('score') else None)), flush=True)
    proposals = {}
    for size, ids, minimum in [('50_orders',[2,6],30), ('100_orders',[9,13],60)]:
        measured = [r['process_wall_seconds'] for r in records if r['instance'] in ids and r['valid']]
        missing = [r['instance'] for r in records if r['instance'] in ids and not r['valid']]
        proposals[size] = dict(successful_baseline_wall_seconds=measured, incomplete_instances=missing,
            proposed_initial_gp_process_deadline_seconds=max(minimum,10*math.ceil(5*max(measured)/10)) if measured and not missing else None,
            rationale='Exploratory 5x maximum measured baseline wall, rounded up to 10s; floor 30s/60s. '
                      'Not a proven GP worst-case bound. Calibrate on train/validation before final test.')
    summary = dict(policy='vnsme', protocol_sha256=hashlib.sha256(Path(protocol_path).read_bytes()).hexdigest(),
                   records=records, rollout_budget_proposals=proposals,
                   gp_runs=0, sealed_test_rollouts=0)
    write(out/'summary.json', summary)
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--protocol', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--instances', type=int, nargs='+', default=[1,2,6,9,13])
    args = parser.parse_args()
    if Path(sys.executable).resolve() != (ROOT/'.venv/Scripts/python.exe').resolve():
        parser.error('use repository venv')
    measure(args.protocol, args.output, args.instances)
