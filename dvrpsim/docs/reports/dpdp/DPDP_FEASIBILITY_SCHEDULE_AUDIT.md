# Kiểm chứng tính khả thi và lịch dự báo DPDP

Ngày: 05/11/2026, Asia/Bangkok. Đã đọc `DPDP_SCORING_AUDIT.md`; không làm lại audit chấm điểm.
Không thấy AGENTS.md áp dụng trên chuỗi thư mục cha hoặc trong repository (loại .git/.venv).

## 1. Môi trường, Git và bảo toàn dữ liệu

- Interpreter: `C:\Users\Cuongdz\Documents\LA\dvrpsim\.venv\Scripts\python.exe`.
- Python 3.14.4, Windows AMD64; dvrpsim 0.0.1 editable, SimPy 4.1.2.
- Git: nhánh main, commit nền `29f4cd8f481fa5ac8cbf97a1372ee5b845e20c4a`.
- Trước làm việc, các tệp audit chấm điểm, test, script và một số tệp run_logs đã là untracked. Không stage, commit hoặc push.
- Lưu trạng thái Git và SHA-256 của **95 tệp có sẵn** trong `feasibility_schedule_evidence/initial_state.json`.
- Đối chiếu sau thực thi: chỉ `examples/case_studies/dpdp/dpdp_routing.py` đổi đúng một dòng; **94 tệp còn lại giữ nguyên byte**, gồm CSV, log cũ, công cụ và test chấm điểm, tài liệu cũ.
- Simulator thử nghiệm dùng subclass chỉ thay logging/init trong fixture; không tạo logger mặc định vì logger đó có thể mở dvrp.log ở chế độ ghi đè. Lỗi thực thi được để propagate qua env.run(), không bị Model.run() bắt rồi chỉ ghi log.

Tệp sửa:

```text
examples/case_studies/dpdp/dpdp_routing.py   # vehicle.id -> vehicle_id, đúng một dòng
```

Tệp mới:

```text
dpdp_feasibility.py                       # bộ kiểm tra độc lập, không import simulator
dpdp_schedule.py                          # lịch FCFS cho tuyến cố định từ snapshot
dpdp_audit_fixtures.py                    # mô phỏng nhỏ bằng DPDPVehicle thực
test_dpdp_feasibility.py                  # 37 kiểm tra
test_dpdp_execution_guards.py             # 3 kiểm tra đối chiếu thực thi
test_dpdp_schedule.py                     # 12 kiểm tra
DPDP_FEASIBILITY_SCHEDULE_AUDIT.md
feasibility_schedule_evidence/
    initial_state.json
    dpdp_routing_before.py.txt
    departure_before.txt
    xingtian_checker.py.txt
    after_tests.txt
    schedule_rows.json
    preservation_check.json
```

## 2. Nguồn và quy tắc khóa

Đọc mã local: `src/dvrpsim/utils/checker.py`, `elements/vehicle.py`, `elements/order.py`,
`model.py`, và mã/tài liệu case study DPDP.
Đọc checker Xingtian tại cùng commit tham chiếu của audit trước:
`e4ef3a1c92d19d1d08c3ef0e2156b6fecefdbe04`.

Nguồn khóa/chia đơn:
https://github.com/huawei-noah/xingtian/blob/e4ef3a1c92d19d1d08c3ef0e2156b6fecefdbe04/simulator/dpdp_competition/src/utils/checker.py

Bản nguồn nguyên giấy phép lưu tại `feasibility_schedule_evidence/xingtian_checker.py.txt`.

Các điểm cần phân biệt:

1. Local checker cấm đổi nhà máy đích khi xe đang chạy, và cấm sửa current visit khi `service_start_time is not None` (kể cả đã phục vụ xong). `_apply_decision` chỉ sửa danh sách công việc current visit, không di chuyển xe tới một nhà máy khác.
2. Xingtian `__is_returned_destination_valid` giữ **factory và arrive_time** của destination đã có. Hàm này không yêu cầu toàn bộ danh sách pickup/delivery ở destination phải giữ nguyên.
3. Bộ kiểm tra mới vì vậy giữ factory/arrival của destination đã cam kết; giữ current lists khi service đã bắt đầu; **không khóa cả suffix tương lai** và không tự khóa mọi destination operation list.
4. Với current visit đã khóa, Plan dùng nội dung giống snapshot biểu thị giữ nguyên; adapter áp dụng sau này phải hiểu đây là no-op, không gửi một yêu cầu thay thế current_visit tới local checker.
5. Chia đơn: nguồn gốc phát hiện cả phân cho nhiều xe lẫn lấy cùng đơn tại nhiều pickup visit. Chỉ được làm vậy nếu tổng demand đơn gốc vượt sức chứa xe đồng nhất. Đơn không vượt tải vẫn có thể có nhiều item, nhưng phải lấy trong một batch; item là ID nguyên vẹn.

## 3. Bộ kiểm tra độc lập và hợp đồng đầu vào

`dpdp_feasibility.validate(items, fleet, plans, delivered=...)` nhận:

- Danh mục item chuẩn: quantity, original order, nhà máy lấy/giao; không cho quyết định tự sửa quantity.
- Snapshot đáng tin: stack đáy -> đỉnh, current visit và cờ service_started, destination cam kết.
- **Kế hoạch đầy đủ cho các item đã công bố được đưa vào kiểm tra**, không phải tuyến ngắn cố ý bỏ sót item. Phải cung cấp đủ item của mỗi đơn gốc để quyết định quyền chia đơn.
- Current list vẫn gồm thao tác đã hoàn thành; tập delivered/stack xác định thao tác đã thực hiện để không replay. Các visit tương lai chỉ chứa việc còn lại.

Hàm trả True hoặc ném Infeasible có `rule`, `vehicle`, `item`, `step` trong thông báo.
Không dùng due date làm ràng buộc cứng; không từ chối một tuyến chỉ vì giao trễ.
Tải được cộng/trừ sau **từng thao tác**, dùng Decimal và so sánh chính xác; không thêm epsilon tải.

| Quy tắc | Nơi có sẵn | Phần kiểm tra độc lập và ca đối chứng |
|---|---|---|
| Tải <= capacity, kể cả hàng ban đầu | checker kiểm tra theo visit; vehicle kiểm tra khi load | CAPACITY: đúng 15 được chấp nhận; tải trung gian 20 bị loại; tải ban đầu vượt 15 bị loại |
| Lấy trước giao, đúng xe | vehicle kiểm tra khi thực thi | PICKUP_BEFORE_DELIVERY_OR_WRONG_VEHICLE; stack/owner toàn fleet |
| Item tồn tại, nguyên vẹn | object lookup và một số kiểm tra lúc chạy | UNKNOWN_ITEM: thiếu ID hoặc biểu diễn item kèm quantity thay thế đều bị loại |
| Không lấy/giao trùng | vehicle có guard khi thực thi | DUPLICATE_OPERATION, DUPLICATE_PICKUP, DUPLICATE_DELIVERY; kể cả khác visit |
| LIFO | vehicle kiểm tra lúc giao | LIFO: kiểm tra stack sau từng thao tác, trong và giữa các visit |
| Dỡ trước xếp tại cùng visit | Vehicle._service | Giao rồi lấy hợp lệ; không thể lấy một item rồi giao ngay trong cùng visit vì thứ tự thực là dỡ trước |
| Đúng nhà máy | vehicle kiểm tra lúc chạy | FACTORY cho từng thao tác |
| Chia đơn có điều kiện | local checker chưa có | ORDER_SPLIT: đơn tổng 15 không chia giữa xe hoặc pickup visit; đơn tổng 20 có thể chia 10+10; item 16 không chia nhỏ được |
| Destination cam kết | local giữ factory khi đang chạy; gốc giữ cả arrive_time | DESTINATION_LOCK: đổi factory hoặc arrival bị loại; sửa lists vẫn được nếu các quy tắc khác đạt |
| Current work đã chốt | local cấm khi đã bắt đầu phục vụ | CURRENT_LOCK: đổi/reorder bị loại; no-op được chấp nhận; phần đã thực hiện không bị đếm hai lần |
| Current chưa phục vụ | local cho sửa lists trước start | Cho phép thay lists khi đang chờ, nhưng không đổi factory hiện tại |
| Suffix tương lai | được phép thay | Chấp nhận phương án sắp xếp lại suffix hợp lệ, không áp một khóa toàn tuyến |
| Phục vụ đủ tập item đầu vào | local checker chưa có guard đầy đủ | MISSING_SERVICE, UNDELIVERED_LOAD |

**37 ca feasibility PASS.** Các ca hợp lệ/vi phạm cụ thể có tên trong `test_dpdp_feasibility.py` và `after_tests.txt`.

**3 ca thực thi PASS:** cùng tuyến LIFO đúng được validator chấp nhận và simulator hoàn tất;
tuyến sai LIFO được local `_check_decision` chấp nhận nhưng validator loại trước chạy và DPDPVehicle ném SimulationError lúc thực thi;
tải 20 trên xe 15 bị validator và DPDPVehicle cùng phát hiện.
Không sửa checker tổng quát hay chính sách demo để che khoảng trống này; baseline phải gọi guard độc lập trước khi áp dụng quyết định.

## 4. Lịch dự báo và khoảng chiếm bến

Mã local xác định:

- `Vehicle._request_for_service` xin resource trước service.
- `DPDPVehicle._service` đợi docking_time=1800 giây, sau đó gọi service chuẩn.
- `Vehicle._service` dỡ lần lượt delivery_list, rồi xếp lần lượt pickup_list; mỗi đơn vị lượng hàng mất 240 giây cho mỗi thao tác.
- Resource được release trong finally sau khi service kết thúc, trước `_service_finish`.

Do đó bến bị chiếm trong **[service_start, service_finish)**, bao gồm tiếp cận bến và toàn bộ xếp/dỡ.
Arrival trước queue; waiting=start-arrival. Với các fixture không có earliest-service/dwell constraint, start cũng là thời điểm chiếm bến.
Đã kiểm tra resource.count trong các pha docking/loading/unloading và sau khi rời; không chỉ suy ra từ tổng thời gian.

`dpdp_schedule.predict_fixed_routes(model)` là bộ dự báo độc lập dùng lịch sự kiện và lịch rảnh từng bến,
không gọi mô phỏng giả cho mỗi phương án, không phát thêm đơn, không sửa state.
Nó giữ phần phục vụ đang chạy, cho xe đang chạy đến đúng ETA, và dự báo toàn bộ tuyến cố định còn lại.
Current row ghi cả arrival/start trong quá khứ khi snapshot lấy giữa phục vụ.

**Sai số cho phép đã đặt trước: 1e-9 giây. Sai lệch đo được lớn nhất: 0 giây.**
Không tăng tolerance sau khi chạy. Tất cả thời gian dưới đây tính bằng giây tương đối.

## 5. Bảng thời gian: tính tay / dự báo / simulator

Ký hiệu mỗi ô `a / b / c` lần lượt là **tính tay / dự báo / simulator**.
P là nhà máy lấy; Q là nhà máy giao. Với các fixture cơ bản, P có số bến nêu trong tên,
Q có đủ bến cho số xe để không tạo thêm hàng chờ ngoài chủ đích của fixture.
Mỗi xe có một đơn một item lượng 1. Các depot riêng có thời gian tới P là 10/20/30 giây; P->Q=20.

| Fixture / xe / visit | Arrival | Chiếm bến | Chờ | Docking | Dỡ | Xếp | Rời | Completion tính trễ |
|---|---|---|---|---|---|---|---|---|
| Một xe / V1 / P | 10/10/10 | 10/10/10 | 0/0/0 | 1800/1800/1800 | 0/0/0 | 240/240/240 | 2050/2050/2050 | — |
| Một xe / V1 / Q | 2070/2070/2070 | 2070/2070/2070 | 0/0/0 | 1800/1800/1800 | 240/240/240 | 0/0/0 | 4110/4110/4110 | 2070/2070/2070 |
| Hai xe, 1 bến / V2 / P | 20/20/20 | 2050/2050/2050 | 2030/2030/2030 | 1800/1800/1800 | 0/0/0 | 240/240/240 | 4090/4090/4090 | — |
| Hai xe, 1 bến / V2 / Q | 4110/4110/4110 | 4110/4110/4110 | 0/0/0 | 1800/1800/1800 | 240/240/240 | 0/0/0 | 6150/6150/6150 | 4110/4110/4110 |
| Ba xe, 1 bến / V3 / P | 30/30/30 | 4090/4090/4090 | 4060/4060/4060 | 1800/1800/1800 | 0/0/0 | 240/240/240 | 6130/6130/6130 | — |
| Ba xe, 1 bến / V3 / Q | 6150/6150/6150 | 6150/6150/6150 | 0/0/0 | 1800/1800/1800 | 240/240/240 | 0/0/0 | 8190/8190/8190 | 6150/6150/6150 |
| Ba xe, 2 bến / V2 / P | 20/20/20 | 20/20/20 | 0/0/0 | 1800/1800/1800 | 0/0/0 | 240/240/240 | 2060/2060/2060 | — |
| Ba xe, 2 bến / V2 / Q | 2080/2080/2080 | 2080/2080/2080 | 0/0/0 | 1800/1800/1800 | 240/240/240 | 0/0/0 | 4120/4120/4120 | 2080/2080/2080 |
| Ba xe, 2 bến / V3 / P | 30/30/30 | 2050/2050/2050 | 2020/2020/2020 | 1800/1800/1800 | 0/0/0 | 240/240/240 | 4090/4090/4090 | — |
| Đồng thời, 1 bến / V2 / P | 10/10/10 | 2050/2050/2050 | 2040/2040/2040 | 1800/1800/1800 | 0/0/0 | 240/240/240 | 4090/4090/4090 | — |
| Đồng thời, 2 bến / V2 / P | 10/10/10 | 10/10/10 | 0/0/0 | 1800/1800/1800 | 0/0/0 | 240/240/240 | 2050/2050/2050 | — |
| Dỡ+xếp cùng visit / V1 / P | 10/10/10 | 10/10/10 | 0/0/0 | 1800/1800/1800 | 240/240/240 | 240/240/240 | 2290/2290/2290 | 10/10/10 |
| Dỡ+xếp / V1 / Q | 2310/2310/2310 | 2310/2310/2310 | 0/0/0 | 1800/1800/1800 | 240/240/240 | 0/0/0 | 4350/4350/4350 | 2310/2310/2310 |

Các hàng còn lại giống hàng tương ứng của V1/V2 phía trên; **toàn bộ từng hàng của cả 9 fixture**,
không rút gọn, nằm trong `feasibility_schedule_evidence/schedule_rows.json`.

| Snapshot bắt đầu dự báo | Điều kiện đã chạy | Kết quả |
|---|---|---|
| t=0 | Một xe; hai xe khác giờ; đồng thời một/hai bến | Dự báo và simulator trùng bảng tay |
| t=5 | Xe đang chạy tới P, ETA=10 | ETA local=10; lịch còn lại trùng tay/simulator |
| t=100 | Một xe đang docking tại P | Giữ start=10; rời=2050; không cộng lại một dịch vụ từ t=100 |
| t=100 | Ba xe cùng P: một phục vụ, hai chờ | Rời 2050/4090/6130; đúng từng xe |
| t=100 | Ba xe cùng P, hai bến | Rời 2050/2060/4090 |
| t=2200 | Dỡ xong một item, còn đang xếp item khác | Rời P=2290; Q arrival=2310; không replay thao tác đã xong |

Ví dụ cuối phân biệt rõ thời điểm: item carried đến P=10, bắt đầu bến=10,
docking kết thúc=1810, dỡ thực tế kết thúc=2050, xếp item mới xong/rời=2290.
DPDPVehicle đặt completion tính trễ của carried về **10**, không phải 2050 hay 2290.
Due=5 nên tardiness=5 giây, đã assert trực tiếp. Item giao ở Q dùng completion=2310, không phải physical delivery=4350.

## 6. Bằng chứng lỗi departure_times trước/sau

Fixture thực: ba xe đến P lúc 10,20,30; P có một bến; docking+load=2040 giây/xe; lấy snapshot t=100.

Tính tay:

```text
V1: start 10,   leave 10+2040   = 2050
V2: start 2050, leave 2050+2040 = 4090
V3: start 4090, leave 4090+2040 = 6130
```

Trước sửa, chạy 9 test schedule đầu tiên: **7 PASS, 2 FAIL**, process exit 1.
`test_departure_map_distinct_vehicles` nhận `{'V_1': 6130, 'V_2': 6130, 'V_3': 6130}`.
`test_state_next_arrival_for_each_vehicle` cũng thất bại với leave list `[6130,6130,6130]`.
Đầu ra thất bại thật lưu ở `departure_before.txt`; source thật trước sửa lưu ở `dpdp_routing_before.py.txt`.

Sửa tối thiểu:

```diff
 for vehicle_id, departure_time in departure_times_at_location.items():
-    departure_times[vehicle.id] = departure_time
+    departure_times[vehicle_id] = departure_time
```

Sau sửa: cả 9 test ban đầu PASS. Khi bổ sung kiểm tra port occupancy, mixed-service và simultaneous FIFO,
**12/12 test schedule PASS**. Leave list đúng `[2050,4090,6130]`; next arrival tại Q đúng `[2070,4110,6150]`.
Không sửa các tham số hoặc công thức để ép PASS.

## 7. Hồi quy cuối cùng và lệnh PowerShell

**67/67 kiểm tra PASS:** 37 feasibility + 3 guard đối chiếu thực thi + 12 schedule + **15 chấm điểm có sẵn**.
Đầu ra cuối trong `feasibility_schedule_evidence/after_tests.txt` (exit 0).
Không sửa hoặc mở rộng audit chấm điểm; chỉ chạy lại đúng test cũ theo yêu cầu hồi quy.

```powershell
Set-Location 'C:\Users\Cuongdz\Documents\LA\dvrpsim'
& '.\.venv\Scripts\python.exe' -B -m unittest -v test_dpdp_feasibility test_dpdp_execution_guards test_dpdp_schedule test_verify_dpdp_score

# In lại bảng tay/dự báo/simulator của các fixture nhỏ; không ghi tệp:
& '.\.venv\Scripts\python.exe' -B '.\dpdp_audit_fixtures.py'
```

Các lệnh chỉ chạy mô phỏng nhỏ, tuyến cố định; không gọi demo instance_1 hoặc toàn benchmark,
không ghi đè log và không cài package.

## 8. Phần chưa xác minh và điều kiện bắt đầu baseline

**Đủ điều kiện bắt đầu xây baseline chèn đơn trên instance nhỏ**, với phạm vi:

- Dùng guard độc lập cho complete remaining plan, snapshot và toàn bộ item của đơn gốc.
- Giữ nguyên công thức chấm đã audit; điểm trễ là soft penalty.
- Giữ current commitment và destination factory/arrival, chỉ sửa phần chưa khóa.
- Dự báo trên tuyến cố định, không dùng đơn chưa công bố.

Không có blocker tái hiện nào còn mở trong các fixture được yêu cầu. Các giới hạn cần giữ rõ:

- Guard hiện chưa nối vào routing_callback/demo và chưa có adapter sản phẩm cho JSON state/decision;
  adapter trong fixture chỉ dùng đối chiếu các trạng thái simulator đã kiểm soát.
- Đây không phải bộ kiểm chứng toàn bộ lịch sử trước snapshot. Stack/delivered và cam kết đầu vào được tin cậy;
  cần manifest/history nếu muốn truy nguyên mọi batch chia đơn đã xảy ra trước đó.
- Không nhận fleet dị chủng; không hỗ trợ validator bị đưa thiếu item của cùng đơn gốc hoặc chỉ một partial route tùy ý.
- Forecast không bao quát earliest-service/dwell constraints, policy delay, đóng/mở bến, đơn tương lai hoặc tái điều phối trong quá trình dự báo.
- Simultaneous FIFO đã kiểm tra một tình huống nhỏ theo thứ tự đăng ký xe; chưa chứng minh mọi thứ tự sự kiện đồng thời giữa các giai đoạn ở mạng lớn.
- Chưa chạy instance_1 bằng baseline; chưa triển khai baseline, GP hay CFA-VNS.
- **Không suy từ các fixture PASS rằng toàn bộ simulator local tương đương Xingtian.**
