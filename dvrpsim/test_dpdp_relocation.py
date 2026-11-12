"""Synthetic path mapping failures; never inspect sealed data."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from dpdp_relocation import Relocation, load_relocation
from dpdp_vnsme_reference_v3 import load_reference, FITNESS_VERSION, EXECUTION_CONTRACT


class RelocationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.mapping = Relocation('C:/historical_nonexistent_dpdp', self.root)
        (self.root/'artifact').write_bytes(b'evidence')
        self.sha = hashlib.sha256(b'evidence').hexdigest()

    def test_original_pin_required_to_match_and_bytes_preserved(self):
        p = self.mapping.resolve('C:/historical_nonexistent_dpdp/artifact', self.sha)
        self.assertEqual(p, self.root/'artifact')
        self.assertEqual(p.read_bytes(), b'evidence')
        with self.assertRaisesRegex(ValueError, 'checksum'):
            self.mapping.resolve('C:/historical_nonexistent_dpdp/artifact', 'bad')

    def test_missing_traversal_outside_relative_and_sealed_rejected(self):
        for path, exception in [
            ('C:/historical_nonexistent_dpdp/missing', FileNotFoundError),
            ('C:/historical_nonexistent_dpdp/../outside', ValueError),
            (str(self.root.parent), ValueError), ('artifact', ValueError),
            ('C:/historical_nonexistent_dpdp/instance_7/orders.csv', PermissionError)]:
            with self.subTest(path=path), self.assertRaises(exception):
                self.mapping.resolve(path)

    def test_ambiguous_source_and_multiple_mappings_rejected(self):
        with patch.object(Path, 'exists', return_value=True):
            with self.assertRaisesRegex(ValueError, 'ambiguous'):
                self.mapping.resolve('C:/historical_nonexistent_dpdp/artifact')
        config = self.root/'config.json'
        config.write_text(json.dumps(dict(schema='dpdp-relocation-v1', mappings=[{},{}])))
        with self.assertRaises(ValueError): load_relocation(config)

    def test_loader_checks_original_hash_before_auditing_and_keeps_historical_paths(self):
        row = dict(instance=2, run_directory='C:/historical_nonexistent_dpdp',
                   supervision_directory='C:/historical_nonexistent_dpdp',
                   artifact_sha256={'artifact':self.sha}, supervision_sha256={}, J='3')
        summary = self.root/'summary.json'
        def write():
            summary.write_text(json.dumps(dict(valid=True, fitness_version=FITNESS_VERSION,
                contract_version=EXECUTION_CONTRACT, records=[row])))
        write()
        current = dict(row, run_directory=str(self.root), supervision_directory=str(self.root))
        with patch('dpdp_vnsme_reference_v3.audit_vnsme_run', return_value=current) as audit:
            scores, data = load_reference(summary, {2}, self.mapping)
            self.assertEqual(scores, {2:3.})
            self.assertEqual(data['records'][0], row)
            self.assertEqual(data['resolved_run_directories']['2'], str(self.root))
            audit.assert_called_once()
        row['artifact_sha256']['artifact'] = 'bad'
        write()
        with patch('dpdp_vnsme_reference_v3.audit_vnsme_run') as audit:
            with self.assertRaisesRegex(ValueError, 'checksum'):
                load_reference(summary, {2}, self.mapping)
            audit.assert_not_called()


if __name__ == '__main__': unittest.main()
