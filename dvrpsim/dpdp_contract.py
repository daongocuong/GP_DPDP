"""Versioned DPDP service promises, tentative plans, and execution commitments.

The legacy accepted-route contract remains the default. The opt-in v3 contract
keeps every observed request until delivered; acceptance does not freeze an
unpicked assignment. Complete published routes must still serve all physical
work, and current service/destination constraints use the unchanged validator.
"""
from dataclasses import replace
from decimal import Decimal
import hashlib
import json
from pathlib import Path

from dpdp_feasibility import Plan, Visit

LEGACY_CONTRACT = 'dpdp-accepted-route-v2'
EXECUTION_CONTRACT = 'dpdp-execution-commitment-v3'
CONTRACT_VERSIONS = (LEGACY_CONTRACT, EXECUTION_CONTRACT)
PROTOCOL = Path(__file__).resolve().parent/'protocols/dpdp_execution_commitment_v3.json'


class CommitmentError(ValueError):
    pass


# Ghi chú: Xác định contract V2/V3; với V3 kiểm checksum protocol trước khi trả metadata.
def contract_metadata(version):
    if version not in CONTRACT_VERSIONS:
        raise CommitmentError(f'unknown DPDP contract: {version}')
    result = dict(contract_version=version)
    if version == EXECUTION_CONTRACT:
        content = PROTOCOL.read_bytes()
        digest = hashlib.sha256(content).hexdigest()
        if digest != PROTOCOL.with_suffix(PROTOCOL.suffix+'.sha256').read_text().strip():
            raise CommitmentError('execution contract protocol checksum mismatch')
        descriptor = json.loads(content)
        if descriptor['contract_version'] != version:
            raise CommitmentError('execution contract version mismatch')
        result.update(contract_protocol=str(PROTOCOL), contract_protocol_sha256=digest)
    return result


# Ghi chú: Đổi decision thô thành Plan; giữ công việc hiện tại và ETA của destination đã khóa.
def plans_from_raw(snapshot, raw):
    """The runner's existing conversion, preserving current work and locked ETA."""
    plans = {}
    for vehicle, plan in snapshot.plans.items():
        decision = raw['vehicles'].get(vehicle)
        if decision is None or decision.get('next_visits') is None:
            plans[vehicle] = plan
            continue
        route = tuple(Visit(node['location'], tuple(node.get('delivery_list', [])),
                            tuple(node.get('pickup_list', []))) for node in decision['next_visits'])
        locked = snapshot.fleet[vehicle].destination
        if locked and route and route[0].factory == locked.factory:
            route = (replace(route[0], arrival=locked.arrival),) + route[1:]
        if decision.get('current_visit') is not None:
            raise CommitmentError('runner policies must preserve current work')
        plans[vehicle] = Plan(plan.current, route)
    return plans


class ExecutionCommitment:
    """Account for all requests across epochs; never create a vehicle route.

    check() is pure so a policy can validate before returning a decision.
    record() is called once by the shared runner guard. No order status is
    changed here. Simulator acceptance remains irreversible, as before.
    """
    version = EXECUTION_CONTRACT

    # Ghi chú: Tạo sổ theo dõi yêu cầu, lời hứa phục vụ, hàng đã pickup/giao và lịch sử qua các kỳ.
    def __init__(self):
        self.requests = {}
        self.promised = set()
        self.picked = {}
        self.delivered = set()
        self.history = []
        self.completed = False
        self.terminal_state = None

    # Ghi chú: Chụp thuộc tính bất biến của item để phát hiện yêu cầu bị sửa giữa các kỳ.
    @staticmethod
    def spec(order):
        return (order.original_id, str(Decimal(str(order.quantity))),
                order.pickup_location.id, order.delivery_location.id,
                order.release_date, order.due_date)

    # Ghi chú: Kiểm cam kết mà không cập nhật sổ: mọi item đã thấy phải được hạch toán và hàng đã pickup phải giữ đúng chủ xe.
    def check(self, snapshot, raw, plans=None):
        if self.completed:
            raise CommitmentError('contract already finalized')
        if self.history and snapshot.now < self.history[-1]['simulation_seconds']:
            raise CommitmentError('TIME_REVERSED')
        objects = snapshot.objects
        universe = set(objects)
        if not set(self.requests) <= universe:
            raise CommitmentError('REQUEST_LOSS: previously observed item disappeared')
        for i, order in objects.items():
            if i in self.requests and self.spec(order) != self.requests[i]:
                raise CommitmentError(f'REQUEST_CHANGED: {i}')
            if order.release_date > snapshot.now:
                raise CommitmentError(f'UNRELEASED_ITEM: {i}')
            if order.is_rejected or order.is_canceled:
                raise CommitmentError(f'SERVICE_PROMISE_CANCELLED: {i}')
            if i in self.promised and not order.is_accepted:
                raise CommitmentError(f'ACCEPTANCE_REVERSED: {i}')
            if i in self.delivered and not order.is_delivered:
                raise CommitmentError(f'DELIVERY_REVERSED: {i}')
            if i in self.picked:
                actual = (order.pickup_vehicle.id if order.pickup_vehicle else None, order.pickup_time)
                if not order.is_picked_up or actual != self.picked[i]:
                    raise CommitmentError(f'PHYSICAL_OWNERSHIP_CHANGED: {i}')
        physical_owners = {i: v for v, state in snapshot.fleet.items() for i in state.carrying}
        for i, order in objects.items():
            if order.is_under_delivery and physical_owners.get(i) != (
                    order.pickup_vehicle.id if order.pickup_vehicle else None):
                raise CommitmentError(f'PHYSICAL_STACK_MISSING_OR_WRONG_OWNER: {i}')
        if set(raw['vehicles']) - set(snapshot.fleet):
            raise CommitmentError('UNKNOWN_VEHICLE')
        if any(d is not None and d.get('current_visit') is not None for d in raw['vehicles'].values()):
            raise CommitmentError('runner policies must preserve current work')
        newly_accepted = set()
        for i, decision in raw['orders'].items():
            if i not in universe:
                raise CommitmentError(f'UNKNOWN_REQUEST: {i}')
            if decision['status'] != 'accepted':
                raise CommitmentError(f'SERVICE_PROMISE_CANCELLED: {i}')
            if objects[i].is_delivered:
                raise CommitmentError(f'ACCEPT_DELIVERED: {i}')
            newly_accepted.add(i)
        plans = plans_from_raw(snapshot, raw) if plans is None else plans
        admitted = snapshot.admitted(plans)
        # This complete-plan validator is unchanged: no published item or
        # physically committed load can lack its remaining service.
        snapshot.check(plans, admitted)
        if not newly_accepted <= admitted:
            raise CommitmentError('accepted item missing from returned plan')
        delivered = set(snapshot.delivered)
        required = set()
        for state in snapshot.fleet.values():
            required.update(state.carrying)
            if state.current:
                required.update(state.current.pickups)
                required.update(state.current.deliveries)
        committed = required - delivered
        if not committed <= admitted:
            raise CommitmentError('COMMITTED_SERVICE_MISSING')
        # Ghi chú: Phân biệt tuyến dự kiến với hàng đã cam kết thực hiện; item chưa pickup có thể còn tentative.
        tentative = admitted - delivered - committed
        # Ghi chú: Yêu cầu chưa đưa lên tuyến vẫn nằm trong ledger dưới trạng thái pending, không bị bỏ khỏi nghĩa vụ phục vụ.
        pending = universe - delivered - committed - tentative
        if any(objects[i].is_picked_up for i in pending):
            raise CommitmentError('PICKED_ITEM_PENDING')
        states = dict(delivered=delivered, committed=committed, tentative=tentative, pending=pending)
        # A fitting original order cannot be divided between publication and
        # pending work, then picked in separate batches across later epochs.
        capacity = Decimal(str(next(iter(snapshot.fleet.values())).capacity))
        groups = {}
        for i, item in snapshot.items.items():
            groups.setdefault(item.order, set()).add(i)
        for order, ids in groups.items():
            if Decimal(str(snapshot.demands[order])) <= capacity and ids & pending and ids - pending:
                raise CommitmentError(f'ORDER_SPLIT: fitting order partly omitted: {order}')
        members = [i for ids in states.values() for i in ids]
        if len(members) != len(set(members)) or set(members) != universe:
            raise CommitmentError('REQUEST_ACCOUNTING: each request must occur exactly once')
        return dict(simulation_seconds=snapshot.now, observed_items=len(universe),
                    states={k: sorted(v) for k, v in states.items()},
                    promised_items=sorted(self.promised | newly_accepted |
                                          {i for i, o in objects.items() if o.is_accepted}))

    # Ghi chú: Sau khi check thành công, cập nhật sổ yêu cầu và lịch sử cam kết một lần cho decision.
    def record(self, snapshot, raw, plans=None):
        event = self.check(snapshot, raw, plans)
        for i, order in snapshot.objects.items():
            self.requests.setdefault(i, self.spec(order))
            if order.is_picked_up:
                self.picked[i] = (order.pickup_vehicle.id, order.pickup_time)
        self.promised.update(event['promised_items'])
        self.delivered.update(snapshot.delivered)
        self.history.append(event)
        return event

    # Ghi chú: Cổng kết thúc: chỉ công nhận hoàn tất khi toàn bộ item đầu vào đã xuất hiện và được giao.
    def finish(self, snapshot, expected_items):
        """Only the end-of-run gate may consult the complete input item set."""
        if set(snapshot.objects) != set(expected_items) or set(self.requests) != set(expected_items):
            raise CommitmentError('INCOMPLETE_REQUEST_UNIVERSE')
        if set(snapshot.delivered) != set(expected_items):
            raise CommitmentError('INCOMPLETE_SERVICE: pending work cannot receive a final score')
        # Recheck immutable requests, physical history and acceptance even when
        # no further dispatch is needed after the final delivery.
        self.terminal_state = self.check(snapshot, {'vehicles': {}, 'orders': {}})
        self.delivered.update(snapshot.delivered)
        self.completed = True

    # Ghi chú: Xuất sổ cam kết sang dữ liệu JSON để audit lại sau rollout.
    def export(self):
        return dict(contract_version=self.version, complete=self.completed,
                    requests={i: list(spec) for i, spec in self.requests.items()},
                    promised_items=sorted(self.promised), picked={i: list(v) for i, v in self.picked.items()},
                    delivered_items=sorted(self.delivered), history=self.history, terminal_state=self.terminal_state)
