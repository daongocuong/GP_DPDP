"""Temporary idle-sleep request, released when the reference supervisor exits."""
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
kernel = ctypes.WinDLL('kernel32', use_last_error=True)
kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel.OpenProcess.restype = wintypes.HANDLE
kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
kernel.WaitForSingleObject.restype = wintypes.DWORD
kernel.CloseHandle.argtypes = [wintypes.HANDLE]
kernel.CloseHandle.restype = wintypes.BOOL
kernel.SetThreadExecutionState.argtypes = [wintypes.DWORD]
kernel.SetThreadExecutionState.restype = wintypes.DWORD

state = dict(supervisor_pid=int(sys.argv[1]), started_at=datetime.now(timezone.utc).isoformat(),
             api='SetThreadExecutionState', flags=['ES_CONTINUOUS', 'ES_SYSTEM_REQUIRED'],
             documentation='https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-setthreadexecutionstate')
handle = kernel.OpenProcess(0x00100000, False, state['supervisor_pid'])
try:
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    previous = kernel.SetThreadExecutionState(0x80000001)
    if not previous:
        raise ctypes.WinError(ctypes.get_last_error())
    state.update(active=True, previous_execution_state=previous)
    (HERE/'idle_sleep_request.json').write_text(json.dumps(state, indent=2), encoding='utf-8')
    while True:
        result = kernel.WaitForSingleObject(handle, 5000)
        if result == 0:
            break
        if result != 0x102:
            raise ctypes.WinError(ctypes.get_last_error())
except BaseException as exc:
    state['error'] = f'{type(exc).__name__}: {exc}'
finally:
    state.update(active=False, released_at=datetime.now(timezone.utc).isoformat(),
                 release_return_value=kernel.SetThreadExecutionState(0x80000000))
    if handle:
        kernel.CloseHandle(handle)
    (HERE/'idle_sleep_request.json').write_text(json.dumps(state, indent=2), encoding='utf-8')
