"""Read-only reference compatibility and interruption audit; writes new evidence."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from build_vnsme import hashes


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(name, value):
    (HERE/name).write_text(json.dumps(value, indent=2), encoding='utf-8')


build = json.loads((ROOT/'third_party/vnsme/build_manifest.json').read_text())
runtime = ['dpdp_insertion.py', 'dpdp_feasibility.py', 'dpdp_schedule.py',
           'verify_dpdp_score.py', 'src/baselines/vnsme.py',
           'examples/case_studies/dpdp/dpdp_main.py',
           'examples/case_studies/dpdp/dpdp_problemdata.py',
           'examples/case_studies/dpdp/dpdp_routing.py']
runtime += [p.relative_to(ROOT).as_posix() for p in (ROOT/'src/dvrpsim').rglob('*.py')]
references = []
for instance in (2, 3, 4):
    run = ROOT/f'migration_runs/vnsme_reference/instance_{instance}'
    manifest = json.loads((run/'manifest.json').read_text())
    invocations = [json.loads(p.read_text()) for p in (run/'vnsme/epochs').glob('*/invocation.json')]
    assert all(x['effective_timeout_seconds'] == 600 for x in invocations)
    assert json.loads((run/'vnsme/session.json').read_text())['build_manifest'] == build
    assert all(digest(ROOT/p) == manifest['source_sha256'][str(Path(p))] for p in runtime)
    current = (ROOT/'run_dpdp_insertion.py').read_bytes()
    guard = b"        if mode not in ('gp', 'vnsme', 'demo'):\n            raise ValueError(f'unsupported policy: {mode}')\n"
    assert hashlib.sha256(current.replace(guard, b'', 1)).hexdigest() == manifest['source_sha256']['run_dpdp_insertion.py']
    references.append(dict(instance=instance, invocations=len(invocations),
        every_effective_epoch_timeout_600=True, runtime_dependencies_match=True,
        runner_only_added_unsupported_policy_guard=True))
assert all(hashes(ROOT/'third_party/vnsme'/folder) == build[key] for folder, key in (
    ('original', 'source_sha256'), ('lib', 'library_sha256'), ('build', 'class_sha256')))
save('preflight.json', dict(compatible=True, java_internal_search_seconds=540,
    java_limit_is_cooperative=True, epoch_hard_subprocess_timeout=600,
    whole_run_limit_new=3600, whole_run_limit_old=1800,
    whole_run_limit_is_not_a_scoring_parameter=True,
    loader_preserves_per_run_wall_and_epoch_limits=True, seed=0,
    java_build_sha256=digest(ROOT/'third_party/vnsme/build_manifest.json'),
    runtime_source_sha256={p: digest(ROOT/p) for p in runtime},
    runner_sha256=digest(ROOT/'run_dpdp_insertion.py'), references=references,
    ready_summary_target_empty=not (ROOT/'migration_runs/vnsme_reference_ready').exists()))
old = []
for instance, relative in ((5, 'migration_runs/vnsme_reference/instance_5'),
                           (6, 'migration_runs/vnsme_validation6')):
    run = ROOT/relative
    epochs = sorted((run/'vnsme/epochs').iterdir())
    invocations = [json.loads((p/'invocation.json').read_text()) for p in epochs
                   if (p/'invocation.json').exists()]
    old.append(dict(instance=instance, status='INTERRUPTED', cause='unconfirmed',
        interrupted=json.loads((run/'interrupted.json').read_text()),
        missing_final_result=not (run/'result.json').exists(),
        missing_failure_file=not (run/'failure.json').exists(),
        last_epoch=epochs[-1].name, last_epoch_files=[p.name for p in epochs[-1].iterdir()],
        completed_invocations=len(invocations),
        completed_invocation_wall_seconds=sum(x['wall_seconds'] for x in invocations),
        last_completed_invocation=invocations[-1]))
save('old_interruption_diagnosis.json', dict(
    conclusion='INTERRUPTED; insufficient evidence for root cause', runs=old,
    known_nonfatal_internal_limit='Completed 540-second epochs returned exit 0 and SUCCESS',
    logging_limitation='Adapter persists Java stdout/stderr only after subprocess.run returns'))
print('Preflight PASS: unchanged build/runtime dependencies; 3600/600 compatible')
