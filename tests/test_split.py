import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import search


class SplitCandidateTests(unittest.TestCase):
    def test_candidates_cover_main_tactics(self):
        seq = ["A", "B", "C", "D", "E", "F"]
        # 实际乘坐 C→E, 售罄
        got = search.split_candidates(seq, 2, 4, max_attempts=8)
        self.assertIn((2, 3), got)          # 买短乘长: 补 E 前一段
        self.assertIn((2, 5), got)          # 买长乘短: 买到终点
        self.assertIn((1, 4), got)          # 前一站买, 保上车站
        for ai, bi in got:
            self.assertTrue(0 <= ai <= 2 < bi <= 5)
            self.assertNotEqual((ai, bi), (2, 4))

    def test_candidates_respect_bounds(self):
        seq = ["A", "B", "C"]
        got = search.split_candidates(seq, 0, 2, max_attempts=8)
        for ai, bi in got:
            self.assertGreaterEqual(ai, 0)
            self.assertLessEqual(bi, 2)
        self.assertNotIn((-1, 2), got)
        self.assertNotIn((0, 0), got)

    def test_classify(self):
        self.assertEqual(search.classify_split(2, 3, 2, 4), "买短乘长")
        self.assertEqual(search.classify_split(2, 5, 2, 4), "买长乘短")
        self.assertEqual(search.classify_split(1, 3, 2, 4), "买长又买短")
        self.assertEqual(search.classify_split(1, 5, 2, 4), "买长乘短")


class ParetoTests(unittest.TestCase):
    @staticmethod
    def plan(price, dur, k, buy_short=False):
        transfers = [{"kind": "同站换乘"}] * k
        return {"price_pp": price, "duration_min": dur, "transfers": transfers,
                "buy_short": {"split": "x"} if buy_short else None}

    def test_dominated_plan_removed(self):
        plans = [self.plan(500, 600, 1), self.plan(520, 620, 1), self.plan(400, 900, 3)]
        kept = search.pareto_filter(plans)
        self.assertIn(plans[0], kept)
        self.assertIn(plans[2], kept)
        self.assertNotIn(plans[1], kept)

    def test_unpriced_never_dominated_by_priced(self):
        cheap_known = self.plan(300, 500, 0)
        unknown = self.plan(None, 900, 2)
        kept = search.pareto_filter([cheap_known, unknown])
        self.assertEqual(kept, [cheap_known, unknown])

    def test_two_unpriced_never_compare(self):
        a = self.plan(None, 900, 2)
        b = self.plan(None, 400, 0)
        self.assertEqual(search.pareto_filter([a, b]), [a, b])

    def test_same_train_segment_not_counted_as_transfer(self):
        p = {"transfers": [{"kind": "同车分段"}, {"kind": "同站换乘"}], "buy_short": None}
        self.assertEqual(search.plan_transfers_k(p), 1)

    def test_equal_plans_both_kept(self):
        a, b = self.plan(500, 600, 1), self.plan(500, 600, 1)
        self.assertEqual(search.pareto_filter([a, b]), [a, b])


if __name__ == '__main__':
    unittest.main()
