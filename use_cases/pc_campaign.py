"""Pedestrian-crossing campaigns: MapRoulette tasks where OSM lacks a crossing.

Serves both pedestrian-crossing campaigns, as cw_campaign does the two
cycleway ones:

    pedestrian_crossing_campaign/          traffic signs (DE:350)
    pedestrian_crossing_marking_campaign/  zebra markings (map feature points)

Both look for detections where OpenStreetMap has no `highway=crossing` node
nearby. The steps are the generic ones in campaign.py; this module holds what
the two campaigns share - the distances - and what differs: the classes and the
task texts.
"""

from __future__ import annotations

import pandas as pd

import campaign

# Mapillary class -> sign number, bare, as the task text uses it.
# https://trafficsigns.osm-verkehrswende.org/DE?signs=DE:350
UEBERWEG_ZEICHEN = {
    "information--pedestrians-crossing--g1": 350,
}

# Mapillary class -> label, for the marking campaign (map feature points).
UEBERWEG_MARKIERUNGEN = {
    "marking--discrete--crosswalk-zebra": "Lane Marking - Crosswalk",
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
_MAPILLARY_HIGHLIGHT_MARKIERUNG = "".join(f"&mapFeature[]={v}" for v in UEBERWEG_MARKIERUNGEN)

_KOPIERVORLAGE = f"""### Kopiervorlage

`highway=crossing`{campaign.BR}
`crossing=uncontrolled`{campaign.BR}
`crossing:markings=zebra`"""


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

{_KOPIERVORLAGE}

---

Viel Erfolg beim Prüfen und Mappen! 🗺️
"""


def _instruction_markierung(abstand, aufnahme, image_url):
    bild_zeile = campaign.bild_zeile(image_url, aufnahme, "die Markierung")
    return f"""
### 🚧 Aufgabe: Erkannten Zebrastreifen prüfen und Fußgängerüberweg in OSM ergänzen

Bitte schaue dir den Bereich rund um diese erkannte Fahrbahnmarkierung an. Vermutlich fehlt hier ein Fußgängerüberweg, den du hinzufügen kannst. Der nächste in OSM gemappte Überweg (`highway=crossing`) ist **{abstand}** entfernt.

---

### 🖼️ Bild

{bild_zeile}

---

### 📚 Nützliche Links

- 🚶 [**OSM-Wiki: Fußgängerüberweg**](https://wiki.openstreetmap.org/wiki/DE:Tag:highway%3Dcrossing)
- 🚶 [**OSM-Wiki: crossing allgemein**](https://wiki.openstreetmap.org/wiki/DE:Key:crossing)
- 🚶 [**OSM-Wiki: crossing:markings**](https://wiki.openstreetmap.org/wiki/Key:crossing:markings)

---

{_KOPIERVORLAGE}

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


def aufgabe_markierung(row):
    """MapRoulette properties of one task of the marking campaign.

    Expects the columns value, dist_crossing_m, image_id and image_captured_at.
    `MapFeaturePoint` is the label of the 2025 round.
    """
    image_id = row["image_id"] if pd.notna(row["image_id"]) else None
    return {
        "image_id": image_id,
        "MapFeaturePoint": UEBERWEG_MARKIERUNGEN[row["value"]],
        "instruction": _instruction_markierung(
            campaign.abstand_text(row["dist_crossing_m"], MESSRADIUS_M),
            row["image_captured_at"],
            campaign.bild_url(image_id, _MAPILLARY_HIGHLIGHT_MARKIERUNG),
        ),
    }
