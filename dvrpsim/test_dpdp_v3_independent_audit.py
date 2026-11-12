"""Mutations must be rejected by the independent replayer, not runner guards."""
from copy import deepcopy
from decimal import Decimal
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from dpdp_v3_independent_audit import AuditFailure, inspect_plan, audit

def visit(factory,pickups=(),deliveries=(),arrival=None):
    return dict(factory=factory,pickups=list(pickups),deliveries=list(deliveries),arrival=arrival)

def fixture(capacity=2):
    items={i:dict(original_id=i,quantity=Decimal(1),pickup='P',delivery='D',release=0,due=100) for i in ('a','b')}
    demands={i:Decimal(1) for i in items}; vehicles={'V':Decimal(capacity)}
    fleet={'V':dict(capacity=capacity,carrying=[],current=None,service_started=False,destination=None)}
    future=[visit('P',['a','b']),visit('D',deliveries=['b','a'])]
    raw=[dict(location=x['factory'],pickup_list=x['pickups'][:],delivery_list=x['deliveries'][:]) for x in future]
    event=dict(items={i:dict(delivered=False) for i in items},fleet=fleet,
        previous_plans={'V':dict(current=None,future=[])},published_plans={'V':dict(current=None,future=future)},
        raw=dict(vehicles={'V':dict(current_visit=None,next_visits=raw)},orders={}))
    return event,items,demands,vehicles

def replace_route(event,future):
    event['published_plans']['V']['future']=future
    event['raw']['vehicles']['V']['next_visits']=[dict(location=x['factory'],pickup_list=x['pickups'][:],delivery_list=x['deliveries'][:]) for x in future]

class AdversarialPlanTests(unittest.TestCase):
    def assert_bad(self,event,items,demands,vehicles,reason):
        with self.assertRaisesRegex(AuditFailure,reason): inspect_plan(event,items,demands,vehicles)

    def test_valid(self):
        self.assertEqual(inspect_plan(*fixture()),set())

    def test_capacity(self):
        e,i,d,v=fixture(1); self.assert_bad(e,i,d,v,'CAPACITY')

    def test_lifo(self):
        e,i,d,v=fixture(); replace_route(e,[visit('P',['a','b']),visit('D',deliveries=['a','b'])]); self.assert_bad(e,i,d,v,'LIFO')

    def test_delivery_before_pickup(self):
        e,i,d,v=fixture(); replace_route(e,[visit('D',deliveries=['a']),visit('P',['a','b']),visit('D',deliveries=['b'])]); self.assert_bad(e,i,d,v,'DELIVERY_BEFORE_PICKUP')

    def test_duplicate_pickup_and_delivery(self):
        e,i,d,v=fixture(); replace_route(e,[visit('P',['a','a','b']),visit('D',deliveries=['b','a'])]); self.assert_bad(e,i,d,v,'DUPLICATE')
        e,i,d,v=fixture(); replace_route(e,[visit('P',['a','b']),visit('D',deliveries=['b','a','a'])]); self.assert_bad(e,i,d,v,'DUPLICATE')

    def test_destination_factory_and_eta_lock(self):
        e,i,d,v=fixture(); e['fleet']['V']['destination']=visit('P',arrival=7)
        e['published_plans']['V']['future'][0]['arrival']=8
        self.assert_bad(e,i,d,v,'DESTINATION_LOCK')
        e['published_plans']['V']['future'][0]['arrival']=7
        e['published_plans']['V']['future'][0]['factory']='D'
        e['raw']['vehicles']['V']['next_visits'][0]['location']='D'
        self.assert_bad(e,i,d,v,'DESTINATION_LOCK')

    def test_current_lock(self):
        e,i,d,v=fixture(); e['fleet']['V']['current']=visit('P'); self.assert_bad(e,i,d,v,'CURRENT_LOCK')

    def test_carrying_cannot_move_to_other_vehicle(self):
        e,i,d,v=fixture(); v['W']=v['V']; e['fleet']['V']['carrying']=['a']
        e['fleet']['W']=dict(capacity=2,carrying=[],current=None,service_started=False,destination=None)
        e['previous_plans']['W']=dict(current=None,future=[])
        e['published_plans']['W']=dict(current=None,future=[visit('D',deliveries=['a'])])
        e['raw']['vehicles']['W']=dict(current_visit=None,next_visits=[dict(location='D',pickup_list=[],delivery_list=['a'])])
        replace_route(e,[visit('P',['b']),visit('D',deliveries=['b'])])
        self.assert_bad(e,i,d,v,'UNDELIVERED_LOAD|OWNERSHIP')

class AdversarialLogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source=Path(__file__).resolve().parent/'vnsme_evidence/v3_independent_audit_20261109_r1/synthetic_run'
        if not cls.source.exists(): raise unittest.SkipTest('bounded synthetic evidence not present')
        cls.paths=json.loads((cls.source/'manifest.json').read_text())['input_paths']
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.run=Path(self.tmp.name)/'run'; shutil.copytree(self.source,self.run)
    def tearDown(self): self.tmp.cleanup()
    def test_full_replay_and_missing_pending(self):
        self.assertEqual(audit(self.run,self.paths)['status'],'PASS')
        trace=self.run/'decision_trace.jsonl'; events=[json.loads(x) for x in trace.read_text().splitlines()]
        del events[1]['items']['a-1']; trace.write_text(''.join(json.dumps(x)+'\n' for x in events))
        self.assertEqual(audit(self.run,self.paths)['status'],'FAIL')
    def test_missing_final_delivery_and_missing_trace(self):
        log=self.run/'simulation.log'; lines=log.read_text().splitlines()
        log.write_text('\n'.join(x for x in lines if 'order a-1 is delivered' not in x)+'\n')
        self.assertEqual(audit(self.run,self.paths)['status'],'FAIL')
        (self.run/'decision_trace.jsonl').unlink()
        self.assertEqual(audit(self.run,self.paths)['status'],'UNVERIFIABLE')
    def test_mutated_java_locked_eta_is_rejected(self):
        epoch=self.run/'vnsme/epochs/00001'; path=epoch/'output_destination.json'
        decision=json.loads(path.read_text()); decision['V_1']['arrive_time']+=60
        path.write_text(json.dumps(decision))
        self.assertEqual(audit(self.run,self.paths)['status'],'FAIL')

if __name__=='__main__': unittest.main()
