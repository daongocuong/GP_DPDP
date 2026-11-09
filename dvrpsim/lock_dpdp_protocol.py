"""Lock data roles BEFORE new GP; no GP or simulation is run by this script."""
import argparse
import hashlib
import json
from pathlib import Path

from dpdp_dataset import ROOT
from prepare_dpdp_data import COMMIT, verify_existing


def write_protocol(dataset, output):
    dataset, output = Path(dataset).resolve(), Path(output).resolve()
    manifest = verify_existing(dataset)
    data_hash = hashlib.sha256((dataset/'source_manifest.json').read_bytes()).hexdigest()
    roles = {
        'development_previously_exposed': [1, 17],
        '50_orders': {'train': [2,3,4,5], 'validation': [6], 'final_test_sealed': [7,8]},
        '100_orders_proposed': {'train': [9,10,11,12], 'validation': [13,14], 'final_test_sealed': [15,16]},
    }
    payload = dict(protocol='dpdp-official-split-v1', client_date='2026-11-05', timezone='Asia/Bangkok',
                   source_repository='huawei-noah/xingtian', source_commit=COMMIT,
                   dataset_manifest=str((dataset/'source_manifest.json').relative_to(ROOT)),
                   dataset_manifest_sha256=data_hash, roles=roles,
                   baseline_calibration_instances=[2,6,9,13], legacy_regression_instances=[1],
                   prohibited_rollout_instances_this_task=[7,8,15,16],
                   gp_allowed_this_task=False, environment_seed=0,
                   calibration_hard_process_deadline_seconds=180,
                   inventory={i:{k:v[k] for k in ('original_orders','items_after_loader','vehicles')}
                              for i,v in manifest['instances'].items()},
                   constraints=[
                       'Only checksum/schema/loader inventory may inspect sealed test CSVs in this task; no rollout or score.',
                       'Instances 1 and 17 have already exposed GP results; never label them untouched final test.',
                       'The 100-order split is provisional before GP; 9 and 13 are timing calibration on proposed train/validation.',
                       'If an instance is used to choose methods, its results are development/validation, not untouched test.',
                       'Freeze candidate generation, features, methods, budgets and selection rules before a separately authorized final test.',
                       'Shared factory network and possible scenario relationships preclude assuming statistical independence merely from IDs.',
                       'No new GP training, validation-based tree choice or test opening in this preparation task.',
                   ])
    raw = (json.dumps(payload, indent=2, sort_keys=True)+'\n').encode()
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('xb') as handle:
        handle.write(raw)
    checksum = hashlib.sha256(raw).hexdigest()
    with output.with_suffix(output.suffix+'.sha256').open('x', encoding='ascii') as handle:
        handle.write(checksum+'  '+output.name+'\n')
    print('protocol_sha256='+checksum)
    return payload


def load_locked_protocol(path):
    path = Path(path).resolve()
    raw = path.read_bytes()
    expected = path.with_suffix(path.suffix+'.sha256').read_text(encoding='ascii').split()[0]
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError('protocol checksum mismatch')
    protocol = json.loads(raw)
    manifest = ROOT/protocol['dataset_manifest']
    if hashlib.sha256(manifest.read_bytes()).hexdigest() != protocol['dataset_manifest_sha256']:
        raise ValueError('dataset manifest changed after protocol lock')
    if protocol['source_commit'] != COMMIT or protocol['gp_allowed_this_task']:
        raise ValueError('invalid preparation protocol')
    return protocol


def authorize_baseline(protocol, instances):
    allowed = set(protocol['baseline_calibration_instances']+protocol['legacy_regression_instances'])
    if not set(instances) <= allowed or set(instances) & set(protocol['prohibited_rollout_instances_this_task']):
        raise ValueError('requested instance is not authorized for this baseline calibration')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    write_protocol(args.dataset, args.output)
