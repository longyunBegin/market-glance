import datetime as dt
import io
import json
import os
import stat
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

import twelvedata_internal as twelve


SAMPLE = {
    "meta": {"symbol": "AAPL", "interval": "1day", "exchange": "NASDAQ"},
    "values": [{"datetime": "2026-10-08", "open": "100.1", "high": "102",
                "low": "99", "close": "101.25", "volume": "1234"}],
    "status": "ok",
}


class FakeClock:
    def __init__(self, value=1_800_000_000):
        self.value = value

    def now(self):
        return self.value

    def sleep(self, seconds):
        self.value += seconds


class TwelveDataInternalTests(unittest.TestCase):
    def test_request_uses_official_time_series_parameters_and_normalizes_values(self):
        response = io.BytesIO(json.dumps(SAMPLE).encode("utf-8"))
        with patch("twelvedata_internal.urllib.request.urlopen", return_value=response) as open_url:
            record = twelve._request_json("AAPL", "1day", 30, "test-token")
        request = open_url.call_args.args[0]
        self.assertIn("/time_series?", request.full_url)
        self.assertIn("symbol=AAPL", request.full_url)
        self.assertIn("interval=1day", request.full_url)
        self.assertIn("outputsize=30", request.full_url)
        self.assertIn("timezone=UTC", request.full_url)
        self.assertIn("apikey=test-token", request.full_url)
        self.assertEqual(record["symbol"], "AAPL")
        self.assertEqual(record["meta"]["exchange"], "NASDAQ")
        self.assertEqual(record["values"][0]["close"], "101.25")

    def test_http_errors_never_echo_api_key_from_request_url(self):
        leaked_url = "https://api.twelvedata.com/time_series?apikey=do-not-leak"
        error = urllib.error.HTTPError(leaked_url, 403, "forbidden", {}, None)
        with patch("twelvedata_internal.urllib.request.urlopen", side_effect=error):
            with self.assertRaises(twelve.TwelveDataError) as raised:
                twelve._request_json("AAPL", "1day", 30, "do-not-leak")
        self.assertNotIn("do-not-leak", str(raised.exception))
        self.assertIn("HTTP 403", str(raised.exception))

    def test_key_file_must_be_user_private(self):
        with tempfile.TemporaryDirectory() as temporary:
            key_file = Path(temporary) / "twelvedata.env"
            key_file.write_text("TWELVE_DATA_API_KEY=local-test-key\n", encoding="utf-8")
            key_file.chmod(0o644)
            with self.assertRaisesRegex(twelve.TwelveDataError, "chmod 600"):
                twelve._read_key_file(key_file)
            key_file.chmod(0o600)
            self.assertEqual(twelve._read_key_file(key_file), "local-test-key")

    def test_state_directory_is_rejected_when_inside_served_app_root(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            app = root / "app"
            app.mkdir()
            with self.assertRaisesRegex(twelve.TwelveDataError, "outside"):
                twelve.private_state_dir(home=root, xdg_state_home=app / "state", app_dir=app)
            self.assertNotIn(str(app), str(twelve.private_state_dir(
                home=root, xdg_state_home=root / "private-state", app_dir=app)))

    def test_collection_writes_only_private_files_and_uses_one_credit_per_symbol(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            app = root / "app"
            state = root / "outside-app" / "twelvedata"
            app.mkdir()
            clock = FakeClock()
            requested = []

            def fake_request(symbol, interval, outputsize, api_key):
                requested.append((symbol, interval, outputsize, api_key))
                return {"symbol": symbol, "interval": interval, "values": SAMPLE["values"]}

            with patch.object(twelve, "BASE", str(app)):
                result = twelve.collect(
                    ["AAPL", "MSFT", "AAPL"], "1day", 30, api_key="test-key",
                    state_dir=state, request_func=fake_request, wait=False,
                    clock=clock.now, sleeper=clock.sleep,
                )
            self.assertEqual(result["saved"], 2)
            self.assertEqual([request[0] for request in requested], ["AAPL", "MSFT"])
            self.assertTrue(all(request[3] == "test-key" for request in requested))
            self.assertFalse(Path(result["path"]).is_relative_to(app))
            self.assertEqual(stat.S_IMODE(state.stat().st_mode), 0o700)
            self.assertEqual(stat.S_IMODE(Path(result["path"]).stat().st_mode), 0o600)
            with open(result["path"], encoding="utf-8") as stream:
                saved = json.load(stream)
            self.assertEqual(set(saved["series"]), {"AAPL|1day", "MSFT|1day"})
            with open(state / "credits.json", encoding="utf-8") as stream:
                ledger = json.load(stream)
            self.assertEqual(ledger["daily_count"], 2)

    def test_collection_waits_before_ninth_request_in_rolling_minute(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            app = root / "app"
            app.mkdir()
            clock = FakeClock()
            called = []

            def fake_request(symbol, interval, outputsize, api_key):
                called.append(symbol)
                return {"values": SAMPLE["values"]}

            with patch.object(twelve, "BASE", str(app)):
                result = twelve.collect(
                    ["S%d" % index for index in range(9)], api_key="test-key",
                    state_dir=root / "state", request_func=fake_request, wait=True,
                    clock=clock.now, sleeper=clock.sleep,
                )
            self.assertEqual(result["saved"], 9)
            self.assertEqual(len(called), 9)
            self.assertGreaterEqual(clock.value, 1_800_000_060)

    def test_local_daily_credit_cap_stops_before_request(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            app = root / "app"
            state = root / "state"
            app.mkdir()
            clock = FakeClock()
            today = dt.datetime.fromtimestamp(clock.value, dt.timezone.utc).date().isoformat()
            state.mkdir()
            (state / "credits.json").write_text(json.dumps({
                "utc_day": today, "daily_count": 800, "recent_timestamps": []
            }), encoding="utf-8")
            request = lambda *args, **kwargs: self.fail("must not make an API request")
            with patch.object(twelve, "BASE", str(app)):
                with self.assertRaisesRegex(twelve.TwelveDataError, "800 requests"):
                    twelve.collect(["AAPL"], api_key="test-key", state_dir=state,
                                   request_func=request, clock=clock.now)

    def test_invalid_symbols_and_interval_are_rejected_without_network(self):
        for symbols, interval in ((["AAPL&apikey=x"], "1day"), (["AAPL"], "2min")):
            with self.subTest(symbols=symbols, interval=interval):
                with self.assertRaises(twelve.TwelveDataError):
                    twelve.collect(symbols, interval, api_key="test-key", state_dir="/tmp/private-test")


if __name__ == "__main__":
    unittest.main()
