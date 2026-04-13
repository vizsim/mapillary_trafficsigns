
# Bicycle Infrastucture Traffic Signs Output

This folder contains the output file for detected traffic signs related to bicycle infrastructure from Mapillary.
The output has been created on **2026-03-31**.

## Applied Filters

- Only detections with **last_seen_at** after the rolling cutoff (Berlin local date minus the configured **36**‑month / **3**‑year lookback; **example** cutoff from `freshness_metadata.json`: **2023-04-13**)
- Excluded signs within **30 m** of motorways (reduces false positives on Autobahnen)
- Same-calendar-day **first_seen_at** / **last_seen_at** rows get a **Hinweis** in the export (possible temporary signage). Markings apply a separate minimum-days-between rule — [detection filters doc](../../../docs/mapillary-detection-filters.md)

**Constants in code:** [`use_cases/shared/detection_filter_constants.py`](../../shared/detection_filter_constants.py) (`LAST_SEEN_LOOKBACK_MONTHS`, `FRESHNESS_TIMEZONE`, `compute_last_seen_cutoff_date_str`, `freshness_export_metadata`, `MOTORWAY_EXCLUSION_BUFFER_M`).

**Per-run mirror:** [`freshness_metadata.json`](freshness_metadata.json) (computed cutoff and Berlin export time).

## Output Files

- GeoJSON / Parquet exports (from the notebook run)
- `freshness_metadata.json` — rolling `last_seen` cutoff and export timestamp (Berlin)

## Signs

| VZ-Code | Beschreibung | Verkehrszeichen | Anzahl | Mapillary Wording |
|-------|-------------|:---------------:|-------:|-----------------|
| DE:237 | Radweg | <img src="https://trafficsigns.osm-verkehrswende.org/_next/static/media/DE_237.36e48b6d.svg" width="40"> | 27535 | `regulatory--bicycles-only--g1` |
| DE:240 | Gemeinsamer Geh- und Radweg | <img src="https://trafficsigns.osm-verkehrswende.org/_next/static/media/DE_240.c2d222a0.svg" width="40"> | 61832 | `regulatory--shared-path-pedestrians-and-bicycles--g1` |
| DE:241 | Getrennter Geh- und Radweg | <img src="https://trafficsigns.osm-verkehrswende.org/_next/static/media/DE_241_31.3627eb18.svg" width="40"> oder <img src="https://trafficsigns.osm-verkehrswende.org/_next/static/media/DE_241_30.7eec6f94.svg" width="40"> | 21905 | `regulatory--dual-path-pedestrians-and-bicycles--g1`<br>`regulatory--dual-path-bicycles-and-pedestrians--g1` |
| DE:244.2 | Ende Fahrradstraße | <img src="https://trafficsigns.osm-verkehrswende.org/_next/static/media/DE_244_2.b586a5a6.svg" width="40"> | 461 | `regulatory--end-of-bicycles-only--g2` |
| DE:1022-10 | Radfahrer frei | <img src="https://trafficsigns.osm-verkehrswende.org/_next/static/media/DE_1022_10.cda7bd53.svg" width="40"> | 13621 | `complementary--except-bicycles--g1` |
| DE:1000-33 | Radverkehr im Gegenverkehr | <img src="https://trafficsigns.osm-verkehrswende.org/_next/static/media/DE_1000_33.c18820f3.svg" width="40"> | 6812 | `complementary--bike-route--g1` |

## Statistics Plot

![Anzahl pro Monat](signs_by_month.svg)
