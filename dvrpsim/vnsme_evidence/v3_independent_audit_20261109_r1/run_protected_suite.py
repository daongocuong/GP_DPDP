"""Run all unit tests behind a process-local guard for sealed CSV reads."""
import json
from pathlib import Path
import sys,time,unittest
root=Path(__file__).resolve().parents[2]; here=Path(__file__).parent
sys.path.insert(0,str(root))
from dpdp_sealed import sealed_instance
violations=[]
def deny(event,args):
    if event!='open' or not args: return
    path=args[0]
    if isinstance(path,(str,bytes,Path)):
        try: instance=sealed_instance(Path(path.decode() if isinstance(path,bytes) else path))
        except (OSError,ValueError): return
        if instance is not None:
            violations.append(str(path)); raise PermissionError(f'protected regression suite blocked CSV for final instance_{instance}')
sys.addaudithook(deny)
tag=sys.argv[1] if len(sys.argv)>1 else 'protected'
start=time.perf_counter(); suite=unittest.defaultTestLoader.discover(str(root),pattern='test*.py')
with (here/f'regression_{tag}.log').open('x',encoding='utf-8') as out:
    result=unittest.TextTestRunner(out,verbosity=2).run(suite)
payload=dict(tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),skipped=len(result.skipped),
    wall_seconds=time.perf_counter()-start,sealed_csv_open_attempts=len(violations),violations=violations,
    passed=result.wasSuccessful() and not violations and not result.skipped)
(here/f'regression_{tag}.json').write_text(json.dumps(payload,indent=2),encoding='utf-8')
print(json.dumps(payload)); raise SystemExit(0 if payload['passed'] else 1)
