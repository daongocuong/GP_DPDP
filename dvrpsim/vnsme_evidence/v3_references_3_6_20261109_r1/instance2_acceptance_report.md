# Kiểm toán replay độc lập và reference v3 instance 2

## Kết quả

Reference thật VNSME v3 cho instance 2 đã hoàn tất, được chấm lại, qua auditor replay độc lập và được loader v3 chấp nhận. **GO để tiếp tục tuần tự reference v3 instance 3–6**, dừng ngay nếu lượt nào timeout, gap, thiếu item, sai scorer, hoặc auditor không PASS. **NO-GO cho GP training** cho tới khi reference 2–6 đầy đủ và trainer/protocol v3 được bật riêng. Không chạy 9, 10, 13 hoặc GP training trong nhiệm vụ này.

Instance 2 có 50 đơn/110 item, 167 lần điều phối, 110 pickup và 110 delivery. Result: D=478.7 km, T=0 giây, J=95.74. Checker tính độc lập cùng J=95.74. `result.valid=true`, completion contract PASS; commitments xác nhận đủ item; auditor độc lập PASS; supervisor EXITED code 0, không timeout, gap hoặc tiến trình còn trong job. Loader đã nạp summary một-instance thật với `fitness_version=gp-fitness-vnsme-v3`, `contract_version=dpdp-execution-commitment-v3`, denominator dương 95.74.

Thư mục lượt chạy: `vnsme_runs/v3_instance2_acceptance_20261109_r1/`. Summary được loader nhận tại `reference_2/summary.json`, SHA-256 `50fd40cbdae6d2a777184fcc2418b75889cae166f38350917fcdf4ee2e52472`.

## Ranh giới kiểm tra độc lập

Auditor đọc decision trace append-only, các Huawei input/output đã lưu theo epoch, `simulation.log`, input CSV đã cho phép và manifest. Auditor không gọi guard của runner. Nó kiểm lại tuyến trước/sau mỗi quyết định rồi dựng lại stack từ log pickup/delivery để đối chiếu snapshot.

| Ràng buộc | Kết quả | Bằng chứng độc lập |
|---|---|---|
| Pickup trước delivery, item phải đang trên đúng xe | PASS | Thứ tự pickup/delivery, owner và stack được dựng từ log; so khớp với snapshot |
| Capacity mọi thời điểm | PASS | Quantity từ orders CSV, tải cộng/trừ theo từng event và trên từng route |
| LIFO | PASS | Kiểm tra stack top ở từng delivery trong tuyến và log vật lý |
| Pickup/delivery trùng | PASS | Kiểm tra uniqueness trên tuyến và chuỗi event |
| Current visit/service lock | PASS | So route đang thực thi với log arrival/service/departure và route kế tiếp |
| Destination/factory/ETA đã khóa | PASS | So snapshot trước quyết định, Huawei vehicle input, Java destination output; đang đi thì arrival ETA tính lại từ departure và travel matrix |
| Không mất request, không dùng request chưa release | PASS | Tập request tại từng routing marker phải bằng tập request release đã ghi trước thời điểm đó; Huawei input chỉ chứa tập này |
| Pending được đưa lại vào kỳ sau | PASS | Pending kỳ trước phải có đúng trong `unallocated_order_items.json` kế tiếp |
| Không đảo sự kiện vật lý | PASS | Snapshot mỗi epoch phải khớp pickup/delivery/owner tích lũy từ log |
| Quy tắc không chia đơn vừa capacity | PASS | Original-order demand và token pickup theo route/xe được kiểm tra lại |
| Hoàn tất | PASS | Mọi 110 item đều pickup và delivery đúng một lần; đối chiếu result, commitments, scorer |
| Dự báo ETA khi xe đang tại bến | UNVERIFIABLE về độ chính xác dự báo | Auditor xác nhận ETA đã ghi được giữ nguyên tới Java publication; chưa tự tính lại thuật toán xếp hàng bến của predictor |

Ràng buộc cuối không phủ định kiểm tra ETA lock: giá trị đã cam kết không bị thay trong publication và ETA lúc di chuyển được tính lại độc lập. Nó giới hạn kết luận về tính chính xác của dự báo queue ETA khi xe còn ở bến. Vì vậy auditor báo giới hạn này thay vì gọi lại scheduler runner hoặc tự tuyên bố dự báo đúng.

Artifact cũ không có decision trace nên auditor trả `UNVERIFIABLE`; không nâng saved-epoch PASS hoặc VNSME v2 thành audit replay đầy đủ. Schema mới `dpdp-independent-replay-v1` lưu item definitions/status, stack/carrying, current visit, destination/ETA, previous và published plans, raw action cho từng decision. Output Java, ba file input và danh tính Java mỗi kỳ nằm trong thư mục epoch. Hash trace và artifact được ghi trong record/summary.

## Kiểm thử đối kháng và dữ liệu test

Mutation tests độc lập đã làm auditor từ chối quá tải, sai LIFO, delivery trước pickup, pickup/delivery trùng, đổi current/destination/ETA, chuyển hàng đang chở sang xe khác, mất pending item, thiếu delivery cuối, thiếu trace và hash artifact sai. Thử sửa ETA trong Java output cũng bị auditor từ chối. Bộ smoke tổng hợp đã qua replay 14 quyết định trước; reference thật đạt 167 quyết định.

Đường đọc được khóa tại `resolve_inputs`/`rows`, `verify_existing`, `read_dpdp_problem` và `verify_dpdp_score.read_orders`. Kiểm tra manifest chỉ dùng metadata tin cậy cho instance niêm phong và bỏ qua đọc nội dung CSV của chúng. `acquire` dừng trước khi tải nội dung CSV test. Đây là ranh giới của workflow Python trong repo; nó không thay ACL của Windows đối với lệnh tự mở tệp ngoài các loader này.

Incident từ lượt trước: bộ regression cũ từng gọi `verify_existing`, hàm trước đó đọc byte và chạy schema/loader trên CSV 7–8, 15–16. Không có rollout, score hay model selection từ chúng. Sau khi sửa, regression có audit hook từ chối mọi lần mở CSV test ghi **0 lần thử truy cập**.

Regression cuối: **205/205 PASS**, 0 fail/error/skip, 39.78 giây; audit hook bảo vệ CSV niêm phong ghi 0. Xem `regression_final2.json` và `regression_final2.log`. Regression bao gồm test offline saved epochs, không chạy benchmark 9/10/13; trong lượt này chỉ full rollout benchmark instance 2 được chạy.

## Provenance và bước tiếp

HEAD `0bd773291d5d9034f1e7b81688bc2dfaf87308c7`; seed môi trường 0; 5 xe; Java OpenJDK 26.0.1. Protocol split SHA-256 `21c7f62c06a4402214dd0051728bec4fb8051cb8ab420866cd565c669a49f859`; contract descriptor SHA-256 `c751559337adbe2138a455819465764d726cf4bba26e5544715df4b90e44b6ed`; Java build SHA-256 `49f85c57affe25a86e32522d82e16bde833c9211b7e34b56e08f79fd1f751046`. Instance 2 input hashes nằm tại `protocol_manifest.json` và `instance2_acceptance.json`. Output của lần chạy là thư mục mới; không artifact lịch sử nào bị ghi đè.

Supervisor chạy giới hạn không đổi: 540 giây cooperative search trong Java, tối đa 600 giây mỗi epoch, 10800 giây cả rollout. Instance 2 hoàn thành trong 33.75 giây supervisor. Tiếp tục 3, 4, 5, 6 tuần tự trong thư mục output mới cho mỗi lượt. Giữ cùng seed, contract, build, protocol và cấu hình. Nếu một lượt không hợp lệ hoặc UNVERIFIABLE, dừng và giữ artifact đó; không chạy instance kế tiếp cho tới khi chẩn đoán xong.
