"""Read-only performance audit of the existing instance 10 artifacts.

No Java, simulator, scorer, training, datasets, or production writes are used.
Run from any cwd with Python -B. Outputs are confined to this script's directory.
Topology counts describe saved snapshots, not instrumented live search states.
"""
from collections import Counter
from datetime import datetime
import csv
import hashlib
import json
from pathlib import Path
import re
import time

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
RUN = ROOT / 'vnsme_runs/scale100_reference_20261109_r1'
EPOCHS = RUN / 'instance_10/vnsme/epochs'
START = time.perf_counter()
CPU_START = time.process_time()
READ_HASHES = {}


def blob(path):
    blob = path.read_bytes()
    READ_HASHES[str(path.relative_to(ROOT))] = hashlib.sha256(blob).hexdigest()
    return blob


def data(path):
    return blob(path).decode('utf-8')


def read(path):
    return json.loads(data(path))


def write(name, obj):
    (OUT / name).write_text(json.dumps(obj, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def snapshot_routes(route):
    return {v: nodes.split() for v, nodes in re.findall(r'(V_\d+):\[([^\]]*)\]', route)}


def route_counts(route):
    routes = snapshot_routes(route)
    pickups = sum(token.startswith('p') for nodes in routes.values() for token in nodes)
    return dict(nodes=sum(map(len, routes.values())), pickups=pickups,
                nodes_by_vehicle={v: len(nodes) for v, nodes in routes.items()},
                block_count_upper_bound=pickups,
                exchange_pair_upper_bound=pickups * (pickups - 1) // 2)


rows = []
for epoch in sorted(EPOCHS.iterdir()):
    if not epoch.is_dir():
        continue
    inv = read(epoch / 'invocation.json')
    pending = read(epoch / 'unallocated_order_items.json')
    carrying = read(epoch / 'ongoing_order_items.json')
    stderr_present = (epoch / 'stderr.txt').is_file()
    stdout_present = (epoch / 'stdout.txt').is_file()
    stderr = data(epoch / 'stderr.txt') if stderr_present else ''
    stdout = data(epoch / 'stdout.txt') if stdout_present else ''
    summary = re.findall(r'PDPairExchange:(\d+); BlockExchange:(\d+);BlockRelocate:(\d+); mPDG:(\d+); usedTime:([\d.]+) seconds; cost:([\d.]+)', stderr)
    counts = Counter(stderr.splitlines())
    previous = read(epoch / 'solution_before.json') if (epoch / 'solution_before.json').exists() else {}
    result = read(epoch / 'solution.json') if (epoch / 'solution.json').exists() else {}
    row = dict(epoch=int(epoch.name), invocation=inv, pending_items=len(pending),
               carrying_items=len(carrying), pending_orders=len({i['order_id'] for i in pending}),
               stdout_artifact_present=stdout_present, stderr_artifact_present=stderr_present,
               stderr_bytes=(epoch / 'stderr.txt').stat().st_size if stderr_present else None,
               stderr_lines=sum(counts.values()) if stderr_present else None, stderr_common_lines=counts.most_common(8),
               has_success=('SUCCESS' in stdout.split()) if stdout_present else None,
               cooperative_timeout=('TimeOut!!' in counts) if stderr_present else None,
               previous_private=route_counts(previous.get('route_after', '')),
               resulting_private=route_counts(result.get('route_after', '')) if result else None)
    if summary:
        a,b,c,d,e,f = summary[-1]
        row['search_summary'] = dict(PDPairExchange=int(a), BlockExchange=int(b),
                                    BlockRelocate=int(c), mPDG=int(d), used_seconds=float(e), cost=float(f))
    rows.append(row)

beats = [json.loads(line) for line in data(RUN / 'instance_10_heartbeats.jsonl').splitlines()]
gaps = []
for a,b in zip(beats, beats[1:]):
    wall = (datetime.fromisoformat(b['observed_at']) - datetime.fromisoformat(a['observed_at'])).total_seconds()
    monotonic = b['elapsed_seconds'] - a['elapsed_seconds']
    gaps.append(dict(from_at=a['observed_at'], to_at=b['observed_at'], wall_seconds=wall,
                     monotonic_seconds=monotonic, clock_difference_seconds=wall-monotonic,
                     from_epoch=a['last_epoch'], to_epoch=b['last_epoch']))
child_samples = [b for b in beats if 'child_processes' in b]
child_names = Counter()
cpu_series = {}
for b in child_samples:
    if not isinstance(b['child_processes'], list):
        continue
    for p in b['child_processes']:
        child_names[p['Name']] += 1
        cpu = (int(p['KernelModeTime']) + int(p['UserModeTime'])) / 10_000_000
        cpu_series.setdefault(p['ProcessId'], []).append(dict(at=b['observed_at'], name=p['Name'], cpu_seconds=cpu))

execution = read(RUN / 'instance_10_execution.json')
thread_dump = data(RUN / 'instance_10_epoch_00087_threads.txt')
main = re.search(r'"main"[^\n]*cpu=([\d.]+)ms elapsed=([\d.]+)s', thread_dump)
thread = dict(cpu_seconds=float(main[1])/1000, elapsed_seconds=float(main[2]),
              cpu_fraction=float(main[1])/1000/float(main[2]), state='RUNNABLE',
              stack=['main_algorithm.cost:3856', 'main_algorithm.blockExchange:918',
                     'main_algorithm.variableNeighbourhoodSearch:242', 'main_algorithm.main:119'])
valid = [r for r in rows if r['invocation']['valid']]
slow = [r for r in rows if r['invocation']['wall_seconds'] > 10]
all_gaps = sorted(gaps, key=lambda g:g['wall_seconds'], reverse=True)
heartbeat = dict(count=len(beats), child_sample_count=len(child_samples), child_names=dict(child_names),
                 java_child_samples=child_names.get('java.exe', 0)+child_names.get('java.EXE', 0),
                 child_cpu_observations=cpu_series, largest_gaps=all_gaps[:10],
                 gaps_over_15_seconds=[g for g in gaps if g['wall_seconds'] > 15],
                 final_beat=beats[-1], execution_ended_at=execution['ended_at'],
                 final_beat_to_recorded_end_seconds=(datetime.fromisoformat(execution['ended_at'])-datetime.fromisoformat(beats[-1]['observed_at'])).total_seconds())
metrics = dict(source_run=str(RUN.relative_to(ROOT)), selected_epochs=[r for r in rows if r['epoch'] in (87,103,104,127)],
               epoch_count=len(rows), valid_invocation_count=len(valid), slow_epochs=[r['epoch'] for r in slow],
               successful_Java_wall_seconds=sum(r['invocation']['wall_seconds'] for r in valid),
               all_invocation_wall_seconds=sum(r['invocation']['wall_seconds'] for r in rows),
               successful_cooperative_timeouts=[r['epoch'] for r in valid if r['cooperative_timeout']],
               successful_long_epoch_wall_seconds=sum(r['invocation']['wall_seconds'] for r in valid if r['invocation']['wall_seconds']>10),
               failed_epoch_wall_seconds=sum(r['invocation']['wall_seconds'] for r in rows if not r['invocation']['valid']),
               epoch87_thread_dump=thread,
               topology_limit='Counts are saved private snapshots. They are upper bounds on block pairs in those snapshots, not measured candidate/cost calls during search. Current-scene restoration, dispatch, and search can change topology.')
for p in [ROOT/'third_party/vnsme/original/main_algorithm.java', ROOT/'third_party/vnsme/build_manifest.json',
          RUN/'run_reference.py', RUN/'summary.json', RUN/'final_verification.json']:
    data(p)
manifest = read(ROOT/'third_party/vnsme/build_manifest.json')
historical_session = read(RUN/'instance_10/vnsme/session.json')
build_verification = dict(saved_session_manifest_matches_current=historical_session['build_manifest']==manifest)
for directory, key in [('original','source_sha256'), ('lib','library_sha256'), ('build','class_sha256')]:
    folder = ROOT/'third_party/vnsme'/directory
    current = {p.relative_to(folder).as_posix(): hashlib.sha256(blob(p)).hexdigest()
               for p in sorted(folder.rglob('*')) if p.is_file()}
    build_verification[key] = dict(file_count=len(current), matches_saved_build_manifest=current==manifest[key])
assert build_verification['saved_session_manifest_matches_current']
assert all(build_verification[k]['matches_saved_build_manifest'] for k in ('source_sha256','library_sha256','class_sha256'))
write('build_verification.json', build_verification)
write('epoch_metrics.json', rows)
write('selected_metrics.json', metrics)
write('heartbeat_metrics.json', heartbeat)
with (OUT / 'epoch_metrics.csv').open('w', encoding='utf-8', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(['epoch', 'valid', 'invocation_wall_seconds', 'pending_items', 'pending_orders', 'carrying_items',
                     'previous_private_nodes', 'previous_private_pickup_nodes', 'previous_exchange_pair_upper_bound',
                     'resulting_private_nodes', 'resulting_private_pickup_nodes', 'resulting_exchange_pair_upper_bound',
                     'cooperative_timeout', 'BlockExchange', 'BlockRelocate', 'stderr_bytes'])
    for r in rows:
        s = r.get('search_summary', {})
        after = r['resulting_private'] or {}
        writer.writerow([r['epoch'], r['invocation']['valid'], r['invocation']['wall_seconds'],
                         r['pending_items'], r['pending_orders'], r['carrying_items'],
                         r['previous_private']['nodes'], r['previous_private']['pickups'],
                         r['previous_private']['exchange_pair_upper_bound'], after.get('nodes'), after.get('pickups'),
                         after.get('exchange_pair_upper_bound'), r['cooperative_timeout'], s.get('BlockExchange'),
                         s.get('BlockRelocate'), r['stderr_bytes']])
integrity = {path: hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==digest for path,digest in READ_HASHES.items()}
assert all(integrity.values())
write('input_sha256.json', READ_HASHES)
write('resource_record.json', dict(execution='offline Python artifact analysis only', java_invocations=0,
      simulator_runs=0, GP_training_runs=0, observed_wall_seconds=time.perf_counter()-START,
      observed_process_cpu_seconds=time.process_time()-CPU_START, declared_python_wall_budget_seconds=30,
      declared_Java_budget_seconds=0, input_files_checked_unchanged=len(integrity), all_input_hashes_unchanged=True,
      process_cleanup='Synchronous Python process exited. No Java or background child processes were launched.'))
print(json.dumps(dict(epochs=len(rows), slow_epochs=metrics['slow_epochs'], cooperative_timeouts=metrics['successful_cooperative_timeouts'],
                     largest_heartbeat_gap=all_gaps[0], main_cpu_fraction=thread['cpu_fraction'],
                     java_child_samples=heartbeat['java_child_samples'], input_files_checked=len(integrity)), indent=2))
