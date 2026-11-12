# Roadmap tiếp tục dự án

Audit 2026-11-10. Không có thay đổi implementation hoặc experiment trong tài liệu này được thực thi. Ước lượng S/M/L là độ phức tạp tương đối, không phải thời gian chạy benchmark. Đường dẫn module dưới đây tương đối với `LA/dvrpsim/`.

## Việc đầu tiên: khóa danh tính reference, chưa training

**P0.1 — Quyết định canonical run cho instance 5 và 6, sau đó assemble reference 2–6. Độ phức tạp M.**

- Mục tiêu: bộ denominator có provenance rõ ràng, không cherry-pick. Bảy collection hiện tại đã được audit lại PASS, gồm hai instance-5 runs khác D/J và hai instance-6 runs cùng D/J.
- Module/file: `dpdp_vnsme_reference_v3.py:{audit_vnsme_run,load_reference,main}`, hai `record.json` của instance 5, hai record instance 6, `vnsme_evidence/fast_audit_instance5_20261110_152157/audit_report.json`, `.../v3_instance5_recovery_20261110_r1/preflight_instance6.json`.
- Tiên quyết: giữ nguyên mọi run và hash; người tiếp tục hiểu recovery J=3309.546666... khác standalone J=3303.826666...; xác định kế hoạch chọn run đã có từ trước nếu evidence tồn tại. Không tự ưu tiên J thấp.
- Bước đề xuất: đối chiếu timestamp, command, Java/private-solution provenance, host date/time, long epochs và code/settings; tìm tiêu chí canonical đã được thỏa thuận. Nếu chưa có, ghi rõ quyết định mới và giới hạn lựa chọn sau khi đã biết điểm. Đóng băng một record mỗi ID. Re-audit, assemble vào output mới, load exact set {2,3,4,5,6}, ghi acceptance report/summary hash. Việc assemble là thay đổi experimental artifact, cần nhiệm vụ tiếp theo cho phép; audit hiện tại chỉ ghi handover.
- Acceptance: load_reference PASS cho đúng 5 IDs, không duplicate/mixed-v2/missing/hash mismatch; mỗi J truy ngược đúng run đã chọn; không sửa snapshot cũ.
- Evidence: canonical-selection decision, input record hashes, combined summary/hash, loader output và provenance matrix, sealed-access count=0.
- Rủi ro: selection bias, wall-time-dependent trajectory, nhầm standalone/recovery, absolute paths làm loader không portable. Không cần full rerun chỉ để khắc phục thiếu summary nếu existing runs vẫn hợp lệ.

Lệnh tương lai sau khi đã chọn R5/R6, chạy từ `LA/dvrpsim` (chỉ là bản mẫu, **không chạy nguyên văn với placeholder**):

```text
./.venv/Scripts/python.exe -B dpdp_vnsme_reference_v3.py assemble --records
  vnsme_runs/v3_instance2_acceptance_20261109_r1/record.json
  vnsme_runs/v3_references_3_6_20261109_r1/instance_3/record.json
  vnsme_runs/v3_references_3_6_20261109_recovery_r1/instance_4/record.json
  <R5>/record.json <R6>/record.json --output <NEW_CANONICAL_REFERENCE_DIRECTORY>
```

Ghép thành một invocation đúng shell; không dùng v2 `migration_runs/vnsme_reference_ready/summary.json`.

## P0 — Các điều kiện bắt buộc trước thí nghiệm mới

**P0.2 — Bảo toàn working tree và nguồn có thể tái lập. Độ phức tạp S/M.**

- Mục tiêu: người khác nhận được đúng code/evidence ngoài HEAD.
- File: 9 tracked modified và untracked được liệt kê trong `CURRENT_STATUS.md`; `.gitignore`, `.gitattributes`, source/build manifests.
- Tiên quyết: snapshot read-only và danh sách run canonical từ P0.1; không reset/stash/discard thay đổi có sẵn.
- Bước: inventory/hash code, protocol và artifact cần thiết; chuẩn bị review diff; archive bytes + package/compiler/runtime metadata + ignored outputs; ghi các absolute paths và kế hoạch relocation. Chỉ commit/publish khi thuộc phạm vi được giao.
- Acceptance: fresh inspection xác định đúng runtime fingerprint của reference; không có artifact thay đổi ngầm do EOL; người nhận có đủ inputs phát triển/code/evidence để kiểm tra.
- Evidence: source/artifact inventory/hash manifest, dependency versions, reviewed diff, eventual commit/archive ID.
- Rủi ro: Git không chứa ignored runs, v3 source untracked, CRLF biến hash, Python minimum metadata sai. Không patch historical artifacts để che mismatch.

**P0.3 — Chốt protocol v3 trước khi viết/chạy evolution chính thức. Độ phức tạp M.**

- Mục tiêu: một specification có thể enforce, đồng bộ penalty/hash/seed/budget/model selection.
- File: `protocols/dpdp_gp_vnsme_v3_draft.json`, `dpdp_official_experiment_v1.json`, split/contract, `dpdp_gp_fitness_v3.py`.
- Tiên quyết: P0.1 PASS, P0.2 source archive, ghi nhận sealed incident.
- Bước: tạo protocol phiên bản mới giữ nguyên snapshots v2; pin đúng combined summary/hash; sửa phân biệt split SHA21c7... và manifest SHAcf723...; chọn penalty thực tế; specify population/generations/seeds/caps/timeout/cache/invalid rules, selection/rerun policy và runtime reporting; validation không evolution; chỉ enable sau review/checks.
- Acceptance: schema/semantic validation từ code, không silent defaults, không trộn fitness versions hoặc dùng metadata filename làm proof.
- Evidence: protocol mới + SHA sidecar, configuration validation report, GO/NO-GO checklist có lý do.
- Rủi ro: tự xem G=3/pop6 là đủ nghiên cứu, cùng chọn rule sau biết điểm, descriptor không được trainer đọc. Không bật draft bằng cách đổi `enabled=true` đơn thuần.

## P1 — Tính đúng đắn khoa học

**P1.1 — Disclosure sealed incident và kiểm soát truy cập. Độ phức tạp M.**

- Mục tiêu: giữ cách diễn đạt trung thực và chứng minh workflow mới không chạm sealed bytes.
- File: `dpdp_sealed.py`, `prepare_dpdp_data.py`, loaders/scorer, `test_dpdp_sealed.py`, `vnsme_evidence/v3_reference_supervision_20261109_r1/REPORT.md`.
- Tiên quyết: không mở test để điều tra; dùng code/log metadata.
- Bước: lập incident timeline từ báo cáo, phân biệt byte/schema access với rollout/score/model use; rà call paths có thể bypass; kiểm synthetic path guards và recording open attempts bằng bounded tests trong nhiệm vụ được phép. Xác định ảnh hưởng methodology trước final evaluation; không tự thay split.
- Acceptance: công bố không còn khẳng định “never read”; development checks zero sealed opens; giải thích mức bảo vệ application-only/copies; quyết định cuối về holdout có ghi rationale.
- Evidence: incident note, guarded test report, access log và final-evaluation authorization plan.
- Rủi ro: gọi metadata exposure là score leakage khi chưa có bằng chứng, hoặc phủ nhận incident vì guard đã sửa.

**P1.2 — Forecast/feature/feasibility semantic audit. Độ phức tạp M/L.**

- Mục tiêu: phân biệt đặc tính cây, lỗi forecast và sai model dynamics.
- File: `dpdp_insertion.py`, `dpdp_schedule.py`, `dpdp_feasibility.py`, `dpdp_v3_independent_audit.py`, `test_dpdp_policy_audit.py`, feasibility/schedule report/tests.
- Tiên quyết: protocol semantics giữ ổn định; chỉ synthetic/development data.
- Bước: thiết kế cases ongoing service, FCFS equal arrivals, already delivered/current load, destination ETA, order-splitting qua epochs; tính tay 5 features và so independent prediction; kiểm signed ΔD/ΔT và C10 sign flip. Nếu cần sửa feature/predictor, version hóa và xem lại tác động reference fingerprints trước chạy lại.
- Acceptance: numerical examples/independent oracle khớp; ETA forecast limitation được thu hẹp hoặc ghi rõ; hard feasibility không bị đổi thành soft; không đưa private future orders vào ranker.
- Evidence: focused regression report, feature calculation examples, replay audit matrix với PASS/UNVERIFIABLE có phạm vi.
- Rủi ro: sửa feature để overfit một tree; source fingerprint change làm denominator cũ không còn hợp lệ với code mới.

**P1.3 — Reproducibility và runtime fairness. Độ phức tạp M.**

- Mục tiêu: công bố đúng sự khác nhau giữa simulator seed, GP RNG và Java time-dependent search.
- File: `src/baselines/vnsme.py`, Java `main_algorithm.java`, supervisor, runner timing fields, protocol mới.
- Tiên quyết: P0.1 lựa chọn canonical; không chạy full repeats trong nhiệm vụ read-only hiện tại.
- Bước: trước hết so saved epoch/publication trajectories của hai instance-5 runs; xem wall-stop boundaries và midnight offset; tránh quy cho `new Random()` không có call site. Specify CPU/hardware/load, thread/run counts, deadline và phân tách online dispatch/Java startup/training/scoring/supervision. Đề xuất repeat study sau khi budget được cấp.
- Acceptance: nguyên nhân được chứng minh hoặc ghi UNKNOWN với cách kiểm tra; báo cáo không dùng seed0 làm bằng chứng Java deterministic; không so runtime khác định nghĩa.
- Evidence: saved-run comparison, reproducibility contract, timing schema, eventual repeat logs.
- Rủi ro: wall-clock/host date, shared machine contention, compute instantaneous trong mô phỏng, chi phí experiment lớn.

## P2 — Phát triển GP (chỉ sau P0)

**P2.1 — Xây trainer/evaluator/cache v3 thực sự. Độ phức tạp L.**

- Mục tiêu: nối evolutionary loop với v3 rollout và denominator certified, không dùng v2 adapter ngầm.
- File: `train_dpdp_gp_multinstance.py`, `dpdp_gp_fitness.py`, `dpdp_gp_fitness_v3.py`, `run_dpdp_insertion.py`, v3 audit/trace.
- Tiên quyết: P0 PASS và P1 constraints được xử lý/ghi rõ; protocol v3 thống nhất.
- Bước: interface config bắt buộc đọc/enforce protocol; explicit `--contract-version`; cache namespace mới bind tree/feature/evolution/sim/scorer/data/source/reference/env/budgets; fail closed invalid/missing evidence; validator train exact IDs và selection isolation; generation/checkpoint format với RNG state nếu muốn resume. Dùng synthetic/bounded smoke trước, không coi smoke là official result.
- Acceptance: reject v2/mixed denominator và cache, invalid rollout không có valid J; selection deterministic trên records; no sealed reads; mọi emitted artifact có provenance và evaluator offline v3 chấp nhận.
- Evidence: design review, focused tests + bounded smoke, emitted protocol/config/cache schema, source hash manifest.
- Rủi ro: quá nhiều rollout, timeout penalty che bottleneck, cache stale, chỉ đổi version string mà chưa đổi execution contract. Không khuyên chạy GP v3 chính thức trước khi đáp ứng gates.

**P2.2 — Thiết kế và chạy development study có ngân sách. Độ phức tạp L.**

- Mục tiêu: kiểm tra ranker GP và cải thiện có hypothesis, không hứa sẽ thắng VNSME.
- File: trainer v3 mới, feature/primitive config, experiment protocol, selected model/analysis reports.
- Tiên quyết: P2.1 và GO training; chưa mở final test.
- Bước: đặt hypotheses từ C10/sign/scale constraints; predefine seeds/budgets/ablations trên train, validation chỉ theo rule; estimate rollout budget bằng bounded development probes; training chính thức vào output mới sau authorization riêng; freeze selected tree/hash/config và explain failures.
- Acceptance: completed generations/candidates/rollouts với provenance, đủ validation selection và uncertainty; báo cáo negative outcomes; không reuse legacy fitness như v3.
- Evidence: population/generation/training/candidates/tree JSON, cache lineage, rollout audit, train/val tables và runtime.
- Rủi ro: tuning quá nhiều trên validation 6; pop6/G3 là pilot nhỏ, chưa đủ kết luận generalization; overfit distance matrix/seed.

## P3 — Đánh giá và báo cáo cuối

**P3.1 — Đóng băng và đánh giá cuối trong workflow được cấp phép riêng. Độ phức tạp L.**

- Mục tiêu: đo kết quả cuối với cùng contract/scorer/data/initial conditions và quyết định holdout minh bạch.
- File: sealed workflow chưa có bypass development, frozen model/protocol/reference, report scripts.
- Tiên quyết: P0/P1/P2 hoàn thành; sealed incident xử lý; người dùng cho phép mở final test; freeze methods trước khi đọc kết quả. 100-order vẫn proposed đến khi protocol riêng khóa.
- Bước: thiết kế final access path có audit trail, chạy đúng run/repeat policy đã cam kết, independent replay/rescore, report J/D/T/completion/ratio/runtime cho cả GP/VNSME; không tune hoặc debug trên sealed results.
- Acceptance: đầy đủ final evidence, comparable constraints/settings, ghi failures, không chọn lại tree theo test; không làm kết luận thống kê vượt số scenario/seeds.
- Evidence: final authorization/freeze hashes, execution/audit manifests, paired comparison, reproducibility archive và paper-ready methods/limitations.
- Rủi ro: opened test không còn phục vụ tuning, khác local/Huawei dynamics, sample nhỏ/dependent, lựa chọn có bias, missing ignored outputs.

**P3.2 — Hoàn thiện báo cáo và bàn giao tái lập. Độ phức tạp M.**

- Mục tiêu: người đọc phân biệt rõ GP/Greedy lịch sử/VNSME v2/v3 và kiểm tra lại kết luận.
- File: `docs/reports/dpdp/`, các handover, experiment archive và build provenance.
- Tiên quyết: P3.1 hoặc báo cáo rõ experiment chưa hoàn tất.
- Bước: tổng hợp methods, contract delta, dataset lineage/split incident, exact objective, hypotheses, training/selection, raw result tables và limitations; kiểm mỗi số có artifact gốc; cập nhật status bằng file mới, không ghi đè evidence lịch sử.
- Acceptance: không claim GP beats baseline khi bảng không chứng minh, không claim untouched test trái incident, repo/artifact bundle có đủ hash/versions.
- Evidence: final report, machine-readable tables, artifact index/checksums, reproduction instructions có expected outputs.
- Rủi ro: prose cũ lỗi thời như `TIEN_DO_GP_DPDP.md`, trộn run/version, omission của negative results.
