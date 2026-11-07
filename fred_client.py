"""Small, reusable FRED API client for V2 (latest observations only)."""

import math
from datetime import date as calendar_date

import requests


class FredError(Exception):
    """A FRED request failed or returned unusable data."""


class FredClient:
    BASE_URL = "https://api.stlouisfed.org/fred"

    def __init__(self, api_key, timeout=15):
        self.api_key = api_key
        self.timeout = timeout
        self.session = requests.Session()  # Reuse the connection across requests.

    def close(self):
        self.session.close()

    def _get_json(self, endpoint, **parameters):
        """Fetch JSON and report safe errors without revealing the API key."""
        parameters.update({"api_key": self.api_key, "file_type": "json"})

        try:
            response = self.session.get(
                f"{self.BASE_URL}/{endpoint}",
                params=parameters,
                timeout=self.timeout,
            )
        except requests.RequestException:
            raise FredError("Network error or request timed out") from None

        if response.status_code != 200:
            # Do not print the request URL: it contains the private API key.
            try:
                message = response.json().get("error_message", "Request rejected")
            except (ValueError, AttributeError):
                message = "Request rejected"
            raise FredError(f"HTTP {response.status_code}: {message}")

        try:
            data = response.json()
        except ValueError:
            raise FredError("FRED did not return valid JSON") from None
        if not isinstance(data, dict):
            raise FredError("Unexpected FRED response format")
        return data

    def get_metadata(self, series_id):
        """Read units, frequency, and FRED's last metadata update date."""
        data = self._get_json("series", series_id=series_id)
        series = data.get("seriess", [])  # FRED spells this JSON field 'seriess'.
        if not isinstance(series, list) or not series:
            raise FredError("Series metadata is missing")
        if series[0].get("id") != series_id:
            raise FredError("Series metadata ID does not match")
        return series[0]

    def check_connection(self):
        """Verify that the key can access a known public FRED series."""
        self.get_metadata("UNRATE")

    def get_latest(self, series_id):
        """Return the newest *numeric* observation and its metadata.

        A recent FRED observation can be '.', meaning missing. We scan
        backwards instead of interpreting missing data as zero.
        """
        metadata = self.get_metadata(series_id)
        data = self._get_json(
            "series/observations",
            series_id=series_id,
            sort_order="desc",
            limit=40,
        )

        observations = data.get("observations", [])
        if not isinstance(observations, list):
            raise FredError("Unexpected observations format")

        for observation in observations:
            raw_value = observation.get("value", ".")
            try:
                value = float(raw_value)
            except (TypeError, ValueError):
                continue
            if not math.isfinite(value):
                continue

            date = observation.get("date")
            if not date:
                continue

            return {
                "value": value,
                "raw_value": str(raw_value),  # Keep FRED's original precision.
                "observation_date": date,
                "age_days": (calendar_date.today() - calendar_date.fromisoformat(date)).days,
                "last_updated": metadata.get("last_updated", "Unknown")[:10],
                "units": metadata.get("units", "Unknown"),
                "frequency": metadata.get("frequency_short", metadata.get("frequency", "Unknown")),
            }

        raise FredError("No numeric observations among the 40 most recent records")
