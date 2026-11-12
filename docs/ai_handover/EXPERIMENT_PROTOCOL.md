# Protocol, điều kiện chứng nhận và GO/NO-GO

Ngày 2026-11-10, Asia/Bangkok. Các đường dẫn trong tài liệu này tương đối với `LA/dvrpsim/`. Đây là mô tả/khuyến nghị từ audit, **không phải protocol v3 đã được bật**.

## Dataset và split

**VERIFIED:** nguồn pinned `huawei-noah/xingtian`, commit `e4ef3a1c92d19d1d08c3ef0e2156b6fecefdbe04`, dataset local `datasets/xingtian/e4ef3a1c92d19d1d08c3ef0e2156b6fecefdbe04/`. Chỉ metadata source manifest/split và input phát triển 2–6 được dùng để audit reference; không mở sealed CSV.

| Scale | Train | Validation | Final test | Trạng thái protocol |
|---|---|---|---|---|
| 50 original orders, 5 xe | 2,3,4,5 | 6 | 7,8 | Split khóa, development allowed |
| 100 original orders, 5 xe | 9,10,11,12 | 13,14 | 15,16 | Proposed, không tự mở rộng training |
| Legacy examples | 1,17 | Không phải untouched holdout | Không dùng làm final test | Đã exposed |

Nguồn: `protocols/dpdp_gp_split_v1.json`. Không giả định các instance độc lập thống kê chỉ vì ID khác nhau; chung network và có thể quan hệ scenario.

Các hash đã tính lại và khớp sidecar:

| Artifact | SHA-256 |
|---|---|
| `protocols/dpdp_gp_split_v1.json` | `21c7f62c06a4402214dd0051728bec4fb8051cb8ab420866cd565c669a49f859` |
| Source manifest dataset | `cf72390459bdb50facd666ae4dbbaa9b6712f2161d61ba6756309a0c100968bc` |
| `protocols/dpdp_execution_commitment_v3.json` | `c751559337adbe2138a455819465764d726cf4bba26e5544715df4b90e44b6ed` |
| `protocols/dpdp_gp_vnsme_v3_draft.json` | `7c5edb44a8d6c67a2b8f810209270f0aa42aacbc8ca7871039ffd743f116beb0` |
| `protocols/dpdp_official_experiment_v1.json` | `bdd0be5153dfb27576b1f1b41ad0fa22179528e0b5eaf06400fb219b1467bb84` |

Build-manifest hash dùng trong các reference v3: `49f85c57affe25a86e32522d82e16bde833c9211b7e34b56e08f79fd1f751046`. Audit v3 kiểm tra các map source/lib/class của build, không chỉ tên file. Source manifest hash được xác nhận qua `metadata()` trong audit 2–6; không xác nhận lại bytes sealed được kê trong manifest.

## Scoring và môi trường chung

`J = total_distance_km / vehicle_num + total_tardiness_seconds * 10000 / 3600`.

Tardiness là tổng theo original order, mỗi order dùng thời điểm đến delivery factory muộn nhất của các item, không dùng service finish. `verify_dpdp_score.py:aggregate_score, verify` dùng Decimal; invalid/incomplete/duplicate/missing deliveries không có benchmark J hợp lệ.

Simulation: dispatch=600s, dock=1800s, load/unload=240s mỗi unit; seed initial locations=0; safety horizon=604800s; GP visit merging=false; compute time instantaneous trong simulator. Cùng CSV hashes, initial locations, simulator/scorer source fingerprint, packages/Python, contract và settings giữa GP/VNSME. Nguồn: `dpdp_vnsme_reference.py:SIMULATION`, `dpdp_vnsme_reference_v3.py:metadata, audit_run`, `dpdp_gp_fitness_v3.py:evaluate`.

Không gọi điểm local là bằng chứng hoàn toàn tương đương Huawei runtime. Scorer log không tự kiểm chứng tất cả feasibility; phải cộng guard và independent trace replay.

## Baseline contract v3

`dpdp-execution-commitment-v3`: release tạo nghĩa vụ service đến khi giao đủ; accept không đảo ngược; hàng chưa pickup ngoài current work là tentative, có thể tạm không publish/reassign nhưng phải còn trong observable ledger/unallocated; physical ownership/current work/destination factory và arrival bị khóa. Các ledger states partition đúng request universe. Completion gate kiểm tra toàn bộ input đã observed/delivered. Không reject/cancel/forget/fallback hoặc promote Java private plan vào publication. Nguồn: `dpdp_contract.py:ExecutionCommitment`, descriptor v3.

GP dùng insertion policy hiện tại ít tự do tái cấu trúc hơn Java VNSME; fairness về thông tin/scorer/constraints phải được công bố cùng sự khác biệt search space và publication. Không thay thuật toán Java để ép giống GP trong lúc so sánh.

VNSME budgets của collection contract: cooperative Java 540s, hard epoch 600s, rollout 10800s. Supervisor Windows Job Object kiểm tra epoch/run deadlines, gap >5s invalid, cleanup descendants. Java in `TimeOut!!` do cooperative search stop không đồng nghĩa hard subprocess timeout: dùng invocation end markers, valid outputs và supervision để kết luận. Nguồn: `dpdp_vnsme_reference_v3.py:audit_vnsme_run`, `dpdp_v3_supervisor.py:supervise`, Java `variableNeighbourhoodSearch`.

## GP mechanics và feature contract

**VERIFIED:** chỉ năm terminal features, input model không có instance ID/future requests:

| Feature | Cách tính chính xác |
|---|---|
| `delta_distance_km` | after fleet remaining-route distance − before; origin là current factory hoặc previous factory khi đang travel; không tự clamp âm |
| `delta_tardiness_seconds` | after − before tổng `max(0, latest admitted item arrival per original order − due)` trên admitted set; không itemwise tardiness |
| `delta_waiting_seconds` | after − before tổng queue waiting của tất cả schedule rows/xe; đơn vị vehicle-seconds |
| `new_order_slack_seconds` | `group.due − after['latest'][group.order]`, có thể âm; latest của các item order đã admitted |
| `min_residual_capacity` | Minimum `vehicle.capacity − stack load` qua initial/current/future pickup/delivery trên **xe candidate**, bỏ qua operation current đã hoàn thành |

Nguồn: `dpdp_insertion.py:Snapshot.metrics, extract_features, min_residual`. Before được cập nhật sau mỗi group insertion, không cố định toàn dispatch. Forecast biết các request đã release, không request chưa release; lateness soft. Negative ΔD có thể có trên distance matrix không metric; không tự sửa dấu feature để chữa một tree.

Candidate grouping: EDD, release, original ID; trong order giảm quantity rồi ID; next-fit đến capacity, item indivisible; delivery list reverse pickup để LIFO. Với mỗi xe theo sorted ID, enumerate pickup p rồi delivery d>p; nếu destination đã announce thì p>=1. Mỗi candidate qua full fleet checker trước forecast. Chọn minimum `(tree_score, vehicle_id, p, d)`; không feasible thì defer sang dispatch sau, không impute score cuối. Nguồn: `split_observed_orders`, `candidates`, `InsertionPolicy.decide`.

Trees: binary `+,-,*,/`; division khi `abs(denominator)<=1e-9` trả numerator, còn denominator âm vẫn chia bình thường. Finite magnitude >1e12 saturate về signed 1e12; nonfinite raise, invalid cả rollout. Max depth=4/root0, nodes<=31. Constants random [-2,2], 3 decimals; seeds population là ΔD và ΔD+ΔT rồi random grow/full. Tournament key `(fitness,nodes,canonical)`; cross/mutate tối đa 10 retries rồi giữ parent. Nguồn `dpdp_gp.py`.

## Fitness, selection, seed và cache

V2 đang chạy và draft v3 đều mô tả train equal-weight `mean(J_GP(i)/J_VNSME(i))` cho i=2,3,4,5. Không dùng ratio of sums. Một rollout train invalid làm tree invalid; validation 6 không breed; chọn lowest validation ratio, tie train fitness, node count, canonical string. Version và denominator phải đúng contract.

V2 code thực tế: penalty **1e15**, benchmark_J=None khi lỗi/timeout/incomplete; pop default=6, G default=2 (0..G), seed default=20261106, tournament=3, crossover=.8, mutation=.3, elitism=1, maxdepth4/nodes31, environment seed0, timeout30s. Official v2 run config: G=3, seed20261109. Không nhập nhằng default CLI với saved run config.

**VERIFIED mismatch:** official descriptor `dpdp_official_experiment_v1.json` ghi penalty=1e9 trong khi code/config dùng 1e15; field `split_protocol_sha256` lại là source-manifest hash cf7239..., không phải split hash 21c7f6.... Trainer đọc split và CLI args, không enforce toàn bộ descriptor official. Tài liệu giai đoạn cũ không đủ làm chứng nhận protocol adherence.

`dpdp_gp_fitness.py:cache_key/context` hash canonical tree + context: version gp-final-j-v2, instance, data hashes, all selected Python source hashes, split/source manifest/reference hashes, numeric policy/limits, evolution/environment seed, wall budget, settings, Python executable/version/packages. Cache hit kiểm context/key và log hash, không audit lại mọi cached result artifact. Code changes hoặc absolute-path/executable khác có thể đổi key. Nguồn `RolloutEvaluator.evaluate, context, verify_pins`.

V3 evaluator chỉ offline, không có v3 rollout cache/trainer hoàn chỉnh. Không reuse v2 cache hoặc chỉ đổi label fitness_version. Cần bind explicit contract, normalized-reference hash, feature/ranker code, scorer/sim versions, budget/seed/data; đánh giá validity lại ở cache hit theo protocol mới. Đây là **đề xuất**, chưa được triển khai.

## Sealed policy và sự cố lịch sử

Audit này tuân thủ cấm mở CSV 7–8/15–16. Chỉ đọc metadata split/protocol để xác nhận role và code guard. `dpdp_dataset.py`, loader case study, scorer CSV reader gọi `require_development_path`; `prepare_dpdp_data.py:verify_existing` skip sealed records và instance loader. V3 reference allowlist chỉ development IDs. `dpdp_sealed.py` tự nói đây là application boundary, không chặn arbitrary OS read/copies đổi tên; chưa có bypass final evaluation development.

**REPORTED incident:** `vnsme_evidence/v3_reference_supervision_20261109_r1/REPORT.md` ghi test discovery từng gọi verify_existing đọc bytes/checksum/schema/loader của sealed CSV. Báo cáo nói không rollout/scoring/selection. Summary independent audit xác nhận có incident. Cần lưu disclosure và quyết định tác động methodology; không tự đổi split hoặc khẳng định “chưa bao giờ mở test”. Guard về sau không xóa lịch sử đó.

## Acceptance checklist và quyết định hiện tại

Để một **run** được nhận: có input/source/build/protocol hashes, identical settings, result valid + complete, ledger toàn bộ item delivered, guard mỗi dispatch, đủ trace/epoch markers/outputs, independent replay/scorer khớp D/T/J, supervisor EXITED0 không gaps/leaks, không hard timeout; record checksum và re-audit khớp.

Để một **reference bộ** được nhận: đúng duy nhất 2–6 và vai trò, lựa chọn canonical run được lập trước dựa quy tắc không cherry-pick, mọi row qua audit, assemble vào output mới, `load_reference(summary,{2,3,4,5,6})` PASS, summary hash đóng băng. Hiện từng instance đã PASS nhưng bộ này **chưa có**.

Để **GP v3 training GO**: reference bộ đã chứng nhận; protocol v3 mới enabled và đóng băng đúng split/penalty/seeds/config/model selection; trainer/evaluator/cache thật sự opt-in v3; read guards và bounded synthetic checks có evidence; source/environment archive xác định được. Hiện **NO-GO**: thiếu canonical combined summary, training protocol v3 vẫn disabled, trainer hiện là v2; run-selection và historical sealed disclosure còn cần xử lý.

Để **final evaluation GO**: chỉ sau train/selection đóng băng model/tree/hash, kết thúc tuning, xử lý sealed incident và xác định quyền mở final test trong workflow riêng được người dùng cho phép; so sánh contract/scorer/budgets/metrics nhất quán. Nhiệm vụ audit này không cho phép mở test. Không đề xuất chạy sealed để debug bất kỳ blocker nào.
