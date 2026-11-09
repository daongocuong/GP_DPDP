# Tài liệu DPDP

Thư mục này tập hợp các báo cáo kiểm chứng và thí nghiệm DPDP theo trình tự nghiên cứu. Các đường dẫn tệp được viết trong báo cáo được tính từ thư mục gốc của repository, trừ khi có ghi chú khác.

## Kiểm chứng nền tảng

1. [Audit bộ chấm điểm](DPDP_SCORING_AUDIT.md): định nghĩa D, T, J và đối chiếu scorer.
2. [Audit tính khả thi và lịch dự báo](DPDP_FEASIBILITY_SCHEDULE_AUDIT.md): guard tuyến và lịch dự báo.
3. [Báo cáo baseline chèn đơn](DPDP_INSERTION_BASELINE_REPORT.md): chính sách baseline và kết quả đối chiếu demo.
4. [Chuẩn bị dữ liệu benchmark](DPDP_DATA_PREPARATION_REPORT.md): nguồn dữ liệu, manifest và protocol chia tập.
5. [Tích hợp VNSME Java](VNSME_INTEGRATION_REPORT.md): baseline đánh giá chính, kiểm chứng instance 2 và trạng thái simulator Huawei.

## Thí nghiệm GP

1. [GP pilot đơn instance](GP_PILOT_REPORT.md): pilot ban đầu trên dữ liệu phát triển.
2. [GP đa instance 50 đơn](GP_MULTINSTANCE_DEVELOPMENT_REPORT.md): huấn luyện trên instance 2–5 và chọn cây bằng validation instance 6.

## Vị trí mã và dữ liệu

- Công cụ dòng lệnh, scorer, baseline, guard, lịch dự báo và kiểm thử vẫn ở thư mục gốc để giữ nguyên các lệnh đã dùng.
- Dữ liệu benchmark chính thức ở `datasets/`; protocol đã khóa ở `protocols/`.
- Kết quả được chia theo loại trong `baseline_runs/`, `dataset_runs/`, `gp_runs/` và `run_logs/`.
- Bằng chứng kiểm chứng được chia theo chủ đề trong `baseline_evidence/`, `dataset_evidence/`, `feasibility_schedule_evidence/` và `gp_evidence/`.
- Mã nguồn tham chiếu Xingtian dùng cho audit ở `scoring_reference/`.

Các thư mục kết quả và bằng chứng giữ nguyên đường dẫn vì manifest và hồ sơ chạy cũ có tham chiếu tới vị trí đó. Báo cáo được gom riêng để dễ tìm mà không sửa nội dung hoặc dữ liệu lịch sử.
