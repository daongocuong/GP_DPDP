**Sửa lỗi timeout và kiểm toán blocker VNSME scale-100 — 09/11/2026**

Đã sửa lỗi xử lý ngoại lệ timeout và chạy thành công 161/161 kiểm thử. Hai lỗi công bố tuyến trên 9/13 vẫn là blocker thiết kế: không có sửa đổi adapter đơn thuần đáp ứng đồng thời cam kết accepted hiện tại và chính sách công bố trì hoãn nguyên gốc của Java. Không chạy lại reference dài và chưa sẵn sàng tiếp tục GP scale-100.

Repo: `C:\Users\Cuongdz\Documents\LA\dvrpsim`. Git root hiện là thư mục cha `C:\Users\Cuongdz\Documents\LA`, HEAD `0bd773291d5d9034f1e7b81688bc2dfaf87308c7`. Không tìm thấy AGENTS.md áp dụng trong các thư mục cha hoặc nhánh liên quan. Đã lưu git status và hash trước sửa; giữ nguyên các file untracked có sẵn của người dùng, gồm draft protocol chính thức, test_dpdp_policy_audit.py và TIEN_DO_GP_DPDP.md ở thư mục cha.

**Nguyên nhân và phân loại từng lỗi**

| Lượt cũ | Bằng chứng xác minh | Phân loại | Trạng thái sau tác vụ |
|---|---|---|---|
| 9, kỳ 61 | Hai item 0949430034-{1,2} đã nhận từ kỳ 59 trên V_4; Java chuyển cặp riêng sang V_3 rồi không công bố V_3 | Bất tương thích hợp đồng adapter/Huawei, không phải nghiệm riêng thiếu item | Giữ từ chối, chưa giải quyết thiết kế |
| 13, kỳ 22 | Item 0316410009-1 và sáu item 0325060010-{1..6} đã nhận trên V_5; cùng chuyển riêng sang V_3 và bị ẩn khỏi bản công bố | Cùng bất tương thích hợp đồng | Giữ từ chối, chưa giải quyết thiết kế |
| 10, kỳ 127 | Traceback có TimeoutExpired 600 giây, sau đó Path.write_bytes nhận str gây TypeError | Lỗi triển khai của nhánh ghi log; nguyên nhân timeout thực còn chưa tách khỏi gián đoạn giám sát | Đã sửa xử lý ngoại lệ; không tuyên bố đã chữa hiệu năng Java |

Hai trạng thái 9/13 được dựng lại từ log sự kiện và output kỳ trước, không tiến thời gian mô phỏng. Phép chiếu huawei_state của mô hình phục dựng khớp toàn bộ JSON đầu vào Java đã lưu. Guard thật tái hiện lỗi; không sửa Snapshot hoặc mock kết quả validator để có PASS. Hash 433 artifact dùng trong fixture được pin trong saved_epoch_fixture_pins.json.

Ở cả hai trường hợp, item lỗi còn trong input unallocated, chưa được lấy hàng, không thuộc carrying/current visit/điểm đến đã chốt. Chuyển chúng sang xe khác là hợp lệ nếu giữ đủ pickup/delivery và các ràng buộc. Cả hai kế hoạch riêng đầy đủ của Java qua kiểm tra tải, LIFO, precedence, ownership, điểm đến và phục vụ đủ; chính bản công bố thất bại MISSING_SERVICE khi kiểm tra cùng tập cam kết.

**Ai sở hữu cam kết và vì sao không sửa công bố để ép PASS**

Huawei gốc không có trạng thái ACCEPTED. Đơn GENERATED chưa lấy hàng tiếp tục được gửi dưới dạng unallocated dù đã được lên kế hoạch; planned_route có thể được thay lại mỗi kỳ, còn hàng đang trên xe và điểm đến đã chốt phải được giữ. Java lưu nghiệm riêng đầy đủ trước khi MergeNode và công bố prefix. Với isDelay bật, emergencyIndex khởi tạo -1; tuyến xe chưa có hàng/điểm đến chỉ được công bố khi đủ điều kiện khẩn cấp. V_3 ở cả hai kỳ không có carrying/destination và chưa đạt ngưỡng khẩn cấp, nên bản công bố rỗng là hành vi có chủ đích.

Adapter hiện nhận mọi item xuất hiện trong tuyến công bố vào simulator rồi bảo vệ cam kết accepted ở các kỳ sau. Guard đó đúng với hợp đồng tích hợp hiện tại và vẫn nguyên vẹn sau sửa. Việc không công bố lại item đã nhận vi phạm hợp đồng này dù Java vẫn nhớ nó trong nghiệm riêng. Đây không phải bằng chứng VNSME không tìm được tuyến vật lý khả thi.

Các cách ép thành công đều thay đổi ngữ nghĩa: công bố thêm suffix riêng làm đổi isDelay; giữ tuyến cũ thay đổi nghiệm Java đã chọn; cấm chuyển xe thay đổi tìm kiếm; hủy accepted hoặc bỏ guard vi phạm yêu cầu của tác vụ. Không áp dụng các cách đó. Cần một quyết định thiết kế tích hợp/baseline được mô tả và kiểm thử riêng trước khi chạy lại. Theo ngoại lệ được yêu cầu trong task, tác vụ báo rõ giới hạn thay vì tạo PASS giả.

Chi tiết vòng đời, tất cả item liên quan và vị trí mã nguồn nằm trong contract_analysis.json. Các tham chiếu dòng adapter trong file này được ghi khi bắt đầu kiểm toán; bản mã trước sửa được lưu ở vnsme.before.py.txt. Phần VNSMEPolicy và huawei_state không thay nội dung.

**Bản sửa đã triển khai**

File sản phẩm duy nhất sửa: `src/baselines/vnsme.py`.

- Chuyển stdout/stderr của TimeoutExpired an toàn từ bytes, str hoặc None; giữ nguyên bytes không giải mã lại.
- Giữ chính đối tượng TimeoutExpired gốc làm exception cause của VNSMEError; không để TypeError ghi log che nó.
- Ghi configured/effective timeout trước khi khởi chạy và giữ command/cwd, timeout thực trong ngoại lệ, epoch, thời gian và trạng thái invalid.
- Lỗi ghi stdout và stderr được ghi nhận riêng; lỗi ghi invocation.json trong finally không thay thế ngoại lệ chính. Nếu một subprocess thành công nhưng không lưu được invocation bắt buộc, lượt gọi bị từ chối thay vì được nhận làm bằng chứng hợp lệ.
- Không thay 540/600/10800 giây, Java source/class, objective, feasibility, bộ sinh ứng viên, dự báo, tie-break hoặc công thức fitness GP.

Đã tái hiện lỗi cũ bằng bản adapter trước sửa và TimeoutExpired có output kiểu str: lỗi cũ đúng là TypeError memoryview. Sau sửa, các tổ hợp output giữ đúng nguyên nhân TimeoutExpired. Không chạy mô phỏng đầy đủ để tái hiện lỗi đã biết.

**Test mới và kết quả thực chạy**

| Kiểm tra | Kết quả | Ý nghĩa |
|---|---|---|
| Adapter cũ, test VNSME trước sửa | 16/16 PASS | Mốc kiểm thử ban đầu; nhánh có partial str chưa được bao phủ |
| test_dpdp_vnsme_timeout + test_dpdp_vnsme | 22/22 PASS | 6 test timeout mới, gồm 9 tổ hợp kiểu stream, lỗi ghi từng artifact, invocation cuối và subprocess timeout thật |
| test_dpdp_vnsme_scale100 | 7/7 PASS | Tái hiện hai kỳ thật, giữ trạng thái nhận đơn, không tạo điểm, kiểm tra thiếu dịch vụ, chuyển xe hợp lệ và mutation tải/LIFO/precedence |
| Toàn bộ discover test_*.py | **161/161 PASS**, 0 skip | 25.475 giây wall, 0 failure/error |
| Loader + scorer reference 2–6 | PASS | Hash artifact và điểm cũ giữ nguyên, không rollout lại VNSME |

Các test từ 9/13 PASS vì xác nhận guard tiếp tục từ chối output không đáp ứng hợp đồng, không có nghĩa hai rollout đã hợp lệ. Test timeout thật dùng một subprocess Python ngắn phát stdout/stderr rồi chờ, không gọi thuật toán Java. Full suite hiện có còn chạy các kiểm tra simulator tổng hợp và regression cây cố định trên instance 1 phát triển cũ trong thư mục tạm; đó không phải GP training hoặc full reference scale-100. Không có rollout test cuối 7–8/15–16.

Reference 2–6 đã được loader hiện có kiểm hash, kiểm session/build, chấm lại log và xác nhận giao đủ. Có 29 file summary/protocol/manifest/build/artifact được đối chiếu trước/sau. J giữ nguyên: 2=95.74; 3=97.44; 4=100.76; 5=3303.926666666666666666666667; 6=105.04. Không tuyên bố đã tái chạy mô phỏng đầy đủ 2–6.

**Hiệu năng instance 10 và giới hạn chứng cứ**

Phân tích offline chỉ đọc artifact: 127 Java invocation thành công, trong đó 121 invocation nhanh có median khoảng 0.180 giây; sáu invocation 87/103/104/105/120/122 dùng khoảng 540 giây mỗi kỳ. Sáu kỳ chiếm 3240.406/3262.702 giây, tức 99.3% thời gian wall của các invocation thành công.

Epoch 87 có thread dump đo main-thread CPU 199.469 giây trong 208.07 giây elapsed, RUNNABLE ở cost → blockExchange. Log báo 729356 BlockExchange và 364678 BlockRelocate trả thành công. Đây là số lần operator trả thành công, không phải số ứng viên. Các epoch 103/104 cũng có hàng trăm nghìn lượt operator. Tại 122, BlockRelocate lớn dù BlockExchange bằng 0, nên bottleneck không chỉ thuộc một operator.

Java liệt kê cặp block, sao chép/khôi phục ArrayList và tính lại lịch toàn bộ đội xe cho nhiều ứng viên chồng lặp; cost không phải delta cục bộ. Các mốc 540 giây chỉ được kiểm giữa operator, không ngắt bên trong; một số nhánh continue bỏ qua kiểm tra kế tiếp. Các điều kiện chấp nhận trong 2-opt cho phép mở rộng mức cost, nên không thể suy ra tìm kiếm chỉ cải thiện đơn điệu. Không thay những quy tắc đó hoặc gọi chúng là lỗi đã được chữa. Tăng kích thước không đủ giải thích toàn bộ: snapshot 125/126 có cùng 34 node như 127 nhưng kết thúc khoảng 0.19 giây; epoch 87 nhỏ hơn vẫn dùng hết budget. Log không đủ để chứng minh một chu kỳ tuyến cụ thể.

Epoch 127 thiếu stdout/stderr và không có Java CPU sample. Heartbeat có khoảng trống 3644.719 giây; đồng hồ wall và elapsed cùng tăng tương ứng, nên không chỉ là chỉnh giờ wall. Lại có khoảng 4138.493 giây từ heartbeat cuối đến ghi nhận kết thúc. Supervisor cũ chỉ lấy con trực tiếp của launcher Python, bỏ sót Java cháu; watchdog chỉ hoạt động khi vòng polling được lập lịch. Không kết luận máy đã sleep hoặc Java đã tính CPU liên tục trong các khoảng đó. Timeout 600 giây được traceback xác nhận; nguyên nhân active overrun, pause hoặc phối hợp cả hai còn chưa xác định.

Phân tích offline mới dùng khoảng 0.931 giây wall/0.906 giây Python CPU, kiểm 4676 input giữ nguyên, không chạy Java. Nguồn Java, 3748 file thư viện và 18 class khớp build manifest/session cũ. Báo cáo hiệu năng riêng, CSV từng epoch và script tái lập nằm trong performance/.

**Quyết định rerun và readiness**

Không launch full reference mới cho 9/10/13. Hai blocker cam kết vẫn tồn tại; test từ chối qua không giải quyết được chúng. Ngoài ra instance 10 đã tiêu tốn khoảng 54.4 phút Java thành công trước epoch lỗi; ba lần mới với budget 10800 giây có thể tốn tới chín giờ trước overhead, không có cơ sở chắc chắn sẽ hoàn tất. Không dùng rerun đắt tiền để tái xác nhận lỗi đã được artifact chứng minh.

Trước khi rerun cần giải quyết thiết kế cam kết/công bố mà không hạ guard; giám sát mới phải theo đệ quy cây tiến trình, đo CPU/elapsed riêng, ghi start/deadline/exit/detection lag và dùng watchdog độc lập. Watchdog cũng không thể chạy khi toàn hệ thống bị đình chỉ; phải ghi nhận gap, không âm thầm kéo dài budget. Supervisor lịch sử giữ nguyên, chưa triển khai hoặc tuyên bố đã kiểm chứng supervisor mới.

**Chưa sẵn sàng tiếp tục thí nghiệm GP scale-100 hoặc huấn luyện chính thức dựa trên reference 9/10/13.** Lỗi ghi log đã được sửa; hợp đồng tích hợp và chẩn đoán/giám sát runtime là các phần còn lại. Không có reference mới, điểm J mới, fitness mới hoặc kết quả held-out mới trong tác vụ này.

**File thay đổi và bàn giao**

- `src/baselines/vnsme.py`: sửa nhánh timeout/ghi chẩn đoán.
- `test_dpdp_vnsme_timeout.py`: mới, unit/integration timeout.
- `test_dpdp_vnsme_scale100.py`: mới, replay trạng thái đã lưu, giữ cam kết và kiểm chứng reference.
- `vnsme_evidence/scale100_blockers_20261109_r2/`: báo cáo này, summary.json, test log/JSON, pins, preflight/preservation, hợp đồng, tái hiện timeout trước sửa và performance/. Bộ test saved-epoch phụ thuộc các artifact lịch sử được pin; cần giữ chúng cùng bộ kiểm chứng khi bàn giao.

Trong 25021 file có sẵn đã hash trước sửa, chỉ src/baselines/vnsme.py thay đổi; 25020 file khác giữ nguyên. So sánh AST xác nhận nguyên nội dung VNSMEPolicy và huawei_state; Java/build, fitness, protocol, dữ liệu và lịch sử không thay đổi. Không push, merge hoặc commit tự động.

Lệnh kiểm thử từ gốc dvrpsim:

```powershell
.\.venv\Scripts\python.exe -B -m unittest test_dpdp_vnsme_timeout test_dpdp_vnsme_scale100 test_dpdp_vnsme -v
.\.venv\Scripts\python.exe -B -m unittest discover -p "test_*.py" -v
```

Tái lập phân tích hiệu năng bằng dữ liệu đã lưu, không Java:

```powershell
.\.venv\Scripts\python.exe -B vnsme_evidence\scale100_blockers_20261109_r2\performance\analyze_saved.py
```
