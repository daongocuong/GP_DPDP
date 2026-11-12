"""Compare task-start snapshots without reading held-out benchmark CSVs."""
import hashlib
import json
from pathlib import Path
root=Path(__file__).resolve().parents[2]; here=Path(__file__).resolve().parent
digest=lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
files=('run_dpdp_insertion.py','dpdp_contract.py','dpdp_vnsme_reference.py')
unchanged={name:digest(root/name)==digest(here/(name.replace('/','_')+'.before')) for name in files}
prior=root/'vnsme_evidence/scale100_contract_resolution'
pins=json.loads((prior/'artifact_sha256.json').read_text(encoding='utf-8'))
historical={name:digest(prior/name)==sha for name,sha in pins.items()}
data=dict(start_snapshots_unchanged=unchanged,prior_evidence_pins_pass=all(historical.values()),
          prior_evidence_checked=len(historical),held_out_benchmark_csvs_read_by_this_script=False,
          adapter_changed_for_v3_only=True)
(here/'preservation.json').write_text(json.dumps(data,indent=2),encoding='utf-8')
print(json.dumps(data,indent=2))
assert all(unchanged.values()) and all(historical.values())
