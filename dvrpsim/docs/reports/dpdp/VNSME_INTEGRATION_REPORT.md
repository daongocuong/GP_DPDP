# Tích hợp VNSME Java vào GP-DPDP — 08/11/2026

VNSME đã được tích hợp làm baseline đánh giá chính và đã chạy hết instance 2
trong dvrpsim. Greedy vẫn là mẫu số chuẩn hóa fitness GP. Mã Java, bộ sinh ứng
viên chèn, fitness, scorer, cây GP đã chọn và protocol chia tập cũ được giữ nguyên.
Lượt Huawei chưa chạy được vì Windows Application Control chặn DLL của pandas.
Không có điểm Huawei và chưa thể kết luận về chênh lệch giữa hai simulator.

## Khảo sát và cấu hình

Repo Python thực tế là `C:/Users/Cuongdz/Documents/LA/dvrpsim`; thư mục
`C:/Users/Cuongdz/Documents/LA/VNSME` chứa gói Java được cung cấp.

Entry point thí nghiệm là `run_dpdp_insertion.py`, dùng builder/provider/updater
trong `examples/case_studies/dpdp/dpdp_main.py`. Greedy và GP cùng dùng
`dpdp_insertion.py`; GP chỉ thay hàm chấm ứng viên. `Snapshot.check()` gọi
`dpdp_feasibility.validate()` để kiểm tra complete remaining plan. Điểm cuối
được tính lại bằng `verify_dpdp_score.py` từ log thực thi.

Protocol cũ `protocols/dpdp_gp_split_v1.json` giữ nguyên: train 2–5,
validation 6, final test 7–8 cho nhóm 50 đơn. Instance 2 là dữ liệu phát triển,
đã nằm trong train của cây GP; bảng này là kiểm chứng tích hợp, không phải
đánh giá cuối hoặc bằng chứng khái quát hóa. Không chạy rollout trên 7–8,
15–16. Suite cũ có kiểm tra inventory/checksum/loader của dữ liệu đã khóa;
việc đó không tạo rollout hoặc điểm trên các test cuối.

Gói Java không có README, Maven/Gradle hay launcher dùng được. Metadata nhắc
đến file Python không có trong gói. IntelliJ khai báo Java 8. Entry point thật
là `main_algorithm.main`; Java đọc đường dẫn tương đối dưới CWD, không nhận
đường dẫn dữ liệu từ args. Chi tiết trường JSON và đường dẫn được ghi trong
`third_party/vnsme/README.md` theo mã nguồn thực tế.

Build đã chạy bằng OpenJDK/javac **26.0.1**, với `--release 8 -encoding UTF-8`.
Build thành công, có cảnh báo deprecated/unchecked và target Java 8 đã cũ;
không có lỗi biên dịch. `original/` khớp byte với toàn bộ 10 file Java gốc;
3.748 class thư viện trong `lib/org/` khớp byte với gói cung cấp. Không sử dụng
`main_algorithm.class` có sẵn để thay cho việc build nguồn.

Simulator Huawei đầy đủ đã được lấy về `third_party/huawei-xingtian/` tại
commit **e4ef3a1c92d19d1d08c3ef0e2156b6fecefdbe04**, cùng commit với dữ liệu
và scoring reference cũ. Không sửa mã upstream. Harness chỉ thay lớp gọi
subprocess để cô lập dữ liệu, áp timeout và lưu bằng chứng từng kỳ.

## Adapter và ràng buộc

- `--policy vnsme` và `--policy greedy` được thêm vào runner. Các tên cũ
  `insertion`, `baseline`, `gp`, `demo` vẫn dùng được.
- Mỗi rollout có một CWD Java riêng. Mỗi kỳ lưu ba JSON đầu vào, hai JSON đầu
  ra, `solution_before.json` nếu có, `solution.json`, stdout/stderr và thông tin
  subprocess trong `vnsme/epochs/NNNNN/`.
- `solution.json` được giữ qua các kỳ, vì Java lưu toàn bộ kế hoạch nội bộ ở
  đó. Java gốc trì hoãn điều xe (`isDelay=true`), chỉ công bố phần tuyến cần
  thực hiện; đơn chưa công bố không được tự động chấp nhận. Adapter không ép
  xuất toàn bộ kế hoạch nội bộ.
- Trạng thái gửi Java chỉ lấy từ các đơn đã được order provider phát hành.
  Không lấy danh sách đơn tương lai trong `private_data['orders']`. Cung cấp
  cả đơn đã lên kế hoạch nhưng chưa lấy, đúng nghĩa Huawei “unallocated”.
- Khi xe đang phục vụ, dùng tải hàng dự kiến sau công việc hiện tại và thời
  điểm rời sớm nhất của hàm hiện có. Thứ tự hàng là đáy → đỉnh. Tuyến trả về
  không sửa current visit; guard kiểm tra lại trên tải thực tế và công việc
  còn lại của current visit.
- Java chỉ được sửa phần tuyến tương lai theo checker hiện có. Nhà máy và
  ETA của điểm đến đã công bố đều được đối chiếu với JSON Java trước khi
  chuyển đổi. Danh sách thao tác ở điểm đến được phép thay nếu vẫn hợp lệ.
- Guard kiểm tra LIFO, tải trung gian, lấy trước giao, sở hữu đơn, nguyên tắc
  chia đơn, giao hết các item đã nhận và khóa current/destination. Adapter
  chặn thêm item chưa biết/chưa phát hành và việc làm biến mất item đã nhận.
- Bổ sung `gps_id`, `operation_time`, loại pallet và trạng thái 1/2. Các mốc
  thời gian dùng offset nửa đêm của host cho cả rollout; thời lượng giữ nguyên.
  Giá trị không nguyên hoặc vượt miền `int` Java bị từ chối, không cắt ngầm.
- Trước mỗi subprocess, xóa hai output cũ. Exit code khác 0, thiếu `SUCCESS`,
  JSON thiếu/hỏng, sai tập xe, schema sai hoặc `solution.json` không tiến triển
  đều gây lỗi có đường dẫn epoch. Có xử lý lần Java tự reset bộ nhớ ở kỳ 600
  giây theo đúng mã gốc. Input/output JSON và tiến triển bộ nhớ được lưu lại.
- Kiểm tra hash source, thư viện và class với build manifest trước rollout;
  thay đổi mà chưa build lại sẽ gây lỗi rõ ràng.
- `--vnsme-epoch-seconds` là timeout riêng mỗi kỳ; `--wall-seconds` là budget
  cả lượt. Subprocess Java nhận mức nhỏ hơn của hai budget còn lại và được
  kết thúc khi timeout. Runner kiểm tra budget giữa các event và sau scoring.
  Công cụ so sánh còn có deadline tiến trình ngoài bằng budget + 30 giây để
  ghi artifact; khi vượt mức này nó dừng cả cây tiến trình.

Java gốc giả định xe `V_1..V_n` theo thứ tự, item có hậu tố liên tiếp và dispatch
600 giây. Adapter kiểm tra thứ tự xe. Các giả định này phù hợp instance 2;
không tuyên bố hỗ trợ dữ liệu tùy ý ngoài schema Huawei.

## Kết quả thực chạy cuối

Nguồn bảng: `vnsme_runs/verified_instance2/comparison.json`. Cả ba dùng seed 0,
cùng 5 xe, dữ liệu/hash, vị trí ban đầu, dispatch 600 giây, docking 1.800 giây,
load/unload 240 giây mỗi đơn vị, horizon 7 ngày và wall budget 1.800 giây.
Java mỗi kỳ có budget 600 giây. Thời gian ra quyết định gồm serialize, JVM,
optimizer, đọc kết quả và guard; là tổng thời gian của mọi kỳ.

`J = D / 5 + 10000 × T / 3600`, với T là tổng trễ theo đơn gốc, lấy thời điểm
đến nhà máy giao trước khi xếp hàng/docking/unload.

| Chính sách | Trạng thái | Đơn/item hoàn tất | J | D (km) | T (giây) | Tổng quyết định (giây) | Quyết định lớn nhất (giây) | Số kỳ | Tổng rollout (giây) |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Greedy | PASS | 50/110 | 8650.6 | 628.0 | 3069 | 0.451753 | 0.038525 | 174 | 0.601942 |
| GP đã chọn | PASS | 50/110 | 23840.566667 | 744.5 | 8529 | 0.450380 | 0.046198 | 170 | 0.591099 |
| VNSME Java | PASS | 50/110 | 95.74 | 478.7 | 0 | 29.861462 | 0.707444 | 167 | 30.022908 |
| VNSME / Huawei | BLOCKED lúc startup | Chưa chạy | — | — | — | — | — | 0 | 0.880946 đến lỗi startup |

Cây GP dùng nguyên file `gp_runs/multinstance_50_20261105/main/selected_tree.json`,
SHA-256 `283b97fb88376d2bdbb966d59c976038a619e497b700ed89b29a79db912d272f`.
Không chọn lại cây theo instance 2. Điểm greedy và GP khớp kết quả phát triển
cũ; mẫu số chuẩn hóa greedy không đổi. VNSME và GP dùng những lớp chính sách
khác nhau về khả năng sửa tuyến; đây là so sánh chính sách hoàn chỉnh trên cùng
simulator, không phải phép thử chỉ thay hàm chấm cùng tập ứng viên.

## Kiểm tra đã thực hiện

| Kiểm tra | Trạng thái | Bằng chứng |
| --- | --- | --- |
| Build nguồn Java gốc | PASS | `third_party/vnsme/build_manifest.json` |
| Nguồn và dependency khớp gói cung cấp | PASS | `third_party/vnsme/provenance.json` |
| Suite hồi quy và adapter | PASS, 134 tests | `vnsme_runs/final_tests.txt` |
| Complete-plan guard từng kỳ VNSME | PASS, 167 kỳ | `verified_instance2/vnsme/decisions.json` |
| Tất cả đơn/item hoàn tất | PASS cả ba | `verified_instance2/*/result.json` |
| Chấm lại độc lập log thực chạy | PASS cả ba | `*/comparison_independent_score.json` |
| Cấu hình, dữ liệu và vị trí ban đầu giống nhau | PASS | `comparison.json: same_simulator_configuration=true` |
| Archive không chứa item tương lai; khóa factory/ETA đúng | PASS, 167 kỳ | `vnsme_evidence/verification.json` |
| Core fitness/greedy/scorer/guard/schedule không đổi | PASS theo hash so với manifest probe đầu | `vnsme_evidence/verification.json` |
| Rollout Huawei hoàn tất/checker Huawei/điểm Huawei | CHƯA CHẠY | Startup bị chặn trước lần gọi Java đầu tiên |
| Đối chiếu hai simulator | CHƯA THỰC HIỆN | Chưa có trajectory/score Huawei |

Các đường dẫn rút gọn trong bảng nằm dưới `vnsme_runs/`. Những thư mục probe
khác được giữ lại, không dùng làm bằng chứng của bảng kết quả cuối.

## Vướng mắc Huawei

Simulator ban đầu chưa có trong workspace; hiện đã có đủ source đã ghim.
Venv ban đầu thiếu pandas/numpy; đã cài pandas 3.1.1, numpy 2.5.4 cùng các
dependency (xem `vnsme_evidence/environment.json`). Khi import, Windows trả:

```text
ImportError: DLL load failed while importing interval:
An Application Control policy has blocked this file.
```

Module bị chặn là `pandas._libs.interval`, trước khi khởi tạo simulator hoặc
gọi Java. Kết quả ghi `valid=false`, `score=null`, `decision_count=0` tại
`vnsme_runs/huawei_instance2_final/result.json`. Cần môi trường Python có
pandas được chính sách máy cho phép tải để chạy nốt. Không sửa hoặc tắt chính
sách bảo vệ máy. Không có cơ sở thực nghiệm để gán nguyên nhân chênh lệch điểm
giữa hai simulator tại thời điểm này.

## Lệnh chạy lại

Chạy PowerShell; mỗi `--output` phải là thư mục mới:

```powershell
Set-Location C:\Users\Cuongdz\Documents\LA\dvrpsim
.\.venv\Scripts\python.exe build_vnsme.py
.\.venv\Scripts\python.exe -m unittest discover -v
.\.venv\Scripts\python.exe compare_dpdp_baselines.py --output vnsme_runs\rerun_instance2 --wall-seconds 1800 --vnsme-epoch-seconds 600
```

Chạy riêng VNSME trong dvrpsim:

```powershell
.\.venv\Scripts\python.exe run_dpdp_insertion.py --policy vnsme --instance-directory datasets\xingtian\e4ef3a1c92d19d1d08c3ef0e2156b6fecefdbe04\benchmark\instance_2 --output vnsme_runs\rerun_vnsme_instance2 --wall-seconds 1800 --vnsme-epoch-seconds 600
```

Chạy Huawei sau khi pandas import được trong venv:

```powershell
.\.venv\Scripts\python.exe -c "import pandas; print(pandas.__version__)"
.\.venv\Scripts\python.exe run_vnsme_huawei.py --output vnsme_runs\rerun_huawei_instance2 --wall-seconds 1800 --vnsme-epoch-seconds 600
```

Harness Huawei cố định instance 2; không có chế độ quét tất cả instance.
Nếu cần lấy lại simulator, dùng ba lệnh trong `third_party/README.md`.
Lệnh compiler và Java thực tế, classpath tuyệt đối, CWD và phiên bản được
lưu trong build manifest và từng `vnsme/session.json`.

## File thêm hoặc sửa bởi tác vụ này

- **Sửa:** `run_dpdp_insertion.py`; `docs/reports/dpdp/README.md`.
- **Thêm mã:** `src/baselines/__init__.py`, `src/baselines/vnsme.py`,
  `build_vnsme.py`, `compare_dpdp_baselines.py`, `run_vnsme_huawei.py`,
  `test_dpdp_vnsme.py`.
- **Thêm protocol/tài liệu:** `protocols/dpdp_vnsme_integration_v1.json`,
  báo cáo này, `third_party/README.md`, `third_party/vnsme/README.md`.
- **Thêm mã gốc và build:** `third_party/vnsme/original/**`,
  `third_party/vnsme/lib/org/**`, `third_party/vnsme/build/**`,
  `third_party/vnsme/build_manifest.json`, `third_party/vnsme/provenance.json`;
  checkout độc lập `third_party/huawei-xingtian/`.
- **Thêm artifact:** `vnsme_runs/**`, `vnsme_evidence/environment.json`,
  `vnsme_evidence/verification.json`.
- **Môi trường:** cài thêm pandas, numpy, python-dateutil, tzdata trong venv;
  không đổi dependency bắt buộc của package dvrpsim.

Repo đã có nhiều file untracked và `dpdp_routing.py` đã được sửa trước tác vụ;
không coi những thay đổi sẵn có là thay đổi của tích hợp này. Không commit/push.
