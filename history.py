
"""V3.1: Historical FRED observations using point-in-time data."""

import math
from datetime import date

from us_dates import us_today
from decimal import Decimal

from fred_client import FredError


class HistoricalUnavailable(Exception):
    """No historical vintage exists for the requested date."""


# Some indicators were published after their historical data began.
# SAHMREALTIME has observations dating back to 1959, but ALFRED
# vintages of this published series begin in September 2019.

FIRST_HISTORICAL_VINTAGE = {
    "SAHMREALTIME": date(2019, 9, 6),
}


# ======================================
# Retrieve Historical Series
# ======================================

def get_historical_series(client, series_id, as_of_date):
    """
    Get up to five years of observations as known on a chosen date.

    Future data and subsequent revisions are excluded by the
    FRED API's realtime_start and realtime_end parameters.
    """

    as_of = date.fromisoformat(str(as_of_date))

    if as_of > us_today():
        raise ValueError("Historical date cannot be in the future.")

    # Check for indicators that did not have a published vintage yet.
    first_vintage = FIRST_HISTORICAL_VINTAGE.get(series_id)

    if first_vintage and as_of < first_vintage:
        raise HistoricalUnavailable(
            f"ALFRED vintages begin {first_vintage.isoformat()}"
        )

    selected = as_of.isoformat()

    # Five years of observations, for future trend analysis.
    start = f"{max(1776, as_of.year - 5):04d}-01-01"

    try:
        # Historical series metadata
        metadata_response = client._get_json(
            "series",
            series_id=series_id,
            realtime_start=selected,
            realtime_end=selected,
        )

        series_list = metadata_response.get("seriess", [])

        if not series_list or series_list[0].get("id") != series_id:
            raise HistoricalUnavailable(
                "No series metadata for this date"
            )

        metadata = series_list[0]

        # Historical observations, using the selected vintage.
        response = client._get_json(
            "series/observations",
            series_id=series_id,
            realtime_start=selected,
            realtime_end=selected,
            observation_start=start,
            observation_end=selected,
            sort_order="asc",
            limit=100000,
            output_type=1,
        )

    except FredError as error:
        # An absent ALFRED vintage is not a network failure.
        if "does not exist in alfred" in str(error).lower():
            raise HistoricalUnavailable(
                "No ALFRED vintage for this date"
            ) from None

        # Keep genuine API or connection errors visible.
        raise

    raw_observations = response.get("observations", [])

    if not isinstance(raw_observations, list):
        raise FredError("Unexpected historical observations format")

    observations = []

    for entry in raw_observations:

        observation_date = entry.get("date", "")

        if not observation_date or observation_date > selected:
            continue

        raw_value = str(entry.get("value", "."))

        try:
            value = float(raw_value)

            if not math.isfinite(value):
                value = None

        except (ValueError, TypeError):
            value = None

        observations.append({
            "observation_date": observation_date,
            "raw_value": raw_value,
            "value": value,
        })

    if not observations:
        raise HistoricalUnavailable(
            "No observations available on this date"
        )

    return {
        "series_id": series_id,
        "units": metadata.get("units", "Unknown"),
        "frequency": metadata.get(
            "frequency_short",
            metadata.get("frequency", "Unknown")
        ),
        "observations": observations,
    }





# ======================================
# Reconstruct Historical Treasury Spread
# ======================================

def reconstruct_treasury_spread(client, as_of_date):
    """
    Reconstruct T10Y3M using historical DGS10 and DGS3MO.

    Both yields must:
    - Come from the selected historical vintage.
    - Have a valid numerical observation.
    - Refer to the same trading date.
    """

    ten_year = get_historical_series(
        client, "DGS10", as_of_date
    )

    three_month = get_historical_series(
        client, "DGS3MO", as_of_date
    )

    def available_values(series):
        return {
            item["observation_date"]: item["raw_value"]
            for item in series["observations"]
            if item["value"] is not None
        }

    long_yields = available_values(ten_year)
    short_yields = available_values(three_month)

    common_dates = set(long_yields) & set(short_yields)

    if not common_dates:
        raise HistoricalUnavailable(
            "No matching historical Treasury yield dates"
        )

    latest_date = max(common_dates)

    spread = (
        Decimal(long_yields[latest_date])
        - Decimal(short_yields[latest_date])
    )

    return {
        "value": float(spread),
        "raw_value": str(spread),
        "observation_date": latest_date,
        "units": "Percent",
        "frequency": "D",
        "derived": True,
    }



def get_latest_as_of(client, series_id, as_of_date):
    """Retrieve the latest numerical value known on a historical date."""

    try:
        history = get_historical_series(
            client,
            series_id,
            as_of_date
        )

    except HistoricalUnavailable:

        # Reconstruct the Treasury spread using two
        # historically available underlying yield series.
        if series_id == "T10Y3M":
            return reconstruct_treasury_spread(
                client, as_of_date
            )

        raise

    for observation in reversed(history["observations"]):

        if observation["value"] is None:
            continue

        return {
            "value": observation["value"],
            "raw_value": observation["raw_value"],
            "observation_date": observation["observation_date"],
            "units": history["units"],
            "frequency": history["frequency"],
            "derived": False,
        }

    raise HistoricalUnavailable(
        "No valid numerical observations available"
    )
