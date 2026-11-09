# GP pilot: xếp hạng ứng viên chèn DPDP

Ngày: 05/11/2026, Asia/Bangkok.

**Kết quả chính: đã triển khai và chạy GP pilot; chưa có bằng chứng GP tốt hơn baseline.**
Cây được chọn là `(delta_distance_km + delta_tardiness_seconds)`. Nó đã có trong quần thể khởi tạo;
hai thế hệ tiến hóa không cải thiện fitness. Trên cả hai instance đối chiếu, cây này tạo log trùng từng byte với baseline.

## 1. Môi trường, mã và bảo toàn

- Repository: `C:\Users\Cuongdz\Documents\LA\dvrpsim`.
- Interpreter: `C:\Users\Cuongdz\Documents\LA\dvrpsim\.venv\Scripts\python.exe`, Python 3.14.4, dvrpsim 0.0.1 editable, SimPy 4.1.2.
- Commit nền: `29f4cd8f481fa5ac8cbf97a1372ee5b845e20c4a`, main; không commit/push.
- Đã đọc baseline report, mã baseline/guard/forecast/scorer. Không tìm thấy AGENTS.md áp dụng trên chuỗi thư mục cha hoặc trong repository ngoài .git/.venv đã loại trừ.
- Kiểm tra SHA-256 trước/sau trên 159 tệp có sẵn: chỉ sửa `dpdp_insertion.py` và `run_dpdp_insertion.py`; 157 tệp khác giữ nguyên từng byte.
- CSV, scorer, guard, forecast, các audit, log, kết quả baseline và bằng chứng cũ giữ nguyên. Bản sửa departure_times dùng vehicle_id vẫn nguyên vẹn.
- Manifest từng rollout lưu source hashes, data hashes, commit, thay đổi chưa commit, Python/packages, vị trí xe, seed và cấu hình. Không cài thêm thư viện.

Tệp sửa:

| Tệp | Thay đổi |
|---|---|
| `dpdp_insertion.py` | Hook score_function tùy chọn, kiểm tra kết quả finite; thêm ranking_score riêng với delta_score dự báo |
| `run_dpdp_insertion.py` | Cùng runner cho demo/baseline/gp; insertion là alias cũ; nạp cây, chọn instance, giới hạn wall time, telemetry cây |

Tệp mới:

| Tệp | Chức năng |
|---|---|
| `dpdp_gp.py` | Biểu diễn/kiểm tra cây, số học bảo vệ, lưu/nạp, khởi tạo, tournament, crossover, mutation, elitism |
| `dpdp_gp_fitness.py` | Rollout mới trong subprocess, fitness từ scorer độc lập, deadline và cache có provenance |
| `train_dpdp_gp.py` | Smoke trước tiến hóa và protocol pilot nhỏ cố định |
| `test_dpdp_gp.py` | 15 kiểm tra mới |
| `GP_PILOT_REPORT.md` | Báo cáo này |
| `gp_evidence/` | Trạng thái trước sửa, snapshot mã, kiểm tra cuối, khóa cây và bảo toàn |
| `gp_runs/pilot_20261105_v2/` | Pilot hoàn tất, model tốt nhất, cache, toàn bộ rollout và diễn biến thế hệ |
| `gp_runs/comparison_20261105/` | Bốn lượt baseline/GP đối chiếu mới |
| `gp_runs/demo_adapter_smoke/` | Chứng minh adapter demo vẫn chạy đúng |

`gp_runs/pilot_20261105/` giữ lại lượt phát triển bị lỗi lưu Decimal vào cache, không được dùng làm kết quả pilot.
Đã sửa serialization benchmark_J thành chuỗi và thêm regression test cache bằng rollout thật, trước khi huấn luyện lại hoặc đánh giá instance_17.

## 2. Ranh giới GP và baseline

GP chỉ thay giá trị scalar dùng trong tuple chọn ứng viên:

```text
(ranking_score, vehicle_id, pickup_index, delivery_index)
```

Quan sát đơn, chia nhóm, enumeration mọi cặp pickup/delivery trong suffix, guard, forecast toàn đội xe,
đặc trưng, thứ tự xử lý đơn, no-merge và phá hòa được dùng lại nguyên từ baseline.
Kiểm tra AST xác nhận các hàm/classes Snapshot, split_observed_orders, candidates, extract_features,
min_residual và insertion_score không đổi. Guard, forecast và scorer cũng khớp SHA-256 trước sửa.

Baseline mặc định vẫn dùng:

```text
delta_D / N + 10000 * delta_T / 3600
```

N là toàn bộ số xe. Không chỉnh công thức hoặc tham số baseline sau khi xem GP.
Log baseline mới trên instance_1 còn trùng từng byte với kết quả baseline trước bước GP này.

`TreeRanker` nhận đúng năm scalar dưới đây. Tham số vehicle_num được giữ chỉ để khớp chữ ký gọi baseline,
nhưng **không được chuyển vào cây**, không phải terminal. Cây không giữ model, log, instance ID hoặc metadata huấn luyện.

| Terminal, theo thứ tự lưu trong model | Đơn vị |
|---|---|
| delta_distance_km | km, toàn đội xe |
| delta_tardiness_seconds | giây, gom theo đơn gốc |
| delta_waiting_seconds | xe-giây, toàn đội xe |
| new_order_slack_seconds | giây |
| min_residual_capacity | đơn vị pallet chuẩn |

Không thêm đặc trưng và không đọc đơn tương lai. Không chuẩn hóa dữ liệu bằng thống kê của instance_17.
Phép cộng cây có thể kết hợp các scalar khác đơn vị như một hàm xếp hạng số học; đây không phải công thức điểm benchmark mới.

## 3. Biểu diễn và an toàn số học

- Node có loại feature, const hoặc phép toán nhị phân `+`, `-`, `*`, `/`.
- Khởi tạo hằng ngẫu nhiên uniform [-2,2], làm tròn 3 chữ số; có thể lai/đột biến cùng các terminal khác.
- Chia bảo vệ: nếu `abs(mẫu) <= 1e-9`, trả tử số; nếu không, chia bình thường.
- Giá trị finite đầu vào và sau mỗi phép toán được bão hòa vào [-1e12,1e12]. NaN/Inf hoặc lỗi chuyển kiểu phát sinh NumericTreeError; không âm thầm thay bằng một thứ hạng hợp lệ.
- Hằng số khi nạp phải finite và nằm trong [-1e12,1e12]. Unknown feature/operator/schema bị từ chối.
- Độ sâu tối đa 4, tính root là 0; tối đa 31 node. Kiểm tra khi nạp/khởi tạo/variation. Crossover hoặc mutation thử tối đa 10 proposal; nếu không đạt giới hạn thì giữ parent.
- Không dùng eval hoặc thực thi Python từ tệp cây.

Model `best_tree.json` có expression đọc được, cấu trúc JSON, SHA-256 cây, primitive set,
thứ tự/đơn vị terminal, numeric policy, giới hạn cây, tham số/seed GP và source hashes.
Nạp cây để chạy lại không cần huấn luyện.

## 4. Fitness, invalid và cache

Fitness không phải ranking_score hoặc delta_score tại quyết định.
Mỗi rollout bắt đầu một subprocess với simulator mới, cùng CSV và seed vị trí xe 0.
Sau khi mọi item hoàn tất và guard đạt, runner chấm log bằng verify_dpdp_score.
Fitness evaluator còn **đọc lại log và gọi scorer độc lập ở parent**, so khớp D/T/J và số item/đơn hoàn tất với runner.

```text
fitness hợp lệ = float(J benchmark từ quỹ đạo hoàn tất)
invalid fitness = 1e15, benchmark_J = null, valid = false
```

Chuỗi J đầy đủ được giữ trong artifact; float chỉ dùng cho lựa chọn tiến hóa.
Penalty không được xuất như một điểm benchmark hợp lệ. Missing item, lỗi guard, exception,
cây lỗi số học/schema, hết horizon hoặc deadline đều không có J hợp lệ.

Huấn luyện đặt hard timeout **10 giây cho subprocess rollout**; parent có thể còn tốn thời gian kiểm chứng/cache.
Trường `process_wall_seconds` trong fitness record đo cả đoạn kiểm chứng sau subprocess,
nên có thể hơi lớn hơn 10 giây cho một rollout con đã hoàn tất trước deadline;
`request_wall_seconds` còn bao gồm xây key/cache. Tổng wall time pilot đo tất cả các phần này.
Các lượt đối chiếu cuối có deadline 60 giây cho cả tiến trình runner, giống nhau cho baseline/GP.

Cache key gồm cây canonical, instance, hashes của cả bốn CSV, environment seed và evolution seed,
toàn bộ cấu hình ảnh hưởng rollout (dispatch/docking/loading/unloading/lambda/horizon/deadline), numeric policy/limits,
source hashes của mã Python liên quan, Python executable/version và package versions.
Cache hit kiểm tra lại context/key và hash log. Cache không chỉ khóa theo chuỗi biểu thức.
Một forced fresh repeat không ghi đè cache cũ và phải cho cùng validity/J/log hash.

## 5. Dữ liệu thật và protocol đã khóa

Kiểm kê trực tiếp thư mục dữ liệu:

| Instance có trên máy | Xe | Đơn gốc | Item | Vai trò |
|---|---:|---:|---:|---|
| instance_1/50_1.csv | 5 | 50 | 95 | Smoke, train và đối chiếu mô tả |
| instance_17/300_1.csv | 20 | 300 | 592 | Chỉ đối chiếu sau khi lưu/khóa cây |

Không có 64 instance local. Validation=[] và test=[]: **không có một thiết kế train/validation/test độc lập**.
Instance_17 không được dùng chọn cây hoặc chỉnh GP; một instance khác quy mô trên cùng mạng nhà máy vẫn chưa đủ để kết luận tổng quát hóa.

`protocol.json` được ghi trước smoke và tiến hóa. Model tốt nhất được ghi trước mọi đánh giá instance_17;
`gp_evidence/frozen_model.json` lưu mã băm tệp model trước khi bắt đầu đối chiếu.
Kiểm tra sau đối chiếu xác nhận tệp cây và nguồn code không đổi.

## 6. Smoke và cấu hình tiến hóa thực tế

Smoke dùng cây `(delta_distance_km + delta_tardiness_seconds)` trên instance_1:

- Rollout hợp lệ, J=170.54 từ scorer cuối.
- Có các lần gọi cây tại quyết định; không rơi về baseline mặc định.
- Một lần gọi lại trúng cache; một lần forced repeat tạo simulator mới cho cùng log hash/J.
- Kết quả trong `pilot_20261105_v2/smoke.json`.

Đây là cấu hình đo chi phí pilot, **không phải tối ưu tham số**:

| Tham số | Giá trị |
|---|---|
| Seed RNG tiến hóa | 20261105, random.Random riêng |
| Quần thể | 6 |
| Thế hệ | Gen 0 khởi tạo + 2 thế hệ tiến hóa |
| Khởi tạo | Hai seed đơn giản ΔD, ΔD+ΔT; bốn cây grow/full có seed, depth 1–3 |
| Tournament | 3 |
| Crossover | 0.8 |
| Mutation | 0.3, độc lập sau crossover |
| Elitism | 1 |
| Giới hạn cây | depth 4, 31 node |
| Objective | Mean J trên train (hiện chỉ instance_1); cùng J thì ưu tiên cây nhỏ hơn rồi canonical JSON |

Các phép variation/select dùng cùng RNG đã ghi; policy rollout không dùng ngẫu nhiên.
Không cộng complexity penalty vào J; kích thước cây chỉ phá hòa fitness bằng nhau.

## 7. Kết quả tiến hóa và các trường hợp thua

| Thế hệ | Best fitness J | Cá thể invalid trong quần thể | Cache hit |
|---|---:|---:|---:|
| 0 | 170.54 | 4/6 | 1/6 |
| 1 | 170.54 | 1/6 | 3/6 |
| 2 | 170.54 | 1/6 | 5/6 |

Tổng wall time smoke + train: **75.058152 giây**.
21 yêu cầu đánh giá gồm smoke/cache/repeat và 18 lượt population; 10 cache hit;
11 subprocess thực (10 genotype khác nhau và một forced repeat).
5 subprocess hoàn tất hợp lệ, 6 timeout; 6 cây invalid khác nhau; không có numeric-tree-error request trong pilot thực.
Các test riêng vẫn xác nhận NaN/Inf/schema sai được từ chối.

Một số cây đã chạy hợp lệ nhưng **thua baseline J=170.54** trên instance_1:

| Cây | J thực |
|---|---:|
| delta_distance_km | 9992094.551111… |
| delta_tardiness_seconds | 196.52 |
| ((delta_waiting_seconds * delta_distance_km) * (new_order_slack_seconds - delta_tardiness_seconds)) + delta_tardiness_seconds | 196.52 |

Sáu cây timeout giữ fitness phạt 1e15, benchmark_J=null. Không bỏ chúng khỏi thống kê.
Cây tốt nhất 3 node, depth 1 đã nằm trong khởi tạo; không có cải thiện do các thế hệ sau.
Toàn bộ members, status, cache hit, thời gian, biểu thức và artifact paths được lưu trong generation_0/1/2.json và training.json.

## 8. Đối chiếu baseline và cây đã khóa

Tất cả lượt sau đều fresh state, seed=0, dispatch=600 giây, docking=1800 giây,
load/unload=240 giây/đơn vị, cùng guard/forecast/generator và source/data hashes.

| Instance / policy | Hoàn tất đơn/item | Hợp lệ | D (km) | T (giây) | J | Wall toàn tiến trình | Callback max |
|---|---|---|---:|---:|---:|---:|---:|
| 1 / baseline | 50/95 | Có | 852.7 | 0 | 170.54 | 0.849192 s | 0.013205 s |
| 1 / GP | 50/95 | Có | 852.7 | 0 | 170.54 | 0.889564 s | 0.013196 s |
| 17 / baseline | 300/592 | Có | 3372.3 | 25586 | 71240.837222… | 49.904519 s | 1.838959 s |
| 17 / GP | 300/592 | Có | 3372.3 | 25586 | 71240.837222… | 49.523810 s | 1.761162 s |

Wall toàn tiến trình đo ngoài subprocess, gồm startup, manifest/data/build, mô phỏng và scorer.
Thời gian mô phỏng + chấm trong runner lần lượt là 0.493951, 0.516080, 49.517114 và 49.147296 giây.
Các chênh lệch thời gian nhỏ không được coi là lợi thế tốc độ có ý nghĩa thống kê.

Trên instance_1, cả hai xét 970 ứng viên, loại 401, GP đánh giá 569 ứng viên hợp lệ.
Trên instance_17, cả hai xét 51597, loại 26256, GP đánh giá 25341 ứng viên hợp lệ.
Mỗi cặp baseline/GP có **log trùng từng byte**, không chỉ cùng J. Vì vậy chưa thấy thay đổi quyết định trên hai kịch bản này.
Điều này vẫn không biến hai hàm xếp hạng thành tương đương trên mọi trạng thái.

Kết quả nằm tại `gp_runs/comparison_20261105/`, có manifest, decisions.json,
result.json và independent_score.json cho mỗi lượt. Scorer CLI không sửa đổi đã chấm lại cả bốn log.
Adapter demo cũng hoàn tất instance_1: D=1057, T=57558, J=160094.733333…, khớp kết quả demo cũ.

## 9. Kiểm tra hồi quy

**98/98 kiểm tra PASS**: toàn bộ 83 kiểm tra cũ + 15 kiểm tra GP mới.
Đầu ra cuối: `gp_evidence/all_tests_final.txt`.

Các kiểm tra mới bao gồm chia bảo vệ tại biên epsilon, bão hòa hữu hạn,
NaN/Inf/giá trị không chuyển được, terminal/operator bị cấm, depth/node cap,
lưu/nạp/hash tamper, seed/elitism/crossover/mutation, invariance generator/guard/forecast/baseline,
cùng ứng viên nhưng cây có thể chọn xe khác, scorer cuối độc lập,
invalid/timeout không có J giả, cache key đầy đủ, cache roundtrip và fresh repeat thật,
và kiểm kê đúng instance đang tồn tại.

Giới hạn thời gian đã áp dụng thật trong pilot; test timeout bổ sung dùng giả lập để kiểm tra nhánh lỗi một cách xác định.
Không chạy huấn luyện hay chọn cây trên instance_17.

## 10. Lệnh tái chạy

Dùng output mới; runner/trainer từ chối ghi đè thư mục đã có.

```powershell
Set-Location 'C:\Users\Cuongdz\Documents\LA\dvrpsim'

& '.\.venv\Scripts\python.exe' -B -m unittest -v test_dpdp_feasibility test_dpdp_execution_guards test_dpdp_schedule test_verify_dpdp_score test_dpdp_insertion test_dpdp_gp

# Smoke và huấn luyện lại đúng pilot preset, seed 20261105:
& '.\.venv\Scripts\python.exe' -B '.\train_dpdp_gp.py' --output '.\gp_runs\pilot_rerun'

# Nạp cây đã lưu để chạy độc lập, không train lại:
& '.\.venv\Scripts\python.exe' -B '.\run_dpdp_insertion.py' --policy gp --tree '.\gp_runs\pilot_20261105_v2\best_tree.json' --instance 1 --seed 0 --wall-seconds 60 --output '.\gp_runs\gp1_rerun'
& '.\.venv\Scripts\python.exe' -B '.\run_dpdp_insertion.py' --policy baseline --instance 1 --seed 0 --wall-seconds 60 --output '.\gp_runs\baseline1_rerun'

& '.\.venv\Scripts\python.exe' -B '.\run_dpdp_insertion.py' --policy gp --tree '.\gp_runs\pilot_20261105_v2\best_tree.json' --instance 17 --seed 0 --wall-seconds 60 --output '.\gp_runs\gp17_rerun'
& '.\.venv\Scripts\python.exe' -B '.\run_dpdp_insertion.py' --policy baseline --instance 17 --seed 0 --wall-seconds 60 --output '.\gp_runs\baseline17_rerun'

# Cùng runner hỗ trợ demo; insertion vẫn là alias tương thích cũ:
& '.\.venv\Scripts\python.exe' -B '.\run_dpdp_insertion.py' --policy demo --instance 1 --output '.\gp_runs\demo_rerun'
```

Hai lượt instance_17 mất khoảng 50 giây/lượt trên máy lúc đo; tải máy có thể làm một lượt khác chạm deadline 60 giây.
Deadline 10 giây huấn luyện là một lựa chọn ngân sách pilot, không phải giới hạn 10 phút của benchmark.

## 11. Hạn chế và điều kiện để tuyên bố GP tốt hơn baseline

- Chỉ hai instance local, không có test độc lập đủ lớn; train chỉ một instance và một seed tiến hóa.
- Cây thắng là seed có sẵn, không có cải thiện fitness qua tiến hóa. Kết quả hiện tại chứng minh pipeline và tái lập, không chứng minh lợi ích học.
- Sáu timeout cho thấy nhiều cây tạo quyết định dẫn đến tuyến dài/chi phí enumeration lớn. Chưa cắt tỉa generator hoặc bỏ các thất bại này để làm kết quả đẹp.
- Các feature chưa scale/typed theo đơn vị; saturation bảo đảm tính số học nhưng có thể làm nhiều ứng viên hòa điểm ở các cây khác.
- Kế thừa giới hạn baseline: cố định công việc cũ, khóa current/first destination, không merge visit; forecast không biết các yêu cầu tương lai.
- Chưa chứng minh mọi trạng thái/sự kiện đồng thời tương đương Xingtian, chưa có kết quả nhiều mạng nhà máy hoặc toàn bộ benchmark.
- Trước khi tuyên bố GP tốt hơn cần dữ liệu train/validation/test tách ở cấp phiên/instance, nhiều seed tiến hóa,
  protocol và ngân sách khóa trước test, so chất lượng lẫn wall time theo cặp, báo cả invalid/timeout và độ phân tán.
  Nếu dùng instance_17 để điều chỉnh ở bước sau thì không còn coi nó là một đánh giá chưa dùng để chọn phương pháp.

**GP pilot đã triển khai và chạy được; hiện chưa đủ căn cứ tuyên bố GP tốt hơn baseline.**
Không còn lỗi tái hiện cản trở pipeline trong phạm vi đã kiểm tra. Phần thiếu chính là thiết kế đánh giá độc lập đủ dữ liệu/seed
và bằng chứng cây tiến hóa tạo cải thiện thực, thay vì chỉ giữ lại một hàm khởi tạo đã tốt.
