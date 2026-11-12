# Trạng thái repository và evidence

Snapshot audit ngày **2026-11-10, khoảng 19:28 Asia/Bangkok**. Các đường dẫn bên dưới tương đối với Git root `C:/Users/Cuongdz/Documents/LA`, trừ các hậu tố run được định nghĩa riêng.

## Repository đã xác minh

- **VERIFIED:** root `C:/Users/Cuongdz/Documents/LA`, branch `complete-gp-dpdp`, HEAD `0bd773291d5d9034f1e7b81688bc2dfaf87308c7`.
- Lịch sử hiện có một commit: `2026-11-09 16:51:07 +0700`, “Initial commit: GP_DPDP project with dvrpsim, VNSME baseline, and research documentation”. Không có đủ lịch sử Git để tái dựng các giai đoạn trước initial commit; các mốc v2/v3 còn phải dựa artifact, code hash và báo cáo.
- **VERIFIED:** trước bàn giao có 9 tracked files modified, không có staged change trong `git status --short`; diff 186 insertions/38 deletions. Chỉ sáu tài liệu handover được thêm trong audit này. Không commit/reset/stash/refactor.
- Python đúng cho CLI: `LA/dvrpsim/.venv/Scripts/python.exe` 3.14.4; SimPy 4.1.2; dvrpsim 0.0.1; OpenJDK 26.0.1. Root `.venv` cũng 3.14.4 nhưng không thỏa interpreter guard của các CLI. `python` PATH không chạy được trong session này.

Tracked modified trước audit:

```text
dvrpsim/dpdp_dataset.py
dvrpsim/dpdp_vnsme_reference.py
dvrpsim/examples/case_studies/dpdp/dpdp_problemdata.py
dvrpsim/prepare_dpdp_data.py
dvrpsim/run_dpdp_insertion.py
dvrpsim/src/baselines/vnsme.py
dvrpsim/test_dpdp_dataset.py
dvrpsim/test_dpdp_gp.py
dvrpsim/verify_dpdp_score.py
```

Untracked có ý nghĩa trước audit (từ `git status --short`):

```text
TIEN_DO_GP_DPDP.md
dvrpsim/.gitattributes
dvrpsim/dpdp_contract.py
dvrpsim/dpdp_gp_fitness_v3.py
dvrpsim/dpdp_sealed.py
dvrpsim/dpdp_v3_independent_audit.py
dvrpsim/dpdp_v3_supervisor.py
dvrpsim/dpdp_v3_trace.py
dvrpsim/dpdp_vnsme_reference_v3.py
dvrpsim/protocols/dpdp_execution_commitment_v3.json[.sha256]
dvrpsim/protocols/dpdp_gp_vnsme_v3_draft.json[.sha256]
dvrpsim/protocols/dpdp_official_experiment_v1.json[.sha256]
dvrpsim/test_dpdp_execution_contract.py
dvrpsim/test_dpdp_policy_audit.py
dvrpsim/test_dpdp_sealed.py
dvrpsim/test_dpdp_v3_independent_audit.py
dvrpsim/test_dpdp_v3_reference.py
dvrpsim/test_dpdp_v3_supervisor.py
dvrpsim/test_dpdp_vnsme_scale100.py
dvrpsim/test_dpdp_vnsme_timeout.py
dvrpsim/vnsme_evidence/fast_audit_instance5_20261110_152157/
dvrpsim/vnsme_evidence/scale100_blockers_20261109_r2/
dvrpsim/vnsme_evidence/scale100_contract_resolution/
dvrpsim/vnsme_evidence/v3_independent_audit_20261109_r1/
dvrpsim/vnsme_evidence/v3_instance5_recovery_20261110_r1/
dvrpsim/vnsme_evidence/v3_reference_supervision_20261109_r1/
dvrpsim/vnsme_evidence/v3_references_3_6_20261109_r1/
dvrpsim/vnsme_evidence/v3_references_3_6_20261109_recovery_r1/
```

`[.sha256]` ở danh sách này nghĩa là có cả JSON và file sidecar, không phải tên file literal. Run directories bị `.gitignore` bỏ qua, dù tồn tại trên máy. Không được hiểu “không có trong git status” là “không có run”.

## VNSME v3 — kết quả audit trực tiếp

**VERIFIED:** gọi lại `dvrpsim/dpdp_vnsme_reference_v3.py:audit_vnsme_run` trên từng collection bên dưới, không gọi `run_reference`, không khởi động Java/simulator. Hàm kiểm tra contract/config/data/build/runtime, ledger completion, guard, independent physical/publication replay, scorer và supervision. Với cả bảy collection: kết quả audit bằng chính xác `record.json` đã lưu; mọi SHA-256 trong `artifact_sha256`, `supervision_sha256` và `protocol_manifest_sha256` được đọc lại, không mismatch. Mỗi lần khoảng 1.8–3.3 giây.

Đặt `R = dvrpsim/vnsme_runs/`. Mỗi hàng sau có đủ `R/<collection>/protocol_manifest.json`, `record.json`, `run/{manifest,result,decisions,commitments}.json`, `run/simulation.log`, `run/decision_trace.jsonl`, `run/vnsme/session.json`, per-epoch I/O/markers và `supervisor/{supervision.json,heartbeats.jsonl,process.log}`. Hash maps nằm trong record; không bắt buộc có `.sha256` riêng cạnh từng artifact.

| Instance | Vai trò | Collection sau R/ | Trạng thái full run | D km | T giây | J | Runner wall s | Supervisor wall s |
|---:|---|---|---|---:|---:|---:|---:|---:|
| 2 | Train | `v3_instance2_acceptance_20261109_r1` | VERIFIED PASS | 478.7 | 0 | 95.74 | 32.1266 | 33.7461 |
| 3 | Train | `v3_references_3_6_20261109_r1/instance_3` | VERIFIED PASS | 487.2 | 0 | 97.44 | 26.7209 | 29.3908 |
| 4 | Train | `v3_references_3_6_20261109_recovery_r1/instance_4` | VERIFIED PASS | 504.6 | 0 | 100.92 | 1649.2622 | 1650.8704 |
| 5 | Train | `v3_instance5_recovery_20261110_r1` | VERIFIED PASS; chưa chọn canonical | 464.4 | 1158 | 3309.546666666666666666666667 | 2726.1255 | 2728.0264 |
| 6 | Validation | `v3_instance6_validation_20261110_r1` | VERIFIED PASS | 525.2 | 0 | 105.04 | 569.3246 | 571.6410 |

Các run trên đều `state=EXITED`, `exit_code=0`, `valid_supervision=true`, `gaps=[]`, không process thuộc job còn sót theo artifact; không hard epoch/rollout timeout trong validation. Không suy rộng điều đó thành không có Java hiện đang chạy ở toàn máy.

Giao đủ **50 original orders** mỗi instance; item/decision counts lần lượt: 2 = 110/167, 3 = 78/160, 4 = 88/155, 5 = 107/153, 6 = 86/156. Đây là completed items và dispatch count, không phải số original orders.

### Instance 5, 6: các lượt khác cũng hợp lệ

| Instance | Collection sau R/ | Full audit/hash/record | D km | T giây | J | Runner wall s | Supervisor wall s |
|---:|---|---|---:|---:|---:|---:|---:|
| 5 | `v3_instance5_standalone_r1` | VERIFIED PASS | 435.8 | 1158 | 3303.826666666666666666666667 | 2726.4607 | 2728.2600 |
| 6 | `v3_instance6_standalone_r1` | VERIFIED PASS | 525.2 | 0 | 105.04 | 568.9773 | 571.4352 |

Hai lượt instance 5 có cùng audited runtime fingerprint/contract/build/settings và đều hợp lệ, nhưng distance chênh 28.6 km, J chênh 5.72. **VERIFIED:** đây là khác biệt giữa kết quả lưu, không được tự chọn J thấp hơn rồi gọi đó là baseline canonical. **UNKNOWN:** nguyên nhân chính xác chưa được phân lập; Java wall-time search và host time là yếu tố cần kiểm tra. Không kết luận do RNG: `new Random()` có trong `randomLocalSearch`, nhưng tìm kiếm call site chỉ thấy định nghĩa, chưa thấy hàm được gọi trong source này.

Evidence phụ: `dvrpsim/vnsme_evidence/fast_audit_instance5_20261110_152157/audit_report.json` ghi full-validator/loader PASS, record_match=true, provenance với 2–4 khớp; nó trỏ tới **standalone** J=3303.826666..., không phải recovery J=3309.546666.... `v3_instance5_recovery_20261110_r1/preflight_instance6.json` trong **vnsme_evidence** lại dùng recovery J=3309.546666.... Không gộp hai luồng evidence thành một run.

### Combined reference v3

**NOT FOUND / INCOMPLETE ở cấp bộ reference:** kiểm tra các `summary.json` trong `dvrpsim/vnsme_runs` có đường dẫn v3 chỉ thấy summary singleton tại `v3_instance2_acceptance_20261109_r1/reference_2/summary.json` (records=[2]). Chưa thấy summary v3 records=[2,3,4,5,6]. Output dự kiến trong preflight là `vnsme_runs/v3_reference_ready_2_6_20261110_r1`; thư mục đó không có trong inventory top-level.

Vì thế: năm instance đã có full run riêng được chứng nhận; **chưa chứng nhận bộ denominator canonical 2–6 qua `load_reference(...,{2,3,4,5,6})`**. Audit này cố ý không chạy `assemble` vì sẽ tạo experimental artifact ngoài sáu tài liệu được phép. Không xem preflight `all_pass=true` là combined PASS.

### Lượt gián đoạn lịch sử

- **REPORTED:** instance 4 ở `R/v3_references_3_6_20261109_r1/instance_4` bị ngắt, 106 epoch starts/105 end markers, không final result/record/supervision. Không là reference; không nhầm với recovery PASS.
- **REPORTED:** instance 5 ở `R/v3_references_3_6_20261109_recovery_r1/instance_5` bị ngắt, 112 starts/111 ends, heartbeat cuối epoch 00111 ~359s, chưa chạm 600s timeout, thiếu final result/record/supervision. Sau đó có lượt 10/11 hoàn tất như trên.
- Nguồn: `dvrpsim/vnsme_evidence/v3_references_3_6_20261109_r1/STATUS.md`, `.../instance4_epoch_count_correction.md`, `.../v3_references_3_6_20261109_recovery_r1/{STATUS.md,RESULTS.md,instance5_interrupted.json}`. Chi tiết heartbeat lịch sử không được tính lại trong audit này.

## GP hiện tại

| Run/implementation | Trạng thái xác minh | Ý nghĩa |
|---|---|---|
| `dvrpsim/gp_runs/vnsme_v2_new_training_20261108_r1` | VERIFIED có generations 0/1/2, candidates, selected_tree, training, fitness models/cache/rollouts; số đo dưới là REPORTED từ JSON | Completed **v2**, không là kết quả v3 |
| `dvrpsim/gp_runs/official_gp_multinstance_20261109` | VERIFIED chỉ có top-level `experiment_protocol.json`, `generation_0.json`; không selected_tree/training/candidates cuối hoặc generation 1–3 | INCOMPLETE; không có bằng chứng hoàn tất protocol G=3 |
| `dvrpsim/dpdp_gp_fitness_v3.py` | VERIFIED offline normalized evaluator | Có API audit saved GP runs và tính ratio; không train/breed/cache/CLI training v3 |
| `dvrpsim/protocols/dpdp_gp_vnsme_v3_draft.json` | VERIFIED `DRAFT_NOT_ENABLED_FOR_TRAINING`, `enabled=false` | GP v3 chính thức NO-GO |

V2 run 08/11 báo `status=complete`, seed 20261106, pop=6, generations=2 (0..2), 55 process rollouts, wall=359.9827s. Selected tree:

```text
(((delta_tardiness_seconds / delta_distance_km) - min_residual_capacity) + delta_tardiness_seconds)
```

Selected train mean ratio **106.09054959678747**, validation ratio **1.7524752475247525**. Đây là số lưu trong selected_tree/training, **không tái audit tất cả GP rollouts** trong nhiệm vụ này; không có nghĩa GP vượt VNSME. V2 denominator trong `migration_runs/vnsme_reference_ready/summary.json` khác contract v3; ví dụ instance 4 v2 J=100.76, v3 J=100.92, instance 5 v2 J=3303.926666..., không thay lẫn nhau.

Run “official” seed 20261109 ghi G=3, pop=6, timeout=30s, fitness version **v2**; generation 0 có sáu valid trees, best train mean ratio **23.908337888479483**. Không có bằng chứng xác định vì sao dừng sau generation 0 hoặc rằng tiến trình còn chạy; không gọi “đang training” chỉ vì `TIEN_DO_GP_DPDP.md` nói vậy. Không kiểm tra/kill tiến trình nghiên cứu trong audit này.

Các pilot/diagnostic lịch sử được giữ: `gp_runs/pilot_20261105*`, `multinstance_50_20261105`, `vnsme_v2_new_training`, `c10_instance3_diagnostic_20261109_r1`, `delta_j_diagnostic_20261109_r1`, `scale100_diagnostic_20261109_r1`. Không tái chứng nhận kết quả của chúng; diagnostic không tự trở thành trained method.

**VERIFIED về cơ chế:** C10 có thể ưu tiên tăng tardiness khi delta distance âm. `test_dpdp_policy_audit.py` tái hiện feature ΔD=-0.1, ΔT=5978 cho rank=-53814.5 thay vì candidate không tardy rank=-13. Đây là thuộc tính của cây và phép chia signed; không đủ để kết luận feature implementation sai. File test có mặt, không chạy lại suite trong audit này.

## Phát hiện khoa học và công việc dang dở

1. **VERIFIED P0:** thiếu combined canonical reference v3 + frozen training protocol/trainer v3; không bắt đầu training v3 chính thức.
2. **VERIFIED P0:** hai valid instance-5 trajectories khác điểm; cần run-selection policy, không cherry-pick theo J.
3. **REPORTED P0/P1:** từng có đọc sealed CSV trong regression discovery, xem `vnsme_evidence/v3_reference_supervision_20261109_r1/REPORT.md`. `v3_independent_audit_20261109_r1/summary.json` cũng có `final_test_read_incident_from_prior_run=true`. Không chứng minh có sealed rollout, nhưng cũng không thể khẳng định untouched bytes.
4. **VERIFIED P1:** protocol `dpdp_official_experiment_v1.json` ghi penalty 1e9, code `INVALID_FITNESS` và official run config dùng 1e15; protocol cũng gắn tên split SHA bằng hash **source manifest** cf7239..., trong khi actual split SHA là 21c7f6.... Phải sửa trong **protocol phiên bản mới**, không sửa snapshot cũ. Trainer nhận split, không đọc/enforce toàn bộ official protocol.
5. **VERIFIED P1:** replay tự ghi limitation: at-location future ETA chỉ đối chiếu pre-decision lock, chưa forecast lại độc lập. Predictor có equal-arrival ties theo thứ tự xe. Báo cáo không được biến PASS giới hạn này thành chứng minh mọi dự báo ETA đúng.
6. **VERIFIED P1:** nguồn v3 chưa commit, outputs bị Git ignore, record dùng absolute paths; HEAD đơn lẻ không tái lập working tree.
7. **VERIFIED P1:** baseline có wall-clock cooperative stop 540s, hard epoch=600s, rollout=10800s; thời gian tìm kiếm không cộng vào simulation. So sánh runtime phải công bố cả GP online dispatch, training/offline cost và VNSME Java startup/search, không chỉ J hay total wall.
8. **INFERRED:** công việc gần nhất tập trung v3 contract resolution, independent audit/sealed guards, recovery 5 và validation 6, rồi audit standalone 5. Đây là suy luận từ dirty files, timestamp và launcher/evidence; không có hội thoại trước audit để biết chính xác ý định Codex trước đó.

## Chưa xác minh

UNKNOWN: nguyên nhân khác nhau giữa hai instance-5 runs; canonical run nào được phê duyệt; tình trạng tiến trình GP hiện tại; toàn bộ GP cache/result hashes; 100-order reference coverage/khả năng mở rộng; equivalence đầy đủ với Huawei simulator; mức độ tác động của sự cố đọc sealed đến tính độc lập khoa học; PASS của test suite ở working tree hiện tại. Không đọc nội dung sealed để trả lời các câu hỏi này.
