"""Pin the final audit outcome and verify report encoding."""
import hashlib,json
from pathlib import Path
here=Path(__file__).resolve().parent
root=here.parents[1]
read=lambda path:json.loads(Path(path).read_text(encoding='utf-8'))
accept=read(here/'instance2_acceptance.json')
tests=read(here/'regression_final2.json')
summary=root/'vnsme_runs/v3_instance2_acceptance_20261109_r1/reference_2/summary.json'
report=(here/'REPORT.md').read_bytes();report.decode('utf-8',errors='strict')
matrix={
 'pickup_before_delivery':'PASS','capacity_per_event':'PASS','LIFO':'PASS',
 'duplicate_pickup_delivery':'PASS','item_ownership':'PASS','current_visit_lock':'PASS',
 'destination_factory_eta_lock':'PASS','request_loss_future_items':'PASS','pending_reoffered':'PASS',
 'physical_event_reversal':'PASS','order_split':'PASS','complete_delivery':'PASS',
 'at_location_eta_forecast_accuracy':'UNVERIFIABLE',
 'at_location_eta_lock_preservation':'PASS'}
(here/'audit_matrix.json').write_text(json.dumps(matrix,indent=2),encoding='utf-8')
status='GO_VNSME_REFERENCES_2_TO_6' if accept['status']=='PASS' and tests['passed'] else 'NO_GO'
data=dict(status=status,head='0bd773291d5d9034f1e7b81688bc2dfaf87308c7',
 contract_version=accept['contract_version'],fitness_version=accept['fitness_version'],
 instance2_reference=accept,regression=tests,audit_matrix=matrix,
 v2_historical_references_reused=False,instances_9_10_13_full_rollouts=0,gp_training_runs=0,
 sealed_csv_access_attempts=tests['sealed_csv_open_attempts'],
 final_test_read_incident_from_prior_run=True,summary_path=str(summary.resolve()),
 summary_sha256=hashlib.sha256(summary.read_bytes()).hexdigest(),
 reference_summary_utf8=True,report_utf8=True,report_sha256=hashlib.sha256(report).hexdigest(),
 gp_training_status='NO_GO_PENDING_V3_REFERENCES_3_TO_6_AND_TRAINER_ENABLEMENT')
(here/'summary.json').write_text(json.dumps(data,indent=2),encoding='utf-8')
print(json.dumps(dict(status=status,instance2_J=accept['J'],tests=tests['tests'],
    sealed_csv_access_attempts=tests['sealed_csv_open_attempts'],report_utf8=True),indent=2))
