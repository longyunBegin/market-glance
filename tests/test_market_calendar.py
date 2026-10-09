import unittest
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from market_calendar import early_closes, holidays, is_trading_day, market_status

ET = ZoneInfo("America/New_York")


class MarketCalendarTests(unittest.TestCase):
    def test_2026_recurring_exchange_holidays(self):
        self.assertIn(datetime(2026, 1, 19).date(), holidays(2026))  # MLK Day
        self.assertIn(datetime(2026, 4, 3).date(), holidays(2026))   # Good Friday
        self.assertIn(datetime(2026, 11, 26).date(), holidays(2026)) # Thanksgiving
        self.assertFalse(is_trading_day(datetime(2026, 4, 3).date()))

    def test_new_year_observed_on_previous_year(self):
        self.assertFalse(is_trading_day(datetime(2021, 12, 31).date()))

    def test_holiday_status_and_next_open(self):
        status = market_status(datetime(2026, 11, 26, 10, 0, tzinfo=ET))
        self.assertTrue(status["holiday"])
        self.assertEqual(status["class"], "closed")
        self.assertIn("NYSE假日", status["label"])
        self.assertIn("下次盘前", status["countdown"])
        self.assertIn("2026-11-27T04:00:00", status["next_transition"])

    def test_regular_session_and_early_close(self):
        regular = market_status(datetime(2026, 6, 1, 10, 0, tzinfo=ET))
        self.assertEqual(regular["class"], "open")
        self.assertIn("Regular", regular["label"])
        self.assertIn(datetime(2026, 11, 27).date(), early_closes(2026))
        afternoon = market_status(datetime(2026, 11, 27, 14, 0, tzinfo=ET))
        self.assertEqual(afternoon["class"], "after")
        self.assertIn("提前收市日", afternoon["label"])
        open_session = market_status(datetime(2026, 11, 27, 12, 59, 30, tzinfo=ET))
        self.assertIn("提前收市 0h 01m", open_session["countdown"])

    def test_weekends_are_closed(self):
        status = market_status(datetime(2026, 10, 10, 12, 0, tzinfo=ET))
        self.assertEqual(status["class"], "closed")
        self.assertIn("周末", status["label"])
        self.assertIn("2026-10-12T04:00:00", status["next_transition"])

    def test_before_premarket_and_after_hours_point_to_next_real_session(self):
        before = market_status(datetime(2026, 10, 9, 3, 59, 59, tzinfo=ET))
        self.assertEqual(before["class"], "closed")
        self.assertIn("盘前开始 0h 01m", before["countdown"])
        after = market_status(datetime(2026, 10, 9, 20, 1, tzinfo=ET))
        self.assertEqual(after["class"], "closed")
        self.assertIn("下次盘前", after["countdown"])
        self.assertGreaterEqual((datetime.fromisoformat(after["next_transition"]) -
                                 datetime(2026, 10, 9, 20, 1, tzinfo=ET)).total_seconds(), 0)

    def test_utc_time_is_converted_to_new_york_session(self):
        # 13:30 UTC is 09:30 EDT on this date, exactly the regular open.
        status = market_status(datetime(2026, 10, 9, 13, 30, tzinfo=timezone.utc))
        self.assertEqual(status["class"], "open")
        self.assertIn("2026-10-09T09:30:00-04:00", status["as_of"])


if __name__ == "__main__":
    unittest.main()
