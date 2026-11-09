"""Show why the independent guard is needed, using real vehicle execution."""
import unittest
from dpdp_audit_fixtures import build, validate_live_snapshot
from dpdp_feasibility import Infeasible
from dvrpsim import Order
from dvrpsim.exceptions import SimulationError


def two_items(quantity=1, reverse=True):
    m = build()
    v = next(iter(m.vehicles))
    first = next(iter(m.orders))
    first.quantity = quantity
    first.pickup_duration = first.delivery_duration = 240 * quantity
    other = Order('other', original_id='other')
    other.quantity = quantity
    other.pickup_location = first.pickup_location
    other.delivery_location = first.delivery_location
    other.pickup_duration = other.delivery_duration = 240 * quantity
    m._add_order(other)
    other.accept()
    v.next_visits[0].pickup_list.append(other)
    v.next_visits[1].delivery_list = [other, first] if reverse else [first, other]
    return m


class RealExecutionGuards(unittest.TestCase):
    def test_valid_lifo_executes(self):
        m = two_items()
        self.assertTrue(validate_live_snapshot(m))
        m.env.run()
        self.assertTrue(all(o.is_delivered for o in m.orders))

    def test_local_checker_allows_wrong_lifo_independent_guard_catches(self):
        m = two_items(reverse=False)
        v = next(iter(m.vehicles))
        m._check_decision({'vehicles': {v: {'current_visit': None, 'next_visits': v.next_visits}}, 'orders': {}})
        with self.assertRaisesRegex(Infeasible, 'LIFO'):
            validate_live_snapshot(m)
        with self.assertRaisesRegex(SimulationError, 'LIFO'):
            m.env.run()

    def test_intermediate_overload_caught_before_and_during_execution(self):
        m = two_items(quantity=10)
        with self.assertRaisesRegex(Infeasible, 'CAPACITY'):
            validate_live_snapshot(m)
        with self.assertRaisesRegex(SimulationError, 'capacity'):
            m.env.run()


if __name__ == '__main__':
    unittest.main()
