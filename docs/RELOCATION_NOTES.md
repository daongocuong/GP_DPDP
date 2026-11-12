# Ghi nhận relocation phục vụ khảo sát V2

Kiểm tra ngày 2026-11-11, Asia/Bangkok. Phạm vi: xác minh cấu trúc workspace và phân biệt đường dẫn cũ với artifact thiếu; không tái chứng nhận kết quả thí nghiệm hay khảo sát đầy đủ toàn repository.

## Cấu trúc thực tế

- Git root: `D:\LA`, branch `complete-gp-dpdp`; simulator: `D:\LA\dvrpsim`.
- Root có `docs/`, `dvrpsim/`, `VNSME/`, `.git/`, `.venv/`; simulator có `src/`, `examples/`, `datasets/`, `protocols/` và các collections runs/evidence.
- `C:\Users\Cuongdz\Documents\LA` không tồn tại tại thời điểm kiểm tra.
- Cả `D:\LA\.venv\Scripts\python.exe` và `D:\LA\dvrpsim\.venv\Scripts\python.exe` tồn tại. Hai `pyvenv.cfg` vẫn ghi lệnh tạo environment ở root cũ. Chỉ đọc metadata, chưa chạy interpreter/package checks; chưa kết luận environment hoạt động hoặc hỏng. Không tạo lại environment.
- Working tree đã có nhiều thay đổi staged/untracked trước lượt kiểm tra; không stage, commit hay thay đổi các nội dung đó.

## Bằng chứng reference V2

Đọc [summary V2](../dvrpsim/migration_runs/vnsme_reference_ready/summary.json), ánh xạ tiền tố cũ sang `D:\LA` chỉ trong bộ nhớ để kiểm tra. Không ghi lại đường dẫn trong summary/manifests/artifacts.

| Instance | Run tương đối với `dvrpsim/` | Vị trí cũ | Vị trí mới | SHA-256 các file được summary ghim |
| --- | --- | --- | --- | --- |
| 2 | `migration_runs/vnsme_reference/instance_2` | Không tồn tại | Tồn tại | 5/5 khớp |
| 3 | `migration_runs/vnsme_reference/instance_3` | Không tồn tại | Tồn tại | 5/5 khớp |
| 4 | `migration_runs/vnsme_reference/instance_4` | Không tồn tại | Tồn tại | 5/5 khớp |
| 5 | `migration_runs/reference_retry_20261108_01/instance_5` | Không tồn tại | Tồn tại | 5/5 khớp |
| 6 | `migration_runs/reference_retry_20261108_01/instance_6` | Không tồn tại | Tồn tại | 5/5 khớp |

Mỗi run kiểm tra `simulation.log`, `manifest.json`, `result.json`, `decisions.json`, `vnsme/session.json`: tổng cộng **25/25 file tồn tại và khớp SHA-256 trong summary**. Đây là stale absolute paths do relocation, không phải 25 artifacts bị mất. Không suy rộng kết quả này sang mọi per-epoch file, cache hoặc collection khác; không chạy replay/rescore.

## Ảnh hưởng tới khảo sát và loader

- [PROJECT_HOME](PROJECT_HOME.md) vẫn ghi Git root cũ trong bảng trạng thái; các snapshot handover/audit có thể chứa đường dẫn hoặc trạng thái lịch sử. Dùng cấu trúc thực tế nêu trên khi khảo sát, giữ nguyên các snapshot.
- [Loader V2](../dvrpsim/dpdp_vnsme_reference.py) lấy trực tiếp `row['run_directory']` để đọc/hash file; `independent_score` còn so sánh absolute `manifest['input_paths']` với input hiện tại. Theo source, các kiểm tra này có thể thất bại sau relocation dù payload còn nguyên. Chưa thực thi loader; không gọi thông báo lỗi đường dẫn là bằng chứng mất artifact hay kết quả sai.
- Sửa summary đơn lẻ không giải quyết toàn bộ provenance: manifests cũng chứa paths và được ghim hash. Không chỉnh historical artifacts, sidecars hoặc hashes để làm kiểm tra qua.
- Khi kiểm tra một đường dẫn cũ: ghi nhận chuỗi gốc, kiểm tra vị trí gốc, kiểm tra counterpart cùng hậu tố dưới `D:\LA`, rồi đối chiếu hash nếu có pin. Phân biệt: stale path với counterpart tồn tại; không tìm thấy cả hai vị trí; có file nhưng hash khác; chưa đủ bằng chứng. Không kết luận file bị mất do relocation chỉ từ một đường dẫn không tồn tại.

## Ví dụ artifact thực sự không có tại vị trí mới

Trong `dvrpsim/gp_runs/official_gp_multinstance_20261109/`, `experiment_protocol.json` và `generation_0.json` tồn tại; `training.json` và `selected_tree.json` không tồn tại tại vị trí mới. [PROJECT_HOME](PROJECT_HOME.md) đã ghi run này incomplete trước lượt kiểm tra này. Phân loại là **thiếu output cuối tại run được kiểm tra**, không quy nguyên nhân cho relocation và không suy đoán process đang chạy. Chưa tìm kiếm các bản sao ở mọi nơi khác.

Lượt kiểm tra chỉ đọc filesystem/source/metadata và tính hash các file V2 được nêu; thay đổi duy nhất là tài liệu ghi nhận này. Không sửa hàng loạt paths, sửa historical artifacts/hashes, build, training, chạy test suite, đọc nội dung sealed instances hay tái tạo environment.
