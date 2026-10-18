"""Tempo-30 campaign: MapRoulette tasks from Mapillary 30 signs near schools.

Finds 30 km/h signs (DE:274-30) near a school or kindergarten where no road
within 50 m carries a 30 in OpenStreetMap - neither maxspeed=30 nor a
conditional, directional, HGV or zone variant of it. The steps are the generic
ones in campaign.py; this module holds the sign, what counts as a mapped 30, the
distances and the task text. Used by schools_tempo30_campaign/maproulette_tasks.ipynb.
"""

from __future__ import annotations

import geopandas as gpd
import pandas as pd

import campaign

# Mapillary class -> sign number.
ZEICHEN = {"regulatory--maximum-speed-limit-30--g1": "274-30"}

# Road types a 30 sign can apply to - the filter of the 2025 round. Motorways,
# living streets, tracks and paths are not among them.
STRASSENTYPEN = (
    "trunk",
    "primary",
    "secondary",
    "tertiary",
    "trunk_link",
    "primary_link",
    "secondary_link",
    "tertiary_link",
    "unclassified",
    "residential",
    "service",
    "road",
)

# A sign becomes a task when no road within this radius carries a 30.
SUCHRADIUS_M = 50.0

# ... and when a school or kindergarten lies within this distance. The 2025 round
# buffered the sign by 50 m and the school by 400 m and took the signs whose
# buffers met - that is, up to 450 m between sign and school.
SCHULRADIUS_M = 450.0

# Signs closer to each other than this become one task, the one seen last.
ZUSAMMENFASSEN_M = 30.0

# Columns that hold a plain value, and columns that hold a conditional one
# ("30 @ (Mo-Fr 07:00-17:00)"), in the maxspeed extract of 0_prepare_osm_network.
_GLEICH_30 = ("maxspeed", "maxspeed_forward", "maxspeed_backward", "maxspeed_hgv")
_BEDINGT_30 = (
    "maxspeed_conditional",
    "maxspeed_forward_conditional",
    "maxspeed_backward_conditional",
    "maxspeed_hgv_conditional",
)

_MAPILLARY_HIGHLIGHT = "".join(
    f"&trafficSign[]={value}"
    for value in (
        "regulatory--maximum-speed-limit-30--g1",
        "regulatory--maximum-speed-limit-50--g1",
        "warning--roadworks--g1",
    )
)


def filter_tempo30_ways(ways, verbose=True):
    """The roads of STRASSENTYPEN with a 30 in OSM, as the 2025 round counted it.

    A 30 is maxspeed, maxspeed:forward, :backward or :hgv equal to "30", one of
    their :conditional variants containing "30 @", or zone:maxspeed=DE:30.
    Missing columns are skipped.
    """
    strassen = ways[ways["highway"].isin(STRASSENTYPEN)]
    treffer = pd.Series(False, index=strassen.index)
    for spalte in _GLEICH_30:
        if spalte in strassen.columns:
            treffer |= strassen[spalte].eq("30")
    for spalte in _BEDINGT_30:
        if spalte in strassen.columns:
            treffer |= strassen[spalte].str.contains("30 @", na=False, regex=False)
    if "zone_maxspeed" in strassen.columns:
        treffer |= strassen["zone_maxspeed"].eq("DE:30")
    tempo30 = strassen[treffer]
    if verbose:
        print(f"Straßen mit Tempo 30: {len(tempo30):,} von {len(strassen):,}".replace(",", "."))
    return tempo30


def read_schools(path, verbose=True):
    """Schools and kindergartens as points and areas, as in the 2025 round.

    The extract also holds relations that are no area (type=site and the like);
    they are left out, as before.
    """
    schulen = gpd.read_parquet(path, columns=["amenity", "osm_layer", "geometry"])
    schulen = schulen[schulen["osm_layer"].isin(["points", "multipolygons"])].reset_index(drop=True)
    if verbose:
        print(f"Schulen und Kitas: {len(schulen):,}".replace(",", "."))
    return schulen


def _instruction(aufnahme, image_url, lat, lon):
    bild_zeile = campaign.bild_zeile(image_url, aufnahme, "das Zeichen")
    br = campaign.BR
    osb_url = f"https://www.openstreetbrowser.org/#map=17.4/{lat}/{lon}&basemap=osm-mapnik&categories=car_maxspeed"
    unfallkarte_url = f"https://vizsim.github.io/unfallkarte/?p={lat},{lon},17.4,U,||||,,ysk"
    return f"""
### 🚧 Aufgabe: Tempo-30-Verkehrszeichen prüfen und ggf. als `maxspeed` eintragen

Bitte schaue dir den Bereich rund um dieses erkannte Verkehrszeichen an. Vermutlich fehlt hier ein Tempo-30-Abschnitt, den du ergänzen kannst: Keine Straße im Umkreis von **{SUCHRADIUS_M:.0f} m** trägt in OSM eine 30.

Schön wäre es auch, wenn du gleich weitere `maxspeed`-Angaben in der Nähe von Schule/Kindergarten ergänzt.

---

### 🖼️ Bild & Karte

{bild_zeile}

- 🗺️ In [**openstreetbrowser (maxspeed)**]({osb_url}) ansehen{br}
(Hinweis: Ist hilfreich, um den aktuellen Stand der maxspeed-Angaben vor Ort zu prüfen.)

- 🗺️ In der [**„Unfallkarte“ (maxspeed, Mapillary-Zeichen, Schulen/Kindergärten)**]({unfallkarte_url}) ansehen

---

### 📚 Nützliche Links

- [**OSM-Wiki: maxspeed**](https://wiki.openstreetmap.org/wiki/DE:Key:maxspeed)
- [**OSM-Wiki: maxspeed:conditional**](https://wiki.openstreetmap.org/wiki/DE:Key:maxspeed)
- [**Traffic Sign Tool**](https://trafficsigns.osm-verkehrswende.org/DE?signs=DE:274-30,1042-33[Mo-Fr+16:00-18:00])

---

### ✍️ Hinweise/Beispiele zum Tagging:

- **Konstant:**{br}
  `maxspeed=30`{br}
  Optional: `source:maxspeed=sign`

- **Zeitabhängig (ohne Wochentage):**{br}
  `maxspeed:conditional=30 @ (07:00-17:00)`{br}
  *(mehrere Zeitfenster per Semikolon trennen, z. B. `30 @ (07:00-08:30;13:00-16:00)`)*

- **Zeitabhängig (mit Wochentagen):**{br}
  `maxspeed:conditional=30 @ (Mo-Fr 07:00-17:00)`

- **Fahrzeugbezogen (Lkw/HGV):**{br}
  Allgemein: `maxspeed:hgv=30`{br}
  Zeitabhängig: `maxspeed:hgv:conditional=30 @ (07:00-17:00)`

- **Richtungsbezogen (abhängig von der Way-Richtung):**{br}
  z. B. stadteinwärts (Way-**forward**): `maxspeed:forward=30`{br}
  z. B. stadtauswärts (Way-**backward**): `maxspeed:backward=50`{br}
  Zeitabhängig nur **backward**: `maxspeed:backward:conditional=30 @ (07:00-08:30;13:00-16:00)`

- Falsch-Positive wie Baustellen gerne als „Not an Issue“ markieren, damit sie nicht mehr auftauchen.

Viel Erfolg beim Prüfen und Mappen! 🗺️
"""


def aufgabe(row):
    """MapRoulette properties of one task, for campaign.build_maproulette_geojson.

    Expects the columns image_id and image_captured_at. Unlike the 2025 round,
    `image_id` holds the image and the feature id the detection - they were swapped.
    """
    lat, lon = round(row.geometry.y, 6), round(row.geometry.x, 6)
    image_id = row["image_id"] if pd.notna(row["image_id"]) else None
    return {
        "image_id": image_id,
        "Verkehrzeichen": ZEICHEN[row["value"]],
        "instruction": _instruction(
            row["image_captured_at"], campaign.bild_url(image_id, _MAPILLARY_HIGHLIGHT), lat, lon
        ),
    }
