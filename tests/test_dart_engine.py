import sys
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from dart_engine import (
    REPORT_ANNUAL,
    REPORT_HALF,
    REPORT_Q1,
    REPORT_Q3,
    calculate_financial_metrics,
    latest_period,
    parse_amount,
    score_item,
)


def statement(account_id, account_name, statement, current, previous=None, prior=None, previous_quarter=None):
    return {
        "account_id": account_id,
        "account_nm": account_name,
        "sj_div": statement,
        "thstrm_amount": current,
        "frmtrm_amount": previous,
        "bfefrmtrm_amount": prior,
        "frmtrm_q_amount": previous_quarter,
    }


class DartPeriodTests(unittest.TestCase):
    def test_amount_parser(self):
        self.assertEqual(parse_amount("1,234"), 1234)
        self.assertEqual(parse_amount("(1,234)"), -1234)
        self.assertIsNone(parse_amount("-"))

    def test_latest_normally_filed_period(self):
        self.assertEqual(latest_period(datetime(2026, 4, 1)), (2025, REPORT_ANNUAL))
        self.assertEqual(latest_period(datetime(2026, 5, 16)), (2026, REPORT_Q1))
        self.assertEqual(latest_period(datetime(2026, 8, 15)), (2026, REPORT_HALF))
        self.assertEqual(latest_period(datetime(2026, 11, 15)), (2026, REPORT_Q3))


class FinancialMetricTests(unittest.TestCase):
    def test_growth_and_roe(self):
        current = [
            statement("ifrs-full_BasicEarningsLossPerShare", "기본주당이익", "IS", "200", previous_quarter="100"),
            statement("ifrs-full_Revenue", "매출액", "IS", "1500", previous_quarter="1000"),
        ]
        annual = [
            statement("ifrs-full_BasicEarningsLossPerShare", "기본주당이익", "IS", "300", "200", "100"),
            statement("ifrs-full_ProfitLoss", "당기순이익", "IS", "120"),
            statement("ifrs-full_Equity", "자본총계", "BS", "1000", "800"),
        ]

        result = calculate_financial_metrics(current, annual)

        self.assertEqual(result["quarterEpsGrowth"], 100)
        self.assertEqual(result["quarterSalesGrowth"], 50)
        self.assertEqual(result["annualEpsGrowth"], 75)
        self.assertEqual(result["annualEpsLatestGrowth"], 50)
        self.assertAlmostEqual(result["roe"], 13.33)

    def test_sepa_and_canslim_score(self):
        item = {
            "trendScore": 8,
            "high52Pct": 98,
            "changePct": 3,
            "volumeRatio50": 2,
            "rs": 90,
            "institutionalAccumulation": True,
        }
        financial = {
            "quarterEpsGrowth": 100,
            "quarterSalesGrowth": 50,
            "annualEpsGrowth": 75,
            "annualEpsLatestGrowth": 50,
            "annualEpsSeries": [300, 200, 100],
            "roe": 20,
        }

        score_item(item, financial, True)

        self.assertEqual(item["canSlimScore"], 11)
        self.assertEqual(item["sepaGrade"], "S")
        self.assertTrue(item["epsExplosion"])
        self.assertTrue(item["financialDataAvailable"])


if __name__ == "__main__":
    unittest.main()
