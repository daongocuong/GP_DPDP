"""Append-only execution evidence for v3, without influencing decisions."""
from dataclasses import asdict
import json
from pathlib import Path

SCHEMA = 'dpdp-independent-replay-v1'

class TraceWriter:
    def __init__(self, path):
        self.path=Path(path)
        with self.path.open('x',encoding='utf-8') as out:
            out.write(json.dumps(dict(kind='header',schema=SCHEMA),sort_keys=True)+'\n')

    def decision(self,snapshot,raw,plans):
        items={}
        for item,order in snapshot.objects.items():
            items[item]=dict(original_id=order.original_id,quantity=order.quantity,
                pickup=order.pickup_location.id,delivery=order.delivery_location.id,
                release=order.release_date,due=order.due_date,accepted=order.is_accepted,
                picked=order.is_picked_up,delivered=order.is_delivered,
                pickup_vehicle=order.pickup_vehicle.id if order.pickup_vehicle else None,
                pickup_time=order.pickup_time,delivery_time=order.delivery_time)
        event=dict(kind='decision',time=snapshot.now,items=items,
            fleet={key:asdict(value) for key,value in snapshot.fleet.items()},
            previous_plans={key:asdict(value) for key,value in snapshot.plans.items()},
            published_plans={key:asdict(value) for key,value in plans.items()},raw=raw)
        with self.path.open('a',encoding='utf-8') as out:
            out.write(json.dumps(event,sort_keys=True,allow_nan=False)+'\n')
