"""Bounded Java process-tree smoke; does not run VNSME search or a benchmark."""
import json
from pathlib import Path
import shutil
import subprocess
import sys

root=Path(__file__).resolve().parents[2]; here=Path(__file__).resolve().parent
sys.path[:0]=[str(root),str(root/'src')]
from dpdp_v3_supervisor import supervise,process_identity
from baselines.vnsme import JavaSession

probe=here/'java_probe'; probe.mkdir(exist_ok=False)
java=shutil.which('java'); javac=shutil.which('javac')
source=probe/'SleepProbe.java'
source.write_text('public class SleepProbe { public static void main(String[] a) throws Exception { System.out.println("started"); Thread.sleep(30000); } }',encoding='utf-8')
subprocess.run([javac,str(source)],check=True,capture_output=True,timeout=15)
parent_code='import subprocess,time; subprocess.Popen(%r); time.sleep(30)' % [java,'-cp',str(probe),'SleepProbe']
command=[sys.executable,'-c',parent_code]
timeout=supervise(command,here/'smoke_java_timeout',2,.1,1)
gap=supervise(command,here/'smoke_monitor_gap',5,.1,.4,test_stall=1)
observed=[p for s in timeout['samples'] for p in s['processes'] if p['name'].lower()=='java.exe']
clean=True
for p in observed:
    try: current=process_identity(p['pid'])
    except OSError: continue
    clean &= current['creation_filetime_100ns']!=p['creation_filetime_100ns']
epoch=here/'smoke_traced_epoch'; epoch.mkdir(exist_ok=False)
session=object.__new__(JavaSession); session.directory=probe; session.command=[java,'-cp',str(probe),'SleepProbe']
try: session._invoke_traced(epoch,.5)
except subprocess.TimeoutExpired: traced=True
else: traced=False
start=json.loads((epoch/'invocation_start.json').read_text()); end=json.loads((epoch/'invocation_process_end.json').read_text())
result=dict(timeout_state=timeout['state'],java_observed=bool(observed),java_identities=observed,
            killed_java_not_alive=clean,timeout_job_empty=not timeout['remaining_job_processes'],
            gap_state=gap['state'],gap_job_empty=not gap['remaining_job_processes'],
            adapter_timeout_preserved=traced,adapter_java_identity=start['identity'],adapter_end=end,
            benchmark_rollouts=0,vnsme_searches=0)
(here/'smoke_summary.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
assert (result['timeout_state']=='TIMEOUT' and result['java_observed'] and clean and result['timeout_job_empty']
        and result['gap_state']=='MONITORING_GAP' and result['gap_job_empty'] and traced and end['timed_out'])
print(json.dumps(result,indent=2))
