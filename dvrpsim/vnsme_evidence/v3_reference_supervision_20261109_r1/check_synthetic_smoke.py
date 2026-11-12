"""Re-score the bounded real-Java synthetic run; never adopt it as reference."""
import json
from pathlib import Path
import sys
root=Path(__file__).resolve().parents[2]; here=Path(__file__).resolve().parent
sys.path.insert(0,str(root))
from verify_dpdp_score import verify
run=here/'smoke_synthetic_run'
read=lambda p: json.loads(p.read_text(encoding='utf-8'))
manifest=read(run/'manifest.json'); result=read(run/'result.json'); ledger=read(run/'commitments.json')
job=read(here/'smoke_synthetic_supervision/supervision.json'); paths=manifest['input_paths']
score=json.loads(json.dumps(verify(run/'simulation.log',paths['orders'],paths['vehicles'],paths['routes']),default=str))
epochs=sorted((run/'vnsme/epochs').iterdir())
assert result['valid'] and result['contract_complete'] and ledger['complete'] and score['valid']
assert result['completed_items']==score['items']==2 and result['completed_original_orders']==score['original_orders']==2
assert all(str(result['score'][k])==str(score[k]) for k in ('total_score','total_distance_km','total_tardiness_seconds'))
assert job['valid_supervision'] and job['exit_code']==0 and not job['gaps'] and not job['remaining_job_processes']
assert len(epochs)==len(ledger['history'])==result['decision_count']==14
assert all(read(e/'invocation.json')['valid'] and not read(e/'invocation_process_end.json')['timed_out'] for e in epochs)
out=dict(valid=True,independent_rescore_matches=True,synthetic_orders=2,synthetic_items=2,
         java_invocations=len(epochs),score=score,reference=False,full_benchmark=False)
(here/'smoke_synthetic_check.json').write_text(json.dumps(out,indent=2),encoding='utf-8')
print(json.dumps(out,indent=2))
