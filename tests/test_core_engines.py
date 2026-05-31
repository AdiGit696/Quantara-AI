import unittest
from unittest.mock import patch

import pandas as pd

from engines.data_service import resolve_ticker
from engines.basket_engine import prescreen_market_candidates
from engines.risk_engine import calculate_trade_plan
from engines.scoring_engine import build_scorecard, recommendation_from_scores
from portfolio_analyzer import _prepare_portfolio_frame
from providers.manager import DataProviderManager, ProviderUnavailable
from engines.fundamental_analyzer import _first_available, _latest
from engines.formatting import format_metric_value


class FailingProvider:
    name = "failing"

    def get_price(self, *args, **kwargs):
        raise ProviderUnavailable("failed")


class WorkingProvider:
    name = "working"

    def get_price(self, *args, **kwargs):
        return pd.DataFrame({"Open": [1], "High": [2], "Low": [1], "Close": [1.5]})


class CoreEngineTests(unittest.TestCase):
    def test_risk_engine_uses_atr_and_min_rr(self):
        plan = calculate_trade_plan(100, 2, prediction={"future_30": 110, "expected_return_pct": 10})
        self.assertAlmostEqual(plan["stop_loss"], 97.0)
        self.assertAlmostEqual(plan["target"], 105.4)
        self.assertGreaterEqual(plan["risk_reward"], 1.8)

    def test_risk_engine_rejects_oversized_weak_setup(self):
        plan = calculate_trade_plan(100, 9, prediction={"future_30": 101, "expected_return_pct": 1})
        self.assertFalse(plan["is_tradeable"])

    def test_score_mapping_reduces_wait_bias(self):
        scorecard = build_scorecard(
            probability=82,
            uncertainty=14,
            risk_pct=3,
            atr_pct=2,
            risk_reward=2,
            fundamental_score=72,
            expected_return_pct=6,
            trend="Uptrend",
        )
        self.assertIn(
            recommendation_from_scores(scorecard, expected_return_pct=6, risk_reward=2, trend="Uptrend", fundamentals={"score": 72}),
            {"BUY", "STRONG BUY"},
        )

    def test_score_mapping_uses_watch_for_middling_setup(self):
        scorecard = {"confidence_score": 48, "risk_score": 50, "master_score": 48}
        self.assertEqual(recommendation_from_scores(scorecard, expected_return_pct=1, risk_reward=1.1), "WATCH")

    def test_ratio_formatting_is_not_currency(self):
        self.assertEqual(format_metric_value("debt_to_equity", 1.3, ticker="TCS.NS"), "1.30")
        self.assertEqual(format_metric_value("current_ratio", 2, ticker="TCS.NS"), "2.00")
        self.assertEqual(format_metric_value("roe", 14.5, ticker="TCS.NS"), "14.50%")

    def test_portfolio_parser_infers_columns(self):
        frame = pd.DataFrame({"Company Name": ["Infosys Ltd"], "Qty": [2], "Average Cost": [1400]})
        prepared, errors = _prepare_portfolio_frame(frame)
        self.assertFalse(prepared.empty)
        self.assertEqual(list(prepared.columns), ["Ticker", "Quantity", "Buy_Price"])

    def test_provider_failover(self):
        manager = DataProviderManager(providers=[FailingProvider(), WorkingProvider()], retries=1)
        frame = manager.get_price("TEST.NS")
        self.assertFalse(frame.empty)

    @patch("engines.basket_engine._download_chunk")
    def test_prescreen_batches_and_caps_deep_analysis(self, download_chunk):
        history = pd.DataFrame({
            "Close": list(range(100, 140)),
            "Volume": [1000] * 39 + [1500],
        })
        download_chunk.side_effect = lambda tickers, period="3mo": {ticker: history for ticker in tickers}
        candidates = [{"ticker": f"TEST{index}.NS"} for index in range(40)]
        shortlisted = prescreen_market_candidates(candidates, keep_ratio=0.5, max_candidates=12, chunk_size=10, max_workers=2)
        self.assertEqual(len(shortlisted), 12)
        self.assertEqual(download_chunk.call_count, 4)

    def test_fundamental_duplicate_rows_are_scalar_safe(self):
        frame = pd.DataFrame([[100, 90], [120, 110]], index=["Total Revenue", "Total Revenue"])
        series = _first_available(frame, ["Total Revenue"])
        self.assertEqual(_latest(series), 100.0)

    @patch("engines.data_service._ticker_has_recent_prices", return_value=True)
    def test_ticker_resolver_fuzzy_name(self, _):
        universe = [{"ticker": "BHARTIARTL.NS", "symbol": "BHARTIARTL", "name": "Bharti Airtel Limited", "exchange": "NSE"}]
        resolved = resolve_ticker("BHARTI AIRTEL LTD", universe=universe)
        self.assertEqual(resolved["ticker"], "BHARTIARTL.NS")


if __name__ == "__main__":
    unittest.main()
