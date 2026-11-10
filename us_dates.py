"""A consistent U.S. Eastern calendar date across local and cloud hosts.

The app must not advance to the next day just because a UTC-hosted worker
has crossed midnight before the U.S. has.
"""

from datetime import datetime, timezone
from dateutil.tz import gettz


def us_today(now_utc=None):
    """Return the current calendar date in America/New_York, including DST."""
    if now_utc is None:
        now_utc = datetime.now(timezone.utc)
    if now_utc.tzinfo is None or now_utc.utcoffset() is None:
        raise ValueError("A timezone-aware instant is required")
    eastern = gettz("America/New_York")
    if eastern is None:
        raise RuntimeError("America/New_York timezone data is unavailable")
    return now_utc.astimezone(eastern).date()
