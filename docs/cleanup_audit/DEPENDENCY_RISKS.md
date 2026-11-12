# Dependency graph và rủi ro khi cleanup

Audit 2026-11-10. Phân tích tĩnh source/literal references và selected manifests, không import project hoặc chạy workflow. Corpus744 files (~10.76MB) loại venv, Git internals, sealed contents, dataset contents và phần lớn run/cache bodies. Regex import inventory có thể thiếu dynamic/generated imports, có thể đếm imports trong branch không chạy; explicit code/manifest references được phân biệt với text mention. Không có kết luận runtime-unused tuyệt đối từ zero matches.

## Active execution dependencies

~~~text
run_dpdp_insertion.py
  -> sys.path + examples/case_studies/dpdp/{dpdp_main,problemdata,routing}.py
  -> src/dvrpsim/ (SimPy environment/model/elements/resources)
  -> dpdp_dataset -> dpdp_sealed
  -> dpdp_insertion -> dpdp_schedule + dpdp_feasibility
  -> GP ranker: dpdp_gp -> insertion FEATURE_UNITS
  -> VNSME: src/baselines/vnsme -> JavaSession/private exchange
          -> third_party/vnsme/{build,lib} + build_manifest.json
          -> common factory/route CSV + original Java classpath
  -> dpdp_contract -> feasibility
  -> dpdp_v3_trace + independent audit + verify_dpdp_score

fitness_v3 (offline, không trainer)
  -> dpdp_vnsme_reference_v3
     -> dpdp_gp_fitness.digest (module v2!)
     -> dpdp_vnsme_reference.SIMULATION (module v2!)
     -> contract/dataset/scorer/build hash/replay/supervision

train_dpdp_gp_multinstance.py (V2)
  -> dpdp_gp_fitness.RolloutEvaluator
  -> dpdp_vnsme_reference.load_reference
  -> migration_runs/vnsme_reference_ready/summary.json
     -> absolute run_directory records 2/3/4/5/6
  -> split + source manifest + development CSV
  -> subprocess same exact nested .venv interpreter
~~~

Nguồn: imports/code của các module trên. Không xóa dpdp_gp_fitness.py hoặc dpdp_vnsme_reference.py vì tên v2: v3 import trực tiếp chúng cho utility/config. Nếu muốn tách helper chung, đó là refactor riêng có hash-compatibility strategy, không cleanup file.

### Root non-test local import inventory

| File | Local imports found (tĩnh) |
| --- | --- |
| `dvrpsim/build_vnsme.py` | Không local import thấy trong scan |
| `dvrpsim/compare_dpdp_baselines.py` | `dpdp_dataset`, `verify_dpdp_score` |
| `dvrpsim/dpdp_audit_fixtures.py` | `dpdp_main`, `dpdp_routing`, `dvrpsim`, `dpdp_feasibility`, `dpdp_schedule` |
| `dvrpsim/dpdp_contract.py` | `dpdp_feasibility` |
| `dvrpsim/dpdp_dataset.py` | `dpdp_sealed`, `dpdp_problemdata` |
| `dvrpsim/dpdp_feasibility.py` | Không local import thấy trong scan |
| `dvrpsim/dpdp_gp.py` | `dpdp_insertion` |
| `dvrpsim/dpdp_gp_fitness.py` | `dpdp_gp`, `verify_dpdp_score`, `dpdp_dataset` |
| `dvrpsim/dpdp_gp_fitness_v3.py` | `dpdp_vnsme_reference_v3` |
| `dvrpsim/dpdp_insertion.py` | `dvrpsim`, `dpdp_feasibility`, `dpdp_schedule` |
| `dvrpsim/dpdp_schedule.py` | Không local import thấy trong scan |
| `dvrpsim/dpdp_sealed.py` | Không local import thấy trong scan |
| `dvrpsim/dpdp_v3_independent_audit.py` | `dpdp_dataset`, `dpdp_v3_trace` |
| `dvrpsim/dpdp_v3_supervisor.py` | Không local import thấy trong scan |
| `dvrpsim/dpdp_v3_trace.py` | Không local import thấy trong scan |
| `dvrpsim/dpdp_vnsme_reference.py` | `dpdp_dataset`, `dpdp_gp_fitness`, `verify_dpdp_score`, `dpdp_contract`, `train_dpdp_gp_multinstance` |
| `dvrpsim/dpdp_vnsme_reference_v3.py` | `dpdp_contract`, `dpdp_dataset`, `dpdp_gp_fitness`, `dpdp_vnsme_reference`, `verify_dpdp_score`, `build_vnsme`, `dpdp_v3_independent_audit`, `dpdp_v3_supervisor` |
| `dvrpsim/lock_dpdp_protocol.py` | `dpdp_dataset`, `prepare_dpdp_data` |
| `dvrpsim/measure_dpdp_data.py` | `dpdp_dataset`, `lock_dpdp_protocol`, `prepare_dpdp_data` |
| `dvrpsim/prepare_dpdp_data.py` | `dpdp_dataset`, `dpdp_sealed` |
| `dvrpsim/run_dpdp_insertion.py` | `dpdp_main`, `dpdp_problemdata`, `dpdp_routing`, `dvrpsim.utils.logging`, `dpdp_feasibility`, `dpdp_insertion`, `verify_dpdp_score`, `dpdp_dataset`, `dpdp_contract`, `dpdp_v3_trace`, `dpdp_gp`, `baselines.vnsme` |
| `dvrpsim/run_vnsme_huawei.py` | `baselines.vnsme`, `build_vnsme` |
| `dvrpsim/train_dpdp_gp.py` | `dpdp_gp`, `dpdp_gp_fitness` |
| `dvrpsim/train_dpdp_gp_multinstance.py` | `dpdp_gp`, `dpdp_gp_fitness`, `dpdp_dataset`, `prepare_dpdp_data`, `dpdp_vnsme_reference` |
| `dvrpsim/verify_dpdp_log.py` | Không local import thấy trong scan |
| `dvrpsim/verify_dpdp_score.py` | `dpdp_sealed` |

Không import không có nghĩa unused: build/supervisor/CLI utility có thể chỉ dùng standard library và được subprocess gọi. Module dpdp_main/problemdata/routing resolve qua runtime sys.path vào case study, không nằm root Python directory.

## CLI surface

Root dvrpsim có44 Python files,26 non-test/18 test;14 non-test __main__ entrypoints:

- `dvrpsim/build_vnsme.py`
- `dvrpsim/compare_dpdp_baselines.py`
- `dvrpsim/dpdp_audit_fixtures.py`
- `dvrpsim/dpdp_v3_supervisor.py`
- `dvrpsim/dpdp_vnsme_reference.py`
- `dvrpsim/dpdp_vnsme_reference_v3.py`
- `dvrpsim/lock_dpdp_protocol.py`
- `dvrpsim/measure_dpdp_data.py`
- `dvrpsim/prepare_dpdp_data.py`
- `dvrpsim/run_dpdp_insertion.py`
- `dvrpsim/run_vnsme_huawei.py`
- `dvrpsim/train_dpdp_gp.py`
- `dvrpsim/train_dpdp_gp_multinstance.py`
- `dvrpsim/verify_dpdp_score.py`

Phân nhóm để giảm cognitive load, không rename/delete:

- V3 hiện hành: run_dpdp_insertion.py, dpdp_vnsme_reference_v3.py (preflight/run/assemble), dpdp_v3_supervisor.py, verify_dpdp_score.py.
- Dataset/build maintenance: prepare_dpdp_data.py, lock_dpdp_protocol.py, measure_dpdp_data.py, build_vnsme.py. Một số commands tải/ghi data hoặc simulation, không tự chạy để cleanup.
- V2/legacy/research tools: train_dpdp_gp_multinstance.py (v2), train_dpdp_gp.py (raw-J pilot), dpdp_vnsme_reference.py (v2 nhưng helpers active), compare_dpdp_baselines.py, run_vnsme_huawei.py; dpdp_audit_fixtures.py phục vụ fixture/tests.
- Tests/examples/evidence scripts còn __main__ riêng, đã inventory nhưng không coi là14 user-facing root tools.

Chưa có training CLI v3 certified. Draft v3 enabled=false; không tận dụng cleanup để train/freeze reference bằng cách đổi version label.

## Filesystem family references

Các count là số corpus files có target string sau normalize separators; generic variable name và source-hash exclusion string có thể tạo match, không phải mọi match đều là filesystem dependency.

| Target | Matching corpus files | Representative source mentions | Implication |
| --- | --- | --- | --- |
| `gp_runs` | 57 | `dvrpsim/compare_dpdp_baselines.py`<br>`dvrpsim/dpdp_gp_fitness.py`<br>`dvrpsim/dpdp_gp_fitness_v3.py`<br>`dvrpsim/measure_dpdp_data.py`<br>`dvrpsim/test_dpdp_insertion.py` | REVIEW reference type; không delete theo import count |
| `vnsme_runs` | 44 | `dvrpsim/dpdp_gp_fitness.py`<br>`dvrpsim/run_dpdp_insertion.py`<br>`dvrpsim/test_dpdp_vnsme_scale100.py`<br>`dvrpsim/vnsme_evidence/v3_independent_audit_20261109_r1/finalize.py`<br>`dvrpsim/vnsme_evidence/v3_independent_audit_20261109_r1/verify_instance2.py` | REVIEW reference type; không delete theo import count |
| `gp_evidence` | 20 | `dvrpsim/test_dpdp_gp.py` | REVIEW reference type; không delete theo import count |
| `vnsme_evidence` | 72 | `dvrpsim/test_dpdp_v3_independent_audit.py`<br>`dvrpsim/test_dpdp_v3_reference.py`<br>`dvrpsim/test_dpdp_vnsme_scale100.py`<br>`dvrpsim/vnsme_evidence/v3_instance5_recovery_20261110_r1/preflight.py`<br>`dvrpsim/vnsme_evidence/v3_reference_supervision_20261109_r1/preservation.py` | REVIEW reference type; không delete theo import count |
| `migration_runs` | 46 | `dvrpsim/dpdp_gp_fitness.py`<br>`dvrpsim/dpdp_vnsme_reference.py`<br>`dvrpsim/test_dpdp_vnsme_scale100.py`<br>`dvrpsim/reference_completion_evidence/20261108_retry_01/make_report.py`<br>`dvrpsim/reference_completion_evidence/20261108_retry_01/preflight.py` | REVIEW reference type; không delete theo import count |
| `baseline_runs` | 23 | `dvrpsim/dpdp_gp_fitness.py` | REVIEW reference type; không delete theo import count |
| `dataset_runs` | 11 | Không source mention; docs/JSON vẫn có | REVIEW reference type; không delete theo import count |
| `protocols` | 49 | `dvrpsim/compare_dpdp_baselines.py`<br>`dvrpsim/dpdp_contract.py`<br>`dvrpsim/dpdp_vnsme_reference_v3.py`<br>`dvrpsim/test_dpdp_dataset.py`<br>`dvrpsim/test_dpdp_vnsme_scale100.py` | REVIEW reference type; không delete theo import count |
| `third_party/vnsme` | 90 | `dvrpsim/build_vnsme.py`<br>`dvrpsim/dpdp_vnsme_reference.py`<br>`dvrpsim/dpdp_vnsme_reference_v3.py`<br>`dvrpsim/test_dpdp_vnsme_scale100.py`<br>`dvrpsim/reference_completion_evidence/20261108_retry_01/preflight.py` | REVIEW reference type; không delete theo import count |
| `docs/ai_handover` | 3 | Không source mention; docs/JSON vẫn có | REVIEW reference type; không delete theo import count |


## Manifest/path/hash closure cần bảo vệ

### V3 accepted collections

Record contains absolute run_directory/supervision_directory, per-artifact SHA maps, protocol manifest hash, data/source/build/split/contract identity. Seven collections được giữ toàn bộ, không chỉ các file trong map. audit_vnsme_run/load_reference đọc lại inputs/current source/build, ledger/result/trace/Java markers/supervisor rồi so record. Di chuyển collection thay path equality/current-record representation; rename source file làm runtime fingerprint lookup fail dù contents không đổi. Recompression rồi xóa original làm loader không thấy file; nén có sidecar path manifest cũng chưa được loader hỗ trợ.

Critical artifacts: manifest.json/result.json/record.json/protocol_manifest.json, commitments.json, decisions.json, decision_trace.jsonl với physical/decision events, simulation.log, vnsme/session.json, per-epoch input/output/process markers/live stdout/stderr, supervisor supervision.json/heartbeats.jsonl/process.log. Giữ private solution snapshots phục vụ forensic/replay, không promote private plan để thay publication.

### V2 reference closure (không được blanket archive)

Default summary `dvrpsim/migration_runs/vnsme_reference_ready/summary.json` được dpdp_vnsme_reference.DEFAULT_SUMMARY, trainer và official protocol dùng. Nó trỏ:

- `dvrpsim/migration_runs/vnsme_reference/instance_2`
- `dvrpsim/migration_runs/vnsme_reference/instance_3`
- `dvrpsim/migration_runs/vnsme_reference/instance_4`
- `dvrpsim/migration_runs/reference_retry_20261108_01/instance_5`
- `dvrpsim/migration_runs/reference_retry_20261108_01/instance_6`

Năm directories **164.812 MiB** còn là denominator provenance của completed GP v2. Source helper vẫn active cho v3. Archive/đổi tên migration_runs toàn bộ sẽ phá historical load/reproduction và current v2 defaults. Không coi reference_retry là failed throwaway vì tên retry: instance5/6 bên trong đang được summary chấp nhận.

### Source-hash dependencies ngoài import graph

`dvrpsim/dpdp_gp_fitness.py:source_hashes` quét ROOT.rglob('*.py'), exclude .git/.venv/__pycache__/baseline_runs/gp_runs/vnsme_runs/migration_runs/third_party, nhưng **không exclude vnsme_evidence/reference_completion_evidence/dataset_runs**. Move/delete Python scripts dưới evidence có thể thay context cache hoặc full provenance snapshot dù không import chúng. Runner manifest cũng ghi source fingerprints rộng. V3 runtime_fingerprint kiểm subset core/case-study/simulator, không được suy diễn mọi full source maps trong history đều portable sau move.

### Build và classpath

build_vnsme.py:build lấy original sources + lib, ghi build classes và **ghi đè build_manifest.json** chứa command/compiler/runtime/source/library/class hashes. Current reference records pin manifest hash. Xóa build rồi rebuild với compiler/path/version khác có thể fail byte identity và certificate. Class .class trong lib là supplied dependency, chưa có rebuild-from-source recipe. Chỉ18 project build outputs ~0.143MiB nên xóa chúng tiết kiệm rất ít nhưng rủi ro lớn.

### Environment path và external consumers

run_dpdp_insertion.py/trainers/prepare_dpdp_data/measure_dpdp_data enforce exact dvrpsim/.venv/Scripts/python.exe. Cache context chứa sys.executable/Python/packages. Root .venv không equivalent và không thấy core workflow dùng trong bounded corpus (chỉ handover nhắc LA/.venv), nhưng chưa kiểm IDE/user shortcuts/processes ngoài repo. Dỡ root env chỉ sau approval + metadata archive/recreate check và xác nhận không job dùng. Không dỡ nested env chỉ để giữ một interpreter.

## Logs, cache và compatibility links

- JavaSession writer/error text trỏ stderr.txt, traced mode tạo java_stderr_live.txt; test_dpdp_vnsme.py, test_dpdp_vnsme_timeout.py và performance/analyze_saved.py tham chiếu filename. Không nằm artifact hash map chưa đủ chứng minh không có consumers.
- GP cache có run_directory/log_sha256/normalized-reference pins; xóa cache có thể buộc rerun đắt và invalidate provenance. Saving chỉ1.81MiB không đáng so với risk; giữ cùng study.
- GP selected_tree training metadata và model files chứa source hash maps/tree/numeric schema; thay code caps/features làm load/model comparability đổi. Không dọn tree snapshots theo cùng expression.
- dvrpsim/DPDP_SCORING_AUDIT.md là compatibility redirect237B, không duplicate report. mkdocs.yml và .github workflow phụ thuộc docs paths; giữ LICENSE/gitignore/CI configs.
- dvrpsim/examples/case_studies/rmdp/data/180_2.txt32,035,416B thực sự được rmdp_main.py tham chiếu, dù không thuộc GP. Đây là optional upstream example archival candidate, không temp/unused.

## Trạng thái unused có thể kết luận

**Không tìm thấy pipeline-active usage trong bounded scan** cho dataset_runs như runtime input, root .venv như core CLI interpreter, non-DPDP examples như GP runtime, hay nhiều raw-J/Greedy pilot runs. Tuy vậy chúng có docs/manifest/historical roles. Chỉ đánh dấu C ARCHIVE_CANDIDATE/F REVIEW, không DELETE. Giữ code compatibility modules kể cả CLI legacy, chưa refactor.

Không thể chứng minh hoàn chỉnh absence of references: không scan mọi ignored JSON/cache body, external tools/IDE/OS tasks, dynamic user commands hoặc closed-over snapshots ngoài repo. Mọi relocation cần explicit dependency closure và restore test ở phase0/3.

## Đơn giản hóa kiến trúc đáng làm ở nhiệm vụ riêng

1. **Đơn giản hóa navigation trước:** một current workflow index phân biệt v3/v2/historical, active path catalog/read-only labels; không đổi file locations hoặc semantics.
2. **V3 source chỉ ~ít trăm KB:** không phải nguyên nhân storage. Giữ separation giữa feasibility, forecast, tree ranker, commitment và independent replay; merge checker với auditor làm mất oracle independence.
3. **Helper dependency coupling:** digest/SIMULATION hiện được import từ v2 modules, evaluator/trainer/runner nhiều nguồn defaults. Refactor helper/config chung sau khi có baseline/protocol và regression strategy; không gọi xóa file v2 là cleanup.
4. **Future output logging:** loại bản capture stream thứ hai/lưu bounded diagnostic hoặc compression có format/audit contract mới cho run tương lai; không chỉnh record/old logs và không đổi Java search objective.
5. **Future portable manifests:** tách immutable payload identity với location resolution để loader có thể đọc path mapping; giữ record cũ nguyên và kiểm original byte identity. Đây là design work, chưa có migration implementation.
