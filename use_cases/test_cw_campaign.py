"""Tests for cw_campaign - what is specific to the cycleway campaigns, without network.

The generic steps (loading, distances, newest image, comparison) moved to
campaign.py, and their tests to test_campaign.py.

Run: `uv run pytest` in the repo root.
"""

import gzip
import json
import re
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import LineString, Point

import cw_campaign as cw


# --- Prioritaeten -----------------------------------------------------------


def test_assign_priority_bildet_die_stufen_ab():
    abstand = pd.Series([np.inf, 40.0, 30.0, 29.9, 25.0, 24.9, 0.0])
    prio = cw.assign_priority(abstand)

    assert list(prio[:3]) == [0, 0, 0]       # ab 30 m: hohe Prioritaet
    assert list(prio[3:5]) == [1, 1]         # 25 bis unter 30 m: mittel
    assert prio[5:].isna().all()             # darunter: keine Aufgabe


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
    """Markdown needs two spaces at the end of a line for a hard break.

    While the module was written, an editor removed exactly these spaces, and
    the notes in MapRoulette ran on from the link line. Since then they are the
    constant `BR` in campaign.py - this test pins that.
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


# --- Zeichentabelle ---------------------------------------------------------


def test_radweg_zeichen_leitet_sich_aus_der_tabelle_ab():
    """Eine Quelle fuer maproulette_tasks und radinfra_1_export - die Nummern
    duerfen nicht auseinanderlaufen."""
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


def test_readme_zeichen_nutzt_die_beschreibungen_aus_zeichen():
    """Die deutsche Bezeichnung ist der Schluessel in die Zaehlung.

    Sie steht als `traffic_sign_description` in der veroeffentlichten GeoJSON.
    Laeuft sie hier auseinander, zaehlt die README still Nullen - die englische
    daneben darf sich dagegen frei aendern.
    """
    aus_tabelle = {beschreibung for _, beschreibung in cw.ZEICHEN.values()}
    aus_readme = {eintrag[2] for eintrag in cw.README_ZEICHEN}
    assert aus_tabelle == aus_readme


# --- README: Zaehlung, Historie, Deltas -------------------------------------

_ZAEHLUNG = {
    "Radweg": 32401,
    "Gemeinsamer Geh- und Radweg": 75639,
    "Getrennter Geh- und Radweg": 25751,
    "Ende Fahrradstraße": 571,
    "Radfahrer frei": 16153,
    "Radverkehr im Gegenverkehr": 8150,
}


@pytest.mark.parametrize(
    "aktuell, vorher, erwartet",
    [
        (110, 100, "+10"),
        (90, 100, "-10"),
        (100, 100, "+0"),
        (12345, 1, "+12,344"),
        (100, None, cw.NO_VALUE),
        (100, "keine zahl", cw.NO_VALUE),
    ],
)
def test_format_delta(aktuell, vorher, erwartet):
    assert cw.format_delta(aktuell, vorher) == erwartet


def test_build_readme_zeigt_delta_und_summe():
    vorher = dict(_ZAEHLUNG, Radweg=32000)
    readme = cw.build_readme(_ZAEHLUNG, "2026-09-20", previous=vorher, previous_date="2026-09-13")

    assert "| Code | Sign | Description (DE) | Description (EN) | Count | Δ | Mapillary class |" in readme
    assert "| Radweg | Cycle path | 32,401 | +401 |" in readme
    assert "| **Previous run** | 2026-09-13 |" in readme
    assert "change since the previous run (2026-09-13)" in readme

    # Summe ueber alle Zeichen, Delta nur aus dem einen geaenderten.
    assert f"| **Total** | | | | **{sum(_ZAEHLUNG.values()):,}** | **+401** | |" in readme
    assert f"| **Total signs** | {sum(_ZAEHLUNG.values()):,} |" in readme


def test_build_readme_ohne_vorlauf_laesst_das_delta_leer():
    readme = cw.build_readme(_ZAEHLUNG, "2026-09-20")

    assert "**Previous run**" not in readme
    assert "stays empty until a second run" in readme
    assert f"| 32,401 | {cw.NO_VALUE} |" in readme


def test_build_readme_zaehlt_unbekannte_zeichen_nicht_in_die_summe():
    """Sonst wichen Summenzeile und Spalten voneinander ab."""
    readme = cw.build_readme({**_ZAEHLUNG, "Unbekanntes Zeichen": 999}, "2026-09-20")
    assert f"**{sum(_ZAEHLUNG.values()):,}**" in readme


def test_sign_history_rundlauf(tmp_path):
    cw.append_sign_history(tmp_path, "2026-09-13", {"Radweg": 32000}, runs=[], verbose=False)
    runs = cw.load_sign_history(tmp_path, url=None, verbose=False)
    cw.append_sign_history(tmp_path, "2026-09-20", {"Radweg": 32401}, runs=runs, verbose=False)

    runs = cw.load_sign_history(tmp_path, url=None, verbose=False)
    assert [run["date"] for run in runs] == ["2026-09-13", "2026-09-20"]

    # Der aktuelle Lauf vergleicht sich mit dem davor, nicht mit sich selbst.
    vorher, datum = cw.latest_sign_counts(runs, before="2026-09-20")
    assert (vorher, datum) == ({"Radweg": 32000}, "2026-09-13")


def test_append_sign_history_ersetzt_den_lauf_vom_selben_tag(tmp_path):
    """Ein Rerun nach Abbruch darf die Referenz des naechsten Laufs nicht sein."""
    cw.append_sign_history(tmp_path, "2026-09-13", {"Radweg": 1}, runs=[], verbose=False)
    runs = cw.load_sign_history(tmp_path, url=None, verbose=False)
    cw.append_sign_history(tmp_path, "2026-09-20", {"Radweg": 2}, runs=runs, verbose=False)
    runs = cw.load_sign_history(tmp_path, url=None, verbose=False)
    cw.append_sign_history(tmp_path, "2026-09-20", {"Radweg": 3}, runs=runs, verbose=False)

    runs = cw.load_sign_history(tmp_path, url=None, verbose=False)
    assert [run["date"] for run in runs] == ["2026-09-13", "2026-09-20"]
    assert runs[-1]["zeichen"] == {"Radweg": 3}
    assert cw.latest_sign_counts(runs, before="2026-09-20") == ({"Radweg": 1}, "2026-09-13")


def test_latest_sign_counts_ohne_historie():
    assert cw.latest_sign_counts([], before="2026-09-20") == ({}, None)
    nur_heute = [{"date": "2026-09-20", "zeichen": {"Radweg": 1}}]
    assert cw.latest_sign_counts(nur_heute, before="2026-09-20") == ({}, None)


def test_load_sign_history_ergaenzt_den_lokalen_stand_um_den_server(monkeypatch, tmp_path):
    """ts_output/ liegt nicht in git - ein leerer Ordner darf die Historie nicht kappen."""
    cw.append_sign_history(tmp_path, "2026-09-20", {"Radweg": 2}, runs=[], verbose=False)

    class _Antwort:
        status_code = 200

        @staticmethod
        def raise_for_status():
            pass

        @staticmethod
        def json():
            return {"runs": [{"date": "2026-09-13", "zeichen": {"Radweg": 1}}]}

    monkeypatch.setattr(cw.requests, "get", lambda *a, **k: _Antwort())
    runs = cw.load_sign_history(tmp_path, url="https://example.invalid/h.json", verbose=False)
    assert [run["date"] for run in runs] == ["2026-09-13", "2026-09-20"]


def test_load_sign_history_vertraegt_kaputte_dateien(monkeypatch, tmp_path):
    """Ohne Historie entfallen nur die Deltas - der Lauf darf nicht scheitern."""
    cw.sign_history_path(tmp_path).write_text("{kein json", encoding="utf-8")

    def _kaputt(*args, **kwargs):
        raise cw.requests.RequestException("kein Netz")

    monkeypatch.setattr(cw.requests, "get", _kaputt)
    assert cw.load_sign_history(tmp_path, url="https://example.invalid/h.json", verbose=False) == []


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


def test_build_readme_zaehlt():
    readme = cw.build_readme({"Radweg": 42}, "2026-09-20")

    assert "| DE:237 |" in readme
    assert "| Radweg | Cycle path | 42 |" in readme
    assert "| Radfahrer frei | Bicycles excepted | 0 |" in readme  # nicht gezaehlt -> 0
    assert "| **Data created** | 2026-09-20 |" in readme


@pytest.mark.parametrize(
    "ordner, build",
    [
        ("cycleway_complete_campaign/ts_output", lambda: cw.build_readme({}, "2026-10-17")),
        ("cycleway_complete_marking_campaign/mk_output", lambda: cw.build_readme_markierungen({}, "2026-10-17")),
    ],
)
def test_readme_lists_every_published_file(ordner, build):
    """The README is read on data.vizsim.de below the file listing, so it must
    describe every file the upload script publishes for its folder - and link
    to it relatively, not as if the files still lived in this repository."""
    skript = (Path(__file__).resolve().parents[1] / "scripts" / "upload_outputs_to_b2.sh").read_text(encoding="utf-8")
    block = skript.split(f'sync_dir "use_cases/{ordner}"')[1].split(";;")[0]
    veroeffentlicht = {re.sub(r"\\(.)", r"\1", m) for m in re.findall(r'"\.\*([^"$]+)\$"', block)}
    assert len(veroeffentlicht - {"README.md"}) >= 3  # the parser found the includes

    readme = build()
    for name in veroeffentlicht - {"README.md"}:
        assert f"]({name})" in readme, f"{name} fehlt in der README"
    assert "clone this repository" not in readme


def test_build_readme_uebernimmt_die_filterwerte():
    readme = cw.build_readme({}, "2026-09-20", seit="2024-02-03", autobahn_abstand_m=45)
    assert "| **Detections newer than** | 2024-02-03 |" in readme
    assert "| **Motorway exclusion** | 45 m |" in readme
    assert "Signs within 45 m of a motorway are excluded" in readme


# --- Metadaten --------------------------------------------------------------


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


_SYMBOL = "Lane marking - symbol (bicycle)"


def test_build_readme_markierungen():
    readme = cw.build_readme_markierungen({_SYMBOL: 35250}, "2026-09-17", seit="2024-02-03", min_days=90)
    assert "| **Data created** | 2026-09-17 |" in readme
    assert "| **Total markings** | 35,250 |" in readme
    assert "| **Detections newer than** | 2024-02-03 |" in readme
    assert "| **First to last sighting** | more than 90 days |" in readme
    assert "`marking--discrete--symbol--bicycle`" in readme
    # Same section headings as the traffic-sign README.
    assert "## Files" in readme and "## Detections per month" in readme

    # No previous run: an empty delta, not a zero.
    assert "**Previous run**" not in readme
    assert f"| **Δ since previous run** | {cw.NO_VALUE} |" in readme


def test_build_readme_markierungen_zeigt_das_delta():
    readme = cw.build_readme_markierungen(
        {_SYMBOL: 36400, "unknown class": 7},
        "2026-10-22",
        previous={_SYMBOL: 36346},
        previous_date="2026-10-15",
    )
    assert "| **Previous run** | 2026-10-15 |" in readme
    assert "| **Total markings** | 36,400 |" in readme
    assert "| **Δ since previous run** | +54 |" in readme


def test_marking_history_lives_in_its_own_file(tmp_path):
    cw.append_sign_history(
        tmp_path, "2026-10-15", {_SYMBOL: 36346}, runs=[], filename=cw.MARKING_HISTORY_FILENAME, verbose=False
    )
    assert (tmp_path / "markings_history.json").exists()
    assert not (tmp_path / cw.SIGN_HISTORY_FILENAME).exists()

    runs = cw.load_sign_history(tmp_path, url=None, filename=cw.MARKING_HISTORY_FILENAME, verbose=False)
    assert cw.latest_sign_counts(runs, before="2026-10-22") == ({_SYMBOL: 36346}, "2026-10-15")
    assert cw.load_sign_history(tmp_path, url=None, verbose=False) == []
    assert cw.MARKING_HISTORY_URL.endswith("/mapillary_map-feature-points/cycleway-campaign/markings_history.json")


def test_export_spalten_markierungen_ist_festgenagelt():
    assert cw.EXPORT_SPALTEN_MARKIERUNGEN == [
        "MapFeaturePoint", "first_seen_at", "last_seen_at", "id", "value", "geometry",
    ]


def test_read_dataset_metadata(tmp_path):
    assert cw.read_dataset_metadata(tmp_path / "fehlt.json") == (None, None, {})

    pfad = tmp_path / "ml-ts_metadata.json"
    pfad.write_text(json.dumps({
        "ml_data_from": "2026-09-01", "processed_date": "2026-09-15",
        "bundeslaender": {"DE-HB": "x"},
    }))
    assert cw.read_dataset_metadata(pfad) == ("2026-09-01", "2026-09-15", {"DE-HB": "x"})


def test_dataset_stand_nimmt_das_juengste_datum():
    assert cw.dataset_stand(["2026-09-01", "2026-09-15"]) == "2026-09-15"
    assert cw.dataset_stand([None, "2026-09-01"]) == "2026-09-01"
    assert cw.dataset_stand([], fallback="2020-01-01") == "2020-01-01"
    assert cw.dataset_stand(["keindatum"], fallback="2020-01-01") == "2020-01-01"
