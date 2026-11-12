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

def supervise(command, output, timeout, interval=1.0, gap_limit=5.0, test_stall=0, epoch_root=None):
    if os.name != 'nt':
        raise RuntimeError('Windows Job Objects required')
    if timeout <= 0 or interval <= 0 or gap_limit <= interval:
        raise ValueError('invalid watchdog timing')
    output = Path(output).resolve(); output.mkdir(parents=True, exist_ok=False)
    job = CreateJob(None, None); check(job, 'CreateJobObject')
    pi = PROCESS_INFORMATION(); created = False
    start = time.monotonic(); start_wall = time.time(); started_utc = now(); deadline = start + timeout
    wall_deadline = start_wall + timeout
    record = dict(command=command, started_utc=started_utc, timeout_seconds=timeout,
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
                    if tick >= deadline or wall >= wall_deadline:
                        record.update(state='TIMEOUT', detection_lag_seconds=max(tick-deadline,wall-wall_deadline)); break
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
                        record.update(state='EXITED', exit_code=code.value, valid_supervision=True); break
                    last = tick; last_wall = wall
                    if test_stall and not stalled:
                        stalled = True; time.sleep(test_stall)
                    else:
                        time.sleep(min(interval, max(0, deadline-time.monotonic())))
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
