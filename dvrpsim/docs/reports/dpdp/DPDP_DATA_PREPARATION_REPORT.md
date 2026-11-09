# Chuẩn bị instance chính thức cho GP-DPDP

Ngày: 05/11/2026, Asia/Bangkok. **Không chạy GP, không huấn luyện hoặc chọn cây, không chạy test cuối.**

## 1. Nguồn duy nhất và cấu trúc dữ liệu

Nguồn: `huawei-noah/xingtian`, commit cố định
`e4ef3a1c92d19d1d08c3ef0e2156b6fecefdbe04`, thư mục
`simulator/dpdp_competition/benchmark/`.

https://github.com/huawei-noah/xingtian/tree/e4ef3a1c92d19d1d08c3ef0e2156b6fecefdbe04/simulator/dpdp_competition/benchmark

Đã tải **32 CSV nguyên byte**: 30 tệp của instance_2–16 và hai CSV dùng chung.
Không tải từ branch động hoặc nguồn khác; không tạo dữ liệu thay thế.
Mỗi tệp tải từ raw.githubusercontent.com tại commit trên, kiểm tra Git blob SHA-1 với tree của chính commit,
rồi ghi SHA-256 vào manifest. Không clone/fetch/reset repository dvrpsim hoặc thay đổi lịch sử Git.

```text
datasets/xingtian/e4ef3a1c92d19d1d08c3ef0e2156b6fecefdbe04/
    source_manifest.json
    source_manifest.sha256
    benchmark/
        factory_info.csv
        route_info.csv
        instance_2/ ... instance_16/
```

Manifest có URL, source path, commit, filename, Git blob SHA-1, SHA-256, byte count cho từng tệp;
mỗi instance còn có số đơn gốc, item sau loader, xe và kết quả kiểm chứng.

**SHA-256 source_manifest.json:**

```text
cf72390459bdb50facd666ae4dbbaa9b6712f2161d61ba6756309a0c100968bc
```

Hai CSV dùng chung đã so với dữ liệu local kiểm chứng trước đây, **trùng từng byte**:

| CSV | SHA-256 |
|---|---|
| factory_info.csv | ed0f987404c09c0bf562212478784f29e29ce41f52cebbb277e1e219dd9a81e4 |
| route_info.csv | 26e6cc70cf96c2a73e0ce3fdd9d002715a0719c92802544aa810b669772a3550 |

Có 154 nhà máy và 23562 cặp OD có hướng. Bản local không bị thay thế; hai bản mới nằm trong snapshot dữ liệu riêng.

## 2. Bảo toàn và thay đổi mã

- Interpreter: `C:\Users\Cuongdz\Documents\LA\dvrpsim\.venv\Scripts\python.exe`, Python 3.14.4.
- Git main, commit nền `29f4cd8f481fa5ac8cbf97a1372ee5b845e20c4a` giữ nguyên. Không commit/push hoặc cài thư viện.
- Không tìm thấy AGENTS.md áp dụng trong chuỗi thư mục cha hoặc repository, ngoài .git/.venv đã loại trừ.
- Trạng thái Git và hashes của 278 tệp có sẵn được lưu trước làm việc.
- **277/278 tệp có sẵn giữ nguyên byte**; tệp duy nhất sửa là `run_dpdp_insertion.py`.
- Giữ nguyên instance_1, instance_17, mọi CSV cũ, scorer, audit, cây GP, cache/log/kết quả pilot, bằng chứng cũ và bản sửa vehicle_id.

Tệp sửa/tạo:

| Tệp | Nội dung |
|---|---|
| run_dpdp_insertion.py | Thêm --instance-directory và --data-directory; tự tìm đúng một order/vehicle CSV, truyền cùng file dùng chung vào loader, manifest và scorer |
| dpdp_dataset.py | Resolve input và kiểm tra schema/ID/tải/thời gian/loader, không chạy simulator |
| prepare_dpdp_data.py | Tải đúng nguồn/commit, kiểm tra blob/hash/common CSV, manifest, verify offline |
| lock_dpdp_protocol.py | Tạo protocol và SHA-256 trước thí nghiệm; kiểm tra hash và quyền baseline calibration |
| measure_dpdp_data.py | Chỉ chạy baseline, từ chối test đã khóa, deadline và scorer CLI độc lập |
| test_dpdp_dataset.py | 14 kiểm tra mới |
| protocols/dpdp_gp_split_v1.json và .json.sha256 | Protocol phân tập đã khóa |
| dataset_evidence/ | Trạng thái trước sửa, kết quả kiểm tra và bảo toàn cuối |
| dataset_runs/baseline_calibration_20261105/ | Năm lượt baseline mới, summary, manifests và log |
| DPDP_DATA_PREPARATION_REPORT.md | Báo cáo này |

Các lựa chọn legacy --instance 1/17 và default instance_1 giữ nguyên.
Không sửa logic policy, guard, forecast, objective hoặc loader.
Log baseline instance_1 chạy hồi quy trùng từng byte với log baseline đã có.

## 3. Kiểm chứng dữ liệu và loader

Tất cả 15 instance mới đều đạt:

- Header/schema đúng thứ tự cột mà loader hiện tại đọc theo chỉ số; không có ô thừa/thiếu.
- ID factory/order/vehicle hợp lệ và không trùng trong tập tương ứng; các nhà máy trong route/order tồn tại.
- Ma trận OD đầy đủ, khoảng cách/thời gian hữu hạn và không âm; bến hữu hạn có sức chứa dương.
- Fleet đồng nhất; q_standard/q_small/q_box là số nguyên không âm; mỗi đơn có item; demand bằng tổng quantity 1/0.5/0.25.
- Item nguyên vẹn vừa tải xe. Đơn gốc vượt tải được ghi nhận, không bị sửa hoặc loại.
- load_time/unload_time của CSV khớp quantity * 240 mà loader hiện tại áp dụng.
- Giờ HH:MM:SS hợp lệ; due qua ngày cộng 86400 theo loader; không biến giao trễ thành bất khả thi.
- Gọi loader thật, đối chiếu từng item ID, original_id, quantity, release, due, pickup/delivery, xe và ma trận với dữ liệu CSV.

Các bản CSV chính thức không bị chỉnh sửa để qua kiểm tra.
Mạng tải thành công; không có mismatch common CSV hoặc lỗi loader cần sửa.
Downloader được kiểm tra nhánh lỗi mạng và byte mismatch: fail closed, không tạo dữ liệu giả, không cho tiếp tục thí nghiệm.

## 4. Kiểm kê và trạng thái từng instance

Tất cả dòng dưới đây đã tải đúng nguồn và kiểm chứng schema/hash/loader; mỗi instance có vehicle_info_5.csv, **5 xe**.

| Instance | Order CSV | Đơn gốc | Item sau loader | Vai trò | Baseline trong tác vụ |
|---|---|---:|---:|---|---|
| 2 | 50_2.csv | 50 | 110 | Train | Hoàn tất hợp lệ |
| 3 | 50_3.csv | 50 | 78 | Train | Chưa chạy |
| 4 | 50_4.csv | 50 | 88 | Train | Chưa chạy |
| 5 | 50_5.csv | 50 | 107 | Train | Chưa chạy |
| 6 | 50_6.csv | 50 | 86 | Validation | Hoàn tất hợp lệ |
| 7 | 50_7.csv | 50 | 150 | Test cuối, giữ kín | Không rollout/chấm điểm |
| 8 | 50_8.csv | 50 | 128 | Test cuối, giữ kín | Không rollout/chấm điểm |
| 9 | 100_1.csv | 100 | 175 | Train đề xuất | Hoàn tất hợp lệ |
| 10 | 100_2.csv | 100 | 295 | Train đề xuất | Chưa chạy |
| 11 | 100_3.csv | 100 | 182 | Train đề xuất | Chưa chạy |
| 12 | 100_4.csv | 100 | 253 | Train đề xuất | Chưa chạy |
| 13 | 100_5.csv | 100 | 157 | Validation đề xuất | Hoàn tất hợp lệ |
| 14 | 100_6.csv | 100 | 201 | Validation đề xuất | Chưa chạy |
| 15 | 100_7.csv | 100 | 182 | Test cuối đề xuất, giữ kín | Không rollout/chấm điểm |
| 16 | 100_8.csv | 100 | 173 | Test cuối đề xuất, giữ kín | Không rollout/chấm điểm |

Test 7/8/15/16 chỉ được đọc để kiểm checksum/schema/count/loader theo yêu cầu kiểm kê; không chạy simulator, không có D/T/J hoặc GP trên chúng.
Instance_1 và instance_17 giữ ở thư mục local cũ: 1 chạy baseline hồi quy; 17 không chạy lại trong tác vụ.

## 5. Protocol phân tập khóa trước thí nghiệm

Tệp: `protocols/dpdp_gp_split_v1.json`.

**SHA-256:**

```text
21c7f62c06a4402214dd0051728bec4fb8051cb8ab420866cd565c669a49f859
```

Protocol tham chiếu đúng hash manifest nguồn, được ghi trước mọi baseline calibration mới và trước mọi GP mới.
Không thay đổi protocol sau khi xem điểm baseline.

- Development đã phơi bày kết quả: **1 và 17**; không coi là test chưa đụng tới.
- 50 đơn: train **2–5**, validation **6**, test cuối **7–8**.
- 100 đơn, đề xuất riêng: train **9–12**, validation **13–14**, test cuối **15–16**.
- Baseline calibration được cho phép trong bước này: **2,6,9,13**; hồi quy legacy **1**.
- gp_allowed_this_task=false; test 7/8/15/16 bị chặn bởi script calibration.

Kết quả trên 9/13 chỉ là phép đo baseline trên train/validation đề xuất, không được gọi là test cuối.
Nếu một instance được dùng để chọn phương pháp ở bước sau thì phải ghi rõ vai trò phát triển/validation;
không đổi tên các kết quả đó thành test chưa dùng.
Các instance dùng chung mạng nhà máy; chia theo ID không tự chứng minh độc lập thống kê hoặc khả năng chuyển sang mạng mới.

## 6. Baseline thực đo và scorer độc lập

Chỉ policy baseline hiện có, seed vị trí xe 0, dispatch 600 giây,
docking 1800 giây, load/unload 240 giây/đơn vị, safety horizon 7 ngày mô phỏng.
Deadline đo khả năng chạy là **180 giây toàn tiến trình/lượt**, không phải ngân sách GP được suy từ pilot cũ.
Không cắt tỉa ứng viên, không thay CSV hay công thức để giảm thời gian/điểm.

| Instance / vai trò | Đơn/item hoàn tất | Hợp lệ | D km | T giây | J độc lập | Wall toàn tiến trình | Callback lớn nhất |
|---|---|---|---:|---:|---:|---:|---:|
| 1 / hồi quy development | 50/95 | Có | 852.7 | 0 | 170.54 | 0.859454 s | 0.013943 s |
| 2 / train 50 | 50/110 | Có | 628.0 | 3069 | 8650.6 | 0.994878 s | 0.039813 s |
| 6 / validation 50 | 50/86 | Có | 683.0 | 2600 | 7358.822222… | 0.871506 s | 0.021956 s |
| 9 / train 100 đề xuất | 100/175 | Có | 1105.1 | 430699 | 1196607.131111… | 4.944900 s | 0.354813 s |
| 13 / validation 100 đề xuất | 100/157 | Có | 1089.0 | 664101 | 1844942.8 | 9.444550 s | 0.684768 s |

| Instance | Ứng viên xét | Bị loại trước forecast |
|---|---:|---:|
| 1 | 970 | 401 |
| 2 | 1160 | 509 |
| 6 | 974 | 383 |
| 9 | 11647 | 7308 |
| 13 | 15572 | 9752 |

Wall toàn tiến trình đo bằng perf_counter ở parent, gồm khởi động Python,
manifest/data/build, mô phỏng, callback và scorer trong runner. Scorer CLI kiểm tra lại sau đó không cộng vào cột này.
Thời gian từng callback và thời gian mô phỏng tương ứng nằm trong decisions.json.
Không đồng nhất wall time với thời gian mô phỏng; các đơn trễ vẫn hợp lệ và bị phạt theo J.

Mỗi output folder có simulation.log, manifest.json, result.json, decisions.json và independent_score.json.
Scorer CLI chạy độc lập dùng đúng order/vehicle CSV của instance và ma trận mới đã đối chiếu,
kiểm tra đủ item/sự kiện/chặng xe rồi tính D/T/J. Không dùng điểm lựa chọn ứng viên thay J thực.

## 7. Đề xuất ngân sách rollout GP từ số đo

Các đề xuất nằm trong summary.json, **chưa áp vào hoặc chạy GP**:

| Quy mô | Baseline đại diện | Wall lớn nhất đo được | Ngân sách GP ban đầu đề xuất |
|---|---|---:|---:|
| 50 đơn / 5 xe | 2 và 6 | 0.994878 s | **30 giây/subprocess rollout** |
| 100 đơn / 5 xe | 9 và 13 | 9.444550 s | **60 giây/subprocess rollout** |

Quy tắc đề xuất minh bạch: 5 lần wall baseline lớn nhất đo được, làm tròn lên bội 10 giây,
với floor 30 giây cho 50 đơn và 60 giây cho 100 đơn.
Đây là ngân sách khởi đầu có headroom, không phải chặn trên đã chứng minh cho mọi cây GP.
Cây kém có thể tạo tuyến dài và nhiều ứng viên hơn baseline; cần đo tỷ lệ timeout và chi phí trên train/validation,
khóa ngân sách huấn luyện cuối trước khi mở test cuối. Không dùng kết quả test để nâng timeout hoặc chọn phương pháp.
Không suy ra giới hạn chung từ timeout 10 giây pilot cũ, hoặc suy rằng đã đáp ứng ngân sách 10 phút của benchmark.

## 8. Kiểm tra và bằng chứng bảo toàn

**97/97 kiểm tra liên quan PASS:** 83 kiểm tra baseline/feasibility/schedule/scorer có sẵn + 14 kiểm tra dữ liệu/protocol mới.
Đầu ra thật: `dataset_evidence/related_tests.txt`.

Các ca mới kiểm tra path legacy và directory mới, từ chối file mơ hồ,
schema positional, unknown factory, count âm/phân số, giờ sai, thời gian xếp/dỡ không khớp,
common-byte mismatch, lỗi mạng không tạo dataset giả, verify offline trên dữ liệu thật,
vai trò phân tập, chặn test và phát hiện protocol bị sửa.

Không gọi suite test GP có rollout thật, vì yêu cầu của bước này là không chạy GP.
Không huấn luyện hoặc chọn cây theo validation; không đọc điểm GP mới của bất kỳ instance nào.
`dataset_evidence/final_verification.json` ghi source/protocol hashes, Git HEAD không đổi,
log baseline instance_1 trùng byte với bản cũ, 0 GP run và 0 sealed-test rollout.

## 9. Lệnh tái lập

Dùng đúng venv. Downloader từ chối ghi đè output tồn tại; để tải lại, chọn output mới hoặc dùng workspace sạch.
Commit nguồn là hằng số trong downloader, không có tùy chọn đổi branch/source.

```powershell
Set-Location 'C:\Users\Cuongdz\Documents\LA\dvrpsim'
$Data = '.\datasets\xingtian\e4ef3a1c92d19d1d08c3ef0e2156b6fecefdbe04'

# Lấy dữ liệu trên workspace sạch, hoặc đổi --output sang đường dẫn mới:
& '.\.venv\Scripts\python.exe' -B '.\prepare_dpdp_data.py' --output $Data

# Với snapshot đã có, chỉ verify offline, không ghi đè:
& '.\.venv\Scripts\python.exe' -B '.\prepare_dpdp_data.py' --output $Data --verify-only

# Tạo protocol trên workspace sạch; nếu đã có, kiểm tra hash thay vì ghi đè:
& '.\.venv\Scripts\python.exe' -B '.\lock_dpdp_protocol.py' --dataset $Data --output '.\protocols\dpdp_gp_split_v1.json'
Get-FileHash "$Data\source_manifest.json" -Algorithm SHA256
Get-FileHash '.\protocols\dpdp_gp_split_v1.json' -Algorithm SHA256

# Baseline-only calibration, chỉ IDs đã được protocol cho phép; output phải mới:
& '.\.venv\Scripts\python.exe' -B '.\measure_dpdp_data.py' --protocol '.\protocols\dpdp_gp_split_v1.json' --output '.\dataset_runs\calibration_rerun'

# Hoặc chạy riêng một instance train, không GP:
& '.\.venv\Scripts\python.exe' -B '.\run_dpdp_insertion.py' --policy baseline --instance-directory "$Data\benchmark\instance_2" --seed 0 --wall-seconds 180 --output '.\dataset_runs\instance2_rerun'

& '.\.venv\Scripts\python.exe' -B -m unittest -v test_dpdp_feasibility test_dpdp_execution_guards test_dpdp_schedule test_verify_dpdp_score test_dpdp_insertion test_dpdp_dataset
```

Nếu tải mạng lỗi, script ghi ACQUISITION_FAILED.json với URL/lỗi cụ thể và cấm calibration.
Nếu hai CSV chung khác byte, script dừng trước khi tải/ghi instance mới; không sửa CSV để tiếp tục.
Nếu snapshot bị sửa sau tải, verify_existing và calibration kiểm tra checksum trước khi chạy.

## 10. Việc tối thiểu còn cần trước đợt huấn luyện GP tiếp theo

**Dữ liệu và runner baseline đã sẵn sàng; preset GP cũ chưa phải protocol huấn luyện mới.**

1. Cho GP fitness evaluator nhận danh sách/path từ protocol đã khóa. discover_instances/context hiện vẫn mặc định thư mục legacy chỉ có 1/17;
   CLI runner đã nhận directory mới nhưng trainer cũ vẫn train=[1]. Không chỉ chạy lại preset cũ rồi gọi là thí nghiệm trên dữ liệu mới.
2. Khóa cấu hình huấn luyện mới tham chiếu hash protocol và manifest: train 2–5, validation 6,
   ngân sách ban đầu 30 giây cho nhóm này, seed tiến hóa và cách gộp fitness nhiều instance.
   Chưa tự chọn ở đây giữa trung bình J và chuẩn hóa bằng baseline cố định trên train.
3. Giữ cache key đầy đủ path/instance, data hashes, cấu hình thời gian, seed và source version; dùng cache/output mới,
   không tái sử dụng mù cache fitness của pilot instance_1.
4. Áp whitelist train/validation và chặn test 7/8/15/16 trong orchestration GP;
   chỉ mở test cuối sau khi phương pháp, selection rule và ngân sách được khóa và có tác vụ đánh giá cuối riêng.
   Với nhóm 100 đơn, chốt vai trò đề xuất trước khi học/chọn phương pháp; các phép đo 9/13 hiện là calibration train/validation.

Không còn lỗi mạng/schema/loader hoặc baseline bị chứng minh cản trở việc chuẩn bị dữ liệu.
Phần còn thiếu trước huấn luyện mới là nối fitness/trainer vào protocol nhiều instance và khóa cấu hình huấn luyện,
không phải tạo thêm dữ liệu hoặc thay giá trị benchmark.
