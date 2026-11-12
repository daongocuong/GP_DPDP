# Ghi chú: Thêm thư mục src vào đường tìm module nếu môi trường chưa nhận diện package dvrpsim.
def setup_dvrpsim_import():
    import sys, pathlib, importlib.util

    if importlib.util.find_spec( 'dvrpsim' ) is None:
        source_path = str( pathlib.Path(__file__).resolve().parents[3] / 'src' )
        
        if source_path not in sys.path:
            sys.path.insert(0, source_path)
            
        print( f'module "dvrpsim" will be imported from "{source_path}"' )

setup_dvrpsim_import()

import os

from typing import Dict, List

from dvrpsim import Model, Vehicle, Order, Location, VehicleLoading
from dvrpsim import ModelError

from dvrpsim.utils.order_providers import order_provider
from dvrpsim.utils.routing         import create_directory
from dvrpsim.utils.statistics      import collect_vehicle_statistics, collect_order_statistics, print_statistics
from dvrpsim.utils.updaters        import periodic_updater

from dpdp_problemdata import read_dpdp_problem
from dpdp_routing     import dpdp_module_routing, get_dpdp_state

class DPDPVehicle(Vehicle):
    # Ghi chú: Khởi tạo xe DPDP từ lớp Vehicle của simulator.
    def __init__( self, id:str ) -> None:
        super().__init__(id)

    # Ghi chú: Tra quãng đường giữa hai nhà máy trong probdata; dùng cho thống kê vận chuyển.
    def travel_distance( self, origin, destination ):
        return self.model.private_data.get( 'distances' ).get( ( origin.id, destination.id ), 0 )
    
    # Ghi chú: Tra thời gian đi đường để simulator lên lịch sự kiện xe đến nơi.
    def travel_time( self, origin, destination ):
        return self.model.private_data.get( 'travel_times' ).get( ( origin.id, destination.id ), 0 )

    # Ghi chú: Chờ thời gian docking rồi thực hiện quy trình dỡ/nạp hàng của Vehicle.
    def _service(self):
        # docking
        yield self.model.env.medium_timeout( self.model.private_data.get( 'docking_time' ) )

        # default service procedure
        yield self.model.env.process( super()._service() )

    # Ghi chú: Gán thời điểm hoàn thành giao hàng bằng lúc đến nhà máy, trước chờ dock và dỡ hàng, theo định nghĩa điểm J.
    def on_service_finish(self):
        # adjust delivery times
        for order in self.current_visit.delivery_list:
            order.delivery_time = self.current_visit.arrival_time
            self.model.log.custom( f'delivery time of order {order} has been set to {order.delivery_time}', vehicle= self )

    # Ghi chú: Tính danh sách hàng trên xe sau visit hiện tại bằng bản sao, không sửa tải thực của xe.
    @property
    def loaded_orders_after_current_visit(self) -> List[Order]:
        after_list = self.carrying_orders[:]
        
        if self.is_on_the_way:
            return after_list
        
        for order in self.current_visit.delivery_list:
            if order in after_list:
                after_list.remove(order)

        for order in self.current_visit.pickup_list:
            if order not in after_list:
                after_list.append(order)

        return after_list

class DPDPModel(Model):
    # Ghi chú: Khởi tạo model DPDP dựa trên bộ máy mô phỏng sự kiện của Model.
    def __init__(self):
        super().__init__()

    # Ghi chú: Chuyển trạng thái simulator sang cấu trúc dữ liệu mà thuật toán định tuyến sử dụng.
    def get_state(self):
        return get_dpdp_state(self)

    # Ghi chú: Tạo thư mục trao đổi JSON cho callback demo dùng giao tiếp qua file.
    def init(self):
        # create data interaction directory for file-based routing
        interaction_directory = os.path.join( os.path.dirname( __file__ ), 'routing', 'data_interaction' )
        self.log.info( f'(initialization) creating data interaction directory "{interaction_directory}"' )
        create_directory( interaction_directory )

    # Ghi chú: Xuất trạng thái, gọi thuật toán demo rồi chuyển kết quả về decision của simulator.
    def routing_callback(self):
        interaction_directory   = os.path.join( os.path.dirname( __file__ ), 'routing', 'data_interaction' )
        vehicle_info_file       = os.path.join( interaction_directory, 'vehicle_info.json' )
        ongoing_orders_file     = os.path.join( interaction_directory, 'ongoing_order_items.json' )
        unallocated_orders_file = os.path.join( interaction_directory, 'unallocated_order_items.json' )
        destination_file        = os.path.join( interaction_directory, 'output_destination.json' )
        routes_file             = os.path.join( interaction_directory, 'output_route.json' )

        state = self.get_state()
        
        decision = dpdp_module_routing(
            self, state,
            vehicle_info_file, unallocated_orders_file, ongoing_orders_file, destination_file, routes_file,
            'routing.demo_algorithm', 'routing', vehicle_info_file, ongoing_orders_file, unallocated_orders_file, destination_file, routes_file
        )

        return decision

# Ghi chú: Dựng model từ probdata: tạo nhà máy/dock, lên lịch release đơn, tạo xe LIFO và quyết định mỗi 600 giây.
def build_dpdp_model( probdata:Dict[str,dict] ) -> Model:
    # create model
    model = DPDPModel()

    # set problem data
    model.private_data = probdata

    # create and add locations
    for location_id, location_data in probdata['locations'].items():
        location          = Location( location_id )
        location.resource = model.create_resource( capacity= location_data['docking_ports'] )

        model.add_location( location )

    # create and request orders
    orders = []

    for order_id, order_data in probdata['orders'].items():        
        order = Order( order_data['id'] )

        order.original_id       = order_data['original_id']
        order.quantity          = order_data['quantity']
        order.release_date      = order_data['release_date']
        order.due_date          = order_data['due_date']
        order.pickup_location   = model.get_location_by_id( order_data['pickup_location'] )
        order.delivery_location = model.get_location_by_id( order_data['delivery_location'] )
        order.pickup_duration   = probdata['loading_time']   * order.quantity
        order.delivery_duration = probdata['unloading_time'] * order.quantity

        if order.pickup_location is None:
            raise ModelError( f'unknown pickup location for order {order}: {order_data["pickup_location"]}' )

        if order.delivery_location is None:
            raise ModelError( f'unknown delivery location for order {order}: {order_data["delivery_location"]}' )                

        orders.append( order )

    # Ghi chú: Đơn chỉ xuất hiện khi tới release_date; release không tự gọi định tuyến ngay.
    model.env.process( order_provider( model, orders, decision_point_on_request= False ) )

    # create and add vehicles
    for vehicle_id, vehicle_data in probdata['vehicles'].items():        
        vehicle = DPDPVehicle( vehicle_id )

        vehicle.capacity         = vehicle_data['capacity']
        vehicle.initial_location = model.get_location_by_id( vehicle_data['initial_location'] )
        vehicle.loading_rule     = VehicleLoading.LIFO

        if vehicle.initial_location is None:
            raise ModelError( f'unknown initial location for vehicle {vehicle}: {vehicle_data["initial_location"]}' )
        
        model.add_vehicle( vehicle )

    # decision points in every 10 minutes
    # Ghi chú: Cứ 600 giây mô phỏng mới có một kỳ quyết định, kể cả sau khi đơn cuối đã release.
    model.env.process( periodic_updater( model, 600, stop_after_last_order_request= False ) )

    return model

if __name__ == '__main__':
    data_folder    = os.path.join( os.path.dirname( __file__ ), 'data' )
    data_factories = os.path.join( data_folder, 'factory_info.csv' )
    data_routes    = os.path.join( data_folder, 'route_info.csv' )
    
    # first example
    instance_folder   = os.path.join( data_folder,     'instance_1' )
    instance_vehicles = os.path.join( instance_folder, 'vehicle_info_5.csv' )
    instance_orders   = os.path.join( instance_folder, '50_1.csv' )
    
    # # second example
    # instance_folder   = os.path.join( data_folder,     'instance_17' )
    # instance_vehicles = os.path.join( instance_folder, 'vehicle_info_20.csv' )
    # instance_orders   = os.path.join( instance_folder, '300_1.csv' )
    
    probdata = read_dpdp_problem( data_factories, data_routes, instance_vehicles, instance_orders )
    model = build_dpdp_model( probdata )
    model.run()
    
    print_statistics( collect_vehicle_statistics( model ), header= 'vehicle' )
    print_statistics( collect_order_statistics( model ), header= 'order', onebyone= False )
