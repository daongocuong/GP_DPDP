"""Versioned contract replay and small real simulations; never a 100-order run."""
from copy import deepcopy
import contextlib
import csv
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import run_dpdp_insertion as runner
from dpdp_contract import (CommitmentError, ExecutionCommitment, LEGACY_CONTRACT,
                           EXECUTION_CONTRACT, contract_metadata)
from dpdp_feasibility import Infeasible
from dpdp_gp import Node, TreeRanker, save_tree
from dpdp_insertion import InsertionPolicy, Snapshot
from dpdp_vnsme_reference import independent_score
from baselines.vnsme import VNSMEError, huawei_state
from dvrpsim import Order
from dvrpsim.elements.order import OrderStatus
from dvrpsim.elements.vehicle import VehicleStatus
from test_dpdp_insertion import make, order, visit
from test_dpdp_vnsme import policy, node
from test_dpdp_vnsme_scale100 import restore_saved_epoch, archived_policy, CASES


ROOT=Path(__file__).resolve().parent


def empty():
    return dict(vehicles={},orders={})


def plan(vehicle='V_1',pickups=('a',),deliveries=('a',)):
    return dict(vehicles={vehicle:dict(current_visit=None,next_visits=[
        dict(location='P',pickup_list=list(pickups),delivery_list=[]),
        dict(location='Q',pickup_list=[],delivery_list=list(deliveries))])},orders={})


def attach(model):
    model.commitment_contract=ExecutionCommitment()
    return model.commitment_contract


def synchronize_vehicle_status(model):
    # The saved-event reducer restores visits, times and stacks. Native Model
    # enforcement additionally uses the status enum; derive it from those facts.
    for v in model.vehicles:
        if v.current_visit is None:
            v.status=VehicleStatus.EN_ROUTE
        elif v.current_visit.service_finish_time is not None:
            v.status=VehicleStatus.IDLE
        elif v.current_visit.service_start_time is not None:
            v.status=VehicleStatus.UNDER_SERVICE
        else:
            v.status=VehicleStatus.WAITING_FOR_SERVICE


class SavedContractReplayTests(unittest.TestCase):
    def test_legacy_rejects_and_v3_accounts_withdrawn_work_across_saved_epochs(self):
        for instance,epoch,affected in CASES:
            with self.subTest(instance=instance):
                previous=restore_saved_epoch(instance,epoch-1)
                model,origin,metadata,state,output,_=previous
                ledger=attach(model)
                p=archived_policy(origin,metadata,state,output)
                p.commitment_contract=ledger
                runner.guard_raw_decision(model,p.decide(model))
                self.assertTrue(set(affected)<=set(ledger.history[-1]['states']['tentative']))
                # Physical execution between these two observations comes from
                # the historical event log, not a new full simulator rollout.
                current=restore_saved_epoch(instance,epoch)
                model,origin,metadata,state,output,_=current
                synchronize_vehicle_status(model)
                before_status={i:(o.status,o.acceptance_time) for i,o in Snapshot.observe(model).objects.items()}
                legacy=archived_policy(origin,metadata,state,output)
                with self.assertRaisesRegex(VNSMEError,'dropped previously accepted'):
                    legacy.decide(model)
                model.commitment_contract=ledger
                p=archived_policy(origin,metadata,state,output)
                p.commitment_contract=ledger
                raw=p.decide(model)
                self.assertTrue(set(affected).isdisjoint(raw['orders']))
                runner.guard_raw_decision(model,raw)
                self.assertTrue(set(affected)<=set(ledger.history[-1]['states']['pending']))
                universe=set(Snapshot.observe(model).objects)
                self.assertEqual(set(ledger.requests),universe)
                model._enforce_decision(deepcopy(raw))
                after=Snapshot.observe(model)
                self.assertEqual(set(after.objects),universe)
                for i in affected:
                    self.assertTrue(after.objects[i].is_accepted)
                    self.assertEqual((after.objects[i].status,after.objects[i].acceptance_time),before_status[i])
                    self.assertFalse(after.objects[i].is_picked_up)
                # These retained accepted requests really reappear as Huawei
                # unallocated after enforcement; they are not forgotten or
                # treated as carrying items.
                forwarded=huawei_state(model,origin,metadata)
                self.assertTrue(set(affected)<={o['id'] for o in forwarded['unallocated_orders']})
                self.assertTrue(set(affected)<=ledger.promised)
                self.assertFalse(ledger.completed)


class RequestLedgerTests(unittest.TestCase):
    def test_accepted_pending_is_retained_and_GP_can_schedule_it(self):
        model=make();order(model,'a').accept();ledger=attach(model)
        runner.guard_raw_decision(model,empty())
        self.assertEqual(ledger.history[-1]['states']['pending'],['a'])
        gp=InsertionPolicy(TreeRanker(Node('feature','delta_distance_km')))
        raw=gp.decide(model)
        runner.guard_raw_decision(model,raw)
        self.assertEqual(ledger.history[-1]['states']['tentative'],['a'])
        self.assertEqual(raw['orders'],{})
        self.assertTrue(model.get_order_by_id('a').is_accepted)

    def test_request_disappearance_and_definition_change_are_rejected(self):
        for mutation in ('remove','change'):
            model=make();o=order(model,'a');attach(model)
            runner.guard_raw_decision(model,empty())
            if mutation=='remove':
                model._orders.pop('a')
            else:
                o.due_date+=1
            with self.subTest(mutation=mutation),self.assertRaisesRegex(CommitmentError,'REQUEST_'):
                runner.guard_raw_decision(model,empty())

    def test_acceptance_reversal_rejection_and_cancellation_are_rejected(self):
        for action in ('reverse','reject','cancel'):
            model=make();o=order(model,'a');o.accept();attach(model)
            runner.guard_raw_decision(model,empty())
            if action=='reverse':
                o.status=OrderStatus.NO_DECISION
            elif action=='reject':
                o.status=OrderStatus.REJECTED
            else:
                o.status=OrderStatus.CANCELED
            with self.subTest(action=action),self.assertRaises(CommitmentError):
                runner.guard_raw_decision(model,empty())

    def test_new_acceptance_requires_complete_publication(self):
        model=make();order(model,'a');attach(model)
        raw=empty();raw['orders']['a']={'status':'accepted'}
        with self.assertRaisesRegex(ValueError,'accepted item missing'):
            runner.guard_raw_decision(model,raw)

    def test_published_missing_delivery_and_duplicate_service_are_rejected(self):
        for deliveries in ((),('a','a')):
            model=make();order(model,'a');attach(model)
            raw=plan(deliveries=deliveries)
            with self.subTest(deliveries=deliveries),self.assertRaises(Infeasible):
                runner.guard_raw_decision(model,raw)

    def test_current_work_and_locked_destination_are_protected(self):
        model=make();order(model,'a');attach(model)
        raw=empty();raw['vehicles']['V_1']={'current_visit':{'pickup_list':[]}}
        with self.assertRaisesRegex(CommitmentError,'current work'):
            runner.guard_raw_decision(model,raw)
        v=next(iter(model.vehicles))
        v.next_visits=[visit(model,'P',['a']),visit(model,'Q',deliveries=['a'])]
        raw=plan();raw['vehicles']['V_1']['next_visits'][0]['location']='R'
        with self.assertRaisesRegex(Infeasible,'DESTINATION_LOCK'):
            runner.guard_raw_decision(model,raw)

    def test_v3_Java_output_must_keep_locked_factory_and_ETA(self):
        for factory,arrival in [('R',100020),('P',100021)]:
            model=make();order(model,'a');ledger=attach(model)
            v=next(iter(model.vehicles))
            v.next_visits=[visit(model,'P',['a']),visit(model,'Q',deliveries=['a'])]
            p=policy(dict(destinations={'V_1':node(factory,['a'],arrival=arrival)},
                          routes={'V_1':[node('Q',deliveries=['a'])]}))
            p.commitment_contract=ledger
            with self.subTest(factory=factory),self.assertRaisesRegex(VNSMEError,'locked'):
                p.decide(model)
            self.assertEqual(ledger.history,[])

    def test_carrying_cannot_be_deferred_or_transferred(self):
        model=make(2);o=order(model,'a',pickup='H1');o.accept()
        v=next(iter(model.vehicles));o.pickup(v);v.carrying_orders.append(o)
        v.next_visits=[visit(model,'Q',deliveries=['a'])];ledger=attach(model)
        runner.guard_raw_decision(model,empty())
        raw=empty();raw['vehicles'][v.id]={'current_visit':None,'next_visits':[]}
        with self.assertRaises(Infeasible):
            runner.guard_raw_decision(model,raw)
        v.carrying_orders.remove(o)
        with self.assertRaisesRegex(CommitmentError,'PHYSICAL_STACK'):
            ledger.check(Snapshot.observe(model),raw)
        v.carrying_orders.append(o)
        other=list(model.vehicles)[1];o.pickup_vehicle=other
        with self.assertRaisesRegex(CommitmentError,'PHYSICAL_OWNERSHIP'):
            runner.guard_raw_decision(model,empty())
        self.assertIn('a',ledger.picked)

    def test_capacity_lifo_and_precedence_remain_strict(self):
        for rule in ('capacity','lifo','precedence'):
            model=make();order(model,'a');order(model,'b');attach(model)
            raw=plan(pickups=('a','b'),deliveries=('b','a'))
            if rule=='capacity':
                next(iter(model.vehicles)).capacity=1
            elif rule=='lifo':
                raw['vehicles']['V_1']['next_visits'][1]['delivery_list']=['a','b']
            else:
                raw['vehicles']['V_1']['next_visits'][0]['pickup_list']=['a']
            with self.subTest(rule=rule),self.assertRaises(Infeasible):
                runner.guard_raw_decision(model,raw)

    def test_fitting_order_cannot_be_partly_deferred_to_split_service_over_epochs(self):
        model=make();order(model,'a',original='one');order(model,'b',original='one');attach(model)
        with self.assertRaisesRegex(CommitmentError,'ORDER_SPLIT'):
            runner.guard_raw_decision(model,plan())

    def test_pending_service_cannot_pass_completion_gate(self):
        model=make();order(model,'a');ledger=attach(model)
        runner.guard_raw_decision(model,empty())
        with self.assertRaisesRegex(CommitmentError,'INCOMPLETE_SERVICE'):
            ledger.finish(Snapshot.observe(model),{'a'})
        self.assertFalse(ledger.completed)

    def test_time_and_delivery_history_cannot_move_backwards(self):
        model=make();order(model,'a');ledger=attach(model)
        model.env._now=10
        runner.guard_raw_decision(model,empty())
        model.env._now=9
        with self.assertRaisesRegex(CommitmentError,'TIME_REVERSED'):
            runner.guard_raw_decision(model,empty())
        model.env._now=10
        ledger.delivered.add('a')
        with self.assertRaisesRegex(CommitmentError,'DELIVERY_REVERSED'):
            runner.guard_raw_decision(model,empty())


def tiny_data(root):
    """Two original orders, one vehicle, five factories; no official instance."""
    common=root/'tiny';common.mkdir();folder=common/'synthetic_contract';folder.mkdir()
    def csvfile(path,header,rows):
        with path.open('w',encoding='utf-8',newline='') as f:
            w=csv.writer(f);w.writerow(header);w.writerows(rows)
    factories=['H','P','Q','R','S']
    csvfile(common/'factory_info.csv',['factory_id','longitude','latitude','port_num'],[(i,0,0,1) for i in factories])
    csvfile(common/'route_info.csv',['route_code','start_factory_id','end_factory_id','distance','time'],
        [(f'{a}-{b}',a,b,0 if a==b else 1,0 if a==b else 20) for a in factories for b in factories])
    csvfile(folder/'vehicle_info_1.csv',['car_num','capacity','operation_time','gps_id'],[('V_1',15,24,'G_1')])
    csvfile(folder/'orders.csv',['order_id','q_standard','q_small','q_box','demand','creation_time',
        'committed_completion_time','load_time','unload_time','pickup_id','delivery_id'],
        [('a',1,0,0,1,'00:00:00','04:00:00',240,240,'P','Q'),
         ('b',1,0,0,1,'00:00:00','04:00:00',240,240,'R','S')])
    return common,folder


class TinyLifecycleTests(unittest.TestCase):
    def run_tiny(self,mode,root,never_publish=False):
        common,folder=tiny_data(root)
        tree=root/'tree.json';save_tree(tree,Node('feature','delta_distance_km'))
        sessions=[]
        class Session:
            def __init__(self,*args,**kwargs):
                self.inputs=[];sessions.append(self)
            def invoke(self,state,remaining=None):
                self.inputs.append(deepcopy(state))
                if never_publish:
                    return {'destinations':{'V_1':None},'routes':{'V_1':[]}}
                active={i['id'] for i in state['ongoing_orders']+state['unallocated_orders']}
                unpicked={i['id'] for i in state['unallocated_orders']}
                route=[]
                for i,pickup,delivery in [('a-1','P','Q'),('b-1','R','S')]:
                    if i=='b-1' and len(self.inputs)==2:
                        continue
                    if i in unpicked:route.append(node(pickup,[i]))
                    if i in active:route.append(node(delivery,deliveries=[i]))
                locked=state['vehicle_info'][0]['destination']
                if route and locked:
                    if route[0]['factory_id']!=locked['factory_id']:
                        raise AssertionError('synthetic policy would divert locked work')
                    route[0]['arrive_time']=locked['arrive_time']
                return dict(destinations={'V_1':route[0] if route else None},routes={'V_1':route[1:]})
        output=root/'run'
        argv=['runner','--policy',mode,'--instance-directory',str(folder),'--data-directory',str(common),
            '--output',str(output),'--contract-version',EXECUTION_CONTRACT,'--wall-seconds','15',
            '--max-simulation-seconds','1200' if never_publish else '20000']
        if mode=='gp':argv+=['--tree',str(tree)]
        with patch('sys.argv',argv),patch('baselines.vnsme.JavaSession',Session),contextlib.redirect_stdout(io.StringIO()):
            code=runner.main()
        return code,output,sessions

    def test_real_multi_epoch_publication_deferral_republication_and_delivery(self):
        with tempfile.TemporaryDirectory() as name:
            acceptance=[]
            original_accept=Order.accept
            def accept(o):
                acceptance.append(o)
                return original_accept(o)
            with patch.object(Order,'accept',accept):
                code,out,sessions=self.run_tiny('vnsme',Path(name))
            self.assertEqual(code,0)
            read=lambda p:json.loads(p.read_text())
            result=read(out/'result.json');ledger=read(out/'commitments.json')
            self.assertTrue(result['valid'] and result['contract_complete'] and ledger['complete'])
            self.assertEqual(ledger['terminal_state']['states']['delivered'],['a-1','b-1'])
            self.assertEqual((result['completed_original_orders'],result['completed_items']),(2,2))
            history=ledger['history']
            self.assertIn('b-1',history[0]['states']['tentative'])
            self.assertIn('b-1',history[1]['states']['pending'])
            self.assertIn('b-1',history[2]['states']['tentative'])
            self.assertIn('b-1',{i['id'] for i in sessions[0].inputs[2]['unallocated_orders']})
            log=(out/'simulation.log').read_text()
            for i in ('a-1','b-1'):
                self.assertEqual(log.count(f'order {i} is picked up'),1)
                self.assertEqual(log.count(f'order {i} is delivered'),1)
                self.assertEqual(sum(o.id==i for o in acceptance),1)
                self.assertEqual(next(o for o in acceptance if o.id==i).acceptance_time,0)
            paths=read(out/'manifest.json')['input_paths']
            actual=runner.verify(out/'simulation.log',paths['orders'],paths['vehicles'],paths['routes'])
            self.assertEqual(str(actual['total_score']),result['score']['total_score'])

    def test_GP_uses_same_contract_and_final_gate(self):
        with tempfile.TemporaryDirectory() as name:
            code,out,_=self.run_tiny('gp',Path(name))
            result=json.loads((out/'result.json').read_text())
            self.assertEqual(code,0)
            self.assertTrue(result['contract_complete'])
            self.assertEqual(result['completed_items'],2)

    def test_incomplete_pending_run_has_no_J_and_cannot_certify_legacy_reference(self):
        with tempfile.TemporaryDirectory() as name:
            with patch.object(runner,'verify',side_effect=AssertionError('must not score incomplete')) as scorer:
                code,out,_=self.run_tiny('vnsme',Path(name),never_publish=True)
            result=json.loads((out/'result.json').read_text())
            self.assertEqual(code,1);self.assertFalse(result['valid']);self.assertIsNone(result['score'])
            self.assertFalse(result['contract_complete']);scorer.assert_not_called()
            with self.assertRaisesRegex(ValueError,'different commitment contract'):
                independent_score(out,ROOT/'datasets/unused','synthetic_contract')

    def test_completed_service_with_failed_scorer_still_has_no_valid_J(self):
        with tempfile.TemporaryDirectory() as name:
            with patch.object(runner,'verify',side_effect=ValueError('independent scorer rejected log')):
                code,out,_=self.run_tiny('vnsme',Path(name))
            result=json.loads((out/'result.json').read_text())
            self.assertEqual(code,1)
            self.assertEqual(result['completed_items'],2)
            self.assertTrue(result['contract_complete'])
            self.assertFalse(result['valid'])
            self.assertIsNone(result['score'])

    def test_versioned_protocol_is_opt_in_and_cannot_relabel_old_references(self):
        self.assertEqual(contract_metadata(LEGACY_CONTRACT),{'contract_version':LEGACY_CONTRACT})
        self.assertIn('contract_protocol_sha256',contract_metadata(EXECUTION_CONTRACT))
        self.assertNotEqual(LEGACY_CONTRACT,EXECUTION_CONTRACT)


if __name__=='__main__':
    unittest.main()
