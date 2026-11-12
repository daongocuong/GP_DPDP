import logging
import csv
import random

from typing import Dict

# Ghi chú: Đọc bốn nguồn CSV và ghép thành probdata cho simulator; kiểm tra đường dẫn development trước khi mở dữ liệu.
def read_dpdp_problem( location_file: str, route_file: str, vehice_file: str, order_file: str ) -> dict:
    from dpdp_sealed import require_development_path
    for _path in (location_file, route_file, vehice_file, order_file):
        require_development_path(_path)
    logging.info( 'read problem data...' )

    probdata = {
        'locations': {},
        'orders':    {},
        'vehicles':  {},

        'travel_times': {},
        'distances':    {},

        'docking_time':   1800, # seconds
        'loading_time':   240,  # seconds per order quantity
        'unloading_time': 240,  # seconds per order quantity
    }
    
    __read_locations( probdata, location_file ),
    __read_routes( probdata, route_file ),
    __read_vehicles( probdata, vehice_file ),
    __read_orders( probdata, order_file )
    __set_initial_locations_for_vehicles( probdata )

    logging.info( 'problem data has been read' )

    return probdata

# Ghi chú: Nạp ID nhà máy và số dock; số dock quyết định bao nhiêu xe được phục vụ đồng thời.
def __read_locations( probdata, filename_with_path:str ) -> None:
    with open( filename_with_path, 'r' ) as csvfile:
        csvreader = csv.reader( csvfile, delimiter=',' )
        next( csvreader ) # skip header

        for line in csvreader:
            location = {
                'id':            line[0],
                'docking_ports': int(line[3])
            }
            probdata['locations'][location['id']] = location

# Ghi chú: Nạp quãng đường và thời gian di chuyển theo cặp nhà máy có hướng.
def __read_routes( probdata, filename_with_path:str ) -> None:
    with open( filename_with_path, 'r' ) as csvfile:
        csvreader = csv.reader( csvfile, delimiter=',' )
        next( csvreader ) # skip header

        for line in csvreader:
            probdata['distances'][(line[1],line[2])]    = float(line[3])
            probdata['travel_times'][(line[1],line[2])] = int(line[4])

# Ghi chú: Nạp ID và sức chứa xe; vị trí xuất phát sẽ được gán ở bước riêng.
def __read_vehicles( probdata, filename_with_path:str ) -> None:
    with open( filename_with_path, 'r' ) as csvfile:
        csvreader = csv.reader( csvfile, delimiter=',' )
        next( csvreader ) # skip header

        for line in csvreader:
            vehicle = {
                'id':               line[0],
                'capacity':         int(line[1]),
                'initial_location': None
            }

            probdata['vehicles'][vehicle['id']] = vehicle    

# Ghi chú: Đổi giờ sang giây và tách đơn gốc thành các item nguyên khối 1, 0.5 hoặc 0.25 pallet.
def __read_orders( probdata, filename_with_path:str ) -> None:
    with open( filename_with_path, 'r' ) as csvfile:
        csvreader = csv.reader( csvfile, delimiter=',' )
        next( csvreader ) # skip header

        for line in csvreader:
            _release_date = list(map( int, line[5].split(':') ))
            _due_date     = list(map( int, line[6].split(':') ))

            release_date = _release_date[0] * 3600 + _release_date[1] * 60 + _release_date[2]
            due_date     =     _due_date[0] * 3600 +     _due_date[1] * 60 +     _due_date[2]

            # Ghi chú: Hạn giao nhỏ hơn giờ tạo được hiểu là nằm ở ngày kế tiếp.
            if due_date < release_date: # due date is on the next day
                due_date += 86400

            items = [ 1.0 ] * int(line[1]) + [ 0.5 ] * int(line[2]) + [ 0.25 ] * int(line[3])

            for i in range(len(items)):
                order = {
                    'id':                f'{line[0]}-{i+1}',
                    'original_id':       line[0],
                    'release_date':      release_date,
                    'pickup_location':   line[9],
                    'delivery_location': line[10],
                    'due_date':          due_date,
                    'quantity':          items[i]
                }

                probdata['orders'][order['id']] = order

# Ghi chú: Gán nhà máy xuất phát bằng seed 0 để các lần dựng cùng dữ liệu có cùng vị trí ban đầu.
def __set_initial_locations_for_vehicles( probdata:Dict[str,dict] ) -> None:
    random.seed(0)
    location_list = list(probdata['locations'].values())

    for vehicle in probdata['vehicles'].values():
        index = random.randint(0, len(location_list) - 1)
        vehicle['initial_location'] = location_list[index]['id']
