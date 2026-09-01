import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from rs_engine import has_recent_pocket_pivot, market_cap_size, percentile_scores, range_signals, trend_template_score, weighted_return


class WeightedReturnTests(unittest.TestCase):
    def test_requires_253_closes(self):
        self.assertIsNone(weighted_return([100.0] * 252))

    def test_flat_series_is_zero(self):
        self.assertEqual(weighted_return([100.0] * 253), 0.0)

    def test_recent_move_is_reflected_in_all_overlapping_windows(self):
        closes = [100.0] * 253
        closes[-63:] = [150.0] * 63
        self.assertAlmostEqual(weighted_return(closes), 0.50)


class PercentileTests(unittest.TestCase):
    def test_percentile_range_and_ties(self):
        result = percentile_scores({"A": 1.0, "B": 2.0, "C": 2.0, "D": 4.0})
        self.assertEqual(result["A"], 0)
        self.assertEqual(result["B"], result["C"])
        self.assertEqual(result["D"], 75)


class SignalTests(unittest.TestCase):
    def test_pocket_pivot(self):
        closes = [10, 9, 10, 9, 10, 9, 10, 9, 10, 11, 10, 11, 10, 11, 10, 11, 12, 13]
        volumes = [100] * 17 + [101]
        self.assertTrue(has_recent_pocket_pivot(closes, volumes))

    def test_market_cap_labels(self):
        self.assertEqual(market_cap_size(299_999_999_999), "소형")
        self.assertEqual(market_cap_size(300_000_000_000), "중형")
        self.assertEqual(market_cap_size(1_000_000_000_000), "중대형")
        self.assertEqual(market_cap_size(10_000_000_000_000), "대형")

    def test_perfect_trend_template_scores_eight(self):
        self.assertEqual(trend_template_score(150, 140, 130, 120, 115, 100, 155, 80), 8)

    def test_range_signals_detect_nr7_and_dry_up(self):
        closes = list(range(100, 153))
        highs = [value + 2 for value in closes]
        lows = [value - 2 for value in closes]
        highs[-1], lows[-1] = closes[-1] + 0.5, closes[-1] - 0.5
        volumes = [1000] * 52 + [400]
        result = range_signals(closes, highs, lows, volumes)
        self.assertIn("nr7", result)
        self.assertIn("dryUp", result)


if __name__ == "__main__":
    unittest.main()
