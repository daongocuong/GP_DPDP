# Chuẩn bị reference VNSME v3 và giám sát Java

Trạng thái: **NO-GO cho reference chính thức nhiều giờ và huấn luyện GP v3**. Cơ chế mới đã qua kiểm thử và smoke tổng hợp, nhưng chưa có reference v3 hoàn chỉnh thật để kiểm tra đường nhận/adopt end-to-end. Scorer độc lập không kiểm tra lại toàn bộ capacity, LIFO và lock từ các quyết định đã lưu; những ràng buộc đó hiện dựa vào guard chạy trực tiếp và chứng từ do runner ghi. Cần có công cụ replay độc lập đầy đủ hoặc quyết định nghiên cứu chấp nhận giới hạn bằng chứng này trước khi coi reference là đã audit độc lập đầy đủ. Trainer hiện hành vẫn là v2; cấu hình v3 chỉ là bản thảo bị vô hiệu hóa.

**Sự cố phạm vi test:** Trong lúc chạy `unittest discover`, các test hiện hữu `test_real_manifest_hash_schema_and_loader_offline` và `test_reads_locked_train_validation_and_never_authorizes_final_test` gọi `verify_existing`. Hàm đó đọc byte, checksum và schema/loader của toàn bộ dataset, bao gồm CSV 7–8 và 15–16. Việc đọc này vượt yêu cầu “không mở test” nếu hiểu theo nghĩa không đọc tệp. Không có rollout, chấm điểm hay lựa chọn mô hình trên các instance đó. Đây là lỗi kiểm soát phạm vi của lượt thực hiện; các lần kiểm tra riêng sau khi phát hiện không đọc thêm CSV test.

## Hợp đồng và bảo toàn

- HEAD `0bd773291d5d9034f1e7b81688bc2dfaf87308c7`; thư mục git đang có thay đổi từ trước, không commit hoặc ghi đè chúng.
- `dpdp-execution-commitment-v3` vẫn opt-in. GP và VNSME cùng đi qua `guard_raw_decision` và `ExecutionCommitment`; pending còn được đưa vào kỳ sau, acceptance không đảo ngược, carrying/current/destination lock được validator kiểm tra; finish đòi đủ input items, scorer chạy sau completion gate.
- Descriptor `protocols/dpdp_execution_commitment_v3.json` SHA-256 `c751559337adbe2138a455819465764d726cf4bba26e5544715df4b90e44b6ed` khớp sidecar. Java source/class/lib và build manifest được kiểm tra; không build lại hoặc sửa thuật toán.
- `run_dpdp_insertion.py`, `dpdp_contract.py` và `dpdp_vnsme_reference.py` khớp snapshot đầu lượt. 43 hash báo cáo cũ đã đối chiếu nguyên vẹn; tham khảo `preservation.json`. Adapter chỉ có nhánh trace mới khi chọn v3; nhánh subprocess v2 cũ được giữ. Loader v2 đã chấm lại và chấp nhận reference 2–6 lịch sử, không chứng nhận chúng theo v3.
- Replay đã chạy lại: hai cặp kỳ lưu sẵn 9/60–61, 13/21–22 PASS; lifecycle tổng hợp GP và VNSME PASS. Đây không phải full benchmark.

## Workflow v3

`dpdp_vnsme_reference_v3.py` tách riêng khỏi loader v2: preflight kiểm tra contract, split, hash dataset được phép và build Java; `run` dùng output mới và contract v3; `assemble` kiểm tra các record trước khi xuất summary; `load_reference` kiểm tra lại artifact, provenance, completion, guard và chấm lại `simulation.log`. Chỉ nhận J hữu hạn dương cho VNSME; không nhận v2, dữ liệu dở, điểm private solution hoặc output từ supervision lỗi. Kiểm tra filesystem/hash là xác minh toàn vẹn, không phải chữ ký chống giả mạo.

`dpdp_gp_fitness_v3.py` tính trung bình các tỷ số train từ rollout GP và reference v3 sau kiểm tra contract, input, cấu hình, initial locations, source simulator/scorer và cùng cây; validation trả riêng. `protocols/dpdp_gp_vnsme_v3_draft.json` là bản thảo `enabled=false`, không kết nối hoặc kích hoạt trainer v2. Thực nghiệm 100 đơn vẫn mang nhãn split đề xuất trong protocol hiện có. Chưa có J v3 chính thức nào, nên loader chỉ được kiểm tra trường hợp chấp nhận bằng record giả lập; chưa PASS đường nhận reference hoàn chỉnh thật.

## Watchdog và smoke

`dpdp_v3_supervisor.py` dùng Windows Job Object, tạo root ở trạng thái suspended, gán job rồi mới chạy; tiến trình con/cháu nằm trong job. Heartbeat lưu PID, creation FILETIME/UTC, PID cha, CPU user/kernel và elapsed/wall. Phát hiện gap theo cả hai đồng hồ; khi gap hoặc timeout thì hủy job và không chứng nhận lượt. Job có `KILL_ON_JOB_CLOSE` nếu supervisor chết. Không thể chạy watchdog trong lúc toàn máy bị đình chỉ: khi khôi phục, gap làm lượt không hợp lệ thay vì kéo dài budget âm thầm.

Adapter v3 ghi PID/creation, thời điểm và deadline của Java, kết thúc, timeout/detection lag; stdout/stderr được ghi trực tiếp vào file trong epoch để còn chẩn đoán khi cưỡng bức dừng. Epoch rất ngắn có thể kết thúc giữa hai heartbeat, vì vậy không khẳng định luôn có mẫu CPU Java; record invocation vẫn lưu danh tính. 540 giây trong Java là kiểm tra hợp tác giữa các operator, không phải deadline cứng; adapter giữ 600 giây/kỳ và watchdog giữ 10800 giây/lượt, không thay thuật toán hoặc budget.

- Regression cuối: **192/192 PASS**, 0 fail/error/skip, 50.34 giây; xem `regression_verified_r3.json` và log. Các test đọc CSV niêm phong nêu trên nằm trong con số này.
- Probe Java thật: timeout sau 2 giây được ghi, phát hiện Java descendant theo PID + creation time, job rỗng và PID đó không còn sống; monitoring gap giả lập bị từ chối và dọn job; deadline epoch giả lập cũng được kiểm thử. Xem `smoke_summary.json` và `test_dpdp_v3_supervisor.py`.
- Hai lần chạy Java VNSME thật trên epoch đầu rỗng đã lưu của instance 13, hard limit 10 giây/kỳ và 30 giây supervisor, đều thoát thành công. Đây là probe một kỳ, không phải rollout.
- Một rollout tổng hợp 2 đơn/2 item với Java VNSME thật và runner v3 đã hoàn tất: 14 epoch, scorer độc lập khớp, job rỗng, không gap. Runner khoảng 1.48 giây, supervisor khoảng 2.78 giây. Giới hạn của smoke là 5 giây/kỳ, 30 giây runner, 45 giây watchdog; không dùng J tổng hợp làm reference. Xem `smoke_synthetic_check.json`.
- Các trường hợp loader từ chối v2, tập instance sai, thiếu/không hoàn tất và checksum sai được kiểm thử. Normalization tách validation và từ chối contract khác. Chưa có reference v3 benchmark thật để thử đường chấp nhận không dùng mock.

## Chi phí và thứ tự đề xuất

Preflight đã xác nhận 2–5 train, 6 validation; 9–10 train và 13 validation thuộc đề xuất 100 đơn. Không có rollout benchmark mới cho 2–6 hay 9/10/13 trong nhiệm vụ này. Với 10800 giây mỗi lượt, năm lượt nhỏ có trần 15 giờ và ba lượt 13/9/10 thêm tối đa 9 giờ, chưa tính overhead; đây là trần, không phải ước tính chắc chắn hoàn tất. Lượt v2 lịch sử 2–6 lần lượt tốn khoảng 30, 28, 1111, 3268, 566 giây; các số đó không dự đoán chắc thời gian v3.

Instance 10 cũ có 127 invocation thành công, trong đó 6 kỳ gần 540 giây chiếm 3240.4/3262.7 giây invocation thành công; kỳ 127 timeout 600 giây. Heartbeat cũ mất khoảng 3644.7 giây và không có mẫu CPU Java cho kỳ lỗi. Không thể xác định từ bằng chứng cũ có sleep, Java tính CPU liên tục hay nguyên nhân cụ thể. Nếu cần, làm profiling bounded trên bản sao epoch đã lưu sau khi kiểm định supervision, với timeout cứng và thu CPU/diagnostic; không tăng timeout hoặc sửa search để tạo PASS.

Sau khi giải quyết blocker và xác nhận readiness, từ gốc repo chạy từng lệnh sau, dừng ngay nếu exit code khác 0; đổi tên thư mục nếu đã tồn tại. Lệnh có thể thực thi về mặt kỹ thuật nhưng **chưa được khuyến nghị chạy chính thức trong trạng thái NO-GO hiện nay**.

```powershell
.\.venv\Scripts\python.exe -B dpdp_vnsme_reference_v3.py preflight --instance 13
.\.venv\Scripts\python.exe -B dpdp_vnsme_reference_v3.py run --contract-version dpdp-execution-commitment-v3 --instance 2 --output vnsme_runs\v3_refs_20261109_r1\instance_2
.\.venv\Scripts\python.exe -B dpdp_vnsme_reference_v3.py run --contract-version dpdp-execution-commitment-v3 --instance 3 --output vnsme_runs\v3_refs_20261109_r1\instance_3
.\.venv\Scripts\python.exe -B dpdp_vnsme_reference_v3.py run --contract-version dpdp-execution-commitment-v3 --instance 4 --output vnsme_runs\v3_refs_20261109_r1\instance_4
.\.venv\Scripts\python.exe -B dpdp_vnsme_reference_v3.py run --contract-version dpdp-execution-commitment-v3 --instance 5 --output vnsme_runs\v3_refs_20261109_r1\instance_5
.\.venv\Scripts\python.exe -B dpdp_vnsme_reference_v3.py run --contract-version dpdp-execution-commitment-v3 --instance 6 --output vnsme_runs\v3_refs_20261109_r1\instance_6
.\.venv\Scripts\python.exe -B dpdp_vnsme_reference_v3.py assemble --records vnsme_runs\v3_refs_20261109_r1\instance_2\record.json vnsme_runs\v3_refs_20261109_r1\instance_3\record.json vnsme_runs\v3_refs_20261109_r1\instance_4\record.json vnsme_runs\v3_refs_20261109_r1\instance_5\record.json vnsme_runs\v3_refs_20261109_r1\instance_6\record.json --output vnsme_runs\v3_refs_20261109_r1\summary_50
```

Sau khi 2–6 hoàn tất, scorer và loader xác nhận từng lượt, tiếp tục theo thứ tự 13, 9, rồi 10. Với 10, trước tiên xem lại chẩn đoán performance và xác minh monitoring trên máy đang chạy:

```powershell
.\.venv\Scripts\python.exe -B dpdp_vnsme_reference_v3.py run --contract-version dpdp-execution-commitment-v3 --instance 13 --output vnsme_runs\v3_refs_20261109_r1\instance_13
.\.venv\Scripts\python.exe -B dpdp_vnsme_reference_v3.py run --contract-version dpdp-execution-commitment-v3 --instance 9 --output vnsme_runs\v3_refs_20261109_r1\instance_9
.\.venv\Scripts\python.exe -B dpdp_vnsme_reference_v3.py run --contract-version dpdp-execution-commitment-v3 --instance 10 --output vnsme_runs\v3_refs_20261109_r1\instance_10
```

Sau mỗi lệnh, kiểm tra exit code, `supervisor/supervision.json`, `run/result.json`, `run/commitments.json`, `record.json` và log. Bất kỳ timeout, gap, thiếu item, thiếu guard, checksum lệch hoặc scorer lệch đều dừng và không adopt. Lệnh trên không mở 7–8, 15–16 và không chạy GP.
