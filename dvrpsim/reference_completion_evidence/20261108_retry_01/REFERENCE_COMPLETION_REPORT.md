# Hoàn thiện reference VNSME cho gp-fitness-vnsme-v2

Trạng thái tác vụ: **COMPLETE**.

Bắt đầu: 2026-11-08T19:59:51.195968+07:00. Kết thúc: 2026-11-08T21:04:11.428164+07:00.

## Lượt bị gián đoạn trước đây

Giữ trạng thái **INTERRUPTED**, nguyên nhân chưa được xác minh. Hai lượt
cũ không có result.json cuối, failure.json hoặc mã thoát của tiến trình.
Thư mục kỳ cuối chỉ có đầu vào và solution_before.json, không có invocation.json hoàn tất.

| Instance | Kỳ cuối bắt đầu (thư mục) | Số invocation đã hoàn tất |
| --- | --- | ---: |
| 5 | 00100 | 100 |
| 6 | 00063 | 63 |

Các dòng TimeOut!! trong những kỳ trước đó đi kèm exit code 0 và SUCCESS:
đây là giới hạn tìm kiếm nội bộ, không chứng minh nguyên nhân mất tiến trình.
Truy vấn sự kiện Windows có ghi nhận trạng thái nguồn thấp; chưa có bằng chứng
liên kết trực tiếp chúng với việc dừng Python/Java. Truy vấn crash và resource
exhaustion trong cửa sổ đã lưu không tìm thấy sự kiện Python/Java phù hợp.
Chi tiết nằm trong old_interruption_diagnosis.json, old_power_events.json
và old_crash_event_query.json; không sửa interrupted.json lịch sử.

## Giới hạn thời gian và provenance

- Java gốc kiểm tra thời gian tìm kiếm khoảng 540 giây từ đầu invocation.
  Đây là kiểm tra tại các điểm trong thuật toán, không phải hard timeout cho mọi operator.
- Adapter giới hạn subprocess mỗi kỳ bằng min(600, ngân sách tổng còn lại).
- Runner giới hạn cả lượt bằng 3.600 giây; supervisor có hard deadline ngoài
  3.630 giây để dành thời gian khởi tạo và ghi artifact.
- Mọi invocation đã hoàn tất của reference 2–4 dùng effective timeout 600 giây.
  Tăng giới hạn tổng từ 1.800 lên 3.600 không thay ngân sách tìm kiếm mỗi kỳ
  hoặc công thức J; loader lưu budget riêng của mỗi reference.
- Java build, class, thư viện, simulator, scorer và các dependency runtime
  được đối chiếu hash trước khi chạy. Không build lại và không sửa mã production.
- Runner so với manifest 2–4 chỉ khác guard từ chối các tên policy đã gỡ.
  Bỏ đúng guard đó cho hash khớp bản cũ; nhánh VNSME không đổi.
- Seed môi trường 0; Java gốc không nhận seed qua CLI, giữ nguyên cách gọi.
- SHA-256 build manifest: `49f85c57affe25a86e32522d82e16bde833c9211b7e34b56e08f79fd1f751046`.
- Dữ liệu, vị trí ban đầu, dispatch 600 giây, docking 1.800 giây, load/unload
  240 giây mỗi đơn vị, lambda 10.000 và horizon 7 ngày giữ nguyên.

## Kết quả hai lượt mới

| Instance | Trạng thái | Exit code | Kỳ cuối (thư mục) | Thời gian runner (giây) | Thời gian giám sát (giây) | Đơn/item hoàn tất |
| --- | --- | ---: | --- | ---: | ---: | --- |
| 5 | COMPLETE | 0 | 00152 | 3267.7279658000916 | 3279.075 | 50/107 |

Instance 5: `C:\Users\Cuongdz\Documents\LA\dvrpsim\migration_runs\reference_retry_20261108_01\instance_5`.
| 6 | COMPLETE | 0 | 00155 | 565.7710579000413 | 570.087 | 50/86 |

Instance 6: `C:\Users\Cuongdz\Documents\LA\dvrpsim\migration_runs\reference_retry_20261108_01\instance_6`.

Hai lượt chạy tuần tự: 5 kết thúc trước khi bắt đầu 6. Mỗi lượt dùng CWD
và solution.json riêng. Giám sát lưu heartbeat JSONL, cây tiến trình, PID,
bộ nhớ và thread dump cho các kỳ kéo dài. Java stdout/stderr vẫn theo adapter
gốc, được ghi vào archive sau khi invocation trả về. Mã thoát Windows quan sát
thêm nằm trong observed_process_exits.jsonl.

Lượt 5 mới dùng khoảng 3.268 giây, lớn hơn giới hạn tổng 1.800 giây cũ.
Điều này xác nhận budget cũ không đủ cho trajectory mới, không chứng minh
nguyên nhân dừng của trajectory cũ khi chưa có mã thoát.

Helper tạm thời yêu cầu hệ thống giữ thức trong lúc supervisor chạy và nhả
yêu cầu khi supervisor kết thúc, dùng [SetThreadExecutionState của Windows](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-setthreadexecutionstate).

## Summary và loader

Summary: `C:\Users\Cuongdz\Documents\LA\dvrpsim\migration_runs\vnsme_reference_ready\summary.json`.
SHA-256: `cf44e4a41cc7e1f29dbf98cd968a555d6dcefe0aade6a49d4e1575fbbf47f02d`.

Loader **PASS**: đủ train 2–5 và validation 6, mọi J dương, policy/version,
seed, build, input/config, artifact hash, guard, hoàn tất và chấm lại log hợp lệ.

| Instance | VNSME J | GP J đã lưu | J_GP/J_VNSME |
| --- | ---: | ---: | ---: |
| 2 | 95.74 | 23840.56666666666666666666667 | 249.013648074647 |
| 3 | 97.44 | 16767.09555555555555555555556 | 172.076103813173 |
| 4 | 100.76 | 164.52 | 1.632790789996 |
| 5 | 3303.926666666666666666666667 | 5417.302222222222222222222222 | 1.639655709334 |
| 6 | 105.04 | 184.08 | 1.752475247525 |

## Cây GP cố định

Cây: `C:\Users\Cuongdz\Documents\LA\dvrpsim\gp_runs\multinstance_50_20261105\main\selected_tree.json`.
SHA-256 file: `8c118c6ee23c2cb419e75a732eaa7bc45821118357a4100f2929b58b57313187`.
SHA-256 cây canonical: `283b97fb88376d2bdbb966d59c976038a619e497b700ed89b29a79db912d272f`.
Hash file bao gồm metadata; hash cây dùng biểu diễn canonical của các node.
Các tử số J lấy từ log GP đã lưu; hash log và scorer độc lập được xác minh lại.
Không chạy thêm rollout GP, không tiến hóa và không chọn lại cây.

Fitness train v2: **106.090549596787**.
Tỷ số validation instance 6: **1.752475247525**.

Công thức train là mean(J_GP(i)/J_VNSME(i)), i thuộc 2–5.
Validation là J_GP(6)/J_VNSME(6). Fitness lịch sử giữ nguyên định nghĩa cũ.

Lệnh huấn luyện để chạy sau, dùng thư mục output mới:

```powershell
Set-Location C:\Users\Cuongdz\Documents\LA\dvrpsim
.\.venv\Scripts\python.exe train_dpdp_gp_multinstance.py --baseline-summary migration_runs\vnsme_reference_ready\summary.json --output gp_runs\vnsme_v2_new_training
```

## Phạm vi và bảo toàn

Đã kiểm tra 17973 artifact lịch sử; unchanged = True.
Không chạy/chấm điểm instance 7–8 hoặc 15–16. Không huấn luyện GP.
Chỉ thêm artifact chạy mới và helper chẩn đoán trong thư mục bằng chứng này.
Bằng chứng chính: preflight.json, supervisor_status.json, adopt_invocation.json,
fitness_v2_verification.json và historical_preservation.json.
