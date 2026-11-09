    # Kiểm chứng bộ chấm DPDP

    Ngày kiểm tra: 05/11/2026 (Asia/Bangkok). Không chạy lại mô phỏng.

    ## Phiên bản và phạm vi

    - Interpreter: `C:\Users\Cuongdz\Documents\LA\dvrpsim\.venv\Scripts\python.exe`, Python 3.14.4, Windows AMD64.
    - Repository local: `https://github.com/sztaki-hu/dvrpsim.git`, nhánh `main`, commit nền `29f4cd8f481fa5ac8cbf97a1372ee5b845e20c4a`.
    - Venv trong repository: dvrpsim 0.0.1 editable từ source local; SimPy 4.1.2. Công cụ kiểm chứng chỉ dùng thư viện chuẩn, không import simulator.
    - Công cụ mới: `verify_dpdp_score.py`, phiên bản 1.0.0; SHA-256 `3eec01e6bdb93c0be2a1a9c881b8bbd60896d66c35ddd8b1df46e0a36348cdc7`.
    - Đã đọc `verify_dpdp_log.py`: giữ nguyên để bảo toàn công cụ cũ; công cụ mới độc lập vì cần tính quãng đường, điểm tổng và kiểm tra thời điểm điều chỉnh bằng sự kiện đến thực tế.
    - Không thấy AGENTS.md áp dụng ở các thư mục cha hoặc trong workspace, ngoài .git và .venv đã loại trừ.
    - Không sửa thuật toán, simulator local, CSV hoặc log cũ; không cài thư viện.

    ## Nguồn tham chiếu được cố định

    Repository Xingtian: `huawei-noah/xingtian`, commit `e4ef3a1c92d19d1d08c3ef0e2156b6fecefdbe04`.
    Đây là commit được tham chiếu trong kiểm chứng, không phải tuyên bố về phiên bản lịch sử lúc tạo log.

    Các đường dẫn dưới đây tương đối với `simulator/dpdp_competition/` tại commit trên:

    | Nguồn | Nội dung đối chiếu |
    |---|---|
    | `src/utils/evaluator.py:31–38` | Điểm tổng, chia quãng đường cho toàn bộ số xe, đổi trễ giây sang giờ |
    | `src/utils/evaluator.py:58–100` | Lấy completion đầu tiên của item; gom theo order_id; lấy item muộn nhất; cộng trễ dương |
    | `src/conf/configs.py` | LAMDA=10000; COMPLETED=3; tốc độ xếp/dỡ 0.25 pallet/phút |
    | `src/simulator/history.py:78–113` | Ghi trạng thái item tại arrive_time, không phải leave_time |
    | `src/utils/input_utils.py:84–94` | Chuyển giờ CSV thành epoch giây; hạn qua ngày cộng 86400 |
    | `src/common/route.py` | Khoảng cách km, di chuyển giây; cùng nhà máy có khoảng cách 0 |
    | `benchmark/readme.md` | Định nghĩa đơn vị và các cột CSV |

    URL evaluator:
    https://github.com/huawei-noah/xingtian/blob/e4ef3a1c92d19d1d08c3ef0e2156b6fecefdbe04/simulator/dpdp_competition/src/utils/evaluator.py

    Snapshot có bản quyền/license gốc nằm trong `scoring_reference/xingtian/`.
    `scoring_reference/provenance.json` lưu URL, commit, Git blob SHA và mã băm CSV.
    Các snapshot chỉ phục vụ kiểm tra; không được import như một simulator thứ hai.

    ## Đơn vị và định nghĩa

    Khoảng cách trong `route_info.csv` là **km**; thời gian di chuyển là **giây**.
    Cả bốn CSV local (route_info, factory_info, instance_1/50_1, instance_1/vehicle_info_5)
    đã được tải đối chiếu từ commit tham chiếu và **trùng SHA-256 từng byte**.
    Route matrix có 23562 dòng; factory có 154 dòng; đơn gốc 50 dòng; xe 5 dòng.

    Mã local `dpdp_problemdata.py` tính giờ yêu cầu/hạn giao thành giây từ 00:00 ngày vận hành.
    Nếu hạn nhỏ hơn giờ yêu cầu, cộng 86400. Cột số trong log là `model.env.now`, không phải thời gian thực thi.
    Không dùng cột HH:MM:SS để tính điểm vì cột đó quay vòng qua ngày.
    FINISH=106200 giây tương ứng 29 giờ 30 phút mô phỏng, dù log hiển thị 05:30:00.

    Simulator gốc dùng epoch giây có ngày; local dùng giây tương đối.
    Trừ cùng một mốc 00:00 khỏi cả arrival và deadline giữ nguyên hiệu thời gian.
    Không suy ra ngày chạy thực hoặc timezone của phiên lịch sử từ các con số tương đối này.

    Với log hợp lệ, hoàn thành item là **thời điểm xe đến nhà máy giao**, trước chờ bến/tiếp cận bến/dỡ hàng.
    Mã local `DPDPVehicle.on_service_finish()` đặt lại delivery_time bằng arrival_time;
    nguồn gốc `History.add_history_of_order_items()` cũng dùng arrive_time.
    Công cụ mới lấy arrival thực từ chuỗi sự kiện, rồi kiểm tra thời điểm điều chỉnh trong log trùng arrival.
    Nó không dùng thời điểm `is delivered` làm completion tính trễ.

    ```text
    C_o = max(arrival_i cho mọi item i thuộc đơn gốc o)
    T_o = max(0, C_o - due_o)                  [giây]
    T = sum(T_o)                             [giây, không nhân theo số item]
    D = sum(khoảng cách các chặng của mọi xe) [km]
    J = D / N + T * 10000 / 3600
    ```

    N là tổng số xe trong CSV, kể cả xe không đi. Cùng nhà máy đóng góp 0 km.
    Mỗi chặng khác nhà máy phải có trong ma trận; thiếu OD bị báo không hợp lệ, không thay bằng 0.
    Chuỗi chặng phải liên tục, mỗi departure phải có arrival đúng điểm và đúng thời gian tra ma trận.

    Evaluator gốc chọn trạng thái COMPLETED sớm nhất nếu một item có nhiều trạng thái hoàn thành.
    Công cụ kiểm chứng chủ động nghiêm ngặt hơn: yêu cầu toàn bộ item từ CSV được yêu cầu/lấy/giao/điều chỉnh đúng một lần;
    item thiếu, không biết hoặc giao trùng đều không hợp lệ và không xuất điểm.
    Điều này không thay đổi điểm trên lịch sử phục vụ hợp lệ.

    ## Các trường hợp tính tay và kiểm tra

    Các ca tính tay dùng D=12 km, N=2, nên phần quãng đường bằng 6; due=100 giây.
    Đáp án được viết thành hằng số trong test, không lấy kết quả hàm tính làm kỳ vọng.

    | Trường hợp | Đáp án tính tay | Kết quả |
    |---|---|---|
    | Item đến 90 hoặc 100 | T=0; J=6 | PASS |
    | Item đến 160 | T=60; J=6+10000/60=172.666666… | PASS |
    | Một đơn có item đến 120 và 160 | T=max(120,160)-100=60; J=172.666666…; không cộng 20+60 | PASS |
    | Thiếu một item | Không hợp lệ | PASS |
    | Giao một item hai lần | Không hợp lệ | PASS |
    | Item ngoài CSV | Không hợp lệ | PASS |
    | Yêu cầu 23:00, hạn 01:00 ngày sau | release=82800; due=90000 | PASS |

    Tổng cộng **15 test PASS** bằng `unittest`: thêm kiểm tra hồi quy log cũ,
    log sao chép tạm bị thiếu/giao trùng, thời điểm điều chỉnh sai, chặng hỏng, thiếu OD,
    và đối chiếu hai trường hợp với các hàm evaluator gốc.
    Test dựng bản sao lỗi trong thư mục tạm; không sửa log thật.
    Các test nguồn gốc thực thi riêng class/function evaluator bằng AST, thay logger/config bằng adapter tối thiểu;
    không chạy simulator hoặc code cấu hình tạo thư mục.

    ## Kết quả đối chiếu log

    Đầu vào: `run_logs/dpdp_success.log`.
    SHA-256 trước/sau: `c55c7462c6f9ca9d3c79930de867b7a98aa7737bc2c36f5bd67bf64c420841c9`.

    | Thành phần | Báo cáo trước | Kiểm chứng độc lập |
    |---|---:|---:|
    | Xe / đơn gốc / item | 5 / 50 / 95 | 5 / 50 / 95 |
    | Tổng quãng đường | 1057 | 1057 km |
    | Quãng đường trung bình | 211.4 | 211.4 km/xe |
    | Tổng trễ | 57558 | 57558 giây |
    | Số đơn trễ | 10/50 | 10/50 |
    | Chặng departure–arrival hoàn chỉnh | Chưa báo cáo | 99 |
    | Phạt trễ trong điểm tổng | Chưa báo cáo | 159883.333333… |
    | Điểm tổng | Chưa báo cáo | **160094.733333…** |

    Tính tay điểm tổng: `1057/5 + 57558*10000/3600 = 2401421/15`.
    Không có sai lệch cần sửa; không thay dữ liệu hoặc công thức để ép khớp.
    Các hàm evaluator gốc trên lịch sử adapter từ log cũng cho D=1057, T=57558, J=160094.733333…
    (float khác biểu diễn với Decimal ở các chữ số rất nhỏ).
    Kết quả từng xe, từng đơn và mã băm nằm trong `scoring_reference/dpdp_success_score.json`.

    ## Giới hạn và quyết định

    **Định nghĩa và đơn vị chấm điểm đã đối chiếu đầy đủ: điểm trên quỹ đạo log này tương thích với evaluator của benchmark tại commit tham chiếu.**
    Điều này không chứng minh simulator local và Xingtian sinh cùng một quỹ đạo, hoặc tái lập điểm của một bài báo.

    Các phần chưa xác minh:

    - Log không có manifest khóa mã nguồn/cấu hình/vị trí xe tại thời điểm chạy; source_commit.txt chỉ là bằng chứng hỗ trợ.
    - Vị trí ban đầu được suy ra từ departure đầu tiên, chưa kiểm tra bằng manifest độc lập.
    - Chưa kiểm chứng toàn bộ tải, LIFO, điều kiện chia đơn, khóa công việc và thứ tự hàng chờ của thuật toán bất kỳ.
    - Chưa kiểm chứng các quy mô/instance khác, hoặc tính tương đương động lực mô phỏng với simulator gốc.
    - Không có ngày chạy thực và thời lượng thực thi trong log.
    - Công cụ đọc định dạng log INFO của demo local; không tuyên bố là bộ đọc mọi định dạng log DPDP.

    **Đủ điều kiện chuyển sang xây baseline chèn đơn ở mức phát triển**, dùng bộ chấm đã xác minh này cho kết quả hoàn thành hợp lệ.
    Baseline vẫn cần bộ kiểm tra khả thi và kiểm chứng lịch dự báo trước khi dùng cho thực nghiệm hoặc huấn luyện GP.

    ## Lệnh tái kiểm tra

    Chạy từ repository bằng đúng venv bên trong. Các lệnh không chạy mô phỏng và không ghi đè kết quả:

    ```powershell
    Set-Location 'C:\Users\Cuongdz\Documents\LA\dvrpsim'
    & '.\.venv\Scripts\python.exe' -B -m unittest -v test_verify_dpdp_score
    & '.\.venv\Scripts\python.exe' -B '.\verify_dpdp_score.py' '.\run_logs\dpdp_success.log'
    ```

    CLI in JSON, exit 0 khi hợp lệ, exit 1 khi không hợp lệ. Các số Decimal xuất dạng chuỗi để giữ độ chính xác.
    Muốn kiểm tra instance khác, truyền rõ `--orders`, `--vehicles`, `--matrix`; mặc định chỉ dành cho instance_1.
