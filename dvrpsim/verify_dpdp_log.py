"""Check the original DPDP example's log against the repository CSV inputs."""
import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path

root = Path(__file__).resolve().parent
log_path = Path(sys.argv[1]) if len(sys.argv) > 1 else root / 'run_logs/dpdp_success.log'
raw = log_path.read_bytes()
log = raw.decode('utf-16' if raw.startswith((b'\xff\xfe', b'\xfe\xff')) else 'utf-8-sig')
data = root / 'examples/case_studies/dpdp/data'

def read_csv(path):
    with path.open(newline='', encoding='utf-8-sig') as handle:
        return list(csv.DictReader(handle))

rows = read_csv(data / 'instance_1/50_1.csv')
vehicles = read_csv(data / 'instance_1/vehicle_info_5.csv')
expected = {
    f"{row['order_id']}-{i + 1}"
    for row in rows
    for i in range(sum(int(row[key]) for key in ('q_standard', 'q_small', 'q_box')))
}

def require(condition, message):
    if not condition:
        raise RuntimeError(message)

require(len(rows) == 50 and len(vehicles) == 5, 'Unexpected input size')
require(not re.search(r'ERROR|WARNING|Traceback|could not finish simulation', log), 'Error or warning in log')
events = {}
for kind in ('requested', 'picked up', 'delivered'):
    matches = re.findall(
        r'INFO\s*:\s*([\d.]+)\s*\|\s*[\d:]+\s*\|\s*(?:(V_\d+)\s*\|\s*)?order (\S+) is ' + kind,
        log,
    )
    require(Counter(item for _, _, item in matches) == Counter(expected), f'Incomplete/duplicate {kind} events')
    events[kind] = {item: (float(time), vehicle) for time, vehicle, item in matches}

finishes = re.findall(r'INFO\s*:\s*([\d.]+)\s*\|\s*[\d:]+\s*\|\s*FINISH', log)
require(len(finishes) == 1, 'Missing or duplicate FINISH')
finish = float(finishes[0])
for item in expected:
    request = events['requested'][item]
    pickup = events['picked up'][item]
    delivery = events['delivered'][item]
    require(request[0] <= pickup[0] <= delivery[0] <= finish, f'Invalid event sequence: {item}')
    require(pickup[1] == delivery[1], f'Vehicle mismatch: {item}')

adjustments = re.findall(r'delivery time of order (\S+) has been set to ([\d.]+)', log)
require(Counter(item for item, _ in adjustments) == Counter(expected), 'Missing delivery-time adjustments')
delivery_times = {item: float(time) for item, time in adjustments}

def seconds(value):
    h, m, s = map(int, value.split(':'))
    return h * 3600 + m * 60 + s

tardiness = {}
for row in rows:
    due = seconds(row['committed_completion_time'])
    if due < seconds(row['creation_time']):
        due += 86400
    delivered = max(time for item, time in delivery_times.items() if item.rsplit('-', 1)[0] == row['order_id'])
    tardiness[row['order_id']] = max(0, delivered - due)

require('vehicle    ' in log and 'tardiness' in log and log.count('total      ') == 2, 'Missing statistics tables')
sample = '0003480001-1'
summary = {
    'verification': 'PASS',
    'log': str(log_path.resolve()),
    'vehicles': len(vehicles),
    'factories': len(read_csv(data / 'factory_info.csv')),
    'original_orders': len(rows),
    'items_requested_picked_up_delivered_once_each': len(expected),
    'finish_seconds': finish,
    'last_physical_delivery_seconds': max(time for time, _ in events['delivered'].values()),
    'late_original_orders': sum(value > 0 for value in tardiness.values()),
    'total_tardiness_seconds': sum(tardiness.values()),
    'average_tardiness_seconds': sum(tardiness.values()) / len(rows),
    'sample_item': sample,
    'sample_events': {kind: values[sample] for kind, values in events.items()},
    'sample_effective_delivery_seconds': delivery_times[sample],
}
print(json.dumps(summary, indent=2))
