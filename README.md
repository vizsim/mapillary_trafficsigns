# mapillary_trafficsigns

This project downloads detected traffic signs in Germany by Bundesland from Mapillary using the vector tile layer:

- [Traffic Sign Tiles API Documentation](https://www.mapillary.com/developer/api-documentation?locale=de_DE#traffic-sign-tiles)

For more information, see:

- [Traffic Signs API Documentation](https://www.mapillary.com/developer/api-documentation/traffic-signs?locale=de_DE)

Icon sprites are available at:

- [mapillary_sprite_source repository](https://github.com/mapillary/mapillary_sprite_source)

---

## ⚠️ License & Data Availability

This project uses traffic sign detections provided via the Mapillary API, which are subject to [Mapillary's API Terms of Use](https://www.mapillary.com/legal/api-terms).

According to these terms:

> You may use the Mapillary API and derived metadata only for purposes related to map editing or improvement (e.g. OpenStreetMap), and you may not redistribute the raw data or store it in a public repository.

Therefore:

- **The downloaded detection data is NOT included in this repository.**
- The `output/` folder has been removed to comply with the license terms.
- If you wish to access this data, you must retrieve it yourself using the Mapillary API.

This repository only contains the code used to download, filter, and process traffic sign detections from Mapillary for use in OSM-related tasks.

---

## 🗺️ Use-Cases

The goal of the [cycleway_complete_campaign](use_cases/cycleway_complete_campaign) is to assist in identifying missing cycleway infrastructure in OpenStreetMap by using automatically detected traffic signs (e.g., mandatory cycleways, shared paths) from Mapillary.

