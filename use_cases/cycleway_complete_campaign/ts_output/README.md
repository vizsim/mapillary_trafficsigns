
# Bicycle Infrastucture Traffic Signs Output

This folder contains the output file for detected traffic signs related to bicycle infrastructure from Mapillary.  
The output has been created on **2026-01-20**.

## Applied Filters

- Only detections newer than **2023-01-01**
- Excluded all signs located within **30 m of motorways** (to reduce false positives)

## Signs

| VZ-Code | Beschreibung | Verkehrszeichen | Anzahl | Mapillary Wording |
|-------|-------------|:---------------:|-------:|-----------------|
| DE:237 | Radweg | <img src="https://trafficsigns.osm-verkehrswende.org/_next/static/media/DE_237.36e48b6d.svg" width="40"> | 26352 | `regulatory--bicycles-only--g1` |
| DE:240 | Gemeinsamer Geh- und Radweg | <img src="https://trafficsigns.osm-verkehrswende.org/_next/static/media/DE_240.c2d222a0.svg" width="40"> | 59100 | `regulatory--shared-path-pedestrians-and-bicycles--g1` |
| DE:241 | Getrennter Geh- und Radweg | <img src="https://trafficsigns.osm-verkehrswende.org/_next/static/media/DE_241_31.3627eb18.svg" width="40"> oder <img src="https://trafficsigns.osm-verkehrswende.org/_next/static/media/DE_241_30.7eec6f94.svg" width="40"> | 20858 | `regulatory--dual-path-pedestrians-and-bicycles--g1`<br>`regulatory--dual-path-bicycles-and-pedestrians--g1` |
| DE:244.2 | Ende Fahrradstraße | <img src="https://trafficsigns.osm-verkehrswende.org/_next/static/media/DE_244_2.b586a5a6.svg" width="40"> | 442 | `regulatory--end-of-bicycles-only--g2` |
| DE:1022-10 | Radfahrer frei | <img src="https://trafficsigns.osm-verkehrswende.org/_next/static/media/DE_1022_10.cda7bd53.svg" width="40"> | 13094 | `complementary--except-bicycles--g1` |
| DE:1000-33 | Radverkehr im Gegenverkehr | <img src="https://trafficsigns.osm-verkehrswende.org/_next/static/media/DE_1000_33.c18820f3.svg" width="40"> | 6509 | `complementary--bike-route--g1` |

## Statistics Plot

![Anzahl pro Monat](signs_by_month.svg)
