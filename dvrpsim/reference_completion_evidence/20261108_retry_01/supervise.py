"""Sequential reference retries with durable process/epoch diagnostics.

This is an experiment artifact, not a policy or simulator modification.
Only instance 5 then instance 6 are run. Historical files are read-only.
"""
import argparse
from datetime import datetime, timezone, timedelta
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
OUTPUT = ROOT/'migration_runs/reference_retry_20261108_01'
PYTHON = ROOT/'.venv/Scripts/python.exe'
DATA = ROOT/'datasets/xingtian/e4ef3a1c92d19d1d08c3ef0e2156b6fecefdbe04/benchmark'
READY = ROOT/'migration_runs/vnsme_reference_ready/summary.json'
sys.path.insert(0, str(ROOT))
from dpdp_vnsme_reference import independent_score, load_reference
from train_dpdp_gp_multinstance import (load_locked, aggregate_training, validation_key,
                                       DEFAULT_PROTOCOL, DEFAULT_DATASET)
from dpdp_gp import load_tree, tree_hash
from dpdp_gp_fitness import assess_result
from verify_dpdp_score import verify


def now():
    return datetime.now(timezone(timedelta(hours=7))).isoformat()


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    path = Path(path)
    temp = path.with_name(path.name+'.tmp')
    temp.write_text(json.dumps(value, indent=2, ensure_ascii=True, default=str), encoding='utf-8')
    os.replace(temp, path)


def check_pins():
    before = json.loads((HERE/'preflight.json').read_text())
    assert before['compatible']
    assert digest(ROOT/'third_party/vnsme/build_manifest.json') == before['java_build_sha256']
    assert digest(ROOT/'run_dpdp_insertion.py') == before['runner_sha256']
    for path, sha in before['runtime_source_sha256'].items():
        assert digest(ROOT/path) == sha, path
    for instance, old in ((5, ROOT/'migration_runs/vnsme_reference/instance_5'),
                          (6, ROOT/'migration_runs/vnsme_validation6')):
        manifest = json.loads((old/'manifest.json').read_text())
        assert manifest['initial_location_seed'] == 0
        files = [Path(manifest['input_paths'][key]) for key in ('orders','vehicles','factories','routes')]
        assert sorted(digest(p) for p in files) == sorted(manifest['data_sha256'].values())
    return before


def processes(parent):
    # Return only descendants of this specific runner, not unrelated processes.
    script = (f'$rootPid={int(parent)}; $all=@(Get-CimInstance Win32_Process); '
        '$ids=@($rootPid); do { $added=@($all | Where-Object { '
        '$_.ParentProcessId -in $ids -and $_.ProcessId -notin $ids } | '
        'ForEach-Object ProcessId); $ids+= $added } while ($added.Count -gt 0); '
        '$all | Where-Object { $_.ProcessId -in $ids } | Select-Object '
        'ProcessId,ParentProcessId,Name,CommandLine,WorkingSetSize,KernelModeTime,UserModeTime '
        '| ConvertTo-Json -Depth 4 -Compress')
    result = subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',script],
        capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=10,
        creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode:
        return dict(error=result.stderr[-1000:])
    data = json.loads(result.stdout) if result.stdout.strip() else []
    return data if isinstance(data, list) else [data]


def epoch_state(run):
    folder = run/'vnsme/epochs'
    entries = sorted(folder.iterdir()) if folder.exists() else []
    if not entries:
        return dict(last_epoch=None, completed_invocations=0)
    last = entries[-1]
    completed = [p for p in entries if (p/'invocation.json').exists()]
    info = dict(last_epoch=last.name, completed_invocations=len(completed),
                last_epoch_age_seconds=time.time()-last.stat().st_mtime,
                last_epoch_files=sorted(p.name for p in last.iterdir()))
    if completed:
        info['last_completed_invocation'] = json.loads((completed[-1]/'invocation.json').read_text())
    return info


def run_one(instance, java):
    check_pins()
    run = OUTPUT/f'instance_{instance}'
    assert not run.exists()
    command = [str(PYTHON), '-u', str(ROOT/'run_dpdp_insertion.py'), '--policy', 'vnsme',
        '--instance-directory', str(DATA/f'instance_{instance}'), '--output', str(run),
        '--seed', '0', '--java', java, '--wall-seconds', '3600', '--vnsme-epoch-seconds', '600']
    record = dict(instance=instance, run_directory=str(run), command=command, cwd=str(ROOT),
                  started_at=now(), status='RUNNING', valid=False, returncode=None,
                  wall_seconds=3600, epoch_seconds=600, supervisor_deadline_seconds=3630)
    started = time.monotonic()
    last_sample = -30.0
    sampled_epochs = set()
    with (HERE/f'instance_{instance}_process.log').open('x', encoding='utf-8') as log:
        proc = subprocess.Popen(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                                creationflags=subprocess.CREATE_NO_WINDOW)
        record['runner_pid'] = proc.pid
        write(HERE/f'instance_{instance}_supervision.json', record)
        with (HERE/f'instance_{instance}_heartbeats.jsonl').open('x', encoding='utf-8') as beats:
            while proc.poll() is None:
                elapsed = time.monotonic()-started
                beat = dict(observed_at=now(), elapsed_seconds=elapsed,
                            runner_pid=proc.pid, runner_alive=True)
                try:
                    beat.update(epoch_state(run))
                    if elapsed-last_sample >= 30:
                        beat['processes'] = processes(proc.pid)
                        last_sample = elapsed
                        if beat.get('last_epoch_age_seconds', 0) > 90 and isinstance(beat['processes'], list):
                            for process in beat['processes']:
                                if process['Name'].lower() == 'java.exe' and beat['last_epoch'] not in sampled_epochs:
                                    sampled_epochs.add(beat['last_epoch'])
                                    pid = process['ProcessId']
                                    trace = subprocess.run([str(Path(java).with_name('jcmd.exe')), str(pid),
                                        'Thread.print', '-l'], capture_output=True, timeout=10)
                                    (HERE/f'instance_{instance}_epoch_{beat["last_epoch"]}_threads.txt').write_bytes(
                                        trace.stdout+b'\nSTDERR\n'+trace.stderr)
                except Exception as exc:
                    beat['diagnostic_error'] = f'{type(exc).__name__}: {exc}'
                beats.write(json.dumps(beat, default=str)+'\n')
                beats.flush()
                write(HERE/'heartbeat.json', dict(phase=f'instance_{instance}', **beat))
                if elapsed > 3630:
                    killed = subprocess.run(['taskkill','/PID',str(proc.pid),'/T','/F'], capture_output=True)
                    (HERE/f'instance_{instance}_deadline_kill.txt').write_bytes(killed.stdout+killed.stderr)
                    record['status'] = 'PROCESS_TIMEOUT'
                    break
                time.sleep(10)
        try:
            record['returncode'] = proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            record['status'] = 'TERMINATION_FAILED'
    record.update(ended_at=now(), elapsed_seconds=time.monotonic()-started, **epoch_state(run))
    if record['returncode'] == 0:
        try:
            score = independent_score(run, DEFAULT_DATASET, instance)
            write(run/'retry_independent_score.json', score)
            record.update(status='COMPLETE', valid=True, score=score)
        except Exception as exc:
            record.update(status='INVALID', error=f'{type(exc).__name__}: {exc}')
    elif record['status'] == 'RUNNING':
        record['status'] = 'FAILED'
    if (run/'result.json').exists():
        record['runner_result'] = json.loads((run/'result.json').read_text())
    write(HERE/f'instance_{instance}_supervision.json', record)
    return record


def assemble_and_assess():
    assert not READY.parent.exists(), 'Ready reference target no longer empty; refusing overwrite'
    runs = [ROOT/f'migration_runs/vnsme_reference/instance_{i}' for i in (2,3,4)]
    runs += [OUTPUT/f'instance_{i}' for i in (5,6)]
    command = [str(PYTHON), str(ROOT/'dpdp_vnsme_reference.py'), '--adopt-runs', *map(str,runs),
               '--output', str(READY.parent)]
    with (HERE/'adopt_process.log').open('x', encoding='utf-8') as log:
        result = subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, timeout=180,
                                creationflags=subprocess.CREATE_NO_WINDOW)
    write(HERE/'adopt_invocation.json', dict(command=command, returncode=result.returncode))
    assert result.returncode == 0, 'Adoption failed; see adopt_process.log'
    _, ph, mh, _, train, validation = load_locked(DEFAULT_PROTOCOL, DEFAULT_DATASET)
    scores, payload = load_reference(READY, train+validation, ph, mh, DEFAULT_DATASET)
    fixed_path = ROOT/'gp_runs/multinstance_50_20261105/main/selected_tree.json'
    tree, _ = load_tree(fixed_path)
    stored = json.loads((ROOT/'migration_runs/frozen_gp_check/raw_scores.json').read_text())
    records = stored['records']
    assert {r['instance'] for r in records} == set(train+validation)
    for record in records:
        assert record['valid'] and record['tree_sha256'] == tree_hash(tree)
        run = Path(record['run_directory'])
        assert digest(run/'simulation.log') == record['log_sha256']
        manifest = json.loads((run/'manifest.json').read_text())
        result = json.loads((run/'result.json').read_text())
        paths = manifest['input_paths']
        actual = verify(run/'simulation.log', paths['orders'], paths['vehicles'], paths['routes'])
        assert assess_result(result, actual) == float(record['benchmark_J'])
        assert str(actual['total_score']) == record['benchmark_J']
    aggregate = aggregate_training([r for r in records if r['instance'] in train], scores)
    assert aggregate['valid']
    val = next(r for r in records if r['instance'] == validation[0])
    key = validation_key(dict(val, baseline_J=scores[validation[0]]), aggregate['fitness'], tree)
    evaluation = dict(loader_pass=True, summary=str(READY), summary_sha256=digest(READY),
        vnsme_scores=scores, gp_scores={r['instance']:r['benchmark_J'] for r in records},
        tree_file=str(fixed_path), tree_file_sha256=digest(fixed_path), tree_sha256=tree_hash(tree),
        train=aggregate, validation_ratio=key[0], gp_evolution_performed=False,
        numerator_source='stored fixed-tree J; log hashes and independent scorer reverified',
        final_test_rollouts=[])
    write(HERE/'fitness_v2_verification.json', evaluation)
    return evaluation


def preservation():
    before = json.loads((HERE/'historical_sha256_before.json').read_text())
    changed = [path for path, sha in before.items()
               if not (ROOT/path).is_file() or digest(ROOT/path) != sha]
    result = dict(files_checked=len(before), unchanged=not changed, changed=changed)
    write(HERE/'historical_preservation.json', result)
    assert not changed, 'Historical artifacts changed'
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    check_pins()
    if args.check:
        print('Supervisor configuration and runtime pins PASS')
        return
    assert Path(sys.executable).resolve() == PYTHON.resolve()
    assert not OUTPUT.exists()
    OUTPUT.mkdir(parents=True)
    status = dict(supervisor_pid=os.getpid(), started_at=now(), status='RUNNING', runs=[],
                  supervisor_sha256=digest(Path(__file__)), scope='references only; 5 then 6')
    write(HERE/'supervisor_status.json', status)
    try:
        java = json.loads((ROOT/'migration_runs/vnsme_reference/instance_2/vnsme/session.json').read_text())['command'][0]
        for instance in (5,6):
            record = run_one(instance, java)
            status['runs'].append(record)
            write(HERE/'supervisor_status.json', status)
        if all(r['valid'] for r in status['runs']):
            status['evaluation'] = assemble_and_assess()
            status['status'] = 'COMPLETE'
        else:
            status['status'] = 'REFERENCE_FAILURE'
    except BaseException as exc:
        status.update(status='FAILED', error=f'{type(exc).__name__}: {exc}', traceback=traceback.format_exc())
    finally:
        try:
            status['historical_preservation'] = preservation()
        except Exception as exc:
            status.update(status='FAILED', preservation_error=str(exc))
        status['ended_at'] = now()
        write(HERE/'supervisor_status.json', status)


if __name__ == '__main__':
    main()
