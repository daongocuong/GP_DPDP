"""Run GP, VNSME or the upstream demo with isolated artifacts and manifest.

Uses the repository venv. Output directory must not exist. No old file writes.
The independent score verifier is called only on completed, guarded runs.
"""
import argparse
from dataclasses import replace
from datetime import datetime, timezone, timedelta
import hashlib
import importlib.metadata
import json
import logging
from pathlib import Path
import subprocess
import sys
from time import perf_counter
import traceback
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
CASE = ROOT / 'examples/case_studies/dpdp'
sys.path.insert(0, str(ROOT/'src'))
sys.path.insert(0, str(CASE))
import dpdp_main
from dpdp_problemdata import read_dpdp_problem
from dpdp_routing import dpdp_module_routing, get_dpdp_state
from dvrpsim.utils.logging import DefaultLoggingCallback
from dpdp_feasibility import Plan, Visit
from dpdp_insertion import InsertionPolicy, Snapshot, FEATURE_UNITS
from verify_dpdp_score import verify
from dpdp_dataset import resolve_inputs
from dpdp_contract import (LEGACY_CONTRACT, EXECUTION_CONTRACT, CONTRACT_VERSIONS,
                           ExecutionCommitment, contract_metadata, plans_from_raw)


# Ghi chú: Tính SHA-256 của nội dung file để ghi nhận chính xác phiên bản source hoặc dữ liệu.
def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# Ghi chú: Ghi JSON vào file mới; chế độ x ngăn ghi đè artifact đã tồn tại.
def dump(path, value):
    with Path(path).open('x', encoding='utf-8') as handle:
        json.dump(value, handle, indent=2, default=str)


def git_stdout(*args):
    """Capture Git provenance as bytes and decode UTF-8 without locale loss."""
    command = ['git', '-C', str(ROOT), *args]
    raw = subprocess.check_output(command)
    try:
        return raw.decode('utf-8')
    except UnicodeDecodeError as exc:
        raise ValueError(f"Git {' '.join(args)} returned non-UTF-8 stdout at byte {exc.start}") from exc


class RunLog(DefaultLoggingCallback):
    # Ghi chú: Tạo logger riêng cho rollout và lưu simulation.log để scorer có thể kiểm tra lại.
    def _configure_logger(self):
        self.logger = logging.Logger(f'dpdp-run-{self.model.run_dir}', logging.DEBUG)
        self.logger.propagate = False
        handler = logging.FileHandler(self.model.run_dir / 'simulation.log', mode='x', encoding='utf-8')
        handler.setFormatter(logging.Formatter('%(levelname)-8s: %(message)s'))
        self.logger.addHandler(handler)

    # Default logger suppresses zero-distance same-factory transitions. Preserve
    # all logical visits in NEW logs so the independent verifier can locate
    # every actual arrival, including a separate visit at the same factory.
    # Ghi chú: Ghi mọi lần rời nhà máy, kể cả chặng cùng nhà máy, để giữ đầy đủ visit trong log.
    def on_departure(self, vehicle):
        self.logger.info(f'{self._prefix} {vehicle} | departed from {vehicle.previous_location} to {vehicle.next_location}')

    # Ghi chú: Ghi thời điểm xe đến nhà máy làm căn cứ đối chiếu hành trình và thời điểm giao hàng.
    def on_arrival(self, vehicle):
        self.logger.info(f'{self._prefix} {vehicle} | arrived at {vehicle.current_location}')


# Ghi chú: Đổi decision thành kế hoạch, kiểm tra khả thi rồi ghi cam kết V3 và trace trước khi simulator thực thi.
def guard_raw_decision(model, raw):
    snapshot = Snapshot.observe(model)
    plans = plans_from_raw(snapshot, raw)
    admitted = snapshot.admitted(plans)
    newly_accepted = {i for i, value in raw['orders'].items() if value['status'] == 'accepted'}
    if not newly_accepted <= admitted:
        raise ValueError('accepted item missing from route')
    snapshot.check(plans, admitted)
    contract = getattr(model, 'commitment_contract', None)
    if contract is not None:
        contract.record(snapshot, raw, plans)
    writer = getattr(model, 'audit_trace_writer', None)
    if writer is not None:
        writer.decision(snapshot, raw, plans)
    return plans


class RunModel(dpdp_main.DPDPModel):
    # Ghi chú: Chọn policy GP/VNSME/demo và contract; GP dùng cây xếp hạng, VNSME dùng adapter gọi Java.
    def __init__(self, mode, run_dir, tree_path=None, vnsme_config=None,
                 contract_version=LEGACY_CONTRACT, profile_feasibility=True,
                 decision_progress=False):
        if mode not in ('gp', 'vnsme', 'demo'):
            raise ValueError(f'unsupported policy: {mode}')
        self.mode, self.run_dir = mode, run_dir
        contract_metadata(contract_version)
        if contract_version == EXECUTION_CONTRACT and mode not in ('gp', 'vnsme'):
            raise ValueError('execution commitment contract requires gp or vnsme')
        self.contract_version = contract_version
        self.commitment_contract = ExecutionCommitment() if contract_version == EXECUTION_CONTRACT else None
        self.audit_trace_writer = None
        if contract_version == EXECUTION_CONTRACT:
            from dpdp_v3_trace import TraceWriter
            self.audit_trace_writer = TraceWriter(run_dir/'decision_trace.jsonl')
        self.ranker = None
        if mode == 'gp':
            from dpdp_gp import TreeRanker, load_tree
            tree, _ = load_tree(tree_path)
            self.ranker = TreeRanker(tree)
        self.policy = InsertionPolicy(self.ranker, profile_feasibility=profile_feasibility,
            progress_callback=self.write_decision_progress if decision_progress else None) if mode == 'gp' else None
        if mode == 'vnsme':
            from baselines.vnsme import VNSMEPolicy
            self.policy = VNSMEPolicy(run_dir/'vnsme', contract=self.commitment_contract, **vnsme_config)
        self.wall_deadline = None
        self.decision_times = []
        self.smoke_stop_requested = False
        super().__init__()

    def write_decision_progress(self, stats):
        """Persist sparse workload counters for a supervised extended pilot."""
        if not getattr(self, 'stage_trace_path', None):
            return
        started = getattr(self, 'active_decision_started', None)
        append_stage_trace(self.stage_trace_path, dict(schema='dpdp-smoke-decision-v1',
            event='PROGRESS', algorithm=self.mode, partition=self.stage_partition,
            decision_index=len(self.decision_times)+1, simulation_seconds=self.env.now,
            decision_elapsed_seconds=(perf_counter()-started if started is not None else None),
            elapsed_wall_seconds=perf_counter()-self.stage_started,
            candidate_count=stats.get('examined', 0), feasible_count=stats.get('feasible', 0),
            rejected_count=stats.get('rejected', 0), groups_total=stats.get('groups_total', 0),
            groups_processed=stats.get('groups_processed', 0)))

    # Ghi chú: Gắn logger của rollout thay cho logger mặc định của model.
    def _init_logger(self):
        self.log = RunLog(self)

    # Ghi chú: Tạo thư mục trao đổi dữ liệu bên trong output riêng của rollout.
    def init(self):
        (self.run_dir / 'interaction').mkdir()


    # Ghi chú: Tại mỗi kỳ định tuyến: gọi policy, kiểm decision qua guard và đo thời gian tính toán thực.
    def routing_callback(self):
        start = perf_counter()
        decision_index = len(self.decision_times) + 1
        self.active_decision_started = start
        decision_started_utc = datetime.now(timezone.utc).isoformat()
        if getattr(self, 'stage_trace_path', None):
            append_stage_trace(self.stage_trace_path, dict(schema='dpdp-smoke-decision-v1',event='START', algorithm=self.mode,
                partition=self.stage_partition, decision_index=decision_index,
                simulation_seconds=self.env.now, wall_started_utc=decision_started_utc,
                elapsed_wall_seconds=perf_counter()-self.stage_started))
        try:
            if self.mode == 'vnsme':
                raw = self.policy.decide(self, remaining=self.wall_deadline-perf_counter())
            elif self.mode == 'gp':
                raw = self.policy.decide(self)
            else:
                directory = self.run_dir / 'interaction'
                vehicle, ongoing, unallocated, destination, route = [str(directory / name) for name in (
                    'vehicle_info.json', 'ongoing_order_items.json', 'unallocated_order_items.json',
                    'output_destination.json', 'output_route.json')]
                raw = dpdp_module_routing(self, get_dpdp_state(self), vehicle, unallocated, ongoing,
                                         destination, route, 'routing.demo_algorithm', 'routing',
                                         vehicle, ongoing, unallocated, destination, route)
            guard_raw_decision(self, raw)
        except BaseException as exc:
            if getattr(self, 'stage_trace_path', None):
                append_stage_trace(self.stage_trace_path, dict(schema='dpdp-smoke-decision-v1',event='ERROR',
                    algorithm=self.mode,partition=self.stage_partition,decision_index=decision_index,
                    simulation_seconds=self.env.now,wall_started_utc=decision_started_utc,
                    elapsed_wall_seconds=perf_counter()-self.stage_started,status='error',
                    completed_decisions=len(self.decision_times),stop_reason=f'{type(exc).__name__}: {exc}'))
            self.active_decision_started = None
            raise
        wall_seconds=perf_counter()-start
        self.decision_times.append(dict(simulation_seconds=self.env.now,
                                        wall_seconds=wall_seconds, guard_passed=True))
        if getattr(self, 'stage_trace_path', None):
            profile = None
            policy_decisions = getattr(self.policy, 'decisions', None)
            if self.mode == 'gp' and policy_decisions:
                profile = insertion_profile_payload(policy_decisions[-1])
            append_stage_trace(self.stage_trace_path, dict(schema='dpdp-smoke-decision-v1',event='END', algorithm=self.mode,
                partition=self.stage_partition, decision_index=decision_index,
                simulation_seconds=self.env.now, wall_started_utc=decision_started_utc,
                wall_ended_utc=datetime.now(timezone.utc).isoformat(), decision_elapsed_seconds=wall_seconds,
                elapsed_wall_seconds=perf_counter()-self.stage_started, status='completed',
                completed_decisions=len(self.decision_times), stop_reason=None, profile=profile))
        self.active_decision_started = None
        if getattr(self, 'max_decision_points', None) == len(self.decision_times):
            # Do not raise inside routing_callback: dvrpsim wraps callback
            # exceptions as RoutingError. Let the simulator accept this
            # guarded decision, then stop from the outer event loop.
            self.smoke_stop_requested = True
        return raw


def insertion_profile_payload(decision_stats):
    """Build a trace profile with disjoint validator phases and explicit nested timers."""
    profile_fields = ('groups_total', 'groups_processed', 'groups_already_admitted',
        'examined', 'feasible', 'rejected', 'scored', 'grouping_seconds',
        'candidate_enumeration_seconds', 'route_copy_seconds',
        'feasibility_wall_seconds', 'schedule_prediction_seconds',
        'metric_accounting_seconds', 'forecast_wall_seconds',
        'feature_extraction_seconds', 'gp_scoring_seconds',
        'route_update_seconds', 'snapshot_wall_seconds', 'wall_seconds',
        'feasibility_profile_enabled')
    profile = {key: decision_stats[key] for key in profile_fields if key in decision_stats}
    profile['groups_assigned'] = len(decision_stats.get('chosen', ()))
    profile['groups_deferred'] = len(decision_stats.get('deferred', ()))
    profile_enabled = decision_stats.get('feasibility_profile_enabled',
        'feasibility_validator_total_seconds' in decision_stats)
    profile['feasibility_profile_enabled'] = bool(profile_enabled)
    if profile_enabled:
        profile['feasibility_timing'] = dict(
            validator_total_seconds=decision_stats.get('feasibility_validator_total_seconds', 0.0),
            top_level_phase_seconds=dict(
                initial_vehicle_scan=decision_stats.get('feasibility_initial_vehicle_scan_seconds', 0.0),
                vehicle_route_scan=decision_stats.get('feasibility_vehicle_route_scan_seconds', 0.0),
                global_checks=decision_stats.get('feasibility_global_checks_seconds', 0.0)),
            nested_check_seconds=dict(
                capacity=decision_stats.get('feasibility_capacity_check_seconds', 0.0),
                lifo=decision_stats.get('feasibility_lifo_check_seconds', 0.0),
                pickup_delivery_operations_inclusive=decision_stats.get(
                    'feasibility_pickup_delivery_seconds', 0.0)),
            nested_timer_semantics=(
                'feasibility_wall_seconds surrounds and overlaps validator_total_seconds. Top-level phases sum to validator_total_seconds. '
                'Nested checks overlap the route phase; '
                'pickup_delivery_operations_inclusive also includes capacity and LIFO time. Do not add nested timers to phases.'))
    return profile


def append_stage_trace(path, event):
    with Path(path).open('a', encoding='utf-8') as out:
        out.write(json.dumps(event, sort_keys=True)+'\n'); out.flush()
        import os
        os.fsync(out.fileno())


class SmokeLimitReached(Exception):
    pass


def step_simulation_event(model, started, wall_seconds, max_simulation_seconds):
    """Advance one SimPy event, then honor the bounded-smoke stop outside callback."""
    if perf_counter()-started > wall_seconds:
        raise TimeoutError('run wall-time limit reached; run invalid')
    next_event = model.env.peek()
    if next_event > max_simulation_seconds:
        raise ValueError('safety horizon reached with pending events; incomplete run')
    model.env.step()
    if getattr(model, 'smoke_stop_requested', False):
        raise SmokeLimitReached('decision limit reached after completed decision')


# Ghi chú: Chụp cấu hình, môi trường, hash source/dữ liệu và contract để truy nguồn kết quả rollout.
def manifest(mode, orders, vehicles, max_seconds, factories=None, routes=None, contract_version=LEGACY_CONTRACT):
    # Capture exact diff/status text; only one-line Git identifiers lose the line ending.
    files = [p for p in ROOT.rglob('*.py') if not any(x in p.parts for x in (
        '.git', '.venv', '__pycache__', 'vnsme_runs', 'third_party'))]
    # Ghi chú: Ưu tiên đường dẫn tương đối với project, giữ đường dẫn tuyệt đối nếu file ở bên ngoài.
    def label(path):
        try:
            return str(path.resolve().relative_to(ROOT))
        except ValueError:
            return str(path.resolve())
    return dict(started_at=datetime.now(timezone(timedelta(hours=7))).isoformat(),
                policy=mode, commit=git_stdout('rev-parse', 'HEAD').strip(),
                branch=git_stdout('branch', '--show-current').strip(),
                git_status=git_stdout('status', '--short', '--untracked-files=all'),
                tracked_diff=git_stdout('diff', '--'), python_executable=sys.executable, python_version=sys.version,
                packages={name: importlib.metadata.version(name) for name in ('dvrpsim', 'simpy')},
                source_sha256={str(p.relative_to(ROOT)): digest(p) for p in files},
                data_sha256={label(p): digest(p) for p in (
                    factories or CASE/'data/factory_info.csv', routes or CASE/'data/route_info.csv', orders, vehicles)},
                initial_location_seed=0, algorithm_seed=None, dispatch_step_seconds=600,
                docking_seconds=1800, loading_seconds_per_quantity=240, unloading_seconds_per_quantity=240,
                lambda_=10000, safety_horizon_simulation_seconds=max_seconds,
                primary_evaluation_baseline='vnsme', gp_fitness_reference='vnsme',
                feature_units=FEATURE_UNITS, visit_merging=False,
                logging='all logical arrivals/departures, including zero-distance same-factory visits',
                execution_time_in_simulation='instantaneous, local simulator default',
                **contract_metadata(contract_version))


# Ghi chú: Điều phối một rollout: kiểm CLI, dựng model, chạy sự kiện đến hoàn tất rồi kiểm điểm và lưu kết quả.
def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--policy', choices=('demo', 'gp', 'vnsme'), required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--tree', type=Path)
    parser.add_argument('--contract-version', choices=CONTRACT_VERSIONS, default=LEGACY_CONTRACT,
                        help='v3 is an opt-in semantic revision; legacy references are not certified for it')
    inputs = parser.add_mutually_exclusive_group()
    inputs.add_argument('--instance', type=int, choices=(1, 17), default=None)
    inputs.add_argument('--instance-directory', type=Path)
    parser.add_argument('--data-directory', type=Path)
    parser.add_argument('--seed', type=int, choices=(0,), default=0)
    parser.add_argument('--wall-seconds', type=float, default=120)
    parser.add_argument('--vnsme-epoch-seconds', type=float, default=600)
    parser.add_argument('--vnsme-search-budget-seconds', type=float,
        help='Java internal cooperative search budget; separate from --vnsme-epoch-seconds subprocess hard timeout')
    parser.add_argument('--java', default='java')
    parser.add_argument('--max-simulation-seconds', type=float, default=7*86400)
    parser.add_argument('--max-decision-points', type=int)
    parser.add_argument('--no-feasibility-profile', action='store_false',
                        dest='feasibility_profile_enabled', default=True,
                        help='disable per-check feasibility timers; routing behavior is unchanged')
    parser.add_argument('--decision-progress', action='store_true',
                        help='append sparse workload counters for supervised diagnostic pilots')
    parser.add_argument('--stage-trace', type=Path)
    parser.add_argument('--stage-partition', default='unspecified')
    args = parser.parse_args()
    import math
    if not math.isfinite(args.wall_seconds) or args.wall_seconds <= 0:
        parser.error('--wall-seconds must be positive and finite')
    if not math.isfinite(args.vnsme_epoch_seconds) or args.vnsme_epoch_seconds <= 0:
        parser.error('--vnsme-epoch-seconds must be positive and finite')
    if args.vnsme_search_budget_seconds is not None and (
            not math.isfinite(args.vnsme_search_budget_seconds) or args.vnsme_search_budget_seconds <= 0):
        parser.error('--vnsme-search-budget-seconds must be positive and finite')
    if args.policy == 'gp' and args.tree is None:
        parser.error('--tree is required for gp')
    if args.max_decision_points is not None and args.max_decision_points < 1:
        parser.error('--max-decision-points must be positive')
    if args.tree is not None and args.policy != 'gp':
        parser.error('--tree is only applicable to gp')
    if args.contract_version == EXECUTION_CONTRACT and args.policy not in ('gp', 'vnsme'):
        parser.error('v3 contract is supported only for gp and vnsme')
    contract_metadata(args.contract_version)
    if Path(sys.executable).resolve() != (ROOT/'.venv/Scripts/python.exe').resolve():
        parser.error('Use the repository .venv/Scripts/python.exe')
    directory = args.output.resolve()
    directory.mkdir(parents=True, exist_ok=False)
    paths = resolve_inputs(args.instance, args.instance_directory, args.data_directory)
    orders, vehicles, factories, routes = (paths[k] for k in ('orders', 'vehicles', 'factories', 'routes'))
    metadata = manifest(args.policy, orders, vehicles, args.max_simulation_seconds, factories, routes,
                        contract_version=args.contract_version)
    metadata.update(instance=paths['instance'], wall_limit_seconds=args.wall_seconds,
                    instance_directory=str(paths['directory']),
                    input_paths={k: str(paths[k]) for k in ('orders', 'vehicles', 'factories', 'routes')})
    if args.policy == 'gp':
        metadata['feasibility_profile_enabled'] = args.feasibility_profile_enabled
        metadata['decision_progress_enabled'] = args.decision_progress
    if args.policy == 'vnsme':
        metadata.update(vnsme_subprocess_hard_timeout_seconds=args.vnsme_epoch_seconds,
                        vnsme_internal_search_budget_seconds=args.vnsme_search_budget_seconds,
                        vnsme_internal_search_budget_scope=('variable_neighbourhood_search'
                            if args.vnsme_search_budget_seconds is not None else None),
                        primary_evaluation_baseline='vnsme', gp_fitness_reference='vnsme')
    if args.tree is not None:
        from dpdp_gp import load_tree
        _, payload = load_tree(args.tree)
        metadata.update(gp_tree=payload, tree_file_sha256=digest(args.tree))
    probdata = read_dpdp_problem(str(factories), str(routes), str(vehicles), str(orders))
    metadata['initial_locations'] = {v: d['initial_location'] for v, d in probdata['vehicles'].items()}
    dump(directory/'manifest.json', metadata)
    # Reuse the actual builder, provider, updater, vehicles and benchmark settings.
    try:
        model = RunModel(args.policy, directory, args.tree, dict(factories=factories, routes=routes,
            vehicles=vehicles, timeout=args.vnsme_epoch_seconds, java=args.java,
            search_budget_seconds=args.vnsme_search_budget_seconds), contract_version=args.contract_version,
            profile_feasibility=args.feasibility_profile_enabled,
            decision_progress=args.decision_progress)
    except Exception as exc:
        error = f'{type(exc).__name__}: {exc}'
        dump(directory/'failure.json', dict(error=error, stage='initialization', traceback=traceback.format_exc()))
        dump(directory/'result.json', dict(valid=False, error=error, stage='initialization', score=None))
        print(error)
        return 1
    with patch.object(dpdp_main, 'DPDPModel', return_value=model):
        dpdp_main.build_dpdp_model(probdata)
    start = perf_counter()
    model.wall_deadline = start + args.wall_seconds
    model.stage_started = start
    model.stage_trace_path = args.stage_trace.resolve() if args.stage_trace else None
    model.stage_partition = args.stage_partition
    model.max_decision_points = args.max_decision_points
    error = None
    valid = False
    score = None
    partial_stop = False
    try:
        model.init()
        model.on_simulation_start()
        # Ghi chú: Tiến từng sự kiện SimPy; wall-time và thời gian mô phỏng là hai giới hạn khác nhau.
        while model.env.peek() != float('inf'):
            step_simulation_event(model, start, args.wall_seconds, args.max_simulation_seconds)
        if perf_counter()-start > args.wall_seconds:
            raise TimeoutError('run wall-time limit reached; run invalid')
        model.on_simulation_finish()
        if len(list(model.delivered_orders)) != len(probdata['orders']):
            raise ValueError('not all requested items delivered')
        if model.commitment_contract is not None:
            model.commitment_contract.finish(Snapshot.observe(model), set(probdata['orders']))
        simulation_wall_seconds = perf_counter()-start
        for handler in model.log.logger.handlers:
            handler.flush()
        # Ghi chú: Chỉ chấm điểm sau khi đã giao đủ item và qua cổng hoàn tất contract.
        score = verify(directory/'simulation.log', orders, vehicles, routes)
        if perf_counter()-start > args.wall_seconds:
            raise TimeoutError('run wall-time limit reached during final scoring; run invalid')
        valid = True
    except SmokeLimitReached:
        partial_stop = True
        error = None
    except Exception as exc:
        score = None
        error = f'{type(exc).__name__}: {exc}'
        dump(directory/'failure.json', dict(error=error, traceback=traceback.format_exc()))
    elapsed = perf_counter()-start
    policy_decisions = model.policy.decisions if model.policy else []
    dump(directory/'decisions.json', dict(timings=model.decision_times, insertion=policy_decisions))
    if model.commitment_contract is not None:
        dump(directory/'commitments.json', model.commitment_contract.export())
    summary = dict(valid=valid, error=error, total_wall_seconds=elapsed,
                   status='SMOKE_COMPLETED' if partial_stop else 'COMPLETED' if valid else 'INVALID',
                   partial=partial_stop, stop_reason='decision_limit' if partial_stop else error,
                   simulation_wall_seconds=locals().get('simulation_wall_seconds'),
                   simulation_finish_seconds=model.env.now, vehicles=len(list(model.vehicles)),
                   original_orders=len({o.original_id for o in model.orders}),
                   observed_items=len(list(model.orders)), completed_items=len(list(model.delivered_orders)),
                   completed_original_orders=sum(all(o.is_delivered for o in model.orders if o.original_id == original)
                       for original in {o.original_id for o in model.orders}),
                   decision_count=len(model.decision_times),
                   candidates_examined=sum(d['examined'] for d in policy_decisions),
                   candidates_rejected=sum(d['rejected'] for d in policy_decisions),
                   deferred_groups=sum(len(d['deferred']) for d in policy_decisions),
                   decision_wall_seconds_total=sum(d['wall_seconds'] for d in model.decision_times),
                   decision_wall_seconds_max=max((d['wall_seconds'] for d in model.decision_times), default=0),
                   gp_evaluation=model.ranker.stats if model.ranker else None,
                   score=score, contract_version=args.contract_version,
                   contract_complete=model.commitment_contract.completed if model.commitment_contract is not None else None)
    dump(directory/'result.json', summary)
    for handler in model.log.logger.handlers:
        handler.close()
    print(json.dumps(summary, indent=2, default=str))
    return 0 if partial_stop else 0 if valid else 1


if __name__ == '__main__':
    sys.exit(main())
