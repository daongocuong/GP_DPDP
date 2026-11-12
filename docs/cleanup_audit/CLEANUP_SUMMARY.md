# Cleanup audit summary — GP–DPDP

Ngày2026-11-10, Asia/Bangkok. **Chưa cleanup:** không xóa/move/rename, không sửa source/protocol/artifact, không commit/reset/clean, không training/simulation/Java search/test discovery; sealed7/8/15/16 chỉ stat metadata. Chỉ tạo7reports trong docs/cleanup_audit/.

## Kết quả chính

- Repository trước reports: **55,782 files, 5,828 directories gồm root, 2,034,035,362B = 1.894 GiB (2.034GB logical)**. Không phải allocated NTFS bytes; không có lỗi inventory/symlink.
- Git tracked7937files/83.046 MiB; untracked651files/19.260 MiB; ignored46663files/**1.769 GiB**; Git internals531files/25.588 MiB. Git clone không mang phần lớn result evidence.
- Source versions: HEAD0bd773291d5d9034f1e7b81688bc2dfaf87308c7, branch complete-gp-dpdp,9 modified tracked files + untracked v3 modules/tests/protocol/evidence đã có từ trước.

| Thư mục lớn | Size | Ý nghĩa |
| --- | --- | --- |
| dvrpsim/vnsme_runs | 994.360 MiB (1,042,662,395 B) | Accepted + interrupted + legacy; không blanket delete/archive |
| dvrpsim/gp_runs | 415.337 MiB (435,512,744 B) | Completed/incomplete studies + diagnostic/rollout/cache |
| dvrpsim/migration_runs | 249.436 MiB (261,552,889 B) | Năm v2 denominator runs vẫn được current trainer/default tham chiếu |
| dvrpsim/.venv | 135.935 MiB (142,538,180 B) | Main interpreter required; phần cache là candidate |
| dvrpsim/examples | 33.252 MiB (34,867,505 B) | DPDP runtime + optional upstream examples |
| dvrpsim/third_party | 26.178 MiB (27,449,855 B) | VNSME build/lib/source và Huawei snapshot |


## Giữ nguyên lúc này

1. **Bảy accepted VNSME v3 collections, 633.569 MiB**: instances2/3/recovery4, cả hai valid5 và cả hai valid6. Các record chứa absolute paths + artifact/source/build/protocol dependencies; giữ cả logs/copies ngoài map.
2. **V2 reference closure 164.812 MiB**: migration_runs/vnsme_reference/instance_2/3/4 và reference_retry_20261108_01/instance_5/6. Tên legacy/retry không nghĩa không còn dùng.
3. Completed GP v2 runs/selected trees/fitness/cache/audit, official incomplete generation0, interrupted historical4/5 forensic, sealed-read incident evidence, source/build/protocol/data/split manifests và traces/ledger/replay/supervision.
4. Source/tests/untracked v3, dataset nguyên bản/sealed, active nested venv, vendor original/lib/build và scoring reference. Không gọi supplied .class dependencies là cache rebuild được.

## Có thể cân nhắc dọn hoặc archive

- **DELETE_CANDIDATE có điều kiện:**2863 __pycache__/*.pyc, tổng**57.904 MiB**; tất cả có source .py counterpart theo stat. Chỉ sau backup/restore checks và approval, không có safe-delete certificate hiện tại.
- **REVIEW:** root .venv12.537 MiB (13,145,539 B); package versions khác main nên không equivalent. Nếu bỏ sau đã dọn pyc, chỉ thêm**6.556 MiB**, không double-count toàn env.
- **ARCHIVE_CANDIDATE:** selected legacy diagnostics/pilots/smoke/scale100 study/baseline_runs/dataset_runs subset12paths **277.514 MiB**. Cần dependency/restore map; không move trong audit. Same-drive relocation saving0.
- **REVIEW/KEEP:**1345 same-size Java stderr pairs, one-copy footprint370.063MiB; chỉ3pairs lớn nhất được hash-equal. Cả3nằm trong protected accepted runs → giữ. Bản duplicated stream là cơ hội giảm output **tương lai**, không automatic deletion của evidence cũ.
- **Không phải cơ hội lớn:** docs Markdown toàn repo0.574MiB, GP fitness/cache1.809MiB, Java project build0.143MiB. Giữ provenance quan trọng hơn dung lượng này.

## Tiết kiệm dự kiến

| Scenario | Logical savings |
| --- | --- |
| Đã thực hiện / được duyệt trong nhiệm vụ này | **0B** |
| Phase1 toàn bộ bytecode, sau xác minh/approval | tối đa**57.904MiB** |
| Bytecode + rootenv unique remainder, sau external-use/recreate checks riêng | tối đa**64.460MiB**, không cộng trùng |
| Chuyển archive cùng ổ hoặc copy giữ local | **0B** |
| Selected historical subset offload + được phép bỏ local sau restore test | upper local footprint**277.514MiB**, chưa bảo đảm đủ điều kiện |
| Exact byte duplicate evidence / compression | **0B approved**; chưa đo compression savings |

Không cộng archive estimate vào low-risk deletion saving hoặc đếm parent/child directories hai lần. Không chọn bỏ artifact theo điểm nghiên cứu tốt/xấu.

## Top10 opportunities theo lợi ích/rủi ro

| # | Opportunity | Benefit / size | Decision / risk |
| --- | --- | --- | --- |
| 1 | Python bytecode cache | 57.904MiB conditional recovery | DELETE_CANDIDATE sau phase0; low risk khi idle/source/preservation checks pass |
| 2 | Root .venv usage review | 12.536MiB whole; additional6.556MiB sau pyc | REVIEW external consumers/recreate; giữ main env |
| 3 | Future Java stderr single-stream/log retention design | Giảm tăng trưởng;388038880B candidate duplicate footprint hiện tại không được tính saving | Separate logging/audit task; KEEP old accepted logs |
| 4 | GP scale100 diagnostic archive | 95.814 MiB | C archive review, traces/reports linked, high provenance risk |
| 5 | VNSME scale100 historical study archive | 112.124 MiB | C archive review, performance/test evidence consumers |
| 6 | Legacy multinstance GP history archive | 27.377 MiB | C archive review; preserve selected tree/protocol/dependencies |
| 7 | Other legacy diagnostic/smoke/pilot bundles | Subset trong277.514MiB, không cộng lần nữa | Archive coherent study; không delete traces/cache riêng lẻ |
| 8 | Original supplied VNSME package external preservation | 12.918 MiB (13,545,151 B) | KEEP lúc này; byte duplicates active copy nhưng provenance khác |
| 9 | Optional non-DPDP upstream examples | rmdp/data/180_2.txt30.551MiB | Archive tùy scope đồ án; example vẫn tham chiếu, không unused |
| 10 | Current workflow/documentation index | Storage gần0; giảm14CLI/version confusion | Docs-only separate task; giữ reports/redirects/evidence |


## Quyết định cần người dùng phê duyệt

- Backup destination/retention/restore approach; preservation scope riêng cho sealed nếu cần sao lưu bytes.
- Phase1 project-only cache~1.04MiB hay toàn environments~57.90MiB, sau backup checks.
- Root .venv có external consumer không và có được phép recreate-test/remove sau đó không.
- Historical subset nào được offload sang ổ khác; retention và restore-on-demand có chấp nhận được không.
- Có giao docs-navigation/refactor/portable manifests/future logging như nhiệm vụ riêng hay không.

## Trình tự an toàn

Phase0 backup+restore validation → Phase1 approved cache-only candidates → Phase2 current docs index/historical labels → Phase3 dependency-mapped archive → Phase4 separately approved code/entrypoint/logging refactor → Phase5 bounded regression/hash/provenance/audit checks. No blanket unittest discover, sealed reads hoặc research reruns để chứng minh cleanup an toàn. Mismatch thì restore original bytes/paths, không sửa record/hash để qua audit.

**Chưa thực hiện cleanup. Chờ người dùng phê duyệt kế hoạch cụ thể.**

## Reports

- REPOSITORY_INVENTORY.md: total, Git/extension/family stats,30largest files/directories, growth proxies.
- FILE_CLASSIFICATION.md: A–F rules/tallies, group-level size/dependencies/Git/regeneration/risk/action, critical closure.
- DUPLICATES_AND_REDUNDANCY.md: exact/same-size/semantic/obsolete/unused distinction, selective hash results và duplicates index.
- DEPENDENCY_RISKS.md: import/CLI/manifest/classpath/absolute-path/hash dependencies và unresolved reference scope.
- PROPOSED_STRUCTURE.md: minimal current layout + logical catalog, future archive/portability constraints.
- CLEANUP_PLAN.md: savings table, phase0–5 scope/prerequisites/risk/acceptance/rollback.
- CLEANUP_SUMMARY.md: tài liệu này.
