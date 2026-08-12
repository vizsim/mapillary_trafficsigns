
# Bicycle Infrastucture Traffic Signs Output

This folder contains the output file for detected traffic signs related to bicycle infrastructure from Mapillary.  
The output has been created on **2026-08-12**.

## Applied Filters

- Only detections newer than **2023-01-01**
- Excluded all signs located within **30 m of motorways** (to reduce false positives)

## Signs

| VZ-Code | Beschreibung | Verkehrszeichen | Anzahl | Mapillary Wording |
|-------|-------------|:---------------:|-------:|-----------------|
| DE:237 | Radweg | <img src="https://cdn.jsdelivr.net/npm/@osm-traffic-signs/converter@0.6.0/dist/data-svgs/DE/svgs/DE_237.svg" width="40" alt="DE:237"> | 31424 | `regulatory--bicycles-only--g1` |
| DE:240 | Gemeinsamer Geh- und Radweg | <img src="https://cdn.jsdelivr.net/npm/@osm-traffic-signs/converter@0.6.0/dist/data-svgs/DE/svgs/DE_240.svg" width="40" alt="DE:240"> | 72684 | `regulatory--shared-path-pedestrians-and-bicycles--g1` |
| DE:241 | Getrennter Geh- und Radweg | <img src="https://cdn.jsdelivr.net/npm/@osm-traffic-signs/converter@0.6.0/dist/data-svgs/DE/svgs/DE_241_31.svg" width="40" alt="DE:241-31"> oder <img src="https://cdn.jsdelivr.net/npm/@osm-traffic-signs/converter@0.6.0/dist/data-svgs/DE/svgs/DE_241_30.svg" width="40" alt="DE:241-30"> | 24874 | `regulatory--dual-path-pedestrians-and-bicycles--g1`<br>`regulatory--dual-path-bicycles-and-pedestrians--g1` |
| DE:244.2 | Ende Fahrradstraße | <img src="https://cdn.jsdelivr.net/npm/@osm-traffic-signs/converter@0.6.0/dist/data-svgs/DE/svgs/DE_244_2.svg" width="40" alt="DE:244.2"> | 535 | `regulatory--end-of-bicycles-only--g2` |
| DE:1022-10 | Radfahrer frei | <img src="https://cdn.jsdelivr.net/npm/@osm-traffic-signs/converter@0.6.0/dist/data-svgs/DE/svgs/DE_1022_10.svg" width="40" alt="DE:1022-10"> | 15585 | `complementary--except-bicycles--g1` |
| DE:1000-33 | Radverkehr im Gegenverkehr | <img src="https://cdn.jsdelivr.net/npm/@osm-traffic-signs/converter@0.6.0/dist/data-svgs/DE/svgs/DE_1000_33.svg" width="40" alt="DE:1000-33"> | 7865 | `complementary--bike-route--g1` |

## Statistics Plot

![Anzahl pro Monat](signs_by_month.svg)

## Downloads

The files in this folder are also published for direct download, so consumers do
not need to clone this repository:

| File | Download |
| --- | --- |
| 🗺️ Vector tiles (PMTiles) | <https://data.vizsim.de/mapillary_trafficsigns/cycleway-campaign/mapillary_trafficsigns_bicycle_latest.pmtiles> |
| 📦 GeoJSON (gzip) | <https://data.vizsim.de/mapillary_trafficsigns/cycleway-campaign/mapillary_trafficsigns_bicycle_latest.geojson.gz> |

Data © Mapillary, redistributed under [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/).
