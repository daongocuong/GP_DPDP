"""Run unchanged Java VNSME on pinned Huawei simulator, instance 2 only.

Uses upstream simulation, checker and evaluator unchanged. Replaces only the
subprocess transport to isolate files, enforce deadlines and archive each call.
"""
import argparse
import importlib.metadata
import json
import logging
import os
from pathlib import Path
import shutil
import sys
from time import perf_counter
import traceback

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT/'src'))
from baselines.vnsme import JavaSession, write_json
from build_vnsme import hashes

COMMIT = 'e4ef3a1c92d19d1d08c3ef0e2156b6fecefdbe04'
UPSTREAM = ROOT/'third_party/huawei-xingtian/simulator/dpdp_competition'
DATA = ROOT/f'datasets/xingtian/{COMMIT}/benchmark'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--wall-seconds', type=float, default=1800)
    parser.add_argument('--vnsme-epoch-seconds', type=float, default=600)
    parser.add_argument('--java', default='java')
    args = parser.parse_args()
    import math
    if not math.isfinite(args.wall_seconds) or args.wall_seconds <= 0:
        parser.error('--wall-seconds must be positive and finite')
    directory = args.output.resolve()
    directory.mkdir(parents=True, exist_ok=False)
    startup_start = perf_counter()
    session = JavaSession(directory/'vnsme', DATA/'factory_info.csv', DATA/'route_info.csv',
                          args.vnsme_epoch_seconds, args.java)
    shutil.copytree(DATA/'instance_2', session.directory/'benchmark/instance_2')
    try:
        return run(args, directory, session)
    except Exception as exc:
        failure = dict(valid=False, simulator='Huawei', instance=2, upstream_commit=COMMIT,
                       stage='startup', error=f'{type(exc).__name__}: {exc}',
                       traceback=traceback.format_exc(),
                       command=[sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]],
                       decision_count=len(session.records), score=None,
                       total_wall_seconds=perf_counter()-startup_start,
                       checker_passes=0, completion_status='startup_blocked',
                       wall_limit_seconds=args.wall_seconds,
                       vnsme_epoch_limit_seconds=args.vnsme_epoch_seconds)
        write_json(directory/'result.json', failure)
        print(json.dumps(failure, indent=2))
        return 1


def run(args, directory, session):
    # Configs creates output folders on import: import an isolated source copy.
    source = directory/'huawei'
    shutil.copytree(UPSTREAM/'src', source/'src', ignore=shutil.ignore_patterns('__pycache__', 'output'))
    sys.path.insert(0, str(source))
    os.chdir(session.directory)
    from src.conf.configs import Configs
    Configs.benchmark_folder_path = str(session.directory/'benchmark')
    Configs.algorithm_data_interaction_folder_path = str(session.exchange)
    for attr, name in [('algorithm_vehicle_input_info_path', 'vehicle_info.json'),
                       ('algorithm_unallocated_order_items_input_path', 'unallocated_order_items.json'),
                       ('algorithm_ongoing_order_items_input_path', 'ongoing_order_items.json'),
                       ('algorithm_output_destination_path', 'output_destination.json'),
                       ('algorithm_output_planned_route_path', 'output_route.json')]:
        setattr(Configs, attr, str(session.exchange/name))
    from src.simulator import simulate_api, simulate_environment
    from src.utils.checker import Checker
    from src.utils.evaluator import Evaluator
    from src.utils.logging_engine import logger
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
    handler = logging.FileHandler(directory/'simulation.log', mode='x', encoding='utf-8')
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    start = perf_counter()
    checks = []
    original_check = Checker.check_dispatch_result

    def checked(*values):
        passed = original_check(*values)
        checks.append(passed)
        if not passed:
            raise ValueError('Huawei checker rejected dispatch')
        return passed

    Checker.check_dispatch_result = staticmethod(checked)

    def transport(command):
        state = {key: json.loads((session.exchange/name).read_text()) for key, name in [
            ('vehicle_info', 'vehicle_info.json'), ('ongoing_orders', 'ongoing_order_items.json'),
            ('unallocated_orders', 'unallocated_order_items.json')]}
        session.invoke(state, args.wall_seconds-(perf_counter()-start))
        return session.records[-1]['wall_seconds'], 'SUCCESS'

    simulate_environment.subprocess_function = transport
    result = dict(valid=False, simulator='Huawei', instance=2, upstream_commit=COMMIT,
                  command=[sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]],
                  wall_limit_seconds=args.wall_seconds, vnsme_epoch_limit_seconds=args.vnsme_epoch_seconds,
                  packages={n: importlib.metadata.version(n) for n in ('pandas', 'numpy', 'simpy')},
                  upstream_source_sha256=hashes(source/'src'))
    try:
        env = simulate_api.__initialize('factory_info.csv', 'route_info.csv', 'instance_2')
        if env is None:
            raise RuntimeError('Huawei initialization failed; see simulation.log')
        env.algorithm_calling_command = session.command
        result['initial_locations'] = {v: x.cur_factory_id for v,x in env.id_to_vehicle.items()}
        env.run()
        history = env.history.get_order_item_status_history()
        completed = {i for i, rows in history.items() if any(r['state'] == 3 for r in rows)}
        if completed != set(env.id_to_order_item):
            raise ValueError('Huawei history missing item completion')
        distance = Evaluator.calculate_total_distance(env.history.get_vehicle_position_history(), env.route_map)
        tardiness = Evaluator.calculate_total_over_time(history)
        score = distance/len(env.id_to_vehicle) + tardiness*10000/3600
        if score != env.total_score:
            raise ValueError('Huawei final score mismatch')
        if perf_counter()-start > args.wall_seconds:
            raise TimeoutError('Huawei rollout wall-time exhausted')
        result.update(valid=True, completed_items=len(completed), original_orders=len(env.id_to_order),
                      score=dict(total_score=score, total_distance_km=distance, total_tardiness_seconds=tardiness))
        write_json(directory/'history_items.json', history)
        write_json(directory/'history_vehicles.json', env.history.get_vehicle_position_history())
    except BaseException as exc:
        result.update(error=f'{type(exc).__name__}: {exc}', traceback=traceback.format_exc())
    finally:
        result.update(total_wall_seconds=perf_counter()-start, decision_count=len(session.records),
                      decision_wall_seconds_total=sum(r['wall_seconds'] for r in session.records),
                      decision_wall_seconds_max=max((r['wall_seconds'] for r in session.records), default=0),
                      checker_passes=sum(checks), checker_failures=checks.count(False))
        write_json(directory/'result.json', result)
        handler.close()
    print(json.dumps({k:v for k,v in result.items() if k != 'upstream_source_sha256'}, indent=2))
    return 0 if result['valid'] else 1


if __name__ == '__main__':
    sys.exit(main())
