# Trạng thái khôi phục VNSME v3

- Instance 2: reference đã xác minh; loader v3 PASS.
- Instance 3: PASS, loader v3 chấp nhận.
- Instance 4: restart từ đầu trong output riêng; PASS qua supervisor, scorer, independent replay và loader v3.
- Instance 5: INTERRUPTED theo lần ngắt của người dùng. Có 112 epoch bắt đầu và 111 epoch có marker kết thúc. Epoch 00111 còn hoạt động ở heartbeat cuối; không quan sát thấy Java timeout. Không có result.json, record.json hoặc supervisor summary cuối, do đó lượt chưa được chấp nhận.
- Instance 6: chưa chạy.
- Chưa tạo reference tổng hợp 2–6; GP v3 training chưa sẵn sàng.
- Không mở CSV đánh giá cuối, không chạy GP và không chạy instance đánh giá.

Bản đính chính epoch-count của lượt instance 4 lịch sử nằm ở historical_instance4_epoch_count_correction.md; artifact lịch sử được giữ nguyên. Output restart 4 và lượt 5 dở dang ở vnsme_runs/v3_references_3_6_20261109_recovery_r1/.