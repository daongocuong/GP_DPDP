# Chuyển fitness GP sang VNSME

Theo lựa chọn mới, Greedy đã được bỏ khỏi luồng chạy hiện tại. Runner không
còn nhận `greedy`, `baseline` hoặc `insertion`; không chuyển ngầm các tên này
sang một chính sách khác. So sánh hiện tại chỉ gồm GP và VNSME.

`dpdp_insertion.py` giữ bộ chia nhóm, sinh ứng viên, đặc trưng, dự báo lịch và
guard dùng cho GP. Đã bỏ hàm chấm Greedy và fallback mặc định; `InsertionPolicy`
bắt buộc nhận hàm chấm ứng viên. Các kiểm thử cấu trúc xác nhận phần dùng chung
không bị đổi. Dịch vụ Java, scorer J và mô phỏng không thay đổi.

Fitness mới là `mean(J_GP(i)/J_VNSME(i))` trên train 2–5, phiên bản
`gp-fitness-vnsme-v2`. Validation vẫn dùng instance 6, với mẫu số VNSME.
Các tie-break và penalty giữ nguyên. Summary Greedy cũ bị từ chối, kể cả khi
truyền bằng `--baseline-summary`. Reference thiếu, lỗi hoặc có J không dương
sẽ chặn huấn luyện, không tự thay mẫu số.

`dpdp_vnsme_reference.py` tạo điểm VNSME riêng cho train 2–5 và validation 6.
Loader kiểm tra policy, phiên bản, seed, build Java, input/config, hash
artifact, guard và chấm lại log độc lập. File summary được ghim hash trong
protocol thí nghiệm và cache context, rồi kiểm tra lại qua các lần đánh giá.
Không tái sử dụng cache fitness theo định nghĩa cũ.

Các kết quả/pilot/protocol/báo cáo lịch sử được giữ nguyên, kể cả các nhắc đến
Greedy. Chúng mô tả định nghĩa fitness lúc thực chạy; không so trực tiếp
fitness chuẩn hóa lịch sử với v2. Điểm J tuyệt đối vẫn so được nếu cùng cấu
hình. `train_dpdp_gp.py` là pilot đơn instance lịch sử dùng raw J; workflow
chuẩn hóa hiện tại là `train_dpdp_gp_multinstance.py`.

Không tiến hóa hoặc chọn lại mô hình GP trong tác vụ chuyển đổi. Cây đã chọn
trước đây được chạy kiểm tra lại trên 2–6; điểm J đều khớp lịch sử. Không chạy
test cuối 7–8 hoặc 15–16. Không sửa hay xóa kết quả cũ.

## Kiểm chứng mã và kết quả lịch sử

- Suite hiện tại: **145/145 PASS**, log `migration_evidence/tests.txt`.
- Đã kiểm tra 5.912 file kết quả/bằng chứng/protocol/báo cáo có trước tác vụ:
  tất cả khớp hash trước và sau sửa. Xem `migration_evidence/preservation_*.json`.
- So sánh thực chạy mới trên instance 2 chỉ chứa GP và VNSME, cả hai hợp lệ.
  GP: J = 23840.566667, D = 744.5 km, T = 8529 giây; VNSME:
  J = 95.74, D = 478.7 km, T = 0. Cả hai giao đủ 50 đơn/110 item.
  Xem `migration_runs/gp_vs_vnsme_instance2/comparison.json`.
- Cây GP cũ được chạy lại trên 2–6 và khớp các J cũ:
  23840.566667; 16767.095556; 164.52; 5417.302222; 184.08.
  Đây là kiểm tra cây cố định, không phải huấn luyện hay chọn cây mới.
  Xem `migration_runs/frozen_gp_check/raw_scores.json`.
- Đã thử loader trên summary VNSME đang thiếu các instance: bị từ chối đúng,
  không trả về fitness từ một bộ mẫu số thiếu. Xem
  `migration_evidence/incomplete_reference_rejected.json`.

Môi trường Huawei bị chặn import pandas như báo cáo tích hợp trước vẫn là
vướng mắc riêng. Các reference hiện tại dùng dvrpsim và scorer J đã kiểm chứng.

## Chạy lại

Trong PowerShell ở thư mục `C:\Users\Cuongdz\Documents\LA\dvrpsim`:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -v
.\.venv\Scripts\python.exe dpdp_vnsme_reference.py --output migration_runs\new_vnsme_reference
.\.venv\Scripts\python.exe train_dpdp_gp_multinstance.py --baseline-summary migration_runs\new_vnsme_reference\summary.json --output migration_runs\new_gp_training
.\.venv\Scripts\python.exe compare_dpdp_baselines.py --output migration_runs\new_gp_vnsme_comparison
```

Các thư mục output phải mới. Default reference của trainer là
`migration_runs/vnsme_reference_ready/summary.json`; lệnh tạo reference không có
`--output` tạo đúng vị trí này. Việc tạo lại reference và huấn luyện trong ví
dụ là thao tác chủ động khi cần một thí nghiệm mới.

Có thể ghép các rollout VNSME đã hoàn tất ở những thư mục khác nhau bằng
`dpdp_vnsme_reference.py --adopt-runs <run2> <run3> <run4> <run5> <run6>
--output <thư mục mới>`. Mỗi rollout vẫn phải qua toàn bộ kiểm tra provenance,
guard và chấm lại log; không chấp nhận điểm nhập tay. Cách này tránh phải chạy
lại những instance có tìm kiếm kéo dài khi đã có kết quả hợp lệ.

## File thay đổi

- Runner, so sánh, policy chèn: `run_dpdp_insertion.py`,
  `compare_dpdp_baselines.py`, `dpdp_insertion.py`, `src/baselines/__init__.py`.
- Fitness/training và calibration: `dpdp_gp_fitness.py`,
  `train_dpdp_gp_multinstance.py`, `measure_dpdp_data.py`.
- Thêm `dpdp_vnsme_reference.py`, `protocols/dpdp_vnsme_fitness_v2.json`,
  `test_dpdp_vnsme_normalization.py`.
- Cập nhật kiểm thử chèn/GP để dùng ranker tường minh:
  `test_dpdp_insertion.py`, `test_dpdp_gp.py`.
- Tài liệu hiện hành: `README.md`, báo cáo này. Artifact mới nằm trong
  `migration_runs/` và `migration_evidence/`.

## Trạng thái bộ mẫu số VNSME

Phần chuyển đổi mã đã được kiểm thử; **chưa đủ reference để huấn luyện GP mới**.
Hai tiến trình của instance 5 và 6 không còn chạy và không có `result.json`
cuối. Nguyên nhân dừng chưa xác minh được; không ghi chúng là timeout hoặc
PASS. Thông tin đã lưu trong `interrupted.json` của từng lượt.

| Instance | Trạng thái | J đã chấm độc lập |
| --- | --- | ---: |
| 2 | PASS | 95.74 |
| 3 | PASS | 97.44 |
| 4 | PASS | 100.76 |
| 5 | INTERRUPTED ở kỳ 100; không có điểm cuối | — |
| 6 | INTERRUPTED ở kỳ 63; không có điểm cuối | — |

Instance 4 hoàn tất trong khoảng 1.111 giây, với hai kỳ tìm kiếm dùng hết
540 giây nội bộ của Java. Instance 5 cũng có hai kỳ 540 giây trước khi bị
gián đoạn. Các lượt 5 và 6 có giai đoạn chạy song song trên workspace riêng.
Không có tiến trình solver còn chạy sau kiểm tra cuối.

Trainer mặc định tìm `migration_runs/vnsme_reference_ready/summary.json`.
File này chưa được tạo: trainer sẽ từ chối khởi chạy khi thiếu bộ mẫu số đầy
đủ, không dùng lại summary Greedy hoặc điểm tạm. Chưa tính fitness v2 đầy đủ
cho cây GP cố định và chưa huấn luyện lại GP.

Để bổ sung hai lượt còn thiếu mà giữ kết quả hợp lệ 2–4, chạy với các thư mục
mới. Budget lớn hơn dưới đây là lựa chọn chạy lại, chưa được kiểm chứng là
đủ cho mọi kỳ tìm kiếm:

```powershell
.\.venv\Scripts\python.exe run_dpdp_insertion.py --policy vnsme --instance-directory datasets\xingtian\e4ef3a1c92d19d1d08c3ef0e2156b6fecefdbe04\benchmark\instance_5 --output migration_runs\retry_reference5 --wall-seconds 3600 --vnsme-epoch-seconds 600
.\.venv\Scripts\python.exe run_dpdp_insertion.py --policy vnsme --instance-directory datasets\xingtian\e4ef3a1c92d19d1d08c3ef0e2156b6fecefdbe04\benchmark\instance_6 --output migration_runs\retry_reference6 --wall-seconds 3600 --vnsme-epoch-seconds 600
.\.venv\Scripts\python.exe dpdp_vnsme_reference.py --adopt-runs migration_runs\vnsme_reference\instance_2 migration_runs\vnsme_reference\instance_3 migration_runs\vnsme_reference\instance_4 migration_runs\retry_reference5 migration_runs\retry_reference6
```

Chỉ ghép khi cả hai lượt mới hoàn tất hợp lệ. `--adopt-runs` sẽ chấm lại và
kiểm tra toàn bộ năm reference trước khi tạo summary sẵn sàng cho trainer.
