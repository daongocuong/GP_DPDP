# Kế hoạch nghiên cứu GP cho bài toán DPDP

**Ngày lập:** 04/11/2026.  
**Trạng thái:** Đề xuất nghiên cứu và kế hoạch triển khai; chưa có kết quả thực nghiệm.  
**GP:** Genetic Programming, lập trình di truyền.  
**DPDP:** Dynamic Pickup and Delivery Problem, trong tài liệu này chỉ biến thể ICAPS 2021 vận chuyển giữa các nhà máy, có LIFO và cửa bốc dỡ hữu hạn.

## 1. Đánh giá thẳng trước khi chọn hướng

GP có vai trò hợp lý nếu được dùng để **học quy tắc lựa chọn phương án chèn đơn**, kết hợp với bộ xây tuyến và kiểm tra ràng buộc cố định. Các bài [R3] và [R4] cung cấp tiền lệ học heuristic bằng GP trên những bài toán định tuyến động liên quan. Chúng không chứng minh GP hiệu quả trên đúng ICAPS-DPDP.

Hướng này sẽ thiếu thuyết phục nếu chỉ đổi một công thức chấm điểm thủ công thành cây biểu thức rồi gọi đó là đóng góp mới. Sự cần thiết của GP phải được kiểm tra bằng đối chứng với hàm tuyến tính đã được chỉnh tốt, chi phí huấn luyện và khả năng dùng trên những trường hợp chưa gặp.

Ba điểm cần giữ tỉnh táo:

1. **Có thể dùng GP không có nghĩa là cần GP.** Nếu một vài trọng số đã cho kết quả tương đương, mô hình đơn giản là lựa chọn có lý.
2. **Tính động chưa đủ để biện minh bằng tốc độ.** Mô hình DPDP này có kỳ điều phối 10 phút [R5]. Đây không phải yêu cầu mặc định phải ra quyết định trong vài mili giây.
3. **Cây GP nhỏ chưa bảo đảm toàn bộ thuật toán nhanh hay dễ hiểu.** Sinh phương án hợp lệ và dự báo lịch cửa bốc dỡ có thể chiếm phần lớn thời gian; cây lớn có thể rất khó giải thích.

Vì vậy, coi đây là một giả thuyết cần sàng lọc bằng thử nghiệm nhỏ. Không cam kết trước GP sẽ thắng CFA-VNS hoặc cho một tỷ lệ cải thiện cụ thể.

## 2. Tên đề tài, mục tiêu và phạm vi

### 2.1. Tên đề xuất

**Học quy tắc chèn đơn bằng lập trình di truyền cho bài toán lấy–giao hàng động có ràng buộc LIFO và cửa bốc dỡ hữu hạn.**

Tên tiếng Anh:

**Learning Insertion Rules with Genetic Programming for Dynamic Pickup and Delivery with LIFO and Limited Docking Capacity.**

### 2.2. Câu hỏi nghiên cứu

> Trên cùng một bộ sinh phương án chèn hợp lệ, quy tắc do GP học có cải thiện chi phí vận hành trên dữ liệu chưa gặp so với hàm tuyến tính đã được chỉnh tốt, với chi phí ra quyết định chấp nhận được hay không?

Các câu hỏi phụ:

- Thông tin chờ cửa bốc dỡ cung cấp thêm giá trị cho quy tắc GP đến mức nào?
- Quy tắc có ổn định qua nhiều lần huấn luyện và các mức tải khác nhau không?
- Chất lượng và thời gian của toàn bộ phương pháp nằm ở đâu so với CFA-VNS khi có bản tái hiện đủ tin cậy?
- Cần sử dụng quy tắc bao nhiêu lần để chi phí huấn luyện trở nên hợp lý so với phương pháp đối chứng?

### 2.3. Phạm vi bắt buộc

- Giữ đúng mô hình đơn hàng động, tải trọng, LIFO, cửa bốc dỡ hữu hạn và quyết định đã chốt.
- Xây dựng một bộ chèn đơn dùng chung cho heuristic thủ công, hàm tuyến tính và GP.
- Huấn luyện ngoại tuyến; khi kiểm tra chỉ sử dụng quy tắc đã chọn.
- So sánh trên dữ liệu chưa dùng huấn luyện hoặc chọn cấu hình.
- Báo cáo cả chi phí vận hành, tính hợp lệ và thời gian tính toán.

### 2.4. Phần mở rộng có điều kiện

- Tái hiện CFA-VNS đầy đủ để làm đối chứng mạnh.
- Thử GP kết hợp cùng một bước tìm kiếm cục bộ ở cả hai phía.
- Kiểm tra khả năng chuyển sang nhóm quy mô khác.

Không đưa các phần này vào mốc tối thiểu nếu việc kiểm chứng môi trường hoặc chi phí mô phỏng chưa hoàn thành. Không đồng thời mở rộng sang dự báo đơn bằng học sâu, điều khiển nhiều tác nhân hoặc thiết kế một simulator mới.

## 3. Tài liệu và mức độ đã xác minh

| Mã | Tài liệu | Vai trò và giới hạn |
| --- | --- | --- |
| R1 | Hao et al. (2022), *Introduction to The Dynamic Pickup and Delivery Problem Benchmark — ICAPS 2021 Competition*. [Toàn văn](https://arxiv.org/pdf/2202.01256) | Căn cứ benchmark và giao tiếp simulator. |
| R2 | Horváth, Kis & Györgyi, *A cost function approximation method for dynamic vehicle routing with docking and LIFO constraints*. [Bản tiền công bố 2024](https://arxiv.org/pdf/2405.01915), [HTML](https://arxiv.org/html/2405.01915v1), [bài xuất bản 2025](https://doi.org/10.1016/j.multra.2025.100194) | CFA-VNS đúng biến thể bài toán. Chưa xác nhận mã tác giả sẵn tải và chạy; bản tiền công bố không mặc nhiên giống hoàn toàn bản xuất bản. |
| R3 | Jacobsen-Grocott et al. (2017), *Evolving Heuristics for Dynamic Vehicle Routing with Time Windows Using Genetic Programming*. [Toàn văn](https://homepages.ecs.vuw.ac.nz/~yimei/papers/CEC17-Josiah.pdf) | Cơ sở học heuristic bằng GP; bài toán và cơ chế phục vụ khác DPDP đang xét. |
| R4 | Jakobović et al. (2023), *Evolving Dispatching Rules for Dynamic Vehicle Routing with Genetic Programming*. [Toàn văn](https://www.zemris.fer.hr/~idurasevic/articles/J26.pdf) | Cơ sở học quy tắc điều phối; không phải một bản GP đã xác minh cho ICAPS-DPDP. |
| R5 | [DPDP: mô tả](https://sztaki-hu.github.io/dvrpsim/src/case_studies/dpdp/1_prob.html), [dữ liệu](https://sztaki-hu.github.io/dvrpsim/src/case_studies/dpdp/2_data.html), [mô hình](https://sztaki-hu.github.io/dvrpsim/src/case_studies/dpdp/3_model.html) | Tài liệu chính thức `dvrpsim`; demo là minh họa mô hình, không tái hiện một thuật toán mạnh. |
| R6 | Horváth & Tamási (2025), *A general modeling and simulation framework for dynamic vehicle routing*, mục 5.2.1 | Bài PDF được cung cấp trong dự án. Mô tả khả năng mô hình hóa DPDP bằng framework. |

Nguồn mã cần kiểm tra ở bước thiết lập:

- [Case study DPDP của dvrpsim](https://github.com/sztaki-hu/dvrpsim/tree/main/examples/case_studies/dpdp).
- [Benchmark và simulator gốc](https://github.com/huawei-noah/xingtian/tree/master/simulator/dpdp_competition).

**Trạng thái hiện tại:** Đã đọc tài liệu mô hình và các nguồn phương pháp nêu trên; chưa cài đặt, chạy benchmark, đo thời gian hoặc tái lập bảng kết quả. Những tham số huấn luyện, lịch làm việc và ngưỡng nghiệm thu bên dưới là đề xuất triển khai, không phải kết quả của tác giả.

## 4. Khóa đặc tả trước khi viết thuật toán

### 4.1. Thông tin và quyết định

Ở thời điểm điều phối, thuật toán chỉ nhận trạng thái hiện tại, các đơn đã công bố và dữ liệu tĩnh hợp lệ. Quyết định bao gồm phân công đơn và cập nhật phần tuyến được phép thay đổi.

Đơn tương lai có thể được simulator lưu trong một tệp để phát sự kiện, nhưng bộ thuật toán không được truy cập phần chưa công bố. Việc chia train/test phải áp dụng cho toàn bộ phiên vận hành, không chia ngẫu nhiên các quyết định của cùng một phiên.

### 4.2. Các ràng buộc cần giữ

| Thành phần | Quy tắc triển khai |
| --- | --- |
| Tải trọng | Kiểm tra tải sau từng thao tác lấy/dỡ, không chỉ tổng lượng hàng của tuyến. |
| Trước–sau | Lấy trước khi giao; hàng đã ở trên xe phải tiếp tục được theo dõi. |
| LIFO | Theo dõi ngăn xếp hàng và thứ tự xử lý tại từng điểm. |
| Chia đơn | Chỉ chia khi quy tắc benchmark cho phép; lưu quan hệ với đơn gốc. |
| Cửa bốc dỡ | Mô hình tài nguyên hữu hạn và thứ tự chờ theo đặc tả. |
| Cam kết | Không thay đổi điểm đến/công việc thuộc phần đã khóa. |
| Hoàn thành | Không biến bài toán thành lựa chọn chỉ phục vụ các đơn dễ. |
| Giao trễ | Phân biệt hạn mềm và ràng buộc cứng; giao trễ không tự động đồng nghĩa tuyến bất khả thi. |

Đây là danh sách kiểm tra triển khai. Chi tiết chính thức phải được dẫn về phiên bản benchmark đã chọn.

### 4.3. Mục tiêu chấm điểm

Dùng một bộ tính điểm cuối cùng chung, ký hiệu `J_benchmark`. Trọng số, đơn vị thời gian, cách gom độ trễ của đơn bị chia và định nghĩa thời điểm giao phải được ghi rõ trong cấu hình.

Không cộng riêng phạt chờ hoặc phạt xe nhàn rỗi vào kết quả của một phương pháp. Đó có thể là công cụ lựa chọn hành động bên trong, còn điểm cuối cùng phải thống nhất.

### 4.4. Sai khác cấu hình phải giải quyết

Tài liệu R2 ghi 60 giây bốc hoặc dỡ cho một pallet chuẩn; trang dữ liệu R5 thể hiện 240 giây trên một đơn vị lượng hàng. **Chưa đủ căn cứ quy hai con số này về cùng một cấu hình.**

Cách xử lý:

1. Đọc mã nạp dữ liệu, cấu hình simulator và quy đổi lượng hàng.
2. Tạo một tình huống một xe, một đơn có lượng hàng xác định; đối chiếu thời gian phục vụ.
3. Ghi cấu hình thực chạy cùng phiên bản mã, nguồn dữ liệu và đơn vị.
4. Nếu chưa hòa giải được, chỉ so các thuật toán chạy cùng cấu hình nội bộ; chưa tuyên bố tái lập điểm công bố.
5. Nếu giữ nhiều cấu hình để phân tích độ nhạy, báo cáo riêng; không chọn cấu hình sau khi xem kết quả test.

Những điểm khác cần kiểm tra: vị trí khởi tạo xe, xử lý sự kiện đồng thời, tài nguyên cửa bốc dỡ trong thời gian tiếp cận, thời điểm giao, khoảng điều phối và điều kiện kết thúc.

## 5. Kiến trúc triển khai và vai trò dvrpsim

| Thành phần | Trách nhiệm |
| --- | --- |
| Bộ dữ liệu và cấu hình | Quản lý dữ liệu, phiên bản, đơn vị, vị trí xe ban đầu và các seed. |
| `dvrpsim` | Chạy vận hành thực tế của một lượt thử: phát đơn, di chuyển, bốc dỡ, hàng chờ, cập nhật trạng thái. |
| Bộ kiểm tra khả thi | Kiểm tra tải, LIFO, chia đơn, công việc đã khóa, số lần phục vụ. |
| Bộ sinh phương án | Đưa ra các cách chèn hợp lệ vào phần tuyến được phép sửa. |
| Bộ dự báo lịch | Ước lượng thời gian đến, chờ, phục vụ và tác động lên các tuyến từ thông tin hiện có. |
| Bộ chấm phương án | Công thức thủ công, hàm tuyến tính hoặc cây GP. |
| Vòng huấn luyện | Sinh và đánh giá quần thể GP qua nhiều lượt mô phỏng. |
| Bộ thực nghiệm | Chạy đối chứng, quản lý seed, thu thập kết quả và thống kê. |

Phân biệt hai loại tính toán:

- **Mô phỏng vận hành:** diễn biến xảy ra khi thực thi các quyết định đã chọn.
- **Dự báo phương án:** lịch giả định để so sánh các tuyến đang cân nhắc, không được đọc các đơn tương lai.

Không gọi cả một lượt mô phỏng hoàn chỉnh cho mỗi phương án nếu chưa đo được khả năng chịu tải. Có thể bắt đầu với bộ dự báo sự kiện chính xác trên thông tin hiện biết, sau đó tối ưu dần và kiểm tra sai số.

Trong huấn luyện, tiến hóa thực hiện bên ngoài; `dvrpsim` cung cấp các lượt đánh giá, không tự học GP.

## 6. Thiết kế bộ chèn dùng chung

### 6.1. Đơn vị xử lý

Giữ đơn hàng và các nhóm hàng theo quy tắc chia đơn đã khóa. Không tự biến mỗi item thành một đơn có thể phân cho xe độc lập nếu đơn gốc không được phép chia.

Giai đoạn đầu dùng một thứ tự xử lý đơn cố định, chẳng hạn theo hạn giao rồi theo mã đơn khi đồng hạng. Nếu sau này học cả thứ tự xử lý, phải coi đó là một thay đổi phương pháp riêng.

### 6.2. Trình tự ở mỗi kỳ

1. Nhận trạng thái hiện tại; khôi phục tuyến đang thực hiện và đánh dấu phần đã khóa.
2. Xác định các đơn mới hoặc chưa được phân công.
3. Với từng đơn/nhóm hàng, sinh các cặp vị trí lấy–giao trên các xe có thể xét.
4. Kiểm tra các ràng buộc cố định; loại phương án sai.
5. Tính đặc trưng và chấm điểm những phương án còn lại.
6. Chọn phương án theo quy tắc đã định; cập nhật tuyến và lịch dự báo.
7. Kiểm tra toàn bộ quyết định trước khi gửi simulator.

### 6.3. Những chi tiết dễ làm sai

- Cửa bốc dỡ là tài nguyên dùng chung. Chèn vào tuyến xe A có thể làm xe B phải chờ; chỉ tính thay đổi trên xe A có thể đánh giá thiếu chi phí.
- Điểm lấy và điểm giao liền nhau là một tập hành động hẹp. Nếu dùng tập này để đơn giản hóa, phải ghi rõ và áp dụng cho mọi đối chứng trực tiếp.
- Nếu cắt bớt số xe/vị trí được xét, cùng một quy tắc cắt phải áp dụng cho hàm tuyến tính và GP.
- Xử lý đồng điểm bằng một thứ tự cố định để tránh vô tình thay đổi giữa các phương pháp.
- Không có phương án sau bước lọc không đồng nghĩa không thể phục vụ. Cần kiểm tra giới hạn sinh phương án và chính sách xử lý tồn đọng.

### 6.4. Phương án dự phòng

Giữ một thủ tục chèn khả thi đơn giản được kiểm tra riêng, có thể nối công việc sau phần tuyến đã có khi hợp lệ. Thủ tục này không được bỏ hàng đang chở, phá cam kết hoặc vượt tải để ép có nghiệm.

Nếu vẫn không thể tạo quyết định hợp lệ, ghi lại trạng thái và dừng lượt thử với trạng thái thất bại rõ ràng. Không lặng lẽ bỏ đơn hoặc cho điểm như đã hoàn thành. Theo dõi tỷ lệ sử dụng phương án dự phòng cho từng phương pháp.

## 7. GP học gì và không học gì

### 7.1. Đầu ra của cây

Với trạng thái `s` và phương án chèn `a` hợp lệ:

`score(a) = g_GP(features(s, a))`

Chọn phương án có điểm thấp nhất. Cây GP học ánh xạ từ các đặc trưng sang điểm; bộ sinh phương án và bộ kiểm tra chịu trách nhiệm xây và giữ tính hợp lệ của tuyến.

Đây là phương pháp học heuristic trong một bộ giải hoàn chỉnh. Không trình bày như GP tự sinh trực tiếp toàn bộ tuyến xe chỉ từ dữ liệu thô.

### 7.2. Tập đặc trưng ban đầu đề xuất

| Biến | Ý nghĩa | Lưu ý tính toán |
| --- | --- | --- |
| `delta_distance` | Quãng đường tăng thêm | Đơn vị thống nhất. |
| `delta_tardiness` | Độ trễ dự báo tăng thêm | Ghi rõ xét một tuyến hay toàn hệ thống. |
| `slack` | Thời gian dư trước hạn theo lịch dự báo | Có thể âm. |
| `pickup_eta` | Thời gian tới điểm lấy | Chỉ dùng trạng thái hiện biết. |
| `delta_wait` | Thay đổi thời gian chờ cửa bốc dỡ dự báo | Không lấy từ log tương lai của simulator. |
| `capacity_margin` | Mức dự phòng tải nhỏ nhất trên tuyến mới | Không dùng tải hiện tại để thay toàn bộ kiểm tra tải. |
| `committed_time` | Khoảng thời gian xe còn bị khóa bởi công việc hiện tại | Định nghĩa thống nhất giữa mọi phương pháp. |

Không mặc định dùng càng nhiều biến càng tốt. Đo chi phí từng biến và bắt đầu với tập nhỏ.

Đặc trưng chuẩn hóa bằng quy tắc cố định hoặc thông số lấy từ train. Không tính thống kê trên toàn bộ train+test. Với trường hợp nằm ngoài khoảng train, quy tắc chặn giá trị phải được công bố.

### 7.3. Biểu diễn GP

Cấu hình khởi đầu do đề tài đề xuất:

- Cây biểu thức có toán tử cộng, trừ, nhân, chia an toàn, `min`, `max`.
- Hằng số giới hạn trong một khoảng hữu hạn.
- Giới hạn độ sâu và số nút; kiểm soát giá trị vô hạn, `NaN` và tràn số.
- Quy định chia an toàn và ngưỡng số học trong cấu hình, dùng giống nhau ở huấn luyện và kiểm tra.
- Phạt độ phức tạp nhỏ hoặc dùng độ phức tạp để chọn giữa các cây có chất lượng gần nhau.

Một cây đã chọn được giữ nguyên khi chạy test. Không chạy tiến hóa lại ở mỗi kỳ điều phối trong phạm vi phương pháp chính.

### 7.4. Fitness

Fitness phải dựa trên chất lượng của toàn bộ phiên vận hành, không chỉ điểm chèn tức thời. Có thể chuẩn hóa điểm mỗi instance bằng một baseline cố định rồi lấy trung bình, nhằm tránh một instance lớn chi phối hoàn toàn quá trình học.

Ví dụ thiết kế:

`fitness(g) = mean_i[J_i(g) / max(J_i(reference), epsilon)] + complexity_penalty(g)`

Đây là hàm huấn luyện đề xuất, không thay thế `J_benchmark` trong báo cáo cuối cùng. Công bố baseline chuẩn hóa, `epsilon`, cách xử lý lượt thất bại và hệ số phạt cây. Nghiệm vi phạm không được hưởng lợi bằng cách kết thúc sớm.

Việc huấn luyện theo lượt hoàn chỉnh cho phép chọn các quy tắc có ích về dài hạn, nhưng không có nghĩa cây GP dự đoán chính xác đơn tương lai. Khả năng này chỉ có thể được đánh giá trên dữ liệu tách biệt.

### 7.5. Ngân sách tính toán

Chạy pilot trước với khoảng 20 cá thể, 5 thế hệ và 2–4 instance nhỏ; đây là thử khả thi, chưa đủ làm kết quả cuối.

Nếu có `P` cá thể, `G` thế hệ sau quần thể đầu, `M` instance mỗi lần đánh giá và `R` lần huấn luyện độc lập, số lượt mô phỏng xấp xỉ:

`N_sim = R × P × (G + 1) × M`

Đây là cận dự toán khi đánh giá lại mọi cá thể, chưa tính validation và test; lưu đệm cá thể trùng có thể giảm tải. Dùng thời gian đo từ pilot để chọn quy mô tiếp theo. Không hứa trước máy cá nhân chạy xong trong vài giờ.

Mục tiêu thực tế là thử 3 seed ở pilot; mở rộng lên khoảng 10 seed nếu ngân sách cho phép. Báo cáo số seed thực chạy và độ bất định tương ứng. Không chọn seed tốt nhất theo test.

## 8. Đối chứng và điều kiện so sánh

| Phương pháp | Vai trò | Điều kiện |
| --- | --- | --- |
| Chèn theo quãng đường tăng thêm | Mốc cơ bản và kiểm tra hệ thống | Bộ sinh, kiểm tra, thứ tự đơn dùng chung. |
| Hàm tuyến tính được chỉnh trọng số | Đối chứng chính cho nhu cầu dùng GP | Cùng đặc trưng, ngân sách chỉnh công bố rõ. |
| GP bỏ biến chờ tường minh | Phân tích tác dụng của tín hiệu chờ | Dùng chung các thành phần khác. |
| GP đầy đủ | Phương pháp đề xuất | Cấu hình và quy tắc chọn cây khóa trước test. |
| CFA-VNS tái hiện | Đối chứng toàn bộ bộ giải | Chỉ dùng khi đạt kiểm tra tái hiện; báo cáo ngân sách và sai khác. |
| Tìm kiếm ngẫu nhiên cây, tùy ngân sách | Kiểm tra lợi ích của tiến hóa so với chỉ thử nhiều công thức | Ngân sách đánh giá cây tương ứng. |

### 8.1. Hàm tuyến tính phải đủ mạnh

Không đặt trọng số tùy ý rồi coi kết quả kém của nó là bằng chứng cho GP. Dùng cùng các đặc trưng và một thủ tục chỉnh trọng số xác định. Quá trình tìm trọng số được đánh giá trên train, chọn cấu hình bằng validation và khóa trước test.

Báo cáo tổng số lượt mô phỏng và thời gian chỉnh của cả hai phương pháp. Có thể bổ sung một phép so cùng ngân sách đánh giá để phân biệt tác dụng của biểu diễn với tác dụng của việc đầu tư nhiều tính toán hơn.

### 8.2. Diễn giải đúng thí nghiệm bỏ biến chờ

Nếu `delta_tardiness` vẫn được tính bằng lịch có hàng chờ, loại `delta_wait` không loại toàn bộ thông tin tắc nghẽn. Khi đó chỉ được kết luận về **giá trị bổ sung của biến chờ tường minh**.

Muốn so toàn bộ cơ chế dự báo có/không có hàng chờ cần một thí nghiệm riêng. Thí nghiệm đó thay cả bộ ước lượng, nên không còn chỉ là so hai tập biến đầu vào.

### 8.3. So với CFA-VNS

Hai câu hỏi phải được báo cáo riêng:

1. **GP có giúp chấm các phương án chung tốt hơn không?** So trực tiếp GP và hàm tuyến tính.
2. **Bộ giải GP cạnh tranh với CFA-VNS thế nào?** So hai hệ thống hoàn chỉnh theo chất lượng và thời gian.

GP thua CFA-VNS về điểm nhưng nhanh hơn có thể tạo ra một đánh đổi đáng phân tích. Muốn nhận định lợi ích tốc độ, cần so thêm CFA-VNS ở các giới hạn thời gian ngắn hơn; không chỉ so GP với một cấu hình tìm kiếm kéo dài.

## 9. Kế hoạch tái hiện CFA-VNS

### 9.1. Ranh giới giữa tái hiện và lấy cảm hứng

R2 dùng chi phí định tuyến có thêm phạt chờ và phạt xe nhàn rỗi; VNS sử dụng các phép biến đổi block/bridge. Nơi cần đọc: mục 3, 4.1, 4.2, Algorithm 1 và Appendix A–E. Bài nêu ngân sách 9 phút/kỳ trong thiết lập thực nghiệm.

Chỉ thêm một hệ số phạt chờ vào chèn đơn thì gọi là **heuristic chèn lấy cảm hứng từ CFA**, không gọi là tái hiện CFA-VNS.

### 9.2. Các bước thực hiện

1. Lập bảng đặc tả từ bài: ký hiệu, công thức, cấu trúc tuyến, cách xử lý đơn và điều kiện kết thúc.
2. Hiện thực bộ dự báo lịch và đối chiếu với simulator trên trường hợp tính tay được.
3. Viết thủ tục tạo tuyến ban đầu theo mô tả; ghi rõ những chi tiết bài không xác định.
4. Hiện thực từng phép biến đổi, kiểm tra giữ ràng buộc và đối chiếu nghiệm nhỏ bằng duyệt toàn bộ.
5. Ghép vòng tìm kiếm, ngân sách và cách chọn nghiệm.
6. Chạy một tập nhỏ; điều tra sai lệch thay vì chỉnh tham số theo kết quả test.
7. Khi đủ tin cậy mới mở rộng và đặt cạnh các con số công bố có cấu hình tương thích.

Lưu một bảng gồm: chi tiết đã theo bài, chi tiết tự quyết định, kiểm tra đã làm và ảnh hưởng có thể có.

### 9.3. Chi phí chạy

Không mặc định áp dụng ngay 9 phút cho tất cả kỳ của tất cả instance. Ví dụ, nếu 100 kỳ đều dùng hết 540 giây thì một lượt đã cần tới 15 giờ cho phần tìm kiếm. Đây là dự toán cực đại theo ví dụ, không phải thời gian đã đo.

Có hai chế độ riêng:

- **Chế độ đối chiếu tài liệu:** cố gắng theo thiết lập tham chiếu, trong ngân sách cho phép.
- **Chế độ so tài nguyên:** nhiều giới hạn ngắn hơn để xây quan hệ chất lượng–thời gian trên cùng phần cứng.

Nếu không đạt tái hiện đầy đủ, vẫn có thể hoàn thành nghiên cứu GP với đối chứng trực tiếp đủ mạnh, nhưng phải thu hẹp tuyên bố. Không gọi phương pháp là vượt CFA-VNS khi chưa có phép so tương ứng.

## 10. Chia dữ liệu và khóa giao thức thực nghiệm

### 10.1. Đơn vị chia

Chia theo instance/phiên vận hành. Nếu nhiều instance cùng được sinh từ một kịch bản nền, xem xét nhóm chúng trước khi chia để giảm rò rỉ.

Không tự khẳng định các tệp độc lập về thống kê chỉ vì tên khác nhau. Lập danh sách instance và kiểm tra quan hệ giữa các biến thể trước.

| Tập | Sử dụng |
| --- | --- |
| Train | Đánh giá fitness, học cây và tìm trọng số. |
| Validation | Chọn cấu hình, dừng học, chọn cây theo quy tắc công bố. |
| Test | Đánh giá cuối; không dùng để chọn biến hoặc sửa mô hình sau khi xem điểm. |

Chốt tỷ lệ sau khi kiểm kê số lượng và nhóm quy mô thực có. Giữ đủ mức tải ở các tập khi có thể. Nếu chỉ đủ ít instance, dùng giao thức chia lặp hoặc các fold có tách nhóm và công bố rõ số lần chọn mô hình.

### 10.2. Hai mức khái quát

- **Cùng phạm vi:** instance mới trên những nhóm tải/quy mô đã xuất hiện trong train.
- **Khác phạm vi:** một nhóm quy mô hoặc mức tải được giữ lại hoàn toàn.

Nếu tất cả instance dùng chung mạng nhà máy, kết luận chỉ liên quan khả năng chuyển giữa các luồng đơn/quy mô trên mạng đó. Chưa có bằng chứng chuyển sang một mạng giao thông khác.

### 10.3. Tính công bằng

- Cùng luồng đơn, vị trí ban đầu, cấu hình, phiên bản và quy tắc chấm điểm.
- Tách seed khởi tạo môi trường, seed thuật toán và seed chia dữ liệu.
- Chạy từ trạng thái mới cho mỗi phương pháp; không nối tiếp trạng thái của phương pháp trước.
- Chỉ cho mỗi thuật toán quan sát thông tin hợp lệ ở thời điểm quyết định.
- Sau những quyết định khác nhau, trạng thái xe/hàng chờ khác nhau là kết quả tự nhiên.
- Báo cáo phần cứng, số luồng và tải tính toán đồng thời.

## 11. Chỉ tiêu và phân tích kết quả

| Nhóm | Chỉ tiêu |
| --- | --- |
| Chất lượng chính | `J_benchmark` theo từng instance và tổng hợp. |
| Phục vụ | Tổng độ trễ, tỷ lệ đơn trễ; xác định theo đơn gốc hay đơn con. |
| Di chuyển | Tổng quãng đường và đại lượng bình quân đúng benchmark. |
| Tắc nghẽn | Tổng thời gian chờ; phân bố theo nhà máy và giai đoạn vận hành. |
| Tính hợp lệ | Số vi phạm, đơn chưa hoàn thành, số lượt chạy thất bại. |
| Tính toán trực tuyến | Trung bình, p95, lớn nhất mỗi lần quyết định; tổng thời gian một instance. |
| Chi phí ngoại tuyến | Tổng lượt đánh giá, giờ CPU/thời gian thực, số seed. |
| Độ phức tạp GP | Số nút, độ sâu, các biến sử dụng. |

Đo riêng thời gian sinh phương án, kiểm tra, tính đặc trưng và chấm cây. Thời gian đọc/ghi tệp có thể báo riêng, nhưng thời gian quyết định đầu-cuối phải có.

### 11.1. Thống kê

- So sánh theo cặp trên cùng instance.
- Báo cáo trung bình, trung vị và độ phân tán; không chỉ lấy lần chạy tốt nhất.
- Tách biến thiên giữa seed học và giữa instance; không coi tất cả kỳ điều phối là mẫu độc lập.
- Nếu dùng khoảng tin cậy bootstrap, lấy mẫu ở cấp instance hoặc nhóm kịch bản phù hợp.
- Có thể bổ sung kiểm định ghép cặp khi số mẫu phù hợp; báo cả độ lớn hiệu ứng.
- Tổng hợp theo nhóm tải để tránh một vài instance cực lớn che khuất các nhóm khác.
- Với điểm đối chứng bằng hoặc gần 0, báo chênh lệch tuyệt đối thay vì phần trăm thiếu ổn định.

Không đưa ra ngưỡng cải thiện giả định như một kết quả. Nếu đặt ngưỡng thực dụng để quyết định tiếp tục, phải đặt trước khi xem test và giải thích theo mục đích sử dụng.

### 11.2. Đánh giá chi phí học

Nếu GP tốn thêm thời gian huấn luyện nhưng tiết kiệm thời gian trực tuyến, có thể ước lượng số lượt sử dụng hòa vốn:

`N_break_even = extra_training_time / time_saved_per_use`

Chỉ dùng khi mẫu số dương và hai phương pháp đạt mức chất lượng có thể so sánh. Đồng thời báo chi phí chỉnh baseline, không coi baseline là miễn phí nếu nó cũng được huấn luyện/chỉnh nhiều lần.

### 11.3. Các hình nên có

1. Điểm theo phương pháp, tách nhóm quy mô.
2. Chất lượng so với thời gian tính toán.
3. Kết quả có/không có biến chờ tường minh.
4. Chất lượng train–validation theo thế hệ GP.
5. Số xe chờ theo thời gian trên một vài instance được chọn theo quy tắc cố định.
6. Một cây GP nhỏ và ví dụ hai phương án mà nó xếp hạng khác hàm tuyến tính.

Tránh chọn riêng một tình huống đẹp để chứng minh toàn bộ phương pháp.

## 12. Kiểm tra đúng trước khi đo tốt

### 12.1. Các tình huống nhỏ cần có

| Tình huống | Điều cần xác nhận |
| --- | --- |
| Một xe, một đơn | Điểm số và lịch phục vụ tính tay khớp. |
| Hai đơn có thứ tự lấy khác nhau | Phát hiện giao sai LIFO. |
| Tải chạm ngưỡng/vượt ngưỡng | Kiểm tra sau từng thao tác. |
| Hai xe, một cửa | Đúng thứ tự chờ và thời điểm bắt đầu phục vụ. |
| Nhiều xe đến đồng thời | Thứ tự xử lý xác định, được ghi rõ. |
| Đơn vượt tải | Chia theo quy tắc; trễ của đơn gốc được gom đúng. |
| Xe đang chạy hoặc phục vụ | Không thay đổi phần công việc bị khóa. |
| Không có đơn mới | Hệ thống vẫn thực hiện hết các đơn đang mở. |
| Cây GP lỗi số học | Không phát sinh quyết định sai hoặc điểm không hữu hạn. |

### 12.2. Đối chiếu bộ dự báo lịch

Với cùng một trạng thái và bộ tuyến, tạm không phát thêm đơn rồi so bộ dự báo với diễn biến simulator: đến, vào hàng chờ, bắt đầu phục vụ, rời, giao và điểm số. Sai lệch phải được giải thích trước khi dùng bộ dự báo để huấn luyện.

Việc tương lai xuất hiện thêm đơn có thể làm dự báo trước đó thay đổi; điều đó khác với sai lệch khi cùng một kịch bản không có thông tin mới.

### 12.3. Ranh giới thông tin

Kiểm tra callback chỉ nhận đơn đã công bố. Tạo hai luồng có cùng lịch sử đến thời điểm `t` nhưng tương lai khác nhau; với cùng seed và trạng thái, quyết định tại `t` phải giống nhau.

## 13. Các mốc triển khai và quyết định tiếp tục

Lịch dưới đây là dự toán 8 tuần, cần điều chỉnh sau pilot và lịch nộp thực tế.

| Mốc | Thời gian dự kiến | Sản phẩm | Điều kiện qua mốc |
| --- | --- | --- | --- |
| M0: Khóa đặc tả | Tuần 1 | Bảng cấu hình, danh sách nguồn và sai khác | Chọn được một cấu hình có thể chạy và giải thích. |
| M1: Chạy đúng môi trường | Tuần 1–2 | Demo, bộ chấm, log tình huống nhỏ | Không có vi phạm trong các tình huống bắt buộc. |
| M2: Bộ chèn và baseline | Tuần 2–3 | Chèn đơn, hàm tuyến tính, đo thời gian | Hoàn thành instance nhỏ và dự báo lịch được kiểm chứng. |
| M3: Pilot GP | Tuần 3–4 | Một vòng học nhỏ, nhiều seed thăm dò | Có chi phí học chấp nhận được; biết GP có tín hiệu đáng theo đuổi không. |
| M4: CFA có điều kiện | Tuần 4–5 | Bản tái hiện và hồ sơ sai khác | Chỉ nhận là CFA-VNS khi đủ thành phần và kiểm tra. |
| M5: Khóa thực nghiệm | Tuần 5–6 | Split, cấu hình, seed, ngân sách | Giao thức được lưu trước khi chạy test. |
| M6: Chạy đánh giá | Tuần 6–7 | Kết quả, thống kê, ablation | Có kết quả cả trường hợp xấu và thất bại. |
| M7: Phân tích, báo cáo | Tuần 8 | Bảng hình, cây GP, giới hạn, demo | Người khác tái chạy được các kết quả chính. |

### 13.1. Cửa quyết định sau M2

Nếu bộ chèn không đúng hoặc dự báo lịch chưa khớp, chưa mở rộng GP. Tập trung sửa mô hình vì một quy tắc học trên chi phí sai không tạo bằng chứng đáng tin.

### 13.2. Cửa quyết định sau M3

Tiếp tục nếu chi phí học khả thi và có tín hiệu trên validation: chất lượng tốt hơn, đánh đổi thời gian hữu ích hoặc hành vi ổn định đáng phân tích. Pilot nhỏ chưa cần chứng minh ưu thế có ý nghĩa thống kê.

Nếu GP chưa tốt, kiểm tra lỗi số học, đặc trưng, không gian hành động và ngân sách một cách có giới hạn. Không tiếp tục thêm toán tử và biến không có điểm dừng.

Nếu sau các kiểm tra hợp lý GP vẫn tương đương hoặc kém hàm tuyến tính, giữ kết quả đó. Có thể điều chỉnh câu hỏi sang giới hạn của biểu diễn GP trong mô hình này; không bịa động cơ để giữ kết luận ban đầu.

### 13.3. Mức hoàn thành

- **Mức tối thiểu:** mô hình đúng, baseline đủ mạnh, GP hoạt động, test độc lập và phân tích trung thực.
- **Mức tốt:** nhiều seed, ablation, phân tích thời gian và khả năng chuyển quy mô.
- **Mức mở rộng:** thêm CFA-VNS được kiểm chứng và đối chiếu theo nhiều ngân sách.

Tái hiện CFA-VNS là đóng góp kỹ thuật đáng kể nhưng không tự chứng minh đóng góp của GP.

## 14. Rủi ro và phương án xử lý

| Rủi ro | Dấu hiệu | Hành động |
| --- | --- | --- |
| Khác cấu hình benchmark | Lịch/điểm sai ngay ở ví dụ nhỏ | Dừng so công bố; chốt đơn vị và phiên bản. |
| Chi phí sinh phương án quá lớn | Phần chấm cây rất nhỏ trong tổng thời gian | Tối ưu/cắt tập ứng viên dùng chung; đo lại toàn bộ. |
| Dự báo chờ kém | Chọn tuyến có vẻ tốt nhưng vận hành tắc | Kiểm tra lịch toàn hệ thống và cơ chế xếp hàng. |
| GP học thuộc | Train tốt, validation/test kém | Giảm độ phức tạp, tăng đa dạng train, kiểm tra chia nhóm. |
| Quá tải tính toán | Một thế hệ mất quá lâu | Đo pilot, giảm quy mô học, dùng cache, giới hạn mở rộng. |
| CFA khó tái hiện | Nhiều chi tiết chưa rõ hoặc điểm lệch | Lưu sai khác, giữ baseline trực tiếp; thu hẹp tuyên bố. |
| Đối chứng yếu | Chỉ hơn công thức chưa chỉnh | Chỉnh hàm tuyến tính và so cùng ngân sách học. |
| Không có lợi ích GP | Qua nhiều seed vẫn không cải thiện | Báo kết quả âm; ưu tiên mô hình đơn giản cho ứng dụng. |

Không tự bỏ cửa bốc dỡ hoặc LIFO để tăng điểm rồi vẫn gọi là bài toán gốc.

## 15. Sản phẩm bàn giao dự kiến

Các đường dẫn dưới đây là cấu trúc đề xuất cho repository tương lai, **chưa phải các tệp đã tạo**.

```text
README.md
docs/problem_spec.md
docs/configuration_differences.md
docs/cfa_reproduction.md
docs/experiment_protocol.md
configs/
data_manifest/
src/problem/
src/simulation/
src/feasibility/
src/insertion/
src/features/
src/policies/
src/gp/
src/baselines/
experiments/
tests/
results/
report/
```

Mỗi lượt chạy lưu tối thiểu: mã phiên bản, cấu hình và mã băm, instance, vị trí khởi tạo, các seed, tên phương pháp, thời gian, điểm thành phần, tình trạng hoàn thành, vi phạm và cây/trọng số sử dụng.

Báo cáo cuối nên theo cấu trúc:

1. Bài toán và lý do cần kiểm tra cách học quy tắc.
2. Công trình liên quan và giới hạn chuyển từ DVRP khác sang DPDP.
3. Mô hình, simulator, dữ liệu và cấu hình.
4. Bộ chèn cố định, đặc trưng và GP.
5. Đối chứng và giao thức thực nghiệm.
6. Kết quả chất lượng–thời gian, ablation và phân tích cây.
7. Giới hạn, kết quả không thuận lợi và khả năng tái lập.

## 16. Cách bảo vệ tính hợp lý của hướng GP

| Câu hỏi có thể gặp | Cách trả lời cần có bằng chứng |
| --- | --- |
| Vì sao không chỉnh vài trọng số là đủ? | Đưa đối chứng tuyến tính đã được chỉnh, cùng đặc trưng và ngân sách công bố. |
| GP có thật sự giải bài toán không? | Chỉ rõ bộ giải gồm xây phương án, kiểm tra và quy tắc học; đo tác dụng của từng phần. |
| Vì sao không dùng CFA-VNS? | Trình bày đánh đổi đo được, không mặc định CFA-VNS quá chậm. |
| Thông tin chờ có gì mới? | Không nhận là mới; kiểm tra giá trị của việc GP sử dụng thông tin đó. |
| Có phải dùng trước thông tin tương lai? | Chứng minh ranh giới callback và phép kiểm tra hai luồng cùng lịch sử. |
| Cây biểu thức có giải thích được không? | Đưa cây nhỏ, ví dụ xếp hạng và phân tích độ nhạy; không chỉ nói cây nên dễ hiểu. |
| Nếu GP không thắng thì sao? | Báo cáo điều kiện thất bại và khi nào hàm đơn giản là đủ; không đổi tiêu chí sau test. |

## 17. Việc nên làm ngay

1. Khóa một cấu hình DPDP sau khi xử lý sai khác thời gian bốc dỡ.
2. Chạy một instance nhỏ bằng `dvrpsim` và lưu lịch/điểm làm chuẩn.
3. Xây bộ kiểm tra và bộ chèn dùng chung.
4. Có hàm tuyến tính được chỉnh và số đo thời gian trước khi tăng quy mô GP.
5. Chạy pilot GP để quyết định tiếp tục bằng bằng chứng.

**Tiêu chuẩn lựa chọn cuối cùng:** GP đáng dùng khi có lợi ích đo được về chất lượng, thời gian hoặc khả năng thích nghi đủ bù chi phí học và độ phức tạp. Việc tìm được simulator và bài báo toàn văn giúp triển khai khả thi; chúng chưa phải bằng chứng GP là lựa chọn tốt nhất.
