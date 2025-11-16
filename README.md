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

## 🪪 License & Data Availability

This project uses traffic sign detections provided via the [Mapillary API](https://www.mapillary.com/developer/api-documentation/traffic-signs?locale=de_DE), which are based on user-contributed imagery and Mapillary's own processing.

According to [Mapillary’s OpenStreetMap Wiki page](https://wiki.openstreetmap.org/wiki/Mapillary#License), these derived datasets may be shared under the same license.

Therefore, the processed detection data can be included here, provided that:

- proper attribution is maintained (“© Mapillary”), and  
- any redistribution follows the [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/) terms.

The latest processed traffic sign detection datasets for each German federal state are available in the [`output/`](./output) folder.

---

## 🗺️ Use-Cases

All use-cases follow the same workflow:

1. **Detect** relevant traffic signs via Mapillary.  
2. **Filter** by specific criteria (e.g., sign type, proximity, absence in OSM).  
3. **Validate & map** missing or incorrect data in OSM via structured MapRoulette tasks.  

### 🚲 Bicycle Infrastucture Completion (Germany)  

- Targets **bicycle-related signs** (like `DE:237`, `DE:240`, `DE:241`) to identify missing cycleways in OSM.  
- **Code Repository:** [cycleway_complete_campaign](https://github.com/vizsim/mapillary_trafficsigns/tree/main/use_cases/cycleway_complete_campaign)  
- **MapRoulette Challenge:** [Cycleway Completion Germany](https://maproulette.org/browse/challenges/52916)  

### 🚸 Tempo-30 Near Schools & Kindergartens (Germany)  

- Focuses on **Tempo-30 signs** (`DE:274-30`) within **400 m of schools and kindergartens**, where `maxspeed` tagging may be missing or incomplete in OSM.  
- **Code Repository:** [schools_tempo30_campaign](https://github.com/vizsim/mapillary_trafficsigns/tree/main/use_cases/schools_tempo30_campaign)  
- **MapRoulette Challenge:** [Tempo-30 Near Schools & Kindergartens](https://maproulette.org/browse/challenges/52985)  

### 🚶 Fehlende Fußgängerüberwege ergänzen (Deutschland)

- Fokussiert auf **Fußgängerüberweg-Zeichen** (`DE:350`) zur Identifizierung fehlender Fußgängerüberwege (`highway=crossing` + `crossing=*`) in OSM.  
- **Code Repository:** [pedestrian_crossing_campaign](https://github.com/vizsim/mapillary_trafficsigns/tree/main/use_cases/pedestrian_crossing_campaign)  
- **MapRoulette Challenge:** [Fehlende Fußgängerüberwege anhand von Mapillary-Verkehrszeichen ergänzen](https://maproulette.org/browse/challenges/53589)  
