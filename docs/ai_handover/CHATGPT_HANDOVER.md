# GP–DPDP: bàn giao độc lập cho ChatGPT

Snapshot **2026-11-10, khoảng 19:28 Asia/Bangkok**. Bạn là AI tiếp nhận dự án nghiên cứu, cần đọc đây như trạng thái có evidence, không như yêu cầu được phép tự chạy thí nghiệm. Audit tạo tài liệu này chỉ đọc code/metadata/evidence phát triển; không sửa code/artifact, không training, không mô phỏng/benchmark mới, không khởi động Java và không mở CSV sealed 7–8/15–16. Chỉ sáu Markdown trong `LA/docs/ai_handover/` được tạo.

Nhãn: **VERIFIED** = code/evidence trực tiếp kiểm tra trong audit; **REPORTED** = con số/nội dung artifact lịch sử chưa tái chứng nhận toàn bộ; **INFERRED** = suy luận có lý do; **UNKNOWN** = chưa đủ evidence. PASS có phạm vi cụ thể, không phải chứng minh mọi thuộc tính khoa học. Đường dẫn ngắn dưới đây tương đối với `C:/Users/Cuongdz/Documents/LA/dvrpsim/`, trừ khi ghi khác.

## 1. Project identity and research objective

Học bằng **Genetic Programming (GP)** một hàm xếp hạng candidate pair-insertion cho **Dynamic Pickup and Delivery between Plants (DPDP)**. Đơn động xuất hiện theo release; xe chạy giữa factory có hữu hạn docking ports; có capacity, LIFO, pickup-before-delivery, locked current work/destination và conditional order splitting. Dataset Huawei/Xingtian pinned commit `e4ef3a1c92d19d1d08c3ef0e2156b6fecefdbe04`; simulator local `dvrpsim`/SimPy; baseline Java VNSME do người dùng cung cấp.

GP học **quy tắc chọn insertion**, không học simulator hay trực tiếp xuất toàn bộ route bằng tree. Full rollout đo chất lượng chính sách cuối; so với VNSME dùng cùng data/settings/scorer/contract. Không có evidence GP vượt VNSME v3; không hứa kết quả đó.

Item 1/.5/.25 standard-pallet là đơn vị không chia nhỏ; order gốc có thể nhiều item. Order vừa capacity phải cùng pickup batch; oversized order chia nhóm. Deadlines mềm, service bắt buộc. Cùng một original order chỉ tính tardiness một lần theo item giao muộn nhất.

**Objective VERIFIED:** `J = total_distance_km/K + 10000*sum_o max(0,max_i(arrival_delivery_i)-due_o)/3600`, K là tổng số xe. Completion là **arrival tại delivery factory trước waiting/docking/unloading**, không service finish. Nguồn: `verify_dpdp_score.py:aggregate_score, verify`; `examples/case_studies/dpdp/dpdp_main.py:DPDPVehicle.on_service_finish`.

## 2. Verified repository state

- Git root: `C:/Users/Cuongdz/Documents/LA`; branch `complete-gp-dpdp`.
- HEAD: `0bd773291d5d9034f1e7b81688bc2dfaf87308c7`, initial commit ngày 2026-11-09 16:51:07 +0700. Chỉ có một commit trong lịch sử local đã kiểm tra; không đủ lịch sử để biết các giai đoạn trước initial commit.
- Working tree dirty trước audit: **9 tracked modified, 186 insertions/38 deletions**, không staged changes thấy trong short status; nhiều untracked v3 source/tests/protocol/evidence. Chưa commit các tính năng v3 nên checkout HEAD không tái tạo trạng thái này.
- Modified: `dpdp_dataset.py`, `dpdp_vnsme_reference.py`, `examples/case_studies/dpdp/dpdp_problemdata.py`, `prepare_dpdp_data.py`, `run_dpdp_insertion.py`, `src/baselines/vnsme.py`, `test_dpdp_dataset.py`, `test_dpdp_gp.py`, `verify_dpdp_score.py`.
- Untracked quan trọng: `dpdp_contract.py`, `dpdp_gp_fitness_v3.py`, `dpdp_sealed.py`, `dpdp_v3_{independent_audit,supervisor,trace}.py`, `dpdp_vnsme_reference_v3.py`, `.gitattributes`, execution-v3/draft-v3/official-v1 protocols + sidecars, execution/policy/sealed/v3/scale100/timeout tests, các thư mục evidence v3; root có `TIEN_DO_GP_DPDP.md`. Danh sách đầy đủ trong `LA/docs/ai_handover/CURRENT_STATUS.md` nhưng không cần đọc để hiểu blocker.
- `.gitignore` bỏ qua `gp_runs`, `vnsme_runs`, `migration_runs`, `baseline_runs`, `dataset_runs`, logs và venv. Kết quả tồn tại trên đĩa nhưng không tự đi cùng Git clone.
- Môi trường: đúng CLI interpreter `LA/dvrpsim/.venv/Scripts/python.exe` = Python **3.14.4**, dvrpsim **0.0.1**, SimPy **4.1.2**; Java **OpenJDK 26.0.1+8-34**. Root `LA/.venv` cũng Python 3.14.4 nhưng không phải interpreter được CLI chấp nhận. `python` trên PATH không chạy được trong session audit. `pyproject.toml` khai >=3.8 trong khi annotation union ở extension cần >=3.10; minimum support cần cập nhật ở nhiệm vụ riêng.
- Không thấy AGENTS.md trong inventory đã tìm. Không đọc `.env`, key/token/credentials. Không build/cài dependencies hoặc chạy test discovery.

## 3. Architecture and execution flow

| Module/symbol | Input → output và ý nghĩa |
|---|---|
| `dpdp_dataset.py:resolve_inputs, validate_instance` | CSV directory/common data → paths/schema inventory; kiểm sealed guard |
| `dpdp_problemdata.py:read_dpdp_problem` trong case study DPDP | CSV → item/vehicle/factory/travel data, due rollover/seed initial locations |
| `dpdp_main.py:build_dpdp_model, DPDPVehicle` trong case study DPDP | Data → release provider, periodic updater, movement/service, LIFO/resources |
| `dpdp_insertion.py:Snapshot, candidates, extract_features, InsertionPolicy` | Live observed state → checked candidate plans/features → selected raw decision |
| `dpdp_feasibility.py:validate` | Complete remaining item/fleet plan → True hoặc `Infeasible(rule,...)`; độc lập simulator |
| `dpdp_schedule.py:predict_fixed_routes` | Current/future fixed routes → FCFS schedule/arrival/wait/service rows |
| `dpdp_gp.py:Node, TreeRanker, breed` | AST/features hoặc population/RNG → candidate score hoặc offspring |
| `run_dpdp_insertion.py:RunModel, guard_raw_decision, main` | Policy/tree/data/budgets → guarded rollout, manifest/result/log/trace/ledger |
| `dpdp_contract.py:ExecutionCommitment` | Mỗi decision và physical state → ledger states; completion gate v3 |
| `src/baselines/vnsme.py:JavaSession, huawei_state, VNSMEPolicy` | Live state → Huawei JSON → Java published routes → raw decision |
| `verify_dpdp_score.py:verify, aggregate_score` | Trajectory + CSV → independent Decimal J/D/T và validity |
| `dpdp_gp_fitness.py:RolloutEvaluator`; `train_dpdp_gp_multinstance.py:run_experiment` | Tree/config + **v2** denominator → process rollouts/cache/generations/selection |
| `dpdp_vnsme_reference_v3.py:audit_run, audit_vnsme_run, load_reference` | Saved runs/records → replay/rescore/source/build/supervision-certified reference |
| `dpdp_gp_fitness_v3.py:evaluate` | Same-tree GP saved runs + v3 denominator → train mean ratio/validation ratios; **offline only** |
| `dpdp_v3_trace.py:TraceWriter`; `dpdp_v3_independent_audit.py:audit` | Physical/decision trace + inputs → independent feasibility/publication checks |
| `dpdp_v3_supervisor.py:supervise` | Command → Windows Job Object process control, heartbeat/deadline/cleanup evidence |

Flow: pinned development CSV → guarded loader → local model/release events → dispatch mỗi **600s** → GP candidate pipeline hoặc Java publication → shared feasibility/v3 commitment guard trước model enforcement → physical events → giao đủ input → final scorer → saved-trace replay + build/input/source hashes + supervision → record → combined reference → GP normalized fitness.

Simulator settings VERIFIED: docking **1800s/visit**, load/unload **240s/unit**, homogeneous fleet LIFO, FCFS ports giữ suốt service, initial-location seed **0**, safety horizon **604800s**, no GP visit merging, compute time instantaneous trong simulation. Resource/vehicle execution ở `src/dvrpsim/{model.py,elements/vehicle.py,environment.py}`; deadlines soft, capacity/LIFO/locks là hard checks.

Entrypoints đọc từ code, không chạy trong audit:

- Từ `LA/dvrpsim`: `./.venv/Scripts/python.exe run_dpdp_insertion.py --policy {demo,gp,vnsme} --output NEW [--tree FILE] [--instance-directory DIR] [--contract-version ...]`; benchmark 2–6 dùng directory, `--instance` legacy chỉ 1/17. Default contract vẫn **v2**.
- `dpdp_vnsme_reference_v3.py preflight --instance N`, `run --instance N --output NEW --contract-version dpdp-execution-commitment-v3`, `assemble --records ... --output NEW`.
- `train_dpdp_gp_multinstance.py --output NEW --baseline-summary ...` vẫn **v2**. Không lấy nó làm trainer v3.
- `build_vnsme.py`, `prepare_dpdp_data.py`, `compare_dpdp_baselines.py`, `verify_dpdp_score.py`, `run_vnsme_huawei.py` là công cụ phụ; nhiều CLI có side effects, không tự chạy vì thấy trong bàn giao.

## 4. GP methodology and implementation

**Individual:** immutable `Node` AST, terminals feature/constant, binary `+ - * /`, caps depth4 (root0)/31 nodes. Canonical JSON/hash và feature/numeric schemas được kiểm khi load model. Constant random [-2,2], 3 decimals; initial population bắt đầu bằng ΔD và ΔD+ΔT rồi random grow/full.

**Candidate:** đơn đã quan sát được sắp EDD/release/original ID, item giảm quantity rồi ID, next-fit groups đến capacity. Pickup/delivery hai visit riêng, delivery reverse list cho LIFO. Enumerate sorted vehicle rồi vị trí p,d>p trong mutable suffix; nếu locked destination thì p>=1. Giữ visits/assignments đã có của GP. Validate cả fleet trước forecast/rank; update before metrics sau từng group; không candidate thì defer, yêu cầu vẫn bắt buộc. Nguồn: `dpdp_insertion.py:split_observed_orders, candidates, InsertionPolicy.decide`.

Năm feature VERIFIED (`Snapshot.metrics`, `extract_features`, `min_residual`):

1. `delta_distance_km` = after-before remaining-route total distance cả fleet, km. Origin current factory hoặc previous factory khi travelling; không clamp âm.
2. `delta_tardiness_seconds` = after-before tổng tardiness theo **original orders** của admitted items, dự báo latest delivery arrival; giây.
3. `delta_waiting_seconds` = after-before tổng queue waiting các schedule rows cả fleet; vehicle-seconds.
4. `new_order_slack_seconds` = group due − after latest admitted item arrival của cùng original order; có thể âm.
5. `min_residual_capacity` = nhỏ nhất capacity − stack quantity qua initial/current/future operations của xe candidate, bỏ qua current operations đã hoàn thành; pallet quantity.

Snapshot chỉ đọc `model.orders` đã release, không future `private_data['orders']`. Fixed-route forecast không tạo đơn/decision mới. Forecast ties future equal arrival theo vehicle order; chưa bảo đảm bằng simulator trong mọi trường hợp.

**Rank:** minimum `(tree_score, vehicle_id, pickup_index, delivery_index)`. Score không phải J/fitness. Protected division trả numerator khi `abs(denominator)<=1e-9`, còn số âm nhỏ hơn -epsilon vẫn chia. Saturation ±1e12 cho finite value vượt ngưỡng; nonfinite raise và invalid rollout. C10 expression `(ΔT/ΔD − minResidual)+ΔT` có sign-flip khi ΔD âm: với ΔD=-0.1, ΔT=5978, residual12.5 cho rank=-53814.5, tốt hơn theo min so với candidate không tardy rank=-13. Đây là đặc tính cây, chưa chứng minh lỗi feature. Regression source: `test_dpdp_policy_audit.py`.

**Rollout/generation:** một tree × một instance full scenario là một rollout. Trainer đánh giá mỗi tree trên train 2–5 rồi breed qua generation0..G. Tournament key `(fitness,node_count,canonical)`, size3; crossover .8, mutation .3, elitism1; operators tối đa10 retries rồi giữ parent. Validation6 không dùng breed; sau evolution chấm unique train-valid trees để chọn thấp nhất validation ratio, tie train fitness/node count/canonical.

**Fitness v2 hiện hành:** equal-weight mean J_GP/J_VNSME trên đúng 2–5; một train rollout invalid làm cả tree invalid. Penalty code **1e15**, benchmark_J=None cho invalid. Default CLI seed20261106/G2/pop6/timeout30s; official saved config seed20261109/G3/pop6/timeout30s. Environment seed0. Không coi penalty là benchmark J.

**Cache v2:** SHA canonical tree + context gồm version, instance, evolution/environment seed, reference summary hash, split/source-manifest/data/source hashes, settings/numeric caps, wall budget, Python executable/version/packages. Hit kiểm key/context và log hash, không audit lại toàn bộ cached artifacts. `verify_pins` phát hiện reference/protocol/manifest thay đổi. Chưa có v3 training/cache tương đương. `dpdp_gp_fitness_v3.py:evaluate` chỉ audit các GP runs đã lưu, so cùng tree/data/simulator/contract/env rồi trả ratio; không tiến hóa/chạy rollout.

## 5. VNSME baseline and integration

Gói gốc `LA/VNSME/{source-code,compiled files}` được nhập byte-for-byte source vào `third_party/vnsme/original`, libs vào `lib`, build vào `build`; manifest ghi compiler/source/lib/class hashes. Compile unchanged source `--release 8` bằng JDK26. **REPORTED:** nhãn Gold/ICAPS2021 dựa gói người dùng, thiếu upstream release checksum/license/Maven/Gradle. Nguồn `third_party/vnsme/README.md`, `provenance.json`, `build_manifest.json`.

Java `main_algorithm.main`: đọc state/old private solution, restore scene, dispatch new hoặc redispatch sau24h, variable neighborhoods (pair exchange, block exchange/relocate, multi-PD-group relocation, 2-opt), update solution, merge nodes, delay publication. Không thay private plan bằng full route dump. Python giữ private working directory/`solution.json` xuyên epochs, convert thời gian integer với host-midnight offset, yêu cầu V_1..V_n đúng order, reject unknown/future items và thay đổi locked factory/ETA.

GP/VNSME dùng chung loader/model/scorer/guard/trace/contract; **không dùng chung candidate search hoặc publication**. GP chỉ pair insertion giữ route cũ; Java có nhiều neighborhood/redispatch/merge/delay. Cần công bố khác biệt đó khi diễn giải kết quả.

**Contract v3** `dpdp-execution-commitment-v3` là semantic revision: release tạo nghĩa vụ đến khi delivered; accept irreversible; unpicked assignment ngoài current work chỉ tentative, có thể omit/reassign nhưng không mất khỏi ledger/unallocated. Current work, physical stack/owner, destination factory/arrival bị khóa. States pending/tentative/committed/delivered partition đúng observed universe; cuối run phải observed/delivered đủ input. V2 accepted-route contract vẫn default và historical denominators không được certified cho v3. Nguồn `dpdp_contract.py`, descriptor v3, `VNSMEPolicy.decide`.

Budgets certified: cooperative search **540s**, hard epoch **600s**, rollout **10800s**. Supervisor Windows Job Object start suspended→assign, sample1s, fail nếu gap>5s/deadline; cleanup descendants. Java `TimeOut!!` có thể chỉ cooperative exit với output hợp lệ, khác hard timeout. Java dùng wall-clock stopping/host midnight; seed0 simulator không chứng minh Java deterministic. Có `new Random()` trong `randomLocalSearch`, nhưng tìm call site chỉ thấy definition; chưa chứng minh RNG tham gia active search.

## 6. Experiment protocol and data split

50-order: train **2,3,4,5**, validation **6**, sealed test **7,8**. 100-order proposed: train9–12, val13–14, sealed15–16. 1/17 đã exposed, không final untouched test. Không giả định statistical independence giữa IDs chung network.

Hash VERIFIED:

- Split `protocols/dpdp_gp_split_v1.json`: `21c7f62c06a4402214dd0051728bec4fb8051cb8ab420866cd565c669a49f859`.
- Dataset source manifest: `cf72390459bdb50facd666ae4dbbaa9b6712f2161d61ba6756309a0c100968bc` (không đọc lại bytes sealed).
- Contract `protocols/dpdp_execution_commitment_v3.json`: `c751559337adbe2138a455819465764d726cf4bba26e5544715df4b90e44b6ed`.
- Java build manifest hash certified trong reference: `49f85c57affe25a86e32522d82e16bde833c9211b7e34b56e08f79fd1f751046`.

Draft `protocols/dpdp_gp_vnsme_v3_draft.json` VERIFIED `enabled=false`, `DRAFT_NOT_ENABLED_FOR_TRAINING`. Existing `train_dpdp_gp_multinstance.py` import v2 loader/fitness version và không truyền contract-v3 cho subprocess. Chỉ có evaluator offline v3; **training v3 NO-GO**.

Protocol v2 “official” `dpdp_official_experiment_v1.json` có hai mismatch VERIFIED: penalty ghi **1e9** trong khi code/config dùng **1e15**; field `split_protocol_sha256` ghi nhầm **source-manifest hash cf7239...** thay vì split21c7.... Trainer nhận split + CLI params, không enforce toàn official descriptor. Tạo protocol mới để sửa, không ghi đè historical snapshots.

Baseline/GP v3 phải cùng data hashes, initial locations, Python/packages, simulator/scorer/runtime fingerprint, contract/settings; same tree trên các GP runs; VNSME denominator finite positive. Mean ratios là fitness, không ratio of sums. Invalid không có valid J; giữ validation ngoài evolution; final test chỉ sau freeze/authorization riêng.

## 7. Verified experimental results

Audit này **gọi lại các hàm chỉ đọc** `audit_vnsme_run` cho bảy saved collections; mỗi check ~1.8–3.3s, không simulator/Java. Mọi result re-score/replay PASS, current record bằng record đã lưu; đọc lại toàn bộ recorded artifact/supervision hashes + protocol-manifest hash không mismatch. Runtime bên dưới là saved runner total wall, không thời gian audit hiện tại.

Đặt `R=vnsme_runs/`. Mỗi collection có `protocol_manifest.json`, `record.json`, `run/manifest.json`, `run/result.json`, `run/decisions.json`, `run/commitments.json`, `run/simulation.log`, `run/decision_trace.jsonl`, `run/vnsme/session.json`, per-epoch I/O/process markers và `supervisor/{supervision.json,heartbeats.jsonl,process.log}`. Hash map nằm trong record. Supervision tất cả EXITED0, valid=true, gaps=[], remaining_job_processes=[]; không hard timeout.

| ID | Collection sau R/ | Full-run status | D km | T s | J | Runner wall s |
|---:|---|---|---:|---:|---:|---:|
| 2 | `v3_instance2_acceptance_20261109_r1` | VERIFIED PASS | 478.7 | 0 | 95.74 | 32.1266 |
| 3 | `v3_references_3_6_20261109_r1/instance_3` | VERIFIED PASS | 487.2 | 0 | 97.44 | 26.7209 |
| 4 | `v3_references_3_6_20261109_recovery_r1/instance_4` | VERIFIED PASS | 504.6 | 0 | 100.92 | 1649.2622 |
| 5 | `v3_instance5_recovery_20261110_r1` | VERIFIED PASS, canonical chưa chốt | 464.4 | 1158 | 3309.546666666666666666666667 | 2726.1255 |
| 6 | `v3_instance6_validation_20261110_r1` | VERIFIED PASS | 525.2 | 0 | 105.04 | 569.3246 |
| 5 | `v3_instance5_standalone_r1` | VERIFIED PASS, alternative | 435.8 | 1158 | 3303.826666666666666666666667 | 2726.4607 |
| 6 | `v3_instance6_standalone_r1` | VERIFIED PASS, alternative | 525.2 | 0 | 105.04 | 568.9773 |

Mỗi instance giao đủ50 original orders; items/dispatches lần lượt 2=110/167, 3=78/160, 4=88/155, 5=107/153, 6=86/156. Supervisor wall cho năm hàng chính lần lượt33.7461/29.3908/1650.8704/2728.0264/571.6410s; alternative5=2728.2600, alternative6=571.4352s.

**VERIFIED combined status: NOT FOUND / INCOMPLETE.** Inventory `vnsme_runs/**/summary.json` với v3 path chỉ thấy singleton `v3_instance2_acceptance_20261109_r1/reference_2/summary.json`; chưa có records2–6 summary. Preflight dự kiến `v3_reference_ready_2_6_20261110_r1` nhưng output đó không có trong top-level inventory. Chưa load_reference exact {2,3,4,5,6}; không chạy assemble trong audit để tuân thủ chỉ ghi docs. Full-run PASS từng instance không đồng nghĩa bộ denominator canonical đã chứng nhận.

**Instance5 khác biệt:** hai run cùng audited runtime/contract/build/settings nhưng D chênh28.6km/J chênh5.72. Không tự chọn best J. Fast audit `vnsme_evidence/fast_audit_instance5_20261110_152157/audit_report.json` chứng nhận standalone J3303.826666...; preflight_instance6 trong `vnsme_evidence/v3_instance5_recovery_20261110_r1/` dùng recovery J3309.546666.... Cần chốt run-selection policy và tìm nguyên nhân.

**REPORTED interruptions lịch sử:** instance4 original run09/11 bị ngắt106 epoch starts/105 ends; recovery4 sau đó PASS. Instance5 trong recovery-suite09/11 ngắt112 starts/111 ends, chưa hard timeout ở heartbeat cuối, thiếu final artifact; hai run5 ngày10/11 sau đó PASS. `.../v3_references_3_6_20261109_recovery_r1/{STATUS.md,RESULTS.md}` còn ghi5 interrupted/6 not run, nên **đã lỗi thời** với snapshot hiện tại. Không xóa các run gián đoạn.

**GP v2 REPORTED results, filesystem VERIFIED:** `gp_runs/vnsme_v2_new_training_20261108_r1` có generations0/1/2, candidates/selected_tree/training, models/cache/rollouts. Status complete, seed20261106, pop6/G2,55 process rollouts,359.9827s; tree `(((delta_tardiness_seconds / delta_distance_km) - min_residual_capacity) + delta_tardiness_seconds)`, train mean ratio106.09054959678747, validation ratio1.7524752475247525. Không tái audit tất cả GP results; ratio>1 không cho phép claim GP thắng VNSME. V2 denominator `migration_runs/vnsme_reference_ready/summary.json` có instance4 J100.76 và instance5 J3303.926666..., không đổi tên thành v3.

**GP official09/11 VERIFIED INCOMPLETE:** `gp_runs/official_gp_multinstance_20261109` chỉ có top-level experiment_protocol và generation0, không generation1–3/training/selected_tree cuối. Config **v2**, seed20261109/G3/pop6; generation0 có6 valid trees, best train ratio23.908337888479483. Không biết lý do dừng hoặc process hiện tại; root `TIEN_DO_GP_DPDP.md` “đang training” chưa được xác nhận.

**REPORTED regression:** `vnsme_evidence/v3_independent_audit_20261109_r1/regression_final2.json` ghi205 tests,0 failures/errors,0 sealed opens,39.78s. Audit không chạy suite, không chứng nhận suite hiện tại PASS.

## 8. Current blockers and unresolved issues

1. **P0 VERIFIED:** chưa canonical combined reference v3, đặc biệt hai valid instance5 khác điểm; cần tránh chọn baseline theo best J sau khi thấy kết quả.
2. **P0 VERIFIED:** protocol v3 disabled, trainer/cache/rollout evaluator hiện hành v2; official v2 cũng incomplete. Không chạy training v3 bằng cách thay denominator/label.
3. **P0/P1 REPORTED:** sealed CSV từng được đọc trong regression discovery; cần disclosure/đánh giá methodology trước final claims (chi tiết mục11).
4. **P1 VERIFIED:** official protocol penalty/hash mismatch; source v3 chưa commit; ignored outputs/absolute record paths gây khó archive/relocation.
5. **P1 VERIFIED:** replay giới hạn at-location future ETA: kiểm lock ghi trước decision, chưa independently reforecast; equal-arrival forecast ties theo vehicle order. Không suy diễn PASS thành proof mọi schedule prediction đúng.
6. **P1 UNKNOWN:** nguyên nhân instance5 variation, Java determinism, đầy đủ equivalence Huawei/local simulator, tính toàn vẹn toàn bộ legacy GP caches, 100-order coverage và scalability.
7. **P1 VERIFIED:** runtime budgets khác GP/VNSME; compute không đi vào simulation. Phải phân biệt online dispatch, training cost, Java startup/search, scorer, supervisor. Không dùng một số total wall mơ hồ để claim speedup.

**INFERRED current work:** dirty files + timestamp/evidence cho thấy chuyển contract v3, supervisor/sealed/independent audit rồi recovery5/validation6 và standalone5 audit. Không có hội thoại trước đó để khẳng định kế hoạch chính xác của Codex hoặc yêu cầu còn đang chạy.

## 9. Immediate next task

**Chốt canonical run-selection, audit/adopt rồi assemble bộ reference v3 2–6 vào output mới, không training.** Trước hết tìm quyết định lựa chọn run đã có; nếu chưa có thì ghi rõ selection sau khi đã biết điểm và lý do, không mặc định chọn J nhỏ nhất. Không cần full rerun chỉ vì thiếu summary khi runs hiện tại vẫn qua audit.

Record candidates đã xác minh:

```text
vnsme_runs/v3_instance2_acceptance_20261109_r1/record.json
vnsme_runs/v3_references_3_6_20261109_r1/instance_3/record.json
vnsme_runs/v3_references_3_6_20261109_recovery_r1/instance_4/record.json
vnsme_runs/v3_instance5_recovery_20261110_r1/record.json
vnsme_runs/v3_instance5_standalone_r1/record.json
vnsme_runs/v3_instance6_validation_20261110_r1/record.json
vnsme_runs/v3_instance6_standalone_r1/record.json
```

Chỉ chọn **một** record5 và **một** record6. Sau lựa chọn: `dpdp_vnsme_reference_v3.py assemble --records <five-record-paths> --output <NEW>` bằng đúng venv. Rồi `load_reference(<NEW>/summary.json,{2,3,4,5,6})` phải PASS; lưu summary hash/selection/provenance/audit output. Đây là nhiệm vụ tương lai cần scope cho phép tạo experimental artifact; audit hiện tại chưa làm.

## 10. Recommended implementation plan

| Priority/task | Tiên quyết và triển khai | Acceptance/evidence | Rủi ro; độ phức tạp |
|---|---|---|---|
| P0 canonical reference | Chọn R5/R6 theo policy, giữ runs, audit/assemble/load exact2–6 | Combined hash + loader PASS + selection decision/provenance matrix | Cherry-pick/absolute paths; M |
| P0 source/environment preservation | Inventory dirty/untracked + ignored artifact archive; xử lý byte/EOL trước thí nghiệm mới, review code | Source/build/data/protocol manifests + reproducible archive/commit khi được phép | HEAD thiếu v3; S/M |
| P0 frozen training protocol v3 | Certified denominator rồi mới protocol mới, correct hashes/penalty, explicit seeds/budgets/config/select/cache | Enabled protocol sau validation, no mixed version, rationale GO | Chỉ đổi enabled không đủ; M |
| P1 sealed disclosure/access | Code/log metadata, không mở test; incident timeline + bounded synthetic guard checks | Zero sealed reads trong workflow mới, impact decision ghi rõ | Application guard không OS isolation; M |
| P1 feature/forecast correctness | Ongoing service/equal arrival/current lock/cross-epoch splitting cases, independent oracles | Focused tests + feature numerical examples + ETA limits | Sửa code có thể invalid reference fingerprints; M/L |
| P1 reproducibility/runtime | So saved instance5 traces trước; phân tích time-stop/midnight, define repeat/timing policy | Reproducibility note hoặc UNKNOWN có kế hoạch; comparable timing schema | Không khẳng định RNG active; M |
| P2 trainer/evaluator/cache v3 | P0 GO; config-enforced explicit contract, new cache namespace, reject v2, synthetic bounded integration | No invalid valid-J, emitted audit/protocol/cache lineage, no sealed opens | Silent legacy default/cache stale; L |
| P2 development study | Trainer/protocol certified rồi mới đặt hypothesis/seeds/budgets, train2–5, select6, freeze model | Full generations/rollouts/candidates/tree/audit/analysis | Validation overfit/pop6G3 nhỏ; L |
| P3 final evaluation | Freeze methods/model/hash, xử lý incident, authorization riêng trước mở test | Final same-contract paired J/D/T/completion/ratio/runtime + replay/hashes | Không tune theo sealed; L |
| P3 report/archive | Kết quả đã chứng nhận hoặc ghi experiment incomplete; giữ nhãn version/history | Source-linked raw tables, limitations/reproduction archive | Claim vượt evidence; M |

Không đề xuất chạy GP v3 chính thức trước khi reference bộ/protocol/trainer được chứng nhận. Không tự mở rộng100-order vì draft có proposed IDs. Không refactor Java để làm nhanh trong lúc thu baseline; mọi methodological change cần protocol/version riêng và xem lại comparability.

## 11. Critical scientific constraints

- **Không mở/đọc/chạy/debug sealed 7–8 hoặc15–16** trong development. Chỉ metadata split/protocol. Không tải/copy lại sealed để bypass guard.
- **REPORTED incident đã xảy ra:** `vnsme_evidence/v3_reference_supervision_20261109_r1/REPORT.md` ghi `unittest discover` từng chạy tests gọi `verify_existing`, đọc bytes/checksum/schema/loader toàn dataset gồm sealed CSV. Báo cáo nói không rollout/scoring/selection sealed. `v3_independent_audit_20261109_r1/summary.json` có `final_test_read_incident_from_prior_run=true`. Không thể nói “chưa bao giờ đọc sealed”; chưa có evidence để nói đã tune bằng sealed scores.
- **VERIFIED hiện tại:** `dpdp_sealed.py` chặn resolved path có component instance_7/8/15/16; guarded dataset/case-study/scorer readers dùng nó; `verify_existing` skip sealed byte/schema validation. Đây là application boundary, không chống arbitrary OS/copies đổi tên. Guard về sau không xóa incident.
- Không dùng validation để breed; final-test sau freeze/authorization riêng, không tune/debug. Không giả định sealed còn untouched chỉ vì không có kết quả ở Git.
- Không trộn Greedy cũ/raw-J pilot, VNSME v2 và v3. Không thay J của legacy record hoặc normalize v2 numerator bằng v3 denominator.
- Không xem preflight PASS, artifact tồn tại hoặc doc “completed” là full-run certificate. Invalid/missing service không có valid J. Cần guard + replay + independent scorer + provenance/supervision, không chỉ scorer.
- Không claim GP beats baseline, deterministic Java, perfect ETA prediction hay Huawei equivalence nếu không có evidence tương ứng. Không giấu negative results/timeout/selection bias.
- Không sửa/xóa experimental artifacts cũ. Không reset working tree; code/evidence untracked là tiến độ thực tế. Checkpoint/resume simulator+Python/Java/RNG chưa được chứng nhận, không nối logs của interrupted runs rồi gọi completed.

## 12. Relevant file paths and evidence references

Ưu tiên đọc theo câu hỏi, không chạy file tự động:

1. `dpdp_vnsme_reference_v3.py:audit_vnsme_run, load_reference` và bảy record paths ở mục9: nguồn chứng nhận hiện tại.
2. `dpdp_contract.py:ExecutionCommitment`, `protocols/dpdp_execution_commitment_v3.json`: ngữ nghĩa v3.
3. `dpdp_gp_fitness_v3.py:evaluate`, `protocols/dpdp_gp_vnsme_v3_draft.json`: offline-only và training disabled.
4. `run_dpdp_insertion.py:guard_raw_decision, RunModel, main`; `src/baselines/vnsme.py:JavaSession, VNSMEPolicy`: execution/adapter.
5. `dpdp_insertion.py`, `dpdp_schedule.py`, `dpdp_feasibility.py`, `dpdp_gp.py`: GP/checker/forecast/features/tree.
6. `verify_dpdp_score.py:verify, aggregate_score`; case-study `DPDPVehicle.on_service_finish`: J và completion semantics.
7. `dpdp_v3_independent_audit.py:audit`; `vnsme_evidence/v3_independent_audit_20261109_r1/audit_matrix.json`: replay coverage/ETA limitation.
8. `vnsme_evidence/fast_audit_instance5_20261110_152157/audit_report.json`: standalone5 acceptance/loader/provenance; không nhầm recovery5.
9. `vnsme_evidence/v3_instance5_recovery_20261110_r1/{preflight.json,preflight_instance6.json,instance5_launcher.json,instance6_launcher.json}`: recovery5/validation6 launch timeline; không dùng preflight thay result.
10. `vnsme_evidence/v3_references_3_6_20261109_recovery_r1/{RESULTS.md,instance5_interrupted.json}`: lịch sử interruption, phần status đã cũ.
11. `vnsme_evidence/v3_reference_supervision_20261109_r1/REPORT.md`: sealed read incident; `v3_independent_audit_20261109_r1/regression_final2.json`: reported205 tests.
12. `gp_runs/vnsme_v2_new_training_20261108_r1/{training.json,selected_tree.json}`, sibling `..._audit/{REPORT.md,final_verification.json,rollout_verification.json}`: v2 complete run/reports chưa tái chứng nhận toàn bộ ở audit này.
13. `gp_runs/official_gp_multinstance_20261109/{experiment_protocol.json,generation_0.json}`: official v2 incomplete.
14. `protocols/dpdp_gp_split_v1.json`, `dpdp_official_experiment_v1.json`, `third_party/vnsme/{README.md,provenance.json,build_manifest.json}`: split/protocol mismatch/build provenance.
15. `LA/docs/ai_handover/PROJECT_CONTEXT.md`, `ARCHITECTURE.md`, `CURRENT_STATUS.md`, `EXPERIMENT_PROTOCOL.md`, `NEXT_STEPS.md`: tài liệu chi tiết bổ sung. Bản bàn giao này đã tự chứa quyết định và blockers quan trọng.

## 13. Open questions requiring verification

1. Đã có run-selection policy/approval trước khi biết điểm để chọn recovery5 hay standalone5 chưa? Canonical6 chọn run nào và vì sao?
2. Hai trajectory instance5 khác nhau chính xác bắt đầu epoch nào, do time-stop/host/private solution hay yếu tố khác? Chưa phân lập nguyên nhân.
3. Ai sẽ sở hữu bước assemble/certify combined denominator và protocol v3 mới? Chưa có summary2–6, không chỉ thiếu một doc status.
4. GP official09/11 dừng ở đâu sau generation0, lý do gì, process còn chạy hay không? Không có final JSON làm bằng chứng hoàn tất.
5. Historical sealed byte/schema access ảnh hưởng tuyên bố independence thế nào? Chưa được phép đọc test để điều tra; cần methodology decision rõ ràng.
6. At-location ETA/equal-arrival forecast có thể có independent oracle tới mức nào? Replay hiện chỉ kiểm lock, không chứng minh forecast accuracy.
7. V3 GP evaluator/protocol cần khóa penalty/timeout/repeat/cache schema nào? Không lấy defaults v2 làm quyết định tự động.
8. Minimum supported Python, portable build/runtime/paths, byte-preserving archive và dependency lock sẽ được định nghĩa thế nào? HEAD và pyproject hiện chưa đủ.
9. Local simulator tương đương Huawei đến mức nào, 100-order feasibility/runtime đến đâu, và đủ scenarios/seeds để kết luận khoa học chưa? Audit này không chạy các phép thử đó.

Hành động tiếp nhận phù hợp: giữ nguyên tiến độ và evidence, báo rõ **từng reference2–6 đã PASS nhưng bộ canonical/protocol/trainer v3 còn NO-GO**, rồi giải quyết mục9 trước khi bàn huấn luyện chính thức.
