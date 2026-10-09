import unittest
from datetime import datetime
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
        self.assertIn("11/27", status["countdown"])

    def test_regular_session_and_early_close(self):
        regular = market_status(datetime(2026, 6, 1, 10, 0, tzinfo=ET))
        self.assertEqual(regular["class"], "open")
        self.assertIn("Regular", regular["label"])
        self.assertIn(datetime(2026, 11, 27).date(), early_closes(2026))
        afternoon = market_status(datetime(2026, 11, 27, 14, 0, tzinfo=ET))
        self.assertEqual(afternoon["class"], "")
        self.assertIn("提前收市日", afternoon["label"])

    def test_weekends_are_closed(self):
        status = market_status(datetime(2026, 10, 10, 12, 0, tzinfo=ET))
        self.assertEqual(status["class"], "closed")
        self.assertIn("周末", status["label"])


if __name__ == "__main__":
    unittest.main()
