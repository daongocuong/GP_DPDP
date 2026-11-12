"""Offline rejection and completion-gate checks; no benchmark rollouts."""
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import dpdp_vnsme_reference_v3 as v3

class ReferenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name)
        self.summary = self.root/'summary.json'

    def tearDown(self): self.tmp.cleanup()

    def write(self, data): self.summary.write_text(json.dumps(data),encoding='utf-8')

    def test_v2_summary_rejected(self):
        self.write(dict(valid=True,fitness_version='gp-fitness-vnsme-v2',contract_version='dpdp-accepted-route-v2'))
        with self.assertRaisesRegex(ValueError,'rejects v2'): v3.load_reference(self.summary,[2])

    def test_instance_mismatch_and_duplicate_rejected(self):
        base=dict(valid=True,fitness_version=v3.FITNESS_VERSION,contract_version=v3.EXECUTION_CONTRACT)
        for rows in ([{'instance':2}], [{'instance':2},{'instance':2}]):
            self.write(dict(base,records=rows))
            with self.assertRaisesRegex(ValueError,'instance set'): v3.load_reference(self.summary,[2,3])

    def test_checksum_mismatch_rejected_before_audit(self):
        (self.root/'artifact').write_text('modified')
        row=dict(instance=2,run_directory=str(self.root),artifact_sha256={'artifact':'bad'},supervision_sha256={})
        self.write(dict(valid=True,fitness_version=v3.FITNESS_VERSION,contract_version=v3.EXECUTION_CONTRACT,records=[row]))
        with self.assertRaisesRegex(ValueError,'checksum'): v3.load_reference(self.summary,[2])

    def test_invalid_incomplete_no_score_even_if_ledger_complete(self):
        source=Path(__file__).resolve().parent/'vnsme_evidence/scale100_contract_resolution/tiny_lifecycle_vnsme/run'
        run=self.root/'run'; shutil.copytree(source,run)
        manifest=json.loads((run/'manifest.json').read_text())
        result=json.loads((run/'result.json').read_text()); result.update(valid=False,contract_complete=False,score=None)
        (run/'result.json').write_text(json.dumps(result))
        metadata=dict(contract_protocol_sha256=manifest['contract_protocol_sha256'])
        settings={k:manifest[k] for k in v3.SIMULATION}
        with patch.object(v3,'metadata',return_value=metadata), patch.object(v3,'SIMULATION',settings), \
             patch.object(v3,'runtime_fingerprint'), patch.object(v3,'verify') as scorer:
            with self.assertRaisesRegex(ValueError,'incomplete'): v3.audit_run(run,'synthetic_contract')
            scorer.assert_not_called()

    def test_development_metadata_and_final_test_sealed(self):
        for instance in (2,3,4,5,6,9,10,13):
            m=v3.metadata(instance)
            self.assertEqual(m['orders'],50 if instance<9 else 100)
            self.assertEqual(m['role'],'validation' if instance in (6,13) else 'train')
        for instance in (7,8,15,16):
            with self.assertRaisesRegex(ValueError,'sealed'): v3.metadata(instance)

    def test_completed_synthetic_gp_is_independently_rescored(self):
        from test_dpdp_execution_contract import TinyLifecycleTests
        code,run,_=TinyLifecycleTests().run_tiny('gp',self.root)
        self.assertEqual(code,0)
        manifest=json.loads((run/'manifest.json').read_text()); paths=manifest['input_paths']
        metadata=dict(contract_protocol_sha256=manifest['contract_protocol_sha256'],input_paths=paths,
                      data_sha256={k:v3.digest(v) for k,v in paths.items()})
        settings={k:manifest[k] for k in v3.SIMULATION}
        with patch.object(v3,'metadata',return_value=metadata), patch.object(v3,'SIMULATION',settings), \
             patch.object(v3,'runtime_fingerprint'):
            score,_=v3.audit_run(run,'synthetic_contract',policy='gp')
        self.assertTrue(score['valid']); self.assertEqual(score['items'],2)

    def test_loader_accepts_pinned_mock_record_and_reaudits(self):
        (self.root/'artifact').write_text('ok'); (self.root/'supervision').write_text('ok')
        row=dict(instance=2,run_directory=str(self.root),supervision_directory=str(self.root),
                 artifact_sha256={'artifact':v3.digest(self.root/'artifact')},
                 supervision_sha256={'supervision':v3.digest(self.root/'supervision')},J='3.5')
        self.write(dict(valid=True,fitness_version=v3.FITNESS_VERSION,contract_version=v3.EXECUTION_CONTRACT,records=[row]))
        with patch.object(v3,'audit_vnsme_run',return_value=row) as audit:
            scores,_=v3.load_reference(self.summary,[2])
        self.assertEqual(scores,{2:3.5}); audit.assert_called_once()

    def test_v3_normalization_separates_validation_and_rejects_mixed_contract(self):
        import dpdp_gp_fitness_v3 as fitness
        manifest=dict(contract_version=v3.EXECUTION_CONTRACT,contract_protocol_sha256='p',
                      initial_locations={'v':'a'},initial_location_seed=0,python_version='x',packages={},
                      tree_file_sha256='treehash',gp_tree={'tree':'same'})
        rows=[dict(instance=2,role='train',run_directory='r2'),dict(instance=6,role='validation',run_directory='r6')]
        base=({2:10.,6:20.},dict(records=rows))
        def audit(run, instance, policy): return {'total_score':str({2:20,6:10}[instance])},dict(manifest)
        with patch.object(fitness,'load_reference',return_value=base),patch.object(fitness,'audit_run',side_effect=audit), \
             patch.object(fitness,'read',return_value=manifest),patch.object(fitness,'runtime_fingerprint',return_value={'source':'h'}):
            actual=fitness.evaluate('ref',{2:'g2',6:'g6'},[2],[6])
        self.assertEqual(actual['train_fitness'],2.)
        self.assertEqual(actual['validation_ratios'],{6:.5})
        reference=dict(manifest,contract_version='dpdp-accepted-route-v2')
        with patch.object(fitness,'load_reference',return_value=base),patch.object(fitness,'audit_run',side_effect=audit), \
             patch.object(fitness,'read',return_value=reference),patch.object(fitness,'runtime_fingerprint',return_value={'source':'h'}):
            with self.assertRaisesRegex(ValueError,'compatibility mismatch'): fitness.evaluate('ref',{2:'g2',6:'g6'},[2],[6])

if __name__=='__main__': unittest.main()
