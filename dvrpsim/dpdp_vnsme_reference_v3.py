"""Separate, fail-closed v3 reference collection and independent re-scoring.

Only development instances are permitted. Running a reference is explicit;
neither this module nor its loader accepts an historical v2 denominator.
"""
import argparse
import json
import math
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile

from dpdp_contract import EXECUTION_CONTRACT, contract_metadata
from dpdp_dataset import resolve_inputs
from dpdp_gp_fitness import digest
from dpdp_vnsme_reference import SIMULATION
from verify_dpdp_score import read_orders, verify

ROOT = Path(__file__).resolve().parent
DATASET = ROOT/'datasets/xingtian/e4ef3a1c92d19d1d08c3ef0e2156b6fecefdbe04'
PROTOCOL = ROOT/'protocols/dpdp_gp_split_v1.json'
FITNESS_VERSION = 'gp-fitness-vnsme-v3'
ALLOWED = {2, 3, 4, 5, 6, 9, 10, 11, 12, 13, 14}
REQUIRED = ('simulation.log', 'manifest.json', 'result.json', 'decisions.json', 'commitments.json', 'vnsme/session.json')

# Ghi chú: Đọc artifact JSON UTF-8 thành đối tượng Python để kiểm metadata và kết quả đã lưu.
def read(path): return json.loads(Path(path).read_text(encoding='utf-8'))

# Ghi chú: Kiểm hash source/library/class Java và tìm Java executable; chưa chạy rollout baseline.
def preflight_build():
    from build_vnsme import hashes
    build = read(ROOT/'third_party/vnsme/build_manifest.json')
    for folder,key in (('original','source_sha256'),('lib','library_sha256'),('build','class_sha256')):
        if hashes(ROOT/'third_party/vnsme'/folder) != build[key]: raise ValueError('Java build checksum mismatch')
    java = shutil.which('java')
    if not java: raise ValueError('Java missing')
    return dict(java_executable=java, java_version=subprocess.check_output([java,'-version'],stderr=subprocess.STDOUT,text=True))

# Ghi chú: Chọn hash simulator/scorer từ manifest và đối chiếu source hiện tại; comment cũng làm đổi hash byte.
def runtime_fingerprint(manifest):
    source = {k.replace('\\', '/'): v for k, v in manifest['source_sha256'].items()}
    required = {'run_dpdp_insertion.py', 'dpdp_contract.py', 'dpdp_feasibility.py',
                'dpdp_insertion.py', 'dpdp_schedule.py', 'dpdp_dataset.py', 'verify_dpdp_score.py',
                'dpdp_sealed.py', 'dpdp_v3_trace.py', 'dpdp_v3_independent_audit.py'}
    selected = {k:v for k,v in source.items() if k in required or k.startswith('src/dvrpsim/')
                or k.startswith('examples/case_studies/dpdp/')}
    if not required <= set(selected) or not any(k.startswith('src/dvrpsim/') for k in selected):
        raise ValueError('incomplete simulator source fingerprint')
    if any(digest(ROOT/name) != sha for name,sha in selected.items()):
        raise ValueError('simulator/scorer source checksum mismatch')
    return selected

# Ghi chú: Chỉ nhận development instance, kiểm split/dataset và tạo metadata dữ liệu/cấu hình cho reference V3.
def metadata(instance):
    if instance not in ALLOWED: raise ValueError('sealed or non-development instance')
    protocol = read(PROTOCOL); ph = digest(PROTOCOL)
    if PROTOCOL.with_suffix('.json.sha256').read_text().split()[0] != ph: raise ValueError('split protocol hash mismatch')
    source = DATASET/'source_manifest.json'; mh = digest(source)
    if mh != protocol['dataset_manifest_sha256'] or (DATASET/'source_manifest.sha256').read_text().split()[0] != mh:
        raise ValueError('dataset manifest hash mismatch')
    roles = protocol['roles']['50_orders' if instance < 9 else '100_orders_proposed']
    role = next((r for r in ('train', 'validation') if instance in roles[r]), None)
    if role is None: raise ValueError('not a train/validation instance')
    paths = resolve_inputs(instance_directory=DATASET/'benchmark'/f'instance_{instance}')
    files = {x['file'].replace('\\', '/'): x['sha256'] for x in read(source)['files']}
    for name in ('orders', 'vehicles', 'factories', 'routes'):
        rel = paths[name].relative_to(DATASET/'benchmark').as_posix()
        if files.get(rel) != digest(paths[name]): raise ValueError(f'dataset hash mismatch: {rel}')
    items, orders = read_orders(paths['orders'])
    return dict(instance=instance, role=role, split_protocol_sha256=ph, source_manifest_sha256=mh,
                data_sha256={k: digest(paths[k]) for k in ('orders', 'vehicles', 'factories', 'routes')},
                input_paths={k: str(paths[k]) for k in ('orders', 'vehicles', 'factories', 'routes')},
                items=len(items), orders=len(orders), seed=0, simulation=SIMULATION,
                java_build_sha256=digest(ROOT/'third_party/vnsme/build_manifest.json'),
                **contract_metadata(EXECUTION_CONTRACT))

# Ghi chú: Kiểm provenance, cam kết và completion, replay độc lập rồi tính lại J cho rollout GP hoặc VNSME V3.
def audit_run(run, instance, policy='vnsme', relocation=None):
    """Rescore and independently replay a complete, evidenced v3 rollout."""
    run = Path(run).resolve(); meta = metadata(instance)
    manifest, result, ledger = (read(run/x) for x in ('manifest.json', 'result.json', 'commitments.json'))
    if manifest.get('policy') != policy or manifest.get('instance') != instance: raise ValueError('policy/instance mismatch')
    for obj in (manifest, result, ledger):
        if obj.get('contract_version') != EXECUTION_CONTRACT: raise ValueError('contract-version mismatch')
    if manifest.get('contract_protocol_sha256') != meta['contract_protocol_sha256']:
        raise ValueError('contract protocol checksum mismatch')
    if any(manifest.get(k) != v for k, v in SIMULATION.items()): raise ValueError('simulation configuration mismatch')
    if not result.get('valid') or not result.get('contract_complete') or not result.get('score') or not ledger.get('complete'):
        raise ValueError('invalid or incomplete rollout')
    runtime_fingerprint(manifest)
    if policy == 'vnsme':
        source = {k.replace('\\', '/'): v for k,v in manifest['source_sha256'].items()}
        if source.get('src/baselines/vnsme.py') != digest(ROOT/'src/baselines/vnsme.py'):
            raise ValueError('VNSME adapter checksum mismatch')
    paths = meta['input_paths']
    resolve = relocation.resolve if relocation else lambda p: Path(p).resolve()
    for k in paths:
        if resolve(manifest['input_paths'][k]) != Path(paths[k]).resolve(): raise ValueError('input path mismatch')
    pinned = {str(resolve(Path(k) if Path(k).is_absolute() else ROOT/Path(k))):v
              for k,v in manifest['data_sha256'].items()}
    if any(pinned.get(str(Path(paths[k]).resolve())) != meta['data_sha256'][k] for k in paths):
        raise ValueError('input hash mismatch')
    items, orders = read_orders(paths['orders']); expected = set(items)
    if set(ledger['requests']) != expected or set(ledger['delivered_items']) != expected:
        raise ValueError('commitment ledger missing required items')
    if len(ledger['delivered_items']) != len(expected): raise ValueError('duplicate ledger item')
    terminal = ledger.get('terminal_state') or {}; states = terminal.get('states') or {}
    if set(states.get('delivered', [])) != expected or any(states.get(x) for x in ('pending', 'tentative', 'committed')):
        raise ValueError('incomplete terminal commitment states')
    guards = read(run/'decisions.json')['timings']
    if not guards or len(guards) != result['decision_count'] or not all(x.get('guard_passed') for x in guards):
        raise ValueError('feasibility guard evidence missing or failed')
    if len(ledger['history']) != len(guards): raise ValueError('commitment history incomplete')
    previous = set()
    for event in ledger['history']:
        parts = [event['states'][k] for k in ('pending','tentative','committed','delivered')]
        ids = [item for part in parts for item in part]
        if len(ids) != len(set(ids)) or len(ids) != event['observed_items'] or not previous <= set(ids) or not set(ids) <= expected:
            raise ValueError('commitment history accounting mismatch')
        previous = set(ids)
    from dpdp_v3_independent_audit import audit
    independent = audit(run, paths, policy=policy)
    if independent['status'] != 'PASS':
        raise ValueError(f'independent replay {independent["status"]}: {independent.get("reason")}')
    score = json.loads(json.dumps(verify(run/'simulation.log', paths['orders'], paths['vehicles'], paths['routes']), default=str))
    if not score['valid'] or any(str(score[k]) != str(result['score'][k]) for k in ('total_score','total_distance_km','total_tardiness_seconds')):
        raise ValueError('independent scorer mismatch')
    if (result['completed_items'], result['completed_original_orders'], score['items'], score['original_orders']) != (len(items), len(orders), len(items), len(orders)):
        raise ValueError('completion count mismatch')
    value = float(score['total_score'])
    if not math.isfinite(value) or value < 0 or (policy == 'vnsme' and value == 0):
        raise ValueError('J must be finite and nonnegative; VNSME denominator must be positive')
    return score, manifest

# Ghi chú: Bổ sung kiểm supervisor, build Java và bằng chứng từng epoch trước khi tạo record reference.
def audit_vnsme_run(run, supervision, instance, relocation=None):
    run = Path(run).resolve(); supervision = Path(supervision).resolve()
    score, manifest = audit_run(run, instance, relocation=relocation)
    meta = metadata(instance); job = read(supervision/'supervision.json')
    if supervision.parent != run.parent: raise ValueError('run and supervisor must share their immutable collection directory')
    preparation = read(run.parent/'protocol_manifest.json')
    for key in ('instance','role','split_protocol_sha256','source_manifest_sha256','data_sha256',
                'seed','simulation','java_build_sha256','contract_version','contract_protocol_sha256'):
        if preparation.get(key) != meta[key]: raise ValueError(f'collection manifest mismatch: {key}')
    if preparation.get('budgets') != dict(java_cooperative_seconds=540, epoch_seconds=600, rollout_seconds=10800):
        raise ValueError('collection budget mismatch')
    if preparation['git_revision'] != manifest['commit'] or preparation['environment']['python'] != manifest['python_version']:
        raise ValueError('collection environment or revision mismatch')
    if not job.get('valid_supervision') or job.get('state') != 'EXITED' or job.get('exit_code') != 0 or job.get('gaps') or job.get('remaining_job_processes'):
        raise ValueError('supervision invalid, timed out, gapped or leaked')
    command = job.get('command', [])
    # Ghi chú: Lấy giá trị một tham số phải xuất hiện đúng một lần trong lệnh supervisor đã lưu.
    def argument(name):
        if command.count(name) != 1: raise ValueError(f'supervised command missing {name}')
        return command[command.index(name)+1]
    resolve = relocation.resolve if relocation else lambda p: Path(p).resolve()
    if (argument('--policy') != 'vnsme' or argument('--contract-version') != EXECUTION_CONTRACT or
        resolve(argument('--output')) != run or resolve(argument('--instance-directory')) != (DATASET/'benchmark'/f'instance_{instance}').resolve()):
        raise ValueError('supervised command does not match rollout')
    if float(argument('--wall-seconds')) != 10800 or float(argument('--vnsme-epoch-seconds')) != 600:
        raise ValueError('supervised command budgets mismatch')
    if job['timeout_seconds'] != 10800 or manifest['wall_limit_seconds'] != 10800 or manifest['vnsme_epoch_limit_seconds'] != 600:
        raise ValueError('reference budget mismatch')
    session = read(run/'vnsme/session.json')
    if session['build_manifest'] != read(ROOT/'third_party/vnsme/build_manifest.json') or session['timeout_seconds'] != 600:
        raise ValueError('Java build/session mismatch')
    if session['java'] != preparation['environment']['java_version'] or Path(session['command'][0]).resolve() != Path(preparation['environment']['java_executable']).resolve():
        raise ValueError('Java executable or version mismatch')
    from build_vnsme import hashes
    for folder, key in (('original','source_sha256'),('lib','library_sha256'),('build','class_sha256')):
        if hashes(ROOT/'third_party/vnsme'/folder) != session['build_manifest'][key]: raise ValueError('Java build changed')
    epochs = sorted((run/'vnsme/epochs').glob('[0-9][0-9][0-9][0-9][0-9]'))
    if len(epochs) != len(read(run/'decisions.json')['timings']): raise ValueError('Java epoch count mismatch')
    files = list(REQUIRED)+['decision_trace.jsonl']
    for epoch in epochs:
        start = read(epoch/'invocation_start.json'); end = read(epoch/'invocation_process_end.json'); inv = read(epoch/'invocation.json')
        if start['pid'] != end['pid'] or start['identity']['pid'] != start['pid'] or end['timed_out'] or end['returncode'] or not inv['valid']:
            raise ValueError('Java invocation missing/invalid')
        if (end['ended_monotonic'] < start['started_monotonic'] or
            end['ended_monotonic'] > start['deadline_monotonic'] or
            not 0 < start['timeout_seconds'] <= 600):
            raise ValueError('Java invocation timing invalid')
        for name in ('invocation_start.json','invocation_process_end.json','invocation.json','vehicle_info.json',
                     'ongoing_order_items.json','unallocated_order_items.json','output_destination.json','output_route.json',
                     'java_stdout_live.txt','java_stderr_live.txt'):
            files.append((epoch/name).relative_to(run).as_posix())
    from dpdp_v3_independent_audit import audit
    independent = audit(run, meta['input_paths'])
    if independent['status'] != 'PASS': raise ValueError(f'independent replay {independent["status"]}')
    return dict(instance=instance, role=meta['role'], valid=True, J=score['total_score'], independent_audit=independent,
                run_directory=str(run), supervision_directory=str(supervision),
                artifact_sha256={name:digest(run/name) for name in files},
                supervision_sha256={name:digest(supervision/name) for name in ('supervision.json','heartbeats.jsonl','process.log')},
                protocol_manifest_sha256=digest(run.parent/'protocol_manifest.json'),
                git_revision=manifest['commit'], contract_protocol_sha256=meta['contract_protocol_sha256'],
                java_build_sha256=meta['java_build_sha256'], data_sha256=meta['data_sha256'],
                split_protocol_sha256=meta['split_protocol_sha256'], source_manifest_sha256=meta['source_manifest_sha256'])

# Ghi chú: Kiểm đúng tập instance, hash artifact và audit lại từng reference trước khi cho dùng J làm mẫu số fitness.
def load_reference(path, expected, relocation=None):
    data = read(path)
    if data.get('fitness_version') != FITNESS_VERSION or data.get('contract_version') != EXECUTION_CONTRACT or not data.get('valid'):
        raise ValueError('v3 loader rejects v2, mixed or invalid reference')
    records = data.get('records', []); ids = [r['instance'] for r in records]
    if not expected or len(ids) != len(set(ids)) or set(ids) != set(expected): raise ValueError('instance set mismatch')
    scores = {}
    resolved_runs = {}
    for row in records:
        if row['instance'] not in ALLOWED: raise ValueError('sealed or non-development instance')
        resolve = relocation.resolve if relocation else lambda p: Path(p).resolve()
        run = resolve(row['run_directory'])
        for name, sha in row['artifact_sha256'].items():
            target = run/name
            if relocation: target = relocation.resolve(target, sha)
            if digest(target) != sha: raise ValueError('artifact checksum mismatch')
        supervision = resolve(row['supervision_directory'])
        for name, sha in row['supervision_sha256'].items():
            target = supervision/name
            if relocation: target = relocation.resolve(target, sha)
            if digest(target) != sha: raise ValueError('supervision checksum mismatch')
        if 'protocol_manifest_sha256' in row and digest(run.parent/'protocol_manifest.json') != row['protocol_manifest_sha256']:
            raise ValueError('collection protocol checksum mismatch')
        current = audit_vnsme_run(run, supervision, row['instance'], relocation=relocation)
        if relocation:
            current = dict(current, run_directory=row['run_directory'],
                           supervision_directory=row['supervision_directory'])
        if current != row: raise ValueError('reference record mismatch')
        scores[row['instance']] = float(row['J'])
        resolved_runs[str(row['instance'])] = str(run)
    if relocation:
        data = dict(data, resolved_run_directories=resolved_runs)
    return scores, data

# Ghi chú: Tạo collection mới, chạy VNSME có giám sát rồi audit và lưu record; hàm này thực sự khởi chạy thí nghiệm.
def run_reference(instance, output):
    from dpdp_v3_supervisor import supervise
    output = Path(output).resolve(); output.mkdir(parents=True, exist_ok=False)
    meta = metadata(instance); java = preflight_build()
    meta.update(git_revision=subprocess.check_output(['git','rev-parse','HEAD'], cwd=ROOT, text=True).strip(),
                environment=dict(python=sys.version, executable=sys.executable, platform=platform.platform(), **java),
                budgets=dict(java_cooperative_seconds=540, epoch_seconds=600, rollout_seconds=10800))
    (output/'protocol_manifest.json').write_text(json.dumps(meta,indent=2),encoding='utf-8')
    run = output/'run'
    command = [sys.executable, str(ROOT/'run_dpdp_insertion.py'), '--policy','vnsme', '--contract-version', EXECUTION_CONTRACT,
        '--instance-directory',str(DATASET/'benchmark'/f'instance_{instance}'), '--output',str(run),
        '--wall-seconds','10800','--vnsme-epoch-seconds','600']
    job = supervise(command, output/'supervisor', 10800, epoch_root=run/'vnsme/epochs')
    if not job['valid_supervision'] or job.get('exit_code') != 0: raise ValueError('reference run failed supervision')
    row = audit_vnsme_run(run, output/'supervisor', instance)
    (output/'record.json').write_text(json.dumps(row,indent=2),encoding='utf-8')
    return row

# Ghi chú: Phân luồng CLI: preflight kiểm đầu vào/build, verify audit reference, run tạo rollout, assemble ghép record đã kiểm.
def main():
    p=argparse.ArgumentParser(description=__doc__); sub=p.add_subparsers(dest='action',required=True)
    pre=sub.add_parser('preflight'); pre.add_argument('--instance',type=int,required=True)
    check=sub.add_parser('verify'); check.add_argument('--summary',type=Path,required=True)
    check.add_argument('--relocation-config',type=Path)
    check.add_argument('--ids',nargs='+',type=int,required=True)
    run=sub.add_parser('run'); run.add_argument('--instance',type=int,required=True); run.add_argument('--output',required=True)
    run.add_argument('--contract-version',required=True,choices=[EXECUTION_CONTRACT])
    assemble=sub.add_parser('assemble'); assemble.add_argument('--records',nargs='+',required=True); assemble.add_argument('--output',required=True)
    a=p.parse_args()
    if a.action=='verify':
        from dpdp_relocation import load_relocation
        relocation=load_relocation(a.relocation_config) if a.relocation_config else None
        scores, data=load_reference(a.summary,a.ids,relocation)
        print(json.dumps(dict(status='PASS',scores=scores,
                              resolved_run_directories=data.get('resolved_run_directories',{})),indent=2)); return
    if a.action=='preflight':
        data=metadata(a.instance); data['java_environment']=preflight_build(); print(json.dumps(data,indent=2)); return
    if a.action=='run': print(json.dumps(run_reference(a.instance,a.output),indent=2)); return
    rows=[read(x) for x in a.records]; ids=[x['instance'] for x in rows]
    if len(ids)!=len(set(ids)) or not set(ids)<=ALLOWED: raise ValueError('invalid instance set')
    for row in rows:
        if audit_vnsme_run(row['run_directory'],row['supervision_directory'],row['instance']) != row: raise ValueError('record mismatch')
    data=dict(valid=True,policy='vnsme',fitness_version=FITNESS_VERSION,contract_version=EXECUTION_CONTRACT,records=rows)
    # Verify the complete candidate before publishing a summary marked valid.
    with tempfile.TemporaryDirectory(prefix='dpdp_v3_summary_') as temp:
        candidate=Path(temp)/'summary.json'; candidate.write_text(json.dumps(data,indent=2),encoding='utf-8')
        load_reference(candidate,ids)
    out=Path(a.output); out.mkdir(parents=True,exist_ok=False)
    with (out/'summary.json').open('x',encoding='utf-8') as f: json.dump(data,f,indent=2)
    print(out/'summary.json')

if __name__=='__main__': main()
