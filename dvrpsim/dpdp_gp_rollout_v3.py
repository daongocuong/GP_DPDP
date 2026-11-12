"""V3-only GP rollouts, fail-closed auditing and context-addressed cache."""
import hashlib
import importlib.metadata
import json
import math
from pathlib import Path
import sys
import time

from dpdp_contract import EXECUTION_CONTRACT, contract_metadata
from dpdp_gp import (FEATURES, PRIMITIVES, NUMERIC_POLICY, Limits, TreeError,
                     canonical, load_tree, save_tree, tree_hash)
from dpdp_vnsme_reference_v3 import (FITNESS_VERSION, audit_run, read,
                                     runtime_fingerprint)

ROOT = Path(__file__).resolve().parent
CACHE_SCHEMA = "dpdp-gp-fitness-cache-v3"
INVALID_FITNESS = 1e15


class RolloutBudgetExceeded(RuntimeError):
    pass


# Ghi chú: Tính SHA-256 để ràng buộc source, cây và artifact với đúng nội dung file.
def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# Ghi chú: Lập bảng hash source đang dùng, chỉ duyệt code gốc/src/examples thay vì các thư mục kết quả cũ.
def source_fingerprint():
    """Pin active code without traversing historical runs, evidence or datasets."""
    files = list(ROOT.glob('*.py'))
    for directory in ('src', 'examples'):
        files.extend((ROOT/directory).rglob('*.py'))
    return {
        p.relative_to(ROOT).as_posix(): digest(p)
        for p in sorted(files) if '__pycache__' not in p.parts
    }


# Ghi chú: Tạo khóa từ cây và toàn bộ context; cùng cây nhưng khác dữ liệu hoặc cấu hình sẽ có khóa khác.
def cache_key(tree, context):
    payload = dict(tree=json.loads(canonical(tree)), context=context)
    raw = json.dumps(payload, sort_keys=True, separators=(',', ':'), allow_nan=False)
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


# Ghi chú: Chỉ chấp nhận cache có khóa/context khớp và đã lưu một điểm J hợp lệ.
def verify_cache_provenance(entry, key, context):
    if entry.get('cache_key') != key or entry.get('context') != context:
        raise ValueError('v3 cache provenance mismatch')
    if not entry.get('valid') or entry.get('benchmark_J') is None:
        raise ValueError('v3 cache contains an invalid entry')
    return True


# Ghi chú: Sau audit, kiểm cây thực chạy và tính tương thích GP/VNSME trước khi cho phép sử dụng J.
def assess_rollout(score, manifest, tree, tree_file, reference_manifest):
    """Accept J only after independent v3 audit and reference compatibility checks."""
    if not isinstance(score, dict) or not manifest:
        raise ValueError('v3 audit did not return a score and manifest')
    if manifest.get('policy') != 'gp' or manifest.get('contract_version') != EXECUTION_CONTRACT:
        raise ValueError('GP rollout policy/contract mismatch')
    tree_value, payload = load_tree(tree_file)
    if tree_hash(tree_value) != tree_hash(tree):
        raise ValueError('saved GP tree differs from evaluated tree')
    if manifest.get('tree_file_sha256') != digest(tree_file) or manifest.get('gp_tree') != payload:
        raise ValueError('GP tree provenance mismatch')
    if manifest.get('contract_protocol_sha256') != reference_manifest.get('contract_protocol_sha256'):
        raise ValueError('GP/VNSME contract protocol mismatch')
    for key in ('contract_version', 'initial_locations', 'initial_location_seed',
                'python_version', 'packages'):
        if manifest.get(key) != reference_manifest.get(key):
            raise ValueError(f'GP/VNSME compatibility mismatch: {key}')
    if runtime_fingerprint(manifest) != runtime_fingerprint(reference_manifest):
        raise ValueError('GP/VNSME simulator/scorer source mismatch')
    try:
        value = float(score['total_score'])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError('audited J is missing or not numeric') from exc
    if not math.isfinite(value) or value < 0:
        raise ValueError('audited J must be finite and nonnegative')
    return value


# Ghi chú: Tạo lệnh chạy GP với contract V3 chỉ định rõ, dữ liệu đã chọn và giới hạn thời gian.
def build_runner_command(tree_file, metadata, output, simulator_seed, wall_seconds):
    inputs = metadata['input_paths']
    return [sys.executable, '-B', str(ROOT/'run_dpdp_insertion.py'),
            '--policy', 'gp', '--contract-version', EXECUTION_CONTRACT,
            '--tree', str(tree_file), '--instance-directory',
            str(Path(inputs['orders']).parent), '--data-directory',
            str(Path(inputs['factories']).parent), '--seed', str(simulator_seed),
            '--wall-seconds', str(wall_seconds), '--max-simulation-seconds',
            str(7*86400), '--output', str(output)]


class V3RolloutEvaluator:
    """Run one isolated v3 GP rollout and re-audit it before exposing J.

    This evaluator has no v2 cache imports, no legacy contract default, no
    VNSME/Java code path, and no retries. A failed audit stays invalid.
    """

    # Ghi chú: Tạo vùng output riêng và giữ reference, metadata, seed, ngân sách cùng cache V3 cho thí nghiệm.
    def __init__(self, directory, *, dataset_root, reference_path, reference_sha256,
                 reference_summary, reference_scores, metadata_by_instance,
                 split_protocol_sha256, source_manifest_sha256, gp_rng_seed,
                 simulator_seed, runner_wall_seconds, supervisor_wall_seconds,
                 total_wall_seconds, cleanup_reserve_seconds, max_processes,
                 started_monotonic, invalid_fitness=INVALID_FITNESS):
        self.directory = Path(directory).resolve()
        self.directory.mkdir(parents=True, exist_ok=False)
        for name in ('models', 'rollouts', 'supervision'):
            (self.directory/name).mkdir()
        self.dataset_root = Path(dataset_root).resolve()
        self.reference_path = Path(reference_path).resolve()
        self.reference_sha256 = reference_sha256
        self.reference_summary = reference_summary
        self.reference_scores = reference_scores
        self.metadata_by_instance = metadata_by_instance
        self.split_protocol_sha256 = split_protocol_sha256
        self.source_manifest_sha256 = source_manifest_sha256
        self.gp_rng_seed = int(gp_rng_seed)
        self.simulator_seed = int(simulator_seed)
        self.runner_wall_seconds = float(runner_wall_seconds)
        self.supervisor_wall_seconds = float(supervisor_wall_seconds)
        self.total_wall_seconds = float(total_wall_seconds)
        self.cleanup_reserve_seconds = float(cleanup_reserve_seconds)
        self.max_processes = int(max_processes)
        self.started_monotonic = float(started_monotonic)
        self.deadline = self.started_monotonic + self.total_wall_seconds
        self.invalid_fitness = float(invalid_fitness)
        self.process_count = 0
        self.records = []
        self.sources = source_fingerprint()
        self.contract = contract_metadata(EXECUTION_CONTRACT)
        self.cache_directory = self.directory/'cache_v3'
        self.cache_directory.mkdir()
        self.cache_path = self.cache_directory/'cache_index.json'
        self.cache = dict(schema=CACHE_SCHEMA, entries={})
        self._write_cache()
        self.records_path = self.directory/'evaluation_records.jsonl'

    # Ghi chú: Ghi artifact JSON mới, từ chối ghi đè file đã tồn tại.
    def _write_json_new(self, path, value):
        with Path(path).open('x', encoding='utf-8', newline='\n') as handle:
            json.dump(value, handle, indent=2, sort_keys=True, allow_nan=False, default=str)
            handle.write('\n')

    # Ghi chú: Ghi index cache qua file tạm rồi replace để giảm nguy cơ file chính bị ghi dở.
    def _write_cache(self):
        temp = self.cache_path.with_suffix('.tmp')
        with temp.open('w', encoding='utf-8', newline='\n') as handle:
            json.dump(self.cache, handle, indent=2, sort_keys=True, allow_nan=False, default=str)
            handle.write('\n')
            handle.flush()
        temp.replace(self.cache_path)

    # Ghi chú: Gom ngữ nghĩa cây, source, dữ liệu, baseline, seed và ngân sách vào context của phép đánh giá.
    def _context(self, tree, instance):
        if instance not in self.metadata_by_instance:
            raise ValueError(f'instance_{instance} is outside configured development IDs')
        meta = self.metadata_by_instance[instance]
        files = meta['input_paths']
        return dict(
            namespace=CACHE_SCHEMA,
            fitness_version=FITNESS_VERSION,
            contract_version=EXECUTION_CONTRACT,
            contract_protocol_sha256=self.contract['contract_protocol_sha256'],
            instance=instance,
            tree_sha256=tree_hash(tree),
            tree_semantics=dict(features=list(FEATURES), primitives=list(PRIMITIVES),
                                numeric_policy=NUMERIC_POLICY, limits=vars(Limits())),
            simulator_and_scorer_sources=self.sources,
            data=dict(source_manifest_sha256=meta['source_manifest_sha256'],
                      files={k: {'path': str(Path(v).resolve()), 'sha256': meta['data_sha256'][k]}
                             for k, v in sorted(files.items())}),
            reference=dict(path=str(self.reference_path), sha256=self.reference_sha256,
                           instance_J=str(self.reference_scores[instance])),
            split_protocol_sha256=self.split_protocol_sha256,
            source_manifest_sha256=self.source_manifest_sha256,
            gp_rng_seed=self.gp_rng_seed,
            simulator_seed=self.simulator_seed,
            budgets=dict(runner_wall_seconds=self.runner_wall_seconds,
                         supervisor_wall_seconds=self.supervisor_wall_seconds,
                         total_wall_seconds=self.total_wall_seconds,
                         cleanup_reserve_seconds=self.cleanup_reserve_seconds,
                         max_rollout_processes=self.max_processes,
                         simulation_horizon_seconds=7*86400),
            settings=dict(dispatch_step_seconds=600, docking_seconds=1800,
                          loading_seconds_per_quantity=240, unloading_seconds_per_quantity=240,
                          lambda_=10000, invalid_fitness=self.invalid_fitness),
            python=dict(version=sys.version, executable=str(Path(sys.executable).resolve()),
                        packages={n: importlib.metadata.version(n) for n in ('dvrpsim', 'simpy')}),
        )

    # Ghi chú: Kiểm ngân sách thời gian toàn thí nghiệm, có thể giữ lại thời gian dự phòng để dọn tiến trình.
    def _check_deadline(self, reserve=0):
        remaining = self.deadline - time.perf_counter()
        if remaining <= reserve:
            raise RolloutBudgetExceeded('global development-smoke wall budget exhausted')
        return remaining

    # Ghi chú: Yêu cầu đủ bằng chứng giám sát và tính hash từng file.
    def _supervision_hashes(self, directory):
        names = ('supervision.json', 'heartbeats.jsonl', 'process.log')
        result = {}
        for name in names:
            path = Path(directory)/name
            if not path.is_file():
                raise ValueError(f'supervisor evidence missing: {name}')
            result[name] = digest(path)
        return result

    # Ghi chú: Yêu cầu đủ log/manifest/result/decision/cam kết/audit và ghi hash để cache kiểm tra lại.
    def _artifact_hashes(self, run):
        names = ('simulation.log', 'manifest.json', 'result.json', 'decisions.json',
                 'commitments.json', 'v3_independent_audit.json')
        result = {}
        for name in names:
            path = Path(run)/name
            if not path.is_file():
                raise ValueError(f'rollout evidence missing: {name}')
            result[name] = digest(path)
        return result

    # Ghi chú: Kiểm tiến trình kết thúc sạch, audit độc lập rollout và chuẩn hóa J theo reference cùng instance.
    def _audit(self, run, supervision, instance, tree, tree_file, expected_context):
        self._check_deadline(reserve=0)
        supervisor = read(Path(supervision)/'supervision.json')
        if (not supervisor.get('valid_supervision') or supervisor.get('state') != 'EXITED'
                or supervisor.get('exit_code') != 0 or supervisor.get('gaps')
                or supervisor.get('remaining_job_processes')):
            raise ValueError('rollout process was not cleanly supervised')
        result = read(Path(run)/'result.json')
        if not result.get('valid') or not result.get('score'):
            raise ValueError('runner result invalid or score missing')
        score, manifest = audit_run(run, instance, policy='gp')
        reference_row = next((r for r in self.reference_summary['records']
                              if r['instance'] == instance), None)
        if reference_row is None:
            raise ValueError('VNSME reference instance missing')
        reference_run = self.reference_summary.get('resolved_run_directories', {}).get(
            str(instance), reference_row['run_directory'])
        reference_manifest = read(Path(reference_run)/'manifest.json')
        value = assess_rollout(score, manifest, tree, tree_file, reference_manifest)
        if value != float(score['total_score']):
            raise ValueError('audited J conversion mismatch')
        ratio = value / float(self.reference_scores[instance])
        if not math.isfinite(ratio) or ratio < 0:
            raise ValueError('normalized v3 ratio is invalid')
        independent = dict(status='PASS', policy='gp', instance=instance,
                           contract_version=EXECUTION_CONTRACT, fitness_version=FITNESS_VERSION,
                           J=str(score['total_score']), VNSME_J=str(self.reference_scores[instance]),
                           normalized_ratio=ratio, tree_sha256=tree_hash(tree),
                           cache_context_sha256=hashlib.sha256(json.dumps(
                               expected_context, sort_keys=True, separators=(',', ':'),
                               allow_nan=False).encode()).hexdigest())
        audit_path = Path(run)/'v3_independent_audit.json'
        if audit_path.exists():
            if read(audit_path) != independent:
                raise ValueError('saved v3 independent audit record mismatch')
        else:
            self._write_json_new(audit_path, independent)
        return value, ratio, manifest, independent

    # Ghi chú: Đối chiếu hash và audit lại rollout đã cache trước khi tái sử dụng điểm.
    def _verify_cache_entry(self, key, context, tree, instance, tree_file, entry):
        verify_cache_provenance(entry, key, context)
        run = Path(entry['run_directory'])
        supervision = Path(entry['supervision_directory'])
        for name, sha in entry['artifact_sha256'].items():
            if digest(run/name) != sha:
                raise ValueError(f'cached rollout evidence checksum mismatch: {name}')
        for name, sha in entry['supervision_sha256'].items():
            if digest(supervision/name) != sha:
                raise ValueError(f'cached supervision evidence checksum mismatch: {name}')
        value, ratio, manifest, _ = self._audit(run, supervision, instance, tree, tree_file, context)
        if str(value) != str(entry['benchmark_J']) or ratio != entry['normalized_ratio']:
            raise ValueError('cached audited score differs from cache record')
        return value, ratio, manifest

    # Ghi chú: Giữ record trong bộ nhớ và nối vào JSONL để lưu vết mỗi yêu cầu đánh giá.
    def _append_record(self, record):
        self.records.append(record)
        with self.records_path.open('a', encoding='utf-8', newline='\n') as handle:
            handle.write(json.dumps(record, sort_keys=True, allow_nan=False, default=str)+'\n')

    # Ghi chú: Đánh giá một cặp cây/instance: thử cache đã kiểm chứng, hoặc chạy rollout mới có supervisor rồi audit; lỗi nhận penalty.
    def evaluate(self, tree, instance):
        started = time.perf_counter()
        try:
            self._check_deadline()
            if instance not in self.metadata_by_instance:
                raise ValueError(f'instance_{instance} is outside configured development IDs')
            context = self._context(tree, instance)
            key = cache_key(tree, context)
            tree_file = self.directory/'models'/f'{tree_hash(tree)}.json'
            if tree_file.exists():
                existing, _ = load_tree(tree_file)
                if tree_hash(existing) != tree_hash(tree):
                    raise ValueError('existing v3 model file mismatch')
            else:
                save_tree(tree_file, tree, training=dict(tree_sha256=tree_hash(tree),
                                                         contract_version=EXECUTION_CONTRACT,
                                                         fitness_version=FITNESS_VERSION))
            # Ghi chú: Cache hit vẫn phải kiểm hash và audit lại bằng chứng trước khi trả điểm.
            if key in self.cache['entries']:
                entry = self.cache['entries'][key]
                value, ratio, _ = self._verify_cache_entry(key, context, tree, instance, tree_file, entry)
                record = dict(cache_key=key, context=context, tree_sha256=tree_hash(tree),
                              instance=instance, valid=True, status='complete',
                              benchmark_J=str(value), fitness=ratio, normalized_ratio=ratio,
                              cache_hit=True, process_started=False,
                              run_directory=entry['run_directory'],
                              supervision_directory=entry['supervision_directory'],
                              request_wall_seconds=time.perf_counter()-started)
                self._append_record(record)
                return record
            remaining = self._check_deadline(reserve=self.cleanup_reserve_seconds)
            # Ghi chú: Giới hạn số rollout mới để toàn bộ thí nghiệm không vượt ngân sách đã khóa.
            if self.process_count >= self.max_processes:
                raise RolloutBudgetExceeded('maximum new GP rollout process count reached')
            timeout = min(self.supervisor_wall_seconds, remaining-self.cleanup_reserve_seconds)
            if timeout <= 0:
                raise RolloutBudgetExceeded('insufficient global budget for another rollout')

            attempt = self.process_count
            suffix = f'{key[:16]}_p{attempt:02d}'
            run = self.directory/'rollouts'/suffix
            supervision = self.directory/'supervision'/suffix
            meta = self.metadata_by_instance[instance]
            tree_file_sha256 = digest(tree_file)
            command = build_runner_command(tree_file, meta, run,
                                           self.simulator_seed,
                                           self.runner_wall_seconds)
            record = dict(cache_key=key, context=context, tree_sha256=tree_hash(tree),
                          tree_file_sha256=tree_file_sha256, expression=tree.text(),
                          instance=instance, valid=False, status='invalid', benchmark_J=None,
                          fitness=self.invalid_fitness, normalized_ratio=None,
                          cache_hit=False, process_started=True, command=command,
                          run_directory=str(run), supervision_directory=str(supervision),
                          error=None)
            self.process_count += 1
            process_started = time.perf_counter()
            try:
                from dpdp_v3_supervisor import supervise
                job = supervise(command, supervision, timeout,
                                interval=0.5, gap_limit=5.0)
                record['supervision'] = {k: v for k, v in job.items()
                                         if k not in ('samples', 'command')}
                if not job.get('valid_supervision') or job.get('state') != 'EXITED' or job.get('exit_code') != 0:
                    record['status'] = 'timeout' if job.get('state') == 'TIMEOUT' else 'invalid'
                    record['error'] = f"supervised rollout ended in {job.get('state')}"
                else:
                    value, ratio, _, _ = self._audit(run, supervision, instance,
                                                     tree, tree_file, context)
                    artifacts = self._artifact_hashes(run)
                    supervision_hashes = self._supervision_hashes(supervision)
                    record.update(valid=True, status='complete', benchmark_J=str(value),
                                  fitness=ratio, normalized_ratio=ratio,
                                  artifact_sha256=artifacts,
                                  supervision_sha256=supervision_hashes)
                    entry = dict(cache_key=key, context=context, valid=True,
                                 benchmark_J=str(value), normalized_ratio=ratio,
                                 run_directory=str(run), supervision_directory=str(supervision),
                                 artifact_sha256=artifacts,
                                 supervision_sha256=supervision_hashes,
                                 tree_sha256=tree_hash(tree), tree_file_sha256=tree_file_sha256)
                    self.cache['entries'][key] = entry
                    self._write_cache()
            except RolloutBudgetExceeded:
                record['status'] = 'budget_exhausted'
                record['error'] = 'global development-smoke wall budget exhausted during rollout audit'
                record['benchmark_J'] = None
                record['fitness'] = self.invalid_fitness
                record['normalized_ratio'] = None
                record.update(process_wall_seconds=time.perf_counter()-process_started,
                              request_wall_seconds=time.perf_counter()-started)
                self._append_record(record)
                raise
            except Exception as exc:
                record['status'] = 'audit_failed' if run.exists() else 'invalid'
                record['error'] = f'{type(exc).__name__}: {exc}'
                record['benchmark_J'] = None
                record['fitness'] = self.invalid_fitness
                record['normalized_ratio'] = None
            record.update(process_wall_seconds=time.perf_counter()-process_started,
                          request_wall_seconds=time.perf_counter()-started)
            self._append_record(record)
            return record
        except RolloutBudgetExceeded:
            raise
        except (TreeError, ValueError, OSError, KeyError, TypeError) as exc:
            record = dict(instance=instance, valid=False, status='invalid',
                          benchmark_J=None, fitness=self.invalid_fitness,
                          normalized_ratio=None, cache_hit=False, process_started=False,
                          error=f'{type(exc).__name__}: {exc}',
                          request_wall_seconds=time.perf_counter()-started)
            self._append_record(record)
            return record
