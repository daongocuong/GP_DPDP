"""Verify the development data boundary without opening final-test CSVs."""
import builtins
import io
from pathlib import Path
import unittest
from unittest.mock import patch

from dpdp_dataset import CASE, rows, resolve_inputs
from dpdp_sealed import require_development_path
from prepare_dpdp_data import verify_existing
from train_dpdp_gp_multinstance import DEFAULT_DATASET
from verify_dpdp_score import read_orders
import sys
sys.path.insert(0,str(CASE))
from dpdp_problemdata import read_dpdp_problem

class SealedBoundaryTests(unittest.TestCase):
    def test_direct_content_and_instance_resolution_are_denied_before_open(self):
        for i in (7,8,15,16):
            path=DEFAULT_DATASET/'benchmark'/f'instance_{i}'/'not-opened.csv'
            with self.assertRaises(PermissionError): require_development_path(path)
            with self.assertRaises(PermissionError): rows(path,'order')
            with self.assertRaises(PermissionError): resolve_inputs(instance_directory=path.parent)
            with self.assertRaises(PermissionError): read_orders(path)
            with self.assertRaises(PermissionError): read_dpdp_problem(path,path,path,path)

    def test_real_manifest_verification_never_opens_sealed_csvs(self):
        old_builtin,old_io=builtins.open,io.open
        def blocked(original):
            def check(file,*args,**kwargs):
                if isinstance(file,(str,Path)) and str(file).lower().endswith('.csv'):
                    require_development_path(file)
                return original(file,*args,**kwargs)
            return check
        with patch('builtins.open',blocked(old_builtin)), patch('io.open',blocked(old_io)):
            manifest=verify_existing(DEFAULT_DATASET)
        self.assertTrue(manifest['all_verified'])  # trusted historical metadata only

if __name__=='__main__': unittest.main()
