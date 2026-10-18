"""Pedestrian-crossing campaign: MapRoulette tasks from Mapillary DE:350 signs.

Finds pedestrian-crossing signs (DE:350) where OpenStreetMap has no
`highway=crossing` node nearby. The steps are the generic ones in campaign.py;
this module holds what is specific to the campaign: the sign, the distances
and the task text. Used by pedestrian_crossing_campaign/maproulette_tasks.ipynb.

The twin for zebra markings (pedestrian_crossing_marking_campaign/) still runs
on code of its own. Once it is converted, this is the module to share, as
cw_campaign is for the two cycleway campaigns.
"""

from __future__ import annotations

import pandas as pd

import campaign

# Mapillary class -> sign number, bare, as the task text uses it.
# https://trafficsigns.osm-verkehrswende.org/DE?signs=DE:350
UEBERWEG_ZEICHEN = {
    "information--pedestrians-crossing--g1": 350,
}

# A sign becomes a task when OSM has no highway=crossing within this radius.
SUCHRADIUS_M = 50.0

# The task text says how far the nearest crossing is, up to this distance.
MESSRADIUS_M = 100.0

# Signs closer to each other than this become one task: a crossing usually has
# a sign on each side of the road. 100 m is where two 50 m circles touch - the
# 2025 rounds merged signs whose 50 m buffers overlapped.
ZUSAMMENFASSEN_M = 100.0

_MAPILLARY_HIGHLIGHT = "".join(f"&trafficSign[]={v}" for v in UEBERWEG_ZEICHEN)


def _instruction(zeichen, abstand, aufnahme, image_url):
    bild_zeile = campaign.bild_zeile(image_url, aufnahme, "das Zeichen")
    return f"""
### 🚧 Aufgabe: Fußgängerüberweg mit Verkehrszeichen **DE:{zeichen}** überprüfen und in OSM ergänzen

Bitte schaue dir den Bereich rund um dieses erkannte Verkehrszeichen an. Vermutlich fehlt hier ein Fußgängerüberweg, den du hinzufügen kannst. Der nächste in OSM gemappte Überweg (`highway=crossing`) ist **{abstand}** entfernt.

---

### 🖼️ Bild

{bild_zeile}

---

### 📚 Nützliche Links

- 🛑 [**Traffic Sign Tool** – DE:{zeichen}](https://trafficsigns.osm-verkehrswende.org/DE?signs=DE:{zeichen})
- 🚶 [**OSM-Wiki: Fußgängerüberweg**](https://wiki.openstreetmap.org/wiki/DE:Tag:highway%3Dcrossing)
- 🚶 [**OSM-Wiki: crossing allgemein**](https://wiki.openstreetmap.org/wiki/DE:Key:crossing)
- 📷 [**Chrome Browser plugin: Mapillary Traffic Sign & Image ID Copier**](https://chromewebstore.google.com/detail/mapillary-traffic-sign-im/eagencdgcmgechomeedlbkhfcihdjhdg)

---

### Kopiervorlage

`highway=crossing`{campaign.BR}
`crossing=uncontrolled`{campaign.BR}
`crossing:markings=zebra`

---

Viel Erfolg beim Prüfen und Mappen! 🗺️
"""


def aufgabe(row):
    """MapRoulette properties of one task, for campaign.build_maproulette_geojson.

    Expects the columns VZ, dist_crossing_m, image_id and image_captured_at.
    `Verkehrzeichen` is spelled as in the 2025 rounds and the cycleway tasks.
    """
    image_id = row["image_id"] if pd.notna(row["image_id"]) else None
    return {
        "image_id": image_id,
        "Verkehrzeichen": str(row["VZ"]),
        "instruction": _instruction(
            row["VZ"],
            campaign.abstand_text(row["dist_crossing_m"], MESSRADIUS_M),
            row["image_captured_at"],
            campaign.bild_url(image_id, _MAPILLARY_HIGHLIGHT),
        ),
    }
