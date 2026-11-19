import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'src'))
from baselines.vnsme import java_search_budget_args

VENDOR = ROOT / 'third_party' / 'vnsme'


class VNSMESearchBudgetTests(unittest.TestCase):
    def test_adapter_builds_separate_java_option(self):
        self.assertEqual(java_search_budget_args(10), ['--search-budget-seconds', '10'])
        self.assertEqual(java_search_budget_args(None), [])
        with self.assertRaises(ValueError):
            java_search_budget_args(0)

    def test_java_parses_budget_and_stops_at_shared_budget_predicate(self):
        javac, java = shutil.which('javac'), shutil.which('java')
        if not javac or not java:
            self.skipTest('JDK is not installed')
        with tempfile.TemporaryDirectory(prefix='vnsme-budget-test-') as temp:
            output = Path(temp) / 'classes'
            output.mkdir()
            sources = sorted((VENDOR / 'original').rglob('*.java'))
            compiled = subprocess.run(
                [javac, '--release', '8', '-encoding', 'UTF-8', '-cp', str(VENDOR / 'lib'),
                 '-d', str(output), *map(str, sources)],
                capture_output=True, text=True, timeout=60)
            self.assertEqual(compiled.returncode, 0, compiled.stderr)
            budget = 0.04
            result = subprocess.run(
                [java, '-cp', str(output) + __import__('os').pathsep + str(VENDOR / 'lib'),
                 'main_algorithm', '--search-budget-seconds', str(budget), '--self-test-search-budget'],
                capture_output=True, text=True, timeout=3)
            self.assertEqual(result.returncode, 0, result.stderr)
            match = re.search(r'SEARCH_BUDGET_PROBE budget_seconds=([0-9.]+) elapsed_seconds=([0-9.]+) iterations=(\d+)', result.stdout)
            self.assertIsNotNone(match, result.stdout)
            self.assertAlmostEqual(float(match.group(1)), budget)
            self.assertGreaterEqual(float(match.group(2)), budget)
            self.assertLess(float(match.group(2)), budget + 0.5)
            self.assertGreater(int(match.group(3)), 0)

    def test_all_previous_nine_minute_search_checks_use_configured_predicate(self):
        source = (VENDOR / 'original' / 'main_algorithm.java').read_text(encoding='utf-8')
        self.assertEqual(source.count('9 * 60'), 1)  # unchanged default value only
        self.assertGreaterEqual(source.count('searchBudgetExpired()'), 9)
        self.assertNotIn('usedTime < 9 * 60', source)
        self.assertNotIn('usedTime > 9 * 60', source)


if __name__ == '__main__':
    unittest.main()
