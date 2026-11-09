# Ghi chú học `dvrpsim` và giải thích từng dòng `demo.py`

Tài liệu đối chiếu với **`dvrpsim 1.0.0` đang cài trong `.venv`** và file `demo.py` hiện tại gồm **108 dòng**. Số dòng bên dưới là số dòng trong `demo.py`, không phải số dòng của tài liệu này. Nếu sửa `demo.py`, số dòng có thể thay đổi.

## 1. `dvrpsim` dùng để làm gì?

`dvrpsim` là thư viện Python để mô phỏng **bài toán định tuyến xe động** — Dynamic Vehicle Routing Problem (DVRP). Trong bài toán động, đơn hàng hoặc thông tin mới xuất hiện trong lúc xe đang hoạt động, nên quyết định điều phối có thể cần cập nhật theo thời gian.

Bạn mô tả kho, khách hàng, xe, đơn hàng và quy tắc điều phối. Thư viện quản lý thời gian mô phỏng, phát sinh sự kiện và cho xe thực hiện những tuyến đã được quyết định.

| Nhu cầu | Vai trò của `dvrpsim` |
|---|---|
| Có đơn mới vào lúc 8, 16, 24... | Đưa đơn vào hệ thống đúng thời điểm mô phỏng đã khai báo. |
| Cần biết xe đang làm gì | Lưu trạng thái xe, vị trí hiện tại, đơn đang chở và các điểm ghé tiếp theo. |
| Cần ra quyết định khi có đơn mới | Gọi `routing_callback()` khi có yêu cầu điều phối. |
| Có quyết định nhận đơn và tuyến xe | Kiểm tra, áp dụng quyết định và mô phỏng xe lấy hàng, di chuyển, giao hàng. |
| Kho chỉ phục vụ được một số xe cùng lúc | Có thể dùng tài nguyên dùng chung để mô phỏng giới hạn phục vụ. Demo chưa dùng chức năng này. |
| Cần phân tích kết quả | Ghi log, lưu lịch sử ghé điểm và cung cấp các hàm tiện ích thu thập thống kê. |

**Thuật toán tối ưu tuyến do bạn cung cấp.** `dvrpsim` không tự tìm đường ngắn nhất hoặc tự chọn cách giao hàng tốt nhất cho demo. Trong chương trình này, chính `DemoModel.routing_callback()` quyết định nhận/từ chối đơn, chọn xe và sắp xếp điểm giao.

Thư viện sử dụng **SimPy** làm nền tảng mô phỏng sự kiện rời rạc. Thời gian mô phỏng nhảy đến sự kiện tiếp theo; `return 5` không làm chương trình đợi 5 giây thực tế. Bạn tự quy ước một đơn vị mô phỏng là giây, phút hoặc đơn vị khác và dùng nhất quán.

## 2. Các thành phần trong chương trình

| Thành phần | Ý nghĩa | Ví dụ trong demo |
|---|---|---|
| `Model` | Lớp quản lý toàn bộ mô phỏng. | Lớp cha của `DemoModel`. |
| `Location` | Một địa điểm: kho hoặc địa chỉ khách. | `KHO`, `KHACH_1`...`KHACH_5`. |
| `Vehicle` | Xe và quy trình hoạt động của xe. | Lớp cha của `Truck`. |
| `Order` | Một yêu cầu lấy hàng và giao hàng. | `DON_1`...`DON_5`. |
| `Visit` | Một lần xe ghé một địa điểm, có thể kèm lấy/giao hàng. | Thư viện tạo từ từng dictionary trong `route`. |
| `model.env` | Môi trường quản lý thời gian và sự kiện. | Dùng để đăng ký tiến trình cung cấp đơn hàng. |
| `order_provider(...)` | Hàm tiện ích cung cấp các đơn theo `release_date`. | Đưa 5 đơn vào mô phỏng lần lượt. |
| `Truck` | Lớp bạn tự định nghĩa, kế thừa `Vehicle`. | Quy định thời gian di chuyển là 5. |
| `DemoModel` | Lớp bạn tự định nghĩa, kế thừa `Model`. | Quy định chính sách điều phối đơn giản. |

**Kế thừa** nghĩa là lớp con dùng được các method của lớp cha. Vì `DemoModel(Model)`, đối tượng `model` dùng được `add_location()`, `add_vehicle()`, `get_state()` và `run()` dù bạn không viết lại các method này.

**Ghi đè method** nghĩa là định nghĩa lại một method của lớp cha trong lớp con. Demo ghi đè `Vehicle.travel_time()` và `Model.routing_callback()` để thay đổi hành vi mặc định.

## 3. Demo đang giải quyết tình huống nào?

Chương trình tạo một kho, một xe và năm khách hàng. Mỗi khách có một đơn, lần lượt xuất hiện vào thời điểm 8, 16, 24, 32 và 40.

Mỗi lần có đơn mới, chương trình thực hiện quy tắc sau:

1. Đọc trạng thái hiện tại.
2. Tìm các đơn đang mở và chưa được phân cho xe.
3. Nếu không có đơn cần xử lý, trả về quyết định rỗng.
4. Tìm xe đang rảnh **và đang ở kho**.
5. Nếu không có xe phù hợp, từ chối các đơn chưa được phân công.
6. Nếu có xe, chọn xe đầu tiên trong danh sách phù hợp.
7. Tạo tuyến: lấy hàng tại kho → giao lần lượt từng đơn → quay về kho.
8. Trả quyết định cho thư viện áp dụng.

Đây là chính sách minh họa. Demo không giữ đơn mới trong hàng đợi khi xe đang bận, không ghép thêm đơn vào tuyến đang chạy và không tối ưu thứ tự giao.

## 4. Giải thích từng dòng `demo.py`

Các dòng trống cũng được liệt kê để có thể đối chiếu đủ 108 dòng. Chúng chỉ giúp bố cục dễ đọc, không tạo hành động khi chạy. Với các dòng bên trong hàm, hành động chỉ diễn ra khi hàm được gọi.

### Dòng 1–10: import thư viện và định nghĩa xe

| Dòng | Code gốc | Chức năng và mục đích |
|---:|---|---|
| 1 | `from dvrpsim import Model, Location, Order, Vehicle` | Import bốn lớp của thư viện để tạo mô hình, địa điểm, đơn hàng và xe. |
| 2 | `from dvrpsim.utils.order_providers import order_provider` | Import hàm tiện ích cung cấp đơn hàng theo thời điểm xuất hiện. Đây là hàm độc lập, không phải method của `Model`. |
| 3 | *(trống)* | Tách phần import khỏi phần định nghĩa lớp. |
| 4 | *(trống)* | Thêm khoảng cách để dễ đọc. |
| 5 | `class Truck(Vehicle):` | Định nghĩa lớp xe `Truck` kế thừa `Vehicle`; có sẵn quy trình di chuyển, lấy hàng, giao hàng của thư viện. |
| 6 | `def travel_time(self, origin, destination):` | Ghi đè method tính thời gian đi từ `origin` đến `destination`. `self` là đối tượng xe hiện tại; hai tham số còn lại là các đối tượng địa điểm. |
| 7 | `# Mỗi chặng đường mất 5 đơn vị thời gian` | Comment giải thích giả định thời gian; Python không thực thi comment. |
| 8 | `return 5` | Trả thời gian di chuyển cố định là 5, chưa sử dụng vị trí hoặc khoảng cách của hai địa điểm. Việc ghé tiếp cùng địa điểm hiện tại được thư viện xử lý không có chặng di chuyển thực tế. |
| 9 | *(trống)* | Tạo khoảng cách giữa các định nghĩa. |
| 10 | *(trống)* | Tạo khoảng cách trước lớp tiếp theo. |

### Dòng 11–24: đọc trạng thái và lọc đơn chưa được phân công

| Dòng | Code gốc | Chức năng và mục đích |
|---:|---|---|
| 11 | `class DemoModel(Model):` | Định nghĩa mô hình riêng, kế thừa các chức năng quản lý mô phỏng của `Model`. |
| 12 | `def routing_callback(self):` | Ghi đè callback điều phối. Thư viện gọi method này khi xử lý một yêu cầu điều phối; kết quả trả về là dictionary quyết định. |
| 13 | `# Đọc trạng thái hiện tại` | Comment mô tả bước lấy dữ liệu đầu vào cho thuật toán. |
| 14 | `state = self.get_state()` | Gọi method kế thừa từ `Model`, lấy dictionary chứa thời gian hiện tại, xe và các đơn đang mở. |
| 15 | *(trống)* | Tách bước đọc trạng thái khỏi bước lọc đơn. |
| 16 | `# Tìm các đơn chưa được phân công` | Comment nêu tiêu chí của danh sách `pending`. |
| 17 | `pending = [` | Bắt đầu tạo list bằng cú pháp list comprehension. |
| 18 | `order_id` | Mỗi phần tử được giữ lại trong list là ID đơn hàng, không phải toàn bộ đối tượng `Order`. |
| 19 | `for order_id, order in state["open_orders"].items()` | Duyệt các cặp ID và dữ liệu đơn đang mở. `.items()` trả từng cặp key/value của dictionary; `order` ở đây là dictionary trạng thái. |
| 20 | `if order["assigned_vehicle"] is None` | Chỉ giữ đơn chưa có xe được phân công. `None` biểu thị chưa có giá trị; dùng `is None` để kiểm tra. |
| 21 | `]` | Kết thúc biểu thức tạo `pending`. |
| 22 | *(trống)* | Tách bước lọc khỏi nhánh kiểm tra kết quả. |
| 23 | `if not pending:` | Kiểm tra list rỗng: hiện không có đơn chưa phân công cần xử lý. |
| 24 | `return {"vehicles": {}, "orders": {}}` | Kết thúc callback với quyết định rỗng: không cập nhật tuyến xe hoặc quyết định đơn hàng trong lần này. |

`open_orders` không chỉ gồm đơn mới: nó còn có thể gồm đơn đã nhận nhưng chưa giao xong. Điều kiện `assigned_vehicle is None` giúp bỏ qua những đơn đã có xe phụ trách. Đơn chưa đến thời điểm xuất hiện chưa có trong `open_orders`.

### Dòng 25–44: tìm xe và xử lý trường hợp thiếu xe

| Dòng | Code gốc | Chức năng và mục đích |
|---:|---|---|
| 25 | *(trống)* | Tách nhánh không có đơn khỏi bước tìm xe. |
| 26 | `# Tìm xe rảnh tại kho` | Comment nêu điều kiện chọn xe. |
| 27 | `available = [` | Bắt đầu list comprehension tạo danh sách xe phù hợp. |
| 28 | `vehicle_id` | Mỗi phần tử trong danh sách là ID xe. |
| 29 | `for vehicle_id, vehicle in state["vehicles"].items()` | Duyệt từng xe trong dictionary trạng thái; `vehicle` ở đây là dictionary, không phải đối tượng `Vehicle`. |
| 30 | `if vehicle["status"] == "IDLE"` | Chỉ xét xe đang rảnh theo trạng thái mô phỏng. |
| 31 | `and vehicle["current_visit"]["location"] == "KHO"` | Yêu cầu thêm xe đang ở kho. Python chỉ xét vế này nếu điều kiện `IDLE` trước đó đúng. |
| 32 | `]` | Kết thúc danh sách `available`. |
| 33 | *(trống)* | Tách việc tìm xe khỏi xử lý kết quả. |
| 34 | `# Không có xe rảnh: từ chối các đơn mới` | Comment mô tả chính sách. Chính xác theo code là từ chối toàn bộ `pending`, tức các đơn đang mở chưa được phân công. |
| 35 | `if not available:` | Kiểm tra không có xe nào vừa rảnh vừa đang ở kho. |
| 36 | `return {` | Bắt đầu trả dictionary quyết định từ chối đơn và kết thúc callback qua nhánh này. |
| 37 | `"vehicles": {},` | Không thay đổi tuyến xe nào; xe đang chạy tiếp tục thực hiện tuyến hiện có. |
| 38 | `"orders": {` | Bắt đầu dictionary quyết định cho các đơn hàng. |
| 39 | `order_id: {"status": "rejected"}` | Tạo một mục quyết định: đơn có ID tương ứng sẽ bị từ chối. Chuỗi `rejected` là giá trị quyết định mà thư viện xử lý. |
| 40 | `for order_id in pending` | Lặp qua tất cả ID trong `pending` để tạo các mục trên bằng dict comprehension. |
| 41 | `},` | Đóng dictionary quyết định đơn hàng. |
| 42 | `}` | Đóng dictionary trả về của nhánh thiếu xe. |
| 43 | *(trống)* | Tách nhánh thiếu xe khỏi nhánh có xe. |
| 44 | `vehicle_id = available[0]` | Chọn xe đầu tiên trong danh sách phù hợp. Không so sánh chi phí, tải trọng hoặc khoảng cách giữa các xe. |

### Dòng 45–72: tạo tuyến và trả quyết định điều phối

| Dòng | Code gốc | Chức năng và mục đích |
|---:|---|---|
| 45 | *(trống)* | Tách bước chọn xe khỏi bước tạo tuyến. |
| 46 | `# Lấy hàng tại kho` | Comment mô tả điểm ghé đầu tiên của tuyến. |
| 47 | `route = [` | Tạo list các điểm ghé theo thứ tự xe sẽ thực hiện. |
| 48 | `{` | Bắt đầu dictionary mô tả một điểm ghé. |
| 49 | `"location": "KHO",` | Đặt địa điểm của điểm ghé này là kho. Dùng ID đã đăng ký trong mô hình. |
| 50 | `"pickup_list": pending,` | Yêu cầu lấy tại kho tất cả đơn trong `pending`. Các phần tử là ID đơn hàng. |
| 51 | `}` | Đóng dictionary của điểm lấy hàng tại kho. |
| 52 | `]` | Kết thúc list ban đầu; lúc này tuyến mới có điểm lấy hàng tại kho. |
| 53 | *(trống)* | Tách điểm lấy hàng khỏi các điểm giao. |
| 54 | `# Giao lần lượt cho từng khách` | Comment mô tả bước thêm các địa điểm giao hàng. |
| 55 | `for order_id in pending:` | Duyệt lần lượt các đơn theo thứ tự trong `pending`; chưa sắp xếp bằng thuật toán tối ưu. |
| 56 | `route.append({` | Bắt đầu tạo dictionary điểm giao và thêm vào cuối list `route`. |
| 57 | `"location": state["open_orders"][order_id]["delivery_location"],` | Tra ID địa điểm giao của đơn hiện tại trong trạng thái, rồi dùng làm địa điểm ghé. |
| 58 | `"delivery_list": [order_id],` | Yêu cầu giao đơn hiện tại tại điểm này. List có một ID. |
| 59 | `})` | Đóng dictionary và lời gọi `append()`; hoàn tất thêm một điểm giao. |
| 60 | *(trống)* | Tách vòng lặp thêm điểm giao khỏi điểm cuối tuyến. |
| 61 | `# Quay về kho sau khi giao xong` | Comment mô tả điểm kết thúc tuyến. |
| 62 | `route.append({"location": "KHO"})` | Thêm một điểm về kho, không kèm danh sách lấy/giao hàng. Dòng này nằm ngoài vòng `for`, nên chỉ thêm một lần. |
| 63 | *(trống)* | Tách bước tạo tuyến khỏi bước trả quyết định. |
| 64 | `return {` | Bắt đầu trả toàn bộ quyết định điều phối cho thư viện. |
| 65 | `"vehicles": {` | Bắt đầu phần quyết định tuyến của xe. |
| 66 | `vehicle_id: {"next_visits": route}` | Đặt chuỗi điểm ghé sắp tới cho xe được chọn bằng list `route`. Các điểm được thực hiện theo thứ tự list. |
| 67 | `},` | Đóng phần quyết định xe. |
| 68 | `"orders": {` | Bắt đầu phần quyết định trạng thái đơn hàng. |
| 69 | `order_id: {"status": "accepted"}` | Tạo quyết định chấp nhận đơn có ID tương ứng; chấp nhận chưa có nghĩa là đã giao xong. |
| 70 | `for order_id in pending` | Tạo quyết định chấp nhận cho mọi đơn trong `pending`. |
| 71 | `},` | Đóng dictionary quyết định đơn hàng. |
| 72 | `}` | Đóng quyết định trả về; thư viện tiếp tục kiểm tra, áp dụng và mô phỏng việc thực hiện tuyến. |

Ví dụ khi `pending = ["DON_1"]`, quyết định trả về có dạng:

```python
{
    "vehicles": {
        "XE_1": {
            "next_visits": [
                {"location": "KHO", "pickup_list": ["DON_1"]},
                {"location": "KHACH_1", "delivery_list": ["DON_1"]},
                {"location": "KHO"},
            ]
        }
    },
    "orders": {
        "DON_1": {"status": "accepted"}
    },
}
```

`vehicles` và `orders` là hai phần của **quyết định**; chúng không phải danh sách đối tượng được tạo mới. `next_visits` quy định thứ tự điểm ghé, `pickup_list` quy định đơn lấy tại điểm ghé và `delivery_list` quy định đơn giao tại điểm ghé.

### Dòng 73–97: tạo mô hình, địa điểm, xe và đơn hàng

| Dòng | Code gốc | Chức năng và mục đích |
|---:|---|---|
| 73 | *(trống)* | Tách phần định nghĩa lớp khỏi phần tạo dữ liệu. |
| 74 | *(trống)* | Thêm khoảng cách để dễ đọc. |
| 75 | `model = DemoModel()` | Tạo đối tượng mô hình, bao gồm môi trường mô phỏng và các cấu trúc quản lý. Chưa bắt đầu chạy thời gian mô phỏng. |
| 76 | *(trống)* | Tách việc tạo mô hình khỏi việc tạo kho. |
| 77 | `# Tạo kho` | Comment mô tả nhóm lệnh tạo địa điểm lấy hàng. |
| 78 | `depot = Location(id="KHO")` | Tạo đối tượng địa điểm có ID `KHO`. Biến `depot` tham chiếu đến đối tượng này. |
| 79 | `model.add_location(depot)` | Đăng ký kho vào mô hình. Đây là method có sẵn của `Model`; tạo `Location` và đăng ký vào `Model` là hai bước riêng. |
| 80 | *(trống)* | Tách việc tạo kho khỏi việc tạo xe. |
| 81 | `# Tạo xe, ban đầu nằm tại kho` | Comment mô tả cấu hình ban đầu của xe. |
| 82 | `truck = Truck(id="XE_1")` | Tạo đối tượng xe có ID `XE_1`; xe này sử dụng method `travel_time()` do bạn định nghĩa. |
| 83 | `truck.initial_location = depot` | Gán địa điểm ban đầu của xe là đối tượng kho. Đây là gán thuộc tính, không phải gọi method. |
| 84 | `model.add_vehicle(truck)` | Đăng ký xe vào mô hình, để thư viện quản lý và đưa vào trạng thái điều phối. |
| 85 | *(trống)* | Tách việc tạo xe khỏi việc tạo đơn. |
| 86 | `# Tạo 5 đơn hàng` | Comment mô tả nhóm lệnh tiếp theo. |
| 87 | `orders = []` | Tạo list Python rỗng để giữ các đối tượng đơn trước khi đưa vào mô phỏng. |
| 88 | *(trống)* | Tách khai báo list khỏi vòng lặp. |
| 89 | `for i in range(5):` | Lặp năm lần với `i` bằng 0, 1, 2, 3, 4; mỗi lần tạo một khách và một đơn. |
| 90 | `customer = Location(id=f"KHACH_{i + 1}")` | Tạo địa điểm khách; f-string chèn giá trị `i + 1` để sinh ID từ `KHACH_1` đến `KHACH_5`. |
| 91 | `model.add_location(customer)` | Đăng ký địa điểm khách hiện tại vào mô hình. |
| 92 | *(trống)* | Tách việc tạo khách khỏi việc tạo đơn tương ứng. |
| 93 | `order = Order(id=f"DON_{i + 1}")` | Tạo đối tượng đơn có ID từ `DON_1` đến `DON_5`. Việc này chưa làm đơn xuất hiện trong mô phỏng. |
| 94 | `order.pickup_location = depot` | Gán địa điểm lấy hàng của đơn là kho. |
| 95 | `order.delivery_location = customer` | Gán địa điểm giao hàng là khách vừa tạo ở lần lặp này. |
| 96 | `order.release_date = (i + 1) * 8` | Gán thời điểm xuất hiện: 8, 16, 24, 32, 40. Đây là mốc thời gian mô phỏng, không phải hạn giao hàng. |
| 97 | `orders.append(order)` | Thêm đối tượng đơn vào list `orders`; chưa đăng ký trực tiếp đơn vào mô hình. `append()` là method của list Python. |

Sau vòng lặp, chương trình có **6 địa điểm** gồm kho và 5 khách, **1 xe**, cùng **5 đối tượng đơn** đang nằm trong list `orders` để chuẩn bị cung cấp theo lịch.

### Dòng 98–108: đăng ký tiến trình và chạy mô phỏng

| Dòng | Code gốc | Chức năng và mục đích |
|---:|---|---|
| 98 | *(trống)* | Tách bước tạo dữ liệu khỏi bước lập lịch sự kiện. |
| 99 | `# Mỗi lần xuất hiện đơn mới, gọi lại thuật toán điều phối` | Comment mô tả tác dụng của tùy chọn `decision_point_on_request=True` bên dưới. |
| 100 | `model.env.process(` | Bắt đầu đăng ký một tiến trình trong môi trường mô phỏng. `process()` là API của môi trường SimPy mà `dvrpsim` sử dụng. |
| 101 | `order_provider(` | Tạo generator cung cấp đơn theo lịch; generator sẽ được môi trường điều khiển khi mô phỏng chạy. |
| 102 | `model,` | Truyền mô hình nhận các đơn hàng. |
| 103 | `orders,` | Truyền danh sách năm đối tượng đơn đã tạo. |
| 104 | `decision_point_on_request=True,` | Mỗi lần một đơn được đưa vào mô hình, yêu cầu điều phối. Thư viện xử lý yêu cầu và gọi `routing_callback()`. |
| 105 | `)` | Đóng lời gọi `order_provider(...)`. |
| 106 | `)` | Đóng lời gọi `model.env.process(...)`; hoàn tất đăng ký tiến trình cung cấp đơn. |
| 107 | *(trống)* | Tách bước đăng ký tiến trình khỏi lệnh chạy mô phỏng. |
| 108 | `model.run()` | Chạy mô phỏng: gọi bước khởi tạo, xử lý sự kiện/tiến trình cho đến khi hết sự kiện, rồi thực hiện bước kết thúc. |

## 5. Kết quả đã kiểm tra bằng cách chạy demo

Đã chạy file `demo.py` hiện tại bằng Python trong `.venv`, đối chiếu trạng thái đơn và lịch sử xe sau mô phỏng. Log của lần kiểm tra được tạo trong thư mục tạm để không ghi đè `dvrp.log` hiện có.

| Đơn | Thời điểm xuất hiện | Quyết định | Lấy hàng | Giao xong | Xe trở về kho sau đơn này | Giải thích |
|---|---:|---|---:|---:|---:|---|
| `DON_1` | 8 | Chấp nhận | 8 | 13 | 18 | Xe rảnh ở kho lúc đơn xuất hiện. |
| `DON_2` | 16 | Từ chối | — | — | — | Xe đang trên đường từ `KHACH_1` về kho, đến 18 mới về. |
| `DON_3` | 24 | Chấp nhận | 24 | 29 | 34 | Xe đã về kho và đang rảnh. |
| `DON_4` | 32 | Từ chối | — | — | — | Xe đang trên đường từ `KHACH_3` về kho, đến 34 mới về. |
| `DON_5` | 40 | Chấp nhận | 40 | 45 | 50 | Xe đã về kho và đang rảnh. |

Kết quả là **3 đơn giao thành công, 2 đơn bị từ chối, 5 lần gọi điều phối**, mô phỏng kết thúc tại **thời điểm 50**. Các thời điểm trên đều dùng đơn vị thời gian mô phỏng.

Ví dụ tuyến đầu tiên: xe nhận và lấy `DON_1` tại kho lúc 8, đến `KHACH_1` lúc 13, giao ngay và trở về kho lúc 18.

Các giả định làm nên kết quả này:

- `pickup_duration` và `delivery_duration` không được gán nên đều bằng 0 theo mặc định: lấy/giao hàng không tốn thêm thời gian mô phỏng.
- Một chặng giữa hai địa điểm khác nhau tốn 5. Điểm lấy hàng đầu tuyến cũng là kho nơi xe đang đứng nên không phát sinh thêm 5 đơn vị cho thao tác ghé lại cùng kho.
- Thời gian tính quyết định điều phối mặc định không làm tăng thời gian mô phỏng.
- Mỗi khi không có xe rảnh tại kho, code từ chối đơn ngay; đơn không được chờ đến khi xe quay lại.
- Trạng thái `Order.status` sau khi giao vẫn có thể là `ACCEPTED`; muốn biết đã giao xong, đọc `order.is_delivered` hoặc `order.delivery_time`. Trạng thái quyết định và thông tin thực hiện giao hàng được lưu riêng.

## 6. Tra nhanh các method và thuộc tính

### Các method chính của `Model`

| Method | Công dụng |
|---|---|
| `add_location(location)` | Đăng ký địa điểm vào mô hình. |
| `add_vehicle(vehicle)` | Đăng ký xe vào mô hình. |
| `request_order(order, decision_point_on_request=False)` | Lập lịch đưa một đơn vào mô hình tại thời điểm xuất hiện; có thể yêu cầu điều phối khi đơn xuất hiện. Là một cách khác để cung cấp đơn, không cần gọi thêm cho các đơn đã dùng `order_provider`. |
| `get_location_by_id(location_id)` | Tìm địa điểm theo ID; trả `None` nếu không có. |
| `get_vehicle_by_id(vehicle_id)` | Tìm xe theo ID; trả `None` nếu không có. |
| `get_order_by_id(order_id)` | Tìm đơn đã được đưa vào mô hình theo ID; trả `None` nếu chưa có. |
| `create_resource(capacity=1)` | Tạo tài nguyên phục vụ dùng chung, có giới hạn năng lực phục vụ đồng thời. |
| `get_state()` | Lấy dictionary trạng thái để thuật toán đọc. |
| `request_for_routing()` | Tạo yêu cầu điều phối; trả sự kiện báo hoàn tất. Nhiều yêu cầu cùng thời điểm có thể được gộp. |
| `routing_callback()` | Điểm tích hợp thuật toán của bạn, trả dictionary quyết định. Bản mặc định từ chối các đơn đang mở. |
| `init()` | Method để tùy biến khởi tạo; mặc định không làm gì, được `run()` gọi. |
| `run()` | Chạy vòng đời mô phỏng. |

### Các method chính của `Vehicle` và `Order`

| Lớp | Method | Công dụng |
|---|---|---|
| `Vehicle` | `travel_time(origin, destination)` | Xác định thời gian di chuyển; demo ghi đè để trả 5. |
| `Vehicle` | `travel_distance(origin, destination)` | Xác định quãng đường phục vụ tính toán/thống kê; mặc định trả 0, demo chưa ghi đè nên chưa có mô hình khoảng cách thực tế. |
| `Vehicle` | `run()` | Khởi động tiến trình thực hiện các điểm ghé của xe; thường do cơ chế áp dụng tuyến của thư viện gọi. |
| `Vehicle` | `interrupt_predeparture()` | Ngắt quá trình chờ trước khi xuất phát, nếu đang có. |
| `Vehicle` | `interrupt_travel()` | Ngắt tiến trình di chuyển; cách xử lý mặc định không cho phép ngắt, cần tùy biến khi dùng. |
| `Vehicle` | `interrupt_preservice()` | Ngắt tiến trình trước phục vụ; cách xử lý mặc định không cho phép ngắt, cần tùy biến khi dùng. |
| `Vehicle` | `interrupt_service()` | Ngắt tiến trình phục vụ; cách xử lý mặc định không cho phép ngắt, cần tùy biến khi dùng. |
| `Order` | `accept()` | Ghi nhận chấp nhận đơn. |
| `Order` | `reject()` | Ghi nhận từ chối đơn, theo điều kiện trạng thái mà thư viện kiểm tra. |
| `Order` | `cancel()` | Ghi nhận hủy đơn, theo điều kiện cho phép hủy. |
| `Order` | `postpone(until)` | Hoãn quyết định xử lý đơn đến một mốc thời gian. |
| `Order` | `interrupt_postponement()` | Ngắt quá trình hoãn nếu đang diễn ra. |
| `Order` | `pickup(vehicle)` | Ghi nhận xe đã lấy đơn, thời điểm lấy và phát callback tương ứng. |
| `Order` | `deliver()` | Ghi nhận thời điểm giao xong và phát callback tương ứng. |
| `Order` | `update()` | Phát thông báo/callback cập nhật đơn; không nhận tham số thay đổi địa chỉ hay thuộc tính. |

Trong luồng thông thường, hãy trả quyết định qua `routing_callback()` để thư viện áp dụng đồng bộ. Chỉ gọi trực tiếp `pickup()` hoặc `deliver()` không thay thế toàn bộ quy trình di chuyển và phục vụ của xe.

### Callback sự kiện

Callback là method được thư viện gọi khi có sự kiện. Bạn ghi đè để thêm hành vi, ví dụ lưu kết quả khi xe đến khách. Một số callback chính:

| Lớp | Callback ví dụ | Khi nào được gọi? |
|---|---|---|
| `Model` | `on_simulation_start()`, `on_simulation_finish()` | Bắt đầu/kết thúc mô phỏng. |
| `Model` | `on_order_request(order)` | Khi đơn xuất hiện trong mô hình. |
| `Model` | `on_order_acceptance(order)`, `on_order_rejection(order)` | Khi đơn được chấp nhận/từ chối. |
| `Model` | `on_order_pickup(order)`, `on_order_delivery(order)` | Khi đơn được lấy/giao. |
| `Model` | `on_vehicle_departure(vehicle)`, `on_vehicle_arrival(vehicle)` | Khi xe rời/đến điểm ghé. |
| `Model` | `on_routing_start()`, `on_routing_finish(decision)` | Trước khi tính quyết định và khi đã có quyết định, trước bước áp dụng. |
| `Vehicle` | `on_departure()`, `on_arrival()` | Sự kiện xuất phát/đến nơi của chính xe đó. |
| `Vehicle` | `on_service_start()`, `on_service_finish()` | Bắt đầu/kết thúc phục vụ tại điểm ghé. |
| `Order` | `on_request()`, `on_pickup()`, `on_delivery()` | Sự kiện xuất hiện/lấy/giao của chính đơn đó. |

Một số callback mặc định của `Model` còn thực hiện khởi tạo hoặc xử lý trạng thái. Khi ghi đè các callback này để bổ sung hành vi, cần xem phần triển khai và giữ lời gọi `super()` phù hợp, đặc biệt ở `on_simulation_start()` và `on_simulation_finish()`.

### Phân biệt method, thuộc tính và hàm Python

| Cách viết | Loại | Ý nghĩa |
|---|---|---|
| `model.add_location(depot)` | Method của `dvrpsim.Model` | Gọi thao tác đăng ký địa điểm. |
| `model.get_state()` | Method của `dvrpsim.Model` | Gọi thao tác lấy trạng thái. |
| `model.vehicles` | Property | Đọc tập các đối tượng xe có thể duyệt; không thêm `()`. |
| `model.open_orders` | Property | Đọc các đối tượng đơn đang mở; khác với dictionary `state["open_orders"]`. |
| `truck.initial_location` | Thuộc tính | Địa điểm ban đầu của xe; có thể gán bằng `=`. |
| `truck.is_idle` | Property | Đọc giá trị đúng/sai về việc xe có rảnh hay không. |
| `order.release_date` | Thuộc tính | Mốc xuất hiện đơn. |
| `order.is_delivered` | Property | Kiểm tra đơn đã giao xong chưa. |
| `model.env.now` | Property của môi trường | Thời điểm mô phỏng hiện tại. |
| `order_provider(...)` | Hàm tiện ích của `dvrpsim` | Tạo generator cung cấp đơn theo lịch. |
| `orders.append(order)` | Method của list Python | Thêm phần tử vào danh sách. |
| `state["vehicles"].items()` | Method của dict Python | Duyệt các cặp key/value. |
| `range(5)` | Hàm dựng sẵn của Python | Tạo dãy 0 đến 4 để lặp. |

Các hàm tiện ích khác có trong bản cài này gồm `periodic_updater(...)` để yêu cầu điều phối định kỳ; `euclidean_distance(...)`, `manhattan_distance(...)`, `great_circle_distance(...)` để tính khoảng cách; và các hàm trong `dvrpsim.utils.statistics` để thu thập/thể hiện thống kê. Chúng là các hàm độc lập trong module tiện ích, không phải method gọi trực tiếp từ `model`.

## 7. Những phần demo chưa mô hình hóa

- Chưa gán tọa độ, chưa dùng bản đồ, mạng đường hoặc dữ liệu thời gian đi lại: mọi chặng giữa hai địa điểm khác nhau đều mất 5.
- Chưa gán tải trọng xe hoặc lượng hàng có ý nghĩa thực tế; chưa đặt hạn giao và cửa sổ thời gian của đơn.
- Chưa gán thời gian lấy/giao hàng, nên chúng bằng 0 theo mặc định.
- Chưa xét nhiều xe, chi phí vận hành hoặc tiêu chí chọn xe tốt nhất.
- Chưa có thuật toán tìm thứ tự giao tối ưu hoặc cơ chế chờ đơn khi xe đang bận.

Nếu muốn thay đổi hành vi, sửa chính sách nhận đơn và tạo tuyến trong `routing_callback()`. Nếu muốn thay đổi thời gian di chuyển, sửa `Truck.travel_time()`. Nếu muốn thay đổi lịch đơn xuất hiện, sửa `order.release_date` ở dòng 96.

## 8. Cách chạy và nguồn đối chiếu

Chạy từ PowerShell tại thư mục project:

```powershell
.\.venv\Scripts\python.exe .\demo.py
```

Lệnh chạy demo bình thường sẽ sử dụng cấu hình log mặc định, trong đó có file `dvrp.log` ở thư mục chạy.

Tài liệu được đối chiếu trực tiếp với mã nguồn đang cài trong project:

- [Chương trình demo](demo.py).
- [Lớp Model](.venv/Lib/site-packages/dvrpsim/model.py).
- [Lớp Vehicle](.venv/Lib/site-packages/dvrpsim/elements/vehicle.py).
- [Lớp Order](.venv/Lib/site-packages/dvrpsim/elements/order.py).
- [Lớp Location](.venv/Lib/site-packages/dvrpsim/elements/location.py).
- [Lớp Visit](.venv/Lib/site-packages/dvrpsim/elements/visit.py).
- [Hàm cung cấp đơn hàng](.venv/Lib/site-packages/dvrpsim/utils/order_providers.py).
- [Môi trường mô phỏng](.venv/Lib/site-packages/dvrpsim/environment.py).

Các bảng tra nhanh liệt kê những API chính phục vụ việc đọc và mở rộng demo; các method nội bộ bắt đầu bằng `_` không được liệt kê đầy đủ.
