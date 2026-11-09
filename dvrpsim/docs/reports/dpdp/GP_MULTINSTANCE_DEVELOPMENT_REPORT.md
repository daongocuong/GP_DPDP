# Báo cáo thí nghiệm GP-DPDP trên nhiều instance 50 đơn

## Phạm vi và dữ liệu

- Python: `.venv\Scripts\python.exe`, phiên bản 3.14.4; `dvrpsim` 0.0.1; SimPy 4.1.2.
- Git HEAD: `29f4cd8f481fa5ac8cbf97a1372ee5b845e20c4a`. Không commit hoặc push.
- Protocol: `protocols/dpdp_gp_split_v1.json`, SHA-256 `21c7f62c06a4402214dd0051728bec4fb8051cb8ab420866cd565c669a49f859`.
- Manifest nguồn: `datasets/xingtian/e4ef3a1c92d19d1d08c3ef0e2156b6fecefdbe04/source_manifest.json`, SHA-256 `cf72390459bdb50facd666ae4dbbaa9b6712f2161d61ba6756309a0c100968bc`.
- Dữ liệu lấy từ `huawei-noah/xingtian`, commit `e4ef3a1c92d19d1d08c3ef0e2156b6fecefdbe04`.
- Hash protocol và manifest được xác minh trước các lượt chạy. Evaluator xác minh lại hai hash này trước từng rollout. GP chỉ chạy trên instance 2–6; không chạy, chấm điểm hoặc chọn cây bằng instance 7–8, 15–16. Instance 1 và 17 không dùng để tính fitness hay chọn cây.

## Quy tắc và cấu hình đã khóa

Train gồm instance `[2, 3, 4, 5]`; validation là instance `[6]`; test cuối `[7, 8]` được giữ kín. Baseline chạy với seed môi trường 0 và timeout 30 giây. GP dùng cùng seed môi trường, cấu hình simulator và timeout. Seed tiến hóa là `20261106`; population 6; generation 0–2; tournament 3; crossover 0.8; mutation 0.3; elitism 1.

Không thay đổi bộ sinh ứng viên, guard, lịch dự báo, đặc trưng, baseline hay cách chuẩn hóa (không chuẩn hóa thêm).

Fitness train là trung bình đều của bốn tỷ số `J_GP(i) / J_baseline(i)`. Mọi mẫu số baseline phải dương. Cây chỉ hợp lệ nếu hoàn tất và được scorer độc lập xác nhận trên cả bốn instance train. Nếu một rollout lỗi hoặc timeout, cây nhận fitness phạt `1e15`; điểm benchmark của rollout lỗi để `null`, và instance đó không bị loại khỏi phép gộp.

Sau tiến hóa, các cây sinh từ train được xét trên validation. Chọn cây hợp lệ có tỷ số J thấp nhất trên instance 6; nếu hòa, lần lượt ưu tiên fitness train thấp hơn, cây ít node hơn, rồi biểu diễn chuẩn theo thứ tự từ điển. Validation không tham gia fitness tiến hóa.

## Kết quả baseline

Baseline instance 3–5 được chạy mới. Log cũ của instance 2 và kết quả baseline instance 6 được chấm lại bằng scorer độc lập. Tất cả các lượt đều hoàn tất hợp lệ với seed 0.

| Instance | Số đơn/item hoàn tất | D (km) | T (giây) | J | Thời gian rollout (giây) | Callback lâu nhất (giây) |
|---:|---:|---:|---:|---:|---:|---:|
| 2 | 50/110 | 628.0 | 3,069 | 8,650.6 | 0.596 | 0.0398 |
| 3 | 50/78 | 604.9 | 0 | 120.98 | 0.493 | 0.0245 |
| 4 | 50/88 | 676.5 | 0 | 135.3 | 0.545 | 0.0380 |
| 5 | 50/107 | 640.2 | 3,158 | 8,900.262222… | 0.524 | 0.0267 |
| 6 (validation) | 50/86 | 683.0 | 2,600 | 7,358.822222… | 0.495 | 0.0220 |

Các kết quả scorer và manifest của baseline nằm trong `gp_runs/multinstance_50_20261105/baseline/`. Log baseline cũ không bị sửa.

## Đo chi phí và kết quả huấn luyện

Probe chi phí dùng 2 cây trên đủ bốn instance train: 8/8 rollout hợp lệ, không timeout; một thế hệ mất 39.974 giây. Sau phép đo này, thí nghiệm chính chạy population 6 với hai thế hệ tiến hóa.

| Thế hệ | Cây hợp lệ | Thời gian thế hệ (giây) |
|---:|---:|---:|
| 0 | 6/6 | 108.378 |
| 1 | 6/6 | 72.358 |
| 2 | 6/6 | 124.393 |

Tổng thời gian thí nghiệm, gồm train, validation, tạo khóa cache và xác minh, là **366.218 giây**. Có 11 cây duy nhất được tạo; cả 11 đều hợp lệ trên train và validation. Có 55 tiến trình rollout thật và 72 cache hit từ các lần đánh giá lại; cả 55 rollout đều hoàn tất. Timeout: 0; lỗi số học của cây: 0; rollout không hợp lệ: 0. Cache mới nằm trong `main/fitness`; cache của pilot cũ không được dùng. Probe được lưu riêng trong `generation_probe_v3`. Hai thư mục probe trước đó giữ lại các lượt tích hợp bị lỗi.

Cây được chọn theo quy tắc validation:

`(((delta_tardiness_seconds / delta_distance_km) - min_residual_capacity) + delta_tardiness_seconds)`

SHA-256 cây: `283b97fb88376d2bdbb966d59c976038a619e497b700ed89b29a79db912d272f`; 7 node, độ sâu 3. Fitness train của cây là **35.793630**. Hash `dpdp_gp_fitness.py` tại thời điểm thí nghiệm: `d06236da401a93f127b69379e7f61a9563dfd3d4127d9acefffd60b8c6d65add`.

Sau thí nghiệm, adapter được sửa để các bài kiểm tra dùng lại được đường dẫn instance legacy. Thay đổi đó chỉ ảnh hưởng nhánh legacy; thí nghiệm đa instance dùng nhánh `instance-directory`. Hash hiện tại của file là `5b6c39613bf1c15bb5c0d567080c76637f930dd87ab2e05f2c59b9c9e92e5087`. Toàn bộ suite hồi quy đã chạy sau thay đổi này.

## So sánh cây được chọn với baseline

Điểm GP được tính từ quỹ đạo hoàn tất và được kiểm tra bằng scorer độc lập. Thời gian và callback dưới đây thuộc rollout của cây được chọn.

| Instance | Vai trò | Số đơn/item | Baseline J | GP D (km) | GP T (giây) | GP J | J_GP/J_baseline | GP rollout (giây) | Callback lâu nhất (giây) |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 2 | train | 50/110 | 8,650.6 | 744.5 | 8,529 | 23,840.566667 | 2.756 | 1.043 | 0.0454 |
| 3 | train | 50/78 | 120.98 | 807.7 | 5,978 | 16,767.095556 | 138.594 | 0.943 | 0.0174 |
| 4 | train | 50/88 | 135.3 | 822.6 | 0 | 164.52 | 1.216 | 0.947 | 0.0289 |
| 5 | train | 50/107 | 8,900.262222 | 725.4 | 1,898 | 5,417.302222 | 0.609 | 1.050 | 0.0336 |
| 6 | validation | 50/86 | 7,358.822222 | 920.4 | 0 | 184.08 | 0.0250 | 0.937 | 0.0113 |

Cây thắng baseline ở instance 5, nhưng thua ở 2, 3 và 4. Trung bình tỷ số train là 35.794, kém baseline theo fitness đã khóa. Trên instance validation 6, J của cây thấp hơn baseline nên cây được chọn theo đúng quy tắc đã định. Đây chỉ là kết quả trên instance validation đã dùng để chọn cây, không chứng minh khả năng tổng quát hóa hoặc ưu thế của GP. Tỷ số ở instance 3 cao do J baseline tại đó thấp; cách gộp tỷ số đã được khóa trước khi chạy GP.

## Artifact và lệnh tái lập

- Baseline mới và kết quả chấm: `gp_runs/multinstance_50_20261105/baseline/`.
- Probe thế hệ: `gp_runs/multinstance_50_20261105/generation_probe_v3/`.
- Thí nghiệm chính, các thế hệ, fitness, cache và cây được chọn: `gp_runs/multinstance_50_20261105/main/`.
- Kiểm chứng cuối: `gp_evidence/multinstance_final_verification.json`.
- Kết quả kiểm thử: `gp_evidence/multinstance_tests_final_20261105.txt`.

Huấn luyện lại trong thư mục output mới:

```powershell
Set-Location 'C:\Users\Cuongdz\Documents\LA\dvrpsim'
& '.\.venv\Scripts\python.exe' -B '.\train_dpdp_gp_multinstance.py' `
  --output '.\gp_runs\multinstance_rerun' --population 6 --generations 2 `
  --seed 20261106 --timeout-seconds 30
```

Nạp cây đã lưu và chạy lại instance 3 mà không huấn luyện:

```powershell
$ds = '.\datasets\xingtian\e4ef3a1c92d19d1d08c3ef0e2156b6fecefdbe04\benchmark'
& '.\.venv\Scripts\python.exe' -B '.\run_dpdp_insertion.py' --policy gp `
  --tree '.\gp_runs\multinstance_50_20261105\main\selected_tree.json' `
  --instance-directory (Join-Path $ds 'instance_3') --data-directory $ds `
  --seed 0 --wall-seconds 30 --output '.\gp_runs\selected_tree_instance3_rerun'
```

Sau khi sửa adapter legacy, **118/118 kiểm tra PASS**: feasibility, execution guards, schedule, scorer, insertion, dữ liệu, GP hiện có và 6 kiểm tra đa instance. Lệnh tái chạy:

```powershell
& '.\.venv\Scripts\python.exe' -B -m unittest -v `
  test_dpdp_feasibility test_dpdp_execution_guards test_dpdp_schedule `
  test_verify_dpdp_score test_dpdp_insertion test_dpdp_dataset `
  test_dpdp_gp test_dpdp_gp_multinstance
```

## Kết luận

1. **Pipeline huấn luyện đa instance đã chạy đúng** theo split train 2–5 và validation 6: hash được xác minh, baseline được chấm lại, mỗi rollout GP dùng simulator mới, fitness lấy từ điểm cuối đã kiểm tra độc lập, và không dùng test cuối.
2. **Chưa có bằng chứng GP cải thiện trên train và validation như một nhóm.** Cây được chọn có J thấp hơn baseline trên instance 6 nhưng fitness train là 35.794 và cây thua baseline ở 3/4 instance train. Cần thêm dữ liệu phát triển trước khi kết luận về cải thiện. Test cuối 7–8 chưa được truy cập.
