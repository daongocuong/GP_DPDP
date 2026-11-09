# Baseline chèn cặp lấy–giao DPDP

Ngày thực hiện: 05/11/2026 (Asia/Bangkok). Không triển khai hoặc huấn luyện GP.

## 1. Môi trường và bảo toàn

- Repository: `C:\Users\Cuongdz\Documents\LA\dvrpsim`, nhánh main, commit nền `29f4cd8f481fa5ac8cbf97a1372ee5b845e20c4a`.
- Interpreter: `C:\Users\Cuongdz\Documents\LA\dvrpsim\.venv\Scripts\python.exe`, Python 3.14.4; dvrpsim 0.0.1 editable, SimPy 4.1.2.
- Không tìm thấy AGENTS.md áp dụng ở các thư mục cha hoặc trong repository, ngoài .git/.venv đã loại trừ.
- Đã đọc mã demo, hai audit, API checker, vehicle/model, bộ kiểm tra độc lập và bộ dự báo trước khi triển khai.
- Giữ nguyên 108/109 tệp có sẵn theo SHA-256. Tệp có sẵn duy nhất được sửa là `dpdp_feasibility.py`, mở rộng API có tương thích ngược. Không sửa CSV, log cũ, scorer, test cũ, audit hoặc bằng chứng cũ.
- Giữ nguyên bản sửa `departure_times[vehicle_id]`; không sửa simulator hay demo policy; không commit/push hoặc cài package.
- Bằng chứng trạng thái trước và kiểm tra bảo toàn: `baseline_evidence/initial_state.json`, `preservation.json`.

## 2. Tệp sửa/tạo và API thực tế

| Tệp | Nội dung |
|---|---|
| `dpdp_feasibility.py` | Thêm tham số tùy chọn `order_demands` vào `validate`, giữ nguyên hành vi mặc định |
| `dpdp_insertion.py` | Snapshot quan sát, chia nhóm, liệt kê ứng viên, đặc trưng và chính sách greedy |
| `run_dpdp_insertion.py` | Adapter simulator, guard trước áp dụng, chạy baseline/demo, logger riêng, manifest và scorer |
| `test_dpdp_insertion.py` | 16 kiểm tra mới |
| `DPDP_INSERTION_BASELINE_REPORT.md` | Báo cáo này |
| `baseline_evidence/` | Kết quả kiểm tra, bảo toàn và đối chiếu tái lập |
| `baseline_runs/instance1_insertion_final/` | Kết quả baseline chính |
| `baseline_runs/instance1_demo_final/` | Kết quả demo đối chiếu chính |
| `baseline_runs/instance1_insertion_repeat/`, `instance1_demo_repeat/` | Lượt lặp để kiểm tra tái lập và thời gian toàn tiến trình |

Hai thư mục `instance1_*_v1` là lượt phát triển trước khi hoàn thiện metadata/thời gian; được giữ lại, không dùng thay kết quả chính.

API dùng lại:

- `dpdp_main.build_dpdp_model(probdata)` tạo đúng xe, locations, order provider và periodic updater của case study.
- `Model.routing_callback()` trả dictionary `vehicles/current_visit/next_visits`, `orders/status`; `_enforce_decision` và checker local vẫn thực hiện việc áp dụng.
- `dpdp_feasibility.validate(...)` kiểm tra từng ứng viên, rồi guard lần cuối trên raw decision trước khi trả cho simulator.
- `dpdp_schedule.predict_fixed_routes(model_view)` dự báo toàn đội xe, kể cả các xe không được chèn đơn nhưng chịu ảnh hưởng bến.
- `verify_dpdp_score.verify(...)` chấm quỹ đạo sau hoàn tất. CLI độc lập cũng đã chạy lại trên cả hai log mới và lưu `independent_score.json`.

Builder được tái sử dụng bằng factory override trong bộ nhớ để tạo RunModel; không sửa tệp builder.
Demo dùng nguyên `routing.demo_algorithm.routing` qua `dpdp_module_routing`, chỉ chuyển thư mục tương tác sang output riêng.

## 3. Chính sách và giới hạn không gian tìm kiếm

1. Snapshot chỉ đọc `model.orders`, là tập đã được order_provider công bố; không đọc danh sách đơn tương lai trong private_data. Chỉ các bảng khoảng cách/thời gian và tham số tĩnh được đọc từ private_data.
2. Giữ nguyên current visit. Điểm đến đầu tiên đã công bố giữ nguyên cả visit và thời điểm đến; metadata ETA được tính từ bộ dự báo hoặc phần đường đang chạy. Đây là lựa chọn bảo thủ của baseline, kể cả khi simulator cho phép sửa thêm danh sách ở destination.
3. Giữ nguyên xe, thứ tự tương đối của mọi visit và mọi thao tác cũ. Không tái phân công, hoán đổi hoặc cải thiện lại công việc đã phân công.
4. Đơn chưa phân công được xử lý theo `(due, release, original_order_id)`.
5. Trong đơn, sắp item theo quantity giảm dần, rồi item ID tăng dần. Chia next-fit: thêm item vào nhóm hiện tại cho tới khi item tiếp theo làm vượt tải, rồi mở nhóm mới. Nếu cả đơn vừa tải, chỉ có một nhóm. Không chia nhỏ item. Nhóm chứa item vượt capacity làm lượt chạy thất bại rõ ràng vì không phục vụ được item nguyên vẹn.
6. Với mỗi nhóm, xét từng xe theo ID, từng vị trí pickup trong suffix được sửa và từng vị trí delivery sau pickup. Hai visit mới **không cần kề nhau**. Không có cắt tỉa theo khoảng cách, số ứng viên, hoặc ngân sách tìm kiếm.
7. Không gộp visit cùng nhà máy trong phiên bản này: mỗi visit riêng vẫn chiếm bến và có đầy đủ docking_time theo simulator. Đây là giới hạn biểu diễn/search, không phải bỏ docking để giảm điểm.
8. Mọi ứng viên đi qua guard trước forecast. Loại theo tải/LIFO/chia đơn/khóa/thiếu-trùng item, không theo độ trễ.
9. Chọn điểm nhỏ nhất; nếu điểm bằng nhau theo số tính được, phá hòa `(vehicle_id, pickup_index, delivery_index)`. Cập nhật cả plan và forecast sau mỗi nhóm.

Đây là **baseline chèn vào tuyến cũ cố định**, không phải tối ưu lại toàn bộ tuyến hoặc CFA-VNS.

Trong lượt chính có 51 nhóm từ 50 đơn gốc, vì có đơn vượt tải. Có **3 nhóm được chọn chèn không kề nhau**.

## 4. Giao diện ứng viên và đặc trưng dùng chung

Các hàm trong `dpdp_insertion.py` là giao diện dùng lại về sau:

```text
Snapshot.observe(model)
split_observed_orders(observed_orders, capacity)
candidates(snapshot, plans, group, admitted_ids, before_metrics, stats)
extract_features(snapshot, before, after, group, vehicle, plan)
insertion_score(features, vehicle_num)
```

`Candidate` chứa xe, hai chỉ số chèn, toàn bộ plans, features và metrics dự báo. Chưa có cây GP, primitive set hay vòng học.

| Đặc trưng | Định nghĩa | Đơn vị |
|---|---|---|
| `delta_distance_km` | Thay đổi tổng quãng đường còn lại của toàn đội | km |
| `delta_tardiness_seconds` | Thay đổi tổng trễ dự báo, gom theo original order và lấy item muộn nhất | giây |
| `delta_waiting_seconds` | Thay đổi tổng thời gian chờ bến của toàn đội | xe-giây |
| `new_order_slack_seconds` | Due trừ completion muộn nhất của original order mới trong phần đã đưa vào plan | giây |
| `min_residual_capacity` | Tải dư nhỏ nhất sau từng thao tác trên tuyến còn lại của xe được chèn, kể cả hàng ban đầu | đơn vị pallet chuẩn |

Lịch hiện tại đang phục vụ giữ đủ arrival/start/duration gốc. Khi có item đã dỡ nhưng visit chưa kết thúc,
forecast dùng arrival tính completion, không dùng thời điểm dỡ tạm thời trong trạng thái Order.
Current/future completions được ghép với các item đã hoàn tất để tổng hợp theo đơn gốc.

Quãng đường đã chạy là hằng số tại một quyết định và triệt tiêu trong delta. Phần đường đang chạy được tính như một chặng cố định ở cả trước và sau nên cũng triệt tiêu.

Nhóm chưa chèn chưa có một lịch hoàn thành làm mốc: so với plan hiện tại, phần trễ mới của nó được cộng vào chi phí; phần trễ của công việc cũ được tính lại.
Với một đơn quá tải có nhiều nhóm, mỗi bước dùng max completion của các nhóm đã chèn; các nhóm sau cập nhật lại max này.
Slack ở bước trung gian do đó chỉ nói về phần đã chèn, chưa phải cam kết cho những nhóm còn chưa xử lý.

Mở rộng `validate(..., order_demands=...)` là cần thiết để kiểm tra từng nhóm tăng dần: tổng demand của đơn gốc phải lấy từ **toàn bộ item đã quan sát**, không được tính nhầm bằng tổng nhỏ của nhóm đang chèn.
Guard vẫn đòi phục vụ đủ mọi item trong tập admitted; các request chưa được chấp nhận không bị giả làm đã giao để qua kiểm tra.

Điểm chọn ứng viên:

```text
delta_J_hat = delta_distance_km / N + 10000 * delta_tardiness_seconds / 3600
N = toàn bộ số xe, kể cả xe không được chọn
```

Thời gian chờ, slack và tải dư được xuất như đặc trưng dùng chung; baseline này chỉ dùng D và T trong công thức trên.
Điểm cuối được chấm từ log thực bằng scorer độc lập, không dùng delta_J_hat thay cho điểm thực.

## 5. Không có ứng viên, hoàn tất và logging

Nếu không có ứng viên, policy ghi BASELINE_DEFER cùng nhóm/item và mã lỗi, giữ request mở, giữ plan hiện có.
Case study đã có periodic_updater mỗi 600 giây với stop_after_last_order_request=False;
nó tiếp tục gọi routing khi còn open order, nên policy sẽ thử lại ở kỳ sau. Không tạo một tuyến sai hoặc tự reject request.

Runner có safety horizon 7 ngày mô phỏng để không chờ vô hạn trong lượt thất bại. Nếu chạm horizon, có exception,
hoặc thiếu item, result có `valid=false`, `score=null`, process exit 1 và failure.json. Đây là giới hạn bảo vệ runner,
không phải điều kiện phục vụ/benchmark mới. Các lượt chính kết thúc tự nhiên trước horizon, không bị giới hạn này tác động.

Output phải chưa tồn tại. Logger được cấu hình riêng, không khởi tạo file handler dvrp.log mặc định.
Log mới ghi cả các chuyển tiếp logic cùng nhà máy (0 km), vì logger demo mặc định bỏ các dòng arrival/departure đó,
có thể làm mất arrival của visit mới trong công cụ kiểm chứng. Chỉ làm đầy đủ dấu vết, không đổi hành vi hoặc thời gian phục vụ.
Logger này giống nhau giữa hai chính sách; log cũ giữ nguyên.

## 6. Kiểm tra

**83/83 kiểm tra PASS**: toàn bộ 67 kiểm tra cũ và 16 kiểm tra mới.
Đầu ra thật: `baseline_evidence/all_tests.txt`.

Các ca mới:

- Liệt kê đủ cặp vị trí trong suffix; có ứng viên hợp lệ pickup/delivery không kề nhau; mọi công việc cũ là subsequence giữ nguyên.
- Ứng viên LIFO sai và quá tải bị loại trước forecast; số lần forecast đúng bằng số ứng viên hợp lệ, cộng forecast mốc.
- Đơn vừa tải 15 gồm hai item 7.5 ở cùng xe; đơn 20 chia 10+10; item 16 báo lỗi.
- Thứ tự EDD/release/ID, chia nhóm và phá hòa xác định.
- Current đang phục vụ và destination xe đang chạy được giữ nguyên; chưa enforce thì live plan không bị mutate.
- Request chưa có ứng viên vẫn mở, không có accepted route giả; kỳ sau thử lại thành công khi bỏ điều kiện chặn trong fixture.
- Đặc trưng queue phản ánh **xe khác**: chèn V1 làm V2 tăng chờ 2030 giây, không chỉ đánh giá xe được chọn.
- Hai item của một đơn tới Q=2310, due=1000: delta T=1310, không phải 2620; slack âm vẫn được chấp nhận.
- Forecast của plan đã chọn khớp completion thực trong fixture tuyến cố định, không phát thêm đơn.
- Lượt không hoàn tất không có score; output cũ không bị ghi đè.
- API guard mở rộng từ chối full demand không nhất quán; 67 ca mặc định cũ vẫn PASS.

## 7. Hai lượt đối chiếu chính trên instance_1

Cùng 5 xe, 50 đơn gốc, 95 item, seed vị trí ban đầu 0, dispatch=600 giây,
docking=1800 giây, load/unload=240 giây/đơn vị. Cả hai manifest có cùng source hashes,
data hashes và vị trí khởi tạo. Không đổi chính sách demo, chỉ chuyển I/O vào thư mục riêng và thêm guard.

| Chỉ tiêu | Chèn cặp | Demo gốc |
|---|---:|---:|
| Đơn gốc hoàn thành | 50/50 | 50/50 |
| Item hoàn thành | 95/95 | 95/95 |
| Guard trước áp dụng + scorer độc lập | Hợp lệ | Hợp lệ |
| Tổng quãng đường D | **852.7 km** | 1057 km |
| Tổng trễ T theo đơn gốc | **0 giây** | 57558 giây |
| Số đơn trễ | 0/50 | 10/50 |
| Điểm J thực | **170.54** | 160094.733333… |
| FINISH mô phỏng | 101400 giây | 106200 giây |
| Số kỳ routing | 169 | 177 |
| Ứng viên xét | 970 | Không áp dụng |
| Ứng viên bị loại | 401 (389 LIFO, 12 tải) | Không áp dụng |
| Ứng viên qua forecast | 569 | Không áp dụng |
| Nhóm phải defer | 0 | Không áp dụng |

Demo chạy mới khớp D/T/J đã báo trước đây, không dùng lại log cũ làm kết quả lượt chạy mới.
Scorer kiểm tra mọi item được yêu cầu/lấy/giao đúng một lần, các chặng xe và arrival; guard bổ sung tính khả thi tại mỗi quyết định.
Điều này không phải chứng minh toàn bộ simulator tương đương Xingtian.

## 8. Thời gian chạy thực và chi phí ứng viên

Mọi thời gian phần này tính bằng **giây thực** dùng perf_counter, không phải giây mô phỏng.

| Phạm vi đo | Chèn cặp | Demo |
|---|---:|---:|
| Mô phỏng + callback + áp dụng, lượt chính | 0.395316 | 0.636967 |
| Phần trên + chấm độc lập, lượt chính | 0.481659 | 0.736074 |
| Tổng thời gian callback, gồm guard cuối | 0.348493 | 0.576722 |
| Callback trung vị | 0.00116150 | 0.00316570 |
| Callback p95, nearest rank | 0.00836790 | 0.00449050 |
| Callback lớn nhất | 0.01427130 | 0.00767710 |
| Toàn tiến trình lượt lặp: khởi động interpreter, manifest/data/build, mô phỏng, score và ghi kết quả | 0.894738 | 1.161359 |

Thời gian từng callback, gồm thời điểm mô phỏng tương ứng, nằm trong `decisions.json` của từng lượt.
Baseline còn lưu thời gian nội bộ và features ứng viên được chọn. Trong lượt chính:

- Kiểm tra khả thi 970 ứng viên: tổng 0.107660 giây.
- Forecast/metrics 569 ứng viên hợp lệ: tổng 0.065936 giây.
- Các số này không gồm mọi forecast mốc/snapshot hoặc guard cuối, nên không được cộng và gọi là toàn thời gian policy.

Demo có I/O JSON qua thuật toán gốc, trong khi baseline chạy trực tiếp trong bộ nhớ; vì vậy không quy chênh lệch thời gian toàn callback thành lợi thế thuần thuật toán.
Instance_1 nhỏ, không có cắt tỉa và chưa cần đề xuất cắt tỉa. Không suy từ các số này rằng đã đáp ứng ngân sách 10 phút trên mọi quy mô benchmark.

## 9. Manifest và tái lập

Mỗi run folder chứa:

- `manifest.json`: commit/branch, trạng thái chưa commit, tracked diff, hashes mọi source Python, executable/version, packages,
  hashes dữ liệu, seed, vị trí ban đầu, tham số, đơn vị features và safety horizon.
- `simulation.log`: quỹ đạo mới đầy đủ.
- `decisions.json`: thời gian từng kỳ và telemetry policy; baseline còn có counters, lý do loại, ứng viên được chọn và features.
- `result.json`: kết quả hoàn tất, thời gian, counts và điểm thực.
- Hai lượt chính có thêm `independent_score.json`: kết quả CLI của scorer không sửa đổi, kèm mã băm log, scorer và interpreter.
- Demo có thư mục `interaction/` riêng; không ghi vào thư mục tương tác demo cũ.

Lặp lại cả hai chính sách với cùng cấu hình: **log simulation.log trùng từng byte**, và điểm độc lập trùng hoàn toàn.
Wall time khác nhau tự nhiên giữa các lượt. `baseline_evidence/comparison.json` lưu kiểm tra tái lập,
đối chiếu cấu hình và thời gian toàn tiến trình; `independent_verification.json` lưu mã băm và D/T/J từ CLI độc lập.

Lệnh tái chạy; chọn thư mục output mới nếu các thư mục bên dưới đã tồn tại:

```powershell
Set-Location 'C:\Users\Cuongdz\Documents\LA\dvrpsim'

& '.\.venv\Scripts\python.exe' -B -m unittest -v test_dpdp_feasibility test_dpdp_execution_guards test_dpdp_schedule test_verify_dpdp_score test_dpdp_insertion

& '.\.venv\Scripts\python.exe' -B '.\run_dpdp_insertion.py' --policy insertion --output '.\baseline_runs\instance1_insertion_rerun'
& '.\.venv\Scripts\python.exe' -B '.\run_dpdp_insertion.py' --policy demo --output '.\baseline_runs\instance1_demo_rerun'

& '.\.venv\Scripts\python.exe' -B '.\verify_dpdp_score.py' '.\baseline_runs\instance1_insertion_rerun\simulation.log'
& '.\.venv\Scripts\python.exe' -B '.\verify_dpdp_score.py' '.\baseline_runs\instance1_demo_rerun\simulation.log'
```

## 10. Giới hạn và GP pilot

- Chỉ một instance được đối chiếu; chưa có thống kê nhiều instance/seed và chưa đo quy mô lớn. Kết quả tốt hơn dummy demo không chứng minh ưu thế tổng quát.
- Không di chuyển công việc cũ, không sửa current/first destination và không thử gộp visit: những giới hạn này phải giữ chung khi so baseline và GP dùng cùng ứng viên.
- Forecast tuyến cố định không biết đơn tương lai; các lần routing sau có thể chèn thêm việc và thay đổi lịch thực. Đây là giới hạn dự báo, không phải quyền đọc trước tương lai.
- Thứ tự sự kiện đồng thời phức tạp chưa được chứng minh tương đương ở mọi trạng thái; các fixture nhỏ và instance_1 không bao phủ toàn benchmark.
- Guard dựa trên snapshot và original demand đã quan sát. Không dùng API với danh mục item giả, thiếu demand gốc, fleet dị chủng hoặc thêm ràng buộc ngoài DPDP đã kiểm chứng.
- Baseline chưa có vòng huấn luyện, split train/validation/test, cache fitness hay xử lý cây lỗi số học. Những phần đó thuộc bước GP sau này, chưa được triển khai.

**Baseline đủ điều kiện bắt đầu GP pilot nhỏ dùng chung split/group, candidate generator, features, guard và scorer hiện có.**
Không còn lỗi cản trở được tái hiện trong phạm vi kiểm tra và instance_1. Pilot phải giữ cùng không gian ứng viên,
không dùng các số đo một instance này làm kết luận nghiên cứu hoặc bảo đảm thời gian cho mọi quy mô.
