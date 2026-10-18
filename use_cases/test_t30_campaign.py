"""Tests for t30_campaign - what counts as a mapped 30, and the task text, without network.

Run: `uv run pytest` in the repo root.
"""

import geopandas as gpd
import pandas as pd
from shapely.geometry import LineString, Point, Polygon

import campaign
import t30_campaign as t30


def _ways(*zeilen):
    """One way per dict of tags (columns as the GDAL OSM driver names them)."""
    spalten = ["highway", "maxspeed", "maxspeed_forward", "maxspeed_backward", "maxspeed_hgv",
               "maxspeed_conditional", "maxspeed_forward_conditional", "maxspeed_backward_conditional",
               "maxspeed_hgv_conditional", "zone_maxspeed"]
    daten = {spalte: [zeile.get(spalte) for zeile in zeilen] for spalte in spalten}
    daten["geometry"] = [LineString([(13.0, 52.0), (13.0, 52.01)])] * len(zeilen)
    return gpd.GeoDataFrame(daten, crs="EPSG:4326")


def test_filter_tempo30_ways_knows_every_variant():
    ways = _ways(
        {"highway": "residential", "maxspeed": "30"},
        {"highway": "primary", "maxspeed_backward": "30"},
        {"highway": "secondary", "maxspeed_conditional": "30 @ (Mo-Fr 07:00-17:00)"},
        {"highway": "tertiary", "maxspeed_hgv_conditional": "30 @ (22:00-06:00)"},
        {"highway": "residential", "zone_maxspeed": "DE:30"},
        {"highway": "residential", "maxspeed": "50"},
        {"highway": "living_street", "maxspeed": "30"},  # not one of the road types
        {"highway": "residential", "maxspeed": "30 mph"},
    )
    assert list(t30.filter_tempo30_ways(ways, verbose=False).index) == [0, 1, 2, 3, 4]


def test_filter_tempo30_ways_skips_missing_columns():
    ways = gpd.GeoDataFrame(
        {"highway": ["residential"], "maxspeed": ["30"], "geometry": [LineString([(0, 0), (1, 1)])]},
        crs="EPSG:4326",
    )
    assert len(t30.filter_tempo30_ways(ways, verbose=False)) == 1


def test_read_schools_keeps_points_and_areas(tmp_path):
    flaeche = Polygon([(13, 52), (13.001, 52), (13.001, 52.001), (13, 52)])
    gpd.GeoDataFrame(
        {
            "amenity": ["school", "kindergarten", "school"],
            "osm_layer": ["points", "multipolygons", "other_relations"],
            "geometry": [Point(13, 52), flaeche, Point(13, 52)],
        },
        crs="EPSG:4326",
    ).to_parquet(tmp_path / "schools.parquet")

    assert list(t30.read_schools(tmp_path / "schools.parquet", verbose=False)["osm_layer"]) == ["points", "multipolygons"]


def test_school_radius_is_the_two_buffers_of_the_2025_round():
    assert t30.SCHULRADIUS_M == 400 + t30.SUCHRADIUS_M


def _properties(**overrides):
    daten = {
        "id": [1620332315157183],
        "value": ["regulatory--maximum-speed-limit-30--g1"],
        "image_id": ["614624237290938"],
        "image_captured_at": [pd.Timestamp("2026-09-12", tz="UTC")],
        "geometry": [Point(13.4, 52.5)],
    }
    daten.update(overrides)
    tasks = gpd.GeoDataFrame(daten, crs="EPSG:4326")
    return campaign.build_maproulette_geojson(tasks, t30.aufgabe)["features"][0]


def test_aufgabe_keeps_image_and_detection_apart():
    """The 2025 round swapped them: the task was named after the image."""
    feature = _properties()
    assert feature["id"] == "1620332315157183"
    assert feature["properties"]["image_id"] == "614624237290938"
    assert "pKey=614624237290938" in feature["properties"]["instruction"]


def test_aufgabe_builds_the_expected_text():
    instruction = _properties()["properties"]["instruction"]
    assert "Keine Straße im Umkreis von **50 m** trägt in OSM eine 30." in instruction
    assert "&trafficSign[]=regulatory--maximum-speed-limit-30--g1" in instruction
    assert "openstreetbrowser.org/#map=17.4/52.5/13.4" in instruction
    assert "**12.09.2026**" in instruction
    # Valid opening-hours syntax: hyphens, not dashes.
    assert "30 @ (Mo-Fr 07:00-17:00)" in instruction


def test_aufgabe_keeps_the_hard_line_breaks():
    zeilen = _properties()["properties"]["instruction"].splitlines()
    for anfang in ("- 📷 [**Mapillary-Bild anzeigen**]", "- **Konstant:**", "  `maxspeed=30`"):
        zeile = next(z for z in zeilen if z.startswith(anfang))
        assert zeile.endswith(campaign.BR), f"hard break missing after {anfang!r}"


def test_aufgabe_without_an_image():
    feature = _properties(image_id=[None], image_captured_at=[pd.NaT])
    assert feature["properties"]["image_id"] is None
    assert "Kein Mapillary-Bild" in feature["properties"]["instruction"]
