"""Replay v3 decisions and physical events without importing runner guards.

The checker derives the physical stack from simulation.log, compares it to each
pre-decision trace, and independently simulates each published remaining plan.
Missing evidence is UNVERIFIABLE, never PASS. It does not reproduce dock-queue
forecasting, so ETA is checked against the captured pre-decision lock and, for
vehicles in transit, independently against the logged departure and matrix.
"""
import csv
from decimal import Decimal
import json
from pathlib import Path
import re

from dpdp_dataset import rows, seconds
from dpdp_v3_trace import SCHEMA

class AuditFailure(ValueError): pass
class MissingEvidence(ValueError): pass

def need(condition, message):
    if not condition: raise AuditFailure(message)

def parse_inputs(paths):
    items={}; demands={}
    for row in rows(paths['orders'],'order'):
        order=row['order_id']; release=seconds(row['creation_time']); due=seconds(row['committed_completion_time'])
        if due<release: due+=86400
        quantities=[Decimal(1)]*int(row['q_standard'])+[Decimal('.5')]*int(row['q_small'])+[Decimal('.25')]*int(row['q_box'])
        demands[order]=sum(quantities,Decimal(0))
        for index,q in enumerate(quantities,1):
            items[f'{order}-{index}']=dict(original_id=order,quantity=q,pickup=row['pickup_id'],
                delivery=row['delivery_id'],release=release,due=due)
    vehicles={r['car_num']:Decimal(r['capacity']) for r in rows(paths['vehicles'],'vehicle')}
    routes={(r['start_factory_id'],r['end_factory_id']):int(r['time']) for r in rows(paths['routes'],'route')}
    return items,demands,vehicles,routes

def inspect_plan(event, items, demands, vehicles):
    fleet=event['fleet']; before=event['previous_plans']; plans=event['published_plans']; raw=event['raw']
    need(set(fleet)==set(vehicles)==set(before)==set(plans)==set(raw['vehicles']),'FLEET')
    admitted=set(i for i,s in event['items'].items() if s['delivered'])
    owner={}; picked=set(); done=set(admitted); batches={}
    capset=set(vehicles.values()); need(len(capset)==1,'CAPACITY_SCHEMA'); capacity=next(iter(capset))
    def batch(item,token):
        order=items[item]['original_id']; batches.setdefault(order,set()).add(token)
        need(demands[order]>capacity or len(batches[order])<=1,f'ORDER_SPLIT {order}')
    for vehicle,state in fleet.items():
        need(Decimal(str(state['capacity']))==vehicles[vehicle],f'CAPACITY_SCHEMA {vehicle}')
        for item in state['carrying']:
            need(item in items and item not in owner and item not in done,f'INITIAL_OWNERSHIP {item}')
            owner[item]=vehicle; picked.add(item); admitted.add(item)
            current=state['current']; token='current' if state['service_started'] and current and item in current['pickups'] else 'initial'
            batch(item,(vehicle,token))
        need(sum((items[i]['quantity'] for i in state['carrying']),Decimal(0))<=capacity,f'CAPACITY {vehicle}')
    for vehicle,state in fleet.items():
        plan=plans[vehicle]; prior=before[vehicle]; decision=raw['vehicles'][vehicle]
        need(plan['current']==prior['current']==state['current'],f'CURRENT_LOCK {vehicle}')
        need(decision.get('current_visit') is None,f'CURRENT_LOCK {vehicle}')
        published=decision['next_visits']
        need(published is not None and len(published)==len(plan['future']),f'PUBLISHED_ROUTE {vehicle}')
        for index,(node,visit) in enumerate(zip(published,plan['future'])):
            need(node['location']==visit['factory'] and node.get('pickup_list',[])==visit['pickups'] and
                 node.get('delivery_list',[])==visit['deliveries'],f'PUBLISHED_ROUTE {vehicle}/{index}')
        lock=state['destination']
        if lock:
            need(plan['future'] and plan['future'][0]['factory']==lock['factory'] and
                 plan['future'][0]['arrival']==lock['arrival'],f'DESTINATION_LOCK {vehicle}')
        stack=list(state['carrying'])
        visits=([('current',plan['current'])] if plan['current'] else [])+[(str(i),x) for i,x in enumerate(plan['future'])]
        for step,visit in visits:
            for operation,key in (('delivery','deliveries'),('pickup','pickups')):
                seen=set()
                for item in visit[key]:
                    need(item in event['items'] and item in items,f'UNKNOWN_ITEM {item}')
                    need(item not in seen,f'DUPLICATE_OPERATION {item}'); seen.add(item); admitted.add(item)
                    if step=='current' and state['service_started']:
                        if operation=='delivery' and item in done: continue
                        if operation=='pickup' and (item in stack or item in done): continue
                    spec=items[item]
                    need(visit['factory']==spec[operation],f'FACTORY {item}')
                    if operation=='delivery':
                        need(item not in done,f'DUPLICATE_DELIVERY {item}')
                        need(item in picked,f'DELIVERY_BEFORE_PICKUP {item}')
                        need(owner.get(item)==vehicle,f'OWNERSHIP {item}')
                        need(stack and stack[-1]==item,f'LIFO {item}')
                        stack.pop(); done.add(item)
                    else:
                        need(item not in picked and item not in done,f'DUPLICATE_PICKUP {item}')
                        batch(item,(vehicle,step)); picked.add(item); owner[item]=vehicle; stack.append(item)
                    need(sum((items[i]['quantity'] for i in stack),Decimal(0))<=capacity,f'CAPACITY {vehicle}')
        need(not stack,f'UNDELIVERED_LOAD {vehicle}')
    need(done==admitted,f'MISSING_SERVICE {sorted(admitted-done)[:4]}')
    for item,decision in raw['orders'].items():
        need(item in event['items'] and decision['status']=='accepted' and item in admitted and
             not event['items'][item]['delivered'],f'SERVICE_PROMISE {item}')
    pending=set(event['items'])-admitted
    for order,demand in demands.items():
        ids={i for i in event['items'] if items[i]['original_id']==order}
        if demand<=capacity and ids:
            need(not (ids & pending and ids-pending),f'ORDER_SPLIT {order}')
    return pending

def check_publication(event, epoch, previously_pending, items):
    destinations=json.loads((epoch/'output_destination.json').read_text(encoding='utf-8'))
    routes=json.loads((epoch/'output_route.json').read_text(encoding='utf-8'))
    unallocated=json.loads((epoch/'unallocated_order_items.json').read_text(encoding='utf-8'))
    ongoing=json.loads((epoch/'ongoing_order_items.json').read_text(encoding='utf-8'))
    input_vehicles=json.loads((epoch/'vehicle_info.json').read_text(encoding='utf-8'))
    ids=[x['id'] for x in unallocated+ongoing]
    need(len(ids)==len(set(ids)) and set(ids)<=set(event['items']),'JAVA_INPUT_UNKNOWN_OR_DUPLICATE')
    need(previously_pending <= {x['id'] for x in unallocated},'PENDING_NOT_REOFFERED')
    need(len(input_vehicles)==len(event['fleet']),'JAVA_INPUT_FLEET')
    origins={v['update_time']-event['time'] for v in input_vehicles}
    need(len(origins)==1,'JAVA_INPUT_TIME'); origin=next(iter(origins))
    for item in unallocated+ongoing:
        spec=items[item['id']]
        need(item['order_id']==spec['original_id'] and Decimal(str(item['demand']))==spec['quantity'] and
             item['pickup_factory_id']==spec['pickup'] and item['delivery_factory_id']==spec['delivery'] and
             item['creation_time']==origin+spec['release'] and item['committed_completion_time']==origin+spec['due'],
             f'JAVA_INPUT_ITEM {item["id"]}')
    for vehicle in input_vehicles:
        name=vehicle['id']; need(name in event['fleet'],'JAVA_INPUT_FLEET')
        lock=event['fleet'][name]['destination']; announced=vehicle['destination']
        need(bool(lock)==bool(announced),f'JAVA_INPUT_DESTINATION {name}')
        if lock:
            need(announced['factory_id']==lock['factory'] and announced['arrive_time']==origin+lock['arrival'],f'JAVA_INPUT_DESTINATION {name}')
            need(destinations[name] is not None and destinations[name]['factory_id']==lock['factory'] and
                 destinations[name]['arrive_time']==announced['arrive_time'],f'DESTINATION_ETA_LOCK {name}')
    need(set(destinations)==set(routes)==set(event['raw']['vehicles']),'JAVA_FLEET')
    for vehicle,first in destinations.items():
        nodes=([first] if first is not None else [])+routes[vehicle]
        actual=[dict(location=n['factory_id'],pickup_list=n['pickup_item_list'],delivery_list=n['delivery_item_list']) for n in nodes]
        need(actual==event['raw']['vehicles'][vehicle]['next_visits'],f'JAVA_PUBLICATION {vehicle}')

def audit(run, paths, policy='vnsme'):
    run=Path(run); trace=run/'decision_trace.jsonl'; log=run/'simulation.log'
    if not trace.is_file() or not log.is_file(): return dict(status='UNVERIFIABLE',reason='missing decision trace or simulation log')
    try:
        lines=[json.loads(line) for line in trace.read_text(encoding='utf-8').splitlines()]
        if not lines or lines[0] != dict(kind='header',schema=SCHEMA): raise MissingEvidence('unsupported or missing trace schema')
        events=lines[1:]; need(bool(events),'NO_DECISIONS')
        items,demands,vehicles,routes=parse_inputs(paths)
        manifest=json.loads((run/'manifest.json').read_text(encoding='utf-8'))
        initial=manifest['initial_locations']; need(set(initial)==set(vehicles),'INITIAL_FLEET')
        stacks={v:[] for v in vehicles}; requested=set(); picked={}; delivered={}; locations=dict(initial); traveling={}
        # Initial simulator visits are already completed at time zero.
        started={v:True for v in vehicles}; current_ops={v:None for v in vehicles}; expected_routes={}
        def route_node(node):
            return dict(factory=node['factory'],pickups=node['pickups'],deliveries=node['deliveries'])
        accepted=set(); pending_prior=set(); position=0; last_time=-1
        pattern=re.compile(r'^\w+\s*:\s*([0-9.]+)\s*\|\s*[^|]+\|\s*(.*)$')
        for line in log.read_text(encoding='utf-8').splitlines():
            match=pattern.match(line)
            if not match: continue
            now=float(match.group(1)); message=match.group(2)
            need(now>=last_time,'TIME_REVERSED'); last_time=now
            request=re.fullmatch(r'order (\S+) is requested \(.*',message)
            vehicle_event=re.fullmatch(r'(\S+) \| order (\S+) is (picked up|delivered)',message)
            depart=re.fullmatch(r'(\S+) \| departed from (\S+) to (\S+)',message)
            arrive=re.fullmatch(r'(\S+) \| arrived at (\S+)',message)
            service=re.fullmatch(r'(\S+) \| service is (started|finished)',message)
            delivery_time=re.fullmatch(r'(\S+) \| delivery time of order (\S+) has been set to ([0-9.]+)',message)
            if request:
                item=request.group(1); need(item in items and item not in requested,f'REQUEST_DUPLICATE_OR_UNKNOWN {item}')
                need(now==items[item]['release'],f'RELEASE_TIME {item}'); requested.add(item)
            elif depart:
                vehicle,a,b=depart.groups(); need(vehicle in vehicles,f'VEHICLE {vehicle}')
                need(locations.get(vehicle)==a,f'DEPARTURE_LOCATION {vehicle}')
                duration=0 if a==b else routes[a,b]; traveling[vehicle]=(b,now+duration); locations.pop(vehicle,None)
                current_ops[vehicle]=None; started[vehicle]=False
            elif arrive:
                vehicle,location=arrive.groups(); need(vehicle in vehicles,f'VEHICLE {vehicle}')
                if vehicle in traveling:
                    dest,eta=traveling.pop(vehicle); need(location==dest and now==eta,f'ARRIVAL_LOCK {vehicle}')
                locations[vehicle]=location
                if vehicle in expected_routes:
                    need(bool(expected_routes[vehicle]),f'UNANNOUNCED_ARRIVAL {vehicle}')
                    current_ops[vehicle]=expected_routes[vehicle].pop(0)
                    need(current_ops[vehicle]['factory']==location,f'DESTINATION_LOCK {vehicle}')
                started[vehicle]=False
            elif service:
                vehicle,phase=service.groups(); need(vehicle in vehicles,f'VEHICLE {vehicle}')
                if phase=='started': started[vehicle]=True
            elif delivery_time:
                vehicle,item,stamp=delivery_time.groups()
                need(item in delivered and picked[item][0]==vehicle and float(stamp)<=now,f'DELIVERY_TIME {item}')
                delivered[item]=float(stamp)
            elif vehicle_event:
                vehicle,item,op=vehicle_event.groups(); need(vehicle in vehicles and item in requested,f'UNKNOWN_PHYSICAL_ITEM {item}')
                spec=items[item]
                if op=='picked up':
                    need(item not in picked and item not in delivered,f'DUPLICATE_PICKUP {item}')
                    need(locations.get(vehicle)==spec['pickup'],f'PICKUP_FACTORY {item}')
                    stacks[vehicle].append(item); picked[item]=(vehicle,now)
                    need(sum((items[i]['quantity'] for i in stacks[vehicle]),Decimal(0))<=vehicles[vehicle],f'CAPACITY {vehicle}')
                else:
                    need(item in picked,f'DELIVERY_BEFORE_PICKUP {item}')
                    need(item not in delivered,f'DUPLICATE_DELIVERY {item}')
                    need(picked[item][0]==vehicle,f'OWNERSHIP {item}')
                    need(stacks[vehicle] and stacks[vehicle][-1]==item,f'LIFO {item}')
                    need(locations.get(vehicle)==spec['delivery'],f'DELIVERY_FACTORY {item}')
                    stacks[vehicle].pop(); delivered[item]=now
            elif message=='<<< routing >>>':
                need(position<len(events),'MISSING_DECISION_TRACE'); event=events[position]
                need(event['kind']=='decision' and event['time']==now,f'DECISION_TIME {position}')
                need(set(event['items'])==requested,f'REQUEST_LOSS_OR_FUTURE {position}')
                need(pending_prior<=requested,f'PENDING_LOST {position}')
                for item,state in event['items'].items():
                    spec=items[item]
                    for key in ('original_id','pickup','delivery','release','due'):
                        need(state[key]==spec[key],f'ITEM_CHANGED {item}/{key}')
                    need(Decimal(str(state['quantity']))==spec['quantity'],f'ITEM_CHANGED {item}/quantity')
                    need(state['picked']==(item in picked) and state['delivered']==(item in delivered),f'PHYSICAL_REVERSAL {item}')
                    if item in picked: need((state['pickup_vehicle'],state['pickup_time'])==picked[item],f'OWNERSHIP {item}')
                    if item in delivered: need(state['delivery_time']==delivered[item],f'DELIVERY_TIME {item}')
                    if item in accepted: need(state['accepted'],f'ACCEPTANCE_REVERSED {item}')
                for vehicle,state in event['fleet'].items():
                    need(state['carrying']==stacks[vehicle],f'PHYSICAL_STACK {vehicle}')
                    if state['current']:
                        need(state['service_started']==started[vehicle],f'CURRENT_SERVICE_STATE {vehicle}')
                        if current_ops[vehicle] is None:
                            need(not state['current']['pickups'] and not state['current']['deliveries'],f'CURRENT_UNVERIFIABLE {vehicle}')
                        else:
                            need(route_node(state['current'])==current_ops[vehicle],f'CURRENT_LOCK {vehicle}')
                    if vehicle in expected_routes:
                        need([route_node(x) for x in event['previous_plans'][vehicle]['future']]==expected_routes[vehicle],f'ROUTE_HISTORY {vehicle}')
                    if vehicle in traveling:
                        lock=state['destination']; need(lock is not None and (lock['factory'],lock['arrival'])==traveling[vehicle],f'TRANSIT_ETA_LOCK {vehicle}')
                    if vehicle in locations and state['current']:
                        need(state['current']['factory']==locations[vehicle],f'CURRENT_LOCATION {vehicle}')
                current_pending=inspect_plan(event,items,demands,vehicles)
                accepted.update(i for i,s in event['items'].items() if s['accepted'])
                accepted.update(event['raw']['orders'])
                if policy=='vnsme': check_publication(event,run/'vnsme/epochs'/f'{position:05d}',pending_prior,items)
                expected_routes={v:[route_node(x) for x in plan['future']] for v,plan in event['published_plans'].items()}
                pending_prior=current_pending
                position+=1
        need(position==len(events),'EXTRA_DECISION_TRACE')
        need(requested==set(items),'INCOMPLETE_REQUEST_UNIVERSE')
        need(set(delivered)==set(items) and all(not s for s in stacks.values()),'INCOMPLETE_SERVICE')
        return dict(status='PASS',decisions=position,items=len(items),physical_pickups=len(picked),physical_deliveries=len(delivered),
                    limits=['at-location future ETA is checked against the recorded pre-decision lock, not independently reforecast'])
    except (FileNotFoundError,KeyError,json.JSONDecodeError,TypeError) as exc:
        return dict(status='UNVERIFIABLE',reason=f'missing or malformed evidence: {type(exc).__name__}: {exc}')
    except (AuditFailure,ValueError) as exc:
        return dict(status='FAIL',reason=str(exc))
