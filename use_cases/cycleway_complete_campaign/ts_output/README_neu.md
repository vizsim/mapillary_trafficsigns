
# Bicycle Infrastucture Traffic Signs Output
This folder contains the output file for detected traffic signs related to bicycle infrastructure from Mapillary.  
The output has been created on **2025-10-30**.

## Applied Filters
- Only detections newer than **2023-01-01**
- Excluded all signs located within **30 m of motorways** (to reduce false positives)

## Signs

| VZ-Code | Mapillary Wording | Beschreibung | Anzahl | Verkehrszeichen |
|------|-------------------|---------------|---------:|--------|
| DE:237 | `regulatory--bicycles-only--g1` | Radweg | 23246 | <img src="https://trafficsigns.osm-verkehrswende.org/_next/static/media/DE_237.36e48b6d.svg" width="40"> |
| DE:240 | `regulatory--shared-path-pedestrians-and-bicycles--g1` | Gemeinsamer Geh- und Radweg | 55334 | <img src="https://trafficsigns.osm-verkehrswende.org/_next/static/media/DE_240.c2d222a0.svg" width="40"> |
| DE:241 | `regulatory--dual-path-pedestrians-and-bicycles--g1`<br>`regulatory--dual-path-bicycles-and-pedestrians--g1` | Getrennter Geh- und Radweg | 19682 | <img src="https://trafficsigns.osm-verkehrswende.org/_next/static/media/DE_241_30.69c98777.svg" width="40"> oder <img src="https://trafficsigns.osm-verkehrswende.org/_next/static/media/DE_241_31.3627eb18.svg" width="40"> |
| DE:244.2 | `regulatory--end-of-bicycles-only--g2` | Ende Fahrradstraße | 412 | <img src="https://trafficsigns.osm-verkehrswende.org/_next/static/media/DE_244_2.b586a5a6.svg" width="40"> |
| DE:1022-10 | `complementary--except-bicycles--g1` | Radfahrer frei | 12474 | <img src="https://trafficsigns.osm-verkehrswende.org/_next/static/media/DE_1022_10.cda7bd53.svg" width="40"> |
| DE:1000-33 | `complementary--bike-route--g1` | Radverkehr im Gegenverkehr | 6237 | <img src="https://trafficsigns.osm-verkehrswende.org/_next/static/media/DE_1000_33.c18820f3.svg" width="40"> |

## Statistics Plot
![Anzahl pro Monat](signs_by_month.svg)
