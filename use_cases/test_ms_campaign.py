"""Tests for ms_campaign - sections, assignment to roads, accident data and task text, without network.

Run: `uv run pytest` in the repo root.
"""

import ast
import hashlib
import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import LineString, Point

import campaign
import ms_campaign as ms

METRISCH = campaign.METRISCHES_CRS


def _roads(*zeilen):
    """One road per (highway, coordinates, tags) in the metric CRS."""
    daten = {
        "osm_id": [str(100 + i) for i in range(len(zeilen))],
        "highway": [z[0] for z in zeilen],
        "maxspeed": [z[2].get("maxspeed") for z in zeilen],
        "maxspeed_forward": [z[2].get("maxspeed_forward") for z in zeilen],
        "maxspeed_backward": [z[2].get("maxspeed_backward") for z in zeilen],
        "name": [z[2].get("name") for z in zeilen],
        "ref": [z[2].get("ref") for z in zeilen],
        "geometry": [LineString(z[1]) for z in zeilen],
    }
    return gpd.GeoDataFrame(daten, crs=METRISCH)


# --- Road types and maxspeed ------------------------------------------------


def test_prepare_notebook_extracts_the_road_types_the_campaign_reads():
    """0_prepare_osm_network keeps the road types in its own list; they must not drift apart."""
    notebook = Path(__file__).resolve().parent / "0_prepare_osm_network.ipynb"
    quellen = ["".join(c["source"]) for c in json.loads(notebook.read_text(encoding="utf-8"))["cells"]]
    zelle = next(q for q in quellen if q.lstrip().startswith("road_types ="))
    zuweisung = ast.parse(zelle).body[0]
    assert sorted(ast.literal_eval(zuweisung.value)) == sorted(ms.STRASSENTYPEN)


def test_read_roads_refuses_unknown_road_types(tmp_path):
    roads = _roads(("primary", [(0, 0), (1, 0)], {}), ("footway", [(0, 0), (0, 1)], {}))
    roads.to_crs(4326).to_parquet(tmp_path / "roads.parquet")
    with pytest.raises(ValueError, match="footway"):
        ms.read_roads(tmp_path / "roads.parquet", verbose=False)


def test_hat_maxspeed_needs_a_value():
    ways = pd.DataFrame({
        "maxspeed": ["50", None, None, None],
        "maxspeed_forward": [None, "70", None, None],
        "maxspeed_backward": [None, None, None, None],
        "zone_maxspeed": [None, None, "DE:30", None],
    })
    assert ms.hat_maxspeed(ways).tolist() == [True, True, False, False]


def test_tempo_reads_the_value_from_the_class():
    assert ms.tempo(pd.Series(["regulatory--maximum-speed-limit-70--g1"])).tolist() == [70]
    assert "regulatory--maximum-speed-limit-20--g1" not in ms.ZEICHEN


# --- Sections ---------------------------------------------------------------


def test_abschnitte_joins_connected_ways_of_the_same_road():
    ways = _roads(
        ("secondary", [(0, 0), (100, 0)], {"name": "Hauptstraße"}),
        ("secondary", [(100, 0), (200, 0)], {"name": "Hauptstraße"}),
        ("secondary", [(300, 0), (200, 0)], {"name": "Hauptstraße"}),  # drawn the other way round
        ("tertiary", [(200, 0), (200, 100)], {"name": "Nebenweg"}),  # touches, other name
        ("tertiary", [(500, 0), (600, 0)], {"name": "Hauptstraße"}),  # same name, not connected
        ("tertiary", [(0, 500), (100, 500)], {"ref": "L 159"}),
        ("tertiary", [(100, 500), (200, 500)], {"ref": "L 159"}),
    )
    label = ms.abschnitte(ways)
    assert label[0] == label[1] == label[2]
    assert len({label[0], label[3], label[4], label[5]}) == 4
    assert label[5] == label[6]
    assert sorted(set(label)) == list(range(4))


def test_abschnitte_of_a_long_chain():
    """Label propagation must not stop early on a long chain, whatever the order."""
    teile = [((i * 10, 0), ((i + 1) * 10, 0)) for i in range(200)]
    reihenfolge = np.random.default_rng(1).permutation(200)
    ways = _roads(*(("primary", list(teile[i]), {"name": "B 1"}) for i in reihenfolge))
    assert set(ms.abschnitte(ways)) == {0}


# --- Assignment to roads ----------------------------------------------------


def _kreuzung():
    """A main road along y=0 and a side street crossing it at x=100."""
    return _roads(
        ("primary", [(0, 0), (200, 0)], {}),
        ("residential", [(100, -100), (100, 100)], {}),
    )


def _punkte(*xy):
    return gpd.GeoDataFrame(geometry=[Point(x, y) for x, y in xy], crs=METRISCH)


def test_naechste_hauptstrasse_keeps_the_junction_and_leaves_the_side_street():
    roads = _kreuzung()
    punkte = _punkte(
        (100, 1),  # at the junction: 1 m from the main road, 0 m from the side street
        (100, 10),  # 10 m into the side street
        (50, 5),  # beside the main road
        (50, 30),  # too far from both
    )
    assert ms.naechste_hauptstrasse(punkte, roads, max_m=15.0).tolist() == [0, -1, 0, -1]


def test_naechste_hauptstrasse_returns_positions_in_roads():
    roads = _roads(
        ("residential", [(0, 50), (200, 50)], {}),
        ("primary", [(0, 0), (200, 0)], {}),
    )
    assert ms.naechste_hauptstrasse(_punkte((20, 2)), roads, max_m=15.0).tolist() == [1]


def test_naechste_hauptstrasse_needs_a_metric_crs():
    with pytest.raises(ValueError, match="metrisch"):
        ms.naechste_hauptstrasse(_punkte((0, 0)), _kreuzung().to_crs(4326), max_m=15.0)


def test_drop_near_motorways():
    roads = _roads(("motorway", [(0, 100), (200, 100)], {}), ("primary", [(0, 0), (200, 0)], {}))
    signs = _punkte((50, 80), (50, 2))
    assert len(ms.drop_near_motorways(signs, roads, verbose=False)) == 1


# --- Accident data ----------------------------------------------------------


class _Antwort:
    def __init__(self, inhalt=b"", daten=None):
        self.inhalt, self.daten = inhalt, daten

    def raise_for_status(self):
        pass

    def json(self):
        return self.daten

    def iter_content(self, chunk_size):
        yield self.inhalt

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _server(monkeypatch, inhalt, sha256):
    latest = {"datei": "unfallorte_2016-2025_2026-10-03.parquet", "sha256": sha256}

    def get(url, **kwargs):
        return _Antwort(daten=latest) if url.endswith("latest.json") else _Antwort(inhalt=inhalt)

    monkeypatch.setattr(ms.requests, "get", get)


def test_sync_unfaelle_keeps_the_dated_name(tmp_path, monkeypatch):
    _server(monkeypatch, b"parquet", hashlib.sha256(b"parquet").hexdigest())
    pfad, latest = ms.sync_unfaelle(tmp_path, verbose=False)
    assert pfad.name == "unfallorte_2016-2025_2026-10-03.parquet"
    assert pfad.read_bytes() == b"parquet"


def test_sync_unfaelle_throws_away_a_bad_download(tmp_path, monkeypatch):
    _server(monkeypatch, b"kaputt", hashlib.sha256(b"parquet").hexdigest())
    with pytest.raises(RuntimeError, match="Prüfsumme"):
        ms.sync_unfaelle(tmp_path, verbose=False)
    assert list(tmp_path.iterdir()) == []


def _unfallatlas(tmp_path, laender_2021=16):
    zeilen = [(jahr, f"{land:02d}") for jahr in (2019, 2020, 2021) for land in range(1, 17)
              if not (jahr == 2021 and land > laender_2021)]
    gdf = gpd.GeoDataFrame({
        "unfall_id": [f"x-{i}" for i in range(len(zeilen))],
        "UJAHR": [j for j, _ in zeilen],
        "UKATEGORIE": [3] * len(zeilen),
        "ULAND": [land for _, land in zeilen],
        "geometry": [Point(13, 52)] * len(zeilen),
    }, crs=4326)
    gdf.to_parquet(tmp_path / "unfaelle.parquet")
    return tmp_path / "unfaelle.parquet"


def test_load_unfaelle_takes_the_years(tmp_path):
    unfaelle = ms.load_unfaelle(_unfallatlas(tmp_path), jahre=(2020, 2021), verbose=False)
    assert sorted(unfaelle["UJAHR"].unique()) == [2020, 2021]


def test_load_unfaelle_refuses_a_year_without_every_state(tmp_path):
    with pytest.raises(RuntimeError, match="2021"):
        ms.load_unfaelle(_unfallatlas(tmp_path, laender_2021=15), jahre=(2020, 2021), verbose=False)


# --- Tasks ------------------------------------------------------------------


def test_prioritaet_from_the_accidents():
    assert ms.prioritaet(pd.Series([2, 4, 9, 10, 40])).tolist() == [pd.NA, 1, 1, 0, 0]


def _abschnitte_mit_daten():
    ways = _roads(
        ("secondary", [(0, 0), (500, 0)], {"name": "Hauptstraße"}),
        ("secondary", [(500, 0), (1000, 0)], {"name": "Hauptstraße"}),
        ("tertiary", [(0, 1000), (500, 1000)], {"ref": "K 12"}),  # sign, too few accidents
        ("tertiary", [(0, 2000), (500, 2000)], {}),  # accidents, no sign
    )
    ways["osm_id"] = ["900", "77", "500", "600"]
    ways["abschnitt"] = [0, 0, 1, 2]
    signs = pd.DataFrame({
        "id": [11, 12, 13],
        "value": ["regulatory--maximum-speed-limit-30--g1", "regulatory--maximum-speed-limit-50--g1",
                  "regulatory--maximum-speed-limit-70--g1"],
        "kmh": [30, 50, 70],
        "first_seen_at": ["2024-01-05", "2023-03-01", "2024-02-01"],
        "last_seen_at": ["2025-06-01", "2026-05-01", "2025-09-01"],
        "abschnitt": [0, 0, 1],
    })
    unfaelle = pd.DataFrame({"abschnitt": [0] * 5 + [1] * 2 + [2] * 20, "UKATEGORIE": [1, 3, 3, 2, 3] + [3] * 22})
    return ways, signs, unfaelle


def test_abschnitt_aufgaben_needs_a_sign_and_enough_accidents():
    aufgaben = ms.abschnitt_aufgaben(*_abschnitte_mit_daten(), verbose=False)
    assert len(aufgaben) == 1
    aufgabe = aufgaben.iloc[0]
    assert aufgabe["id"] == "77"  # smallest way id, compared as a number
    assert aufgabe["unfaelle"] == 5 and aufgabe["unfaelle_schwer"] == 2
    assert aufgabe["prio"] == 1
    assert aufgabe["km"] == pytest.approx(1.0)
    assert aufgabe["strasse"] == "Hauptstraße" and aufgabe["highway"] == "secondary"
    assert aufgabe["tempo"] == "30/50"
    assert aufgabe["zeichen_ids"] == ["12", "11"]  # seen last first
    assert aufgabe.geometry.geom_type == "LineString"  # the two ways merged


def _properties(zeichen_liste=None, **overrides):
    ways, signs, unfaelle = _abschnitte_mit_daten()
    aufgaben = ms.abschnitt_aufgaben(ways, signs, unfaelle, verbose=False)
    bilder = pd.DataFrame(
        {"image_id": ["614624237290938"], "image_captured_at": [pd.Timestamp("2026-05-01", tz="UTC")]},
        index=pd.Index(["12"], name="id"),
    )
    aufgaben["zeichen_liste"] = zeichen_liste or ms.zeichen_liste(aufgaben, signs, bilder)
    for spalte, wert in overrides.items():
        aufgaben[spalte] = [wert]
    return campaign.build_maproulette_geojson(aufgaben, ms.aufgabe)["features"][0]


def test_aufgabe_builds_the_expected_fields():
    feature = _properties()
    properties = feature["properties"]
    assert feature["id"] == "77"
    assert feature["geometry"]["type"] == "LineString"
    assert properties["priority"] == 1 and properties["prioritaet"] == "mittel"
    assert properties["unfaelle"] == 5 and properties["tempo"] == "30/50"
    assert properties["image_id"] == "614624237290938"
    json.dumps(properties, allow_nan=False)


def test_aufgabe_builds_the_expected_text():
    instruction = _properties()["properties"]["instruction"]
    assert "Abschnitt der **Hauptstraße** (1,0 km, `highway=secondary`)" in instruction
    assert "**5 Unfälle mit Personenschaden**, davon 2 mit Getöteten oder Schwerverletzten" in instruction
    assert "**ganzen Abschnitt**" in instruction
    assert "Mapillary hat hier 2 Tempo-Schilder erkannt." in instruction
    zeilen = instruction.splitlines()
    assert zeilen.index(next(z for z in zeilen if "Tempo 50" in z)) < zeilen.index(next(z for z in zeilen if "Tempo 30" in z))
    assert "pKey=614624237290938&focus=photo&trafficSign[]=regulatory--maximum-speed-limit-50--g1" in instruction
    assert "gesehen 03/2023 bis 05/2026" in instruction
    assert "**Tempo 30** · gesehen 01/2024 bis 06/2025 · kein Mapillary-Bild verfügbar" in instruction
    assert "dl-de/by-2-0" in instruction and "2020–2025" in instruction
    assert "30 @ (22:00-06:00)" in instruction  # hyphens: valid opening-hours syntax


def test_aufgabe_keeps_the_hard_line_breaks():
    zeilen = _properties()["properties"]["instruction"].splitlines()
    for anfang in ("- **Mit Schild:**", "  `maxspeed=70`", "- 🗺️ In [**openstreetbrowser"):
        zeile = next(z for z in zeilen if z.startswith(anfang))
        assert zeile.endswith(campaign.BR), f"hard break missing after {anfang!r}"


def test_aufgabe_without_a_name_and_with_more_signs():
    zeichen = [{"id": "1", "value": "regulatory--maximum-speed-limit-70--g1", "kmh": 70,
                "first_seen_at": "2024-01-01", "last_seen_at": "2025-03-01", "image_id": None,
                "image_captured_at": pd.NaT}]
    feature = _properties(zeichen_liste=[zeichen], strasse=None, zeichen_ids=["1", "2", "3"], unfaelle_schwer=0)
    instruction = feature["properties"]["instruction"]
    assert "Abschnitt der **unbenannten Straße**" in instruction
    assert "… und 2 weitere" in instruction
    assert "Mapillary hat hier 3 Tempo-Schilder erkannt." in instruction
    assert "davon" not in instruction.split("Personenschaden")[1].split("\n")[0]
    assert feature["properties"]["strasse"] is None and feature["properties"]["image_id"] is None


def test_aufgabe_with_a_single_sign():
    zeichen = [{"id": "12", "value": "regulatory--maximum-speed-limit-50--g1", "kmh": 50,
                "first_seen_at": "2023-03-01", "last_seen_at": "2026-05-01", "image_id": None,
                "image_captured_at": pd.NaT}]
    instruction = _properties(zeichen_liste=[zeichen], zeichen_ids=["12"])["properties"]["instruction"]
    assert "Mapillary hat hier ein Tempo-Schild erkannt." in instruction
    assert "weitere" not in instruction
