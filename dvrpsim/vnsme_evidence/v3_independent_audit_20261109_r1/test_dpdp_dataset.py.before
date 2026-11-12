"""Data/protocol tests only. No GP, training, or sealed-test rollout."""
import contextlib
import csv
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from dpdp_dataset import ROOT, CASE, DatasetError, resolve_inputs, validate_instance, rows, seconds
from prepare_dpdp_data import COMMIT, compare_common, acquire, verify_existing
from lock_dpdp_protocol import load_locked_protocol, authorize_baseline

DATASET = ROOT/'datasets/xingtian'/COMMIT
BENCHMARK = DATASET/'benchmark'
PROTOCOL = ROOT/'protocols/dpdp_gp_split_v1.json'


class DatasetTests(unittest.TestCase):
    def test_legacy_paths_unchanged(self):
        for number, name in ((1,'50_1.csv'), (17,'300_1.csv')):
            p = resolve_inputs(instance=number)
            self.assertEqual(p['orders'], CASE/f'data/instance_{number}'/name)
            self.assertEqual(p['routes'], CASE/'data/route_info.csv')

    def test_explicit_directory_discovers_real_filenames(self):
        for i, name in ((2,'50_2.csv'), (9,'100_1.csv'), (16,'100_8.csv')):
            p = resolve_inputs(instance_directory=BENCHMARK/f'instance_{i}')
            self.assertEqual(p['orders'].name, name)
            self.assertEqual(p['instance'], i)
            self.assertEqual(p['routes'], BENCHMARK/'route_info.csv')

    def test_ambiguous_directory_refused(self):
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d)/'synthetic_fixture'
            folder.mkdir()
            for name in ('orders.csv','extra.csv','vehicle_info_5.csv'):
                (folder/name).write_text('fixture', encoding='utf-8')
            with self.assertRaises(DatasetError):
                resolve_inputs(instance_directory=folder, data_directory=BENCHMARK)

    def test_positional_schema_must_match_loader(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/'bad.csv'
            p.write_text('capacity,car_num,operation_time,gps_id\n15,V,24,G\n', encoding='utf-8')
            with self.assertRaisesRegex(DatasetError, 'positional'):
                rows(p, 'vehicle')

    def corrupt_order(self, field, value):
        # All mutations are temporary synthetic copies, never official CSVs.
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d)/'synthetic_fixture'
            folder.mkdir()
            shutil.copyfile(BENCHMARK/'instance_2/vehicle_info_5.csv', folder/'vehicle_info_5.csv')
            with (BENCHMARK/'instance_2/50_2.csv').open(encoding='utf-8-sig', newline='') as handle:
                reader = csv.DictReader(handle)
                header, content = reader.fieldnames, list(reader)
            content[0][field] = value
            with (folder/'orders.csv').open('w', encoding='utf-8', newline='') as handle:
                writer = csv.DictWriter(handle, fieldnames=header)
                writer.writeheader()
                writer.writerows(content)
            with self.assertRaises(DatasetError):
                validate_instance(folder, BENCHMARK)

    def test_unknown_factory_refused(self):
        self.corrupt_order('pickup_id', 'NOT_A_FACTORY')

    def test_negative_or_fractional_item_counts_refused(self):
        self.corrupt_order('q_standard', '-1')
        self.corrupt_order('q_standard', '0.5')

    def test_invalid_time_refused(self):
        self.corrupt_order('creation_time', '25:00:00')
        self.assertEqual(seconds('23:59:59'), 86399)

    def test_csv_loader_duration_disagreement_refused(self):
        self.corrupt_order('load_time', '999')

    def test_common_csv_mismatch_fails_closed(self):
        blobs = {n:(BENCHMARK/n).read_bytes() for n in ('factory_info.csv','route_info.csv')}
        self.assertTrue(compare_common(blobs, CASE/'data')['route_info.csv']['byte_identical'])
        blobs['factory_info.csv'] += b'\n'
        with self.assertRaisesRegex(ValueError, 'BYTE MISMATCH'):
            compare_common(blobs, CASE/'data')

    def test_network_failure_creates_no_fake_dataset(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)/'failed_download'
            with patch('prepare_dpdp_data.fetch', side_effect=RuntimeError('Network download failed: pinned API unavailable')):
                with self.assertRaisesRegex(RuntimeError, 'Network download failed'):
                    acquire(out)
            failure = json.loads((out/'ACQUISITION_FAILED.json').read_text(encoding='utf-8'))
            self.assertFalse(failure['experiments_allowed'])
            self.assertFalse((out/'benchmark').exists())

    def test_real_manifest_hash_schema_and_loader_offline(self):
        with contextlib.redirect_stdout(io.StringIO()):
            manifest = verify_existing(DATASET)
        self.assertEqual(set(manifest['instances']), {str(i) for i in range(2,17)})
        self.assertEqual(len(manifest['files']), 32)
        for i, instance in manifest['instances'].items():
            self.assertEqual(instance['original_orders'], 50 if int(i) <= 8 else 100)
            self.assertEqual(instance['vehicles'], 5)
            self.assertEqual(len(instance['files']), 2)
            self.assertTrue(instance['loader_verified'])
        for file in manifest['files']:
            self.assertEqual(file['commit'], COMMIT)
            self.assertTrue(file['url'].startswith(f'https://raw.githubusercontent.com/huawei-noah/xingtian/{COMMIT}/simulator/dpdp_competition/benchmark/'))


class ProtocolTests(unittest.TestCase):
    def test_roles_and_no_gp_permission(self):
        p = load_locked_protocol(PROTOCOL)
        self.assertFalse(p['gp_allowed_this_task'])
        self.assertEqual(p['roles']['development_previously_exposed'], [1,17])
        self.assertEqual(p['roles']['50_orders']['train'], [2,3,4,5])
        self.assertEqual(p['roles']['50_orders']['validation'], [6])
        self.assertEqual(p['roles']['50_orders']['final_test_sealed'], [7,8])

    def test_sealed_tests_never_authorized_for_calibration(self):
        p = load_locked_protocol(PROTOCOL)
        authorize_baseline(p, [1,2,6,9,13])
        for i in (7,8,15,16,17):
            with self.assertRaises(ValueError):
                authorize_baseline(p, [i])

    def test_protocol_tampering_is_detected(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/'protocol.json'
            shutil.copyfile(PROTOCOL, p)
            shutil.copyfile(PROTOCOL.with_suffix('.json.sha256'), p.with_suffix('.json.sha256'))
            p.write_bytes(p.read_bytes()+b' ')
            with self.assertRaisesRegex(ValueError, 'checksum'):
                load_locked_protocol(p)


if __name__ == '__main__':
    unittest.main()
