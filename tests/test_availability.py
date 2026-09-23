import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import search


class AvailabilityTests(unittest.TestCase):
    def test_waitlist_is_not_immediately_buyable(self):
        row = dict(buy='Y', ze='候补', yw='无', yz='', rw='', zy='0', sw='', gr='', wz='')
        self.assertFalse(search.has_seat(row))
        self.assertEqual(search.row_seats(row), {})

    def test_one_available_seat_is_buyable(self):
        row = dict(buy='Y', ze='2', yw='无', yz='', rw='', zy='', sw='', gr='', wz='')
        self.assertTrue(search.has_seat(row))
        self.assertEqual(search.row_seats(row), {'ze': '2'})


if __name__ == '__main__':
    unittest.main()
