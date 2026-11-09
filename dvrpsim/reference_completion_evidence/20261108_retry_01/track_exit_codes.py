"""Observe Windows exit codes via handles, including forcibly timed-out Java."""
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import json
from pathlib import Path
import time

HERE = Path(__file__).resolve().parent
kernel = ctypes.WinDLL('kernel32', use_last_error=True)
kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel.OpenProcess.restype = wintypes.HANDLE
kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
kernel.WaitForSingleObject.restype = wintypes.DWORD
kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
kernel.GetExitCodeProcess.restype = wintypes.BOOL
kernel.CloseHandle.argtypes = [wintypes.HANDLE]
kernel.CloseHandle.restype = wintypes.BOOL
active = {}


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def last_sample(phase):
    path = HERE/f'{phase}_heartbeats.jsonl'
    if not path.exists():
        return {}
    with path.open('rb') as handle:
        handle.seek(max(0, path.stat().st_size-131072))
        lines = handle.read().splitlines()
    for raw in reversed(lines):
        try:
            sample = json.loads(raw)
        except ValueError:
            continue
        if isinstance(sample.get('processes'), list):
            return sample
    return {}


with (HERE/'observed_process_exits.jsonl').open('x', encoding='utf-8') as log:
    while True:
        state = json.loads((HERE/'supervisor_status.json').read_text())
        beat = json.loads((HERE/'heartbeat.json').read_text())
        sample = last_sample(beat['phase'])
        for process in sample.get('processes', []):
            pid = process['ProcessId']
            if pid in active or process['Name'].lower() not in ('java.exe', 'python.exe'):
                continue
            handle = kernel.OpenProcess(0x00101000, False, pid)
            if handle:
                active[pid] = (handle, dict(pid=pid, name=process['Name'],
                    phase=beat['phase'], first_observed_epoch=sample.get('last_epoch'),
                    opened_at=timestamp()))
        for pid, (handle, record) in list(active.items()):
            if kernel.WaitForSingleObject(handle, 0) != 0:
                continue
            code = wintypes.DWORD()
            if kernel.GetExitCodeProcess(handle, ctypes.byref(code)):
                record.update(exit_code_unsigned=code.value,
                              exit_code_signed=ctypes.c_int32(code.value).value)
            else:
                record['query_error'] = ctypes.get_last_error()
            record['exit_observed_at'] = timestamp()
            log.write(json.dumps(record)+'\n')
            log.flush()
            kernel.CloseHandle(handle)
            del active[pid]
        if state['status'] != 'RUNNING':
            break
        time.sleep(10)
    for handle, record in active.values():
        record.update(still_active_at_supervisor_end=True, observed_at=timestamp())
        log.write(json.dumps(record)+'\n')
        kernel.CloseHandle(handle)
