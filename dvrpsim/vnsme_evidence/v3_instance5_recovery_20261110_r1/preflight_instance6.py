"""Read-only validation-instance preflight after accepted instance 5."""

import csv
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from dpdp_sealed import sealed_instance

sealed_attempts = []


def deny(event, args):
    if event == "open" and args and isinstance(args[0], (str, bytes, Path)):
        path = args[0].decode() if isinstance(args[0], bytes) else args[0]
        instance = sealed_instance(path)
        if instance is not None:
            sealed_attempts.append(str(path))
            raise PermissionError(f"sealed final-test instance_{instance}")


sys.addaudithook(deny)

from dpdp_vnsme_reference_v3 import load_reference, metadata, preflight_build, read, runtime_fingerprint

run5 = ROOT / "vnsme_runs/v3_instance5_recovery_20261110_r1"
out6 = ROOT / "vnsme_runs/v3_instance6_validation_20261110_r1"
combined = ROOT / "vnsme_runs/v3_reference_ready_2_6_20261110_r1"
manifest5 = read(run5 / "protocol_manifest.json")
result5 = read(run5 / "run/result.json")
record5 = read(run5 / "record.json")
supervision5 = read(run5 / "supervisor/supervision.json")
meta6 = metadata(6)
java = preflight_build()
fingerprint5 = runtime_fingerprint(read(run5 / "run/manifest.json"))
scores5, _ = load_reference(HERE / "loader_check_instance5/summary.json", [5])
probe = read(HERE / "detach_probe_result.json")
head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
tasklist = subprocess.check_output(
    ["tasklist", "/FI", "IMAGENAME eq java.exe", "/FO", "CSV", "/NH"],
    text=True, errors="replace",
)
java_processes = [row for row in csv.reader(io.StringIO(tasklist)) if row and row[0].lower() == "java.exe"]
free = shutil.disk_usage(ROOT).free
same_keys = ("contract_version", "contract_protocol_sha256", "split_protocol_sha256", "source_manifest_sha256", "java_build_sha256")
checks = {
    "windows_job_object": os.name == "nt",
    "independent_supervisor_probe_pass": probe["state"] == "EXITED" and probe["valid_supervision"] and probe["exit_code"] == 0 and not probe["gaps"] and not probe["remaining_job_processes"],
    "instance5_loader_accepted": scores5[5] == float(record5["J"]) and record5["valid"] and record5["independent_audit"]["status"] == "PASS",
    "instance5_full_delivery": result5["valid"] and result5["contract_complete"] and result5["completed_original_orders"] == 50 and result5["completed_items"] == 107,
    "instance5_valid_supervision": supervision5["state"] == "EXITED" and supervision5["valid_supervision"] and supervision5["exit_code"] == 0 and not supervision5["gaps"] and not supervision5["remaining_job_processes"],
    "instance6_validation_and_size": meta6["role"] == "validation" and meta6["orders"] == 50 and meta6["items"] == 86,
    "same_contract_split_source_build": all(manifest5[k] == meta6[k] for k in same_keys),
    "same_seed_simulation": manifest5["seed"] == meta6["seed"] == 0 and manifest5["simulation"] == meta6["simulation"],
    "same_source_revision": manifest5["git_revision"] == head,
    "same_java_executable_version": manifest5["environment"]["java_executable"] == java["java_executable"] and manifest5["environment"]["java_version"] == java["java_version"],
    "same_budgets": manifest5["budgets"] == {"java_cooperative_seconds": 540, "epoch_seconds": 600, "rollout_seconds": 10800},
    "source_fingerprint_matches_uncommitted_files": bool(fingerprint5),
    "no_java_process_remaining": not java_processes,
    "fresh_instance6_and_combined_outputs": not out6.exists() and not combined.exists(),
    "disk_free_over_1gb": free > 1_000_000_000,
    "sealed_csv_open_attempts_zero": not sealed_attempts,
}
report = {
    "all_pass": all(checks.values()),
    "checks": checks,
    "metadata_6": meta6,
    "java": java,
    "git_head": head,
    "source_fingerprint": fingerprint5,
    "instance5_J": scores5[5],
    "free_bytes": free,
    "instance6_output": str(out6),
    "combined_output": str(combined),
    "sealed_csv_open_attempts": sealed_attempts,
}
(HERE / "preflight_instance6.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps({"all_pass": report["all_pass"], "failed": [k for k, v in checks.items() if not v], "instance6_items": meta6["items"], "free_gb": round(free / 2**30, 2), "sealed_attempts": len(sealed_attempts)}))
if not report["all_pass"]:
    raise SystemExit(2)
