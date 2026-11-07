
"""Automated tests for data_quality.py."""

import unittest
from datetime import date

from data_quality import (
    check_history,
    required_months_available,
)


def month_id(year, month):
    return year * 12 + month - 1


def make_data(start, end, missing=None):
    """Create synthetic monthly observations."""

    missing = missing or set()
    data = {}

    for month in range(
        month_id(*start),
        month_id(*end) + 1
    ):
        year, index = divmod(month, 12)
        label = f"{year:04d}-{index + 1:02d}"

        if label in missing:
            continue

        data[month] = (
            date(year, index + 1, 1),
            float(month),
        )

    return data


class TestDataQuality(unittest.TestCase):

    def test_complete_history(self):
        data = make_data((2024, 9), (2025, 9))

        status, _ = check_history(
            "UNRATE", data, date(2025, 11, 30)
        )

        self.assertEqual(status, "OK")

    def test_known_missing_unemployment(self):
        data = make_data(
            (2024, 8),
            (2026, 9),
            {"2025-10"},
        )

        status, details = check_history(
            "UNRATE", data, date(2026, 11, 5)
        )

        self.assertEqual(status, "KNOWN_GAP")
        self.assertIn("2025-10", details)

    def test_unexplained_missing_month(self):
        data = make_data(
            (2024, 8),
            (2026, 9),
            {"2025-10"},
        )

        status, _ = check_history(
            "PAYEMS", data, date(2026, 11, 5)
        )

        self.assertEqual(status, "GAP")

    def test_stale_economic_data(self):
        data = make_data(
            (2024, 8),
            (2025, 8),
        )

        status, _ = check_history(
            "PERMIT", data, date(2025, 11, 30)
        )

        self.assertEqual(status, "STALE")

    def test_missing_month_not_interpolated(self):
        data = make_data(
            (2024, 8),
            (2026, 9),
            {"2025-10"},
        )

        # Valid year-over-year comparison
        self.assertTrue(
            required_months_available(
                data,
                [
                    month_id(2025, 9),
                    month_id(2026, 9),
                ],
            )
        )

        # Invalid 3-month average: October is missing
        self.assertFalse(
            required_months_available(
                data,
                [
                    month_id(2025, 9),
                    month_id(2025, 10),
                    month_id(2025, 11),
                ],
            )
        )


if __name__ == "__main__":
    unittest.main()
