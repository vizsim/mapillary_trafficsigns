"""Tests fuer cw_campaign - die Rechenschritte, ohne Netz.

Der wichtigste Test ist `test_newest_image_ids_nimmt_neuestes_bild`: er
beschreibt genau den Fehler des Vorgaengers, der das letzte Element einer
unsortierten Liste nahm.

Lauf: `uv run --project .. pytest test_cw_campaign.py` im Kampagnenordner.
"""

import json

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


# --- Grenzverschnitt --------------------------------------------------------


def test_clip_to_boundary_wirft_punkte_ausserhalb_weg():
    punkte = _points([(13.0, 52.0), (20.0, 52.0)], ids=[1, 2])
    grenze = gpd.GeoDataFrame(
        geometry=[Polygon([(12, 51), (14, 51), (14, 53), (12, 53)])], crs="EPSG:4326"
    )
    assert list(cw.clip_to_boundary(punkte, grenze, verbose=False)["id"]) == [1]
