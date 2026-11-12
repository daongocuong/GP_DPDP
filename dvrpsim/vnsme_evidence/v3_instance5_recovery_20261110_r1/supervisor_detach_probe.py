"""Probe whether a hidden launcher survives its interactive PowerShell parent."""

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from dpdp_v3_supervisor import supervise

child_code = (
    "import subprocess,sys; "
    "p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(18)']); "
    "p.wait(); sys.exit(p.returncode)"
)
result = supervise(
    [sys.executable, "-c", child_code],
    HERE / "detach_probe_supervisor",
    timeout=45,
    interval=1,
    gap_limit=5,
)
payload = {
    "state": result["state"],
    "valid_supervision": result["valid_supervision"],
    "exit_code": result.get("exit_code"),
    "gaps": result["gaps"],
    "remaining_job_processes": result["remaining_job_processes"],
    "elapsed_seconds": result["elapsed_seconds"],
    "max_processes_seen": max(len(x["processes"]) for x in result["samples"]),
    "max_heartbeat_gap_seconds": max(x["gap_seconds"] for x in result["samples"]),
}
(HERE / "detach_probe_result.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
if not (payload["state"] == "EXITED" and payload["valid_supervision"] and payload["exit_code"] == 0
        and not payload["gaps"] and not payload["remaining_job_processes"] and payload["max_processes_seen"] >= 3):
    raise SystemExit(2)
