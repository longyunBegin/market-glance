import os
import tempfile
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

import alpaca_data
import fetch
from fetch import fetch_is_due
from server import cache_is_fresh


class FetchIntervalTests(unittest.TestCase):
    def test_fetch_interval_uses_configured_seconds(self):
        self.assertTrue(fetch_is_due(300, None, now=1000))
        self.assertFalse(fetch_is_due(300, 800, now=1000))
        self.assertTrue(fetch_is_due(300, 700, now=1000))
        self.assertTrue(fetch_is_due(60, 900, now=1000))


class KlineCacheTests(unittest.TestCase):
    def test_cache_ttl_expires_and_missing_files_are_stale(self):
        with tempfile.NamedTemporaryFile(delete=False) as stream:
            path = stream.name
        try:
            os.utime(path, (1000, 1000))
            self.assertTrue(cache_is_fresh(path, 900, now=1899))
            self.assertFalse(cache_is_fresh(path, 900, now=1900))
            self.assertFalse(cache_is_fresh(path, 900, now=999))
        finally:
            os.unlink(path)
        self.assertFalse(cache_is_fresh(path, 60, now=1000))

    def test_alpaca_cache_is_separate_from_legacy_yahoo_cache(self):
        yahoo = fetch.kline_cache_path("/tmp/klines", "AAPL", "5m", "yahoo")
        alpaca = fetch.kline_cache_path("/tmp/klines", "AAPL", "5m", "alpaca_iex")
        self.assertEqual(yahoo, "/tmp/klines/AAPL.json")
        self.assertEqual(alpaca, "/tmp/klines/alpaca_iex/AAPL.json")


class AlpacaDataTests(unittest.TestCase):
    def test_missing_credentials_fail_without_network_access(self):
        with patch.dict(os.environ, {"APCA_API_KEY_ID": "", "APCA_API_SECRET_KEY": ""}):
            with self.assertRaisesRegex(RuntimeError, "APCA_API_KEY_ID"):
                alpaca_data._request_json("/v2/stocks/trades/latest", {})

    def test_latest_trades_uses_explicit_iex_feed_and_deduplicates_symbols(self):
        with patch("alpaca_data._request_json", return_value={"trades": {"AAPL": {"p": 123}}}) as request:
            result = alpaca_data.fetch_latest_trades(["AAPL", "MSFT", "AAPL"])
        self.assertEqual(result["AAPL"]["p"], 123)
        self.assertEqual(request.call_args.args[0], "/v2/stocks/trades/latest")
        self.assertEqual(request.call_args.args[1], {"symbols": "AAPL,MSFT", "feed": "iex"})

    def test_historical_bars_use_explicit_iex_feed(self):
        with patch("alpaca_data._request_json", return_value={"bars": []}) as request:
            self.assertEqual(alpaca_data.fetch_bars("AAPL", "5Min", "start", "end"), [])
        self.assertEqual(request.call_args.args[0], "/v2/stocks/AAPL/bars")
        self.assertEqual(request.call_args.args[1]["feed"], "iex")
        self.assertEqual(request.call_args.args[1]["limit"], 10000)

    def test_alpaca_bars_converts_to_chart_candles(self):
        bar = {"t": "2026-10-08T14:30:00Z", "o": 10.1, "h": 11.2,
               "l": 9.8, "c": 10.9, "v": 42}
        with patch("fetch.fetch_alpaca_bars", return_value=[bar]) as request:
            candles, metadata = fetch.fetch_candles("AAPL", "5m", "2d", provider="alpaca_iex")
        expected_timestamp = int(datetime(2026, 10, 8, 14, 30, tzinfo=timezone.utc).timestamp())
        self.assertEqual(candles, [[expected_timestamp, 10.1, 11.2, 9.8, 10.9, 42]])
        self.assertEqual(metadata["provider"], "alpaca_iex")
        self.assertEqual(request.call_args.args[:2], ("AAPL", "5Min"))
        self.assertTrue(request.call_args.args[2].endswith("Z"))

    def test_alpaca_latest_trade_sets_dashboard_quote_price(self):
        bars = [[1, 99, 102, 98, 100, 10]]
        with patch("fetch.fetch_candles", return_value=(bars, {})):
            quote, returned_bars = fetch.fetch_one(
                "AAPL", "Apple", "Watch", provider="alpaca_iex",
                latest_trade={"p": 105.126}, trades_loaded=True,
            )
        self.assertEqual(quote["price"], 105.13)
        self.assertEqual(quote["provider"], "alpaca_iex")
        self.assertEqual(returned_bars, bars)


if __name__ == "__main__":
    unittest.main()
