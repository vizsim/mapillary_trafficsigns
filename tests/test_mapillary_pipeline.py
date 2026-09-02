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
