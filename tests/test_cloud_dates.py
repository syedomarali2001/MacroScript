"""Regression checks for cloud time-zone rollover and FRED vintage requests."""

import unittest
from datetime import date, datetime, timezone
from unittest.mock import patch

from data_loader import _current_vintage, load_observations
from us_dates import us_today


class FakeFredClient:
    def __init__(self):
        self.calls = []

    def _get_json(self, endpoint, **kwargs):
        self.calls.append((endpoint, kwargs))
        return {"observations": [], "count": 0}


class CloudDatesTest(unittest.TestCase):
    def test_eastern_date_is_still_november_9_after_utc_midnight(self):
        instant = datetime(2026, 11, 10, 0, 30, tzinfo=timezone.utc)
        self.assertEqual(us_today(instant), date(2026, 11, 9))

    def test_eastern_date_uses_dst_in_summer(self):
        instant = datetime(2026, 7, 1, 3, 30, tzinfo=timezone.utc)
        self.assertEqual(us_today(instant), date(2026, 6, 30))

    def test_reject_naive_instant(self):
        with self.assertRaises(ValueError):
            us_today(datetime(2026, 11, 10))

    def test_current_fred_requests_do_not_force_a_vintage(self):
        client = FakeFredClient()
        _current_vintage(client, "UNRATE", date(2026, 11, 9))
        self.assertEqual(len(client.calls), 1)
        _, params = client.calls[0]
        self.assertEqual(params["observation_end"], "2026-11-09")
        self.assertNotIn("realtime_start", params)
        self.assertNotIn("realtime_end", params)

    def test_present_mode_uses_us_date_on_cloud(self):
        client = FakeFredClient()
        with patch("data_loader.us_today", return_value=date(2026, 11, 9)):
            bundle = load_observations(client, "present", "2026-11-09")
        self.assertEqual(bundle["as_of"], "2026-11-09")
        self.assertEqual(bundle["errors"], {})
        self.assertEqual(len(client.calls), 6)
        self.assertTrue(all("realtime_start" not in kwargs for _, kwargs in client.calls))

    def test_future_eastern_date_still_rejected(self):
        with patch("data_loader.us_today", return_value=date(2026, 11, 9)):
            with self.assertRaisesRegex(ValueError, "future"):
                load_observations(FakeFredClient(), "present", "2026-11-10")


if __name__ == "__main__":
    unittest.main()
