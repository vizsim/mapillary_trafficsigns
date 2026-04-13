"""
Thresholds for Mapillary-derived layers used in radinfra.de exports and related campaigns.

Rationale: docs/mapillary-detection-filters.md
"""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from dateutil.relativedelta import relativedelta

# --- Recency (traffic signs + markings) ---

# Anchor "today" for rolling freshness (local calendar date in this zone).
FRESHNESS_TIMEZONE = "Europe/Berlin"

# Rolling window: cutoff = Berlin local date today minus this many calendar months.
# Configured: 36 months (3 years).
LAST_SEEN_LOOKBACK_MONTHS = 36


def compute_last_seen_cutoff_date(reference: datetime | None = None) -> date:
    """
    Date such that last_seen_at should be strictly after this (YYYY-MM-DD compare).

    Uses the calendar date in FRESHNESS_TIMEZONE for `reference` (or now), then subtracts
    relativedelta(months=LAST_SEEN_LOOKBACK_MONTHS).
    """
    tz = ZoneInfo(FRESHNESS_TIMEZONE)
    if reference is None:
        ref = datetime.now(tz)
    else:
        ref = reference.astimezone(tz) if reference.tzinfo else reference.replace(tzinfo=tz)
    local_day = ref.date()
    return local_day - relativedelta(months=LAST_SEEN_LOOKBACK_MONTHS)


def compute_last_seen_cutoff_date_str(reference: datetime | None = None) -> str:
    """ISO date string for filters comparing to Mapillary last_seen_at."""
    return compute_last_seen_cutoff_date(reference).strftime("%Y-%m-%d")


def freshness_export_metadata(reference: datetime | None = None) -> dict:
    """Config + computed values for README sidecars / JSON mirrors."""
    tz = ZoneInfo(FRESHNESS_TIMEZONE)
    if reference is None:
        ref = datetime.now(tz)
    else:
        ref = reference.astimezone(tz) if reference.tzinfo else reference.replace(tzinfo=tz)
    cutoff = compute_last_seen_cutoff_date(reference)
    return {
        "freshness_timezone": FRESHNESS_TIMEZONE,
        "last_seen_lookback_months": LAST_SEEN_LOOKBACK_MONTHS,
        "last_seen_cutoff_computed": cutoff.isoformat(),
        "export_computed_at_berlin": ref.isoformat(),
    }


# Lower bound for `first_seen_at` when loading markings (drops invalid/placeholder dates).
FIRST_SEEN_VALID_AFTER_STR = "2000-01-01"

# --- Repeat observation (markings only) ---

# Minimum calendar days between first and last sighting. Mapillary aggregates multiple
# image hits into one id; a span over this many days implies the marking was seen on
# more than one occasion / season, which filters many one-off ML glitches and vanished paint.
MIN_DAYS_BETWEEN_FIRST_AND_LAST_OBSERVATION = 180

# --- Traffic signs only: motorway proximity ---

# Signs whose buffered point intersects a motorway are dropped (many false positives on Autobahnen).
MOTORWAY_EXCLUSION_BUFFER_M = 30
