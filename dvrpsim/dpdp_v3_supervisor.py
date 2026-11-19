"""Windows job-object watchdog for bounded research processes, not a scorer.

All descendants enter the job before the suspended root starts. A watchdog
gap invalidates the run; it never grants extra runtime. No existing output is
overwritten. Job membership, rather than image name, defines ownership.
"""
import argparse
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import json
import math
import msvcrt
import os
from pathlib import Path
import subprocess
import time

K = ctypes.WinDLL('kernel32', use_last_error=True)
HANDLE = wintypes.HANDLE
DWORD = wintypes.DWORD
BOOL = wintypes.BOOL

class STARTUPINFO(ctypes.Structure):
    _fields_ = [('cb', DWORD), ('reserved', wintypes.LPWSTR), ('desktop', wintypes.LPWSTR),
                ('title', wintypes.LPWSTR), ('x', DWORD), ('y', DWORD), ('xsize', DWORD),
                ('ysize', DWORD), ('xcount', DWORD), ('ycount', DWORD), ('fill', DWORD),
                ('flags', DWORD), ('show', wintypes.WORD), ('reserved2size', wintypes.WORD),
                ('reserved2', ctypes.c_void_p), ('stdin', HANDLE), ('stdout', HANDLE), ('stderr', HANDLE)]

class PROCESS_INFORMATION(ctypes.Structure):
    _fields_ = [('process', HANDLE), ('thread', HANDLE), ('pid', DWORD), ('tid', DWORD)]

class BASIC_LIMIT(ctypes.Structure):
    _fields_ = [('per_process_time', ctypes.c_longlong), ('per_job_time', ctypes.c_longlong),
                ('flags', DWORD), ('minimum_working_set', ctypes.c_size_t),
                ('maximum_working_set', ctypes.c_size_t), ('active_process_limit', DWORD),
                ('affinity', ctypes.c_size_t), ('priority', DWORD), ('scheduling', DWORD)]

class IO_COUNTERS(ctypes.Structure):
    _fields_ = [(n, ctypes.c_ulonglong) for n in ('read_ops', 'write_ops', 'other_ops',
                'read_bytes', 'write_bytes', 'other_bytes')]

class EXTENDED_LIMIT(ctypes.Structure):
    _fields_ = [('basic', BASIC_LIMIT), ('io', IO_COUNTERS), ('process_memory', ctypes.c_size_t),
                ('job_memory', ctypes.c_size_t), ('peak_process', ctypes.c_size_t), ('peak_job', ctypes.c_size_t)]

class PROCESSENTRY32(ctypes.Structure):
    _fields_ = [('size', DWORD), ('usage', DWORD), ('pid', DWORD), ('heap', ctypes.c_size_t),
                ('module', DWORD), ('threads', DWORD), ('parent', DWORD), ('priority', ctypes.c_long),
                ('flags', DWORD), ('name', wintypes.WCHAR * 260)]

def api(name, restype, args):
    f = getattr(K, name); f.restype = restype; f.argtypes = args; return f

CreateJob = api('CreateJobObjectW', HANDLE, [ctypes.c_void_p, wintypes.LPCWSTR])
SetJob = api('SetInformationJobObject', BOOL, [HANDLE, ctypes.c_int, ctypes.c_void_p, DWORD])
QueryJob = api('QueryInformationJobObject', BOOL, [HANDLE, ctypes.c_int, ctypes.c_void_p,
                                                   DWORD, ctypes.POINTER(DWORD)])
Assign = api('AssignProcessToJobObject', BOOL, [HANDLE, HANDLE])
InJob = api('IsProcessInJob', BOOL, [HANDLE, HANDLE, ctypes.POINTER(BOOL)])
KillJob = api('TerminateJobObject', BOOL, [HANDLE, wintypes.UINT])
Close = api('CloseHandle', BOOL, [HANDLE])
Resume = api('ResumeThread', DWORD, [HANDLE])
Wait = api('WaitForSingleObject', DWORD, [HANDLE, DWORD])
ExitCode = api('GetExitCodeProcess', BOOL, [HANDLE, ctypes.POINTER(DWORD)])
Open = api('OpenProcess', HANDLE, [DWORD, BOOL, DWORD])
Terminate = api('TerminateProcess', BOOL, [HANDLE, wintypes.UINT])
GetTimes = api('GetProcessTimes', BOOL, [HANDLE] + [ctypes.POINTER(wintypes.FILETIME)]*4)
Snapshot = api('CreateToolhelp32Snapshot', HANDLE, [DWORD, DWORD])
First = api('Process32FirstW', BOOL, [HANDLE, ctypes.POINTER(PROCESSENTRY32)])
Next = api('Process32NextW', BOOL, [HANDLE, ctypes.POINTER(PROCESSENTRY32)])
CreateProcess = api('CreateProcessW', BOOL, [wintypes.LPCWSTR, wintypes.LPWSTR, ctypes.c_void_p,
    ctypes.c_void_p, BOOL, DWORD, ctypes.c_void_p, wintypes.LPCWSTR,
    ctypes.POINTER(STARTUPINFO), ctypes.POINTER(PROCESS_INFORMATION)])

def check(ok, operation):
    if not ok:
        raise ctypes.WinError(ctypes.get_last_error(), operation)


def peak_job_memory_bytes(job):
    """Peak committed memory for all processes in the supervised Windows job."""
    limits = EXTENDED_LIMIT()
    returned = DWORD()
    check(QueryJob(job, 9, ctypes.byref(limits), ctypes.sizeof(limits),
                   ctypes.byref(returned)), 'QueryInformationJobObject')
    return int(limits.peak_job)

def ft(value):
    return (value.dwHighDateTime << 32) | value.dwLowDateTime

def start_utc(value):
    return datetime.fromtimestamp(ft(value)/1e7-11644473600, timezone.utc).isoformat()

def now():
    return datetime.now(timezone.utc).isoformat()

def process_identity(pid):
    p = Open(0x1000, False, pid)
    check(p, 'OpenProcess')
    try:
        c, e, k, u = [wintypes.FILETIME() for _ in range(4)]
        check(GetTimes(p, *(ctypes.byref(x) for x in (c, e, k, u))), 'GetProcessTimes')
        return dict(pid=pid, creation_filetime_100ns=ft(c), started_utc=start_utc(c),
                    cpu_user_seconds=ft(u)/1e7, cpu_kernel_seconds=ft(k)/1e7, cpu_seconds=(ft(k)+ft(u))/1e7)
    finally:
        Close(p)

def processes(job):
    snap = Snapshot(2, 0)
    if snap == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    result = []
    try:
        entry = PROCESSENTRY32(); entry.size = ctypes.sizeof(entry)
        ok = First(snap, ctypes.byref(entry))
        while ok:
            p = Open(0x1000, False, entry.pid)
            if p:
                try:
                    inside = BOOL()
                    if InJob(p, job, ctypes.byref(inside)) and inside.value:
                        c, e, k, u = [wintypes.FILETIME() for _ in range(4)]
                        if GetTimes(p, *(ctypes.byref(x) for x in (c, e, k, u))):
                            result.append(dict(pid=entry.pid, parent_pid=entry.parent, name=entry.name,
                                creation_filetime_100ns=ft(c), started_utc=start_utc(c),
                                cpu_user_seconds=ft(u)/1e7, cpu_kernel_seconds=ft(k)/1e7,
                                cpu_seconds=(ft(k)+ft(u))/1e7))
                finally:
                    Close(p)
            ok = Next(snap, ctypes.byref(entry))
    finally:
        Close(snap)
    return result


class DecisionTraceMonitor:
    """Validate append-only START/END decision events and enforce one live deadline."""
    def __init__(self, path, timeout, partition=None, algorithm=None, timeout_overrides=None):
        self.path=Path(path); self.timeout=float(timeout); self.offset=0
        self.pending=None; self.completed=0; self.last_index=0
        self.partition=partition; self.algorithm=algorithm
        self.timeout_overrides={int(k):float(v) for k,v in (timeout_overrides or {}).items()}

    def timeout_for(self, decision_index):
        return self.timeout_overrides.get(decision_index,self.timeout)

    def poll(self, now):
        if not self.path.is_file():
            raise ValueError('decision trace missing')
        with self.path.open('rb') as f:
            f.seek(self.offset); data=f.read()
        complete=data.rfind(b'\n')+1
        if complete:
            self.offset+=complete
        for raw in data[:complete].splitlines():
            try: event=json.loads(raw.decode('utf-8'))
            except json.JSONDecodeError as exc: raise ValueError('malformed decision trace') from exc
            if event.get('schema')!='dpdp-smoke-decision-v1': raise ValueError('unknown decision trace schema')
            if self.partition is not None and event.get('partition') != self.partition:
                raise ValueError('decision trace partition mismatch')
            if self.algorithm is not None and event.get('algorithm') != self.algorithm:
                raise ValueError('decision trace algorithm mismatch')
            kind=event.get('event'); idx=event.get('decision_index')
            if kind=='START':
                if type(idx) is not int or self.pending is not None or idx!=self.last_index+1:
                    raise ValueError('duplicate/out-of-order START')
                sim=event.get('simulation_seconds')
                if sim is not None and (not isinstance(sim,(int,float)) or sim<0):
                    raise ValueError('invalid simulated time in START')
                self.pending=dict(index=idx,simulation_seconds=event.get('simulation_seconds'),received=now,
                                  timeout_seconds=self.timeout_for(idx),
                                  progress=dict(candidate_count=0,feasible_count=0,rejected_count=0,
                                                groups_total=0,groups_processed=0))
                self.last_index=idx
            elif kind=='PROGRESS':
                if self.pending is None or idx!=self.pending['index']:
                    raise ValueError('orphan/out-of-order PROGRESS')
                if event.get('simulation_seconds') != self.pending['simulation_seconds']:
                    raise ValueError('simulation time changed within decision progress')
                keys=('candidate_count','feasible_count','rejected_count','groups_total','groups_processed')
                current={key:event.get(key) for key in keys}
                if any(type(value) is not int or value<0 for value in current.values()):
                    raise ValueError('invalid workload counters in PROGRESS')
                if any(current[key]<self.pending['progress'][key] for key in keys):
                    raise ValueError('nonmonotonic workload counters in PROGRESS')
                elapsed=event.get('decision_elapsed_seconds')
                if not isinstance(elapsed,(int,float)) or not math.isfinite(elapsed) or elapsed<0:
                    raise ValueError('invalid elapsed time in PROGRESS')
                self.pending['progress']=current
            elif kind in ('END','ERROR'):
                if self.pending is None or idx!=self.pending['index']: raise ValueError('orphan/duplicate END')
                if kind=='END':
                    elapsed=event.get('decision_elapsed_seconds')
                    if not isinstance(elapsed,(int,float)) or elapsed<0 or event.get('status')!='completed':
                        raise ValueError('invalid END marker')
                    # If the END was written after the deadline (or only
                    # observed after it), never accept a late result.
                    limit=self.pending['timeout_seconds']
                    if elapsed >= limit or now-self.pending['received'] >= limit:
                        return dict(kind='DECISION_TIMEOUT',decision_index=self.pending['index'],
                            simulation_seconds=self.pending['simulation_seconds'],
                            decision_elapsed_seconds=max(elapsed,now-self.pending['received']),
                            elapsed_wall_seconds=max(elapsed,now-self.pending['received']),
                            completed_decisions=self.completed,timeout_type='decision_hard_timeout',
                            configured_decision_timeout_seconds=limit,
                            stop_reason='decision_hard_timeout',**self.pending['progress'])
                    self.completed+=1
                self.pending=None
            else: raise ValueError('unknown decision trace event')
        if self.pending is not None and now-self.pending['received']>=self.pending['timeout_seconds']:
            return dict(kind='DECISION_TIMEOUT',decision_index=self.pending['index'],
                        simulation_seconds=self.pending['simulation_seconds'],
                        decision_elapsed_seconds=now-self.pending['received'],
                        elapsed_wall_seconds=now-self.pending['received'],
                        completed_decisions=self.completed,timeout_type='decision_hard_timeout',
                        configured_decision_timeout_seconds=self.pending['timeout_seconds'],
                        stop_reason='decision_hard_timeout',**self.pending['progress'])
        return None

    def finish(self):
        """A worker may not exit with a partial JSON line or an open decision."""
        with self.path.open('rb') as f:
            f.seek(self.offset)
            tail=f.read()
        if tail:
            raise ValueError('truncated final decision trace line')
        if self.pending is not None:
            raise ValueError('worker exited with a decision missing END/ERROR')


def select_timeout_reason(stage_expired, decision_expired):
    """Stage deadline has deterministic priority when both deadlines expire together."""
    if stage_expired:
        return 'stage_wall_timeout'
    if decision_expired:
        return 'decision_hard_timeout'
    return None

def supervise(command, output, timeout, interval=1.0, gap_limit=5.0, test_stall=0, epoch_root=None,
              decision_trace=None, decision_timeout=None, partition=None, algorithm=None,
              stage_started_monotonic=None, decision_timeout_overrides=None):
    if os.name != 'nt':
        raise RuntimeError('Windows Job Objects required')
    if timeout <= 0 or interval <= 0 or gap_limit <= interval:
        raise ValueError('invalid watchdog timing')
    if (decision_trace is None) != (decision_timeout is None):
        raise ValueError('decision trace and timeout must be configured together')
    if decision_trace is not None:
        trace_path=Path(decision_trace)
        trace_path.parent.mkdir(parents=True,exist_ok=True)
        if not trace_path.exists():
            trace_path.open('x',encoding='utf-8').close()
        elif trace_path.stat().st_size:
            raise ValueError('decision trace must be empty for a fresh supervised stage')
        overrides=decision_timeout_overrides or {}
        if any(type(k) not in (int,str) or int(k)<1 or not isinstance(v,(int,float))
               or not math.isfinite(v) or not 0<v for k,v in overrides.items()):
            raise ValueError('invalid per-decision timeout override')
        monitor=DecisionTraceMonitor(trace_path,decision_timeout,partition,algorithm,overrides)
    else:
        monitor=None
    output = Path(output).resolve(); output.mkdir(parents=True, exist_ok=False)
    job = CreateJob(None, None); check(job, 'CreateJobObject')
    pi = PROCESS_INFORMATION(); created = False
    start = time.monotonic(); start_wall = time.time(); started_utc = now()
    stage_origin = start if stage_started_monotonic is None else stage_started_monotonic
    deadline = stage_origin + timeout
    remaining_at_supervisor_start=max(0.0,deadline-start)
    wall_deadline = start_wall + remaining_at_supervisor_start
    record = dict(command=command, started_utc=started_utc, timeout_seconds=timeout,
                  decision_timeout_seconds=decision_timeout,
                  decision_timeout_overrides={str(k):v for k,v in (decision_timeout_overrides or {}).items()},
                  stage_elapsed_before_supervisor_seconds=max(0.0,start-stage_origin),
                  remaining_seconds_at_supervisor_start=remaining_at_supervisor_start,
                  deadline_utc=datetime.fromtimestamp(time.time()+timeout, timezone.utc).isoformat(),
                  state='STARTING', valid_supervision=False, samples=[], gaps=[])
    try:
        limits = EXTENDED_LIMIT(); limits.basic.flags = 0x2000  # kill on final job handle close
        check(SetJob(job, 9, ctypes.byref(limits), ctypes.sizeof(limits)), 'SetInformationJobObject')
        with (output/'process.log').open('xb', buffering=0) as log:
            handle = msvcrt.get_osfhandle(log.fileno()); os.set_handle_inheritable(handle, True)
            startup = STARTUPINFO(); startup.cb = ctypes.sizeof(startup); startup.flags = 0x100
            startup.stdout = handle; startup.stderr = handle; startup.stdin = handle
            cmdline = ctypes.create_unicode_buffer(subprocess.list2cmdline([str(x) for x in command]))
            check(CreateProcess(None, cmdline, None, None, True, 0x4 | 0x08000000, None,
                                str(Path.cwd()), ctypes.byref(startup), ctypes.byref(pi)), 'CreateProcessW')
            created = True
            check(Assign(job, pi.process), 'AssignProcessToJobObject')
            if Resume(pi.thread) == 0xffffffff:
                raise ctypes.WinError(ctypes.get_last_error())
            record.update(state='RUNNING', root_pid=pi.pid)
            last = time.monotonic(); last_wall = time.time(); stalled = False
            with (output/'heartbeats.jsonl').open('x', encoding='utf-8') as heartbeat:
                while True:
                    tick = time.monotonic(); wall = time.time(); gap = tick-last; wall_gap = wall-last_wall
                    sample = dict(utc=now(), elapsed_seconds=tick-start, wall_elapsed_seconds=wall-start_wall,
                                  gap_seconds=gap, wall_gap_seconds=wall_gap, processes=processes(job))
                    heartbeat.write(json.dumps(sample)+'\n'); heartbeat.flush()
                    record['samples'].append(sample)
                    if gap > gap_limit or wall_gap > gap_limit or abs(wall_gap-gap) > gap_limit:
                        record['gaps'].append(dict(seconds=gap, wall_seconds=wall_gap, detected_utc=now()))
                        record['state'] = 'MONITORING_GAP'; break
                    marker_timeout=None
                    if monitor:
                        try:
                            marker_timeout=monitor.poll(tick)
                        except (OSError, ValueError) as exc:
                            trace_error=dict(schema='dpdp-smoke-decision-v1',event='TRACE_ERROR',algorithm=algorithm,
                                partition=partition,error=f'{type(exc).__name__}: {exc}',
                                decision_index=monitor.pending['index'] if monitor.pending else monitor.last_index+1,
                                simulation_seconds=monitor.pending['simulation_seconds'] if monitor.pending else None,
                                elapsed_wall_seconds=tick-start,completed_decisions=monitor.completed,
                                timeout_type=None,stop_reason='invalid_decision_trace')
                            append_trace_event(decision_trace,trace_error)
                            record.update(state='INVALID_TRACE',error=trace_error['error'],stop_event=trace_error); break
                    stage_expired=tick >= deadline or wall >= wall_deadline
                    decision_expired=marker_timeout is not None
                    timeout_reason=select_timeout_reason(stage_expired,decision_expired)
                    # Stage deadline wins ties with a decision deadline.
                    if timeout_reason == 'stage_wall_timeout':
                        latest_progress=(monitor.pending['progress'] if monitor and monitor.pending else
                            dict(candidate_count=None,feasible_count=None,rejected_count=None,
                                 groups_total=None,groups_processed=None))
                        timeout_event=dict(kind='STAGE_TIMEOUT',decision_index=monitor.pending['index'] if monitor and monitor.pending else None,
                            simulation_seconds=monitor.pending['simulation_seconds'] if monitor and monitor.pending else None,
                            elapsed_wall_seconds=tick-start,
                            decision_elapsed_seconds=tick-monitor.pending['received'] if monitor and monitor.pending else None,
                            completed_decisions=monitor.completed if monitor else 0,
                            timeout_type='stage_wall_timeout',stop_reason='stage_wall_timeout',**latest_progress)
                        if decision_trace is not None:
                            append_decision_timeout(decision_trace,timeout_event,partition,algorithm)
                        record.update(state='TIMEOUT',stop_event=timeout_event,detection_lag_seconds=max(tick-deadline,wall-wall_deadline)); break
                    if marker_timeout:
                        append_decision_timeout(decision_trace,marker_timeout,partition,algorithm)
                        record.update(state='DECISION_TIMEOUT',stop_event=marker_timeout); break
                    if epoch_root:
                        for marker in Path(epoch_root).glob('*/invocation_start.json'):
                            if (marker.parent/'invocation_process_end.json').exists():
                                continue
                            try:
                                epoch = json.loads(marker.read_text(encoding='utf-8'))
                            except (OSError, json.JSONDecodeError):
                                continue  # writer may not have finished the start marker
                            if tick >= epoch['deadline_monotonic'] or wall >= epoch.get('deadline_wall_epoch', float('inf')):
                                record.update(state='EPOCH_TIMEOUT', epoch=marker.parent.name,
                                    java_identity=epoch['identity'], detection_lag_seconds=max(0, tick-epoch['deadline_monotonic'],
                                        wall-epoch.get('deadline_wall_epoch', float('inf'))))
                                break
                        if record['state'] == 'EPOCH_TIMEOUT': break
                    if Wait(pi.process, 0) == 0:
                        code = DWORD(); check(ExitCode(pi.process, ctypes.byref(code)), 'GetExitCodeProcess')
                        try:
                            if monitor: monitor.finish()
                        except (OSError, ValueError) as exc:
                            trace_error=dict(schema='dpdp-smoke-decision-v1',event='TRACE_ERROR',algorithm=algorithm,
                                partition=partition,error=f'{type(exc).__name__}: {exc}',
                                decision_index=monitor.pending['index'] if monitor.pending else monitor.last_index+1,
                                simulation_seconds=monitor.pending['simulation_seconds'] if monitor.pending else None,
                                elapsed_wall_seconds=tick-start,completed_decisions=monitor.completed,
                                timeout_type=None,stop_reason='incomplete_decision_trace')
                            append_trace_event(decision_trace,trace_error)
                            record.update(state='INVALID_TRACE',error=trace_error['error'],stop_event=trace_error)
                        else:
                            record.update(state='EXITED', exit_code=code.value, valid_supervision=True)
                        break
                    last = tick; last_wall = wall
                    if test_stall and not stalled:
                        stalled = True; time.sleep(test_stall)
                    else:
                        time.sleep(min(interval, max(0, deadline-time.monotonic())))
            record['peak_job_memory_bytes'] = peak_job_memory_bytes(job)
            # Kill any surviving descendants on every exit, including a successful root.
            check(KillJob(job, 1), 'TerminateJobObject')
            Wait(pi.process, 5000)
            cleanup_deadline = time.monotonic()+5
            record['remaining_job_processes'] = processes(job)
            while record['remaining_job_processes'] and time.monotonic() < cleanup_deadline:
                time.sleep(0.05)
                record['remaining_job_processes'] = processes(job)
            if record['remaining_job_processes']:
                record['valid_supervision'] = False
    except BaseException as exc:
        record.update(state='SUPERVISOR_ERROR', error=f'{type(exc).__name__}: {exc}', valid_supervision=False)
        if created:
            KillJob(job, 1)
            # Assignment can fail before the process joined the job.
            Terminate(pi.process, 1)
            Wait(pi.process, 5000)
        raise
    finally:
        record.update(ended_utc=now(), elapsed_seconds=time.monotonic()-start)
        (output/'supervision.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
        if created:
            Close(pi.thread); Close(pi.process)
        Close(job)
    return record


def append_trace_event(path,row):
    with Path(path).open('a',encoding='utf-8') as out:
        out.write(json.dumps(row,sort_keys=True)+'\n');out.flush();os.fsync(out.fileno())


def append_decision_timeout(path,event,partition,algorithm):
    row=dict(schema='dpdp-smoke-decision-v1',algorithm=algorithm,partition=partition,**event)
    row['event']='TIMEOUT'
    append_trace_event(path,row)

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', required=True); p.add_argument('--timeout-seconds', required=True, type=float)
    p.add_argument('--interval', type=float, default=1); p.add_argument('--gap-limit', type=float, default=5)
    p.add_argument('--epoch-root', help='directory containing per-epoch invocation markers')
    p.add_argument('command', nargs=argparse.REMAINDER)
    a = p.parse_args(); command = a.command[1:] if a.command[:1] == ['--'] else a.command
    if not command: p.error('command is required')
    result = supervise(command, a.output, a.timeout_seconds, a.interval, a.gap_limit, epoch_root=a.epoch_root)
    raise SystemExit(0 if result['valid_supervision'] and result.get('exit_code') == 0 else 1)
