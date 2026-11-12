"""Read-only VNSME v3 recovery preflight; never opens sealed final-test CSVs."""

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


def block_sealed_open(event, args):
    if event != "open" or not args:
        return
    path = args[0]
    if isinstance(path, (str, bytes, Path)):
        try:
            instance = sealed_instance(Path(path.decode() if isinstance(path, bytes) else path))
        except (OSError, ValueError):
            return
        if instance is not None:
            sealed_attempts.append(str(path))
            raise PermissionError(f"sealed CSV access attempted: instance_{instance}")


sys.addaudithook(block_sealed_open)

from dpdp_vnsme_reference_v3 import load_reference, metadata, preflight_build, read, runtime_fingerprint

old = ROOT / "vnsme_runs/v3_references_3_6_20261109_recovery_r1/instance_5"
reference_dirs = {
    2: ROOT / "vnsme_runs/v3_instance2_acceptance_20261109_r1",
    3: ROOT / "vnsme_runs/v3_references_3_6_20261109_r1/instance_3",
    4: ROOT / "vnsme_runs/v3_references_3_6_20261109_recovery_r1/instance_4",
}
reference_summaries = {
    2: reference_dirs[2] / "reference_2/summary.json",
    3: ROOT / "vnsme_evidence/v3_references_3_6_20261109_r1/loader_check_instance_3/summary.json",
    4: ROOT / "vnsme_evidence/v3_references_3_6_20261109_recovery_r1/loader_check_instance_4/summary.json",
}
new5 = ROOT / "vnsme_runs/v3_instance5_recovery_20261110_r1"
new6 = ROOT / "vnsme_runs/v3_instance6_validation_20261110_r1"
combined = ROOT / "vnsme_runs/v3_reference_ready_2_6_20261110_r1"

manifests = {i: read(path / "protocol_manifest.json") for i, path in reference_dirs.items()}
old5_preflight = read(ROOT / "vnsme_evidence/v3_references_3_6_20261109_recovery_r1/preflight_instance5.json")
metas = {i: metadata(i) for i in (5, 6)}
java = preflight_build()
head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
fingerprints = {i: runtime_fingerprint(read(path / "run/manifest.json")) for i, path in reference_dirs.items()}
loaded = {i: load_reference(reference_summaries[i], [i])[0][i] for i in reference_dirs}

tasklist = subprocess.check_output(
    ["tasklist", "/FI", "IMAGENAME eq java.exe", "/FO", "CSV", "/NH"],
    text=True,
    errors="replace",
).strip()
java_processes = [row for row in csv.reader(io.StringIO(tasklist)) if row and row[0].lower() == "java.exe"]
free_bytes = shutil.disk_usage(ROOT).free
common = ("contract_version", "contract_protocol_sha256", "split_protocol_sha256", "source_manifest_sha256", "java_build_sha256")
same_common = all(manifests[2][key] == manifests[3][key] == manifests[4][key] == metas[5][key] == metas[6][key] for key in common)
old5_fields = ("role", "seed", "simulation", "data_sha256", "contract_version", "contract_protocol_sha256", "split_protocol_sha256", "source_manifest_sha256", "java_build_sha256")
checks = {
    "windows_job_object_available": os.name == "nt",
    "old_instance5_is_incomplete": old.is_dir() and not any((old / p).exists() for p in ("run/result.json", "record.json", "supervisor/supervision.json")),
    "old_instance5_unchanged_input_and_config": all(old5_preflight["instance5"][key] == metas[5][key] for key in old5_fields),
    "no_java_from_old_run": not java_processes,
    "fresh_output_dirs": not any(path.exists() for path in (new5, new6, combined)),
    "disk_free_over_1gb": free_bytes > 1_000_000_000,
    "role_and_size": metas[5]["role"] == "train" and metas[6]["role"] == "validation" and metas[5]["orders"] == metas[6]["orders"] == 50 and metas[5]["items"] == 107 and metas[6]["items"] == 86,
    "same_contract_split_source_and_java_build": same_common,
    "same_source_revision": head == manifests[2]["git_revision"] == manifests[3]["git_revision"] == manifests[4]["git_revision"],
    "source_fingerprint_matches_uncommitted_files": fingerprints[2] == fingerprints[3] == fingerprints[4],
    "same_seed_and_simulation": all(manifests[i]["seed"] == metas[5]["seed"] == metas[6]["seed"] == 0 and manifests[i]["simulation"] == metas[5]["simulation"] == metas[6]["simulation"] for i in reference_dirs),
    "same_java_executable_and_version": all(manifests[i]["environment"]["java_executable"] == java["java_executable"] and manifests[i]["environment"]["java_version"] == java["java_version"] for i in reference_dirs),
    "same_budgets_540_600_10800": all(manifests[i]["budgets"] == {"java_cooperative_seconds": 540, "epoch_seconds": 600, "rollout_seconds": 10800} for i in reference_dirs),
    "reference_2_3_4_loader_pass": loaded == {2: 95.74, 3: 97.44, 4: 100.92},
    "sealed_csv_open_attempts_zero": not sealed_attempts,
}
report = {
    "all_pass": all(checks.values()),
    "checks": checks,
    "git_head": head,
    "runtime_fingerprint": fingerprints[2],
    "java": java,
    "free_bytes": free_bytes,
    "metadata_5": metas[5],
    "metadata_6": metas[6],
    "accepted_loader_scores": loaded,
    "new_outputs": [str(new5), str(new6), str(combined)],
    "sealed_csv_open_attempts": sealed_attempts,
}
(HERE / "preflight.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps({"all_pass": report["all_pass"], "failed": [k for k, v in checks.items() if not v], "free_gb": round(free_bytes / 2**30, 2), "accepted_scores": loaded, "sealed_attempts": len(sealed_attempts)}))
if not report["all_pass"]:
    raise SystemExit(2)
