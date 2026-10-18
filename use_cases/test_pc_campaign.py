"""Tests for pc_campaign - the task text of the pedestrian-crossing campaign, without network.

Run: `uv run pytest` in the repo root.
"""

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import Point

import campaign
import pc_campaign as pc


def _task_frame(**overrides):
    daten = {
        "id": [392467478901133],
        "value": ["information--pedestrians-crossing--g1"],
        "VZ": [350],
        "dist_crossing_m": [61.6],
        "image_id": ["2680449905458647"],
        "image_captured_at": [pd.Timestamp("2026-09-12", tz="UTC")],
        "geometry": [Point(8.075, 48.531)],
    }
    daten.update(overrides)
    return gpd.GeoDataFrame(daten, crs="EPSG:4326")


def _properties(**overrides):
    return campaign.build_maproulette_geojson(_task_frame(**overrides), pc.aufgabe)["features"][0]["properties"]


def test_aufgabe_builds_the_expected_fields():
    properties = _properties()

    assert set(properties) == {"image_id", "Verkehrzeichen", "instruction"}
    assert properties["image_id"] == "2680449905458647"
    assert properties["Verkehrzeichen"] == "350"

    instruction = properties["instruction"]
    assert "**DE:350**" in instruction
    assert "pKey=2680449905458647" in instruction
    assert "&trafficSign[]=information--pedestrians-crossing--g1" in instruction
    assert "ist **ca. 62 m** entfernt" in instruction
    assert "**12.09.2026**" in instruction
    assert "trafficsigns.osm-verkehrswende.org/DE?signs=DE:350" in instruction


def test_aufgabe_without_a_crossing_within_the_measuring_radius():
    instruction = _properties(dist_crossing_m=[np.inf])["instruction"]
    assert f"ist **mehr als {pc.MESSRADIUS_M:.0f} m** entfernt" in instruction


def test_aufgabe_without_an_image():
    properties = _properties(image_id=[None], image_captured_at=[pd.NaT])

    assert properties["image_id"] is None
    assert "Kein Mapillary-Bild" in properties["instruction"]
    assert "mapillary.com/app" not in properties["instruction"]


def test_aufgabe_keeps_the_hard_line_breaks():
    """Without the two trailing spaces, MapRoulette joins these lines into one."""
    zeilen = _properties()["instruction"].splitlines()

    for anfang in ("- 📷 [**Mapillary-Bild anzeigen**]", "`highway=crossing`", "`crossing=uncontrolled`"):
        zeile = next(z for z in zeilen if z.startswith(anfang))
        assert zeile.endswith(campaign.BR), f"hard break missing after {anfang!r}"


def test_distances_fit_together():
    # Grouping must not reach further than two search circles, or two crossings
    # that each lack a node could be merged although neither sign is near the other.
    assert pc.ZUSAMMENFASSEN_M <= 2 * pc.SUCHRADIUS_M
    # The text must be able to show a distance beyond the search radius.
    assert pc.MESSRADIUS_M > pc.SUCHRADIUS_M
