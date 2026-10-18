"""Tests for ar_campaign - matching and task text of the access-restriction campaign, without network.

Run: `uv run pytest` in the repo root.
"""

import ast
import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import LineString, Point

import ar_campaign as ar
import campaign

# At 52 N, 0.0003 degrees of longitude are about 21 m.
_ZEICHEN = {gruppe: value for value, (_, gruppe) in ar.ZEICHEN.items()}


def _signs(*gruppen):
    return gpd.GeoDataFrame(
        {
            "id": list(range(len(gruppen))),
            "value": [_ZEICHEN[g] for g in gruppen],
            "geometry": [Point(13.0003, 52.005)] * len(gruppen),
        },
        crs="EPSG:4326",
    )


def _way(**tags):
    daten = {key: [None] for key in ar.OSM_SCHLUESSEL}
    daten.update({key: [value] for key, value in tags.items()})
    daten["highway"] = [tags.get("highway", "residential")]
    daten["geometry"] = [LineString([(13.0, 52.0), (13.0, 52.01)])]
    return gpd.GeoDataFrame(daten, crs="EPSG:4326")


def test_distance_to_matching_way_takes_the_keys_of_the_sign():
    signs = _signs("bicycle", "hgv", "foot")

    # Only hgv=* nearby: answers the HGV sign, not the bicycle or pedestrian one.
    abstand = ar.distance_to_matching_way(signs, _way(hgv="no"))
    assert np.isinf(abstand[0]) and np.isfinite(abstand[1]) and np.isinf(abstand[2])

    # access=* answers every group.
    assert np.isfinite(ar.distance_to_matching_way(signs, _way(access="private"))).all()


def test_distance_to_matching_way_counts_any_value():
    """bicycle=yes next to a no-bicycles sign counts as mapped - the rule of the 2026 round."""
    assert np.isfinite(ar.distance_to_matching_way(_signs("bicycle"), _way(bicycle="yes"))[0])


def test_distance_to_matching_way_beyond_the_radius():
    weit = _signs("bicycle").set_geometry([Point(13.001, 52.005)])  # about 69 m away
    assert np.isinf(ar.distance_to_matching_way(weit, _way(access="no"))[0])


def test_read_access_ways_keeps_every_way_unless_told_to_keep_roads_only(tmp_path):
    ways = pd.concat([_way(access="private"), _way(access="private", highway=None)], ignore_index=True)
    gpd.GeoDataFrame(ways, crs="EPSG:4326").to_parquet(tmp_path / "access.parquet")

    # A parking lot with access=private counts by default, as in the 2026 round.
    assert len(ar.read_access_ways(tmp_path / "access.parquet", verbose=False)) == 2
    nur_strassen = ar.read_access_ways(tmp_path / "access.parquet", nur_strassen=True, verbose=False)
    assert list(nur_strassen["highway"]) == ["residential"]


def test_every_sign_has_its_keys():
    assert {gruppe for _, gruppe in ar.ZEICHEN.values()} <= ar.SCHLUESSEL.keys()
    assert ar.OSM_SCHLUESSEL == sorted({key for keys in ar.SCHLUESSEL.values() for key in keys})


def test_prepare_notebook_extracts_the_keys_the_campaign_matches():
    """0_prepare_osm_network keeps the access keys in its own list; they must not drift apart."""
    notebook = Path(__file__).resolve().parent / "0_prepare_osm_network.ipynb"
    quellen = ["".join(c["source"]) for c in json.loads(notebook.read_text(encoding="utf-8"))["cells"]]
    zelle = next(q for q in quellen if q.lstrip().startswith("access_keys ="))
    zuweisung = ast.parse(zelle).body[0]
    assert sorted(ast.literal_eval(zuweisung.value)) == ar.OSM_SCHLUESSEL


def _properties(**overrides):
    daten = {
        "id": [1234567890123456],
        "value": [_ZEICHEN["bicycle"]],
        "image_id": ["2680449905458647"],
        "image_captured_at": [pd.Timestamp("2026-09-12", tz="UTC")],
        "geometry": [Point(13.0, 52.0)],
    }
    daten.update(overrides)
    tasks = gpd.GeoDataFrame(daten, crs="EPSG:4326")
    return campaign.build_maproulette_geojson(tasks, ar.aufgabe)["features"][0]["properties"]


def test_aufgabe_builds_the_expected_fields():
    properties = _properties()

    assert set(properties) == {"image_id", "Verkehrzeichen", "instruction"}
    assert properties["Verkehrzeichen"] == "254"
    instruction = properties["instruction"]
    assert "**DE:254**" in instruction
    assert "Kein Weg im Umkreis von **30 m** trägt `bicycle=*`, `vehicle=*` oder `access=*`." in instruction
    assert "pKey=2680449905458647" in instruction
    assert "&trafficSign[]=regulatory--no-bicycles--g1" in instruction
    assert "**12.09.2026**" in instruction


def test_aufgabe_without_an_image():
    properties = _properties(image_id=[None], image_captured_at=[pd.NaT])
    assert properties["image_id"] is None
    assert "Kein Mapillary-Bild" in properties["instruction"]
