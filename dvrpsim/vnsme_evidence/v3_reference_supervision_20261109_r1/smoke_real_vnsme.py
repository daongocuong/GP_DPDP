"""One saved, empty initial epoch of instance 13; never a full rollout."""
import json
from pathlib import Path
import sys

root=Path(__file__).resolve().parents[2]; here=Path(__file__).resolve().parent
sys.path[:0]=[str(root),str(root/'src')]
from baselines.vnsme import JavaSession
from dpdp_vnsme_reference_v3 import DATASET

saved=root/'vnsme_runs/scale100_reference_20261109_r1/instance_13/vnsme/epochs/00000'
state={key:json.loads((saved/name).read_text(encoding='utf-8')) for key,name in (
    ('vehicle_info','vehicle_info.json'),('ongoing_orders','ongoing_order_items.json'),
    ('unallocated_orders','unallocated_order_items.json'))}
assert not state['ongoing_orders'] and not state['unallocated_orders']
session=JavaSession(here/'smoke_real_vnsme_session', DATASET/'benchmark/factory_info.csv',
                    DATASET/'benchmark/route_info.csv', timeout=10, trace_process=True)
decision=session.invoke(state)
assert len(decision['destinations'])==5
print(json.dumps(dict(valid=True,instance=13,kind='empty_initial_epoch_smoke',
                      full_rollout=False,reference=False,java_invocations=1)))
