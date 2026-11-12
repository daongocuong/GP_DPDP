# File classification và quyết định giữ/archive/review

Ngày 2026-11-10. Mọi action dưới đây là **đề xuất**, không cho phép cleanup. Size lấy snapshot trước bảy reports; parent groups overlap. Bảng A–F dùng primary classification mỗi file đúng một lần, còn các duplicate/build/history overlays là thông tin bổ sung. Không dùng classification để chọn artifact theo J.

## Primary classification toàn inventory

| Class | Ý nghĩa | Files | Bytes | Size |
| --- | --- | --- | --- | --- |
| A | ACTIVE_CORE (gồm Git và environment operational) | 4,351 | 116,631,916 | 111.229 MiB |
| B | CRITICAL_RESEARCH_EVIDENCE | 33,123 | 1,171,646,131 | 1117.369 MiB |
| C | HISTORICAL_ARCHIVE / upstream examples | 14,892 | 677,746,570 | 646.349 MiB |
| D | REGENERABLE bytecode | 2,863 | 60,717,013 | 57.904 MiB |
| E | DUPLICATE_OR_REDUNDANT đã chứng minh có thể bỏ | 0 | 0 | 0.000 MiB |
| F | UNKNOWN_REVIEW_REQUIRED | 553 | 7,293,732 | 6.956 MiB |

Tổng khớp 55,782 files / 2,034,035,362 bytes. E=0 ở primary tally: đã có exact byte duplicates nhưng **chưa có redundant copy nào được chứng minh an toàn bỏ khỏi dependency/provenance**. D chỉ gồm2863 pyc có source counterpart, không gồm GP fitness cache hay Java dependency classes.

Quy tắc phân loại theo thứ tự ưu tiên (áp dụng cho từng file):

1. Bảo vệ toàn seven v3 collections, completed GP v2 runs/audit, official incomplete GP và v2 denominator closure → B, kể cả cache/log trong các collection đó.
2. __pycache__/*.pyc còn lại → D; đã kiểm stat có source .py cho mọi pyc, không thực thi.
3. Git internal/main dvrpsim venv (trừ pyc) và core/config/tests/protocol/current handover → A; root venv non-cache → F.
4. Dataset, original vendor package, third_party, scoring_reference và các evidence families → B theo cách bảo thủ; future archive overlay không thay primary B.
5. Remaining experimental runs, upstream examples, historical docs/papers → C; configs/license/gitignore được KEEP A. Remaining unresolved old logs → F.
6. Không phân loại sealed contents dựa semantics; dữ liệu sealed là B theo path và protocol metadata.

## Nhóm filesystem đáng chú ý

| Path | Size | Class | Vai trò | Import / CLI | Manifest / evidence | Git | Regenerate? | Action và rủi ro |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `.git` | 25.588 MiB (26,830,647 B) | A | Git history/index/objects | Git commands | Root identity/HEAD; không phải project cache | Git internal | Không thay thế bằng checkout code | KEEP; không clean/prune trong nhiệm vụ này |
| `dvrpsim/src` | 0.329 MiB (344,741 B) | A | Simulator và Python–Java adapter | run_dpdp_insertion, model imports | Source fingerprints trong run/cache | tracked + ignored pyc | Source không regenerable | KEEP; move/refactor đổi imports/hashes |
| `dvrpsim/protocols` | 0.011 MiB (11,788 B) | A/B | Split, execution contract và fitness versions | contract/ref/trainer load trực tiếp | Sidecar hashes + run/experiment protocol pins | tracked + untracked | Không tái tạo chính xác quyết định bằng tên version | KEEP toàn bộ; 10 files rất nhỏ |
| `dvrpsim/datasets` | 2.718 MiB (2,849,657 B) | B | Pinned source data/manifest | dataset/loader/scorer | Input hashes trong records + split pin | tracked | Không dựa network để thay thế archive | KEEP; sealed chỉ metadata |
| `dvrpsim/third_party/vnsme/original` | 0.254 MiB (266,363 B) | B | Vendor source copy dùng build | build_vnsme.py | Source/build provenance | tracked | Nguồn gốc không thể giả lập bằng code tương tự | KEEP; hash bằng original package không nghĩa thừa |
| `dvrpsim/third_party/vnsme/lib` | 12.499 MiB (13,106,060 B) | B | Supplied third-party classes | Java classpath + javac -cp | library_sha256; không có source/library build đầy đủ | tracked | Chưa có quy trình rebuild các dependency này | KEEP; .class không mặc định regenerable |
| `dvrpsim/third_party/vnsme/build` | 0.143 MiB (149,967 B) | B / D kỹ thuật | 18 compiled outputs của source | Java classpath | class_sha256 trong build manifest; record pins build manifest | ignored | Có build.py; byte-identical restore chưa test trong cleanup | KEEP; không xóa dù rebuild được về chức năng |
| `VNSME` | 12.918 MiB (13,545,151 B) | B/C, duplicate overlay | Gói người dùng cung cấp, provenance origin | Build active đọc third_party copy, không thấy active classpath root VNSME | provenance.json; nguyên gói còn docs/config | tracked | Không tái tạo nguyên gói từ 10 source files | KEEP hiện tại; ARCHIVE tương lai nguyên gói sau restore test |
| `dvrpsim/third_party/huawei-xingtian` | 12.297 MiB (12,894,588 B) | B/C | Huawei integration/source snapshot | run_vnsme_huawei.py, historical integration | Provenance/readme; khác local simulator | tracked + ignored pyc | Không mặc định tái tạo từ network | KEEP hiện tại; archive optional sau dependency review |
| `dvrpsim/scoring_reference` | 0.036 MiB (37,337 B) | B | Reference scorer source/version context | Scoring audit/research documentation | Lịch sử exact scoring semantics | tracked | Không thay bằng current upstream | KEEP |
| `dvrpsim/gp_evidence` | 0.196 MiB (205,950 B) | B | Frozen model, validation/preservation evidence | test_dpdp_gp.py đọc artifact | GP pilot/multinstance reports và evidence inventory | tracked | Không rerun để tái tạo history | KEEP; evidence là input test, không chỉ output |
| `dvrpsim/vnsme_evidence` | 20.214 MiB (21,195,611 B) | B/C | Audit, supervision tests, contract resolution, sealed incident | test_dpdp_v3_reference/independent_audit/scale100 + ad-hoc scripts | References accepted runs/source/preservation maps | tracked + untracked + ignored logs | Một số synthetic có thể rerun, incident/timeline không | KEEP; không move scripts/manifests tùy tiện |
| `dvrpsim/migration_runs` | 249.436 MiB (261,552,889 B) | B/C | V2 denominators + retry/historical checks | V2 loader default và trainer dependency | Summary absolute paths trỏ năm run; old GP pins summary | ignored | Historical trajectory không guarantee exact rerun | KEEP toàn parent lúc này; chỉ archive phần ngoài closure sau review |
| `dvrpsim/baseline_runs` | 0.969 MiB (1,016,413 B) | C | Greedy/insertion/demo lịch sử | Current CLI không có Greedy; source_hashes exclude path | baseline_evidence/comparison.json, reports | ignored | Không tái tạo history tự động | ARCHIVE_CANDIDATE sau backup/reference map, chưa move |
| `dvrpsim/dataset_runs` | 1.423 MiB (1,492,633 B) | C | Calibration lịch sử | Không thấy active runtime import/path dependency trong bounded corpus | Data preparation report + summary/manifest | ignored | Historical timing không exact regenerable | ARCHIVE_CANDIDATE; không DELETE |
| `dvrpsim/reference_completion_evidence` | 3.330 MiB (3,491,975 B) | B | V2 recovery/adoption chain | Ad-hoc preflight/supervise/make_report | Links v2 summary/accepted retry runs | tracked + ignored logs | Không tái tạo forensic timeline | KEEP |
| `dvrpsim/.venv` | 135.935 MiB (142,538,180 B) | A + D bytecode | Interpreter hiện hành; libraries khác root venv | CLI checks sys.executable exact path | Manifest/cache context pins interpreter/packages | ignored | Reinstall cần lock/wheels/setup test chưa có | KEEP environment; chỉ pyc là phase1 candidate |
| `.venv` | 12.537 MiB (13,145,539 B) | F + D bytecode | Root venv dvrpsim1.0.0, pip26.2.2, SimPy4.1.2 | Không thấy core CLI dùng root venv; không kiểm IDE/external shell | Existing handover nhắc path; exact-executable external refs unknown | ignored | Cần export metadata + restore test trước | REVIEW, rồi DELETE_CANDIDATE khi xác nhận không dùng |
| `docs/ai_handover` | 0.091 MiB (95,755 B) | A | Sáu handover hiện tại | Không runtime import, là context cho AI/người dùng | Liên kết code/run/evidence | untracked | Không tự tái tạo lại review conclusions | KEEP; không rewrite trong cleanup audit |
| `dvrpsim/docs` | 0.178 MiB (186,153 B) | C/A docs | Tutorials + reports DPDP + docs landing page | MkDocs config/workflow + relative links | Reports historical evidence + narrative | tracked | Không rerun để tái tạo lịch sử | KEEP; future index/canonical doc, không xóa reports |
| `dvrpsim/examples` | 33.252 MiB (34,867,505 B) | C/A dependency | DPDP builder active; rmdp/sddp/tutorials upstream history | DPDP runner dynamic sys.path imports; rmdp_main dùng 180_2.txt | Generic upstream docs/provenance | tracked + ignored pyc | Không coi benchmark examples là temp | KEEP DPDP; non-DPDP archive optional |
| `dvrpsim/run_logs` | 0.329 MiB (345,312 B) | F | Old trajectories/environment/source_commit/verification | No exhaustive reference closure; chưa chứng minh unused | verification.json giữ lineage | ignored | Không biết có thể tái tạo historical logs | REVIEW; không gán DELETE vì extension.log |
| `dvrpsim/dvrp.log` | 0.071 MiB (74,125 B) | F | Old demo log | Chưa thấy active consumer trong bounded scan | Historical role chưa rõ | ignored | Không chắc | REVIEW; lợi ích dưới0.1MiB |
| `dvrpsim/__pycache__` | 0.461 MiB (482,983 B) | D | Python compiled bytecode | Import runtime có thể tự tạo lại từ source | Không trong v3 record map inspected; v2 source hashes exclude __pycache__ | ignored | Đã stat thấy .py counterpart cho mọi pyc trong repo | DELETE_CANDIDATE sau phase0; không thực hiện |


## Accepted VNSME v3 — giữ nguyên toàn collection

| Path | Size | Files | Instance/J (record) | Action |
| --- | --- | --- | --- | --- |
| `dvrpsim/vnsme_runs/v3_instance2_acceptance_20261109_r1` | 9.462 MiB | 2,358 | 2 / 95.74 | B; KEEP toàn bộ; ignored; absolute paths + hashes |
| `dvrpsim/vnsme_runs/v3_references_3_6_20261109_r1/instance_3` | 8.211 MiB | 2,259 | 3 / 97.44 | B; KEEP toàn bộ; ignored; absolute paths + hashes |
| `dvrpsim/vnsme_runs/v3_references_3_6_20261109_recovery_r1/instance_4` | 17.113 MiB | 2,189 | 4 / 100.92 | B; KEEP toàn bộ; ignored; absolute paths + hashes |
| `dvrpsim/vnsme_runs/v3_instance5_recovery_20261110_r1` | 210.120 MiB | 2,161 | 5 / 3309.546666666666666666666667 | B; KEEP toàn bộ; ignored; absolute paths + hashes |
| `dvrpsim/vnsme_runs/v3_instance5_standalone_r1` | 335.725 MiB | 2,161 | 5 / 3303.826666666666666666666667 | B; KEEP toàn bộ; ignored; absolute paths + hashes |
| `dvrpsim/vnsme_runs/v3_instance6_validation_20261110_r1` | 29.291 MiB | 2,203 | 6 / 105.04 | B; KEEP toàn bộ; ignored; absolute paths + hashes |
| `dvrpsim/vnsme_runs/v3_instance6_standalone_r1` | 23.647 MiB | 2,203 | 6 / 105.04 | B; KEEP toàn bộ; ignored; absolute paths + hashes |

Tổng non-overlap **633.569 MiB / 664,345,129 B**. Cleanup này chỉ đọc record metadata; audit replay/scorer PASS thuộc nhiệm vụ handover trước. Không cần tái chạy để quyết định bảo vệ. Không xóa stderr.txt của collection protected chỉ vì record map không liệt kê nó. Hai run5 khác trajectory/J; hai run6 cùng J chưa có nghĩa toàn directory trùng bytes.

## GP cần bảo vệ

| Path | Size | Git | Reason/action |
| --- | --- | --- | --- |
| `dvrpsim/gp_runs/vnsme_v2_new_training` | 115.472 MiB (121,081,554 B) | ignored | B KEEP; completed tree/rollouts hoặc incomplete training/audit chain |
| `dvrpsim/gp_runs/vnsme_v2_new_training_20261108_r1` | 119.070 MiB (124,853,910 B) | ignored | B KEEP; completed tree/rollouts hoặc incomplete training/audit chain |
| `dvrpsim/gp_runs/vnsme_v2_new_training_20261108_r1_audit` | 8.651 MiB (9,070,782 B) | ignored | B KEEP; completed tree/rollouts hoặc incomplete training/audit chain |
| `dvrpsim/gp_runs/official_gp_multinstance_20261109` | 9.147 MiB (9,591,416 B) | ignored | B KEEP; completed tree/rollouts hoặc incomplete training/audit chain |

Tổng 252.340 MiB. Hai vnsme_v2_new_training directories cùng392 files nhưng size khác; selected_tree.json khác bytes; không deduplicate hai run chỉ vì expression/filename giống. Official incomplete giữ generation0/cache/models/rollouts để forensic; không xóa vì thiếu training.json cuối.

## V2 reference closure thực sự còn dùng

Default summary `dvrpsim/migration_runs/vnsme_reference_ready/summary.json` có records trỏ tới:

| Run directory | Size | Files | Action |
| --- | --- | --- | --- |
| `dvrpsim/migration_runs/vnsme_reference/instance_2` | 5.458 MiB | 1,683 | B KEEP; absolute path + artifact hashes |
| `dvrpsim/migration_runs/vnsme_reference/instance_3` | 5.281 MiB | 1,613 | B KEEP; absolute path + artifact hashes |
| `dvrpsim/migration_runs/vnsme_reference/instance_4` | 7.120 MiB | 1,583 | B KEEP; absolute path + artifact hashes |
| `dvrpsim/migration_runs/reference_retry_20261108_01/instance_5` | 129.100 MiB | 1,543 | B KEEP; absolute path + artifact hashes |
| `dvrpsim/migration_runs/reference_retry_20261108_01/instance_6` | 17.852 MiB | 1,573 | B KEEP; absolute path + artifact hashes |

Năm run tổng **164.812 MiB**; summary riêng5091B. V2 loader/trainer/default summary và historical completed GP còn cần chúng. Không archive migration_runs nguyên parent trước khi xử lý closure và portability. Legacy/v2 là version label, không chứng minh unused.

## Các source modules cần giữ, kể cả compatibility

| Module | Bytes | Git |
| --- | --- | --- |
| `dvrpsim/build_vnsme.py` | 1,663 | tracked |
| `dvrpsim/compare_dpdp_baselines.py` | 5,866 | tracked |
| `dvrpsim/dpdp_audit_fixtures.py` | 9,153 | tracked |
| `dvrpsim/dpdp_contract.py` | 9,912 | untracked |
| `dvrpsim/dpdp_dataset.py` | 8,519 | tracked |
| `dvrpsim/dpdp_feasibility.py` | 8,541 | tracked |
| `dvrpsim/dpdp_gp.py` | 9,239 | tracked |
| `dvrpsim/dpdp_gp_fitness.py` | 11,735 | tracked |
| `dvrpsim/dpdp_gp_fitness_v3.py` | 2,512 | untracked |
| `dvrpsim/dpdp_insertion.py` | 15,203 | tracked |
| `dvrpsim/dpdp_schedule.py` | 4,025 | tracked |
| `dvrpsim/dpdp_sealed.py` | 821 | untracked |
| `dvrpsim/dpdp_v3_independent_audit.py` | 17,465 | untracked |
| `dvrpsim/dpdp_v3_supervisor.py` | 12,559 | untracked |
| `dvrpsim/dpdp_v3_trace.py` | 1,480 | untracked |
| `dvrpsim/dpdp_vnsme_reference.py` | 12,100 | tracked |
| `dvrpsim/dpdp_vnsme_reference_v3.py` | 17,923 | untracked |
| `dvrpsim/lock_dpdp_protocol.py` | 4,321 | tracked |
| `dvrpsim/measure_dpdp_data.py` | 5,357 | tracked |
| `dvrpsim/prepare_dpdp_data.py` | 7,575 | tracked |
| `dvrpsim/run_dpdp_insertion.py` | 15,426 | tracked |
| `dvrpsim/run_vnsme_huawei.py` | 7,552 | tracked |
| `dvrpsim/train_dpdp_gp.py` | 6,107 | tracked |
| `dvrpsim/train_dpdp_gp_multinstance.py` | 14,591 | tracked |
| `dvrpsim/verify_dpdp_log.py` | 3,642 | tracked |
| `dvrpsim/verify_dpdp_score.py` | 11,358 | tracked |

Root có44 Python files gồm26 non-test +18 test modules.14 non-test files có __main__ entrypoint. Các module v3 không tách độc lập khỏi v2: dpdp_vnsme_reference_v3 import digest từ dpdp_gp_fitness và SIMULATION từ dpdp_vnsme_reference; fitness_v3 import reference_v3. Không xóa modules v2 để làm gọn v3. Tests/source mới untracked phải giữ trước mọi cleanup.

## Caches / unknown

| Bytecode scope | Files | Bytes | Action |
| --- | --- | --- | --- |
| project | 114 | 1,092,244 | D DELETE_CANDIDATE chỉ sau backup, source/restore checks |
| .venv | 447 | 6,271,244 | D DELETE_CANDIDATE chỉ sau backup, source/restore checks |
| dvrpsim/.venv | 2,302 | 53,353,525 | D DELETE_CANDIDATE chỉ sau backup, source/restore checks |

GP fitness/cache chỉ 1.809 MiB,1897156B; lưu cache context, raw benchmark J, validity, rollout/log paths. Xóa có thể mất lineage hoặc gây rerun đắt/khác trajectory; B/C KEEP, không lump với Python pyc.

Root .venv non-cache 6.556 MiB là F REVIEW; không gọi là exact duplicate environment vì package versions khác. F còn 0.400 MiB old logs (dvrpsim/run_logs/ và dvrpsim/dvrp.log). Không thấy conventional .tmp/.temp/.bak/.old/.swp hoặc directory tmp/temp/.pytest_cache trong snapshot; không tạo cleanup opportunity giả từ tên gọi chung.

## Historical archive candidates (chỉ tương lai)

| Path | Size | Action / constraint |
| --- | --- | --- |
| `dvrpsim/gp_runs/scale100_diagnostic_20261109_r1` | 95.814 MiB | C ARCHIVE sau dependency/restore test; không move hiện tại |
| `dvrpsim/gp_runs/multinstance_50_20261105` | 27.377 MiB | C ARCHIVE sau dependency/restore test; không move hiện tại |
| `dvrpsim/gp_runs/delta_j_diagnostic_20261109_r1` | 16.760 MiB | C ARCHIVE sau dependency/restore test; không move hiện tại |
| `dvrpsim/gp_runs/c10_instance3_diagnostic_20261109_r1` | 10.174 MiB | C ARCHIVE sau dependency/restore test; không move hiện tại |
| `dvrpsim/gp_runs/smoke_test_measure_20261109` | 8.449 MiB | C ARCHIVE sau dependency/restore test; không move hiện tại |
| `dvrpsim/gp_runs/comparison_20261105` | 2.076 MiB | C ARCHIVE sau dependency/restore test; không move hiện tại |
| `dvrpsim/gp_runs/pilot_20261105_v2` | 1.977 MiB | C ARCHIVE sau dependency/restore test; không move hiện tại |
| `dvrpsim/gp_runs/pilot_20261105` | 0.244 MiB | C ARCHIVE sau dependency/restore test; không move hiện tại |
| `dvrpsim/gp_runs/demo_adapter_smoke` | 0.126 MiB | C ARCHIVE sau dependency/restore test; không move hiện tại |
| `dvrpsim/vnsme_runs/scale100_reference_20261109_r1` | 112.124 MiB | C ARCHIVE sau dependency/restore test; không move hiện tại |
| `dvrpsim/baseline_runs` | 0.969 MiB | C ARCHIVE sau dependency/restore test; không move hiện tại |
| `dvrpsim/dataset_runs` | 1.423 MiB | C ARCHIVE sau dependency/restore test; không move hiện tại |

Tổng subset disjoint 277.514 MiB; khác với toàn class C. Traces/diagnostics vẫn scientific evidence; archive giữ bytes + path map + source/evidence closure. Offload thực sự ra ổ khác mới giảm LA drive sau khi được phép bỏ bản local; move cùng ổ không tiết kiệm.
