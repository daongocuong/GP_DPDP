**Giải quyết hợp đồng VNSME–DPDP: phiên bản thực thi v3**

Đã triển khai hợp đồng opt-in `dpdp-execution-commitment-v3`, dùng chung cho GP và VNSME. Hai saved epochs 9/61 và 13/22 qua kiểm tra và enforcement trong hợp đồng mới, trong khi chế độ cũ vẫn từ chối như trước. Đây là thay đổi semantic có phiên bản, không phải sửa lỗi tương thích ngược. Toàn bộ regression suite **179/179 PASS**, không skip. Chưa chạy full simulation 100 đơn, Java search, reference dài hoặc GP training trong nhiệm vụ này.

Git root là `C:\Users\Cuongdz\Documents\LA`; thư mục làm việc `dvrpsim`; HEAD ban đầu `0bd773291d5d9034f1e7b81688bc2dfaf87308c7`. Không tìm thấy AGENTS.md áp dụng. Preflight đã lưu trạng thái git, hash và bản sao ba file trước sửa; các thay đổi chưa commit có sẵn được giữ nguyên, đặc biệt bản sửa timeout, hai test VNSME của lần trước và các file draft protocol/test của người dùng.

**A. Hợp đồng rút ra từ source và chứng cứ**

1. Đơn được phát hành vào DVRPsim với trạng thái NO_DECISION, nằm trong model.orders/open_orders. Huawei dùng GENERATED=1, ONGOING=2, COMPLETED=3 theo configs.py và cập nhật bởi sự kiện vật lý. Bản readme Huawei có một đoạn tiếng Anh ghi số trạng thái khác; kết luận dùng mã thực thi, không dựa vào đoạn mô tả không nhất quán đó.
2. Việc có mặt trong nghiệm riêng hoặc suffix chưa thực thi là kế hoạch tạm thời. DVRPsim ghi `next_visits` là tentative route. Order.accept chỉ đặt trạng thái nhận phục vụ và acceptance_time; nó không lưu một xe hoặc một tuyến bất biến. Xe pickup được lưu riêng khi pickup thật. Chế độ tích hợp v2 đã thêm giả định mạnh hơn rằng một item accepted phải luôn có trong tuyến công bố.
3. Cam kết thực thi gồm stack hàng đã pickup và ownership; các thao tác của current visit được bridge này giữ nguyên; factory/ETA của destination đã chốt. Không thể chuyển hàng đang vận chuyển sang xe khác. Suffix chưa pickup ngoài current visit không bị khóa ownership bởi validator.
4. Item chưa pickup có thể chuyển xe nếu giữ đủ dịch vụ và không vi phạm current/destination, tải, LIFO, precedence hoặc quy tắc chia đơn. GP vốn chọn giữ các assignment cũ trong bộ chèn; đó là lựa chọn thuật toán, không phải một trạng thái ownership của simulator.
5. Trong hợp đồng Huawei, item chưa pickup có thể tạm vắng khỏi publication mà vẫn ở trạng thái generated/unallocated. Trong v3, điều này chỉ được phép cho công việc chưa committed và phải được giữ trong sổ yêu cầu. ACCEPTED không bị đảo lại. Mọi item vẫn bắt buộc được giao cuối lượt.
6. Các visit đã thực thi không được chạy lại. Current work giữ nguyên; carrying stack phải được giao đủ theo LIFO; destination factory/ETA giữ đến khi đến nơi. Các thao tác tại destination chưa đến chỉ có thể đổi nếu các kiểm tra vật lý và đầy đủ dịch vụ còn hợp lệ.
7. Java không công bố một suffix không có nghĩa hủy đơn. Java lưu private route trước MergeNode và isDelay; các item liên quan vẫn ở đó. Input Huawei kế tiếp gửi mọi open item chưa pickup, kể cả accepted. Periodic updater tiếp tục khi còn open orders, nên item chờ không làm mô phỏng kết thúc hợp lệ.
8. Trước sửa, GP giữ tuyến cũ bởi heuristic và VNSME bị guard accepted-route riêng từ chối. V3 áp cùng guard, sổ yêu cầu và completion gate cho cả hai. Không thêm toán tử, feature, primitive hoặc thông tin tương lai cho GP.

Source đối chiếu: `src/dvrpsim/elements/order.py` (khởi tạo/accept/reject/pickup), `elements/vehicle.py` (tentative next_visits, current service, pickup/delivery), `model.py::_enforce_decision`, `examples/case_studies/dpdp/dpdp_routing.py::get_dpdp_state`, `src/dvrpsim/utils/updaters.py`, `dpdp_feasibility.py::validate`. Huawei: `src/common/order.py`, `src/conf/configs.py`, `src/utils/tools.py`, `src/utils/checker.py`, `src/simulator/simulate_environment.py` dưới third_party/huawei-xingtian/simulator/dpdp_competition. Java: main ở 106–125, lưu/khôi phục private solution, MergeNode và outputJsonWithDelayDispatchTime/emergencyIndex ở khoảng 5941–6260. Phân tích vòng đời có hash và địa chỉ source cụ thể vẫn nằm trong r2/contract_analysis.json và các fixture pins, không bị sửa.

**B. So sánh thiết kế**

| Tiêu chí | A: accepted luôn phải công bố | B: tách tentative/committed | C: lớp trung gian giữ nguyên hợp đồng v2 |
|---|---|---|---|
| Ràng buộc DPDP vật lý | Có thể giữ, cần sửa search/publication | Giữ bằng validator và ledger | Không tự giải quyết mâu thuẫn |
| Ngữ nghĩa Huawei | Mạnh hơn Huawei | Phù hợp generated/unpicked | Nếu không đổi semantic thì vẫn bất tương thích |
| Java nguyên gốc | Phải thêm ràng buộc hoặc công bố thêm | Giữ nguyên search và isDelay | Phải giữ tuyến cũ/promote private suffix để ép qua, bị loại |
| Công bằng GP/VNSME | Chỉ công bằng nếu đổi chung nhưng Java thành variant | Cùng contract và guard; heuristic riêng giữ nguyên | Không công bằng nếu lớp trung gian điều phối thay Java |
| Không mất đơn | Guard accepted, nhưng không tương thích output hiện có | Toàn bộ request giữ đến delivered, pending được gửi lại | Phải có ledger; ledger đơn thuần không sửa được semantic v2 |
| Scorer | Có thể giữ, trajectory sẽ đổi do variant | Công thức và thời điểm tính giữ nguyên | Route fallback có thể làm sai nghĩa baseline |
| Kiểm thử/tái lập | Cần kiểm thử variant Java mới | Replay, kiểm toán trạng thái và synthetic lifecycle được | Chỉ hợp lệ nếu trở thành lớp thực thi B, không tự tạo route |
| Mức thay đổi | Sửa thuật toán/công bố Java | Module contract, runner, adapter branch và version metadata | Dễ tạo trạng thái kép hoặc route lệch private solution |

Chọn **B**, hiện thực bằng ledger có trạng thái nhẹ, tương tự phần theo dõi của C nhưng không quản lý hoặc sửa private routes. Lớp này chỉ kiểm tra/accounting; nó không tạo tuyến, giữ tuyến cũ dự phòng, hoặc tự đưa private suffix vào publication. Phương án A sẽ tạo một biến thể baseline; C độc lập không thể giữ đồng thời hai nghĩa mâu thuẫn của accepted.

**C. Định nghĩa và triển khai**

`protocols/dpdp_execution_commitment_v3.json` và checksum là descriptor mới. Mặc định vẫn là `dpdp-accepted-route-v2`; chỉ bật v3 bằng `--contract-version dpdp-execution-commitment-v3`. Cả GP và VNSME dùng cùng lựa chọn đó. Hai file protocol mới được giữ LF bằng .gitattributes riêng, vì repo đang bật core.autocrlf=true và checksum là hash byte.

Ledger lưu mọi request đã quan sát, không đọc private_data['orders'] hoặc tương lai. Các nhóm trạng thái loại trừ nhau:

| Trạng thái ledger | Nghĩa |
|---|---|
| pending | Chưa pickup, ngoài current work và chưa có dịch vụ trong publication hiện tại; có thể là NO_DECISION hoặc đã ACCEPTED |
| tentative | Có kế hoạch công bố nhưng chưa thuộc công việc vật lý/current work đã khóa |
| committed | Hàng trong carrying stack hoặc thao tác current visit được bridge giữ nguyên |
| delivered | Đã có sự kiện giao vật lý; không được xuất hiện như một lần phục vụ mới |

Toàn bộ request thuộc đúng một nhóm. Danh sách promised_items ghi dấu ACCEPTED để ngăn đảo trạng thái; nó không thay tập yêu cầu phục vụ: ngay request chưa accepted cũng phải được giao trong DPDP này. Factory/ETA destination là khóa riêng trên tuyến, không tự làm mọi item trong suffix thành committed.

Guard v3 kiểm tra request không biến mất hoặc đổi định nghĩa; không cancel/reject/unaccept; thời gian và trạng thái pickup/delivery không lùi; physical ownership/stack không bị mất hoặc đổi. Validator complete-plan nguyên gốc vẫn kiểm mọi item đã công bố và mọi công việc vật lý: thiếu pickup/delivery, trùng phục vụ, capacity, LIFO, precedence, current lock và destination lock đều bị từ chối. Đơn gốc vừa tải không được chia giữa pending/publication rồi phục vụ thành nhiều batch qua các kỳ.

VNSME trả đúng tuyến Java đã công bố. Các item rút khỏi suffix chưa committed trở thành pending, vẫn ACCEPTED và vẫn được gửi lại trong unallocated; không có unaccept hoặc fallback. V3 không lặp lại sự kiện accept cho item đã nhận, nên acceptance_time không bị reset mỗi kỳ như nhánh cũ. Nhánh legacy giữ nguyên hành vi cũ.

Guard chung trong runner ghi ledger sau kiểm tra. Kết thúc hợp lệ đòi hỏi toàn bộ tập item đầu vào đã được quan sát và delivered, sau đó scorer hiện có xác minh log. Certificate complete chỉ nói về hoàn tất dịch vụ; nếu scorer lỗi thì result vẫn valid=false và score=null, đã có test riêng. Mô phỏng không thể dừng sớm với pending rồi sinh J hợp lệ.

Manifest/result ghi contract_version, manifest pin checksum protocol, và v3 lưu commitments.json. Loader reference v2 từ chối cả manifest hoặc result mang v3. Không có migration âm thầm của reference cũ và không bật training v3 bằng trainer v2.

**D. Bằng chứng replay trước/sau**

| Saved case | Kết quả legacy | V3 sau guard và native enforcement | Item chờ vẫn ACCEPTED/gửi lại |
|---|---|---|---|
| 9, kỳ 60 → 61 | Từ chối 0949430034-1 | PASS, 59 request được account đầy đủ; 2 item thành pending | 0949430034-{1,2}, mỗi item xuất hiện đúng một lần trong unallocated kế tiếp |
| 13, kỳ 21 → 22 | Từ chối 0316410009-1 | PASS, 16 request được account đầy đủ; 7 item thành pending | 0316410009-1 và 0325060010-{1..6}, mỗi item một lần |

Trạng thái vật lý qua các kỳ được dựng từ log lịch sử; Huawei projection khớp JSON input thật. Native Model._enforce_decision áp publication v3 thành công mà không đổi status/acceptance_time của item bị rút. Tuyến trả về bằng đúng transform của output Java đã lưu. Không tiến thời gian để chạy lại benchmark 100 đơn, không suy ra trajectory tương lai chưa tồn tại sau kỳ lỗi.

`saved_epoch_replay.json` chứa các ledger và assertions trên. `replay_contract.py` tái lập kiểm toán chỉ bằng artifact. Các kỳ replay chứng minh mâu thuẫn tại boundary đã được giải quyết theo v3; không phải chứng nhận hoàn tất toàn instance 9/13.

Để kiểm tra xuyên nhiều kỳ có thực thi thật, dùng một synthetic fixture hai đơn: công bố b → rút b ở kỳ sau trong khi giữ công việc a đang phục vụ → gửi lại b trong input → công bố b lại → pickup/delivery đúng một lần. Callback accept chỉ xảy ra một lần, acceptance_time giữ nguyên. Ledger hoàn tất, checker chấm lại log khớp result. Cùng fixture cũng chạy GP qua cùng guard/completion gate. Các thư mục tiny_lifecycle_vnsme và tiny_lifecycle_gp lưu bằng chứng; Java session trong fixture là test double, không phải lượt đo chất lượng VNSME. J synthetic tương ứng 4 và 3 chỉ là kết quả kiểm tra scorer, không dùng làm reference hoặc kết luận thuật toán tốt hơn.

**E. Regression, tính nguyên bản và lịch sử**

18 test contract mới bao phủ saved epochs, pending/republication, GP scheduling accepted-pending, request loss/change, service cancellation, trạng thái đảo ngược, mất carrying/ownership, current/factory/ETA lock, tải/LIFO/precedence, không phục vụ trùng, không chia đơn vừa tải, completion gate, scorer lỗi và version boundary. Toàn bộ suite chạy **179/179 PASS**, 0 skip, khoảng 48.895 giây wall.

Các test cũ về guard v2 và lỗi logging timeout tiếp tục PASS. JavaSession AST, Java source/library/classes, GP candidate generator/ranker, scorer và fitness sources giữ nguyên. Bộ test chung có regression cây cố định instance 1 và fixture nhỏ trong thư mục tạm; không có GP training. Các kiểm tra dữ liệu/khóa tập test chỉ đọc metadata/checksum/schema theo protocol, không rollout/chấm/tune kết quả final-test.

Reference 2–6 được loader legacy và scorer chấm lại: J 95.74, 97.44, 100.76, 3303.926666666666666666666667, 105.04; hash summary vẫn cf44e4a41cc7e1f29dbf98cd968a555d6dcefe0aade6a49d4e1575fbbf47f02d. Chúng hợp lệ cho v2 và giữ nguyên artifact, **chưa được chứng nhận cho v3**. Công thức J không đổi, nhưng tập hành vi cho phép khác nên không coi điểm cũ hoặc fitness cũ là baseline được kiểm chứng dưới v3.

GP không cần đổi cây, feature, bộ chèn hoặc công thức fitness. Nó phải dùng cùng runner contract v3 khi so với VNSME v3. Việc GP tự giữ suffix cũ là heuristic riêng, không phải một nghĩa khác của cam kết. Trainer/normalization protocol hiện hành vẫn v2; trước training v3 cần protocol/reference và provenance v3 riêng. Không đưa một summary v3 vào workflow v2.

**F. Readiness và việc chưa làm**

- Có hợp đồng nguồn đủ căn cứ: acceptance là nhận phục vụ; unpicked assignment tạm thời; công việc thực thi và ownership vật lý được khóa.
- Có sửa boundary 9/13 trong replay v3; legacy không bị đổi ngầm và vẫn từ chối đúng theo hợp đồng của nó.
- Không sửa search objective, thuật toán Java, MergeNode, isDelay hoặc emergencyIndex. Không thêm route.
- Có thể chuyển sang một đợt rerun kiểm chứng 9/13 opt-in v3 với output mới; **chưa có full-run PASS hoặc reference v3**. Tác vụ này không chạy đợt đó. Runner đã hỗ trợ version mới, còn quy trình thu nhận/normalization reference phải version hóa thay vì dùng loader v2.
- Instance 10 vẫn còn chi phí tìm kiếm/cooperative stopping và vấn đề giám sát đã báo ở r2. Không tối ưu hoặc điều chỉnh chúng ở đây. Budget 540/600/10800 giây không đổi; trước lượt dài vẫn cần giám sát đúng cây tiến trình và xử lý monitoring gap.
- Chưa sẵn sàng huấn luyện GP chính thức theo v3: thiếu reference/full-run validation v3, protocol training/normalization v3 và xử lý blocker vận hành 10. Không dùng kết quả unit test để tuyên bố các việc này đã xong.

**File thay đổi và cách kiểm tra lại**

Ba file có sẵn được sửa trong tác vụ: run_dpdp_insertion.py (chọn contract và common guard/completion), src/baselines/vnsme.py (branch semantic v3, giữ legacy và timeout fix), dpdp_vnsme_reference.py (ngăn trộn contract trong loader v2). File mới: dpdp_contract.py; test_dpdp_execution_contract.py; protocol v3 + checksum; .gitattributes chỉ áp cho hai file protocol mới. Không sửa Java, simulator core, GP source, scorer, các protocol cũ hoặc artifact lịch sử.

Tài liệu, preflight, replay, test log, preservation, summary và các fixture nhỏ được gom ở `vnsme_evidence/scale100_contract_resolution/`. Không push/merge/commit tự động. Tham số opt-in được kiểm tra qua CLI thật; mặc định không đổi.

```powershell
.\.venv\Scripts\python.exe -B -m unittest test_dpdp_execution_contract -v
.\.venv\Scripts\python.exe -B -m unittest discover -p "test_*.py" -v
.\.venv\Scripts\python.exe -B vnsme_evidence\scale100_contract_resolution\replay_contract.py
```

Script replay dùng lại fixture nhỏ đã lưu khi có; không khởi chạy full benchmark hoặc Java search. Chọn semantic trên runner bằng `--contract-version dpdp-execution-commitment-v3` cho cả `--policy gp` và `--policy vnsme`. Không có lệnh reference dài hoặc training nào được thực thi trong nhiệm vụ này.
