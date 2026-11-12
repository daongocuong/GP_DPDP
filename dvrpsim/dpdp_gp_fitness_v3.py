"""Strict offline v3 GP normalization. This module does not train GP."""
import math
from pathlib import Path
from dpdp_vnsme_reference_v3 import (EXECUTION_CONTRACT, FITNESS_VERSION, audit_run,
                                     load_reference, read, runtime_fingerprint)

# Ghi chú: Chuẩn hóa offline các rollout GP đã có theo VNSME V3; kiểm cùng cây và điều kiện chạy, không thực hiện huấn luyện.
def evaluate(reference, gp_runs, train, validation, relocation=None):
    train, validation = tuple(train), tuple(validation)
    if not train or not validation or set(train) & set(validation): raise ValueError('invalid split')
    expected = set(train) | set(validation)
    baselines, summary = (load_reference(reference, expected, relocation) if relocation
                          else load_reference(reference, expected))
    rows = {r['instance']: r for r in summary['records']}
    if len(gp_runs) != len(expected) or set(gp_runs) != expected: raise ValueError('missing or duplicate GP instances')
    ratios = {}
    tree_identity = None
    for instance in sorted(expected):
        role = 'train' if instance in train else 'validation'
        if rows[instance]['role'] != role: raise ValueError('instance has wrong protocol role')
        score, gp = (audit_run(gp_runs[instance], instance, policy='gp', relocation=relocation) if relocation
                     else audit_run(gp_runs[instance], instance, policy='gp'))
        if not gp.get('tree_file_sha256') or not gp.get('gp_tree'): raise ValueError('GP tree provenance missing')
        identity = (gp['tree_file_sha256'], gp['gp_tree'])
        if tree_identity is None: tree_identity = identity
        elif identity != tree_identity: raise ValueError('GP rollouts must use the same tree')
        reference_run = summary.get('resolved_run_directories', {}).get(str(instance), rows[instance]['run_directory'])
        reference_manifest = read(Path(reference_run)/'manifest.json')
        for key in ('contract_version','contract_protocol_sha256','initial_locations','initial_location_seed',
                    'python_version','packages'):
            if gp.get(key) != reference_manifest.get(key): raise ValueError(f'GP/VNSME compatibility mismatch: {key}')
        if runtime_fingerprint(gp) != runtime_fingerprint(reference_manifest): raise ValueError('GP/VNSME simulator source mismatch')
        if not math.isfinite(baselines[instance]) or baselines[instance] <= 0: raise ValueError('invalid VNSME denominator')
        ratio = float(score['total_score'])/baselines[instance]
        if not math.isfinite(ratio) or ratio < 0: raise ValueError('invalid GP ratio')
        ratios[instance] = ratio
    return dict(fitness_version=FITNESS_VERSION, contract_version=EXECUTION_CONTRACT,
                train_fitness=sum(ratios[i] for i in train)/len(train),
                validation_ratios={i:ratios[i] for i in validation}, ratios=ratios,
                validation_used_in_training=False)
