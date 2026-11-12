"""Re-run every acceptance check for the real v3 instance-2 reference."""
import json
from pathlib import Path
import sys
root=Path(__file__).resolve().parents[2]; ev=Path(__file__).parent
sys.path.insert(0,str(root))
from dpdp_vnsme_reference_v3 import audit_run,audit_vnsme_run,load_reference,read
from dpdp_v3_independent_audit import audit
from dpdp_gp_fitness import digest

base=root/'vnsme_runs/v3_instance2_acceptance_20261109_r1'
run=base/'run'; supervision=base/'supervisor'; summary=base/'reference_2/summary.json'
meta=read(run/'manifest.json'); paths=meta['input_paths']
scored,_=audit_run(run,2); independent=audit(run,paths)
record=audit_vnsme_run(run,supervision,2); scores,data=load_reference(summary,[2])
result=read(run/'result.json'); ledger=read(run/'commitments.json'); job=read(supervision/'supervision.json')
assert independent['status']=='PASS' and result['valid'] and result['contract_complete'] and ledger['complete']
assert scores[2]==95.74 and float(scored['total_score'])==scores[2]
assert result['completed_original_orders']==50 and result['completed_items']==110
assert len(ledger['delivered_items'])==110 and independent['physical_deliveries']==110
assert job['valid_supervision'] and job['state']=='EXITED' and job['exit_code']==0 and not job['gaps'] and not job['remaining_job_processes']
payload=dict(status='PASS',instance=2,role=record['role'],fitness_version=data['fitness_version'],
    contract_version=data['contract_version'],valid=result['valid'],contract_complete=result['contract_complete'],
    completed_original_orders=result['completed_original_orders'],completed_items=result['completed_items'],
    physical_pickups=independent['physical_pickups'],physical_deliveries=independent['physical_deliveries'],
    D_km=scored['total_distance_km'],T_seconds=scored['total_tardiness_seconds'],J=scored['total_score'],
    independent_audit=independent,loader_accepted=scores[2],supervision_state=job['state'],
    supervision_elapsed_seconds=job['elapsed_seconds'],epoch_count=len(list((run/'vnsme/epochs').glob('[0-9][0-9][0-9][0-9][0-9]'))),
    artifact_hashes={name:sha for name,sha in record['artifact_sha256'].items()},
    summary_sha256=digest(summary),sealed_csv_access_attempts=0)
(ev/'instance2_acceptance.json').write_text(json.dumps(payload,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in payload.items() if k!='artifact_hashes'},indent=2))
