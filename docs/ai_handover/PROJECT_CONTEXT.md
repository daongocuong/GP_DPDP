# Bối cảnh nghiên cứu GP–DPDP

Ngày audit: 2026-11-10, Asia/Bangkok. Repository: `C:/Users/Cuongdz/Documents/LA`; mã thực thi chủ yếu nằm trong `dvrpsim/`. Tài liệu này phản ánh working tree, không chỉ HEAD.

## Cách đọc evidence

- **VERIFIED**: trực tiếp đọc code hoặc kiểm tra lại artifact trong audit này.
- **REPORTED**: có trong báo cáo/log/artifact, chưa tái chứng nhận trong audit này.
- **INFERRED**: suy luận được giải thích, chưa phải kết quả kiểm nghiệm.
- **UNKNOWN**: thiếu bằng chứng. `NOT FOUND` chỉ nói về phạm vi filesystem đã kiểm tra.

Audit chỉ đọc code, metadata và evidence phát triển; không đọc `.env`/credentials, không mở CSV sealed 7–8/15–16, không training, benchmark hoặc mô phỏng mới. Ngoại lệ ghi duy nhất là sáu Markdown trong `docs/ai_handover/`. Có chạy lại các hàm audit/replay/scorer thuần đọc trên bảy rollout đã lưu; mỗi lượt kiểm tra khoảng 1.8–3.3 giây. Không chạy lại test suite hoặc Java search.

## Bài toán và mục tiêu

**VERIFIED — thiết kế hiện hành:** học bằng Genetic Programming một hàm xếp hạng các cách chèn pickup/delivery khả thi để điều phối xe khi đơn hàng xuất hiện theo thời gian. Đánh giá chính sách GP bằng full rollout trên simulator `dvrpsim`, so với VNSME Java trên cùng dữ liệu, mô phỏng và scorer. Nguồn: `dvrpsim/dpdp_insertion.py:InsertionPolicy`, `dpdp_gp.py:TreeRanker`, `train_dpdp_gp_multinstance.py:run_experiment`, `src/baselines/vnsme.py:VNSMEPolicy`.

Mạng nhà máy có khoảng cách và thời gian di chuyển cho từng cặp; mỗi nhà máy có số docking ports hữu hạn. Đơn gốc được tách thành các item nguyên khối có lượng 1, 0.5 hoặc 0.25 pallet tiêu chuẩn. Xe có capacity và stack LIFO. Đơn chỉ được chính sách thấy sau release; deadline là soft constraint. Đơn vừa capacity phải giữ một batch; đơn lớn hơn capacity có thể chia theo nhóm item. Không được bỏ yêu cầu bắt buộc để làm đẹp điểm. Nguồn: `dpdp_problemdata.py:read_dpdp_problem`, `dpdp_insertion.py:split_observed_orders`, `dpdp_feasibility.py:validate`, `dpdp_contract.py:ExecutionCommitment` (các đường dẫn ngắn trong tài liệu này đều tương đối với `dvrpsim/`, trừ khi ghi khác).

Simulator dùng SimPy; quyết định định kỳ 600 giây, không trigger routing ngay khi request đến; docking 1800 giây mỗi visit, load/unload 240 giây trên một đơn vị lượng. Port bị giữ suốt dock/unload/load; FCFS. Các visit GP không merge nên quay lại cùng factory vẫn có phí phục vụ theo visit. Thời gian tính thuật toán không cộng vào thời gian mô phỏng. Nguồn: `examples/case_studies/dpdp/dpdp_main.py:build_dpdp_model`, `DPDPVehicle._service`, `run_dpdp_insertion.py:manifest`, `dpdp_schedule.py:predict_fixed_routes`.

## Hàm mục tiêu chính xác

**VERIFIED:** với K xe, item i thuộc đơn gốc o, thời điểm hoàn thành item c_i là **đến factory giao hàng**, trước queue/docking/unload:

`C_o = max(c_i: i thuộc o)`

`T = sum_o max(0, C_o - due_o)` tính bằng giây.

`J = (sum_v D_v / K) + (10000 / 3600) * T` với D bằng km.

Tardiness tính một lần mỗi đơn gốc, theo item giao muộn nhất; không lấy tổng tardiness từng item. Scorer dùng `Decimal`; không làm tròn J trước chuẩn hóa. Nguồn: `verify_dpdp_score.py:aggregate_score`, `verify`; simulator điều chỉnh `delivery_time` về arrival trong `DPDPVehicle.on_service_finish`.

Điểm cây GP chỉ là thứ tự ưu tiên candidate, **không phải J**, fitness hay một dự báo bảo đảm về cải thiện cuối rollout. Một cây tốt phải có mọi rollout train hợp lệ và điểm validation tốt theo protocol đóng băng.

## Thuật ngữ GP

| Thuật ngữ | Nghĩa thực tế trong code |
|---|---|
| Individual/tree | AST bất biến `Node` với terminal feature/constant, primitive `+ - * /`; tối đa depth 4 (root 0), 31 nodes |
| Candidate insertion | Chèn hai visit pickup rồi delivery vào suffix của một xe, giữ route cũ; kiểm tra cả fleet trước forecast/rank |
| Dispatch | Một lần gọi chính sách khi simulator đến decision point |
| Rollout | Chạy toàn bộ scenario cho một tree/instance đến giao đủ item, có guard và scorer cuối |
| Generation | Đánh giá population trên train; breed bằng tournament/crossover/mutation/elitism; không phải một dispatch |
| Validation | Instance 6 để chọn cây sau tiến hóa; không tham gia fitness dùng breed |
| Reference | Rollout VNSME có provenance, completion, scorer/replay, supervision và hashes, dùng làm mẫu số |
| Sealed test | 7–8 và 15–16; không được mở/đọc/chạy/debug trong phát triển |

Nguồn: `dpdp_gp.py`, `dpdp_insertion.py`, `dpdp_gp_fitness.py:RolloutEvaluator`, `train_dpdp_gp_multinstance.py`, `protocols/dpdp_gp_split_v1.json`.

## Quyết định nghiên cứu cần giữ

1. **VERIFIED:** baseline chính là VNSME; Greedy cũ chỉ là lịch sử. Runner hiện chỉ nhận `demo`, `gp`, `vnsme`. Không tự phục hồi Greedy/fallback hoặc thay denominator (`run_dpdp_insertion.py:main`, `dpdp_vnsme_reference.py:load_reference`).
2. **VERIFIED:** contract v3 là thay đổi ngữ nghĩa có chủ đích, không phải sửa lỗi tương thích ngược. Yêu cầu đã release là nghĩa vụ đến khi giao; assignment chưa pickup chỉ tentative, có thể bỏ khỏi publication/reassign, vẫn phải xuất hiện trong ledger/unallocated lần sau. Work đang thực hiện, hàng đã pickup, destination factory/ETA bị khóa. V2 mặc định vẫn tồn tại (`dpdp_contract.py`, `protocols/dpdp_execution_commitment_v3.json`).
3. **VERIFIED:** GP và VNSME dùng cùng simulator, checker, v3 guard, completion gate và scorer nhưng **không cùng không gian tìm kiếm**. GP giữ các insertion đã có; VNSME có redispatch/neighborhood search, merge node, delay publication và persistent private solution. Contract chung không có nghĩa hai thuật toán có cùng quyền sửa route thực tế (`InsertionPolicy.decide`, `VNSMEPolicy.decide`, `third_party/vnsme/original/main_algorithm.java:main`).
4. **VERIFIED:** split 50-order train 2–5, validation 6, sealed test 7–8; 100-order train 9–12/validation 13–14/test 15–16 còn proposed. 1 và 17 đã exposed, không được gọi là untouched test (`protocols/dpdp_gp_split_v1.json`).
5. **VERIFIED:** draft GP v3 `enabled=false`; trainer hiện vẫn là v2. Không dùng v2 trainer với denominator v3 (`dpdp_gp_fitness_v3.py`, `train_dpdp_gp_multinstance.py`, `protocols/dpdp_gp_vnsme_v3_draft.json`).

## Giới hạn của kết luận

- **VERIFIED:** các reference v3 2–6 đều đã qua audit đọc lại; chưa thấy combined summary v3 2–6. Instance 5 có hai kết quả hợp lệ khác nhau; cần quy tắc chọn run trước khi khóa reference (`CURRENT_STATUS.md`).
- **REPORTED:** VNSME được nhận diện là Gold/ICAPS 2021 theo gói người dùng cung cấp; thiếu upstream release checksum/license/launcher. Bản Java nhập vào có byte provenance và build manifest, chưa chứng minh danh tính upstream bằng nguồn độc lập (`third_party/vnsme/README.md`, `provenance.json`).
- **REPORTED:** đã có lần đọc CSV sealed qua test discovery/`verify_existing` trước khi thêm guard; không có rollout/scoring/selection sealed được báo cáo. Không thể tiếp tục tuyên bố chúng chưa từng được đọc (`vnsme_evidence/v3_reference_supervision_20261109_r1/REPORT.md: Sự cố phạm vi test`).
- **UNKNOWN:** chưa chứng minh toàn bộ dynamics tương đương simulator Huawei gốc. Scorer chứng nhận trajectory local; replay không độc lập forecast lại at-location ETA. Java có dừng tìm kiếm theo wall clock, host-midnight timestamps; không khẳng định baseline deterministic chỉ vì environment seed=0.
- Không có bằng chứng GP vượt VNSME v3 hoặc kết quả final-test hợp lệ. Một số kết quả v2 có validation ratio >1, phải giữ đúng nhãn lịch sử.
