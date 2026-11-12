# Kết quả khôi phục và trạng thái reference VNSME v3

## Reference đã chấp nhận

| Instance | Vai trò | D (km) | T (giây) | J | Runtime mô phỏng (giây) | Independent replay | Loader v3 |
|---:|---|---:|---:|---:|---:|---|---|
| 2 | Train | 478.7 | 0 | 95.74 | 32.13 | PASS | PASS |
| 3 | Train | 487.2 | 0 | 97.44 | 26.72 | PASS | PASS |
| 4 | Train | 504.6 | 0 | 100.92 | 1649.26 | PASS | PASS |

Ba lượt dùng chung contract v3, source revision 0bd773291d5d9034f1e7b81688bc2dfaf87308c7, Java build SHA-256 49f85c57affe25a86e32522d82e16bde833c9211b7e34b56e08f79fd1f751046, protocol SHA-256 c751559337adbe2138a455819465764d726cf4bba26e5544715df4b90e44b6ed và split SHA-256 21c7f62c06a4402214dd0051728bec4fb8051cb8ab420866cd565c669a49f859. Mỗi instance có hash dữ liệu đơn riêng theo đúng bộ dữ liệu.

## Instance 4: restart, không resume

Không có checkpoint/resume đã kiểm chứng để khôi phục đồng thời simulator, event queue, trạng thái Python/Java và RNG. Vì vậy instance 4 được chạy lại từ đầu, không nối log lượt cũ. Lượt mới hoàn tất 155 quyết định, giao đủ 50 đơn/88 item; scorer/replay audit và loader đều chấp nhận. Supervisor EXITED mã 0, không gap, không process sót; runtime giám sát 1650.87 giây.

Ba epoch Java tốn thời gian nhất:

| Epoch | Thời gian Java (giây) | CPU Java (giây) | Timeout | Exit |
|---:|---:|---:|---|---:|
| 00104 | 540.07 | 530.12 | Không | 0 |
| 00105 | 540.09 | 531.27 | Không | 0 |
| 00106 | 540.08 | 529.38 | Không | 0 |

## Instance 5: bị ngắt, chưa được chấp nhận

Lượt có 112 epoch bắt đầu; 111 epoch có marker kết thúc. Epoch 00111 bắt đầu lúc 2026-11-09 17:07:11 UTC và còn chạy ở heartbeat cuối lúc 17:13:10 UTC: epoch elapsed 359.05 giây, Java CPU 354.27 giây. Timeout cứng epoch là 600 giây, nên chưa xảy ra timeout. Heartbeat có 5158 mẫu, khoảng cách lớn nhất 1.044 giây. Tiến trình Java và Python liên quan không còn sau lần ngắt, nhưng không có result.json, record.json hoặc supervision.json cuối; do đó đây không phải reference hợp lệ.

## Kết quả chưa hoàn tất

Instance 6 chưa chạy. Reference tổng hợp 2–6 chưa tạo hoặc chấp nhận, nên GP v3 training chưa sẵn sàng. Không chạy GP, không chạy instance đánh giá cuối và không mở CSV sealed. Các artifact lịch sử và output dở dang được giữ nguyên.

Chi tiết máy có ở accepted_references_2_4_audit.json và instance5_interrupted.json. Bản đính chính đếm epoch lượt instance 4 lịch sử nằm trong historical_instance4_epoch_count_correction.md.