
"""V4: Load economic observations for three data modes.

present      = current FRED vintage
time_machine = ALFRED vintage on a historical date
research     = today's revised data about a historical period
"""

from datetime import date
import math

from data_quality import check_history
from fred_client import FredError
from history import HistoricalUnavailable, get_historical_series


SERIES_IDS = (
    "UNRATE",
    "PAYEMS",
    "INDPRO",
    "PERMIT",
    "GS10",
    "TB3MS",
)

MODES = ("present", "time_machine", "research")


# ======================================
# 1. Validate Date
# ======================================

def _parse_date(value):
    if value is None:
        return date.today()

    selected = date.fromisoformat(str(value))

    if selected > date.today():
        raise ValueError("Snapshot date cannot be in the future")

    return selected


# ======================================
# 2. Clean FRED Observations
# ======================================

def _clean_observations(raw_observations, cutoff):
    """Keep dates, numeric values, and explicit missing data."""

    clean = []

    for item in raw_observations:

        raw_date = item.get(
            "observation_date",
            item.get("date")
        )

        if not raw_date:
            continue

        try:
            observed = date.fromisoformat(
                str(raw_date)[:10]
            )
        except ValueError:
            continue

        if observed > cutoff:
            continue

        raw_value = item.get("value")

        try:
            number = float(raw_value)

            if not math.isfinite(number):
                number = None

        except (ValueError, TypeError):
            number = None

        clean.append({
            "observation_date": observed.isoformat(),
            "value": number,
        })

    return clean


# ======================================
# 3. Current / Retrospective Data
# ======================================

def _current_vintage(client, series_id, as_of_date):
    """Retrieve today's revised data, up to the selected date."""

    today = date.today().isoformat()

    start = (
        f"{max(1776, as_of_date.year - 5):04d}-01-01"
    )

    response = client._get_json(
        "series/observations",
        series_id=series_id,
        realtime_start=today,
        realtime_end=today,
        observation_start=start,
        observation_end=as_of_date.isoformat(),
        sort_order="asc",
        limit=100000,
        units="lin",
    )

    items = response.get("observations", [])

    if not isinstance(items, list):
        raise FredError(
            f"Invalid observations for {series_id}"
        )

    if response.get("count", len(items)) > len(items):
        raise FredError(
            f"FRED response truncated for {series_id}"
        )

    return items


# ======================================
# 4. Apply V3 Data-Quality Rules
# ======================================

def _quality_for(series_id, observations, as_of_date):
    """Reuse our existing missing-data checks."""

    monthly = {}

    for obs in observations:

        if obs["value"] is None:
            continue

        day = date.fromisoformat(
            obs["observation_date"]
        )

        key = day.year * 12 + day.month - 1

        monthly[key] = (day, obs["value"])

    status, detail = check_history(
        series_id, monthly, as_of_date
    )

    return {
        "status": status,
        "detail": detail,
    }


# ======================================
# 5. Unified Data Loader
# ======================================

def load_observations(client, mode, as_of_date=None):
    """
    Return the same data format for all three modes.

    Returns:
        mode
        as_of
        observations
        quality
        errors

    Recession labels (USREC) are not predictors.
    """

    if mode not in MODES:
        raise ValueError(
            f"Choose one of: {', '.join(MODES)}"
        )

    if mode != "present" and as_of_date is None:
        raise ValueError(
            "Historical modes require an as-of date"
        )

    cutoff = _parse_date(as_of_date)

    if mode == "present" and cutoff != date.today():
        raise ValueError(
            "Present mode must use today's date"
        )

    result = {
        "mode": mode,
        "as_of": cutoff.isoformat(),
        "observations": {},
        "quality": {},
        "errors": {},
    }

    for series_id in SERIES_IDS:

        try:
            if mode == "time_machine":

                # Historical observations as recorded
                # by ALFRED on the selected date.
                raw = get_historical_series(
                    client, series_id, cutoff
                )["observations"]

            else:

                # Present = latest data.
                # Research = current revisions of old data.
                raw = _current_vintage(
                    client, series_id, cutoff
                )

            observations = _clean_observations(
                raw, cutoff
            )

            result["observations"][series_id] = observations

            result["quality"][series_id] = _quality_for(
                series_id, observations, cutoff
            )

        except (HistoricalUnavailable, FredError) as error:

            # Missing data is not replaced with zero.
            result["observations"][series_id] = []

            result["quality"][series_id] = {
                "status": "NO",
                "detail": str(error),
            }

            result["errors"][series_id] = str(error)

    return result
