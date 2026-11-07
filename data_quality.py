
"""Data-quality rules for economic observations.

Missing data is never invented, interpolated, or filled.
"""

REQUIRED_MONTHS = 13
MAX_AGE_DAYS = 110

# Verified structural gaps in official economic datasets.
# BLS did not collect October 2025 unemployment data.
KNOWN_STRUCTURAL_MISSING = {
    "UNRATE": {"2025-10"},
}


# ======================================
# Date Helpers
# ======================================

def month_label(month_number):
    """Convert year*12 + month-1 into YYYY-MM."""

    year, month_index = divmod(month_number, 12)

    return f"{year:04d}-{month_index + 1:02d}"


# ======================================
# Historical Data Quality
# ======================================

def check_history(
    series_id,
    data,
    as_of,
    required_months=REQUIRED_MONTHS,
    max_age_days=MAX_AGE_DAYS,
):
    """
    Validate monthly historical observations.

    Status:
        OK        Complete, sufficiently recent history
        KNOWN_GAP Verified missing historical observation
        GAP       Unexplained missing observation
        STALE     Latest reading exceeds freshness threshold
        NO        No observations available

    Returns (status, details).
    """

    # Never use observations after the selected date.
    available = {
        month: entry
        for month, entry in data.items()
        if entry[0] <= as_of
    }

    if not available:
        return "NO", "No observations available"

    latest_month = max(available)
    latest_date = available[latest_month][0]

    age = (as_of - latest_date).days

    # Check the required consecutive calendar months.
    missing = [
        month_label(latest_month - offset)
        for offset in range(required_months)
        if latest_month - offset not in available
    ]

    missing.reverse()

    known = [
        month for month in missing
        if month in KNOWN_STRUCTURAL_MISSING.get(
            series_id, set()
        )
    ]

    unexpected = [
        month for month in missing
        if month not in known
    ]

    notes = [
        f"Latest observation: {latest_date}",
        f"Reference-period age: {age} days",
    ]

    if known:
        notes.append(
            "Verified missing: " + ", ".join(known)
        )

    if unexpected:
        notes.append(
            "Unexplained missing: " + ", ".join(unexpected)
        )

    details = "; ".join(notes)

    # Check staleness independently of missing months.
    if age > max_age_days:
        return (
            "STALE",
            details + f"; threshold: {max_age_days} days",
        )

    if unexpected:
        return "GAP", details

    if known:
        return "KNOWN_GAP", details

    return "OK", ""


# ======================================
# Feature-Specific Availability
# ======================================

def required_months_available(data, months):
    """
    Check that every exact month needed for a calculation
    exists. Never substitute another month automatically.
    """

    return all(
        month in data
        for month in months
    )
