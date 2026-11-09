import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from dpdp_insertion import InsertionPolicy
from dpdp_gp_fitness import RolloutEvaluator
from dpdp_vnsme_reference import FITNESS_VERSION, adopt
from train_dpdp_gp_multinstance import _baseline_scores, aggregate_training, DEFAULT_BASELINES, DEFAULT_DATASET
import run_dpdp_insertion

ROOT = Path(__file__).resolve().parent


class VNSMENormalizationTests(unittest.TestCase):
    def test_no_implicit_candidate_ranker(self):
        with self.assertRaises(TypeError):
            InsertionPolicy()
        with self.assertRaisesRegex(TypeError, 'explicit'):
            InsertionPolicy(None)

    def test_removed_policy_names_fail_before_output_creation(self):
        for name in ('greedy', 'baseline', 'insertion'):
            with tempfile.TemporaryDirectory() as d:
                output = Path(d)/'run'
                with patch('sys.argv', ['run', '--policy', name, '--output', str(output)]), contextlib.redirect_stderr(io.StringIO()):
                    with self.assertRaises(SystemExit) as exc:
                        run_dpdp_insertion.main()
                self.assertEqual(exc.exception.code, 2)
                self.assertFalse(output.exists())

    def test_removed_policies_rejected_by_python_api_too(self):
        for name in ('greedy', 'baseline', 'insertion'):
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'unsupported policy'):
                run_dpdp_insertion.RunModel(name, Path('unused'))

    def test_old_greedy_summary_cannot_be_used_as_vnsme(self):
        old = ROOT/'gp_runs/multinstance_50_20261105/baseline/summary.json'
        with self.assertRaisesRegex(ValueError, 'requires VNSME'):
            _baseline_scores(old, (2,3,4,5,6), 'unused', 'unused')
        self.assertNotEqual(DEFAULT_BASELINES, old)

    def test_unknown_or_raw_summary_rejected(self):
        for payload in ({}, {'policy':'vnsme'}, {'policy':'gp','fitness_version':FITNESS_VERSION}):
            with tempfile.TemporaryDirectory() as d:
                p=Path(d)/'summary.json'; p.write_text(json.dumps(payload))
                with self.assertRaisesRegex(ValueError, 'requires VNSME'):
                    _baseline_scores(p, (2,3,4,5,6), 'unused', 'unused')

    def test_missing_vnsme_reference_has_actionable_error(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError, 'dpdp_vnsme_reference.py'):
                _baseline_scores(Path(d)/'missing', (2,3,4,5,6), 'unused', 'unused')

    def test_normalized_fitness_uses_vnsme_and_has_new_version(self):
        records=[dict(instance=i,valid=True,benchmark_J='100') for i in (2,3,4,5)]
        result=aggregate_training(records, {2:50,3:100,4:200,5:400})
        self.assertEqual(result['fitness'], .9375)
        self.assertEqual(result['normalization_policy'], 'vnsme')
        self.assertEqual(result['fitness_version'], FITNESS_VERSION)

    def test_nonfinite_vnsme_denominators_rejected(self):
        rows=[dict(instance=i,valid=True,benchmark_J='100') for i in (2,3,4,5)]
        for value in (0,-1,float('nan'),float('inf')):
            with self.subTest(value=value), self.assertRaises(ValueError):
                aggregate_training(rows, {i:value for i in (2,3,4,5)})

    def test_reference_pin_is_part_of_cache_and_checked_during_experiment(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); ref=root/'summary.json'; ref.write_text('reference')
            e=RolloutEvaluator(root/'fitness', 1, normalization_reference_path=ref)
            self.assertEqual(e.context(1)['normalization_reference_sha256'], e.normalization_reference_sha256)
            e.verify_pins()
            ref.write_text('tampered')
            with self.assertRaisesRegex(ValueError, 'normalization reference changed'):
                e.verify_pins()

    def test_adoption_rejects_duplicate_or_sealed_instances_before_scoring(self):
        from train_dpdp_gp_multinstance import DEFAULT_PROTOCOL
        for ids in ((2,2), (7,)):
            with self.subTest(ids=ids), tempfile.TemporaryDirectory() as d:
                root=Path(d); runs=[]
                for index,instance in enumerate(ids):
                    folder=root/str(index); folder.mkdir()
                    (folder/'manifest.json').write_text(json.dumps(dict(instance=instance)))
                    runs.append(folder)
                with patch('dpdp_vnsme_reference.independent_score') as scorer:
                    with self.assertRaisesRegex(ValueError, 'exactly one'):
                        adopt(root/'out', runs, DEFAULT_PROTOCOL, DEFAULT_DATASET)
                    scorer.assert_not_called()
                self.assertFalse((root/'out').exists())

    def test_adoption_requires_all_train_and_validation_runs(self):
        from train_dpdp_gp_multinstance import DEFAULT_PROTOCOL
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); folder=root/'run'; folder.mkdir()
            (folder/'manifest.json').write_text(json.dumps(dict(instance=2)))
            with self.assertRaisesRegex(ValueError, 'missing train/validation'):
                adopt(root/'out', [folder], DEFAULT_PROTOCOL, DEFAULT_DATASET)
            self.assertFalse((root/'out').exists())


if __name__ == '__main__':
    unittest.main()
