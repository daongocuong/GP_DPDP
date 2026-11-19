import unittest
from unittest.mock import patch
from dpdp_feasibility import Item, Visit, VehicleState, Plan, Infeasible, validate


def pickup(*ids):
    return Visit('P', pickups=ids)


def delivery(*ids):
    return Visit('Q', deliveries=ids)


def items(a=1, b=1, same_order=False):
    return {'a': Item('o', a, 'P', 'Q', due=-100),
            'b': Item('o' if same_order else 'other', b, 'P', 'Q')}


class FeasibilityAudit(unittest.TestCase):
    def valid(self, its, fleet, plans, **kwargs):
        self.assertTrue(validate(its, fleet, plans, **kwargs))

    def invalid(self, rule, its, fleet, plans, **kwargs):
        with self.assertRaises(Infeasible) as caught:
            validate(its, fleet, plans, **kwargs)
        self.assertEqual(caught.exception.rule, rule)
        message = str(caught.exception)
        for context in ('vehicle=', 'item=', 'step='):
            self.assertIn(context, message)

    def test_exact_capacity_and_lateness_is_soft(self):
        self.valid({'a': Item('o', 15, 'P', 'Q', due=-100)}, {'V': VehicleState(15)},
                   {'V': Plan(future=(pickup('a'), delivery('a')))})

    def test_optional_profile_preserves_validity_and_reconciles_top_level_timers(self):
        its = items()
        fleet = {'V': VehicleState(15)}
        plans = {'V': Plan(future=(pickup('a', 'b'), delivery('b', 'a')))}
        plain = validate(its, fleet, plans)
        profile = {}
        measured = validate(its, fleet, plans, profile=profile)
        self.assertEqual(plain, measured)
        top_level = sum(profile[key] for key in (
            'feasibility_initial_vehicle_scan_seconds',
            'feasibility_vehicle_route_scan_seconds',
            'feasibility_global_checks_seconds'))
        self.assertAlmostEqual(profile['feasibility_validator_total_seconds'], top_level, delta=1e-5)
        for key in ('feasibility_capacity_check_seconds', 'feasibility_lifo_check_seconds',
                    'feasibility_pickup_delivery_seconds', 'feasibility_vehicle_route_scan_seconds'):
            self.assertGreater(profile[key], 0)

    def test_optional_profile_preserves_first_invalid_rule(self):
        its = items(10, 10)
        fleet = {'V': VehicleState(15)}
        plans = {'V': Plan(future=(pickup('a'), pickup('b'), delivery('b'), delivery('a')))}
        outcomes = []
        measured_profile = {}
        for profile in (None, measured_profile):
            try:
                validate(its, fleet, plans, profile=profile)
            except Infeasible as exc:
                outcomes.append((exc.rule, exc.vehicle, exc.item, exc.step))
        self.assertEqual(outcomes, [('CAPACITY', 'V', 'b', 'future[1]/pickup[0]')]*2)
        phases = sum(measured_profile[key] for key in (
            'feasibility_initial_vehicle_scan_seconds',
            'feasibility_vehicle_route_scan_seconds',
            'feasibility_global_checks_seconds'))
        self.assertAlmostEqual(measured_profile['feasibility_validator_total_seconds'], phases, delta=1e-5)

    def test_intermediate_overload_not_hidden_by_final_zero_load(self):
        self.invalid('CAPACITY', items(10, 10), {'V': VehicleState(15)},
                     {'V': Plan(future=(pickup('a'), pickup('b'), delivery('b'), delivery('a')))})

    def test_initial_loaded_stack_valid(self):
        self.valid(items(), {'V': VehicleState(15, carrying=('a', 'b'))},
                   {'V': Plan(future=(delivery('b', 'a'),))})

    def test_initial_overload(self):
        self.invalid('CAPACITY', items(10, 10), {'V': VehicleState(15, carrying=('a', 'b'))},
                     {'V': Plan(future=(delivery('b', 'a'),))})

    def test_delivery_skips_redundant_capacity_sum_but_pickup_still_checks(self):
        its = {'a': Item('oa', 4, 'P', 'Q'), 'b': Item('ob', 6, 'P', 'Q')}
        fleet = {'V': VehicleState(15, carrying=('a',))}
        plans = {'V': Plan(future=(delivery('a'), pickup('b'), delivery('b')))}
        with patch('dpdp_feasibility.sum', wraps=sum, create=True) as summed:
            self.valid(its, fleet, plans)
        # Initial load and the load-increasing pickup are the only required sums.
        self.assertEqual(summed.call_count, 2)

    def test_capacity_first_error_after_delivery_matches_previous_rule(self):
        its = {'a': Item('oa', 1, 'P', 'Q'), 'b': Item('ob', 16, 'P', 'Q')}
        fleet = {'V': VehicleState(15, carrying=('a',))}
        plans = {'V': Plan(future=(delivery('a'), pickup('b'), delivery('b')))}
        with self.assertRaises(Infeasible) as caught:
            validate(its, fleet, plans)
        self.assertEqual((caught.exception.rule, caught.exception.vehicle,
                          caught.exception.item, caught.exception.step),
                         ('CAPACITY', 'V', 'b', 'future[1]/pickup[0]'))
        self.assertEqual(str(caught.exception),
                         'CAPACITY: vehicle=V, item=b, step=future[1]/pickup[0]: load=16, capacity=15')

    def test_initial_duplicate_ownership(self):
        self.invalid('INITIAL_OWNERSHIP', items(),
                     {'V': VehicleState(15, carrying=('a', 'a'))}, {'V': Plan()})

    def test_delivery_before_pickup(self):
        self.invalid('PICKUP_BEFORE_DELIVERY_OR_WRONG_VEHICLE', items(), {'V': VehicleState(15)},
                     {'V': Plan(future=(delivery('a'), pickup('a', 'b'), delivery('b', 'a')))})

    def test_duplicate_pickup_same_visit(self):
        self.invalid('DUPLICATE_OPERATION', items(), {'V': VehicleState(15)},
                     {'V': Plan(future=(pickup('a', 'a'), delivery('a')))})

    def test_duplicate_pickup_later_visit(self):
        self.invalid('DUPLICATE_PICKUP', items(), {'V': VehicleState(15)},
                     {'V': Plan(future=(pickup('a'), pickup('a'), delivery('a')))})

    def test_duplicate_delivery(self):
        self.invalid('DUPLICATE_DELIVERY', {'a': items()['a']}, {'V': VehicleState(15)},
                     {'V': Plan(future=(pickup('a'), delivery('a'), delivery('a')))})

    def test_unknown_item(self):
        self.invalid('UNKNOWN_ITEM', items(), {'V': VehicleState(15)},
                     {'V': Plan(future=(pickup('missing'),))})

    def test_item_cannot_be_fractional_id_or_quantity_override(self):
        self.invalid('UNKNOWN_ITEM', items(), {'V': VehicleState(15)},
                     {'V': Plan(future=(pickup(('a', 0.5)),))})

    def test_wrong_vehicle(self):
        self.invalid('PICKUP_BEFORE_DELIVERY_OR_WRONG_VEHICLE', {'a': items()['a']},
                     {'V2': VehicleState(15), 'V1': VehicleState(15, carrying=('a',))},
                     {'V2': Plan(future=(delivery('a'),)), 'V1': Plan(future=(delivery('a'),))})

    def test_wrong_factory(self):
        self.invalid('FACTORY', items(), {'V': VehicleState(15)},
                     {'V': Plan(future=(Visit('Q', pickups=('a',)),))})

    def test_lifo_within_visit_valid(self):
        self.valid(items(), {'V': VehicleState(15)},
                   {'V': Plan(future=(pickup('a', 'b'), delivery('b', 'a')))})

    def test_lifo_within_visit_invalid(self):
        self.invalid('LIFO', items(), {'V': VehicleState(15)},
                     {'V': Plan(future=(pickup('a', 'b'), delivery('a', 'b')))})

    def test_lifo_across_visits_invalid(self):
        self.invalid('LIFO', items(), {'V': VehicleState(15)},
                     {'V': Plan(future=(pickup('a'), pickup('b'), delivery('a'), delivery('b')))})

    def test_same_visit_unload_then_load_valid(self):
        its = {'a': Item('o', 15, 'X', 'P'), 'b': Item('other', 15, 'P', 'Q')}
        self.valid(its, {'V': VehicleState(15, carrying=('a',))},
                   {'V': Plan(future=(Visit('P', deliveries=('a',), pickups=('b',)), delivery('b')))})

    def test_cannot_pick_then_deliver_in_same_visit(self):
        its = {'a': Item('o', 1, 'P', 'P')}
        self.invalid('PICKUP_BEFORE_DELIVERY_OR_WRONG_VEHICLE', its, {'V': VehicleState(15)},
                     {'V': Plan(future=(Visit('P', deliveries=('a',), pickups=('a',)),))})

    def test_fitting_order_cannot_split_across_vehicles(self):
        self.invalid('ORDER_SPLIT', items(7.5, 7.5, True),
                     {'V1': VehicleState(15), 'V2': VehicleState(15)},
                     {'V1': Plan(future=(pickup('a'), delivery('a'))),
                      'V2': Plan(future=(pickup('b'), delivery('b')))})

    def test_fitting_order_cannot_split_across_pickup_visits(self):
        self.invalid('ORDER_SPLIT', items(1, 1, True), {'V': VehicleState(15)},
                     {'V': Plan(future=(pickup('a'), delivery('a'), pickup('b'), delivery('b')))})

    def test_oversized_order_split_into_feasible_vehicle_groups(self):
        self.valid(items(10, 10, True), {'V1': VehicleState(15), 'V2': VehicleState(15)},
                   {'V1': Plan(future=(pickup('a'), delivery('a'))),
                    'V2': Plan(future=(pickup('b'), delivery('b')))})

    def test_oversized_order_split_on_same_vehicle(self):
        self.valid(items(10, 10, True), {'V': VehicleState(15)},
                   {'V': Plan(future=(pickup('a'), delivery('a'), pickup('b'), delivery('b')))})

    def test_indivisible_oversized_item(self):
        self.invalid('CAPACITY', {'a': Item('o', 16, 'P', 'Q')}, {'V': VehicleState(15)},
                     {'V': Plan(future=(pickup('a'), delivery('a')))})

    def test_changed_destination_factory(self):
        self.invalid('DESTINATION_LOCK', items(),
                     {'V': VehicleState(15, destination=Visit('P', arrival=10))},
                     {'V': Plan(future=(Visit('X', arrival=10),))})

    def test_changed_destination_arrival(self):
        self.invalid('DESTINATION_LOCK', items(),
                     {'V': VehicleState(15, destination=Visit('P', arrival=10))},
                     {'V': Plan(future=(Visit('P', arrival=11),))})

    def test_destination_lists_not_automatically_locked(self):
        destination = Visit('P', pickups=('a',), arrival=10)
        # Original checker fixes factory/time, not pickup/delivery list identity.
        updated = Visit('P', pickups=('a', 'b'), arrival=10)
        self.valid(items(), {'V': VehicleState(15, destination=destination)},
                   {'V': Plan(future=(updated, delivery('b', 'a')))})

    def test_serving_current_lists_unchanged_valid(self):
        cur = pickup('a', 'b')
        self.valid(items(), {'V': VehicleState(15, current=cur, service_started=True)},
                   {'V': Plan(current=cur, future=(delivery('b', 'a'),))})

    def test_serving_current_lists_reordered_invalid(self):
        cur = pickup('a', 'b')
        self.invalid('CURRENT_LOCK', items(), {'V': VehicleState(15, current=cur, service_started=True)},
                     {'V': Plan(current=pickup('b', 'a'), future=(delivery('a', 'b'),))})

    def test_already_executed_current_pickup_not_replayed(self):
        cur = pickup('a', 'b')
        self.valid(items(1, 1, True),
                   {'V': VehicleState(15, carrying=('a',), current=cur, service_started=True)},
                   {'V': Plan(current=cur, future=(delivery('b', 'a'),))})

    def test_already_executed_current_delivery_not_replayed(self):
        cur = delivery('b', 'a')
        self.valid(items(), {'V': VehicleState(15, carrying=('a',), current=cur, service_started=True)},
                   {'V': Plan(current=cur)}, delivered={'b'})

    def test_waiting_current_lists_can_change(self):
        self.valid(items(), {'V': VehicleState(15, current=pickup('a'))},
                   {'V': Plan(current=pickup('a', 'b'), future=(delivery('b', 'a'),))})

    def test_current_factory_cannot_teleport(self):
        self.invalid('CURRENT_LOCATION', items(), {'V': VehicleState(15, current=pickup('a'))},
                     {'V': Plan(current=Visit('X'))})

    def test_future_suffix_can_be_reordered(self):
        fixed = Visit('P', pickups=('a',), arrival=10)
        # Current commitment only covers first destination. Pickup b after delivery a
        # is a legal replacement of the mutable suffix.
        self.valid(items(), {'V': VehicleState(15, destination=fixed)},
                   {'V': Plan(future=(fixed, delivery('a'), pickup('b'), delivery('b')))})

    def test_missing_service(self):
        self.invalid('MISSING_SERVICE', items(), {'V': VehicleState(15)},
                     {'V': Plan(future=(pickup('a'), delivery('a')))})

    def test_missing_vehicle(self):
        self.invalid('FLEET', items(), {'V': VehicleState(15)}, {})

    def test_finished_current_work_stays_committed(self):
        cur = delivery('a')
        self.invalid('CURRENT_LOCK', {'a': items()['a']},
                     {'V': VehicleState(15, current=cur, service_started=True)},
                     {'V': Plan(current=Visit('Q'))}, delivered={'a'})

    def test_same_order_together_in_one_batch_valid(self):
        self.valid(items(7.5, 7.5, True), {'V': VehicleState(15)},
                   {'V': Plan(future=(pickup('a', 'b'), delivery('b', 'a')))})


if __name__ == '__main__':
    unittest.main()
