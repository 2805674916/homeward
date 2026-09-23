import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fares import hydrate


def choose(payload, seats):
    if not payload: return None
    key = 'O' if '二等座' in seats else 'A9' if '商务座' in seats else None
    return payload.get(key) if key else None

class FareReuseTests(unittest.TestCase):
    def test_shared_leg_is_fetched_once(self):
        legs = [dict(train_no='T1', qfrom='01', qto='02', seat_types='O', date='2026-01-01', seats={'二等座':'9'})]
        plans = [{'legs':[legs[0]], 'buy_short':None}, {'legs':[dict(legs[0])], 'buy_short':None}]
        calls=[]
        summary=hydrate(plans, lambda leg: calls.append(leg['train_no']) or {'O':123}, choose, 5, lambda: 5)
        self.assertEqual(calls, ['T1'])
        self.assertEqual(summary['priced_plans'], 2)
        self.assertEqual(plans[0]['price_pp'], 123)

    def test_missing_quote_never_becomes_zero(self):
        leg=dict(train_no='T2', qfrom='01', qto='02', seat_types='O', date='2026-01-01', seats={'商务座':'1'})
        plan={'legs':[leg], 'buy_short':None}
        hydrate([plan], lambda _: {'O':123}, choose, 5, lambda: 5)
        self.assertIsNone(plan['price_pp'])
        self.assertEqual(plan['price_status'], '部分区间待核价')

if __name__ == '__main__': unittest.main()
