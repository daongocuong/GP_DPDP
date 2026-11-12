"""Write machine-readable evidence and verify UTF-8 report decoding."""
import hashlib
import json
from pathlib import Path
here=Path(__file__).resolve().parent
read=lambda name:json.loads((here/name).read_text(encoding='utf-8'))
legacy=json.loads((here/'legacy_loader_recheck.json').read_text(encoding='utf-16'))
(here/'legacy_loader_recheck_utf8.json').write_text(json.dumps(legacy,indent=2),encoding='utf-8')
report=(here/'REPORT.md').read_bytes(); report.decode('utf-8',errors='strict')
suite=read('regression_verified_r3.json'); synthetic=read('smoke_synthetic_check.json'); smoke=read('smoke_summary.json')
out=dict(status='NO_GO_FULL_REFERENCE',head=(here/'head.txt').read_text(encoding='ascii').strip(),
         contract_version='dpdp-execution-commitment-v3',fitness_version='gp-fitness-vnsme-v3',
         regression=suite, synthetic_real_java=synthetic, supervisor_smoke=dict(
             java_observed=smoke['java_observed'],cleanup=smoke['killed_java_not_alive'],
             timeout_state=smoke['timeout_state'],gap_state=smoke['gap_state']),
         historical_reference_v2_loader_scores=legacy, full_reference_rollouts=0, gp_training_runs=0,
         sealed_instance_rollouts=0,sealed_instance_scoring=0,
         sealed_csvs_read_for_checksum_schema_by_full_suite=True,
         sealed_csv_read_incident='verify_existing invoked by existing full-suite tests; no scoring or rollout',
         blockers=['no completed real v3 reference end-to-end loader test',
                   'no independent complete replay of feasibility; recorded online guard is used',
                   'existing GP trainer is v2; v3 training protocol is disabled'],
         report_utf8=True,report_sha256=hashlib.sha256(report).hexdigest())
(here/'summary.json').write_text(json.dumps(out,indent=2),encoding='utf-8')
print(json.dumps(dict(status=out['status'],tests=suite['tests'],report_utf8=True),indent=2))
