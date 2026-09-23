import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import search


def leg(no, fr, to, dep, arr, lishi='01:00'):
    return {'train_no': no, 'train': no, 'from': fr, 'to': to, 'from_cn': fr, 'to_cn': to,
            'dep': dep, 'arr': arr, 'lishi': lishi, 'seats': {'二等座': '2'},
            'qfrom': '01', 'qto': '02', 'seat_types': 'O'}


CL = {'CSN': ('CSN', 'CS'), 'CS': ('CSN', 'CS')}


class TransferModelTests(unittest.TestCase):
    def kind_of(self, legs):
        plan = search.make_plan('中转', legs, ['2026-09-30', '2026-09-30'], city_cluster=CL)
        return plan['transfers'][0]['kind'] if plan else None

    def test_cross_station_same_city(self):
        self.assertEqual(self.kind_of(
            [leg('T1', 'A', 'CSN', '08:00', '09:00'), leg('T2', 'CS', 'C', '09:45', '11:00')]), '跨站换乘')

    def test_same_station(self):
        self.assertEqual(self.kind_of(
            [leg('T1', 'A', 'CSN', '08:00', '09:00'), leg('T2', 'CSN', 'C', '09:45', '11:00')]), '同站换乘')

    def test_same_train_segment(self):
        self.assertEqual(self.kind_of(
            [leg('T1', 'A', 'B', '08:00', '09:00'), leg('T1', 'B', 'C', '09:05', '10:00')]), '同车分段')

    def test_unreachable_city_rejected(self):
        self.assertIsNone(self.kind_of(
            [leg('T1', 'A', 'B', '08:00', '09:00'), leg('T2', 'X', 'C', '09:45', '11:00')]))

    def test_cluster_builder(self):
        clusters = search.build_city_clusters({'长沙': [('长沙', 'CS'), ('长沙南', 'CSN')]})
        self.assertEqual(clusters.get('CSN'), ('CS', 'CSN'))


if __name__ == '__main__':
    unittest.main()
