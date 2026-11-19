"""Prepare and manually launch bounded instance-35 technical smoke stages.

Importing this module never launches a workload. Smoke stages are diagnostic
and partial; they never produce an objective value.
"""
import argparse
import csv
import json
import math
import os
from pathlib import Path
import sys
import time

import instance35_temporal as protocol
from dpdp_gp import Node, save_tree
from dpdp_v3_supervisor import supervise

LIMITS = dict(decision_points=5, decision_hard_seconds=20,
              stage_wall_seconds=120, full_rollout_guard_seconds=1800,
              simulation_time_slot_seconds=600)
GP_PILOT_LIMITS = dict(decision_points=8, decision_hard_seconds=60,
                       stage_wall_seconds=300, runner_wall_guard_seconds=360)
GP_EXTENDED_PILOT_LIMITS = dict(decision_points=12, decision_hard_seconds=60,
                                stage_wall_seconds=360, runner_wall_guard_seconds=420)


def applied_stage_config(decision_timeout_seconds=None, algorithm='gp'):
    """Return the effective config; timeout overrides are diagnostics, capped at 60s."""
    overrides = {}
    if decision_timeout_seconds is not None:
        decision_timeout = float(decision_timeout_seconds)
        if (not math.isfinite(decision_timeout)
                or not LIMITS['decision_hard_seconds'] <= decision_timeout <= 60):
            raise ValueError('decision-5 diagnostic timeout must be between 20 and 60 seconds')
        overrides = {'5': decision_timeout}
    if algorithm not in ('gp', 'vnsme'):
        raise ValueError(f'unsupported smoke algorithm: {algorithm}')
    config = dict(stage=f'instance35_{algorithm}_operational_smoke', algorithm=algorithm, partition='train',
        max_decision_points=LIMITS['decision_points'],
        decision_hard_timeout_seconds=LIMITS['decision_hard_seconds'],
        decision_timeout_overrides_seconds=overrides,
        stage_wall_timeout_seconds=LIMITS['stage_wall_seconds'],
        runner_wall_guard_seconds=(LIMITS['full_rollout_guard_seconds'] if algorithm == 'gp'
                                   else LIMITS['stage_wall_seconds']),
        simulation_time_slot_seconds=LIMITS['simulation_time_slot_seconds'],
        decision_timeout_origin='supervisor_receives_START_marker',
        stage_timeout_origin='controller_smoke_invocation',
        objective_policy='partial smoke; J and score are null')
    if algorithm == 'vnsme':
        config.update(internal_search_budget_seconds=10,
                      subprocess_hard_timeout_seconds=18,
                      timeout_semantics='Java cooperative search budget; separate subprocess and supervisor hard limits')
    return config


def protocol_metadata(dataset_report):
    """Separate stale inspection proposals from limits actually used by the stage."""
    dataset = dict(dataset_report)
    legacy = dataset.pop('timeout_config', None)
    if legacy is not None:
        dataset['inspection_reference_timeouts_not_applied'] = legacy
    return dict(dataset=dataset, applied_stage_config=applied_stage_config(),
        split_semantics='three independent rollouts; fleet reset at each partition; no carry-over')


def gp_pilot_stage_config(feasibility_profile_enabled=True, decision_cap=8):
    if type(decision_cap) is not int or decision_cap not in (8, 12):
        raise ValueError('GP pilot decision cap must be 8 or 12')
    limits = GP_PILOT_LIMITS if decision_cap == 8 else GP_EXTENDED_PILOT_LIMITS
    if limits['runner_wall_guard_seconds'] <= limits['stage_wall_seconds']:
        raise ValueError('runner wall guard must exceed the supervisor stage deadline')
    return dict(stage='instance35_gp_performance_pilot', algorithm='gp', partition='train',
        max_decision_points=limits['decision_points'],
        decision_hard_timeout_seconds=limits['decision_hard_seconds'],
        stage_wall_timeout_seconds=limits['stage_wall_seconds'],
        runner_wall_guard_seconds=limits['runner_wall_guard_seconds'],
        simulation_time_slot_seconds=LIMITS['simulation_time_slot_seconds'],
        feasibility_profile_enabled=bool(feasibility_profile_enabled),
        decision_progress_enabled=decision_cap == 12,
        objective_policy='partial performance diagnostic; J and score are null')


def is_clean_gp_pilot(outcome, events, runner_result, decision_cap):
    """Accept only an exact, guarded partial run with no timeout or routing error."""
    if type(decision_cap) is not int or decision_cap not in (8, 12):
        return False
    starts, ends = [], []
    active = None
    progress = None
    for event in events:
        if event.get('algorithm') != 'gp' or event.get('partition') != 'train':
            return False
        kind = event.get('event')
        index = event.get('decision_index')
        if kind == 'START':
            if active is not None or index != len(ends)+1 or index > decision_cap:
                return False
            active = index
            progress = None
            starts.append(index)
        elif kind == 'PROGRESS':
            if active is None or index != active:
                return False
            current = tuple(event.get(k) for k in (
                'candidate_count', 'feasible_count', 'rejected_count',
                'groups_total', 'groups_processed'))
            if any(type(v) is not int or v < 0 for v in current):
                return False
            if progress is not None and any(a < b for a, b in zip(current, progress)):
                return False
            progress = current
        elif kind == 'END':
            if active is None or index != active or event.get('status') != 'completed' \
                    or event.get('completed_decisions') != index:
                return False
            elapsed = event.get('decision_elapsed_seconds')
            profile = event.get('profile')
            if not isinstance(elapsed, (int, float)) or elapsed < 0 or not isinstance(profile, dict):
                return False
            final = tuple(profile.get(k) for k in (
                'examined', 'feasible', 'rejected', 'groups_total', 'groups_processed'))
            if any(type(v) is not int or v < 0 for v in final):
                return False
            if progress is not None and any(a < b for a, b in zip(final, progress)):
                return False
            ends.append(index)
            active = None
            progress = None
        else:
            return False
    expected = list(range(1, decision_cap+1))
    return (active is None and starts == ends == expected
        and outcome.get('state') == 'EXITED' and outcome.get('exit_code') == 0
        and outcome.get('valid_supervision') is True and outcome.get('remaining_job_processes') == []
        and runner_result is not None and runner_result.get('status') == 'SMOKE_COMPLETED'
        and runner_result.get('partial') is True and runner_result.get('score') is None
        and runner_result.get('J') is None
        and runner_result.get('decision_count') == decision_cap)


def is_clean_smoke(outcome, events, runner_result, algorithm='gp'):
    """Require the runner, ordered decision trace and Job Object to agree on a 5-step partial run."""
    expected = []
    for index in range(1, LIMITS['decision_points'] + 1):
        expected.extend(('START', 'END'))
    if len(events) != len(expected):
        return False
    for position, (event, kind) in enumerate(zip(events, expected)):
        index = position // 2 + 1
        if (event.get('event') != kind or event.get('decision_index') != index
                or event.get('algorithm') != algorithm or event.get('partition') != 'train'):
            return False
        if kind == 'END' and (event.get('status') != 'completed'
                or event.get('completed_decisions') != index):
            return False
    return (outcome.get('state') == 'EXITED' and outcome.get('exit_code') == 0
        and outcome.get('valid_supervision') is True
        and outcome.get('remaining_job_processes') == []
        and runner_result is not None
        and runner_result.get('status') == 'SMOKE_COMPLETED'
        and runner_result.get('valid') is False
        and runner_result.get('partial') is True
        and runner_result.get('score') is None
        and runner_result.get('J') is None
        and runner_result.get('decision_count') == LIMITS['decision_points'])


def prepare():
    """Create a fresh immutable three-partition input snapshot; no rollout."""
    report = protocol.preflight()
    if protocol.RUN.exists():
        raise FileExistsError(f'preserving existing experiment directory: {protocol.RUN}')
    source_path, vehicle_path, _, _ = protocol.source_files()
    source = protocol.rows(source_path, 'order')
    releases = [protocol.seconds(row['creation_time']) for row in source]
    low, high = min(releases), max(releases)
    cut1, cut2 = low + (high-low)*.60, low + (high-low)*.80
    buckets = {'train': [], 'validation': [], 'test': []}
    for row, released in zip(source, releases):
        name = 'train' if released < cut1 else 'validation' if released < cut2 else 'test'
        buckets[name].append(row)

    # Build under a unique directory and never modify any previous run/evidence.
    protocol.RUN.mkdir(parents=True, exist_ok=False)
    try:
        data = protocol.RUN/'data'
        data.mkdir()
        for name, items in buckets.items():
            folder = data/name
            folder.mkdir()
            with (folder/'orders.csv').open('x', encoding='utf-8', newline='') as handle:
                writer = csv.DictWriter(handle, fieldnames=list(source[0]))
                writer.writeheader()
                writer.writerows(items)
            (folder/'vehicle_info_50.csv').write_bytes(vehicle_path.read_bytes())
        summary = protocol_metadata(report)
        summary['partitions'] = {name: len(items) for name, items in buckets.items()}
        (protocol.RUN/'protocol.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
        return summary
    except BaseException:
        # Leave partial evidence visible for diagnosis; never recursively remove it.
        raise


def run_smoke(algorithm, run_id, decision_timeout_seconds=None):
    stage_started = time.monotonic()
    if sys.platform != 'win32':
        raise RuntimeError('native Windows Job Object supervision is required')
    expected_python = protocol.ROOT/'.venv/Scripts/python.exe'
    if Path(sys.executable).resolve() != expected_python.resolve():
        raise RuntimeError(f'use repository interpreter: {expected_python}')
    if algorithm not in ('gp', 'vnsme'):
        raise ValueError(f'unsupported algorithm: {algorithm}')
    if not run_id or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for c in run_id):
        raise ValueError('run-id may contain only letters, digits, underscore and hyphen')
    if algorithm == 'vnsme' and decision_timeout_seconds is not None:
        raise ValueError('decision-5 override is only supported for GP diagnostic smoke')
    stage_config = applied_stage_config(decision_timeout_seconds, algorithm=algorithm)

    partition = 'train'
    input_dir = protocol.RUN/'data'/partition
    if not input_dir.is_dir():
        raise FileNotFoundError(f'run prepare first: {input_dir}')
    output = protocol.RUN/'smoke'/algorithm/run_id
    output.mkdir(parents=True, exist_ok=False)
    run_dir = output/'runner'
    trace = output/'stage_trace.jsonl'
    # Pre-create the trace so absence before decision 1 is an empty valid stream.
    trace.open('x', encoding='utf-8').close()
    supervisor_dir = output/'supervisor'
    tree = output/'known_tree.json'
    save_tree(tree, Node('feature', 'delta_distance_km'))
    with (output/'smoke_config.json').open('x', encoding='utf-8') as handle:
        json.dump(stage_config, handle, indent=2)
        handle.flush()
        os.fsync(handle.fileno())

    command = [str(expected_python), '-B', str(protocol.ROOT/'run_dpdp_insertion.py'),
        '--policy', algorithm, '--contract-version', 'dpdp-execution-commitment-v3',
        '--instance-directory', str(input_dir), '--data-directory', str(protocol.BENCHMARK),
        '--seed', '0', '--wall-seconds', str(stage_config['runner_wall_guard_seconds']),
        '--max-simulation-seconds', '604800', '--output', str(run_dir),
        '--max-decision-points', str(LIMITS['decision_points']), '--stage-trace', str(trace),
        '--stage-partition', partition]
    if algorithm == 'gp':
        command += ['--tree', str(tree)]
    else:
        command += ['--vnsme-search-budget-seconds', str(stage_config['internal_search_budget_seconds']),
                    '--vnsme-epoch-seconds', str(stage_config['subprocess_hard_timeout_seconds'])]
    supervision_error = None
    try:
        outcome = supervise(command, supervisor_dir, LIMITS['stage_wall_seconds'],
            interval=.05, gap_limit=3, decision_trace=trace,
            decision_timeout=stage_config['decision_hard_timeout_seconds'],
            decision_timeout_overrides=stage_config['decision_timeout_overrides_seconds'],
            partition=partition,
            algorithm=algorithm, stage_started_monotonic=stage_started)
    except BaseException as exc:
        outcome = {'state': 'SUPERVISOR_ERROR', 'valid_supervision': False,
                   'exit_code': None, 'stop_event': None}
        supervision_error = f'{type(exc).__name__}: {exc}'

    events = []
    if trace.exists():
        for number, line in enumerate(trace.read_text(encoding='utf-8').splitlines(), 1):
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                events.append({'event': 'TRACE_PARSE_ERROR', 'line': number})
    completed = sum(e.get('event') == 'END' for e in events)
    runner_result = None
    result_path = run_dir/'result.json'
    if result_path.is_file():
        try:
            runner_result = json.loads(result_path.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError):
            runner_result = None
    clean_smoke = is_clean_smoke(outcome, events, runner_result, algorithm=algorithm)
    status = ('SMOKE_COMPLETED' if clean_smoke else
              'INVALID' if outcome.get('state') == 'EXITED' and outcome.get('exit_code') == 0 else
              'ERROR' if outcome.get('state') == 'EXITED' and outcome.get('exit_code') != 0 else
              outcome.get('state', 'ERROR'))
    stage_result = dict(status=status, applied_stage_config=stage_config,
        partial=True, score=None, J=None,
        completed_decisions=completed, stop_event=outcome.get('stop_event'),
        supervisor_state=outcome.get('state'), valid_supervision=outcome.get('valid_supervision', False),
        supervision_error=supervision_error,
        runner_error=(runner_result.get('error') if runner_result else None),
        invalid_reason=('runner exited without the required five guarded decisions' if status == 'INVALID' else None),
        note='Operational partial smoke only; no final objective is computed or comparable.')
    with (output/'stage_result.json').open('x', encoding='utf-8') as handle:
        json.dump(stage_result, handle, indent=2)
        handle.flush()
        os.fsync(handle.fileno())
    return stage_result


def run_gp_pilot(run_id, feasibility_profile_enabled=True, decision_cap=8):
    """Run a manually invoked, bounded GP performance diagnostic; never scores partial work."""
    stage_started = time.monotonic()
    if sys.platform != 'win32':
        raise RuntimeError('native Windows Job Object supervision is required')
    expected_python = protocol.ROOT/'.venv/Scripts/python.exe'
    if Path(sys.executable).resolve() != expected_python.resolve():
        raise RuntimeError(f'use repository interpreter: {expected_python}')
    if not run_id or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for c in run_id):
        raise ValueError('run-id may contain only letters, digits, underscore and hyphen')
    input_dir = protocol.RUN/'data'/'train'
    if not input_dir.is_dir():
        raise FileNotFoundError(f'run prepare first: {input_dir}')
    output = protocol.RUN/'pilot'/'gp'/run_id
    output.mkdir(parents=True, exist_ok=False)
    runner_dir, trace, supervisor_dir = output/'runner', output/'stage_trace.jsonl', output/'supervisor'
    trace.open('x', encoding='utf-8').close()
    tree = output/'known_tree.json'
    save_tree(tree, Node('feature', 'delta_distance_km'))
    config = gp_pilot_stage_config(feasibility_profile_enabled, decision_cap)
    with (output/'pilot_config.json').open('x', encoding='utf-8') as handle:
        json.dump(config, handle, indent=2)
        handle.flush()
        os.fsync(handle.fileno())
    command = [str(expected_python), '-B', str(protocol.ROOT/'run_dpdp_insertion.py'),
        '--policy', 'gp', '--contract-version', 'dpdp-execution-commitment-v3',
        '--instance-directory', str(input_dir), '--data-directory', str(protocol.BENCHMARK),
        '--seed', '0', '--wall-seconds', str(config['runner_wall_guard_seconds']),
        '--max-simulation-seconds', '604800', '--output', str(runner_dir),
        '--max-decision-points', str(config['max_decision_points']), '--stage-trace', str(trace),
        '--stage-partition', 'train', '--tree', str(tree)]
    if not config['feasibility_profile_enabled']:
        command.append('--no-feasibility-profile')
    if config['decision_progress_enabled']:
        command.append('--decision-progress')
    try:
        outcome = supervise(command, supervisor_dir, config['stage_wall_timeout_seconds'],
            interval=.05, gap_limit=3, decision_trace=trace,
            decision_timeout=config['decision_hard_timeout_seconds'], partition='train',
            algorithm='gp', stage_started_monotonic=stage_started)
        supervision_error = None
    except BaseException as exc:
        outcome = {'state': 'SUPERVISOR_ERROR', 'valid_supervision': False, 'exit_code': None,
                   'stop_event': None, 'remaining_job_processes': None}
        supervision_error = f'{type(exc).__name__}: {exc}'
    events = []
    if trace.exists():
        for number, line in enumerate(trace.read_text(encoding='utf-8').splitlines(), 1):
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                events.append({'event': 'TRACE_PARSE_ERROR', 'line': number})
    completed = sum(e.get('event') == 'END' and e.get('status') == 'completed' for e in events)
    starts = [e for e in events if e.get('event') == 'START']
    ends = [e for e in events if e.get('event') == 'END']
    timed_out = any(e.get('event') == 'TIMEOUT' for e in events) or outcome.get('state') == 'TIMEOUT'
    runner_result = None
    result_path = runner_dir/'result.json'
    if result_path.is_file():
        try:
            runner_result = json.loads(result_path.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError):
            pass
    clean = (not timed_out and is_clean_gp_pilot(
        outcome, events, runner_result, config['max_decision_points']))
    status = 'PILOT_PARTIAL_COMPLETED' if clean else 'TIMEOUT' if timed_out else 'INVALID'
    result = dict(status=status, applied_stage_config=config, partial=True, score=None, J=None,
        completed_decisions=completed, active_decision=(starts[-1].get('decision_index')
            if starts and (not ends or starts[-1].get('decision_index') > ends[-1].get('decision_index')) else None),
        stop_event=outcome.get('stop_event'), supervisor_state=outcome.get('state'),
        valid_supervision=outcome.get('valid_supervision', False),
        remaining_job_processes=outcome.get('remaining_job_processes'), supervision_error=supervision_error,
        note='Partial performance diagnostic only; no final objective is computed or comparable.')
    with (output/'pilot_result.json').open('x', encoding='utf-8') as handle:
        json.dump(result, handle, indent=2)
        handle.flush()
        os.fsync(handle.fileno())
    return result


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='action', required=True)
    sub.add_parser('prepare')
    smoke = sub.add_parser('smoke')
    smoke.add_argument('--algorithm', choices=('gp', 'vnsme'), required=True)
    smoke.add_argument('--run-id', required=True)
    smoke.add_argument('--decision-5-timeout-seconds', type=float,
        help='diagnostic only: override decision 5 from 20 seconds, maximum 60; stage remains capped at 120 seconds')
    pilot = sub.add_parser('pilot')
    pilot.add_argument('--algorithm', choices=('gp',), required=True)
    pilot.add_argument('--run-id', required=True)
    pilot.add_argument('--decision-cap', choices=(8, 12), type=int, default=8,
        help='8-decision repeat or bounded 12-decision extended pilot')
    pilot.add_argument('--no-feasibility-profile', action='store_false',
        dest='feasibility_profile_enabled', default=True,
        help='disable detailed feasibility timers to measure lower-overhead decision runtime')
    args = parser.parse_args()
    result = (prepare() if args.action == 'prepare' else
              run_smoke(args.algorithm, args.run_id, args.decision_5_timeout_seconds)
              if args.action == 'smoke' else
              run_gp_pilot(args.run_id, args.feasibility_profile_enabled, args.decision_cap))
    print(json.dumps(result, indent=2, default=str))


if __name__ == '__main__':
    main()
