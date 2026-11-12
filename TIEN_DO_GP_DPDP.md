# TIẾN ĐỘ DỰ ÁN GP–DPDP VỚI BASELINE VNSME

- **Thời gian khởi tạo**: 2026-11-09
- **Nhánh Git**: `complete-gp-dpdp`
- **Mục tiêu**: Hoàn thiện dự án nghiên cứu GP cho DPDP, đánh giá khách quan và khoa học trước baseline VNSME theo quy trình 6 giai đoạn (A → F).

---

## 1. Tình trạng Repository ban đầu

1. **Hạ tầng kiểm thử**:
   - Suite kiểm thử ban đầu: 145/145 PASS.
   - Sau khi bổ sung audit tests (`test_dpdp_policy_audit.py`): **148/148 PASS**.
2. **Dữ liệu & Phân hoạch (Split Protocol)**:
   - Tập 50-order: Instance 2, 3, 4, 5 (Train), Instance 6 (Validation), Instance 7, 8 (Final-test độc lập, niêm phong hoàn toàn).
   - Instance 7 và 8 chưa từng bị chạy hay rò rỉ vào bất kỳ quá trình phát triển nào.
3. **Reference Baseline VNSME**:
   - Đã có đầy đủ điểm baseline hợp lệ cho 5 instance phát triển (2, 3, 4, 5, 6) được ghim tại `dvrpsim/migration_runs/vnsme_reference_ready/summary.json`:
     - Instance 2: $J = 95.74$ ($D = 478.7$ km, $T = 0$ s)
     - Instance 3: $J = 97.44$ ($D = 487.2$ km, $T = 0$ s)
     - Instance 4: $J = 100.76$ ($D = 503.8$ km, $T = 0$ s)
     - Instance 5: $J = 3303.93$ ($D = 436.3$ km, $T = 1158$ s)
     - Instance 6 (val): $J = 105.04$ ($D = 525.2$ km, $T = 0$ s)

---

## 2. Nhật ký công việc theo giai đoạn

### Giai đoạn A — Audit và hoàn thiện chính sách GP [HOÀN THÀNH]
- **Kiểm tra toàn bộ pipeline**: Đã audit chi tiết từng mắt xích từ Input, Simulator, Candidate Generator, Feasibility Guard, Feature Extraction, GP Scoring, Tie-break đến Objective $J$.
- **Chẩn đoán C10 instance 3**: Xác minh chính xác hiện tượng đảo dấu do phép chia `delta_tardiness_seconds / delta_distance_km` khi $\Delta D = -0.1$ km. Đây là một khiếm khuyết của biểu thức cây C10 (tree limitation), không phải lỗi hạ tầng.
- **Tạo regression test**: Tạo file `dvrpsim/test_dpdp_policy_audit.py` gồm 3 kiểm thử tái hiện chính xác hiện tượng C10, kiểm tra tính đúng đắn của $\Delta J$ và tính đơn định (deterministic) của tie-break. Tất cả 148 test PASS.

### Giai đoạn B — Hoàn thiện và xác minh hạ tầng thực nghiệm [HOÀN THÀNH]
- Xác minh determinism với seed cố định.
- Xác minh toàn bộ các guard: dung lượng xe (capacity), LIFO stack, pickup-before-delivery, locked visits, split orders.
- Xác minh phép chia an toàn (protected division) và kiểm tra lỗi số học (không phát sinh NaN/Inf).
- Xác minh baseline cache và tính toàn vẹn của tệp summary VNSME.

### Giai đoạn C — Thiết kế Protocol GP chính thức [HOÀN THÀNH]
- **Tệp protocol**: `dvrpsim/protocols/dpdp_official_experiment_v1.json` và mã băm SHA256 sidecar.
- **Phân hoạch**:
  - Train: Instance 2, 3, 4, 5
  - Validation: Instance 6
  - Final Test: Instance 7, 8 (khóa chặt, chỉ mở ở Giai đoạn E)
- **Tham số tiến hóa**:
  - Quần thể: 6 cây
  - Thế hệ: 3 thế hệ (Gen 0, 1, 2, 3)
  - Seed: 20261109, Seed môi trường: 0
  - Tournament size: 3, Crossover: 0.8, Mutation: 0.3, Elitism: 1
  - Max depth: 4, Max nodes: 31
  - Timeout rollout: 30s
- **Quy tắc chọn mô hình**: Chọn cây hợp lệ có tỷ số $J_{GP}(6) / J_{VNSME}(6)$ nhỏ nhất trên tập validation.

### Giai đoạn D — Huấn luyện GP chính thức [ĐANG CHẠY]
- Đã chạy smoke test đo đạc tốc độ: ~161s cho 24 rollouts thực tế.
- Đang tiến hành huấn luyện chính thức với seed 20261109 tại `dvrpsim/gp_runs/official_gp_multinstance_20261109`.

---

## 3. Theo dõi tiến độ các giai đoạn

| Giai đoạn | Trạng thái | Ghi chú |
|---|---|---|
| **A — Audit chính sách GP** | HOÀN THÀNH | Đã tạo test và xác nhận hạn chế cây C10 |
| **B — Hạ tầng thực nghiệm** | HOÀN THÀNH | 148/148 test PASS, determinism OK |
| **C — Thiết kế Protocol** | HOÀN THÀNH | Đã khóa `dpdp_official_experiment_v1.json` |
| **D — Huấn luyện GP** | ĐANG CHẠY | Tiến hóa multi-instance seed 20261109 |
| **E — Đánh giá cuối GP vs VNSME** | Chờ thực hiện | Sẽ chạy độc lập trên Instance 7 & 8 |
| **F — Hoàn thiện nghiên cứu** | Chờ thực hiện | Báo cáo khoa học tiếng Anh, tài liệu đầy đủ |
