import unittest

from config_model import validate_config


BASE = {
    "groups": [{"name": "Watch", "tickers": [{"symbol": "AAPL", "name": "Apple"}]}],
}


class ConfigValidationTests(unittest.TestCase):
    def test_defaults_and_normalization(self):
        config = validate_config(BASE)
        self.assertEqual(config["fetch_interval_secs"], 300)
        self.assertEqual(config["anomaly_threshold_pct"], 3.0)
        self.assertEqual(config["market_data_provider"], "yahoo")
        self.assertEqual(config["www_port"], 8090)
        self.assertEqual(config["groups"][0]["tickers"][0]["symbol"], "AAPL")

    def test_market_data_provider_choices(self):
        self.assertEqual(validate_config({**BASE, "market_data_provider": "alpaca_iex"})[
            "market_data_provider"], "alpaca_iex")
        for invalid in ("alpaca", "sip", None, 1):
            with self.subTest(invalid=invalid):
                with self.assertRaisesRegex(ValueError, "行情数据源"):
                    validate_config({**BASE, "market_data_provider": invalid})

    def test_fetch_interval_range_and_type(self):
        for invalid in (59, 86401, 60.5, True, "300"):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    validate_config({**BASE, "fetch_interval_secs": invalid})
        self.assertEqual(validate_config({**BASE, "fetch_interval_secs": 60})["fetch_interval_secs"], 60)
        self.assertEqual(validate_config({**BASE, "fetch_interval_secs": 86400})["fetch_interval_secs"], 86400)

    def test_threshold_and_port_are_checked(self):
        for field, value in (("anomaly_threshold_pct", 0), ("anomaly_threshold_pct", float("inf")),
                             ("www_port", 80), ("www_port", 65536)):
            with self.subTest(field=field, value=value):
                with self.assertRaises(ValueError):
                    validate_config({**BASE, field: value})

    def test_symbols_are_unique_across_groups(self):
        duplicate = {"groups": [
            {"name": "One", "tickers": [{"symbol": "AAPL"}]},
            {"name": "Two", "tickers": [{"symbol": "aapl"}]},
        ]}
        with self.assertRaisesRegex(ValueError, "重复"):
            validate_config(duplicate)

    def test_labels_are_bounded_and_control_characters_removed(self):
        config = validate_config({"groups": [{"name": "<img>\u0001" + "x" * 40,
                                             "tickers": [{"symbol": "AAPL", "name": "<b>"}]}]})
        self.assertLessEqual(len(config["groups"][0]["name"]), 24)
        self.assertNotIn("\u0001", config["groups"][0]["name"])
        self.assertEqual(config["groups"][0]["tickers"][0]["name"], "<b>")


if __name__ == "__main__":
    unittest.main()
