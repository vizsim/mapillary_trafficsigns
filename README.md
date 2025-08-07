# mapillary_trafficsigns

## 📖 Overview

This project provides code to download and process **traffic sign detections from Mapillary** in Germany using the Mapillary vector tile layer API.

It is intended to support **OpenStreetMap (OSM)** mapping tasks such as identifying missing cycleways, based on automatically detected signs like `DE:237`, `DE:240`, `DE:241`, etc.

---

## 📚 Resources

- 📄 [Traffic Sign Tiles API Documentation](https://www.mapillary.com/developer/api-documentation?locale=de_DE#traffic-sign-tiles)  
- 📄 [Traffic Signs API Documentation](https://www.mapillary.com/developer/api-documentation/traffic-signs?locale=de_DE)  
- 📄 [mapillary_sprite_source repository](https://github.com/mapillary/mapillary_sprite_source) (for icon sprites)

---

## ⚠️ License & Data Availability

This project uses traffic sign detections provided via the [Mapillary API](https://www.mapillary.com/developer/api-documentation/traffic-signs?locale=de_DE), which are based on user-contributed imagery and Mapillary's own processing.

As of now, there is **no publicly documented license** specifically for the traffic sign detection data. The general terms of use can be found here:

- [Mapillary Terms of Use](https://www.mapillary.com/legal/terms)
- [Mapillary API Documentation](https://www.mapillary.com/developer/api-documentation)

Out of an abundance of caution regarding potential redistribution restrictions, this repository **does not include any downloaded detection data**.

Therefore:

- **The downloaded detection data is NOT included in this repository.**
- The `output/` folder with the data has been removed to comply with the license terms.
- If you wish to access this data, you must retrieve it yourself using the Mapillary API.

This repository only contains the code used to download, filter, and process traffic sign detections from Mapillary for use in OSM-related tasks.

---

## 🗺️ Use-Cases

The goal of the [cycleway_complete_campaign](use_cases/cycleway_complete_campaign) is to assist in identifying missing cycleway infrastructure in OpenStreetMap by using automatically detected traffic signs (e.g., mandatory cycleways, shared paths) from Mapillary.

You can explore the corresponding MapRoulette challenge here:  
🔗 [**MapRoulette Challenge – Cycleway Completion Germany**](https://maproulette.org/browse/challenges/52916)
