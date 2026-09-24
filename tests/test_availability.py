import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import search


def row(**seats):
    base = dict(buy='Y', ze='', yw='', yz='', rw='', zy='', sw='', gr='', wz='')
    base.update(seats)
    return base


class AvailabilityTests(unittest.TestCase):
    def test_waitlist_is_not_immediately_buyable(self):
        r = row(ze='候补', zy='0')
        self.assertFalse(search.has_seat(r))
        self.assertEqual(search.row_seats(r), {})

    def test_one_available_seat_is_buyable(self):
        r = row(ze='2')
        self.assertTrue(search.has_seat(r))
        self.assertEqual(search.row_seats(r), {'ze': '2'})

    def test_capacity_requires_enough_tickets_for_people(self):
        self.assertFalse(search.has_seat(row(ze='1'), people=2))
        self.assertTrue(search.has_seat(row(ze='2'), people=2))
        self.assertTrue(search.has_seat(row(ze='有'), people=2))

    def test_capacity_sums_across_classes(self):
        # 1 张二等 + 1 张无座: 两人可分单购买
        self.assertTrue(search.has_seat(row(ze='1', wz='1'), people=2))
        # 不同席别合计不足则不可行
        self.assertFalse(search.has_seat(row(ze='1', yz='1'), people=3))

    def test_not_buyable_flag(self):
        self.assertFalse(search.has_seat(dict(row(ze='有'), buy='N')))


if __name__ == '__main__':
    unittest.main()
