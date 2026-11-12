# Kế hoạch cleanup theo giai đoạn — chưa thực hiện

Ngày2026-11-10, Asia/Bangkok. **Đây là audit/planning. Không có quyền xóa, move, rename, sửa code/protocol, commit/reset/clean.** Bảy reports là thay đổi duy nhất được phép. Không chạy training/simulation/benchmark/Java search/test discovery. Mọi phase dưới là công việc tương lai cần được người dùng phê duyệt theo scope cụ thể.

## Ước lượng dung lượng: không cộng trùng

Snapshot tổng **2,034,035,362B = 1.894 GiB**. Sizes logical, chưa biết allocated disk/compression; không có mục tiêu phần trăm giảm bắt buộc.

| Category / paths | Current size | Proposed action | Potential savings | Risk |
| --- | --- | --- | --- | --- |
| Python bytecode ngoài env: all project __pycache__/*.pyc | 1.042 MiB | Conditional DELETE_CANDIDATE sau phase0 | Tối đa 1.042 MiB | Thấp khi source và no-running-jobs checks pass; vẫn cần preservation review |
| Root env bytecode .venv/**/__pycache__/*.pyc | 5.981 MiB | Conditional DELETE_CANDIDATE | Tối đa 5.981 MiB | Cold starts; không đụng distribution/source |
| Main env bytecode dvrpsim/.venv/**/__pycache__/*.pyc | 50.882 MiB | Conditional DELETE_CANDIDATE | Tối đa 50.882 MiB | Current interpreter; cần confirm idle/source available |
| Root .venv whole | 12.537 MiB (13,145,539 B) | REVIEW external usage/recreation; giữ main env | Nếu phase1 đã xóa root pyc: chỉ thêm 6.556 MiB | Khác versions main; external consumers UNKNOWN |
| Main dvrpsim/.venv whole | 135.935 MiB (142,538,180 B) | KEEP current runtime | 0 ngoài pyc đã tính | Exact executable/Python/package context bind |
| Selected historical archive subset12paths | 277.514 MiB | ARCHIVE sau closure/restore test | 0 nếu same-drive move; offload upper footprint 277.514 MiB | High: docs/test/path/hash/forensic references, không approved |
| All class C history/upstream examples | 646.349 MiB | Historical designation, chưa duyệt archive toàn C | Không dùng toàn size này làm savings | Bao gồm interrupted evidence, upstream data và logical overlaps với review scopes |
| Seven accepted v3 collections | 633.569 MiB | KEEP toàn bộ, cả variants5/6 | 0 | Critical record/path/source/build/replay dependencies |
| V2 accepted reference five-run closure | 164.812 MiB | KEEP, không blanket archive migration_runs | 0 | Current v2 trainer/default denominator dependency |
| Completed GP v2 runs/audit + official incomplete | 252.340 MiB | KEEP | 0 | Tree/candidate/cache/rollout/training forensic |
| Same-size stderr candidate pairs | 370.063 MiB one-copy footprint | REVIEW;3 pairs hash verified, mọi protected run giữ | 0 approved; không tính388MB như savings | Evidence/diagnostics, phần lớn chưa hash equality |
| Verified large duplicate log samples3pairs | 138.221 MiB extra copies | KEEP protected collections | 0 | Subset của row stderr candidates, KHÔNG cộng riêng |
| Vendor original source/lib duplicate trees | 12.753 MiB one copy | KEEP active + provenance; optional original-package archive | 0 approved | Library classes không có rebuild workflow; source overlap corpus duplicates |
| GP fitness/cache all studies | 1.809 MiB | KEEP as result provenance | 0 | Không regenerable rẻ/identical; subsets của studies |
| dvrpsim/third_party/vnsme/build | 0.143 MiB (149,967 B) | KEEP | 0 | Tiny saving; class hash/build manifest pin |
| F unresolved non-cache rootenv + old logs | 6.956 MiB | REVIEW; không DELETE | Chưa xác định | Rootenv overlap optional row; old logs chưa closure |
| Markdown docs entire repo | 0.574 MiB | KEEP + navigation/index trong nhiệm vụ riêng | Gần0 | Không đánh đổi history/links để tiết kiệm dưới1MiB |


Các phương án disjoint được tính riêng:

- **Đã thực hiện hoặc được duyệt xóa hiện tại: 0B.** Đây là plan, không có safe-delete certificate/restore test trong nhiệm vụ này.
- **Phase1 bytecode tối đa 60,717,013B = 57.904 MiB** sau kiểm chứng. Chỉ có source-counterpart evidence, chưa chạy recovery/mutation.
- **Nếu còn được duyệt bỏ root env sau đó:** additional 6,874,295B, tổng bytecode + unique root-env remainder **67,591,308B = 64.460 MiB**. Không cộng cả13.145MB root env vào60.717MB pyc vì sẽ double-count6.271MB.
- **Archive subset upper footprint 290,994,443B = 277.514 MiB** độc lập về kịch bản; same-drive relocation0, off-drive copy0 đến khi local removal được phép; compression saving UNKNOWN vì chưa benchmark/pack. Không cộng vào savings low-risk.
- Chưa có automatic deletion allowance cho byte duplicates, .class, GP cache hoặc interrupted runs.

## Phase0 — Backup và kiểm chứng phục hồi

**Paths:** toàn current source/tests/config/untracked v3, protocols/sidecars, selected datasets+manifest metadata, seven v3 collections, v2 denominator closure, GP completed/incomplete/audit, forensic interrupted4/5, incident evidence, vendor source/lib/build/manifests, environment metadata. .git history cũng cần preservation; không manual prune.

**Lý do:** ignored runs chiếm~1.77GiB và không có trong Git clone; HEAD không chứa nhiều v3 source. Absolute paths/hashes ràng buộc original workspace.

**Tiên quyết:** approval backup destination/scope/storage capacity; xác nhận no-running-research-jobs bằng read-only process check ở nhiệm vụ được giao; không tự kill/suspend công việc. Lập dependency/protection index từ reports. Bản backup sealed nếu cần đọc bytes để sao lưu phải có quyền preservation riêng; audit hiện tại chỉ stat và không cấp quyền mở/test data. Không chạy loader/hash sealed để “verify backup”. Không đưa secrets vào archive tùy tiện.

**Bước đề xuất:** copy chứ không move vào destination ngoài active tree đã chọn; ghi approved inventory/hash list cho unsealed source/protected artifacts; environment distribution/runtime/compiler metadata và original path map. Restore thử các unsealed selected files vào scratch bên ngoài repo bằng đúng bytes; mô phỏng path resolution/reference checks có giới hạn, không chạy full study. Với absolute-path loader, không sửa records để dùng scratch; cần restore snapshot về original path trong môi trường cô lập hoặc một compatibility test được thiết kế riêng.

**Risk:** archive thiếu ignored/untracked, spare drive không đủ, checksum metadata không đủ cho payload, restore ở path khác bị hiểu nhầm là certificate fail, sealed scope creep.

**Saving:**0B; backup có thể cần thêm dung lượng.

**Acceptance:** backup đủ dependency closure, restore bytes match approved hashes, no sealed-content access, source/critical artifact state unchanged; có procedure khôi phục original paths/env. Chưa đủ thì không sang phase1.

**Rollback:** chưa xóa/move nên active tree nguyên; nếu backup thất bại giữ local, đánh dấu failed backup thay vì tiếp tục cleanup.

## Phase1 — Dọn bytecode có evidence an toàn

**Paths:** chỉ __pycache__/*.pyc đã inventory, gồm project114files/1092244B, rootenv447files/6271244B, mainenv2302files/53353525B. Không blanket remove cache directories nếu có file khác. Không đụng GP fitness/cache, model snapshots, build/lib classes, traces/logs hoặc directories protected.

**Tiên quyết:** phase0 restore PASS và approval danh sách chính xác; source .py counterpart vẫn tồn tại; confirm không job đang dùng/thay files; inspect preservation maps nếu bytecode thuộc snapshot cần retain. Current 2863pyc đều có source counterparts theo stat, chưa có proof all historical inventories bỏ qua chúng.

**Risk:** cold-start, package có implicit sourceless dependency (metadata hiện không thấy), external tooling, thay inventory archived snapshot. Không cam kết bytecode regenerates identical bytes khi source timestamp/path/compiler đổi; chỉ operational regeneration theo source.

**Saving:** tối đa 57.904 MiB, có thể thấp hơn nếu excluded preservation-bound files. Từ snapshot tổng giảm còn khoảng 1.838 GiB nếu mọi candidate được duyệt và report bytes bỏ qua.

**Acceptance:** deleted-only approved pyc list, không source/.env/sealed/experimental artifact mất, required imports có thể phục hồi trong bounded verification không simulation; critical byte hashes và original paths giữ nguyên.

**Rollback:** restore approved cache payload từ backup hoặc regenerate từ source bằng đúng interpreter trong nhiệm vụ cho phép; không rerun study để tạo cache. Nếu imports/provenance fail, restore trước khi làm phase khác.

**Optional1b root env:** only after user confirms external usage; archive dist-info/setup/package metadata, test recreation ngoài repo. Root env khác main nên chưa gọi redundant. Giữ dvrpsim/.venv bắt buộc. Saving additional 6.556 MiB sau pyc; rollback restore original .venv bytes/path, không chuyển CLI default interpreter.

## Phase2 — Documentation/navigation và nhãn history

**Paths:** root research notes, dvrpsim/README.md, dvrpsim/docs/README.md và docs/reports/dpdp/, docs/ai_handover/, docs/cleanup_audit/, compatibility stub DPDP_SCORING_AUDIT.md.

**Tiên quyết:** phase0 và scope docs-edit riêng; giữ historical report bytes nếu evidence pins; chỉ index/current guide mới/cập nhật được phép. Existing six handover không sửa trong cleanup audit này.

**Lý do/bước:** current landing page chỉ rõ one current workflow v3, status NO-GO, v2 reproduction, historical/forensic sections; dùng links, không copy toàn reports; đánh dấu stale status ở navigation thay vì rewrite dated artifact. Kiểm links relative giữa root/docs và dvrpsim/docs; giữ MkDocs/license/CI config.

**Risk:** thay source-report snapshots hoặc break old links; làm current draft trông như enabled protocol. **Saving:** gần0B, mục tiêu giảm confusion.

**Acceptance:** đọc landing page biết current CLI/contract/certification gates và protected paths; existing report/evidence hashes giữ nguyên; compatibility links còn resolve.

**Rollback:** restore các doc/index version từ phase0; không xóa old reports.

## Phase3 — Archive legacy experiments sau dependency review

**Paths candidates (không approved move):**

| Path | Size |
| --- | --- |
| `dvrpsim/gp_runs/scale100_diagnostic_20261109_r1` | 95.814 MiB |
| `dvrpsim/gp_runs/multinstance_50_20261105` | 27.377 MiB |
| `dvrpsim/gp_runs/delta_j_diagnostic_20261109_r1` | 16.760 MiB |
| `dvrpsim/gp_runs/c10_instance3_diagnostic_20261109_r1` | 10.174 MiB |
| `dvrpsim/gp_runs/smoke_test_measure_20261109` | 8.449 MiB |
| `dvrpsim/gp_runs/comparison_20261105` | 2.076 MiB |
| `dvrpsim/gp_runs/pilot_20261105_v2` | 1.977 MiB |
| `dvrpsim/gp_runs/pilot_20261105` | 0.244 MiB |
| `dvrpsim/gp_runs/demo_adapter_smoke` | 0.126 MiB |
| `dvrpsim/vnsme_runs/scale100_reference_20261109_r1` | 112.124 MiB |
| `dvrpsim/baseline_runs` | 0.969 MiB |
| `dvrpsim/dataset_runs` | 1.423 MiB |


**Tiên quyết:** phase0+2; map docs/tests/manifests/source-hash snapshots/external consumers; xác định preservation owner/retention; approve destination và liệu local copy có thể bỏ. Không gộp migration_runs vì năm denominator runs còn live dependency; không archive accepted v3/GP completed/incomplete hoặc interrupted forensic chỉ vì to. Interrupted4/5 **KEEP nguyên path lúc này**, riêng future forensic preservation review.

**Bước:** lựa subset thật sự detached, copy nguyên relative payload + dependency closure sang archive, verify/restore byte identity ở original paths trong isolation; nếu source Python scripts thuộc wide source_hashes thì giữ original hoặc defer đến refactor-compatible migration. Update navigation bằng archive location metadata trong nhiệm vụ cho phép, giữ original record immutable. Chỉ sau gates và approval riêng mới cân nhắc local removal. Không sửa summary/hashes cho qua checks.

**Risk:** path-sensitive records/cache/context, diagnostics dùng làm test fixtures/performance evidence, archived closure thiếu source/environment, archive same-drive không giúp storage.

**Saving:**0 cùng ổ hoặc backup-only; maximum local footprint277.514MiB cho whole listed subset chỉ nếu offload/restore và removal approved; chưa đo compression ratio và không guaranteed cả12paths đủ điều kiện.

**Acceptance:** each candidate có dependency map/retention approval, archive hash/restore report, no broken active consumers; all protected artifacts nguyên vị trí; no sealed read hoặc research rerun.

**Rollback:** restore exact original directory paths/bytes trước consumers; restore navigation/version map; không tái tạo bằng chạy training/simulation.

## Phase4 — Đơn giản hóa code/entrypoint (nhiệm vụ riêng)

**Paths:** root non-test CLI modules, digest/SIMULATION helpers trong v2, runner/evaluator/config, future logging, package docs.

**Tiên quyết:** source-changing task được giao riêng, certified baseline/protocol+hash-compatibility strategy, functional semantics invariants. Không dùng cleanup approval làm phép sửa Java search/scorer/features/constraints.

**Lý do/bước:** giảm public CLI navigation trước; cân nhắc shared helpers/config validation khi triển khai trainer v3, wrappers ở paths cũ; future runs không duplicate full stderr nếu logging contract mới được audit. Không merge independent oracle vào enforcement checker hoặc xóa v2 files đang import.

**Risk:** current/historical reference loaders check current code fingerprints, source rename/comment edit có thể làm audit fail; caches invalidate; Java build/code identity đổi.

**Saving:** source-space gần0; future output growth có thể giảm đáng kể nhưng chưa đo/không tính như recovered bytes.

**Acceptance:** separate code review/semantics tests, bounded synthetic no-sealed tests, current+historical provenance strategy, original artifacts unmodified. Không chạy official GP v3 khi reference/protocol/trainer chưa GO.

**Rollback:** isolated patch/worktree or archived source restoration theo task riêng; không reset/discard pre-existing dirty changes. Archive current source trước và retain original wrappers nếu cần.

## Phase5 — Regression, audit và provenance sau cleanup

**Paths:** protected collection inventory + code/protocol/build/data metadata, selected unsealed cache/import paths, archive restore map, docs links.

**Tiên quyết:** approved earlier-phase action log/diff, phase0 backup usable, bounded verification plan với sealed-open guard. Không chạy blanket unittest discover: có lịch sử đọc sealed qua verify_existing/test discovery.

**Bước:** compare pre/post counts theo exact approved changes, source/protocol/build manifest/artifact hashes; prove all seven v3 collections, five v2 denominator dependencies, completed/incomplete GP và incident evidence still available; read-only audit/load từ original paths nếu thuộc scope và budget được cấp, không simulation/search. Use focused synthetic tests chỉ sau kiểm call graph; unrelated full benchmark/training không cần thiết.

**Risk:** historical source fingerprint mismatch từ legitimate refactor, verifier vô tình chạy new simulation, test skip bị tính là PASS, sealed access incident lặp lại.

**Saving:**0 thêm; phase5 chứng minh savings đo thật và correctness còn nguyên.

**Acceptance:** chỉ approved deletions/moves/edits, exact protected bytes/path preserved hoặc verified relocation strategy riêng, expected loaders/audits PASS với phạm vi rõ ràng, zero sealed reads, không tuyên bố existing files là validity proof. Final storage report dùng actual logical+physical measurements, không cộng nested directory sizes.

**Rollback:** dừng cleanup ngay khi mismatch; restore approved affected paths từ snapshot; rerun bounded checks. Không sửa manifests/records để che mismatch, không dùng rerun research thay forensic recovery.

## Các quyết định cần người dùng phê duyệt trước thực hiện

1. Backup destination/retention/capacity và phạm vi preserved data (đặc biệt sealed preservation authorization riêng nếu cần).
2. Có cho phép phase1 candidate bytecode list sau restore checks hay không; project-only~1.04MiB hay cả hai environment caches~57.90MiB.
3. Root .venv còn được IDE/tool/user command nào dùng; có cho phép recreate-test và remove whole env sau đó không.
4. Có muốn offload historical subset nào ra ổ khác không; giữ local browse/load hay restore-on-demand; không đưa accepted/forensic runs vào tự động.
5. Có giao docs index/refactor/logging-portability riêng hay chỉ giữ kết quả audit này.

**Chưa thực hiện cleanup. Chờ người dùng phê duyệt kế hoạch cụ thể.** Không có terminal deletion/move command được chuẩn bị hoặc thực thi trong audit này.
