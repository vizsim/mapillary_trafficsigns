"""Tests for campaign - the generic steps of the campaigns, without network.

Until campaign.py was split off cw_campaign.py, these lived in
test_cw_campaign.py. The most important one is still
`test_newest_image_ids_nimmt_neuestes_bild`: it pins the bug of the old
notebooks, which took the last element of an unsorted list.

Run: `uv run pytest` in the repo root.
"""

import json

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import LineString, Point, Polygon

import campaign


def _points(coords, ids=None):
    ids = ids if ids is not None else list(range(len(coords)))
    return gpd.GeoDataFrame(
        {"id": ids, "geometry": [Point(x, y) for x, y in coords]}, crs="EPSG:4326"
    )


def _line_north_south(lon, lat0=52.0, lat1=52.01):
    return gpd.GeoDataFrame(geometry=[LineString([(lon, lat0), (lon, lat1)])], crs="EPSG:4326")


# --- Distances -------------------------------------------------------------


def test_distance_to_nearest_misst_metrisch():
    # Ein Punkt gut 34 m oestlich einer Nord-Sued-Linie (bei 52 N sind
    # 0,0005 Grad Laenge rund 34 m).
    punkte = _points([(13.0005, 52.005)])
    linie = _line_north_south(13.0)

    weit = campaign.distance_to_nearest(punkte, linie, max_distance_m=50)
    assert 30 < weit.iloc[0] < 40

    # Ausserhalb des Suchradius bleibt inf, statt still eine falsche Zahl zu liefern.
    eng = campaign.distance_to_nearest(punkte, linie, max_distance_m=20)
    assert np.isinf(eng.iloc[0])


def test_distance_to_nearest_nimmt_die_naechste_von_mehreren():
    punkte = _points([(13.0005, 52.005)])
    linien = gpd.GeoDataFrame(
        geometry=[
            LineString([(13.0, 52.0), (13.0, 52.01)]),      # ~34 m entfernt
            LineString([(13.0003, 52.0), (13.0003, 52.01)]),  # ~14 m entfernt
        ],
        crs="EPSG:4326",
    )
    assert campaign.distance_to_nearest(punkte, linien, max_distance_m=50).iloc[0] < 20


def test_distance_to_nearest_behaelt_den_index():
    punkte = _points([(13.0005, 52.005), (14.0, 52.0), (13.0005, 52.006)])
    ergebnis = campaign.distance_to_nearest(punkte, _line_north_south(13.0), max_distance_m=50)

    assert list(ergebnis.index) == list(punkte.index)
    assert np.isinf(ergebnis.iloc[1])  # der weit entfernte Punkt
    assert np.isfinite(ergebnis.iloc[0]) and np.isfinite(ergebnis.iloc[2])


def test_distance_to_nearest_ohne_treffer_und_ohne_daten():
    punkte = _points([(13.0, 52.0)])
    leer = gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")

    assert np.isinf(campaign.distance_to_nearest(punkte, leer, max_distance_m=50).iloc[0])
    assert campaign.distance_to_nearest(_points([]), _line_north_south(13.0), 50).empty


def test_distance_to_nearest_lehnt_doppelten_index_ab():
    punkte = _points([(13.0, 52.0), (13.0, 52.0)])
    punkte.index = [7, 7]
    with pytest.raises(ValueError, match="eindeutigen Index"):
        campaign.distance_to_nearest(punkte, _line_north_south(13.0), 50)


# --- Time filters ----------------------------------------------------------


def test_months_seen_zaehlt_kalendermonate():
    signs = pd.DataFrame(
        {
            "first_seen_at": ["2025-01-31", "2025-01-01", "2024-12-31"],
            "last_seen_at": ["2025-02-01", "2025-01-28", "2025-01-01"],
        }
    )
    # Wie der Vorgaenger: Monatsgrenzen zaehlen, nicht volle 30-Tage-Zeitraeume.
    assert list(campaign.months_seen(signs)) == [1, 0, 1]


def test_filter_stable_signs_siebt_frisch_und_kurzlebig_aus():
    signs = gpd.GeoDataFrame(
        {
            "id": [1, 2, 3],
            "first_seen_at": ["2020-01-01", "2026-01-01", "2020-01-01"],
            "last_seen_at": ["2026-06-01", "2026-06-01", "2025-01-01"],
            "geometry": [Point(13, 52)] * 3,
        },
        crs="EPSG:4326",
    )
    uebrig = campaign.filter_stable_signs(signs, seen_after="2025-07-01", min_months=9, verbose=False)

    # 1 bleibt; 2 steht erst seit 5 Monaten; 3 wurde zuletzt vor dem Stichtag gesehen.
    assert list(uebrig["id"]) == [1]


def test_filter_stable_signs_behaelt_den_index():
    """Der Index wird beim Export zur Top-Level-id der GeoJSON-Features.

    Neu durchnummerieren wuerde die ids aller Features stillschweigend
    verschieben - tippecanoe traegt sie in die Vector Tiles.
    """
    signs = gpd.GeoDataFrame(
        {
            "id": [1, 2, 3],
            "first_seen_at": ["2020-01-01"] * 3,
            "last_seen_at": ["2026-06-01", "2020-01-01", "2026-06-01"],
            "geometry": [Point(13, 52)] * 3,
        },
        crs="EPSG:4326",
    )
    uebrig = campaign.filter_stable_signs(signs, "2025-07-01", min_months=0, verbose=False)

    assert list(uebrig.index) == [0, 2]  # nicht [0, 1]


def test_filter_stable_signs_ohne_mindestzeit_wirft_nichts_weg():
    """min_months=0 darf auch Zeilen mit unparsbarem Datum behalten.

    Sonst faellt so eine Zeile still raus: die Monatsdifferenz waere NaN, und
    NaN >= 0 ist False.
    """
    signs = gpd.GeoDataFrame(
        {
            "id": [1, 2],
            "first_seen_at": ["2020-01-01", "kaputt"],
            "last_seen_at": ["2026-06-01", "2026-06-01"],
            "geometry": [Point(13, 52)] * 2,
        },
        crs="EPSG:4326",
    )
    assert list(campaign.filter_stable_signs(signs, "2025-07-01", 0, verbose=False)["id"]) == [1, 2]


# --- Loading: guard, columns, order, boundary, mirror ------------------------


def _write_signs(folder, name, rows):
    gdf = gpd.GeoDataFrame(
        {
            "id": [r[0] for r in rows],
            "value": [r[1] for r in rows],
            "first_seen_at": ["2025-01-01"] * len(rows),
            "last_seen_at": ["2026-01-01"] * len(rows),
            "extra": ["ungenutzt"] * len(rows),
            "geometry": [Point(13, 52)] * len(rows),
        },
        crs="EPSG:4326",
    )
    gdf.to_parquet(folder / f"mapillary_traffic-signs_{name}_latest.parquet")


def _write_markings(folder, name, rows):
    gdf = gpd.GeoDataFrame(
        {
            "id": [r[0] for r in rows],
            "value": [r[1] for r in rows],
            "first_seen_at": ["2025-01-01"] * len(rows),
            "last_seen_at": ["2026-01-01"] * len(rows),
            "geometry": [Point(13, 52)] * len(rows),
        },
        crs="EPSG:4326",
    )
    gdf.to_parquet(folder / f"mapillary_map-feature-points_{name}_latest.parquet")


def test_load_features_guard_schlaegt_bei_fehlender_datei_an(tmp_path):
    """Der Vorfall vom 26.08.2026: ein Bundesland fehlt und niemand merkt es."""
    _write_signs(tmp_path, "DE-HB", [(1, "regulatory--bicycles-only--g1")])

    with pytest.raises(RuntimeError, match="1 von 16"):
        campaign.load_features(tmp_path, expect_files=16, verbose=False)

    # Ohne Sollwert laeuft es durch.
    assert len(campaign.load_features(tmp_path, verbose=False)) == 1


def test_load_features_liest_nur_die_gewuenschten_spalten(tmp_path):
    _write_signs(tmp_path, "DE-HB", [(1, "regulatory--bicycles-only--g1")])
    spalten = ["id", "value", "geometry"]

    geladen = campaign.load_features(tmp_path, columns=spalten, verbose=False)
    assert "extra" not in geladen.columns
    assert set(spalten) <= set(geladen.columns)


def test_load_features_erstes_vorkommen_gewinnt(tmp_path):
    # Dieselbe id in zwei Bundeslaendern - Punkte an der Grenze gibt es wirklich.
    _write_signs(tmp_path, "DE-BB", [(7, "regulatory--bicycles-only--g1")])
    _write_signs(tmp_path, "DE-BE", [(7, "regulatory--shared-path-pedestrians-and-bicycles--g1")])

    geladen = campaign.load_features(tmp_path, verbose=False)
    assert len(geladen) == 1
    # DE-BB kommt alphabetisch zuerst.
    assert geladen.iloc[0]["value"] == "regulatory--bicycles-only--g1"


def test_load_features_ohne_treffer(tmp_path):
    _write_signs(tmp_path, "DE-HB", [(1, "regulatory--stop--g1")])
    with pytest.raises(RuntimeError, match="keine Erkennungen"):
        campaign.load_features(tmp_path, values=["regulatory--bicycles-only--g1"], verbose=False)


def test_load_features_waehlt_den_datensatz_ueber_den_prefix(tmp_path):
    """Beide Datensaetze liegen im selben Ordner - der Prefix trennt sie.

    Beim Bau des mk-Notebooks las load_features zuerst die Verkehrszeichen und
    suchte darin nach Markierungen. Der Guard hat das laut gemeldet, still
    leer zurueckzugeben waere schlimmer gewesen.
    """
    _write_signs(tmp_path, "DE-HB", [(1, "regulatory--bicycles-only--g1")])
    _write_markings(tmp_path, "DE-HB", [(2, "marking--discrete--symbol--bicycle")])

    zeichen = campaign.load_features(tmp_path, prefix=campaign.PREFIX_ZEICHEN, verbose=False)
    marks = campaign.load_features(tmp_path, prefix=campaign.PREFIX_MARKIERUNGEN, verbose=False)

    assert list(zeichen["id"]) == [1]
    assert list(marks["id"]) == [2]


def test_load_features_filtert_beim_lesen_und_praegt_den_index(tmp_path):
    """Frueh filtern bestimmt den Index - und der wird zur Feature-id.

    Wer erst nach dem Zusammenfuegen filtert, bekommt dieselben Zeilen mit
    anderen ids, und tippecanoe traegt die in die Vector Tiles.
    """
    gdf = gpd.GeoDataFrame(
        {
            "id": [1, 2, 3],
            "value": ["marking--discrete--symbol--bicycle"] * 3,
            "first_seen_at": ["2020-01-01", "1970-01-01", "2020-01-01"],
            "last_seen_at": ["2026-01-01", "2026-01-01", "2022-01-01"],
            "geometry": [Point(13, 52)] * 3,
        },
        crs="EPSG:4326",
    )
    gdf.to_parquet(tmp_path / "mapillary_map-feature-points_DE-HB_latest.parquet")

    geladen = campaign.load_features(
        tmp_path,
        prefix=campaign.PREFIX_MARKIERUNGEN,
        seen_after="2023-01-01",
        first_seen_after="2000-01-01",
        verbose=False,
    )
    # id 2 faellt am first_seen_at raus, id 3 am last_seen_at.
    assert list(geladen["id"]) == [1]
    # Dicht durchnummeriert ab 0, weil vor dem Zusammenfuegen gefiltert wurde.
    assert list(geladen.index) == [0]


def test_count_expected_states(tmp_path):
    assert campaign.count_expected_states(tmp_path / "DE-*_tiles.json") is None
    (tmp_path / "DE-HB_tiles.json").write_text("{}")
    (tmp_path / "DE-BE_tiles.json").write_text("{}")
    assert campaign.count_expected_states(tmp_path / "DE-*_tiles.json") == 2


def test_clip_to_boundary_wirft_punkte_ausserhalb_weg():
    punkte = _points([(13.0, 52.0), (20.0, 52.0)], ids=[1, 2])
    grenze = gpd.GeoDataFrame(
        geometry=[Polygon([(12, 51), (14, 51), (14, 53), (12, 53)])], crs="EPSG:4326"
    )
    assert list(campaign.clip_to_boundary(punkte, grenze, verbose=False)["id"]) == [1]


def test_clip_to_boundary_behaelt_den_index():
    """Wie filter_stable_signs: der Index wird beim Export zur Feature-id."""
    punkte = _points([(13.0, 52.0), (20.0, 52.0), (13.5, 52.0)], ids=[1, 2, 3])
    grenze = gpd.GeoDataFrame(
        geometry=[Polygon([(12, 51), (14, 51), (14, 53), (12, 53)])], crs="EPSG:4326"
    )
    drin = campaign.clip_to_boundary(punkte, grenze, verbose=False)

    assert list(drin["id"]) == [1, 3]
    assert list(drin.index) == [0, 2]  # nicht [0, 1]


def test_sync_features_spiegelt_auch_das_manifest(tmp_path, monkeypatch):
    """Parquets und Manifest muessen denselben Stand beschreiben.

    Am 20.09.2026 lagen lokal Parquets vom 17.09. neben einer
    ml-mf_metadata.json vom 01.07. - sync_features holte die Dateien, schrieb
    das Manifest aber nicht mit. radinfra_1_export zieht aus dieser Datei das
    Datum fuer die veroeffentlichte README.
    """
    manifest = {"bundeslaender": {}, "processed_date": "2026-09-17T06:28:45+00:00"}

    class _Antwort:
        status_code = 200

        def json(self):
            return manifest

        def raise_for_status(self):
            pass

    monkeypatch.setattr(campaign.requests, "get", lambda *a, **k: _Antwort())

    (tmp_path / "ml-ts_metadata.json").write_text('{"processed_date": "2026-07-01T00:00:00+00:00"}')
    campaign.sync_features(tmp_path, verbose=False)

    gespiegelt = json.loads((tmp_path / "ml-ts_metadata.json").read_text(encoding="utf-8"))
    assert gespiegelt["processed_date"] == "2026-09-17T06:28:45+00:00"


# --- Newest image ----------------------------------------------------------


class _FakeSession:
    """Antwortet wie die Graph-API, ohne Netz."""

    def __init__(self, features):
        self.features = features
        self.calls = []

    def get(self, url, params=None, timeout=None):
        ids = params["ids"].split(",")
        self.calls.append(ids)
        return _FakeResponse({i: self.features[i] for i in ids if i in self.features})


class _FakeResponse:
    status_code = 200

    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self.payload


@pytest.fixture
def fake_graph(monkeypatch):
    def install(features):
        session = _FakeSession(features)
        monkeypatch.setattr(campaign, "_graph_session", lambda token: session)
        return session

    return install


def test_newest_image_ids_nimmt_neuestes_bild(fake_graph):
    """Das letzte Listenelement ist nicht das neueste - genau hier lag der Fehler.

    An 600 Bremer Radwegzeichen wich das letzte Listenelement in 84 % der
    Faelle vom neuesten Bild ab, in 10 % um mehr als ein Jahr.
    """
    fake_graph(
        {
            "100": {
                "id": "100",
                "images": {
                    "data": [
                        {"id": "neu", "captured_at": 1789215976209},   # 2026-09
                        {"id": "alt", "captured_at": 1485610472866},   # 2017-01
                        {"id": "mittel", "captured_at": 1580551793187},  # 2020-02  <- letztes
                    ]
                },
            }
        }
    )
    ergebnis = campaign.newest_image_ids([100], token="x", verbose=False)

    assert ergebnis.loc["100", "image_id"] == "neu"
    assert ergebnis.loc["100", "image_captured_at"].year == 2026


def test_newest_image_ids_picks_the_same_image_on_a_tie(fake_graph):
    """Two images of one capture share a timestamp; the API order varies between calls."""
    gleichzeitig = [{"id": "111", "captured_at": 5}, {"id": "222", "captured_at": 5}]
    for bilder in (gleichzeitig, gleichzeitig[::-1]):
        fake_graph({"100": {"id": "100", "images": {"data": bilder}}})
        assert campaign.newest_image_ids([100], token="x", verbose=False).loc["100", "image_id"] == "222"


def test_newest_image_ids_haelt_grosse_ids_als_string(fake_graph):
    """Mapillary-IDs uebersteigen 2**53; als Zahl wuerden sie gerundet."""
    gross = "9007199254740993"  # 2**53 + 1
    fake_graph({"100": {"id": "100", "images": {"data": [{"id": gross, "captured_at": 1}]}}})

    ergebnis = campaign.newest_image_ids([100], token="x", verbose=False)
    assert ergebnis.loc["100", "image_id"] == gross


def test_newest_image_ids_stapelt_anfragen(fake_graph):
    features = {str(i): {"id": str(i), "images": {"data": [{"id": f"b{i}", "captured_at": i}]}} for i in range(120)}
    session = fake_graph(features)

    ergebnis = campaign.newest_image_ids(list(range(120)), token="x", chunk_size=50, workers=2, verbose=False)

    assert len(ergebnis) == 120
    assert [len(c) for c in sorted(session.calls, key=len, reverse=True)] == [50, 50, 20]


def test_newest_image_ids_bricht_bei_zu_vielen_luecken_ab(fake_graph):
    """Ein stilles Teilergebnis waere schlimmer als ein Abbruch: Aufgaben ohne
    Foto sehen in MapRoulette genauso plausibel aus wie vollstaendige."""
    fake_graph({"0": {"id": "0", "images": {"data": [{"id": "b", "captured_at": 1}]}}})

    with pytest.raises(RuntimeError, match="ohne Bild"):
        campaign.newest_image_ids(list(range(10)), token="x", verbose=False)


def test_newest_image_ids_vertraegt_features_ohne_bilder(fake_graph):
    fake_graph(
        {
            "1": {"id": "1", "images": {"data": []}},
            "2": {"id": "2", "images": {"data": [{"id": "b2", "captured_at": 5}]}},
        }
    )
    ergebnis = campaign.newest_image_ids([1, 2], token="x", max_fehlerquote=0.6, verbose=False)

    assert pd.isna(ergebnis.loc["1", "image_id"])
    assert ergebnis.loc["2", "image_id"] == "b2"


# --- MapRoulette GeoJSON and comparison ------------------------------------


def _task_frame(**overrides):
    daten = {
        "id": [2018084012013699],
        "image_id": ["3201522749994681"],
        "geometry": [Point(8.77, 53.10)],
    }
    daten.update(overrides)
    return gpd.GeoDataFrame(daten, crs="EPSG:4326")


def _aufgabe(row):
    return {"image_id": row["image_id"]}


def test_build_maproulette_geojson_takes_the_properties_from_the_campaign():
    collection = campaign.build_maproulette_geojson(_task_frame(), lambda row: {"name": f"Aufgabe {row['id']}"})
    feature = collection["features"][0]

    # The id stays a string: Mapillary ids exceed 2**53.
    assert feature["id"] == "2018084012013699"
    assert feature["properties"] == {"name": "Aufgabe 2018084012013699"}
    assert feature["geometry"] == {"type": "Point", "coordinates": (8.77, 53.1)}


def test_bild_zeile_ends_the_link_line_with_a_hard_break():
    zeile = campaign.bild_zeile("https://example.invalid/bild", pd.Timestamp("2026-09-12", tz="UTC"), "das Zeichen")
    link, hinweis = zeile.split("\n")

    assert link.endswith(campaign.BR) and campaign.BR == "  "
    assert hinweis == "(Das ist die neueste Aufnahme, auf der das Zeichen erkannt wurde: **12.09.2026**.)"
    assert campaign.bild_zeile(None, pd.NaT, "das Zeichen") == "- 📷 Kein Mapillary-Bild verfügbar."


def test_abstand_text():
    assert campaign.abstand_text(27.4, 30) == "ca. 27 m"
    assert campaign.abstand_text(np.inf, 100) == "mehr als 100 m"


def test_write_geojson_schreibt_atomar(tmp_path):
    ziel = tmp_path / "tasks.geojson"
    campaign.write_geojson(campaign.build_maproulette_geojson(_task_frame(), _aufgabe), ziel, verbose=False)

    assert json.loads(ziel.read_text(encoding="utf-8"))["features"][0]["id"] == "2018084012013699"
    assert not list(tmp_path.glob("*.tmp"))


def test_compare_task_sets_zeigt_bildwechsel(tmp_path):
    alt = {
        "type": "FeatureCollection",
        "features": [
            {"id": "1", "properties": {"image_id": "altes_bild"}},
            {"id": "2", "properties": {"image_id": "gleich"}},
            {"id": "3", "properties": {"image_id": "weg"}},
        ],
    }
    alt_pfad = tmp_path / "alt.geojson"
    alt_pfad.write_text(json.dumps(alt), encoding="utf-8")

    neu = {
        "type": "FeatureCollection",
        "features": [
            {"id": "1", "properties": {"image_id": "neues_bild"}},
            {"id": "2", "properties": {"image_id": "gleich"}},
            {"id": "4", "properties": {"image_id": "neu"}},
        ],
    }
    vergleich = campaign.compare_task_sets(alt_pfad, neu)

    assert vergleich["gemeinsam"] == 2
    assert vergleich["nur_alt"] == ["3"]
    assert vergleich["nur_neu"] == ["4"]
    assert vergleich["anderes_bild"] == ["1"]

    # Mit dem bereits eingelesenen Stand muss dasselbe herauskommen.
    assert campaign.compare_task_sets(campaign.read_geojson(alt_pfad), neu) == vergleich


def test_read_geojson_vor_dem_ueberschreiben(tmp_path):
    """Ziel- und Vergleichsdatei sind dieselbe - MapRoulette braucht einen festen Pfad.

    Deshalb muss der alte Inhalt vor dem Schreiben in der Hand sein; danach ist
    er weg.
    """
    ziel = tmp_path / "tasks.geojson"
    assert campaign.read_geojson(ziel) is None  # erster Lauf, noch nichts da

    campaign.write_geojson(campaign.build_maproulette_geojson(_task_frame(), _aufgabe), ziel, verbose=False)
    vorher = campaign.read_geojson(ziel)

    campaign.write_geojson(
        campaign.build_maproulette_geojson(_task_frame(image_id=["9999"]), _aufgabe), ziel, verbose=False
    )
    vergleich = campaign.compare_task_sets(vorher, campaign.read_geojson(ziel))

    assert vergleich["gemeinsam"] == 1
    assert len(vergleich["anderes_bild"]) == 1


def test_compare_task_sets_ohne_vorherigen_stand(tmp_path):
    with pytest.raises(FileNotFoundError):
        campaign.compare_task_sets(tmp_path / "gibt_es_nicht.geojson", {"features": []})
