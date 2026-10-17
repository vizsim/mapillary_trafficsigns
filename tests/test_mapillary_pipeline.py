"""Tests fuer mapillary_pipeline - die Export-Entscheidung, ohne Netz.

Der wichtigste Test ist der erste: er beschreibt den Vorfall vom 26.08.2026
(DE-NW mit 998 von 15.243 Tiles ueberschrieben) und waere gegen den alten
Code rot gewesen.
"""

import gzip
import json
import os

import geopandas as gpd
import mercantile
import pytest
from shapely.geometry import Point

import mapillary_pipeline as mp
from mapillary_tiles import TileBatch, TileError


def _gdf(n=3, start_id=1):
    return gpd.GeoDataFrame(
        {"id": list(range(start_id, start_id + n)), "geometry": [Point(9 + i, 48) for i in range(n)]},
        crs="EPSG:4326",
    ).astype({"id": "Int64"})


def _batch(total, gdfs, failed_count=0):
    batch = TileBatch(total=total, gdfs=list(gdfs))
    batch.failed = [(mercantile.Tile(x=1, y=i, z=14), TileError("MVT-Parsefehler", "x")) for i in range(failed_count)]
    return batch


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """Mini-Repo: Tile-Cache fuer zwei Laender, leerer Output, Dummy-Token."""
    cache = tmp_path / "cache"
    cache.mkdir()
    for bl in ("DE-BW", "DE-BY"):
        (cache / f"{bl}_tiles.json").write_text(json.dumps([{"x": 1, "y": i, "z": 14} for i in range(10)]))
    (cache / "junk_tiles.json").write_text("[]")
    monkeypatch.setattr(mp, "load_access_token", lambda path="config.json": "dummy")
    return {"cache": str(cache), "out": str(tmp_path / "out"), "log": str(tmp_path / "logs" / "run.log")}


def _install_fetch(monkeypatch, batch_by_bl):
    def fake(tiles, token, coverage, layer, **kwargs):
        # das Bundesland steckt in desc="🧩 DE-XX"
        return batch_by_bl[kwargs["desc"].split()[-1]]

    monkeypatch.setattr(mp, "fetch_tiles_with_retry", fake)


# --- Die Reissleine ---------------------------------------------------------


def test_reissleine_kein_export_bei_zu_vielen_luecken(repo, monkeypatch):
    # 26.08.2026: 998 von 15.243 Tiles da, trotzdem exportiert. Nie wieder.
    _install_fetch(monkeypatch, {"DE-BW": _batch(total=100, gdfs=[_gdf()], failed_count=60)})

    exported = mp.process_bundesland(mp.PIPELINE_TS, "DE-BW", input_folder=repo["cache"], output_folder=repo["out"])

    assert exported is False
    assert not os.path.exists(repo["out"])  # weder Parquet noch Metadaten angefasst
    failed_list = os.path.join(repo["cache"], "failed", "DE-BW_failed_tiles.json")
    assert len(json.load(open(failed_list))) == 60


def test_export_bei_vollstaendigem_lauf(repo, monkeypatch):
    _install_fetch(monkeypatch, {"DE-BW": _batch(total=100, gdfs=[_gdf(), _gdf(2, 10)], failed_count=1)})

    exported = mp.process_bundesland(mp.PIPELINE_TS, "DE-BW", input_folder=repo["cache"], output_folder=repo["out"])

    assert exported is True
    parquet = os.path.join(repo["out"], "mapillary_traffic-signs_DE-BW_latest.parquet")
    assert len(gpd.read_parquet(parquet)) == 5
    meta = json.load(open(os.path.join(repo["out"], "ml-ts_metadata.json")))
    assert "DE-BW" in meta["bundeslaender"]
    assert meta["processed_date"] is None  # setzt erst der Lauf, nicht der Export


def test_keine_daten_kein_export(repo, monkeypatch):
    _install_fetch(monkeypatch, {"DE-BW": _batch(total=10, gdfs=[])})
    assert mp.process_bundesland(mp.PIPELINE_TS, "DE-BW", input_folder=repo["cache"], output_folder=repo["out"]) is False
    assert not os.path.exists(repo["out"])


def test_mk_schreibt_eigene_dateinamen(repo, monkeypatch):
    _install_fetch(monkeypatch, {"DE-BW": _batch(total=10, gdfs=[_gdf()])})
    mp.process_bundesland(mp.PIPELINE_MK, "DE-BW", input_folder=repo["cache"], output_folder=repo["out"])
    assert os.path.exists(os.path.join(repo["out"], "mapillary_map-feature-points_DE-BW_latest.parquet"))
    assert os.path.exists(os.path.join(repo["out"], "ml-mf_metadata.json"))


# --- Metadaten --------------------------------------------------------------


def test_processed_date_nur_wenn_alle_laender_durchliefen(tmp_path):
    path = str(tmp_path / "meta.json")
    mp.update_bundesland_metadata(path, "DE-BW", "2026-09-02T15:00:00+00:00")
    mp.update_bundesland_metadata(path, "DE-BY", "2026-08-19T15:00:00+00:00")

    mp.finalize_metadata(path, incomplete=["DE-BY"], emit=lambda m: None)
    meta = json.load(open(path))
    assert meta["processed_date"] is None
    assert meta["last_run_incomplete"] == ["DE-BY"]
    assert meta["ml_data_from"] == "2026-08-19T15:00:00+00:00"  # der ehrliche Wert: das aelteste Land

    mp.finalize_metadata(path, incomplete=[], emit=lambda m: None)
    meta = json.load(open(path))
    assert meta["processed_date"] == meta["last_run_date"]
    assert meta["last_run_incomplete"] == []


def test_geojson_ids_als_string_parquet_exakt(repo):
    big = 2**53 + 1
    gdf = gpd.GeoDataFrame({"id": [big], "geometry": [Point(9, 48)]}, crs="EPSG:4326").astype({"id": "Int64"})

    mp.export_geodata(gdf, mp.PIPELINE_TS, repo["out"], "DE-HB", save_geojson_gz=True, emit=lambda m: None)

    stem = os.path.join(repo["out"], "mapillary_traffic-signs_DE-HB_latest")
    assert int(gpd.read_parquet(f"{stem}.parquet")["id"].iloc[0]) == big
    with gzip.open(f"{stem}.geojson.gz", "rt") as f:
        feature = json.load(f)["features"][0]
    assert feature["properties"]["id"] == str(big)  # als String, sonst rundet jeder JS-Konsument


# --- Der ganze Lauf ---------------------------------------------------------


def test_bundeslaender_aus_tile_cache_sortiert_und_gefiltert(repo):
    assert mp.bundeslaender_mit_tiles(repo["cache"]) == ["DE-BW", "DE-BY"]


def test_run_pipeline_bilanz_und_mitschrift(repo, monkeypatch):
    _install_fetch(
        monkeypatch,
        {
            "DE-BW": _batch(total=10, gdfs=[_gdf()]),
            "DE-BY": _batch(total=10, gdfs=[_gdf()], failed_count=5),
        },
    )

    results = mp.run_pipeline(
        mp.PIPELINE_TS, input_folder=repo["cache"], output_folder=repo["out"], log_path=repo["log"]
    )

    assert results == {"DE-BW": True, "DE-BY": False}
    meta = json.load(open(os.path.join(repo["out"], "ml-ts_metadata.json")))
    assert meta["last_run_incomplete"] == ["DE-BY"]
    assert meta["processed_date"] is None
    assert "DE-BY" not in meta["bundeslaender"]
    log = open(repo["log"], encoding="utf-8").read()
    assert "1/2 Bundesländer aktualisiert" in log
    assert "Nicht aktualisiert, alter Stand bleibt stehen: DE-BY" in log
    assert "NICHT exportiert: 50.0%" in log


# --- Reihenfolge und Auswahl --------------------------------------------------

from datetime import datetime, timedelta, timezone  # noqa: E402

NOW = datetime(2026, 9, 3, 12, 0, tzinfo=timezone.utc)


def _meta(**ages_in_days):
    return {"bundeslaender": {b: (NOW - timedelta(days=d)).isoformat() for b, d in ages_in_days.items()}}


def test_aelteste_daten_zuerst_nie_verarbeitete_ganz_vorn():
    meta = _meta(**{"DE-BW": 0.5, "DE-BY": 14.0, "DE-HE": 7.0})
    todo, fresh, ages = mp.plan_bundeslaender(["DE-BW", "DE-BY", "DE-HE", "DE-TH"], meta, now=NOW)
    assert todo == ["DE-TH", "DE-BY", "DE-HE", "DE-BW"]  # TH hat noch nie Daten
    assert fresh == []
    assert ages["DE-TH"] == float("inf") and ages["DE-BY"] == 14.0


def test_frische_laender_werden_uebersprungen():
    meta = _meta(**{"DE-BW": 0.5, "DE-BY": 14.0, "DE-HE": 4.9, "DE-MV": 5.0})
    todo, fresh, _ = mp.plan_bundeslaender(["DE-BW", "DE-BY", "DE-HE", "DE-MV"], meta, max_file_age_days=5, now=NOW)
    assert todo == ["DE-BY", "DE-MV"]  # 5.0 Tage ist nicht mehr frisch
    assert fresh == ["DE-HE", "DE-BW"]


def test_gleich_alte_laender_alphabetisch():
    todo, _, _ = mp.plan_bundeslaender(["DE-TH", "DE-BB", "DE-NW"], {"bundeslaender": {}}, now=NOW)
    assert todo == ["DE-BB", "DE-NW", "DE-TH"]


def test_run_pipeline_holt_nur_veraltete_und_in_altersreihenfolge(repo, monkeypatch):
    # BW ist von heute, BY von vor zwei Wochen -> nur BY, und der Lauf gilt als komplett
    mp._write_metadata(os.path.join(repo["out"], "ml-ts_metadata.json"), _meta(**{"DE-BW": 0.3, "DE-BY": 14.0}))
    monkeypatch.setattr(mp, "datetime", type("dt", (), {"now": staticmethod(lambda tz=None: NOW),
                                                        "fromisoformat": staticmethod(datetime.fromisoformat)}))
    _install_fetch(monkeypatch, {"DE-BY": _batch(total=10, gdfs=[_gdf()])})

    results = mp.run_pipeline(
        mp.PIPELINE_TS, input_folder=repo["cache"], output_folder=repo["out"], log_path=repo["log"]
    )

    assert results == {"DE-BY": True}  # BW wurde gar nicht erst angefragt
    meta = json.load(open(os.path.join(repo["out"], "ml-ts_metadata.json")))
    assert meta["last_run_incomplete"] == []
    assert meta["processed_date"] is not None  # frisch uebersprungen ist nicht unvollstaendig
    log = open(repo["log"], encoding="utf-8").read()
    assert "Übersprungen, Daten jünger als 5 Tage: DE-BW (0.3 d)" in log
    assert "1/1 Bundesländer aktualisiert, 1 frisch übersprungen" in log


def test_explizite_liste_ignoriert_die_altersgrenze(repo, monkeypatch):
    mp._write_metadata(os.path.join(repo["out"], "ml-ts_metadata.json"), _meta(**{"DE-BW": 0.3}))
    _install_fetch(monkeypatch, {"DE-BW": _batch(total=10, gdfs=[_gdf()])})

    results = mp.run_pipeline(
        mp.PIPELINE_TS, ["DE-BW"], input_folder=repo["cache"], output_folder=repo["out"], log_path=repo["log"]
    )

    assert results == {"DE-BW": True}


# --- Aufruf von der Kommandozeile -------------------------------------------


@pytest.fixture
def aufrufe(monkeypatch):
    """Ersetzt run_pipeline und merkt sich, womit main() es aufruft."""
    gemerkt = []
    monkeypatch.setattr(mp, "run_pipeline", lambda *args, **kwargs: gemerkt.append((args, kwargs)) or {})
    return gemerkt


def test_main_ruft_die_pipeline_wie_vorher_das_notebook(aufrufe):
    """Der Wochenlauf: genau das, was 2_/2b_get_…ipynb taten - alle Laender, output/."""
    assert mp.main(["ts"]) == 0
    assert mp.main(["mk"]) == 0
    assert aufrufe == [
        ((mp.PIPELINE_TS, None), {"output_folder": "output"}),
        ((mp.PIPELINE_MK, None), {"output_folder": "output"}),
    ]


def test_main_nachlauf_fuer_einzelne_laender(aufrufe):
    mp.main(["ts", "--bundesland", "DE-NW", "DE-HB"])
    assert aufrufe[0][0] == (mp.PIPELINE_TS, ["DE-NW", "DE-HB"])


@pytest.mark.parametrize("argv", [["xx"], [], ["ts", "--bundesland", "NW"]])
def test_main_lehnt_unsinn_ab(aufrufe, argv):
    with pytest.raises(SystemExit) as ende:
        mp.main(argv)
    assert ende.value.code == 2
    assert aufrufe == []


def test_probelauf_nie_in_den_echten_ausgabeordner(aufrufe, tmp_path):
    """Ein Teilstand in output/ bekaeme einen frischen Zeitstempel: der naechste
    Wochenlauf ueberspraenge das Land und luede den Teilstand hoch."""
    with pytest.raises(SystemExit):
        mp.main(["ts", "--limit-tiles", "5"])
    assert aufrufe == []

    mp.main(["ts", "--limit-tiles", "5", "--output-folder", str(tmp_path)])
    assert aufrufe[0][1] == {"output_folder": str(tmp_path), "limit_tiles": 5}


def test_modulaufruf_als_eigener_prozess():
    """So ruft der Runner im Container: python3 -m mapillary_pipeline."""
    import subprocess
    import sys

    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ergebnis = subprocess.run(
        [sys.executable, "-m", "mapillary_pipeline", "--help"],
        cwd=repo_root, capture_output=True, text=True, timeout=120,
    )
    assert ergebnis.returncode == 0, ergebnis.stderr
    assert "{mk,ts}" in ergebnis.stdout
