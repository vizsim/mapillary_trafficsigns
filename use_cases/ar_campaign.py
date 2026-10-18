"""Access-restriction campaign: MapRoulette tasks from Mapillary prohibition signs.

Finds prohibition signs (DE:250, 251, 253, 254, 255, 259, 260) where no OSM way
nearby carries a tag for the traffic the sign is about - a "no bicycles" sign,
say, with neither bicycle=* nor vehicle=* nor access=* on any way within 30 m.
The steps are the generic ones in campaign.py; this module holds the signs, the
OSM keys that count for each and the task text. Used by
access_restrictions_campaign/maproulette_tasks.ipynb.
"""

from __future__ import annotations

import geopandas as gpd
import numpy as np
import pandas as pd

import campaign

# Mapillary class -> (sign number, group of traffic it restricts).
# https://trafficsigns.osm-verkehrswende.org/DE?signs=DE:250 and so on
ZEICHEN = {
    "regulatory--road-closed-to-vehicles--g3": (250, "general"),
    "regulatory--no-motor-vehicles-except-motorcycles--g1": (251, "motor_vehicle"),
    "regulatory--no-heavy-goods-vehicles--g1": (253, "hgv"),
    "regulatory--no-bicycles--g1": (254, "bicycle"),
    "regulatory--no-motorcycles--g1": (255, "motorcycle"),
    "regulatory--no-pedestrians--g1": (259, "foot"),
    "regulatory--no-motor-vehicles--g1": (260, "motor_vehicle"),
}

# Group -> OSM keys whose presence on a way counts as "restriction mapped".
# Any value counts, as in the 2026 round: a no-bicycles sign next to
# bicycle=yes is a match, too. Whether the value fits is up to the mapper.
SCHLUESSEL = {
    "general": ["access", "vehicle"],
    "motor_vehicle": ["motor_vehicle", "motorcar", "vehicle", "access"],
    "hgv": ["hgv", "motor_vehicle", "vehicle", "access"],
    "bicycle": ["bicycle", "vehicle", "access"],
    "motorcycle": ["motorcycle", "motor_vehicle", "vehicle", "access"],
    "foot": ["foot", "access"],
}

# All keys of SCHLUESSEL - what the OSM extract in 0_prepare_osm_network keeps.
OSM_SCHLUESSEL = sorted({key for keys in SCHLUESSEL.values() for key in keys})

# A sign becomes a task when no way within this radius carries a key of its group.
SUCHRADIUS_M = 30.0

_MAPILLARY_HIGHLIGHT = "".join(f"&trafficSign[]={v}" for v in ZEICHEN)


def read_access_ways(path, nur_strassen=False, verbose=True):
    """The ways of the OSM extract with their access keys.

    The extract holds every way with one of OSM_SCHLUESSEL, highway or not. As
    in the 2026 round, all of them count by default - on the data of 17.10.2026
    that leaves 3,534 candidate signs. `nur_strassen=True` keeps only ways with
    a highway tag: then a parking lot with access=private no longer answers a
    sign next to it, and there are 1,054 candidates more. Of the ways that made
    the difference, about four in five were amenity=parking.
    """
    ways = gpd.read_parquet(path, columns=["highway", *OSM_SCHLUESSEL, "geometry"])
    if nur_strassen:
        ways = ways[ways["highway"].notna()].reset_index(drop=True)
    if verbose:
        art = "Straßen und Wege" if nur_strassen else "alle Wege, auch Flächen wie Parkplätze"
        print(f"Wege mit Zugangs-Tags: {len(ways):,}".replace(",", ".") + f" ({art})")
    return ways


def distance_to_matching_way(signs, ways, max_distance_m=SUCHRADIUS_M):
    """Distance of each sign to the nearest way carrying a key of the sign's group.

    Returns a Series on the index of `signs`, inf where no such way lies within
    `max_distance_m` - the same rule as the 30 m buffers of the 2026 round.
    """
    abstand = pd.Series(np.inf, index=signs.index, dtype="float64")
    gruppe = signs["value"].map(lambda value: ZEICHEN[value][1])
    for name, schluessel in SCHLUESSEL.items():
        teil = signs[gruppe == name]
        if teil.empty:
            continue
        passend = ways[ways[schluessel].notna().any(axis=1)]
        abstand.loc[teil.index] = campaign.distance_to_nearest(teil, passend, max_distance_m)
    return abstand


def _instruction(zeichen, gruppe, aufnahme, image_url):
    bild_zeile = campaign.bild_zeile(image_url, aufnahme, "das Zeichen")
    gesucht = ", ".join(f"`{key}=*`" for key in SCHLUESSEL[gruppe][:-1]) + f" oder `{SCHLUESSEL[gruppe][-1]}=*`"
    return f"""
### 🚧 Aufgabe: Verkehrszeichen **DE:{zeichen}** prüfen und Zugangsbeschränkung ergänzen

Bitte schaue dir den Bereich rund um dieses erkannte Verkehrszeichen an. Vermutlich fehlt hier eine Zugangsbeschränkung in OSM: Kein Weg im Umkreis von **{SUCHRADIUS_M:.0f} m** trägt {gesucht}.

---

### 🖼️ Bild

{bild_zeile}

---

### 📚 Nützliche Links

- 🛑 [**Traffic Sign Tool** – DE:{zeichen}](https://trafficsigns.osm-verkehrswende.org/DE?signs=DE:{zeichen})
- 🔑 [**OSM-Wiki: access**](https://wiki.openstreetmap.org/wiki/DE:Key:access)
- 🔑 [**OSM-Wiki: vehicle**](https://wiki.openstreetmap.org/wiki/DE:Key:vehicle)
- 🔑 [**OSM-Wiki: motor_vehicle**](https://wiki.openstreetmap.org/wiki/DE:Key:motor_vehicle)
- 📷 [**Chrome Browser plugin: Mapillary Traffic Sign & Image ID Copier**](https://chromewebstore.google.com/detail/mapillary-traffic-sign-im/eagencdgcmgechomeedlbkhfcihdjhdg)

---

Trage nur dann ein neues Tag ein, wenn die Beschränkung vor Ort eindeutig erkennbar ist.
Achte auf Zusatzzeichen wie „Anlieger frei“, zeitliche Einschränkungen und die Fahrtrichtung.

Viel Erfolg beim Prüfen und Mappen! 🗺️
"""


def aufgabe(row):
    """MapRoulette properties of one task, for campaign.build_maproulette_geojson.

    Expects the columns value, image_id and image_captured_at. Every task lacks
    a matching way within SUCHRADIUS_M, so the text names that radius.
    `Verkehrzeichen` is spelled as in the 2026 round and the cycleway tasks.
    """
    zeichen, gruppe = ZEICHEN[row["value"]]
    image_id = row["image_id"] if pd.notna(row["image_id"]) else None
    return {
        "image_id": image_id,
        "Verkehrzeichen": str(zeichen),
        "instruction": _instruction(
            zeichen,
            gruppe,
            row["image_captured_at"],
            campaign.bild_url(image_id, _MAPILLARY_HIGHLIGHT),
        ),
    }
