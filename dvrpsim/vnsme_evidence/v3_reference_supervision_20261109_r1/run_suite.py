"""Run the complete local unittest suite and save UTF-8 evidence."""
import json
from pathlib import Path
import sys
import time
import unittest

root=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(root))
start=time.perf_counter()
suite=unittest.defaultTestLoader.discover(str(root),pattern='test*.py')
tag=sys.argv[1] if len(sys.argv)>1 else 'final'
with (Path(__file__).parent/f'regression_{tag}.log').open('x',encoding='utf-8') as stream:
    result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
payload=dict(tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),
             skipped=len(result.skipped),wall_seconds=time.perf_counter()-start,
             passed=result.wasSuccessful() and not result.skipped)
with (Path(__file__).parent/f'regression_{tag}.json').open('x',encoding='utf-8') as out:
    out.write(json.dumps(payload,indent=2))
print(json.dumps(payload))
raise SystemExit(0 if payload['passed'] else 1)
