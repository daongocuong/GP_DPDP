# Cấu trúc đề xuất và phạm vi đơn giản hóa

Ngày2026-11-10. Chỉ là thiết kế, không rename/move/refactor hay thay protocol. Mục tiêu giảm số workflow người dùng phải nhớ và giảm tăng trưởng outputs, giữ nguyên evidence paths/hashes.

## Đánh giá quy mô

Repository logical 1.894 GiB,55782 files. Root dvrpsim44 Python files nhưng18 là tests;26 non-test có14 entrypoints do xen core utilities, GP pilot/v2, dataset/build và historical wrappers. Nhiều version protocols phản ánh semantic evolution, không đơn thuần duplicated code. Source không phải bottleneck storage: vnsme_runs+gp_runs+migration_runs chiếm 1659.134 MiB (85.5% total). Documentation .md toàn repo chỉ 0.574 MiB.

**Kết luận:** quá phức tạp ở navigation/version/status và output lifecycle so với một đồ án, nhưng không có bằng chứng cần xóa hàng loạt modules hoặc viết lại core. Giảm CLI người dùng phải tiếp xúc bằng current workflow guide/catalog là thay đổi nhỏ hơn di chuyển code. Giữ independent checker/replay/scorer riêng để tránh mất kiểm chứng khoa học.

## Stage A: cấu trúc tối thiểu giữ nguyên paths

~~~text
LA/
  .git/                           # giữ Git history, không manual cleanup
  .venv/                          # REVIEW external usage, không xóa hiện tại
  VNSME/                          # original supplied package, provenance
  *.pdf, research notes           # nguồn nghiên cứu, giữ
  docs/
    ai_handover/                  # current context: 6 docs có sẵn
    cleanup_audit/                # 7 reports của nhiệm vụ hiện tại
  dvrpsim/
    .venv/                        # required current interpreter
    src/dvrpsim/                  # core simulation (giữ)
    src/baselines/vnsme.py         # baseline adapter (giữ)
    examples/case_studies/dpdp/    # active builder/loader/routing (giữ)
    dpdp_*.py                     # GP/candidate/check/contract/eval/audit
    run_dpdp_insertion.py          # shared runner; explicit v3 contract
    train_dpdp_gp*.py              # pilot/v2; chưa có certified v3 trainer
    build/prepare/verify tools    # giữ vị trí; phân loại trong guide
    test_*.py                     # tests cùng vị trí để discovery/import không đổi
    datasets/xingtian/<commit>/   # pinned data + split/source metadata; sealed untouched
    protocols/                    # immutable versioned descriptors/sidecars
    third_party/vnsme/            # source/lib/build/manifests, giữ nguyên
    scoring_reference/            # historic objective provenance
    gp_runs/                      # old + new study outputs, không move accepted studies
    vnsme_runs/                   # accepted/interrupted runs tại original paths
    migration_runs/               # v2 denominator closure vẫn cần
    baseline_runs/, dataset_runs/ # archive candidates, chưa move
    *_evidence/                   # accepted/audit/incident/preservation artifacts
    docs/                         # upstream tutorials + historical DPDP reports
~~~

Các chức năng người dùng cần (core simulation, GP, baseline, data, protocols, tests, active outputs, certified evidence, history, docs) đều ánh xạ được vào cấu trúc hiện có. Không cần tạo package hierarchy mới chỉ để có tên thư mục đẹp.

## Stage B: tổ chức bằng catalog thay cho di chuyển ngay

Trong nhiệm vụ documentation riêng được phê duyệt, cập nhật một landing index trỏ rõ:

| View | Existing paths | Quy tắc |
| --- | --- | --- |
| CURRENT_METHOD | core modules, v3 contract, split, draft fitness | Nêu trainer v3 chưa enabled; v2 defaults không được dùng ngầm |
| ACTIVE_STUDY | gp_runs/<new-study>, vnsme_runs/<new-study> do CLI --output chỉ định | Chỉ run mới; không rename old study |
| CERTIFIED_REFERENCES | bảy accepted v3 collection paths + canonical decision sau này | Pointer/index metadata, không copy/move/dedup payload |
| LEGACY_V2_REPRODUCTION | migration_runs/vnsme_reference_ready và năm row dependencies; completed v2 GP | Read-only preserved; vẫn audit tại original paths |
| FORENSIC_HISTORY | interrupted4/5, scale100 diagnostics, incident evidence | Không bỏ vì không thuộc current train; đọc reports trước logs |
| DOCUMENTATION | docs/ai_handover, dvrpsim/docs/reports/dpdp, tutorials | Current status tách khỏi dated historical reports; giữ compatibility links |

Index tương lai cần chỉ rõ last-verified timestamp, version, state, size, evidence references; không duplicate hết nội dung sáu handover trong README. Không tạo index ngoài bảy reports ở nhiệm vụ này.

## Stage C: archive có dependency map và restore path

Historical archive logic có thể tách khỏi active workspace **sau** backup/restore test, không mặc định chuyển vào LA/archive rồi gọi tiết kiệm:

~~~text
<separate-approved-archive-volume>/GP-DPDP/<snapshot-id>/
  original-relative-tree/...      # giữ nguyên byte payload
  archive-index                  # expected hash, original absolute + relative path
  dependency-map                 # source/protocol/build/env/evidence closure
  restore-instructions           # original LA paths cần có cho current loaders
~~~

Đây là cấu trúc tương lai, chưa tạo archive/index hay file ngoài7reports. Move cùng ổ có savings0; copy ra ổ khác vẫn0 cho đến khi local copy được phép bỏ; compressed archive saving chưa đo. Không archive accepted v3/v2 closure hay completed/incomplete GP làm mất khả năng load hiện tại. Với archive C, original records không được sửa paths/hashes cho qua loader. Muốn đọc trực tiếp archive bằng path mapping cần loader support riêng; hiện phải restore đúng paths trước load.

Archive scope đầu tiên để đánh giá: legacy GP diagnostics/pilots/smoke, old scale100 failed/reference study, baseline_runs và dataset_runs; tổng subset 277.514 MiB. Có references trong docs/evidence/source-hash inventories nên đây là boundary cho review, không lệnh chuyển.

## Có thể hợp nhất gì và không nên hợp nhất gì

- **Có thể đơn giản hóa:** navigation/readme/index, config validation trong trainer v3 mới, helper dùng chung digest/SIMULATION sau refactor riêng, một cách đặt tên new-study outputs, logging policy cho future runs, catalog state current/legacy/forensic.
- **Giữ độc lập:** candidate feasibility, schedule forecast, tree evaluation, execution ledger và independent replay/scorer. Chúng có nhiệm vụ/scientific assumptions khác nhau; merge chỉ để giảm file count sẽ làm review khó hơn.
- **Không xóa version protocols:** chỉ11,788B/10files, trong khi historical results pin exact bytes/hash; gom vào một config mutable làm mất traceability.
- **Không sửa source paths ngay:** code hashes và dynamic import setup đang bind locations; refactor thay layout buộc compatibility decision cho reference validation và cache.
- **Không bỏ all upstream examples ngay:** DPDP examples là runtime, rmdp180_2.txt32MB được example code gọi, tutorials/docs dùng upstream model API. Non-DPDP là optional archive package nếu người dùng chọn chỉ giữ GP workspace sau preservation.
- **Không hợp nhất reports bằng overwrite:** dvrpsim/DPDP_SCORING_AUDIT.md là link shim; dated reports ghi methods/version lúc thực chạy. Current index cảnh báo status cũ là đủ.

## Thành phần tối thiểu thật sự cho GP v3

VERIFIED cần: core simulator/DPDP builder/loader, sealed guard + dataset metadata/inputs development, feasibility/forecast/insertion, GP AST/ranker/operators, execution contract/trace, common runner, scorer/independent audit, certified VNSME records + build/lib/source/protocol/env, reference_v3 và offline fitness_v3. V3 reference còn import v2 utility modules, nên giữ chúng cho tới refactor có chứng nhận.

UNKNOWN/chưa xong: canonical combined denominator2–6, active frozen training protocol v3, trainer/evaluator/cache v3 execution loop. Cleanup không giải quyết bằng xóa denominator cũ/đổi enabled flag. Bước nghiên cứu kế tiếp vẫn là canonical reference selection/assembly, rồi protocol/trainer enablement.

## Phạm vi nhiệm vụ refactor riêng nếu được giao sau này

1. Review import/CLI/config coupling và source-fingerprint compatibility trước khi đổi code.
2. Cung cấp adapters/compatibility wrappers tại original import/CLI paths, nếu có migration.
3. Dùng synthetic/bounded checks, không test discovery đọc sealed hoặc chạy benchmark để kiểm refactor.
4. Quyết định làm sao historical audits vẫn resolve original source bytes: archived source environment thay vì chỉnh record.
5. Approval source-changing task riêng; acceptance phải gồm no semantic change của J/features/feasibility/contract/Java objective, current baseline parity và rollback archive.

Không có việc nào ở StageB/C/refactor đã được thực hiện trong audit này.
