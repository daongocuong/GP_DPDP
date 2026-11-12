"""Replay stored epochs and two-order fixtures; no full benchmark or Java run."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
import run_dpdp_insertion as runner
from dpdp_contract import ExecutionCommitment,EXECUTION_CONTRACT
from baselines.vnsme import VNSMEError,huawei_state
from dpdp_insertion import Snapshot
from dpdp_routing import transform_dpdp_decision
from test_dpdp_execution_contract import synchronize_vehicle_status,TinyLifecycleTests
from test_dpdp_vnsme_scale100 import restore_saved_epoch,archived_policy,CASES


def write(name,value):
    (HERE/name).write_text(json.dumps(value,indent=2,default=str),encoding='utf-8')


def main():
    results=[]
    for instance,epoch,affected in CASES:
        ledger=ExecutionCommitment()
        m,origin,metadata,state,output,_=restore_saved_epoch(instance,epoch-1)
        m.commitment_contract=ledger
        p=archived_policy(origin,metadata,state,output);p.commitment_contract=ledger
        runner.guard_raw_decision(m,p.decide(m))
        m,origin,metadata,state,output,_=restore_saved_epoch(instance,epoch)
        synchronize_vehicle_status(m);m.commitment_contract=ledger
        before={i:(o.status.name,o.acceptance_time) for i,o in Snapshot.observe(m).objects.items()}
        legacy=archived_policy(origin,metadata,state,output)
        try:
            legacy.decide(m)
        except VNSMEError as exc:
            old_error=str(exc)
        else:
            raise AssertionError('legacy saved failure unexpectedly accepted')
        p=archived_policy(origin,metadata,state,output);p.commitment_contract=ledger
        raw=p.decide(m)
        assert raw['vehicles']==transform_dpdp_decision(m,output)['vehicles']
        runner.guard_raw_decision(m,raw)
        m._enforce_decision(deepcopy(raw))
        after=Snapshot.observe(m)
        forwarded=huawei_state(m,origin,metadata)
        unallocated=[o['id'] for o in forwarded['unallocated_orders']]
        assert set(affected)<=set(unallocated)
        assert all(unallocated.count(i)==1 for i in affected)
        assert set(affected)<=set(ledger.history[-1]['states']['pending'])
        assert all((after.objects[i].status.name,after.objects[i].acceptance_time)==before[i] for i in affected)
        assert set(ledger.requests)==set(after.objects)
        results.append(dict(instance=instance,saved_epochs=[epoch-1,epoch],legacy_error=old_error,
            new_contract=EXECUTION_CONTRACT,shared_guard_pass=True,native_enforcement_pass=True,
            returned_publication_unchanged=True,affected_items=list(affected),
            acceptance_preserved=True,affected_reoffered_once_as_unallocated=True,
            observed_items=len(after.objects),ledger=ledger.export(),
            final_score_generated=False,full_simulation_run=False,Java_run=False))
    write('saved_epoch_replay.json',results)
    tiny=[]
    for mode in ('vnsme','gp'):
        root=HERE/f'tiny_lifecycle_{mode}'
        if not root.exists():
            root.mkdir()
            code,out,_=TinyLifecycleTests().run_tiny(mode,root)
            assert code==0
        else:
            out=root/'run'
        result=json.loads((out/'result.json').read_text())
        manifest=json.loads((out/'manifest.json').read_text())
        assert result['valid'] and result['contract_complete']
        paths=manifest['input_paths']
        score=runner.verify(out/'simulation.log',paths['orders'],paths['vehicles'],paths['routes'])
        assert str(score['total_score'])==result['score']['total_score']
        certificate=json.loads((out/'commitments.json').read_text())
        assert certificate['complete'] and len(certificate['delivered_items'])==2
        tiny.append(dict(policy=mode,synthetic_orders=2,result=result,
            ledger_complete=True,independent_scorer_pass=True,
            simulation_log_sha256=hashlib.sha256((out/'simulation.log').read_bytes()).hexdigest()))
    write('tiny_integration_results.json',tiny)
    print(json.dumps(dict(saved_epoch_cases=2,synthetic_integration_policies=2,
        benchmark_100_order_runs=0,new_Java_searches=0),indent=2))


if __name__=='__main__':
    main()
