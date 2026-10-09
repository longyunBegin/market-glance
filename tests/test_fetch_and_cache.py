import os
import json
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


class StaleQuoteTests(unittest.TestCase):
    def test_same_provider_quote_is_retained_and_marked_stale(self):
        previous = {"symbol": "AAPL", "price": 100, "provider": "alpaca_iex",
                    "last_success_at": 500}
        quote = fetch._stale_quote(previous, "AAPL", "Apple", "Watch", "alpaca_iex", 600, "timeout")
        self.assertEqual(quote["price"], 100)
        self.assertTrue(quote["stale"])
        self.assertEqual(quote["stale_since"], 600)
        self.assertEqual(quote["provider"], "alpaca_iex")

    def test_other_provider_quote_is_not_reused(self):
        previous = {"symbol": "SIVE.ST", "price": 100, "provider": "alpaca_iex"}
        quote = fetch._stale_quote(previous, "SIVE.ST", "SIVE", "Watch", "yahoo", 600, "timeout")
        self.assertIsNone(quote["price"])
        self.assertEqual(quote["provider"], "yahoo")
        self.assertTrue(quote["stale"])
        self.assertEqual(quote["error"], "timeout")


class MixedProviderFetchTests(unittest.TestCase):
    def test_fetch_loop_routes_each_symbol_and_requests_only_alpaca_symbols(self):
        with tempfile.TemporaryDirectory() as directory:
            config = {
                "anomaly_threshold_pct": 3.0,
                "fetch_interval_secs": 300,
                "groups": [{"name": "Watch", "tickers": [
                    {"symbol": "AAPL", "name": "Apple"},
                    {"symbol": "SIVE.ST", "name": "SIVE"},
                    {"symbol": "^NDX", "name": "Nasdaq 100"},
                ]}],
            }
            with open(os.path.join(directory, "config.json"), "w", encoding="utf-8") as stream:
                json.dump(config, stream)

            def fake_fetch_one(symbol, name, group, provider, **kwargs):
                return ({"symbol": symbol, "name": name, "group": group,
                         "price": 100.0, "provider": provider}, [[1, 1, 1, 1, 1, 1]])

            with patch.object(fetch, "BASE", directory), \
                    patch("fetch.fetch_latest_trades", return_value={"AAPL": {"p": 100}}) as latest, \
                    patch("fetch.fetch_one", side_effect=fake_fetch_one) as fetch_one, \
                    patch("fetch.time.sleep"), \
                    patch("fetch.time.time", return_value=1000):
                fetch.main(["--force"])

            self.assertEqual(latest.call_args.args[0], ["AAPL"])
            routed = {call.args[0]: call.kwargs["provider"] for call in fetch_one.call_args_list}
            self.assertEqual(routed, {"AAPL": "alpaca_iex", "SIVE.ST": "yahoo", "^NDX": "yahoo"})
            with open(os.path.join(directory, "data", "quotes.json"), encoding="utf-8") as stream:
                snapshot = json.load(stream)
            self.assertEqual({quote["symbol"]: quote["provider"] for quote in snapshot["quotes"]}, routed)


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

    def test_yahoo_intraday_request_includes_premarket_and_keeps_its_bars(self):
        timestamp = int(datetime(2026, 10, 9, 12, 0, tzinfo=timezone.utc).timestamp())
        payload = {"chart": {"result": [{
            "meta": {}, "timestamp": [timestamp],
            "indicators": {"quote": [{"open": [10.0], "high": [10.5],
                "low": [9.8], "close": [10.2], "volume": [25]}]},
        }]}}
        with patch("fetch.get", return_value=payload) as request:
            candles, _ = fetch.fetch_candles("SIVE.ST", "5m", "2d", provider="yahoo")
        self.assertIn("includePrePost=true", request.call_args.args[0])
        self.assertEqual(candles, [[timestamp, 10.0, 10.5, 9.8, 10.2, 25]])

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


class QuoteChangeTests(unittest.TestCase):
    @staticmethod
    def candle(year, month, day, hour, minute, close):
        timestamp = int(datetime(year, month, day, hour, minute,
                                 tzinfo=fetch.ET).timestamp())
        return [timestamp, close, close, close, close, 1]

    def fetch_quote(self, intraday, daily, trade, now):
        def candle_source(symbol, interval, period, provider="yahoo"):
            return (intraday if interval == "5m" else daily), {"provider": provider}

        with patch("fetch.fetch_candles", side_effect=candle_source):
            quote, _ = fetch.fetch_one(
                "AAPL", "Apple", "Watch", provider="alpaca_iex",
                latest_trade=trade, trades_loaded=True, now=now,
            )
        return quote

    @staticmethod
    def trade(price, timestamp):
        return {"p": price, "t": timestamp.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")}

    def test_after_hours_price_keeps_close_to_close_change_through_weekend(self):
        daily = [self.candle(2026, 10, 8, 9, 30, 100),
                 self.candle(2026, 10, 9, 9, 30, 102)]
        latest = datetime(2026, 10, 9, 17, 30, tzinfo=fetch.ET)
        quote = self.fetch_quote(
            [self.candle(2026, 10, 9, 16, 0, 103.02)], daily,
            self.trade(103.02, latest), datetime(2026, 10, 11, 12, 0, tzinfo=fetch.ET),
        )
        self.assertEqual(quote["price"], 103.02)
        self.assertEqual(quote["chg_pct"], 2.0)
        self.assertEqual(quote["prev_close"], 100)
        self.assertEqual(quote["regular_close"], 102)
        self.assertEqual(quote["price_session"], "after")
        self.assertEqual(quote["extended_chg_pct"], 1.0)

    def test_premarket_after_holiday_uses_latest_two_trading_closes(self):
        daily = [self.candle(2026, 11, 24, 9, 30, 100),
                 self.candle(2026, 11, 25, 9, 30, 101)]
        latest = datetime(2026, 11, 27, 8, 0, tzinfo=fetch.ET)
        quote = self.fetch_quote(
            [self.candle(2026, 11, 27, 8, 0, 101.5)], daily,
            self.trade(101.5, latest), datetime(2026, 11, 27, 8, 30, tzinfo=fetch.ET),
        )
        self.assertEqual(quote["chg_pct"], 1.0)
        self.assertEqual(quote["prev_close"], 100)
        self.assertEqual(quote["regular_close"], 101)
        self.assertEqual(quote["price_session"], "pre")
        self.assertEqual(quote["extended_chg_pct"], 0.5)

    def test_live_regular_quote_uses_latest_completed_close_as_baseline(self):
        daily = [self.candle(2026, 10, 8, 9, 30, 100),
                 self.candle(2026, 10, 9, 9, 30, 102)]
        latest = datetime(2026, 10, 9, 10, 30, tzinfo=fetch.ET)
        quote = self.fetch_quote(
            [self.candle(2026, 10, 9, 10, 30, 101)], daily,
            self.trade(101, latest), datetime(2026, 10, 9, 10, 35, tzinfo=fetch.ET),
        )
        self.assertEqual(quote["price_session"], "regular")
        self.assertEqual(quote["regular_close"], 100)
        self.assertEqual(quote["prev_close"], 100)
        self.assertEqual(quote["chg_pct"], 1.0)
        self.assertIsNone(quote["extended_chg_pct"])


if __name__ == "__main__":
    unittest.main()
