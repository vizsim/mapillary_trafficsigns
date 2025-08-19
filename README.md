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

All use-cases follow the same workflow:

1. **Detect** relevant traffic signs via Mapillary.  
2. **Filter** by specific criteria (e.g., sign type, proximity, absence in OSM).  
3. **Validate & map** missing or incorrect data in OSM via structured MapRoulette tasks.  

### 🚲 Cycleway Completion (Germany)  

- Targets **bicycle-related signs** (like `DE:237`, `DE:240`, `DE:241`) to identify missing cycleways in OSM.  
- **Code Repository:** [cycleway_complete_campaign](https://github.com/vizsim/mapillary_trafficsigns/tree/main/use_cases/cycleway_complete_campaign)  
- **MapRoulette Challenge:** [Cycleway Completion Germany](https://maproulette.org/browse/challenges/52916)  

### 🚸 Tempo-30 Near Schools & Kindergartens (Germany)  

- Focuses on **Tempo-30 signs** (`DE:274-30`) within **400 m of schools and kindergartens**, where `maxspeed` tagging may be missing or incomplete in OSM.  
- **Code Repository:** [schools_tempo30_campaign](https://github.com/vizsim/mapillary_trafficsigns/tree/main/use_cases/schools_tempo30_campaign)  
- **MapRoulette Challenge:** [Tempo-30 Near Schools & Kindergartens](https://maproulette.org/browse/challenges/52985)  
