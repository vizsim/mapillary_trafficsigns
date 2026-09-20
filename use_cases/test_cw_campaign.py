"""Tests fuer cw_campaign - die Rechenschritte, ohne Netz.

Der wichtigste Test ist `test_newest_image_ids_nimmt_neuestes_bild`: er
beschreibt genau den Fehler des Vorgaengers, der das letzte Element einer
unsortierten Liste nahm.

Lauf: `uv run pytest test_cw_campaign.py` in use_cases/.
"""

import ast
import gzip
import json
import re
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import LineString, Point, Polygon

import cw_campaign as cw


def _points(coords, ids=None):
    ids = ids if ids is not None else list(range(len(coords)))
    return gpd.GeoDataFrame(
        {"id": ids, "geometry": [Point(x, y) for x, y in coords]}, crs="EPSG:4326"
    )


def _line_north_south(lon, lat0=52.0, lat1=52.01):
    return gpd.GeoDataFrame(geometry=[LineString([(lon, lat0), (lon, lat1)])], crs="EPSG:4326")


# --- Abstandsrechnung -------------------------------------------------------


def test_distance_to_nearest_misst_metrisch():
    # Ein Punkt gut 34 m oestlich einer Nord-Sued-Linie (bei 52 N sind
    # 0,0005 Grad Laenge rund 34 m).
    punkte = _points([(13.0005, 52.005)])
    linie = _line_north_south(13.0)

    weit = cw.distance_to_nearest(punkte, linie, max_distance_m=50)
    assert 30 < weit.iloc[0] < 40

    # Ausserhalb des Suchradius bleibt inf, statt still eine falsche Zahl zu liefern.
    eng = cw.distance_to_nearest(punkte, linie, max_distance_m=20)
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
    assert cw.distance_to_nearest(punkte, linien, max_distance_m=50).iloc[0] < 20


def test_distance_to_nearest_behaelt_den_index():
    punkte = _points([(13.0005, 52.005), (14.0, 52.0), (13.0005, 52.006)])
    ergebnis = cw.distance_to_nearest(punkte, _line_north_south(13.0), max_distance_m=50)

    assert list(ergebnis.index) == list(punkte.index)
    assert np.isinf(ergebnis.iloc[1])  # der weit entfernte Punkt
    assert np.isfinite(ergebnis.iloc[0]) and np.isfinite(ergebnis.iloc[2])


def test_distance_to_nearest_ohne_treffer_und_ohne_daten():
    punkte = _points([(13.0, 52.0)])
    leer = gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")

    assert np.isinf(cw.distance_to_nearest(punkte, leer, max_distance_m=50).iloc[0])
    assert cw.distance_to_nearest(_points([]), _line_north_south(13.0), 50).empty


def test_distance_to_nearest_lehnt_doppelten_index_ab():
    punkte = _points([(13.0, 52.0), (13.0, 52.0)])
    punkte.index = [7, 7]
    with pytest.raises(ValueError, match="eindeutigen Index"):
        cw.distance_to_nearest(punkte, _line_north_south(13.0), 50)


# --- Prioritaeten -----------------------------------------------------------


def test_assign_priority_bildet_die_stufen_ab():
    abstand = pd.Series([np.inf, 40.0, 30.0, 29.9, 25.0, 24.9, 0.0])
    prio = cw.assign_priority(abstand)

    assert list(prio[:3]) == [0, 0, 0]       # ab 30 m: hohe Prioritaet
    assert list(prio[3:5]) == [1, 1]         # 25 bis unter 30 m: mittel
    assert prio[5:].isna().all()             # darunter: keine Aufgabe


# --- Zeitfilter -------------------------------------------------------------


def test_months_seen_zaehlt_kalendermonate():
    signs = pd.DataFrame(
        {
            "first_seen_at": ["2025-01-31", "2025-01-01", "2024-12-31"],
            "last_seen_at": ["2025-02-01", "2025-01-28", "2025-01-01"],
        }
    )
    # Wie der Vorgaenger: Monatsgrenzen zaehlen, nicht volle 30-Tage-Zeitraeume.
    assert list(cw.months_seen(signs)) == [1, 0, 1]


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
    uebrig = cw.filter_stable_signs(signs, seen_after="2025-07-01", min_months=9, verbose=False)

    # 1 bleibt; 2 steht erst seit 5 Monaten; 3 wurde zuletzt vor dem Stichtag gesehen.
    assert list(uebrig["id"]) == [1]


# --- Radinfra-Filter --------------------------------------------------------


def test_filter_cycle_infrastructure_erkennt_alle_varianten():
    ways = gpd.GeoDataFrame(
        {
            "highway": ["cycleway", "residential", "residential", "residential", "residential"],
            "bicycle": [None, "designated", None, None, "yes"],
            "cycleway_right": [None, None, "track", "no", None],
            "sidewalk_bicycle": [None, None, None, None, None],
            "geometry": [LineString([(0, 0), (1, 1)])] * 5,
        },
        crs="EPSG:4326",
    )
    treffer = cw.filter_cycle_infrastructure(ways, verbose=False)

    # highway=cycleway, bicycle=designated und cycleway:right=track zaehlen;
    # cycleway:right=no und bicycle=yes zaehlen nicht.
    assert list(treffer.index) == [0, 1, 2]


def test_filter_cycle_infrastructure_ueberspringt_fehlende_spalten():
    ways = gpd.GeoDataFrame(
        {"highway": ["cycleway", "residential"], "geometry": [LineString([(0, 0), (1, 1)])] * 2},
        crs="EPSG:4326",
    )
    # Darf nicht an den nicht vorhandenen cycleway:*-Spalten scheitern.
    assert list(cw.filter_cycle_infrastructure(ways, verbose=False).index) == [0]


def test_sidewalk_bicycle_wird_als_radinfra_gewertet():
    """Der Vorgaenger liess diese Spalte aus - der TODO-Kommentar ist erledigt."""
    ways = gpd.GeoDataFrame(
        {
            "highway": ["residential"],
            "sidewalk_bicycle": ["designated"],
            "geometry": [LineString([(0, 0), (1, 1)])],
        },
        crs="EPSG:4326",
    )
    assert len(cw.filter_cycle_infrastructure(ways, verbose=False)) == 1


# --- Bildauswahl ------------------------------------------------------------


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
        monkeypatch.setattr(cw, "_graph_session", lambda token: session)
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
    ergebnis = cw.newest_image_ids([100], token="x", verbose=False)

    assert ergebnis.loc["100", "image_id"] == "neu"
    assert ergebnis.loc["100", "image_captured_at"].year == 2026


def test_newest_image_ids_haelt_grosse_ids_als_string(fake_graph):
    """Mapillary-IDs uebersteigen 2**53; als Zahl wuerden sie gerundet."""
    gross = "9007199254740993"  # 2**53 + 1
    fake_graph({"100": {"id": "100", "images": {"data": [{"id": gross, "captured_at": 1}]}}})

    ergebnis = cw.newest_image_ids([100], token="x", verbose=False)
    assert ergebnis.loc["100", "image_id"] == gross


def test_newest_image_ids_stapelt_anfragen(fake_graph):
    features = {str(i): {"id": str(i), "images": {"data": [{"id": f"b{i}", "captured_at": i}]}} for i in range(120)}
    session = fake_graph(features)

    ergebnis = cw.newest_image_ids(list(range(120)), token="x", chunk_size=50, workers=2, verbose=False)

    assert len(ergebnis) == 120
    assert [len(c) for c in sorted(session.calls, key=len, reverse=True)] == [50, 50, 20]


def test_newest_image_ids_bricht_bei_zu_vielen_luecken_ab(fake_graph):
    """Ein stilles Teilergebnis waere schlimmer als ein Abbruch: Aufgaben ohne
    Foto sehen in MapRoulette genauso plausibel aus wie vollstaendige."""
    fake_graph({"0": {"id": "0", "images": {"data": [{"id": "b", "captured_at": 1}]}}})

    with pytest.raises(RuntimeError, match="ohne Bild"):
        cw.newest_image_ids(list(range(10)), token="x", verbose=False)


def test_newest_image_ids_vertraegt_features_ohne_bilder(fake_graph):
    fake_graph(
        {
            "1": {"id": "1", "images": {"data": []}},
            "2": {"id": "2", "images": {"data": [{"id": "b2", "captured_at": 5}]}},
        }
    )
    ergebnis = cw.newest_image_ids([1, 2], token="x", max_fehlerquote=0.6, verbose=False)

    assert pd.isna(ergebnis.loc["1", "image_id"])
    assert ergebnis.loc["2", "image_id"] == "b2"


# --- Export -----------------------------------------------------------------


def _task_frame(**overrides):
    daten = {
        "id": [2018084012013699],
        "VZ": [240],
        "dist_cw_m": [27.4],
        "prio": [1],
        "prio_text": ["🟨 Task mit mittlerer Wahrscheinlichkeit valide"],
        "image_id": ["3201522749994681"],
        "image_captured_at": [pd.Timestamp("2026-09-12", tz="UTC")],
        "geometry": [Point(8.77, 53.10)],
    }
    daten.update(overrides)
    return gpd.GeoDataFrame(daten, crs="EPSG:4326")


def test_build_maproulette_geojson_baut_erwartete_felder():
    collection = cw.build_maproulette_geojson(_task_frame())
    feature = collection["features"][0]

    assert feature["id"] == "2018084012013699"
    assert feature["properties"]["image_id"] == "3201522749994681"
    assert feature["properties"]["priority"] == 1
    assert "pKey=3201522749994681" in feature["properties"]["instruction"]
    assert "ca. 27 m" in feature["properties"]["instruction"]
    assert "12.09.2026" in feature["properties"]["instruction"]


def test_build_maproulette_geojson_ohne_bild():
    collection = cw.build_maproulette_geojson(
        _task_frame(image_id=[None], image_captured_at=[pd.NaT])
    )
    instruction = collection["features"][0]["properties"]["instruction"]

    assert collection["features"][0]["properties"]["image_id"] is None
    assert "Kein Mapillary-Bild" in instruction
    assert "mapillary.com/app" not in instruction


def test_instruction_behaelt_die_harten_zeilenumbrueche():
    """Markdown braucht zwei Leerzeichen am Zeilenende.

    Beim Schreiben des Moduls hat ein Editor genau diese Leerzeichen entfernt,
    worauf die Hinweise in MapRoulette an die Linkzeile anschlossen. Seitdem
    stehen sie als Konstante `_BR` im Quelltext - dieser Test haelt das fest.
    """
    instruction = cw.build_maproulette_geojson(_task_frame())["features"][0]["properties"]["instruction"]
    zeilen = instruction.splitlines()

    for kennzeichen in ("Mapillary-Bild anzeigen", "TILDA ansehen"):
        zeile = next(z for z in zeilen if kennzeichen in z)
        assert zeile.endswith("  "), f"harter Umbruch fehlt nach {kennzeichen!r}"
        # Direkt darunter muss der Hinweis stehen, sonst laeuft der Umbruch ins Leere.
        assert zeilen[zeilen.index(zeile) + 1].startswith("(")


def test_build_maproulette_geojson_bei_unendlichem_abstand():
    collection = cw.build_maproulette_geojson(_task_frame(dist_cw_m=[np.inf], prio=[0]))
    assert "mehr als 30 m" in collection["features"][0]["properties"]["instruction"]


def test_write_geojson_schreibt_atomar(tmp_path):
    ziel = tmp_path / "tasks.geojson"
    cw.write_geojson(cw.build_maproulette_geojson(_task_frame()), ziel, verbose=False)

    assert json.loads(ziel.read_text(encoding="utf-8"))["features"][0]["id"] == "2018084012013699"
    assert not list(tmp_path.glob("*.tmp"))


# --- Vergleich --------------------------------------------------------------


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
    vergleich = cw.compare_task_sets(alt_pfad, neu)

    assert vergleich["gemeinsam"] == 2
    assert vergleich["nur_alt"] == ["3"]
    assert vergleich["nur_neu"] == ["4"]
    assert vergleich["anderes_bild"] == ["1"]

    # Mit dem bereits eingelesenen Stand muss dasselbe herauskommen.
    assert cw.compare_task_sets(cw.read_geojson(alt_pfad), neu) == vergleich


def test_read_geojson_vor_dem_ueberschreiben(tmp_path):
    """Ziel- und Vergleichsdatei sind dieselbe - MapRoulette braucht einen festen Pfad.

    Deshalb muss der alte Inhalt vor dem Schreiben in der Hand sein; danach ist
    er weg.
    """
    ziel = tmp_path / "tasks.geojson"
    assert cw.read_geojson(ziel) is None  # erster Lauf, noch nichts da

    cw.write_geojson(cw.build_maproulette_geojson(_task_frame()), ziel, verbose=False)
    vorher = cw.read_geojson(ziel)

    cw.write_geojson(
        cw.build_maproulette_geojson(_task_frame(image_id=["9999"])), ziel, verbose=False
    )
    vergleich = cw.compare_task_sets(vorher, cw.read_geojson(ziel))

    assert vergleich["gemeinsam"] == 1
    assert len(vergleich["anderes_bild"]) == 1


def test_compare_task_sets_ohne_vorherigen_stand(tmp_path):
    with pytest.raises(FileNotFoundError):
        cw.compare_task_sets(tmp_path / "gibt_es_nicht.geojson", {"features": []})


# --- Zeichentabelle ---------------------------------------------------------


def test_radweg_zeichen_leitet_sich_aus_der_tabelle_ab():
    """Eine Quelle fuer 1b_ und xb_ - die Nummern duerfen nicht auseinanderlaufen."""
    assert cw.RADWEG_ZEICHEN == {
        "regulatory--bicycles-only--g1": 237,
        "regulatory--shared-path-pedestrians-and-bicycles--g1": 240,
        "regulatory--dual-path-bicycles-and-pedestrians--g1": 241,
        "regulatory--dual-path-pedestrians-and-bicycles--g1": 241,
    }
    # Zusatzzeichen ordnen keine eigene Radinfra an, gehoeren also nicht in die Kampagne.
    assert "complementary--except-bicycles--g1" in cw.ZEICHEN
    assert "complementary--except-bicycles--g1" not in cw.RADWEG_ZEICHEN


def test_readme_zeichen_deckt_die_tabelle_ab():
    aus_tabelle = {code for code, _ in cw.ZEICHEN.values()}
    aus_readme = {eintrag[0] for eintrag in cw.README_ZEICHEN}
    assert aus_tabelle == aus_readme


# --- Laden: Guard, Spalten, Reihenfolge -------------------------------------


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
        cw.load_features(tmp_path, expect_files=16, verbose=False)

    # Ohne Sollwert laeuft es durch.
    assert len(cw.load_features(tmp_path, verbose=False)) == 1


def test_load_features_liest_nur_die_gewuenschten_spalten(tmp_path):
    _write_signs(tmp_path, "DE-HB", [(1, "regulatory--bicycles-only--g1")])
    spalten = ["id", "value", "geometry"]

    geladen = cw.load_features(tmp_path, columns=spalten, verbose=False)
    assert "extra" not in geladen.columns
    assert set(spalten) <= set(geladen.columns)


def test_load_features_erstes_vorkommen_gewinnt(tmp_path):
    # Dieselbe id in zwei Bundeslaendern - Punkte an der Grenze gibt es wirklich.
    _write_signs(tmp_path, "DE-BB", [(7, "regulatory--bicycles-only--g1")])
    _write_signs(tmp_path, "DE-BE", [(7, "regulatory--shared-path-pedestrians-and-bicycles--g1")])

    geladen = cw.load_features(tmp_path, verbose=False)
    assert len(geladen) == 1
    # DE-BB kommt alphabetisch zuerst.
    assert geladen.iloc[0]["value"] == "regulatory--bicycles-only--g1"


def test_load_features_ohne_treffer(tmp_path):
    _write_signs(tmp_path, "DE-HB", [(1, "regulatory--stop--g1")])
    with pytest.raises(RuntimeError, match="keine Erkennungen"):
        cw.load_features(tmp_path, values=cw.ZEICHEN, verbose=False)


def test_load_features_waehlt_den_datensatz_ueber_den_prefix(tmp_path):
    """Beide Datensaetze liegen im selben Ordner - der Prefix trennt sie.

    Beim Bau des mk-Notebooks las load_features zuerst die Verkehrszeichen und
    suchte darin nach Markierungen. Der Guard hat das laut gemeldet, still
    leer zurueckzugeben waere schlimmer gewesen.
    """
    _write_signs(tmp_path, "DE-HB", [(1, "regulatory--bicycles-only--g1")])
    _write_markings(tmp_path, "DE-HB", [(2, "marking--discrete--symbol--bicycle")])

    zeichen = cw.load_features(tmp_path, prefix=cw.PREFIX_ZEICHEN, verbose=False)
    marks = cw.load_features(tmp_path, prefix=cw.PREFIX_MARKIERUNGEN, verbose=False)

    assert list(zeichen["id"]) == [1]
    assert list(marks["id"]) == [2]


def test_count_expected_states(tmp_path):
    assert cw.count_expected_states(tmp_path / "DE-*_tiles.json") is None
    (tmp_path / "DE-HB_tiles.json").write_text("{}")
    (tmp_path / "DE-BE_tiles.json").write_text("{}")
    assert cw.count_expected_states(tmp_path / "DE-*_tiles.json") == 2


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
    uebrig = cw.filter_stable_signs(signs, "2025-07-01", min_months=0, verbose=False)

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
    assert list(cw.filter_stable_signs(signs, "2025-07-01", 0, verbose=False)["id"]) == [1, 2]


# --- Hinweise und Beschriftung ----------------------------------------------


def _sign_frame(values, first, last):
    return gpd.GeoDataFrame(
        {
            "id": list(range(len(values))),
            "value": values,
            "first_seen_at": first,
            "last_seen_at": last,
            "geometry": [Point(13, 52)] * len(values),
        },
        crs="EPSG:4326",
    )


def test_add_hinweis_markiert_einmalige_erkennung():
    frame = _sign_frame(
        ["regulatory--bicycles-only--g1"] * 2,
        ["2026-01-01", "2026-01-01"],
        ["2026-01-01", "2026-06-01"],
    )
    hinweise = cw.add_hinweis(frame)["Hinweis"]

    assert hinweise.iloc[0] == cw.HINWEIS_EINMALIG  # gleicher Tag
    assert hinweise.iloc[1] == ""


def test_add_hinweis_haengt_erklaerung_an_1000_33():
    frame = _sign_frame(
        [cw.ZEICHEN_1000_33, cw.ZEICHEN_1000_33],
        ["2026-01-01", "2026-01-01"],
        ["2026-06-01", "2026-01-01"],  # zweites nur einmalig gesehen
    )
    hinweise = cw.add_hinweis(frame)["Hinweis"]

    assert hinweise.iloc[0] == cw.HINWEIS_1000_33
    # Beide Hinweise, durch einen Zeilenumbruch getrennt.
    assert hinweise.iloc[1] == cw.HINWEIS_EINMALIG + "\n" + cw.HINWEIS_1000_33


def test_add_hinweis_vertraegt_unparsbare_daten():
    frame = _sign_frame(["regulatory--bicycles-only--g1"], ["kaputt"], ["2026-06-01"])
    assert cw.add_hinweis(frame)["Hinweis"].iloc[0] == ""


def test_add_sign_labels():
    frame = _sign_frame(
        ["regulatory--bicycles-only--g1", "complementary--bike-route--g1"],
        ["2026-01-01"] * 2,
        ["2026-06-01"] * 2,
    )
    beschriftet = cw.add_sign_labels(frame)

    assert list(beschriftet["traffic_sign"]) == ["DE:237", "DE:1000-33"]
    assert beschriftet["traffic_sign_description"].iloc[1] == "Radverkehr im Gegenverkehr"


# --- Export -----------------------------------------------------------------


def _export_frame():
    frame = _sign_frame(
        ["regulatory--bicycles-only--g1"], ["2026-01-01"], ["2026-06-01"]
    )
    # Eine ungerade id oberhalb von 2**53: als double gerundet waere sie gerade.
    frame["id"] = [9007199254740993]
    frame = cw.add_sign_labels(cw.add_hinweis(frame))
    return frame[cw.EXPORT_SPALTEN]


def test_write_geojson_gz_haelt_grosse_ids_exakt(tmp_path):
    """Regression zu den toten Mapillary-Links: ids ueber 2**53 als JSON-Zahl
    rundet jeder JavaScript-Verbraucher auf den naechsten double."""
    ziel = tmp_path / "out.geojson.gz"
    cw.write_geojson_gz(_export_frame(), ziel, verbose=False)

    with gzip.open(ziel, "rt", encoding="utf-8") as f:
        roh = f.read()
    assert '"id": "9007199254740993"' in roh or '"id":"9007199254740993"' in roh

    # anzahl zaehlt zwei: die Top-Level-id des Features (der Index, hier "0")
    # und die Mapillary-id in den properties. Nur letztere ist gross und ungerade.
    anzahl, gross, ungerade = cw.assert_ids_are_strings(ziel, verbose=False)
    assert (anzahl, gross, ungerade) == (2, 1, 1)


def test_assert_ids_are_strings_schlaegt_bei_zahlen_an(tmp_path):
    ziel = tmp_path / "kaputt.geojson.gz"
    with gzip.open(ziel, "wt", encoding="utf-8") as f:
        f.write('{"features": [{"properties": {"id": 9007199254740992}}]}')

    with pytest.raises(AssertionError, match="JSON-Zahl"):
        cw.assert_ids_are_strings(ziel, verbose=False)


def test_write_geojson_gz_schreibt_atomar(tmp_path):
    ziel = tmp_path / "unter" / "out.geojson.gz"
    cw.write_geojson_gz(_export_frame(), ziel, verbose=False)

    assert ziel.exists()
    assert not list(ziel.parent.glob("*.tmp"))


def test_export_spalten_reihenfolge_ist_festgenagelt():
    """radinfra.de und das pmtiles-Notebook haengen an dieser Reihenfolge."""
    assert cw.EXPORT_SPALTEN == [
        "traffic_sign",
        "traffic_sign_description",
        "Hinweis",
        "first_seen_at",
        "last_seen_at",
        "id",
        "value",
        "geometry",
    ]


# --- README -----------------------------------------------------------------


def test_svg_url_bildet_den_paketnamen_nach():
    assert cw.svg_url("DE:237").endswith("/DE_237.svg")
    assert cw.svg_url("DE:1022-10").endswith("/DE_1022_10.svg")
    assert cw.svg_url("DE:244.2").endswith("/DE_244_2.svg")
    # Gepinnte npm-Version - die frueheren Next.js-Pfade lieferten nach jedem
    # Deploy 404, weil ein Build-Hash darin steckte.
    assert f"converter@{cw.SVG_PKG_VERSION}" in cw.svg_url("DE:237")


def test_build_readme_zaehlt_und_haelt_den_zeilenumbruch():
    readme = cw.build_readme({"Radweg": 42}, "2026-09-20")

    assert "| DE:237 | Radweg |" in readme
    assert "| 42 |" in readme
    assert "| 0 |" in readme  # nicht gezaehlte Zeichen erscheinen mit 0
    assert "created on **2026-09-20**" in readme

    zeile = next(z for z in readme.splitlines() if "detected traffic signs" in z)
    assert zeile.endswith("  "), "harter Markdown-Umbruch fehlt"


def test_build_readme_uebernimmt_die_filterwerte():
    readme = cw.build_readme({}, "2026-09-20", seit="2024-02-03", autobahn_abstand_m=45)
    assert "newer than **2024-02-03**" in readme
    assert "**45 m of motorways**" in readme


# --- Metadaten --------------------------------------------------------------


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

    geladen = cw.load_features(
        tmp_path,
        prefix=cw.PREFIX_MARKIERUNGEN,
        seen_after="2023-01-01",
        first_seen_after="2000-01-01",
        verbose=False,
    )
    # id 2 faellt am first_seen_at raus, id 3 am last_seen_at.
    assert list(geladen["id"]) == [1]
    # Dicht durchnummeriert ab 0, weil vor dem Zusammenfuegen gefiltert wurde.
    assert list(geladen.index) == [0]


def test_clip_to_boundary_behaelt_den_index():
    """Wie filter_stable_signs: der Index wird beim Export zur Feature-id."""
    punkte = _points([(13.0, 52.0), (20.0, 52.0), (13.5, 52.0)], ids=[1, 2, 3])
    grenze = gpd.GeoDataFrame(
        geometry=[Polygon([(12, 51), (14, 51), (14, 53), (12, 53)])], crs="EPSG:4326"
    )
    drin = cw.clip_to_boundary(punkte, grenze, verbose=False)

    assert list(drin["id"]) == [1, 3]
    assert list(drin.index) == [0, 2]  # nicht [0, 1]


def test_filter_by_days_seen():
    frame = _sign_frame(
        ["marking--discrete--symbol--bicycle"] * 3,
        ["2025-01-01", "2025-01-01", "2025-01-01"],
        ["2025-07-01", "2025-06-29", "2026-01-01"],
    )
    uebrig = cw.filter_by_days_seen(frame, 180, verbose=False)

    # 181 Tage bleibt, 179 faellt raus, 365 bleibt.
    assert list(uebrig["id"]) == [0, 2]
    assert list(uebrig.index) == [0, 2]


def test_add_marking_label():
    frame = _sign_frame(["marking--discrete--symbol--bicycle"], ["2025-01-01"], ["2026-01-01"])
    assert cw.add_marking_label(frame)["MapFeaturePoint"].iloc[0] == "Lane marking - symbol (bicycle)"


def test_build_readme_markierungen():
    readme = cw.build_readme_markierungen(
        anzahl=35250, stand="2026-09-17", datensatz_von="2026-09-17",
        zeitraum="2014-03-30 00:00:00 - 2026-09-15 00:00:00",
    )
    assert "**Total detections**: 35250" in readme
    assert "created on **2026-09-17**" in readme
    assert "min. 180 days apart" in readme
    assert "Lane marking - symbol (bicycle)" in readme

    zeile = next(z for z in readme.splitlines() if "detected bicycle markings" in z)
    assert zeile.endswith("  "), "harter Markdown-Umbruch fehlt"


def test_export_spalten_markierungen_ist_festgenagelt():
    assert cw.EXPORT_SPALTEN_MARKIERUNGEN == [
        "MapFeaturePoint", "first_seen_at", "last_seen_at", "id", "value", "geometry",
    ]


def test_sync_features_spiegelt_auch_das_manifest(tmp_path, monkeypatch):
    """Parquets und Manifest muessen denselben Stand beschreiben.

    Am 20.09.2026 lagen lokal Parquets vom 17.09. neben einer
    ml-mf_metadata.json vom 01.07. - sync_features holte die Dateien, schrieb
    das Manifest aber nicht mit. xb_ zieht aus dieser Datei das Datum fuer die
    veroeffentlichte README.
    """
    manifest = {"bundeslaender": {}, "processed_date": "2026-09-17T06:28:45+00:00"}

    class _Antwort:
        status_code = 200

        def json(self):
            return manifest

        def raise_for_status(self):
            pass

    monkeypatch.setattr(cw.requests, "get", lambda *a, **k: _Antwort())

    (tmp_path / "ml-ts_metadata.json").write_text('{"processed_date": "2026-07-01T00:00:00+00:00"}')
    cw.sync_features(tmp_path, verbose=False)

    _, processed_date, _ = cw.read_dataset_metadata(tmp_path / "ml-ts_metadata.json")
    assert processed_date == "2026-09-17T06:28:45+00:00"


def test_read_dataset_metadata(tmp_path):
    assert cw.read_dataset_metadata(tmp_path / "fehlt.json") == (None, None, {})

    pfad = tmp_path / "ml-ts_metadata.json"
    pfad.write_text(json.dumps({
        "ml_data_from": "2026-09-01", "processed_date": "2026-09-15",
        "bundeslaender": {"DE-HB": "x"},
    }))
    assert cw.read_dataset_metadata(pfad) == ("2026-09-01", "2026-09-15", {"DE-HB": "x"})


# --- Beide Umgebungen ------------------------------------------------------


def _dritt_importe(modul_pfad):
    """Alle Drittpakete, die ein Modul importiert - auch innerhalb von Funktionen."""
    baum = ast.parse(Path(modul_pfad).read_text(encoding="utf-8"))
    namen = set()
    for knoten in ast.walk(baum):
        if isinstance(knoten, ast.Import):
            namen.update(a.name.split(".")[0] for a in knoten.names)
        elif isinstance(knoten, ast.ImportFrom) and knoten.level == 0 and knoten.module:
            namen.add(knoten.module.split(".")[0])
    return {n for n in namen if n not in sys.stdlib_module_names}


def _pakete_aus_requirements(pfad):
    gefunden = {}
    for zeile in Path(pfad).read_text(encoding="utf-8").splitlines():
        treffer = re.match(r"^([A-Za-z0-9_.\-]+)\s*==\s*(\S+)", zeile.split("#")[0].strip())
        if treffer:
            gefunden[treffer.group(1).lower().replace("_", "-")] = treffer.group(2)
    return gefunden


def _pakete_aus_pyproject(pfad):
    gefunden = {}
    for zeile in Path(pfad).read_text(encoding="utf-8").splitlines():
        treffer = re.match(r'^\s*"([A-Za-z0-9_.\-]+)\s*==\s*([^"]+)"', zeile)
        if treffer:
            gefunden[treffer.group(1).lower().replace("_", "-")] = treffer.group(2)
    return gefunden


# Importname -> Name auf PyPI, wo beide auseinandergehen.
_PAKETNAME = {"dateutil": "python-dateutil", "yaml": "pyyaml", "PIL": "pillow"}

_REPO = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(
    not (_REPO / "requirements.txt").exists() or not (_REPO / "use_cases" / "pyproject.toml").exists(),
    reason="Abhaengigkeitslisten nicht gefunden",
)
def test_cw_campaign_laeuft_in_beiden_umgebungen():
    """cw_campaign wird aus zwei getrennten Umgebungen importiert.

    1b_ laeuft im uv-Env aus use_cases/pyproject.toml, xb_ woechentlich im
    pip-Env des Worker-Images aus requirements.txt. Jedes Paket, das dieses
    Modul importiert, muss deshalb in beiden Listen stehen - sonst faellt der
    Bruch erst im naechsten Mittwochslauf auf.

    Dieser Test ist bewusst Wegwerfware: sobald das Repo auf ein einziges
    uv-Env umgestellt ist (Schritt 4 in docs/plan_notebooks_zu_python.md),
    kann er weg - dann ist die Invariante strukturell erfuellt.
    """
    server = _pakete_aus_requirements(_REPO / "requirements.txt")
    use_cases = _pakete_aus_pyproject(_REPO / "use_cases" / "pyproject.toml")

    benoetigt = {_PAKETNAME.get(n, n).lower().replace("_", "-") for n in _dritt_importe(cw.__file__)}
    assert benoetigt, "keine Drittimporte gefunden - Parser pruefen"

    fehlt_server = sorted(benoetigt - set(server))
    fehlt_use_cases = sorted(benoetigt - set(use_cases))
    assert not fehlt_server, f"fehlt in requirements.txt (Worker-Image): {fehlt_server}"
    assert not fehlt_use_cases, f"fehlt in use_cases/pyproject.toml: {fehlt_use_cases}"

    abweichend = {p: (server[p], use_cases[p]) for p in benoetigt if server[p] != use_cases[p]}
    assert not abweichend, f"verschiedene Versionen je Umgebung: {abweichend}"


def test_dataset_stand_nimmt_das_juengste_datum():
    assert cw.dataset_stand(["2026-09-01", "2026-09-15"]) == "2026-09-15"
    assert cw.dataset_stand([None, "2026-09-01"]) == "2026-09-01"
    assert cw.dataset_stand([], fallback="2020-01-01") == "2020-01-01"
    assert cw.dataset_stand(["keindatum"], fallback="2020-01-01") == "2020-01-01"


# --- Grenzverschnitt --------------------------------------------------------


def test_clip_to_boundary_wirft_punkte_ausserhalb_weg():
    punkte = _points([(13.0, 52.0), (20.0, 52.0)], ids=[1, 2])
    grenze = gpd.GeoDataFrame(
        geometry=[Polygon([(12, 51), (14, 51), (14, 53), (12, 53)])], crs="EPSG:4326"
    )
    assert list(cw.clip_to_boundary(punkte, grenze, verbose=False)["id"]) == [1]
