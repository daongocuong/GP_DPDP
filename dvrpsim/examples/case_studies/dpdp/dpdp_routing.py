# Cầu nối dữ liệu giữa simulator DPDP và thuật toán định tuyến.
# VNSME dùng get_dpdp_state() và transform_dpdp_decision(); demo còn dùng
# nhóm hàm trao đổi JSON bên dưới. GP hiện dùng Snapshot/predict_fixed_routes.
# Các mốc thời gian trong state là giây mô phỏng; demand là pallet chuẩn.
import json
import os

from typing import Dict

from dvrpsim               import Model, Visit, Location
from dvrpsim.utils.routing import call_module_function, call_algorithm_in_subprocess

def calculate_earliest_departure_times_at_location( model:Model, location:Location ):
    # Ước tính giờ rời nhà máy của các xe đang ở đây, theo thứ tự đến.
    # Đây là dự báo từ trạng thái hiện tại, không chạy thêm sự kiện mô phỏng.
    vehicles = [ vehicle for vehicle in model.vehicles if vehicle.is_at_location and vehicle.current_location == location ]
    vehicles.sort( key = lambda vehicle : vehicle.current_visit.arrival_time )

    # service_ends: mã xe -> giờ kết thúc phục vụ dự kiến.
    # reservation_list: các xe đã xét, được sắp theo giờ kết thúc phục vụ.
    service_ends  = {}
    reservation_list = []

    for vehicle in vehicles:
        if not vehicle.has_previous_visit:
            # Xe còn ở vị trí xuất phát được coi là sẵn sàng, không cộng service.
            service_ends[vehicle.id] = 0
            continue # vehicle is at its initial location

        # Một visit chiếm dock trong toàn bộ thời gian docking + dỡ + xếp.
        # Thời gian xếp/dỡ được tính từ hệ số trong private_data và quantity,
        # không đọc trực tiếp cột load_time/unload_time của CSV tại đây.
        service_time = model.private_data.get( 'docking_time' )
        service_time += sum( model.private_data.get( 'loading_time' ) * order.quantity for order in vehicle.current_visit.pickup_list )
        service_time += sum( model.private_data.get( 'unloading_time' ) * order.quantity for order in vehicle.current_visit.delivery_list )

        # Ưu tiên mốc thực tế nếu đã xong hoặc đã bắt đầu phục vụ.
        if vehicle.current_visit.service_finish_time is not None:
            service_ends[vehicle.id] = vehicle.current_visit.service_finish_time
            
        elif vehicle.current_visit.service_start_time is not None:
            service_ends[vehicle.id] = vehicle.current_visit.service_start_time + service_time
            
        elif len(reservation_list) < location.resource.capacity:
            # Các xe đã xét chưa chiếm hết số dock: có thể phục vụ ngay khi đến.
            service_ends[vehicle.id] = vehicle.current_visit.arrival_time + service_time

        else:
            # Khi các dock đều đã được đặt, ước tính lúc có dock dành cho xe.
            # Không thể bắt đầu trước giờ đến của chính xe đó.
            service_started = max( vehicle.current_visit.arrival_time, service_ends[reservation_list[-location.resource.capacity].id] )
            service_ends[vehicle.id] = service_started + service_time

        reservation_list.append( vehicle )
        reservation_list.sort( key = lambda vehicle : service_ends[vehicle.id] )

    # Giờ có thể rời đi không được nhỏ hơn thời gian mô phỏng hiện tại.
    return { vehicle.id : max( model.env.now, service_ends[vehicle.id] ) for vehicle in vehicles }

def calculate_earliest_departure_times( model:Model ):
    # Gom kết quả cho cả đội xe; xe đang di chuyển giữ giá trị None.
    # Mỗi nhà máy chỉ cần tính một lần vì hàm trên xử lý mọi xe ở nhà máy đó.
    departure_times = { vehicle.id : None for vehicle in model.vehicles }

    for vehicle in model.vehicles:
        if not vehicle.is_at_location:
            continue

        if departure_times[vehicle.id] is not None:
            continue # already calculated

        departure_times_at_location = calculate_earliest_departure_times_at_location( model, vehicle.current_visit.location )

        for vehicle_id, departure_time in departure_times_at_location.items():
            departure_times[vehicle_id] = departure_time

    return departure_times

def get_dpdp_state( model:Model ) -> Dict:
    # Chuyển object của simulator thành dictionary dùng cho thuật toán.
    # Chỉ lấy đơn đã xuất hiện trong model, không quét các đơn tương lai
    # nằm trong private_data['orders'].
    state = {
        'vehicle_info':       [],
        'unallocated_orders': [],
        'ongoing_orders':     []
    }

    departure_times = calculate_earliest_departure_times( model )

    for vehicle in model.vehicles:
        expected_arrival_time = 0

        if vehicle.has_next_visit:
            # Xe ở nhà máy: ETA = giờ có thể rời + thời gian đi.
            # Xe đang đi: ETA = giờ đã xuất phát + thời gian của chặng đang đi.
            if vehicle.is_at_location:
                expected_arrival_time = departure_times[vehicle.id] + model.private_data.get( 'travel_times' ).get( (vehicle.current_location.id, vehicle.next_location.id ), 0 )
            else:
                expected_arrival_time = vehicle.previous_visit.departure_time + model.private_data.get( 'travel_times' ).get( ( vehicle.previous_location.id, vehicle.next_location.id ), 0 )

        # carrying_items là hàng sau khi xử lý visit hiện tại, nếu xe ở nhà máy;
        # nếu xe đang đi thì là hàng đang chở. destination là visit kế tiếp.
        # Chuỗi rỗng/0 biểu diễn vị trí, mốc hiện tại không áp dụng khi đang đi;
        # leave_time của destination được đặt 0, chưa dự báo trong hàm này.
        state['vehicle_info'].append( {
            'id':                             vehicle.id,
            'capacity':                       vehicle.capacity,
            'update_time':                    model.env.now,
            'cur_factory_id' :                vehicle.current_visit.location.id  if vehicle.is_at_location else "",
            'arrive_time_at_current_factory': vehicle.current_visit.arrival_time if vehicle.is_at_location else 0,
            'leave_time_at_current_factory':  departure_times[vehicle.id]        if vehicle.is_at_location else 0,
            'carrying_items':                 [ order.id for order in vehicle.loaded_orders_after_current_visit ],
            'destination': {
                'factory_id':         vehicle.next_visit.location.id,
                'delivery_item_list': [ order.id for order in vehicle.next_visit.delivery_list ],
                'pickup_item_list':   [ order.id for order in vehicle.next_visit.pickup_list ],
                'arrive_time':        expected_arrival_time,
                'leave_time':         0
            } if vehicle.has_next_visit else None
        } )

    # Tạo các danh sách riêng để chuyển đổi trạng thái xuất ra cho thuật toán.
    # VNSME còn bổ sung item đã có kế hoạch nhưng chưa pickup trong adapter riêng.
    unallocated_orders = [ order for order in model.open_orders if not order.is_picked_up ]
    ongoing_orders     = list(model.orders_under_delivery)

    # Với xe ở nhà máy, biểu diễn các item như sau khi visit hiện tại hoàn tất:
    # loại item giao tại đây khỏi ongoing, chuyển item lấy tại đây sang ongoing.
    # Chỉ sửa danh sách tạm, không thực hiện pickup/delivery trong simulator.
    for vehicle in model.vehicles:
        if vehicle.is_on_the_way:
            continue

        for order in vehicle.current_visit.delivery_list:
            if order in ongoing_orders:
                ongoing_orders.remove( order )

        for order in vehicle.current_visit.pickup_list:
            if order in unallocated_orders:
                unallocated_orders.remove( order )
                ongoing_orders.append( order )

    # id là mã item, order_id là mã đơn gốc; demand là quantity của riêng item.
    # load_time/unload_time được tính lại theo quantity, đơn vị giây.
    for item in unallocated_orders:
        state['unallocated_orders'].append( {
            'id':                        item.id,
            'order_id':                  item.original_id,
            'demand':                    item.quantity,
            'pickup_factory_id':         item.pickup_location.id,
            'delivery_factory_id':       item.delivery_location.id,
            'creation_time':             item.release_date,
            'committed_completion_time': item.due_date,
            'load_time':                 model.private_data['loading_time'] * item.quantity,
            'unload_time':               model.private_data['unloading_time'] * item.quantity,
        } )
        
    for item in ongoing_orders:
        state['ongoing_orders'].append( {
            'id':                        item.id,
            'order_id':                  item.original_id,
            'demand':                    item.quantity,
            'pickup_factory_id':         item.pickup_location.id,
            'delivery_factory_id':       item.delivery_location.id,
            'creation_time':             item.release_date,
            'committed_completion_time': item.due_date,
            'load_time':                 model.private_data['loading_time'] * item.quantity,
            'unload_time':               model.private_data['unloading_time'] * item.quantity,
        } )

    return state

def remove_old_dpdp_decision( destination_file:str, route_file:str ) -> None:
    # Xóa kết quả lần trước để tránh đọc nhầm kết quả cũ.
    # Code hiện tại bỏ qua mọi lỗi xóa file, kể cả lỗi khác với file không tồn tại.
    try:
        os.remove( os.path.join( destination_file ) )

    except Exception as exc:
        pass

    try:
        os.remove( os.path.join( route_file ) )
                    
    except Exception as exc:
        pass

def write_dpdp_state( state:Dict, vehicle_info_file:str, unallocated_orders_file:str, ongoing_orders_file:str ) -> None:
    # Tách state thành ba file JSON đầu vào cho thuật toán bên ngoài.
    with open( os.path.join( vehicle_info_file ), 'w' ) as jsonfile:
        json.dump( state['vehicle_info'], jsonfile, indent= 2 )

    with open( os.path.join( unallocated_orders_file ), 'w' ) as jsonfile:
        json.dump( state['unallocated_orders'], jsonfile, indent= 2 )

    with open( os.path.join( ongoing_orders_file ), 'w' ) as jsonfile:
        json.dump( state['ongoing_orders'], jsonfile, indent= 2 )

def read_dpdp_decision( destination_file:str, route_file:str ) -> Dict:
    # Đọc hai file đầu ra: điểm đến kế tiếp và phần tuyến tiếp theo của từng xe.
    # Lỗi mở file hoặc JSON không hợp lệ sẽ được truyền lên bên gọi.
    decision = {
        'destinations': {},
        'routes': {}
    }

    with open( os.path.join( destination_file ), 'r' ) as jsonfile:
        decision['destinations'] = json.load( jsonfile )

    with open( os.path.join( route_file ), 'r' ) as jsonfile:
        decision['routes'] = json.load( jsonfile )

    return decision

def transform_dpdp_decision( model:Model, raw_decision:Dict ) -> Dict:
    # Đổi định dạng thuật toán (destinations/routes) sang vehicles/orders
    # mà simulator nhận. Hàm chuyển cấu trúc, không tự tối ưu hay kiểm tra tuyến.
    routes:Dict[str,dict] = { vehicle.id: {} for vehicle in model.vehicles }

    # Destination trở thành phần tử đầu của next_visits; None nghĩa là không có.
    # current_visit=None trong decision nghĩa là không yêu cầu sửa visit hiện tại.
    for vehicle_id, raw_visit in raw_decision['destinations'].items():
        routes[vehicle_id] = {
            'current_visit': None,
            'next_visits':   []
        }

        if raw_visit is None:
            continue

        routes[vehicle_id]['next_visits'].append( {
            'location':      raw_visit['factory_id'],
            'pickup_list':   raw_visit['pickup_item_list'][:],
            'delivery_list': raw_visit['delivery_item_list'][:]
        } )

    # Nối phần tuyến còn lại sau destination. [:] sao chép danh sách ID item.
    for vehicle_id, visits in raw_decision['routes'].items():
        for raw_visit in visits:

            routes[vehicle_id]['next_visits'].append( {
                'location':      raw_visit['factory_id'],
                'pickup_list':   raw_visit['pickup_item_list'][:],
                'delivery_list': raw_visit['delivery_item_list'][:]
            } )

    # Mặc định đánh dấu mọi open order là accepted. Adapter VNSME sẽ điều chỉnh
    # phần orders theo các item thực sự có trong kế hoạch và contract đang dùng.
    return {
        'vehicles': routes,
        'orders': {
            order.id : { 'status': 'accepted' } for order in model.open_orders
        }
    }

def dpdp_module_routing(
    model:Model, state:dict,
    vehicle_info_file:str, unallocated_orders_file:str, ongoing_orders_file:str,
    destination_file:str, route_file:str,
    module_name:str, function_name:str, *args, **kwargs ):
    # Luồng demo: xóa đầu ra cũ -> ghi state -> gọi hàm Python -> đọc và đổi kết quả.
    # module_name/function_name chọn hàm; *args/**kwargs là đối số của hàm đó.
    
    # delete old decision file, if any
    remove_old_dpdp_decision( destination_file, route_file )

    # write state file
    write_dpdp_state( state, vehicle_info_file, unallocated_orders_file, ongoing_orders_file )

    # call external algorithm
    call_module_function( module_name, function_name, *args, **kwargs )

    # read decision
    raw_decision = read_dpdp_decision( destination_file, route_file )

    # transform decision
    decision = transform_dpdp_decision( model, raw_decision )

    return decision

def dpdp_subprocess_routing(
    model:Model, state:dict,
    vehicle_info_file:str, unallocated_orders_file:str, ongoing_orders_file:str,
    destination_file:str, route_file:str,
    algorithm_calling_command ):
    # Cùng quy trình trao đổi JSON, nhưng chạy thuật toán bằng tiến trình ngoài.
    # VNSME V3 hiện dùng adapter riêng, không gọi wrapper này.
    
    # delete old decision file, if any
    remove_old_dpdp_decision( destination_file, route_file )

    # write state file
    write_dpdp_state( state, vehicle_info_file, unallocated_orders_file, ongoing_orders_file )

    # call external algorithm
    call_algorithm_in_subprocess( algorithm_calling_command )

    # read decision
    raw_decision = read_dpdp_decision( destination_file, route_file )

    # transform decision
    decision = transform_dpdp_decision( model, raw_decision )

    return decision
