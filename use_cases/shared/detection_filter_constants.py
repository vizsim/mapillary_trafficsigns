"""
Thresholds for Mapillary-derived layers used in radinfra.de exports and related campaigns.

Rationale: docs/mapillary-detection-filters.md
"""

from __future__ import annotations

# --- Recency (traffic signs + markings) ---

# Mapillary exposes `first_seen_at` and `last_seen_at` per detection id. We require the
# detection to still appear in imagery after this date so mappers see something current.
LAST_SEEN_CUTOFF_DATE_STR = "2023-01-01"

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
