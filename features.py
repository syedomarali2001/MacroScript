
"""V4: Economic feature calculations (no API requests)."""

from datetime import date
import math


# ======================================
# 1. Monthly Date Helpers
# ======================================

def month_id(day):
    """Unique integer for a calendar month."""
    return day.year * 12 + day.month - 1


def month_label(index):
    """Convert a month ID into YYYY-MM."""
    year, month_zero_based = divmod(index, 12)
    return f"{year:04d}-{month_zero_based + 1:02d}"


# ======================================
# 2. Prepare Monthly Data
# ======================================

def monthly_values(observations, as_of_date):
    """
    Convert observations into {month_id: value}.

    - Exclude future reference periods.
    - Ignore missing/non-numeric observations.
    - Never fill missing months.

    IMPORTANT:
    Historical Time Machine must provide the correct
    ALFRED vintage. Date filtering alone does not
    prevent future revisions from leaking into data.
    """

    cutoff = date.fromisoformat(str(as_of_date))
    result = {}

    for item in observations:

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

            if observed > cutoff:
                continue

            raw_value = item.get("value")

            if raw_value is None:
                continue

            value = float(raw_value)

            if not math.isfinite(value):
                continue

        except (ValueError, TypeError):
            continue

        result[month_id(observed)] = value

    return result


# ======================================
# 3. Reusable Statistical Calculations
# ======================================

def moving_average(values, end_month, window=3):
    """Average exact consecutive calendar months."""

    if window < 1:
        raise ValueError("window must be positive")

    sample = [
        values.get(end_month - i)
        for i in range(window)
    ]

    if any(value is None for value in sample):
        return None

    return sum(sample) / window


def change_pp(values, end_month, lag=3):
    """Change in percentage points between two months."""

    if lag < 1:
        raise ValueError("lag must be positive")

    now = values.get(end_month)
    then = values.get(end_month - lag)

    if now is None or then is None:
        return None

    return now - then


def pct_growth(values, end_month, lag):
    """Percentage growth between two exact months."""

    if lag < 1:
        raise ValueError("lag must be positive")

    now = values.get(end_month)
    then = values.get(end_month - lag)

    if now is None or then is None or then <= 0:
        return None

    return 100.0 * (now / then - 1.0)


# ======================================
# 4. Sahm Rule Calculation
# ======================================

def sahm_rule(values, end_month):
    """
    Current 3-month unemployment average minus the
    lowest 3-month average in the preceding 12 months.

    Strict rule:
    All required monthly observations must exist.

    A result >= 0.50 percentage points is a signal.
    """

    current_avg = moving_average(
        values, end_month, 3
    )

    previous_avgs = [
        moving_average(
            values,
            end_month - lag,
            3
        )
        for lag in range(1, 13)
    ]

    if current_avg is None:
        return None

    if any(avg is None for avg in previous_avgs):
        return None

    return current_avg - min(previous_avgs)


# ======================================
# 5. Unemployment Features
# ======================================

def unemployment_features(values):
    """Calculate unemployment trends and Sahm Rule."""

    if not values:
        return {
            "reference_month": None,
            "rate_pct": None,
            "average_3m_pct": None,
            "change_3m_pp": None,
            "sahm_pp": None,
            "sahm_triggered": None,
        }

    end = max(values)

    signal = sahm_rule(values, end)

    return {
        "reference_month": month_label(end),
        "rate_pct": values[end],

        "average_3m_pct": moving_average(
            values, end, 3
        ),

        "change_3m_pp": change_pp(
            values, end, 3
        ),

        "sahm_pp": signal,

        "sahm_triggered": (
            signal >= 0.50
            if signal is not None else None
        ),
    }


# ======================================
# 6. Growth Features
# ======================================

def growth_features(values):
    """
    Used for:
    - Nonfarm payroll employment
    - Industrial production
    - Housing building permits

    Growth is percentage change, not annualized growth.
    """

    if not values:
        return {
            "reference_month": None,
            "level": None,
            "average_3m": None,
            "growth_3m_pct": None,
            "growth_12m_pct": None,
        }

    end = max(values)

    return {
        "reference_month": month_label(end),
        "level": values[end],

        "average_3m": moving_average(
            values, end, 3
        ),

        "growth_3m_pct": pct_growth(
            values, end, 3
        ),

        "growth_12m_pct": pct_growth(
            values, end, 12
        ),
    }


# ======================================
# 7. Treasury Yield Curve
# ======================================

def consecutive_inversion_months(spreads, end_month):
    """
    Count consecutive months with negative spreads.

    Return None if a missing month prevents us from
    determining the full duration.
    """

    current = spreads.get(end_month)

    if current is None:
        return None

    if current >= 0:
        return 0

    months = 0
    cursor = end_month

    while True:

        value = spreads.get(cursor)

        if value is None:
            return None

        if value >= 0:
            return months

        months += 1
        cursor -= 1


def treasury_features(long_rates, short_rates):
    """
    Monthly Treasury spread proxy:

        GS10 - TB3MS

    Both observations must refer to the same month.

    This monthly proxy is not identical to T10Y3M.
    """

    spreads = {
        month: long_rates[month] - short_rates[month]
        for month in (
            long_rates.keys() & short_rates.keys()
        )
    }

    if not spreads:
        return {
            "reference_month": None,
            "spread_pp": None,
            "average_3m_pp": None,
            "inverted": None,
            "inversion_months": None,
        }

    end = max(spreads)

    return {
        "reference_month": month_label(end),
        "spread_pp": spreads[end],

        "average_3m_pp": moving_average(
            spreads, end, 3
        ),

        "inverted": spreads[end] < 0,

        "inversion_months": consecutive_inversion_months(
            spreads, end
        ),
    }


# ======================================
# 8. Calculate All Five Indicators
# ======================================

def calculate_all_features(
    observations_by_series,
    as_of_date
):
    """
    One calculation engine for all three data modes.

    Expected input:
        {
            "UNRATE": [...],
            "PAYEMS": [...],
            "INDPRO": [...],
            "PERMIT": [...],
            "GS10": [...],
            "TB3MS": [...]
        }

    Missing series produce unavailable features
    rather than fabricated results.
    """

    series_ids = (
        "UNRATE",
        "PAYEMS",
        "INDPRO",
        "PERMIT",
        "GS10",
        "TB3MS",
    )

    monthly = {
        series_id: monthly_values(
            observations_by_series.get(series_id, []),
            as_of_date
        )
        for series_id in series_ids
    }

    return {
        "unemployment": unemployment_features(
            monthly["UNRATE"]
        ),

        "payrolls": growth_features(
            monthly["PAYEMS"]
        ),

        "industrial_production": growth_features(
            monthly["INDPRO"]
        ),

        "housing_permits": growth_features(
            monthly["PERMIT"]
        ),

        "treasury_spread": treasury_features(
            monthly["GS10"],
            monthly["TB3MS"]
        ),
    }
