# Kiến trúc thực tế và điểm vào

Audit 2026-11-10, Asia/Bangkok. Tất cả đường dẫn trong các bảng dưới tương đối với `C:/Users/Cuongdz/Documents/LA/dvrpsim/`. Các symbol được trực tiếp đọc; không suy ra từ README cũ.

## Filesystem và môi trường

Git root là `LA/`, không phải `dvrpsim/`. Root có `.git`, `.venv`, `dvrpsim`, `VNSME` (gói Java gốc), các ghi chú nghiên cứu và hai paper PDF (không phân tích trong audit này). `dvrpsim/` có `src`, `examples`, `third_party`, `protocols`, `datasets`, `gp_runs`, `vnsme_runs`, `migration_runs`, `baseline_runs`, `dataset_runs`, các thư mục evidence, test Python và docs/reports. Handover nằm ở `LA/docs/ai_handover/` theo yêu cầu, tách khỏi `dvrpsim/docs/` có sẵn.

**VERIFIED:** Python hai venv root và `dvrpsim/.venv` đều 3.14.4; entrypoint yêu cầu đúng `dvrpsim/.venv/Scripts/python.exe`. Lệnh `python` trên PATH không chạy được trong session audit; phải dùng đường dẫn venv. Java OpenJDK 26.0.1+8-34. `pyproject.toml` khai Python >=3.8, package dvrpsim 0.0.1, dependency `simpy`; môi trường hiện có SimPy 4.1.2. Annotation `Visit | None` và `float | None` trong code mới cần Python >=3.10, nên metadata >=3.8 không mô tả đúng toàn bộ extension hiện tại. Không thấy lockfile dependency trong inventory đã kiểm tra; không cài/nâng cấp gói. Nguồn: `pyproject.toml`, `dpdp_feasibility.py`, kiểm tra `--version`/`importlib.metadata`, manifests của các run v3.

Java nhập 10 file source vào `third_party/vnsme/original`, class phụ thuộc ở `lib`, compile output `build`, provenance/build manifest tại cùng thư mục. Không Maven/Gradle. `build_vnsme.py` compile unchanged source với `--release 8`; audit này không build lại. Nguồn: `third_party/vnsme/README.md`, `build_vnsme.py`.

## Module map

| Module / symbol | Input → output, trách nhiệm | Phụ thuộc và điểm cần chú ý |
|---|---|---|
| `dpdp_dataset.py:resolve_inputs, validate_instance, rows` | Instance directory/common CSV → đường dẫn, inventory/validation | Guard sealed; schema, quantity, thời gian, network. `--instance` legacy chỉ 1/17; benchmark mới dùng directory |
| `prepare_dpdp_data.py:acquire, verify_existing` | Upstream pinned commit hoặc dataset local → source manifest/checks | Acquire có network/write, không chạy trong audit; verify hiện skip sealed bytes và loader; metadata sealed là lịch sử |
| `examples/case_studies/dpdp/dpdp_problemdata.py:read_dpdp_problem` | Factory/route/vehicle/order CSV → locations/items/vehicles/travel data | Split quantity thành item; due qua midnight +86400; seed initial locations; entry guard mọi input |
| `examples/case_studies/dpdp/dpdp_main.py:DPDPModel, DPDPVehicle, build_dpdp_model` | Problem data → model/event processes | `src/dvrpsim/`, SimPy, order provider, updater 600s, LIFO, port Resource, arrival completion |
| `src/dvrpsim/model.py:Model`, `elements/vehicle.py:Vehicle` | Events/raw routing decisions → trajectory | Thực thi state, capacity/loading/service; `utils/checker.py`, environment priorities ảnh hưởng FCFS/ties |
| `dpdp_schedule.py:predict_fixed_routes` | Live model + routes hiện tại → per-vehicle schedule rows | Heap FCFS, reserve ports ongoing service; không có future requests/new routing; equal-arrival tie theo vehicle order |
| `dpdp_feasibility.py:Item, Visit, VehicleState, Plan, validate` | Snapshot item/fleet/plans/delivered/full demands → True hoặc `Infeasible(rule,...)` | Không import simulator; Decimal capacity; complete remaining service, LIFO, uniqueness, precedence, conditional split, locks; deadlines soft |
| `dpdp_insertion.py:Snapshot` | Model quan sát được → item/fleet/route snapshot + metrics | Chỉ `model.orders` đã release; `forecast` tạo proxy, không step simulator; `check` gọi validator |
| `dpdp_insertion.py:split_observed_orders, candidates, extract_features, min_residual` | Snapshot/groups/current plans → candidate objects/features | EDD/release/ID, next-fit items; hai visit riêng; guard toàn fleet trước forecast; delta metrics toàn fleet |
| `dpdp_insertion.py:InsertionPolicy.decide` | Live model + explicit ranker → raw vehicles/orders decision + stats | Minimize rank; tie `(vehicle,pickup_index,delivery_index)`; defer nếu không candidate; không fallback |
| `dpdp_gp.py:Node, TreeRanker, validate_tree, breed` | AST/features/RNG/population → score hoặc thế hệ AST mới | Whitelist 5 features, 4 primitive; schema/hash, numeric policy, caps; chỉ xếp hạng, không đọc simulator/file/instance |
| `dpdp_contract.py:ExecutionCommitment, plans_from_raw, contract_metadata` | Snapshot/raw decision → ledger pending/tentative/committed/delivered | Check/record/finish; nghĩa vụ service không đảo; v3 opt-in, descriptor checksum; không tạo route thay Java |
| `run_dpdp_insertion.py:RunModel, guard_raw_decision, manifest, main` | CLI policy/input/tree/budgets → simulation.log, manifest/result/decisions/commitments/trace | Shared builder, guard trước enforce, completion rồi scorer; output mới; v2 mặc định; ghi code/data/package fingerprints |
| `src/baselines/vnsme.py:JavaSession` | Huawei state JSON → Java output_route/output_destination | Private CWD, copies data, persistent solution, epochs/process markers, 600s deadline capped remaining budget; invalid nếu Java/schema lỗi |
| `src/baselines/vnsme.py:huawei_state, VNSMEPolicy` | Model → integer epoch Huawei input → raw simulator decision | V_1..V_n, PALLET/HALF_PALLET/BOX; host midnight offset; reject unknown/future items/changed lock; v2 drop guard hoặc v3 contract |
| `third_party/vnsme/original/main_algorithm.java:main, variableNeighbourhoodSearch` | File state/private previous solution → optimized plan/publication | Dispatch/redispatch, pair exchange, block exchange/relocate, multi-PD relocate, 2-opt; wall-time stop; merge/delay publication |
| `verify_dpdp_score.py:verify, aggregate_score` | Local trajectory log + input CSV → Decimal D/T/J, validity | Đủ item/exact-once completion, log travel checks, arrival-based J; bản thân scorer không chứng minh LIFO/capacity hay dynamics Huawei |
| `dpdp_gp_fitness.py:RolloutEvaluator, cache_key, assess_result` | Tree/instance/context → raw J hoặc invalid record; cache/models/rollouts | **V2/legacy evaluator**, subprocess deadline, normalized reference pin; không truyền v3 contract; invalid penalty 1e15 |
| `train_dpdp_gp.py` | Pilot config → raw-J GP pilot | Lịch sử, khác normalized multi-instance workflow |
| `train_dpdp_gp_multinstance.py:load_locked, aggregate_training, validation_key, run_experiment` | Locked split + v2 reference + seed/config → generation/candidate/selected tree/training JSON | Chỉ 50-order; train 2–5, select validation 6; imports v2 loader; chưa là trainer v3 |
| `dpdp_vnsme_reference.py:load_reference` | V2 denominator summary → scores/metadata | Historical accepted-route-v2 contract, không thay thế loader v3 |
| `dpdp_vnsme_reference_v3.py:metadata, audit_run, audit_vnsme_run, load_reference, run_reference` | Saved/new explicitly requested v3 runs → audited records/summary | Metadata allowlist; rehash, replay, rescore, supervision/build/source checks; run/assemble ghi file, audit/load chỉ đọc |
| `dpdp_gp_fitness_v3.py:evaluate` | V3 reference + same-tree audited GP runs + train/val sets → ratios/train fitness | **Offline only**, không evolve/execute; compare simulator/data/contract/env/tree provenance; chưa cache/evolution loop v3 |
| `dpdp_v3_supervisor.py:supervise` | Command + budgets → heartbeats/process log/supervision | Windows-only ctypes Job Objects, start suspended then assign; 1s samples, gap >5s fail, descendant kill; không import/run để mô phỏng trong audit |
| `dpdp_v3_trace.py:TraceWriter`; `dpdp_v3_independent_audit.py:audit, inspect_plan, check_publication` | Saved decision/physical trace + input → PASS/FAIL/UNVERIFIABLE | Độc lập ledger/guard; reconstruct capacity/LIFO/locks/ownership/publication, event reversal; ETA forecast limitation vẫn tồn tại |
| `dpdp_sealed.py:sealed_instance, require_development_path` | Resolved path → allowed path hoặc PermissionError | Application boundary theo component `instance_7/8/15/16`; không OS sandbox, không nhận diện data copy đổi tên |
| `compare_dpdp_baselines.py`, `verify_dpdp_log.py`, `run_vnsme_huawei.py` | Historical comparison/log/Huawei execution workflows | Phải kiểm tra contract từng artifact; không mặc định xem comparison cũ là v3; Huawei environment historical issue cần tái xác minh |

## Luồng thực thi

```text
Pinned Xingtian dataset + split metadata + common network
  -> resolve_inputs / guarded CSV loader / initial locations
  -> DPDP model + release provider + periodic updater (600s)
  -> snapshot của request đã quan sát và trạng thái vật lý
     GP: groups -> candidate pair insertion -> feasibility -> FCFS forecast
         -> five features -> TreeRanker -> min key -> raw decision
     VNSME: Huawei JSON -> Java private session/search
         -> published route/destination -> transformation -> raw decision
  -> shared feasibility + opt-in execution commitment guard + trace
  -> Model enforcement -> movement/port queue/service/physical events
  -> repeat đến giao đủ input hoặc fail/timeout/horizon
  -> commitment.finish -> independent scorer -> result
  -> saved-trace replay + hashes + process supervision -> reference record
  -> v3 assemble/load (chưa có combined 2–6) -> v3 offline ratios
```

Luồng train **đang có** khác bước cuối: v2 `RolloutEvaluator` chạy subprocess cho mỗi tree/instance, cache raw J, trainer lấy mean ratio từ **v2 reference**, breed qua generations 0..G, rồi chấm validation các unique train-valid trees và chọn cây. Không tự nối luồng đó với denominator v3.

## CLI thực tế (inventory, không thực thi trong audit)

Chạy từ `LA/dvrpsim` bằng `./.venv/Scripts/python.exe`:

- `run_dpdp_insertion.py --policy {demo,gp,vnsme} --output ... [--tree ...] [--instance-directory ...] [--data-directory ...] [--contract-version ...] [--wall-seconds ...] [--vnsme-epoch-seconds ...]`; `--instance {1,17}` dành cho ví dụ legacy. Không có CLI Greedy hiện hành.
- `dpdp_vnsme_reference_v3.py preflight --instance N`; `run --instance N --output NEW --contract-version dpdp-execution-commitment-v3`; `assemble --records ... --output NEW`. Preflight không chứng nhận full run. Audit hiện tại không gọi run/assemble.
- `dpdp_v3_supervisor.py --output NEW --timeout-seconds ... [--epoch-root ...] -- COMMAND ...`.
- `train_dpdp_gp_multinstance.py --output NEW --baseline-summary V2_SUMMARY --population ... --generations ... --seed ... --timeout-seconds ...`: **chỉ v2**, không phải lệnh nên chạy tiếp cho v3.
- `train_dpdp_gp.py`, `build_vnsme.py`, `prepare_dpdp_data.py`, `lock_dpdp_protocol.py`, `measure_dpdp_data.py`, scorer/comparison CLIs là các công cụ phụ; nhiều lệnh tạo output, tải dữ liệu hoặc chạy rollout nên không phù hợp nhiệm vụ audit read-only.

## Tests/evidence và reproducibility

Tests liên quan: `test_dpdp_feasibility.py`, `test_dpdp_schedule.py`, `test_dpdp_insertion.py`, `test_dpdp_gp.py`, `test_dpdp_gp_multinstance.py`, `test_verify_dpdp_score.py`, `test_dpdp_execution_guards.py`, `test_dpdp_execution_contract.py`, `test_dpdp_policy_audit.py`, `test_dpdp_sealed.py`, `test_dpdp_v3_reference.py`, `test_dpdp_v3_independent_audit.py`, `test_dpdp_v3_supervisor.py`, `test_dpdp_vnsme_scale100.py`, `test_dpdp_vnsme_timeout.py`.

**REPORTED:** protected regression artifact `vnsme_evidence/v3_independent_audit_20261109_r1/regression_final2.json` ghi 205 tests, 0 failures/errors, 0 sealed opens, 39.78s. Audit này không chạy unittest discovery vì có tests subprocess/simulation; không biến báo cáo lịch sử thành chứng nhận test suite hiện tại.

**VERIFIED:** `.gitignore` bỏ qua venv, run directories và logs. Chuyển Git commit một mình sẽ không mang theo bằng chứng kết quả. Record v3 chứa đường dẫn tuyệt đối và loader so sánh chúng, nên relocation cần quy trình migration riêng; không sửa artifact cũ để làm loader qua. `.gitattributes` mới chỉ ép LF contract v3 và sidecar; còn cảnh báo CRLF cho code. Hash-byte provenance có thể fail sau checkout dù semantics không đổi; cần archive byte đúng và xử lý EOL trước thí nghiệm mới.
