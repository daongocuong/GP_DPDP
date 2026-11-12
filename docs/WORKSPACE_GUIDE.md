# GP–DPDP — Workspace Guide

Quy tắc làm việc từ ngày **2026-11-10**. [PROJECT_HOME.md](PROJECT_HOME.md) là nơi duy nhất cập nhật trạng thái công việc hiện hành. Trang này mô tả vận hành và **chính sách đề xuất cho công việc tương lai**, không thay source, CLI defaults, artifact schema hoặc protocol đã khóa.

## Bản đồ thư mục

Đường dẫn dưới đây tương đối với `C:/Users/Cuongdz/Documents/LA`.

| Thư mục / nhóm | Nội dung và cách dùng |
| --- | --- |
| `dvrpsim/src/dvrpsim/`, `examples/case_studies/dpdp/` bên trong `dvrpsim/` | Simulator và DPDP builder/loader/routing đang được runner import; không chỉ là examples có thể bỏ. |
| `dvrpsim/dpdp_*.py`, `run_dpdp_insertion.py`, `src/baselines/vnsme.py` bên trong `dvrpsim/` | GP/candidate/features/checker/forecast/contract/audit/fitness và runner/adapter. Phân biệt role/version theo Project Home. |
| `dvrpsim/test_*.py`, `dpdp_audit_fixtures.py` bên trong `dvrpsim/` | Tests/fixtures; kiểm scope trước khi chạy, không blanket discovery. |
| `dvrpsim/protocols/`, `datasets/xingtian/<commit>/` | Versioned split/contract/fitness descriptors, sidecars và pinned data/source manifest. Sealed chỉ đọc metadata được phép, không nội dung data. |
| `VNSME/`, `dvrpsim/third_party/vnsme/`, `dvrpsim/scoring_reference/` | Original supplied package, active Java source/lib/build/provenance và scoring reference. Supplied dependency `.class` không có nghĩa là cache tái tạo được. |
| `dvrpsim/gp_runs/`, `dvrpsim/vnsme_runs/` | Chứa cả accepted/current/legacy/incomplete runs. Phân loại bằng contract/manifest/evidence, không bằng tên parent directory. Phần lớn bị Git ignore. |
| `dvrpsim/gp_evidence/`, `vnsme_evidence/`, `reference_completion_evidence/` và các `*_evidence/` khác bên trong `dvrpsim/` | Audit, replay, supervision, preservation, incident và reports. Có fixtures hoặc scripts được source-hash inventory/tests tham chiếu. |
| `dvrpsim/migration_runs/`, `baseline_runs/`, `dataset_runs/` bên trong `dvrpsim/` | Migration/v2/Greedy/calibration lịch sử; riêng migration còn chứa denominator dependencies của trainer v2. Không mặc định toàn bộ đều archive được. |
| `docs/ai_handover/`, `docs/cleanup_audit/`, `dvrpsim/docs/reports/dpdp/` | Snapshot bàn giao/kiểm toán và báo cáo nghiên cứu theo giai đoạn. Giữ nguyên, điều hướng qua Project Home thay vì sao chép. |
| `dvrpsim/.venv/` và root `.venv/` | Nested environment là interpreter CLI yêu cầu; root environment khác packages, external usage chưa rõ. Không thay thế/xóa một environment chỉ vì có hai thư mục. |

Không có physical `archive/` mới được tạo. “Historical” là nhãn quản lý, không phải quyết định di chuyển file. Xem [inventory](cleanup_audit/REPOSITORY_INVENTORY.md) và [dependency map](cleanup_audit/DEPENDENCY_RISKS.md) cho chi tiết.

## Protected paths: giữ nguyên bytes và vị trí

Không xóa, move, rename, nén rồi bỏ bản gốc hoặc overwrite các nhóm sau:

- Toàn bộ **bảy accepted VNSME v3 collections**: 2, 3, recovery 4, cả hai valid 5 và cả hai valid 6; danh sách chính xác ở [CURRENT_STATUS](ai_handover/CURRENT_STATUS.md#vnsme-v3--kết-quả-audit-trực-tiếp).
- `dvrpsim/migration_runs/vnsme_reference_ready/summary.json` và năm run được trỏ tới: `vnsme_reference/instance_2`, `instance_3`, `instance_4`; `reference_retry_20261108_01/instance_5`, `instance_6` trong `migration_runs/`.
- Completed GP v2 studies/selected tree/candidates/fitness/cache/rollouts/audit; `gp_runs/official_gp_multinstance_20261109` dù incomplete; interrupted historical runs 4/5 có forensic value.
- Manifests, saved decision/physical traces, ledgers, replay/scorer/supervision artifacts, Java per-epoch/private-solution snapshots, sealed-test incident evidence.
- Source/tests/protocol v3 chưa nằm trong HEAD, dù staged hay untracked; dirty tracked files, source/data/build/protocol manifests và sidecars; pinned dataset/split; vendor original/lib/build và Git history. Không chỉnh index hoặc tự commit phần staged có sẵn.

Records có **absolute paths**; current audits/cache còn bind source/build/protocol hashes. Di chuyển hoặc sửa source dù không đổi semantics vẫn có thể làm kiểm tra provenance fail. Module tên v2 vẫn được v3 import helper; không xóa theo version label. Xem [FILE_CLASSIFICATION](cleanup_audit/FILE_CLASSIFICATION.md) trước mọi đề xuất khác.

## Backup có thể phục hồi — đề xuất, chưa thực hiện

**Không thể phục hồi chỉ bằng Git HEAD:** 9 tracked modifications, các source/tests/protocol/evidence/docs mới chưa commit, cả phần staged và untracked; ignored GP/VNSME/migration outputs/logs/build/environment. Kiểm tra cuối quan sát staging thay đổi trong khi HEAD không đổi; xem Project Home. Một Git patch đơn lẻ không chứa đủ untracked/ignored payload, và staged index không thay thế backup.

Phương án chờ phê duyệt: một snapshot **ngoài active repository, ưu tiên ổ lưu trữ khác** với snapshot ID duy nhất; copy giữ original relative tree, không move local. Cần người dùng chọn destination, dung lượng, retention và phạm vi trước khi tạo backup lớn. Không có backup/archive/script/manifest mới nào được tạo bởi nhiệm vụ này.

Phạm vi tối thiểu cho snapshot có thể phục hồi:

1. Git history/HEAD/index metadata cùng **actual working-tree source bytes**, tests/config/docs, dirty/staged/untracked v3 files; không chỉ diff hoặc clone.
2. Protocols/sidecars, source/data/split/build/provenance manifests; vendor source, dependency libraries và exact compiled outputs của reference.
3. Tất cả protected collections và transitive dependencies nêu trên, gồm GP cache/models/rollouts, v2 denominators, interrupted/incident evidence và per-epoch traces/logs. Summary một mình không thay payload.
4. Dữ liệu development và môi trường phục hồi được: Python/package/compiler/runtime versions, initial-location/config metadata, environment setup/dependency artifacts nếu có. Để bảo đảm exact runtime, chọn backup environment hoặc kiểm recreate trong phạm vi được duyệt; không tự giả định reinstall giống bytes.
5. Inventory/checksums được duyệt, bản đồ original absolute paths, restore instructions và kết quả restore test **trong snapshot backup tương lai**. Không thêm các file này vào repo trong nhiệm vụ chỉ tạo hai docs.

Sealed 7/8/15/16 **không được đọc/hash/loader-test trong nhiệm vụ này**. Nếu backup toàn dữ liệu sealed cần sao chép bytes, phải có phê duyệt preservation riêng và cơ chế không mở data để phân tích; không lấy permission backup làm quyền final evaluation. Không đọc hoặc đưa secrets/credentials vào package một cách tự động.

Acceptance backup: xác nhận đủ ignored/untracked dependency closure, kiểm checksum các payload unsealed được duyệt, phục hồi thử trong môi trường cô lập có **đúng original absolute paths** và kiểm read-only loader/audit theo scope/budget riêng. Không sửa record paths/hashes cho qua và không chạy study mới để thay dữ liệu đã mất. Không tuyên bố “đã backup” trước khi có snapshot ID/location, inventory và restore evidence. Chi tiết phase 0/rollback: [CLEANUP_PLAN](cleanup_audit/CLEANUP_PLAN.md).

## Quy tắc đặt tên và một output root

Áp dụng cho **run mới**; giữ nguyên tên/path lịch sử. Mẫu đề xuất:

```text
<method>-<contract>-<purpose>-<scope>-s<seed>-<YYYYMMDDTHHMMSS+0700>-a<NN>
vnsme-cv3-reference-i05-s0-20261110T210000+0700-a01
gp-cv3-smoke-train02to05-s20261110-20261110T211500+0700-a01
```

Ví dụ GP là **quy tắc tên cho tương lai**, không phải run/trainer v3 đã có hoặc được phép chạy. Timestamp dùng Asia/Bangkok, seed/scope phải là giá trị thực; thêm attempt ID tránh collision. Không dùng `final`, `final2`, `recovery_final` làm định danh. “Accepted/reference” là trạng thái có audit, không phải kết luận từ tên folder.

- Mỗi experiment có **một output root mới**, dùng `--output` sẵn có, trong `dvrpsim/gp_runs/<id>/` hoặc `dvrpsim/vnsme_runs/<id>/`; GP models/cache/rollouts/generations là children của root đó theo writer hiện hành.
- Với reference collection, một instance/attempt là một unit; study nhiều instance có thể dùng study root với instance children khi CLI hiện tại hỗ trợ, không sửa layout để ép giống nhau. Combined-summary collection có root riêng và chỉ tham chiếu original runs, không sao chép payload.
- Không tạo thêm parallel `*_evidence/<id>` hoặc process-log copy tự phát. Dùng các evidence/log locations writer đã hỗ trợ trong output root; nếu công cụ hiện tại bắt buộc external evidence root thì ghi ngoại lệ/path ở Project Home và **giữ compatibility**, không chỉnh writer hoặc move artifact để ép quy tắc.
- Attempt mới phải có root mới; không overwrite/resume bằng cách nối logs. Giữ attempt cũ, lý do retry và parent/reference pointer trong metadata schema đã hỗ trợ hoặc sổ công việc, không tự thêm JSON fields vào record đã accepted.
- Trước khi chạy: xác định scope/version/inputs/budget/seed/output root và run type; kiểm có quyền chạy từ nhiệm vụ hiện tại. Tên folder không thay các manifest pins.

## Artifact schema: theo writer thực tế

Không ép mọi layer có `manifest.json` hoặc `result.json` cùng tên. Root collection, runner và trainer hiện có schema khác nhau:

| Unit hiện có | Artifact locations thực tế |
| --- | --- |
| Runner `run_dpdp_insertion.py` | `<output>/manifest.json`, `result.json`, `simulation.log`, `decisions.json`; v3 thêm `commitments.json`, `decision_trace.jsonl`. Lỗi có thể có `failure.json`; initialization failure có thể thiếu artifact cuối. |
| VNSME dưới runner | `<output>/vnsme/session.json`, private exchange/solution và `epochs/<NNNNN>/` với I/O/invocation artifacts. Traced v3 có start/process-end markers và live stdout/stderr. |
| Certified reference collection v3 | `<collection>/protocol_manifest.json`, `run/` chứa runner artifacts, `supervisor/{supervision.json,heartbeats.jsonl,process.log}`, `record.json` sau khi audit thành công. Không tự fabricate record cho failed run. |
| Reference assembly v3 | `<new-output>/summary.json` pin/point đến các existing records/runs; không duplicate run payload hoặc tự thêm root result/manifest mới. |
| GP training **v2 hiện có** | `experiment_protocol.json`, `generation_<n>.json`, `candidates.json`, `selected_tree.json` khi eligible, `training.json`; `fitness/{cache,models,rollouts}/` với runner outputs. Đây không phải schema certified của trainer v3 chưa hoàn thiện. |

Manifest/config và result/evidence phải truy về run ID, input/source/protocol/contract/seed/budget thực qua schema writer. Thiếu artifact thì ghi INCOMPLETE/UNVERIFIED, không tạo placeholder PASS. Không tạo thêm root log/report chỉ để đủ checklist khi logs đã nằm trong `run/` hoặc `supervisor/`.

**Không sửa logging/schema** hoặc cắt/truncate existing log trước khi có compatibility plan, loader/audit consumers inventory, versioned writer change, focused tests và approval riêng. Không xóa bản stderr trùng bytes trong accepted run. Sources: [runner](../dvrpsim/run_dpdp_insertion.py), [reference v3](../dvrpsim/dpdp_vnsme_reference_v3.py), [trainer v2](../dvrpsim/train_dpdp_gp_multinstance.py), [duplicate analysis](cleanup_audit/DUPLICATES_AND_REDUNDANCY.md).

## Báo cáo và retention để giảm file phát sinh

| Loại | Chính sách đề xuất |
| --- | --- |
| Accepted/reference, cited result, protocol-decision hoặc incident/forensic evidence | Giữ toàn bộ; không auto-expire/delete/dedup/move. Archive hoặc relocation cần scope/phê duyệt, dependency/restore plan riêng. |
| Diagnostic/smoke mới, chưa dùng cho quyết định/claim | Default **review sau 14 ngày**, giữ ít nhất tới khi task liên quan đóng. Review để retain/archive/propose deletion, **không auto-delete**. Nếu được dùng làm reference/fixture/decision evidence thì nâng lên protected, bỏ lịch expiry. |
| Failed/interrupted attempt mới | Giữ đầy đủ đến root-cause/next-attempt acceptance và review; có forensic value thì protected. Không xóa vì incomplete. |
| Logs/cache trong study | Theo retention của study, không dọn riêng GP fitness cache/traces. Python bytecode cleanup là nhiệm vụ riêng có approval/backup, không gắn vào run launch. |

- Không tự tạo Markdown report cho mỗi smoke/diagnostic nhỏ. Dùng machine artifacts có sẵn và một dòng/sửa dòng task ở Project Home.
- Chỉ tạo một report cho milestone/study khi task yêu cầu hoặc cần quyết định khoa học; đặt trong output root bằng tên report hiện có nếu workflow hỗ trợ, hoặc dùng path được task cho phép. Không tự tạo thêm `SUMMARY`, `STATUS`, `REPORT_final*` song song.
- Không tạo script/probe/dump/temporary report trong source/evidence roots khi chưa cần. Ưu tiên kiểm tra read-only trong bộ nhớ; scratch nếu được phép thì ở temp ngoài repo và chỉ chứa unsealed/non-sensitive input.
- Không thêm run outputs vào Git để “backup nhanh”; quản lý backup riêng, source/commit approval riêng. Giữ source và protocol snapshots có provenance; không rewrite historical reports để phù hợp current status.

## Ghi trạng thái không phát sinh nhiều status files

Chỉ cập nhật [sổ công việc trong PROJECT_HOME](PROJECT_HOME.md#sổ-công-việc-duy-nhất). Mỗi task một dòng có ngày/múi giờ, scope, state (PLANNED/RUNNING/INCOMPLETE/BLOCKED/ACCEPTED), evidence pointer, blocker/next action. RUNNING phải có evidence tiến trình hiện tại; ACCEPTED phải có audit/loader outcome đủ phạm vi. Không lấy tên folder hoặc note cũ làm trạng thái.

Khi task xong, cập nhật dòng cũ và trỏ tới immutable run/artifact; không tạo status file mới mỗi lần đổi hướng. Bảng trạng thái nghiên cứu ở Project Home được cập nhật trong nhiệm vụ cho phép; các bảng audit/handover cũ giữ nguyên như snapshots. Guide này chỉ sửa khi quy tắc vận hành thay đổi có chủ đích.

Mọi chạy thí nghiệm, tạo backup lớn, sửa code/protocol/logging schema, archive/cleanup hoặc commit phải thuộc scope được người dùng giao. Việc tạo hai trang điều hướng hiện tại không cấp các quyền đó.
