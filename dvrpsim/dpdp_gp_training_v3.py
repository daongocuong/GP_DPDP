"""Protocol-enforced GP v3 evolution and development-smoke execution."""
import hashlib
import importlib.metadata
import json
import math
from pathlib import Path
import random
import sys
import time

from dpdp_contract import EXECUTION_CONTRACT, contract_metadata
from dpdp_dataset import validate_instance
from dpdp_relocation import load_relocation
from dpdp_gp import (Limits, breed, canonical, initial_population, save_tree,
                     validate_tree)
from dpdp_gp_rollout_v3 import (INVALID_FITNESS, RolloutBudgetExceeded,
                               V3RolloutEvaluator, digest, source_fingerprint)
from dpdp_vnsme_reference_v3 import (FITNESS_VERSION, load_reference, metadata,
                                     read)

ROOT = Path(__file__).resolve().parent
DEFAULT_PROTOCOL = ROOT/'protocols/dpdp_gp_vnsme_v3_dev_smoke_v1.json'
DEFAULT_DATASET = ROOT/'datasets/xingtian/e4ef3a1c92d19d1d08c3ef0e2156b6fecefdbe04'
EXPECTED_REFERENCE_IDS = frozenset({2, 3, 4, 5, 6})
DEVELOPMENT_IDS = frozenset({2, 3, 4, 5, 6})
SEALED_IDS = frozenset({7, 8, 15, 16})


class SealedAccessTracker:
    """Track application-level instance requests; this is not OS file tracing."""
    # Ghi chú: Khởi tạo danh sách ID đã kiểm tra, bị từ chối và được yêu cầu rollout.
    def __init__(self):
        self.checked_ids = []
        self.rejected_ids = []
        self.rollout_ids = []

    # Ghi chú: Chỉ nhận development IDs 2–6 và ghi nhận các yêu cầu; đây là guard ứng dụng, không phải theo dõi file của hệ điều hành.
    def require(self, ids, *, rollout=False):
        values = tuple(ids)
        self.checked_ids.extend(values)
        denied = [instance for instance in values
                  if instance in SEALED_IDS or instance not in DEVELOPMENT_IDS]
        if denied:
            self.rejected_ids.extend(denied)
            raise PermissionError(f'sealed or non-development instance request rejected: {denied}')
        if rollout:
            self.rollout_ids.extend(values)
        return values

    # Ghi chú: Xuất lịch sử kiểm ID cùng giới hạn phạm vi bằng chứng của tracker.
    def report(self):
        return dict(guard='trainer instance-ID allowlist',
                    checked_ids=list(self.checked_ids),
                    rejected_ids=list(self.rejected_ids),
                    rollout_ids=list(self.rollout_ids),
                    os_level_file_open_tracing=False,
                    evidence_scope='trainer/reference/audit instance requests only')


# Ghi chú: Chuẩn hóa JSON để so sánh cấu hình, không cho phép NaN hoặc vô cực.
def _canonical_json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


# Ghi chú: Chỉ nhận cấu hình smoke/pilot đã review; khóa split, seed, ngân sách và ngăn bật official training.
def validate_protocol_document(protocol):
    """Reject protocol drift or attempts to enable the official workflow."""
    pilot = protocol.get('protocol') == 'dpdp-gp-vnsme-v3-dev-pilot-v1'
    if not pilot and protocol.get('protocol') != 'dpdp-gp-vnsme-v3-dev-smoke-v1':
        raise ValueError('unsupported GP v3 protocol')
    if protocol.get('status') != ('DEVELOPMENT_PILOT_ONLY' if pilot else 'DEVELOPMENT_SMOKE_ONLY') or protocol.get('official_training_enabled') is not False:
        raise ValueError('protocol does not explicitly disable official training')
    if protocol.get('contract_version') != EXECUTION_CONTRACT or protocol.get('fitness_version') != FITNESS_VERSION:
        raise ValueError('contract or fitness version mismatch')
    if protocol.get('reference_summary_sha256') != 'ebffa9d2f85d34d4a87f74303b43df90dd6695b66c3bd4540fd9fd423e324847':
        raise ValueError('canonical historical reference hash mismatch')
    roles = protocol.get('locked_roles', {})
    if (roles.get('train') != [2, 3, 4, 5] or roles.get('validation') != [6]
            or roles.get('sealed') != [7, 8, 15, 16]):
        raise ValueError('locked 50-order roles/sealed IDs mismatch')
    smoke = protocol.get('pilot' if pilot else 'smoke', {})
    expected = dict(train_instances_subset=[2, 3], validation_instances=[], population=2,
                    generations=1, gp_rng_seed=20261110, simulator_seed=0,
                    max_new_rollout_processes=8, max_total_wall_seconds=270,
                    max_runner_wall_seconds=20, max_supervisor_wall_seconds=24,
                    cleanup_reserve_seconds=7)
    if pilot:
        expected.update(train_instances_subset=[2,3,4,5], validation_instances=[6],
                        population=4, generations=2, gp_rng_seed=20261111,
                        max_new_rollout_processes=50, max_total_wall_seconds=3600,
                        max_runner_wall_seconds=120, max_supervisor_wall_seconds=125,
                        cleanup_reserve_seconds=15)
    if smoke != expected:
        raise ValueError('development smoke settings differ from reviewed bounded protocol')
    if protocol.get('resume') != 'unsupported; trainer must reject resume requests and create a new output directory':
        raise ValueError('resume policy mismatch')
    fitness = protocol.get('training_fitness', {})
    if (fitness.get('formula') != 'arithmetic mean of J_GP_v3(i) / J_VNSME_v3(i) over exactly the configured training instances'
            or fitness.get('optimization') != 'minimize'
            or fitness.get('invalid_fitness_penalty') != INVALID_FITNESS
            or fitness.get('smoke_scope') != ('full development train only; not official study' if pilot else 'subset diagnostic only; not official train fitness')):
        raise ValueError('fitness definition/penalty mismatch')
    selection = protocol.get('selection', {})
    if selection.get('validation_used_for_evolution') is not False or selection.get('smoke_validation_enabled') is not False:
        raise ValueError('smoke must not consult validation')
    if pilot and selection != PILOT_SELECTION:
        raise ValueError('pilot selection policy mismatch')
    evolution = protocol.get('evolution', {})
    if (evolution.get('tournament') != 3 or evolution.get('crossover_rate') != 0.8
            or evolution.get('mutation_rate') != 0.3 or evolution.get('elitism') != 1
            or evolution.get('tree_limits') != vars(Limits())):
        raise ValueError('evolution parameters differ from reviewed protocol')
    cache = protocol.get('cache', {})
    if cache.get('namespace') != 'gp-fitness-vnsme-v3':
        raise ValueError('v3 cache namespace mismatch')
    if pilot:
        if cache.get('reuse') != 'new run-local cache only; no historical cache import':
            raise ValueError('pilot cache reuse policy mismatch')
        if protocol.get('contract_protocol_sha256') != contract_metadata(EXECUTION_CONTRACT)['contract_protocol_sha256']:
            raise ValueError('pilot contract pin mismatch')
        if not protocol.get('source_sha256') or not protocol.get('relocation_config_sha256'):
            raise ValueError('pilot source/relocation pins missing')
    return protocol


PILOT_SELECTION = dict(
    validation_policy='validation ratio first; then train fitness, node count and canonical tree',
    validation_used_for_evolution=False, smoke_validation_enabled=False,
    schedule='once after all generations complete; no validation on partial/failed run',
    candidates='top 2 unique valid trees across all completed generations ranked by train fitness, node count, canonical tree',
    max_candidates=2,
    tie_break_order=['validation_ratio_ascending', 'train_fitness_ascending',
                     'node_count_ascending', 'canonical_tree_ascending'])


# Ghi chú: Yêu cầu danh sách ID development không rỗng, không trùng và không chứa sealed test.
def require_experiment_ids(ids, tracker=None, *, rollout=False):
    ids = tuple(ids)
    if tracker is not None:
        tracker.require(ids, rollout=rollout)
    elif any(i in SEALED_IDS or i not in DEVELOPMENT_IDS for i in ids):
        raise PermissionError(f'sealed or non-development instance request rejected: {ids}')
    if not ids or len(ids) != len(set(ids)):
        raise ValueError('instance IDs must be nonempty and unique')
    return ids


# Ghi chú: Kiểm reference đúng V3, đủ tập ID mong đợi và đúng vai trò train/validation.
def validate_reference_summary(summary, scores, expected=EXPECTED_REFERENCE_IDS):
    if (summary.get('fitness_version') != FITNESS_VERSION
            or summary.get('contract_version') != EXECUTION_CONTRACT
            or not summary.get('valid')):
        raise ValueError('mixed, v2 or invalid reference summary')
    rows = summary.get('records', [])
    ids = [row.get('instance') for row in rows]
    if len(ids) != len(set(ids)) or set(ids) != set(expected):
        raise ValueError('canonical reference ID set mismatch')
    roles = {row['instance']: row.get('role') for row in rows}
    if any(roles[i] != ('validation' if i == 6 else 'train') for i in expected):
        raise ValueError('canonical reference role mismatch')
    if set(scores) != set(expected):
        raise ValueError('canonical reference score set mismatch')
    return True


# Ghi chú: Fitness cần giảm là trung bình đều J_GP/J_VNSME trên train; thiếu hoặc sai rollout thì cả cây nhận penalty.
def aggregate_training(instance_records, baseline_scores, train_ids,
                       penalty=INVALID_FITNESS):
    """Minimized equal-weight mean of audited GP J / canonical VNSME J."""
    train_ids = tuple(train_ids)
    if not train_ids or len(train_ids) != len(set(train_ids)):
        raise ValueError('training IDs must be nonempty and unique')
    by_id = {}
    for record in instance_records:
        instance = record.get('instance')
        if instance in by_id:
            raise ValueError(f'duplicate GP rollout for instance_{instance}')
        by_id[instance] = record
    ratios = []
    invalid = []
    if set(by_id) != set(train_ids):
        invalid.extend(i for i in train_ids if i not in by_id)
    for instance in train_ids:
        record = by_id.get(instance)
        try:
            baseline = float(baseline_scores[instance])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f'missing VNSME denominator for instance_{instance}') from exc
        if not math.isfinite(baseline) or baseline <= 0:
            raise ValueError('VNSME denominator must be finite and positive')
        if record is None or not record.get('valid') or record.get('benchmark_J') is None:
            ratios.append(None)
            invalid.append(instance)
            continue
        try:
            score = float(record['benchmark_J'])
        except (TypeError, ValueError):
            score = float('nan')
        if not math.isfinite(score) or score < 0:
            ratios.append(None)
            invalid.append(instance)
            continue
        ratio = score / baseline
        if not math.isfinite(ratio) or ratio < 0:
            ratios.append(None)
            invalid.append(instance)
        else:
            ratios.append(ratio)
    valid = not invalid and all(ratio is not None for ratio in ratios)
    return dict(valid=valid,
                fitness=sum(ratios)/len(train_ids) if valid else float(penalty),
                ratios=ratios,
                aggregation='arithmetic_mean_of_J_GP_v3_over_J_VNSME_v3',
                optimization='minimize', fitness_version=FITNESS_VERSION,
                contract_version=EXECUTION_CONTRACT,
                training_instances=list(train_ids), invalid_instances=sorted(set(invalid)))


# Ghi chú: Khóa chọn cây sau tiến hóa: validation ratio → train fitness → số node → biểu diễn cây.
def validation_selection_key(record, baseline_J, train_fitness, tree):
    """Draft rule for its single 50-order validation instance: ratio, train, size, tree."""
    if not record.get('valid') or record.get('benchmark_J') is None:
        return None
    try:
        value, baseline = float(record['benchmark_J']), float(baseline_J)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(value) or value < 0 or not math.isfinite(baseline) or baseline <= 0:
        return None
    nodes, _ = validate_tree(tree)
    return value/baseline, float(train_fitness), nodes, canonical(tree)


# Ghi chú: Chọn candidate có selection_key nhỏ nhất, trả None nếu không có cây đủ điều kiện.
def choose_candidate(candidates):
    eligible = [candidate for candidate in candidates
                if candidate.get('selection_key') is not None]
    return min(eligible, key=lambda candidate: candidate['selection_key']) if eligible else None


# Ghi chú: Chấm shortlist sau tiến hóa trên validation riêng; điểm validation không được đưa vào breeding.
def select_with_validation(trees, train_ids, validation_id, evaluator,
                           baseline_scores, penalty=INVALID_FITNESS):
    """Apply the locked single-instance validation rule after evolution only."""
    if validation_id in train_ids or validation_id not in DEVELOPMENT_IDS:
        raise ValueError('validation ID must be a separate development instance')
    candidates = []
    for tree in trees:
        train_records, aggregate = evaluate_training_tree(
            tree, train_ids, evaluator, baseline_scores, penalty)
        if not aggregate['valid']:
            continue
        validation_record = evaluator.evaluate(tree, validation_id)
        key = validation_selection_key(validation_record,
                                       baseline_scores[validation_id],
                                       aggregate['fitness'], tree)
        candidates.append(dict(tree=tree, train=aggregate,
                               train_records=train_records,
                               validation=validation_record,
                               selection_key=key))
    return choose_candidate(candidates), candidates


# Ghi chú: Chạy cây trên các ID train rồi tổng hợp fitness; hàm này không nhận validation ID riêng.
def evaluate_training_tree(tree, train_ids, evaluator, baseline_scores, penalty=INVALID_FITNESS):
    """Evaluate training IDs only; validation is intentionally not an input."""
    train_ids = require_experiment_ids(train_ids)
    records = [evaluator.evaluate(tree, instance) for instance in train_ids]
    return records, aggregate_training(records, baseline_scores, train_ids, penalty)


# Ghi chú: Lưu record của một thế hệ vào generation_N.json bằng thao tác ghi qua file tạm.
def write_generation(directory, record):
    path = Path(directory)/f"generation_{record['generation']}.json"
    _atomic_json(path, record)
    return path


# Ghi chú: Ghi JSON vào file tạm rồi replace file đích để tránh để lại JSON chính bị ghi dở.
def _atomic_json(path, value):
    path = Path(path)
    temp = path.with_suffix(path.suffix+'.tmp')
    with temp.open('w', encoding='utf-8', newline='\n') as handle:
        json.dump(value, handle, indent=2, sort_keys=True, allow_nan=False, default=str)
        handle.write('\n')
        handle.flush()
    temp.replace(path)


# Ghi chú: Kiểm SHA-256 của file và sidecar nếu có, trả đường dẫn tuyệt đối đã kiểm.
def _check_file_pin(path, expected_sha, label):
    path = Path(path).resolve()
    actual = digest(path)
    if actual != expected_sha:
        raise ValueError(f'{label} checksum mismatch')
    sidecar = path.with_suffix(path.suffix+'.sha256')
    if sidecar.exists() and sidecar.read_text(encoding='utf-8').split()[0] != actual:
        raise ValueError(f'{label} checksum sidecar mismatch')
    return path


# Ghi chú: Kiểm protocol/source pins, split, dataset, reference và môi trường trước khi chuẩn bị metadata cho rollout.
def _load_locked_inputs(protocol_path, dataset_root, tracker, relocation_config=None):
    protocol_path = Path(protocol_path).resolve()
    protocol_hash = digest(protocol_path)
    sidecar = protocol_path.with_suffix(protocol_path.suffix+'.sha256')
    if not sidecar.is_file() or sidecar.read_text(encoding='utf-8').split()[0] != protocol_hash:
        raise ValueError('development smoke protocol checksum sidecar mismatch')
    protocol = validate_protocol_document(json.loads(protocol_path.read_text(encoding='utf-8')))
    # Ghi chú: Source pin so sánh hash byte: sửa comment cũng khiến protocol pilot cũ không còn khớp.
    if 'pilot' in protocol and source_fingerprint() != protocol['source_sha256']:
        raise ValueError('pilot source provenance differs from locked protocol')
    dataset_root = Path(dataset_root).resolve()
    expected_dataset = (ROOT/'datasets/xingtian'/protocol['dataset_commit']).resolve()
    if dataset_root != expected_dataset:
        raise ValueError('dataset root differs from the pinned development dataset')
    split_path = (ROOT/protocol['split_protocol']).resolve()
    _check_file_pin(split_path, protocol['split_protocol_sha256'], 'split protocol')
    split_hash = digest(split_path)
    split = read(split_path)
    if split['roles']['50_orders']['train'] != protocol['locked_roles']['train']:
        raise ValueError('official split train IDs disagree with development protocol')
    if split['roles']['50_orders']['validation'] != protocol['locked_roles']['validation']:
        raise ValueError('official split validation ID disagrees with development protocol')
    source_path = (ROOT/protocol['source_manifest']).resolve()
    _check_file_pin(source_path, protocol['source_manifest_sha256'], 'source manifest')
    source_hash = digest(source_path)
    if source_path.parent.resolve() != dataset_root:
        raise ValueError('source manifest is outside pinned dataset root')
    reference_path = (ROOT/protocol['reference_summary']).resolve()
    if reference_path != (ROOT/'vnsme_runs/v3_reference_canonical_2_6_20261110_r1/combined_reference/summary.json').resolve():
        raise ValueError('protocol points to an unexpected VNSME reference')
    if digest(reference_path) != protocol['reference_summary_sha256']:
        raise ValueError('canonical VNSME v3 reference checksum mismatch')
    # Load/audit exact full canonical ID set before any rollout; the smoke itself
    # later uses only its configured train subset and never validation instance 6.
    relocation = None
    relocation_path = None
    if protocol.get('relocation_config'):
        relocation_path = _check_file_pin(ROOT/protocol['relocation_config'],
                                          protocol['relocation_config_sha256'], 'relocation config')
        if relocation_config and Path(relocation_config).resolve() != relocation_path:
            raise ValueError('relocation override differs from pinned protocol config')
        relocation = load_relocation(relocation_path)
    elif relocation_config:
        relocation_path = Path(relocation_config).resolve()
        relocation = load_relocation(relocation_path)
    baseline_scores, reference_summary = load_reference(reference_path, EXPECTED_REFERENCE_IDS, relocation)
    validate_reference_summary(reference_summary, baseline_scores)
    if any(not math.isfinite(float(baseline_scores[i])) or float(baseline_scores[i]) <= 0
           for i in EXPECTED_REFERENCE_IDS):
        raise ValueError('canonical VNSME denominator is not finite and positive')
    pilot = 'pilot' in protocol
    smoke = protocol['pilot' if pilot else 'smoke']
    train_ids = require_experiment_ids(smoke['train_instances_subset'], tracker)
    validation_ids = require_experiment_ids(smoke['validation_instances'], tracker) if smoke['validation_instances'] else ()
    if not set(train_ids) <= set(protocol['locked_roles']['train']):
        raise ValueError('smoke subset is not contained in locked training IDs')
    if validation_ids and not pilot:
        raise ValueError('this development smoke is locked to no validation evaluation')
    metadata_by_instance = {}
    benchmark = dataset_root/'benchmark'
    for instance in train_ids + validation_ids:
        meta = metadata(instance)
        if meta['role'] != ('validation' if instance in validation_ids else 'train') or meta['source_manifest_sha256'] != source_hash:
            raise ValueError(f'instance_{instance} metadata does not match training/source manifest')
        validate_instance(benchmark/f'instance_{instance}', benchmark)
        metadata_by_instance[instance] = meta
    contract = contract_metadata(EXECUTION_CONTRACT)
    packages = {name: importlib.metadata.version(name) for name in ('dvrpsim', 'simpy')}
    import dvrpsim
    if not dvrpsim.__file__ or not Path(dvrpsim.__file__).resolve().is_relative_to(ROOT/'src'):
        raise ValueError('dvrpsim editable package does not resolve to current repository src')
    for row in reference_summary['records']:
        directory = reference_summary.get('resolved_run_directories', {}).get(str(row['instance']),row['run_directory'])
        manifest = read(Path(directory)/'manifest.json')
        if manifest['python_version'] != sys.version or manifest['packages'] != packages:
            raise ValueError('current Python/packages differ from canonical reference environment')
    snapshot = dict(protocol=protocol, protocol_sha256=protocol_hash,
                    split_protocol_path=str(split_path), split_protocol_sha256=split_hash,
                    source_manifest_path=str(source_path), source_manifest_sha256=source_hash,
                    reference_path=str(reference_path),
                    reference_sha256=protocol['reference_summary_sha256'],
                    reference_scores={str(i): baseline_scores[i] for i in sorted(EXPECTED_REFERENCE_IDS)},
                    contract_protocol_sha256=contract['contract_protocol_sha256'],
                    train_instances=list(train_ids), validation_instances=list(validation_ids),
                    dataset_root=str(dataset_root))
    snapshot['runtime'] = dict(executable=sys.executable, python=sys.version,
                              packages=packages, dvrpsim_file=dvrpsim.__file__)
    if relocation:
        snapshot['relocation_config'] = str(relocation_path)
        snapshot['relocation_config_sha256'] = digest(relocation_path)
        snapshot['historical_execution_paths'] = {str(r['instance']): r['run_directory'] for r in reference_summary['records']}
        snapshot['resolved_run_directories'] = reference_summary['resolved_run_directories']
    return snapshot, baseline_scores, reference_summary, metadata_by_instance


# Ghi chú: Kiểm các đầu vào đã khóa và reference mà không khởi chạy rollout mới; vẫn thực hiện đọc/audit artifact.
def preflight(protocol_path=DEFAULT_PROTOCOL, dataset_root=DEFAULT_DATASET, relocation_config=None):
    tracker = SealedAccessTracker()
    snapshot, _, _, _ = _load_locked_inputs(protocol_path, dataset_root, tracker, relocation_config)
    return dict(status='PREFLIGHT_PASS', rollout_processes_started=0,
                snapshot=snapshot, source_fingerprint=source_fingerprint(),
                sealed_access=tracker.report())


# Ghi chú: Điều phối thí nghiệm development: khóa đầu vào, đánh giá/tiến hóa quần thể, chọn bằng validation nếu là pilot và lưu kết quả.
def run_experiment(output, protocol_path=DEFAULT_PROTOCOL, dataset_root=DEFAULT_DATASET,
                   *, resume=False, prepared_output=False, relocation_config=None):
    if resume:
        raise ValueError('resume is unsupported: exact RNG/config/state restoration is not implemented')
    root = Path(output).resolve()
    if prepared_output:
        if not root.is_dir() or {p.name for p in root.iterdir()} != {'trainer_supervision'}:
            raise ValueError('worker requires a fresh supervisor-owned output; resume is unsupported')
    else:
        root.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    tracker = SealedAccessTracker()
    snapshot = None
    evaluator = None
    generations = []
    candidates = {}
    status = 'failed'
    error = None
    selected = None
    config = None
    protocol_record = None
    try:
        snapshot, baseline_scores, reference_summary, metadata_by_instance = _load_locked_inputs(
            protocol_path, dataset_root, tracker, relocation_config)
        protocol = snapshot['protocol']
        pilot = 'pilot' in protocol
        smoke = protocol['pilot' if pilot else 'smoke']
        config = dict(mode='development_pilot' if pilot else 'development_smoke', contract_version=EXECUTION_CONTRACT,
                      fitness_version=FITNESS_VERSION,
                      population=smoke['population'], generations=smoke['generations'],
                      gp_rng_seed=smoke['gp_rng_seed'], simulator_seed=smoke['simulator_seed'],
                      train_instances=snapshot['train_instances'],
                      validation_instances=snapshot['validation_instances'],
                      locked_train_instances=protocol['locked_roles']['train'],
                      locked_validation_instances=protocol['locked_roles']['validation'],
                      invalid_fitness_penalty=protocol['training_fitness']['invalid_fitness_penalty'],
                      training_fitness=protocol['training_fitness']['formula'],
                      fitness_scope=protocol['training_fitness']['smoke_scope'],
                      validation_used_for_fitness=False,
                      validation_used_for_breeding=False,
                      validation_used_for_selection=pilot,
                      optimization='minimize',
                      evolution=protocol['evolution'],
                      max_new_rollout_processes=smoke['max_new_rollout_processes'],
                      max_total_wall_seconds=smoke['max_total_wall_seconds'],
                      max_runner_wall_seconds=smoke['max_runner_wall_seconds'],
                      max_supervisor_wall_seconds=smoke['max_supervisor_wall_seconds'],
                      resume_supported=False)
        protocol_record = dict(snapshot=snapshot, config=config,
                               source_fingerprint=source_fingerprint(),
                               sealed_access=tracker.report(),
                               started_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()))
        _atomic_json(root/'experiment_protocol.json', protocol_record)
        (root/'generations').mkdir()
        evaluator = V3RolloutEvaluator(
            root/'fitness_v3', dataset_root=dataset_root,
            reference_path=snapshot['reference_path'],
            reference_sha256=snapshot['reference_sha256'],
            reference_summary=reference_summary, reference_scores=baseline_scores,
            metadata_by_instance=metadata_by_instance,
            split_protocol_sha256=snapshot['split_protocol_sha256'],
            source_manifest_sha256=snapshot['source_manifest_sha256'],
            gp_rng_seed=smoke['gp_rng_seed'], simulator_seed=smoke['simulator_seed'],
            runner_wall_seconds=smoke['max_runner_wall_seconds'],
            supervisor_wall_seconds=smoke['max_supervisor_wall_seconds'],
            total_wall_seconds=smoke['max_total_wall_seconds'],
            cleanup_reserve_seconds=smoke['cleanup_reserve_seconds'],
            max_processes=smoke['max_new_rollout_processes'],
            started_monotonic=started,
            invalid_fitness=protocol['training_fitness']['invalid_fitness_penalty'])
        rng = random.Random(smoke['gp_rng_seed'])
        population = initial_population(rng, smoke['population'])
        for generation in range(smoke['generations']+1):
            generation_started = time.perf_counter()
            rng_state_before = rng.getstate()
            members = []
            scored = []
            for tree in population:
                tracker.require(snapshot['train_instances'], rollout=True)
                per_instance, aggregate = evaluate_training_tree(
                    tree, snapshot['train_instances'], evaluator, baseline_scores,
                    protocol['training_fitness']['invalid_fitness_penalty'])
                nodes, depth = validate_tree(tree)
                member = dict(tree=tree.data(), expression=tree.text(),
                              canonical=canonical(tree), nodes=nodes, depth=depth,
                              fitness=aggregate['fitness'], valid=aggregate['valid'],
                              ratios=aggregate['ratios'],
                              invalid_instances=aggregate['invalid_instances'],
                              training_instances={str(i): record for i, record
                                                  in zip(snapshot['train_instances'], per_instance)},
                              fitness_scope=config['fitness_scope'])
                members.append(member)
                scored.append((aggregate['fitness'], tree))
                if aggregate['valid']:
                    candidates.setdefault(canonical(tree), (aggregate['fitness'], tree))
            record = dict(generation=generation, members=members,
                          best_valid_subset_fitness=min((m['fitness'] for m in members if m['valid']), default=None),
                          valid_tree_count=sum(m['valid'] for m in members),
                          population_size=len(population),
                          train_instances=list(snapshot['train_instances']),
                          validation_instances_evaluated=[],
                          validation_used_for_fitness=False,
                          validation_used_for_breeding=False,
                          rng_state_before=rng_state_before,
                          elapsed_generation_wall_seconds=time.perf_counter()-generation_started,
                          elapsed_total_wall_seconds=time.perf_counter()-started,
                          rollout_processes=evaluator.process_count,
                          cache_hits=sum(r.get('cache_hit', False) for r in evaluator.records))
            generations.append(record)
            write_generation(root/'generations', record)
            state = dict(status='running', generations_completed=len(generations),
                         current_generation=generation, config=config,
                         total_wall_seconds=time.perf_counter()-started,
                         rollout_processes=evaluator.process_count,
                         generation_summaries=[dict(generation=g['generation'],
                                                    valid_tree_count=g['valid_tree_count'],
                                                    best_valid_subset_fitness=g['best_valid_subset_fitness'])
                                               for g in generations],
                         sealed_access=tracker.report())
            _atomic_json(root/'training.json', state)
            if not record['valid_tree_count']:
                status = 'failed_no_valid_training_tree'
                error = f'no valid GP tree in generation {generation}'
                break
            # Ghi chú: Chỉ dùng fitness train để sinh thế hệ tiếp theo; chưa dùng validation ở bước này.
            if generation < smoke['generations']:
                rng_state_before_breeding = rng.getstate()
                population = breed(rng, scored, smoke['population'],
                                   protocol['evolution']['tournament'],
                                   protocol['evolution']['crossover_rate'],
                                   protocol['evolution']['mutation_rate'],
                                   protocol['evolution']['elitism'], Limits())
                record['rng_state_before_breeding'] = rng_state_before_breeding
                record['rng_state_after_generation'] = rng.getstate()
                write_generation(root/'generations', record)
        if status != 'failed_no_valid_training_tree':
            if (len(generations) == smoke['generations']+1
                    and all(g['valid_tree_count'] == g['population_size'] for g in generations)):
                status = 'development_smoke_complete'
            elif len(generations) == smoke['generations']+1:
                status = 'partial_invalid_rollouts'
            else:
                status = 'partial'
        candidate_rows = []
        if pilot:
            if status != 'development_smoke_complete':
                raise ValueError('pilot incomplete or invalid; validation selection forbidden')
            # Ghi chú: Pilot lấy tối đa hai cây theo train để chấm validation sau khi tiến hóa hoàn tất.
            shortlist = sorted(candidates.values(), key=lambda x: (x[0], validate_tree(x[1])[0], canonical(x[1])))[:2]
            tracker.require([6], rollout=True)
            selected, candidate_rows = select_with_validation(
                [tree for _, tree in shortlist], snapshot['train_instances'], 6, evaluator,
                baseline_scores, protocol['training_fitness']['invalid_fitness_penalty'])
            if selected is None:
                status = 'failed_no_valid_validation_candidate'
            else:
                save_tree(root/'selected_tree.json', selected['tree'], training=dict(
                    protocol_sha256=snapshot['protocol_sha256'], selection_key=selected['selection_key']))
                status = 'development_pilot_complete'
            candidate_rows = [dict(c, tree=c['tree'].data()) for c in candidate_rows]
        for key, (_, tree) in (sorted(candidates.items()) if not pilot else []):
            train_records = [evaluator.evaluate(tree, instance)
                             for instance in snapshot['train_instances']]
            aggregate = aggregate_training(train_records, baseline_scores,
                                           snapshot['train_instances'],
                                           protocol['training_fitness']['invalid_fitness_penalty'])
            candidate_rows.append(dict(canonical=key, tree=tree.data(), expression=tree.text(),
                                       train_subset_fitness=aggregate['fitness'],
                                       valid=aggregate['valid'], ratios=aggregate['ratios'],
                                       selection_key=None,
                                       eligible_for_model_selection=False,
                                       reason='smoke protocol disables validation and official selection'))
        _atomic_json(root/'candidates.json', candidate_rows)
    except RolloutBudgetExceeded as exc:
        status = 'partial_budget_exhausted'
        error = f'{type(exc).__name__}: {exc}'
    except KeyboardInterrupt:
        status = 'interrupted'
        error = 'interrupted; preserve artifacts and restart in a new directory; resume unsupported'
    except Exception as exc:
        status = 'failed'
        error = f'{type(exc).__name__}: {exc}'

    elapsed = time.perf_counter()-started
    summary = dict(status=status, official_training=False,
                   training_ready=False,
                   config=config,
                   generations=generations,
                   selected_tree='selected_tree.json' if selected else None,
                   selected_by_validation=selected['selection_key'] if selected else None,
                   error=error,
                   total_wall_seconds=elapsed,
                   max_total_wall_seconds=(config or {}).get('max_total_wall_seconds'),
                   rollout_processes=evaluator.process_count if evaluator else 0,
                   max_rollout_processes=(config or {}).get('max_new_rollout_processes'),
                   rollout_records=evaluator.records if evaluator else [],
                   cache_hits=sum(r.get('cache_hit', False) for r in evaluator.records) if evaluator else 0,
                   valid_rollouts=sum(r.get('valid', False) for r in evaluator.records) if evaluator else 0,
                   invalid_rollouts=sum(not r.get('valid', False) for r in evaluator.records) if evaluator else 0,
                   sealed_access=tracker.report(),
                   limitations=['development experiment only; no generalization claim',
                                 'resume is unsupported',
                                 'application-level ID guard is not OS-level file-open tracing'])
    _atomic_json(root/'training.json', summary)
    return summary
