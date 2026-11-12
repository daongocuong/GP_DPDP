"""Read-only status sampler for detached VNSME v3 reference runs."""

import csv
from collections import deque
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
instance = int(sys.argv[1])
if instance not in (5, 6):
    raise SystemExit("only development instances 5 and 6 are allowed")
name = "v3_instance5_recovery_20261110_r1" if instance == 5 else "v3_instance6_validation_20261110_r1"
base = ROOT / "vnsme_runs" / name
launcher = json.loads((HERE / f"instance{instance}_launcher.json").read_text(encoding="utf-8"))
heartbeat_file = base / "supervisor/heartbeats.jsonl"
last = None
if heartbeat_file.exists():
    with heartbeat_file.open(encoding="utf-8") as handle:
        lines = deque(handle, maxlen=1)
    if lines:
        last = json.loads(lines[0])
epochs = sorted((base / "run/vnsme/epochs").glob("[0-9][0-9][0-9][0-9][0-9]"))
started = [p for p in epochs if (p / "invocation_start.json").exists()]
ended = [p for p in epochs if (p / "invocation_process_end.json").exists()]
supervision_path = base / "supervisor/supervision.json"
supervision = json.loads(supervision_path.read_text(encoding="utf-8")) if supervision_path.exists() else None
result_path = base / "run/result.json"
result = json.loads(result_path.read_text(encoding="utf-8")) if result_path.exists() else None
tasklist = subprocess.check_output(
    ["tasklist", "/FI", f"PID eq {launcher['launcher_pid']}", "/FO", "CSV", "/NH"],
    text=True, errors="replace",
)
launcher_alive = any(len(row) >= 2 and row[1].isdigit() and int(row[1]) == launcher["launcher_pid"]
                     for row in csv.reader(io.StringIO(tasklist)))
now = datetime.now(timezone.utc)
status = {
    "sampled_utc": now.isoformat(),
    "instance": instance,
    "launcher_pid": launcher["launcher_pid"],
    "launcher_alive": launcher_alive,
    "heartbeat_utc": last["utc"] if last else None,
    "heartbeat_age_seconds": (now - datetime.fromisoformat(last["utc"])).total_seconds() if last else None,
    "rollout_elapsed_seconds": last["elapsed_seconds"] if last else None,
    "heartbeat_gap_seconds": last["gap_seconds"] if last else None,
    "epochs_started": len(started),
    "epochs_ended": len(ended),
    "last_epoch": started[-1].name if started else None,
    "last_epoch_java_cpu_seconds": next((p["cpu_seconds"] for p in last["processes"] if p["name"] == "java.exe"), None) if last else None,
    "supervision_state": supervision["state"] if supervision else None,
    "supervision_valid": supervision["valid_supervision"] if supervision else None,
    "supervision_exit_code": supervision.get("exit_code") if supervision else None,
    "supervision_gaps": len(supervision["gaps"]) if supervision else None,
    "result_valid": result["valid"] if result else None,
    "record_exists": (base / "record.json").exists(),
}
with (HERE / f"instance{instance}_monitor.jsonl").open("a", encoding="utf-8") as handle:
    handle.write(json.dumps(status) + "\n")
print(json.dumps(status))
