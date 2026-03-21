# mapillary_trafficsigns

> **Note:** Current development/production is taking place in the  
> **mapillary_trafficsigns** repository on the branch  
> [feature/docker-notebook](https://github.com/vizsim/mapillary_trafficsigns/tree/feature/docker-notebook).

## 📖 Overview

This project provides code to download and process **traffic sign detections and road markings from Mapillary** in Germany, using the Mapillary vector tile layer API and the Map Features API.

It is intended to support **OpenStreetMap (OSM)** mapping tasks such as identifying missing cycleways or pedestrian crossings, based on automatically detected signs (e.g. `DE:237`, `DE:240`, `DE:241`) and pavement markings (e.g. bicycle symbols, zebra crossings).

All use-cases are currently focused on **Germany**. The detection data is updated automatically on a regular basis.

---

## 📚 Resources

- 📄 [Traffic Sign Tiles API Documentation](https://www.mapillary.com/developer/api-documentation?locale=de_DE#traffic-sign-tiles)
- 📄 [Traffic Signs API Documentation](https://www.mapillary.com/developer/api-documentation/traffic-signs?locale=de_DE)
- 📄 [Map Features API Documentation](https://www.mapillary.com/developer/api-documentation?locale=de_DE#map-features) (for markings)
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

All use-cases follow the same general workflow:

1. **Detect** relevant traffic signs or road markings via Mapillary.
2. **Filter** by specific criteria (e.g., sign type, proximity, absence in OSM).
3. **Validate & map** missing or incorrect data in OSM via structured MapRoulette tasks.

### 🚦 Traffic Sign-based Use-Cases

#### 🚲 Bicycle Infrastructure Completion

- Targets **bicycle-related signs** (like `DE:237`, `DE:240`, `DE:241`) to identify missing cycleways in OSM.
- **Code Repository:** [cycleway_complete_campaign](https://github.com/vizsim/mapillary_trafficsigns/tree/main/use_cases/cycleway_complete_campaign)
- **MapRoulette Challenge:** [Cycleway Completion Germany](https://maproulette.org/browse/challenges/52916) — changeset hashtag: `#missing-cw_mapillary-signs`

#### 🚸 Tempo-30 Near Schools & Kindergartens

- Focuses on **Tempo-30 signs** (`DE:274-30`) within **400 m of schools and kindergartens**, where `maxspeed` tagging may be missing or incomplete in OSM.
- **Code Repository:** [schools_tempo30_campaign](https://github.com/vizsim/mapillary_trafficsigns/tree/main/use_cases/schools_tempo30_campaign)
- **MapRoulette Challenge:** [Tempo-30 Near Schools & Kindergartens](https://maproulette.org/browse/challenges/52985) — changeset hashtag: `#missing-t30_mapillary-signs`

#### 🚶 Missing Pedestrian Crossings

- Focuses on **pedestrian crossing signs** (`DE:350`) to identify missing `highway=crossing` nodes in OSM.
- **Code Repository:** [pedestrian_crossing_campaign](https://github.com/vizsim/mapillary_trafficsigns/tree/main/use_cases/pedestrian_crossing_campaign)
- **MapRoulette Challenge:** [Fehlende Fußgängerüberwege anhand von Mapillary-Verkehrszeichen ergänzen](https://maproulette.org/browse/challenges/53589) — changeset hashtag: `#missing-ped-cross_mapillary-signs`

#### 🚳 Missing Bicycle Access Tags

- Targets the **"Radfahrer frei" supplementary sign** (`complementary--except-bicycles`) to identify roads where bicycles are permitted by sign but `bicycle=yes` is missing in OSM.
- **Code Repository:** [rad_frei_campaign](https://github.com/vizsim/mapillary_trafficsigns/tree/main/use_cases/rad_frei_campaign)
- **MapRoulette Challenge:** Work in progress – no stable challenge published yet.

### 🖌️ Road Marking-based Use-Cases

#### 🚲 Cycleway Marking Completion

- Uses **Mapillary marking detections** (`marking--discrete--symbol--bicycle`) to identify roads where bicycle pavement markings are visible but OSM tagging is incomplete.
- **Code Repository:** [cycleway_complete_marking_campaign](https://github.com/vizsim/mapillary_trafficsigns/tree/main/use_cases/cycleway_complete_marking_campaign)
- **MapRoulette Challenge:** [Cycleway Marking Completion Germany](https://maproulette.org/browse/challenges/53882) — changeset hashtag: `#missing-cw_mapillary-feature`

#### 🦓 Missing Zebra Crossing Markings

- Uses **Mapillary marking detections** (`marking--discrete--crosswalk-zebra`) to identify pedestrian crossings where `crossing:markings=zebra` is missing in OSM.
- **Code Repository:** [pedestrian_crossing_marking_campaign](https://github.com/vizsim/mapillary_trafficsigns/tree/main/use_cases/pedestrian_crossing_marking_campaign)
- **MapRoulette Challenge:** Work in progress – no stable challenge published yet.

---

## 🔗 Related Projects

### 🗺️ Mapillary Missing Streets

A map showing Mapillary photo coverage based on the OSM road network — helps you find streets for your next Mapillary tour. Blue dotted lines indicate new Mapillary sequences since the last update.

- **Map:** [osm-verkehrswende.org/mapillary](https://www.osm-verkehrswende.org/mapillary/)

### 🧭 Missing Mapillary GraphHopper Routing

An interactive web app for route planning with GraphHopper integration, optimised for identifying and planning routes along roads without Mapillary coverage. Visualises coverage data to help close gaps in street-level imagery.

- **App:** [vizsim.github.io/missing_mapillary_gh-routing](https://vizsim.github.io/missing_mapillary_gh-routing/)
- **Code:** [missing_mapillary_gh-routing](https://github.com/vizsim/missing_mapillary_gh-routing)

### 📊 Mapillary Coverage Analysis

A further development of *Mapillary Missing Streets*, adding aggregated coverage statistics at federal state, district, and municipality level. Beyond per-segment coverage (panorama, regular, or missing), it also layers in detected traffic signs and bicycle infrastructure data from [radinfra.de](https://radinfra.de).

- **Map:** [vizsim.github.io/mapillary_coverage_analysis](https://vizsim.github.io/mapillary_coverage_analysis/viz/)
- **Code:** [mapillary_coverage_analysis](https://github.com/vizsim/mapillary_coverage_analysis)

### 🖱️ Mapillary Traffic Sign & Image ID Copier

A browser extension that detects Mapillary image IDs and traffic signs, copies them in a formatted way to the clipboard, and opens the Traffic Sign Tool. Ideal for OSM mappers and anyone working regularly with Mapillary data.

- **Chrome Web Store:** [Mapillary Traffic Sign & Image ID Copier](https://chromewebstore.google.com/detail/mapillary-traffic-sign-im/eagencdgcmgechomeedlbkhfcihdjhdg)
- **Code:** [mapillary_image_id_copier_addon](https://github.com/vizsim/mapillary_image_id_copier_addon)

### 📈 OSM Changeset Analysis (ohsome-planet)

A workflow for building a changeset database from OSM history data using ohsome-planet, enabling analysis by hashtag, contributor, or region. Includes a dedicated visualisation tracking edits made as part of the Cycleway Completion campaign (`#missing-cw_mapillary-signs`).

- **Campaign stats:** [vizsim.github.io/osm_hashtag_analyse](https://vizsim.github.io/osm_hashtag_analyse/analysen/cw_miss/viz/)
- **Code:** [osm_hashtag_analyse](https://github.com/vizsim/osm_hashtag_analyse/)
