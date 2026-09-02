"""Orchestrierung der beiden Pipelines (ts, mk): Laden, Export, Metadaten, Lauf-Bilanz.

mapillary_tiles.py holt Tiles. Dieses Modul entscheidet, was damit passiert -
und vor allem, was NICHT passiert: kein Export bei zu vielen Luecken, kein
frischer Gesamtstempel bei unvollstaendigem Lauf.

Die Notebooks 2_*.ipynb und 2b_*.ipynb sind nur noch Aufrufer:

    from mapillary_pipeline import PIPELINE_TS, run_pipeline
    run_pipeline(PIPELINE_TS)
"""

from __future__ import annotations

import gc
import glob
import gzip
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone

import geopandas as gpd
import mercantile
import pandas as pd

from mapillary_tiles import COVERAGE_MAP_FEATURES, COVERAGE_TRAFFIC_SIGNS, fetch_tiles_with_retry


@dataclass(frozen=True)
class Pipeline:
    name: str
    coverage: str
    layer: str
    base_name: str
    metadata_file: str


PIPELINE_TS = Pipeline("ts", *COVERAGE_TRAFFIC_SIGNS, "mapillary_traffic-signs", "ml-ts_metadata.json")
PIPELINE_MK = Pipeline("mk", *COVERAGE_MAP_FEATURES, "mapillary_map-feature-points", "ml-mf_metadata.json")

BUNDESLAND_ID = re.compile(r"^DE-[A-Z]{2}$")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class RunLog:
    """print() plus Mitschrift in eine Datei.

    nbconvert schreibt Zell-Ausgaben erst am Ende ins Notebook. Waehrend des
    Laufs sieht man auf dem Server nichts - deshalb war der mk-Lauf vom
    27.08.2026 hinterher nicht rekonstruierbar. Die Datei liegt im Bind-Mount
    und ist live lesbar, auch wenn der Lauf mittendrin stirbt.
    """

    def __init__(self, path: str):
        self.path = path
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"# Lauf gestartet {now_iso()}\n")

    def __call__(self, message: str = "") -> None:
        print(message)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] {message}\n")


# --- Eingaben ---------------------------------------------------------------


def load_access_token(path: str = "config.json") -> str:
    token = os.environ.get("MAPILLARY_ACCESS_TOKEN")
    if token:
        return token
    with open(path) as f:
        return json.load(f)["ACCESS_TOKEN"]


def load_tiles_from_json(bundesland_id: str, input_folder: str = "prep/tile_cache") -> list:
    path = os.path.join(input_folder, f"{bundesland_id}_tiles.json")
    with open(path) as f:
        return [mercantile.Tile(**t) for t in json.load(f)]


def bundeslaender_mit_tiles(input_folder: str = "prep/tile_cache") -> list[str]:
    """IDs aller Bundeslaender mit Tile-Cache, sortiert.

    Ersetzt das Einlesen des Bundesland-GeoJSON von GitHub bei jedem Lauf:
    die Namen daraus wurden nie benutzt, und ein haengender GitHub-Request
    (ohne Timeout) haette den ganzen Lauf gestoppt, bevor ein Tile geholt war.
    """
    ids = []
    for path in glob.glob(os.path.join(input_folder, "*_tiles.json")):
        candidate = os.path.basename(path)[: -len("_tiles.json")]
        if BUNDESLAND_ID.match(candidate):
            ids.append(candidate)
    return sorted(ids)


# --- Metadaten --------------------------------------------------------------


def _read_metadata(path: str) -> dict:
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {"ml_data_from": None, "bundeslaender": {}, "processed_date": None}


def _write_metadata(path: str, metadata: dict) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)


def update_bundesland_metadata(path: str, bundesland_id: str, timestamp: str) -> None:
    metadata = _read_metadata(path)
    metadata["bundeslaender"][bundesland_id] = timestamp
    metadata["ml_data_from"] = min(metadata["bundeslaender"].values())
    _write_metadata(path, metadata)


def finalize_metadata(path: str, incomplete: list[str], emit=print) -> None:
    """Lauf-Stempel setzen - processed_date NUR, wenn alle Laender durchliefen.

    Vorher wurde processed_date bei jedem Export (mk) bzw. am Ende jedes Laufs
    (ts) gesetzt. Beides meldete "frisch", waehrend die Haelfte der Dateien
    Wochen alt war. ml_data_from (= aeltestes Land) bleibt der ehrliche Wert.
    """
    if not os.path.exists(path):
        emit(f"ℹ️ Keine Metadatei unter {path} - nichts zu finalisieren.")
        return
    metadata = _read_metadata(path)
    metadata["last_run_date"] = now_iso()
    metadata["last_run_incomplete"] = list(incomplete)
    if not incomplete:
        metadata["processed_date"] = metadata["last_run_date"]
    _write_metadata(path, metadata)
    emit(f"✔ Metadata aktualisiert: {path}")


# --- Export -----------------------------------------------------------------


def export_geodata(
    gdf: gpd.GeoDataFrame,
    pipeline: Pipeline,
    output_folder: str,
    bundesland_id: str,
    save_parquet: bool = True,
    save_geojson_gz: bool = False,
    emit=print,
) -> None:
    os.makedirs(output_folder, exist_ok=True)
    stem = os.path.join(output_folder, f"{pipeline.base_name}_{bundesland_id}_latest")

    if save_parquet:
        gdf.to_parquet(f"{stem}.parquet", index=False)
        emit(f"✔ Parquet saved to: {stem}.parquet")

    if save_geojson_gz:
        # Mapillary ids are larger than JS Number.MAX_SAFE_INTEGER (2**53). Written
        # as JSON numbers they get rounded to the nearest double by every JS
        # consumer (MapLibre, tippecanoe/PMTiles, web map, MapRoulette), which
        # breaks the resulting Mapillary links. Emit them as strings instead.
        # assign() only rebuilds the id columns, it is not a full frame copy -
        # the parquet written above keeps the lossless int64.
        id_cols = {c: gdf[c].astype("string") for c in ("id", "image_id") if c in gdf.columns}
        gdf_export = gdf.assign(**id_cols) if id_cols else gdf
        geojson_path = f"{stem}.geojson"
        gdf_export.to_file(geojson_path, driver="GeoJSON")
        with open(geojson_path, "rb") as f_in, gzip.open(f"{geojson_path}.gz", "wb") as f_out:
            f_out.writelines(f_in)
        os.remove(geojson_path)
        emit(f"✔ Gzipped GeoJSON saved to: {geojson_path}.gz")

    update_bundesland_metadata(os.path.join(output_folder, pipeline.metadata_file), bundesland_id, now_iso())


# --- Ein Bundesland ---------------------------------------------------------


def process_bundesland(
    pipeline: Pipeline,
    bundesland_id: str,
    *,
    input_folder: str = "prep/tile_cache",
    output_folder: str = "output",
    max_workers: int = 3,
    limit_tiles: int | None = None,
    max_fail_ratio: float = 0.02,
    retry_rounds: int = 1,
    retry_pause: int = 300,
    access_token: str | None = None,
    emit=print,
) -> bool:
    """Ein Bundesland verarbeiten. Rueckgabe: True = exportiert, False = uebersprungen.

    max_fail_ratio ist die Reissleine: ab diesem Anteil endgueltig fehlender
    Tiles wird NICHT exportiert. Lieber die alte, vollstaendige Datei behalten
    als sie durch einen Bruchteil ersetzen. Am 26.08.2026 wurde DE-NW mit 998
    von 15.243 Tiles ueberschrieben - 1.391.990 Schilder runter auf 139.026.
    """
    emit(f"▶️ Starte Verarbeitung für {bundesland_id}...")
    token = access_token or load_access_token()

    tiles = load_tiles_from_json(bundesland_id, input_folder)
    if limit_tiles:
        tiles = tiles[:limit_tiles]

    batch = fetch_tiles_with_retry(
        tiles,
        token,
        pipeline.coverage,
        pipeline.layer,
        max_workers=max_workers,
        desc=f"🧩 {bundesland_id}",
        retry_rounds=retry_rounds,
        retry_pause=retry_pause,
        emit=emit,
    )
    batch.report(emit)
    batch.write_failed(bundesland_id, input_folder, emit)

    exported = False
    if not batch.gdfs:
        emit(f"⚠️ Keine Daten für {bundesland_id} - vorhandene Datei bleibt unverändert.")
    elif batch.fail_ratio > max_fail_ratio:
        emit(
            f"🛑 {bundesland_id} NICHT exportiert: {batch.fail_ratio:.1%} der Tiles fehlen "
            f"(Grenze {max_fail_ratio:.1%}). Datei und Metadaten bleiben unverändert, "
            f"damit kein vollständiger Stand durch einen Teilstand ersetzt wird."
        )
    else:
        # Concat zuerst, dann Liste sofort leeren: die Tile-GDFs muessen weg,
        # bevor der Export den naechsten Speicher-Peak verursacht. mk-Laeufe
        # sind an der 6.5g-Grenze gestorben.
        gdf_all = gpd.GeoDataFrame(pd.concat(batch.gdfs, ignore_index=True), crs=batch.gdfs[0].crs)
        batch.gdfs.clear()
        gc.collect()
        export_geodata(gdf_all, pipeline, output_folder, bundesland_id, emit=emit)
        del gdf_all
        exported = True

    del tiles, batch
    gc.collect()
    return exported


# --- Der ganze Lauf ---------------------------------------------------------


def run_pipeline(
    pipeline: Pipeline,
    bundeslaender: list[str] | None = None,
    *,
    input_folder: str = "prep/tile_cache",
    output_folder: str = "output",
    log_path: str | None = None,
    **kwargs,
) -> dict[str, bool]:
    """Alle Bundeslaender verarbeiten, Bilanz ziehen, Metadaten finalisieren.

    Rueckgabe: {bundesland_id: exportiert?}. kwargs gehen an process_bundesland
    (max_workers, limit_tiles, max_fail_ratio, retry_rounds, retry_pause).
    """
    emit = RunLog(log_path or os.path.join("logs", f"{pipeline.name}_run_latest.log"))
    ids = bundeslaender or bundeslaender_mit_tiles(input_folder)
    token = load_access_token()
    emit(f"🚦 Pipeline {pipeline.name}: {len(ids)} Bundesländer, Mitschrift in {emit.path}")

    results: dict[str, bool] = {}
    for bundesland_id in ids:
        results[bundesland_id] = process_bundesland(
            pipeline,
            bundesland_id,
            input_folder=input_folder,
            output_folder=output_folder,
            access_token=token,
            emit=emit,
            **kwargs,
        )
        gc.collect()

    aktualisiert = [b for b, ok in results.items() if ok]
    uebersprungen = [b for b, ok in results.items() if not ok]
    emit("")
    emit(f"===== Lauf beendet: {len(aktualisiert)}/{len(results)} Bundesländer aktualisiert =====")
    if uebersprungen:
        emit(f"❌ Nicht aktualisiert, alter Stand bleibt stehen: {', '.join(uebersprungen)}")

    finalize_metadata(os.path.join(output_folder, pipeline.metadata_file), uebersprungen, emit)
    return results
