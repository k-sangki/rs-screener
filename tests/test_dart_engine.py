import sys
import tempfile
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
    load_cached_financials,
    latest_period,
    parse_amount,
    save_cached_financials,
    score_item,
)


def statement(
    account_id,
    account_name,
    statement_type,
    current,
    previous=None,
    prior=None,
    previous_quarter=None,
    current_ytd=None,
    previous_ytd=None,
):
    return {
        "account_id": account_id,
        "account_nm": account_name,
        "sj_div": statement_type,
        "thstrm_amount": current,
        "thstrm_add_amount": current_ytd,
        "frmtrm_amount": previous,
        "frmtrm_add_amount": previous_ytd,
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

    def test_financial_cache_expires_and_changes_with_period(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "dart.json"
            fetched = datetime(2026, 8, 20, 12)
            expected = {"005930": {"quarterEpsGrowth": 30}}
            save_cached_financials(path, fetched, expected)

            self.assertEqual(load_cached_financials(path, datetime(2026, 8, 25, 12)), expected)
            self.assertIsNone(load_cached_financials(path, datetime(2026, 8, 28, 13)))
            self.assertIsNone(load_cached_financials(path, datetime(2026, 11, 15, 12)))
            self.assertEqual(
                load_cached_financials(
                    path,
                    datetime(2026, 11, 15, 12),
                    max_age_days=None,
                    require_current_period=False,
                ),
                expected,
            )


class FinancialMetricTests(unittest.TestCase):
    def test_growth_and_roe(self):
        current = [
            statement("ifrs-full_DilutedEarningsLossPerShare", "희석주당이익", "IS", "200", previous_quarter="100"),
            statement("ifrs-full_Revenue", "매출액", "IS", "1500", previous_quarter="1000"),
            statement("ifrs-full_CashFlowsFromUsedInOperatingActivities", "영업활동현금흐름", "CF", "350", "250"),
            statement("ifrs-full_ProfitLossFromOperatingActivities", "영업이익", "IS", "90", current_ytd="180", previous_ytd="120"),
            statement("ifrs-full_AdjustmentsForDepreciationExpense", "감가상각비", "CF", "40", "30"),
            statement("ifrs-full_AdjustmentsForAmortisationExpense", "무형자산상각비", "CF", "10", "8"),
            statement("ifrs-full_PaymentsToAcquirePropertyPlantAndEquipment", "유형자산의 취득", "CF", "70", "50"),
            statement("ifrs-full_PaymentsToAcquireIntangibleAssets", "무형자산의 취득", "CF", "10", "5"),
            statement("ifrs-full_AdjustmentsForInterestExpense", "이자비용", "CF", "12", current_ytd="20", previous_ytd="15"),
        ]
        annual = [
            statement("ifrs-full_BasicEarningsLossPerShare", "기본주당이익", "IS", "300", "200", "100"),
            statement("ifrs-full_ProfitLoss", "당기순이익", "IS", "120"),
            statement("ifrs-full_Equity", "자본총계", "BS", "1000", "800"),
            statement("ifrs-full_CashFlowsFromUsedInOperatingActivities", "영업활동현금흐름", "CF", "1000"),
            statement("ifrs-full_ProfitLossFromOperatingActivities", "영업이익", "IS", "300"),
            statement("ifrs-full_AdjustmentsForDepreciationExpense", "감가상각비", "CF", "100"),
            statement("ifrs-full_AdjustmentsForAmortisationExpense", "무형자산상각비", "CF", "20"),
            statement("ifrs-full_PaymentsToAcquirePropertyPlantAndEquipment", "유형자산의 취득", "CF", "200"),
            statement("ifrs-full_PaymentsToAcquireIntangibleAssets", "무형자산의 취득", "CF", "30"),
            statement("ifrs-full_AdjustmentsForInterestExpense", "이자비용", "CF", "40"),
        ]

        result = calculate_financial_metrics(current, annual, REPORT_HALF)

        self.assertEqual(result["dilutedEpsGrowthYoY"], 100)
        self.assertEqual(result["revenueGrowthYoY"], 50)
        self.assertEqual(result["annualEpsGrowth"], 75)
        self.assertEqual(result["annualEpsLatestGrowth"], 50)
        self.assertAlmostEqual(result["roe"], 13.33)
        self.assertEqual(result["operatingCashFlowTtm"], 1100)
        self.assertEqual(result["ebitdaCapexInterestCoverageTtm"], 5.27)

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
            "dilutedEpsGrowthYoY": 100,
            "revenueGrowthYoY": 50,
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
