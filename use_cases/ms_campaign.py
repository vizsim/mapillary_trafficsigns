"""Maxspeed campaign: main-road sections without maxspeed, with a speed sign and accidents.

Finds sections of main road (trunk to tertiary) without maxspeed in OpenStreetMap
that carry at least one speed-limit sign detected by Mapillary, and counts the
accidents with injuries on each section from the Unfallatlas. A section with
enough accidents becomes a task; the count sets its MapRoulette priority.

A section is a run of connected main-road ways without maxspeed that share their
name (or, without a name, their ref). Counting per OSM way instead would follow
the way splitting of OSM: in towns a road is often cut into pieces of 30 m, and
the piece with the sign rarely holds the accidents.

An accident or a sign belongs to the main road nearest to it - but only if no other
road is clearly closer. Without that rule an accident on a side street a few metres
from the junction would count for the main road. A buffer around each way would
also count every accident at a junction once for each way that meets there.

The generic steps are in campaign.py; this module holds the road types, the
sections, the assignment, the accident data and the task text. Used by
maxspeed_accidents_campaign/maproulette_tasks.ipynb.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import requests
import shapely

import campaign

# --- Configuration ----------------------------------------------------------

# Road types a task can be about.
HAUPTSTRASSEN = (
    "trunk",
    "trunk_link",
    "primary",
    "primary_link",
    "secondary",
    "secondary_link",
    "tertiary",
    "tertiary_link",
)

# Every road type in the roads extract of 0_prepare_osm_network. The ones that are
# no main road are only there so that an accident or a sign can be given to the
# side street or motorway it is on. A test keeps the list and the extract in step.
STRASSENTYPEN = HAUPTSTRASSEN + (
    "motorway",
    "motorway_link",
    "unclassified",
    "residential",
    "living_street",
    "road",
    "busway",
)

AUTOBAHNEN = ("motorway", "motorway_link")

# A way counts as mapped when one of these is set; maxspeed:type, source:maxspeed
# or zone:maxspeed alone does not count - the value itself is missing.
MAXSPEED_SPALTEN = ("maxspeed", "maxspeed_forward", "maxspeed_backward")

# Speed signs, by value. 10 and 20 are left out: at main roads that already have a
# maxspeed they matched it in 4 and 11 % of cases - mostly car parks and side streets.
TEMPI = (30, 40, 50, 60, 70, 80, 90, 100, 110, 120, 130)
ZEICHEN = tuple(f"regulatory--maximum-speed-limit-{tempo}--g1" for tempo in TEMPI)
_TEMPO_AUS_ZEICHEN = re.compile(r"^regulatory--maximum-speed-limit-(\d+)--g1$")

# How far an accident or a sign may be from its main road ...
UNFALL_MAX_M = 15.0
ZEICHEN_MAX_M = 20.0
# ... and how much closer another road may be before it takes the point instead.
NAEHER_ALS_M = 3.0

# Signs this close to a motorway are dropped: they are mostly motorway signs seen
# from a bridge or a slip road (as AUTOBAHN_ABSTAND_M in cw_campaign).
AUTOBAHN_ABSTAND_M = 30.0

# Signs this close to a task of the Tempo-30 campaign are dropped, so that no sign
# turns up in both.
T30_ABSTAND_M = 30.0

# Accidents of these years. Every state is in the Unfallatlas from 2020 on; with
# earlier years Bavaria and Baden-Wuerttemberg would count four years more than NRW.
UNFALL_JAHRE = (2020, 2025)

# Accidents on a section -> MapRoulette priority (0 = High, 1 = Medium). Below the
# smallest threshold a section is no task.
PRIO_AB_UNFAELLE = ((10, 0), (4, 1))

PRIO_TEXT = {0: "hoch", 1: "mittel"}

# A task lists at most this many signs, the ones seen last first.
MAX_ZEICHEN_JE_AUFGABE = 5

UNFALL_URL = "https://data.vizsim.de/unfallorte/"
UNFALL_SPALTEN = ["unfall_id", "UJAHR", "UKATEGORIE", "ULAND", "geometry"]
BUNDESLAENDER = 16

QUELLENVERMERK = (
    "Unfalldaten: Unfallatlas, © Statistische Ämter des Bundes und der Länder, "
    "[dl-de/by-2-0](https://www.govdata.de/dl-de/by-2-0), "
    "[unfallatlas.statistikportal.de](https://unfallatlas.statistikportal.de/); "
    f"aufbereitet von vizsim ([data.vizsim.de/unfallorte]({UNFALL_URL})), "
    f"hier gezählt je Straßenabschnitt, {UNFALL_JAHRE[0]}–{UNFALL_JAHRE[1]}."
)


# --- 1. Roads and sections ---------------------------------------------------


def read_roads(path, metric_crs=campaign.METRISCHES_CRS, verbose=True):
    """The roads extract, in the metric CRS, with the columns this campaign uses.

    Raises if the extract holds a road type this module does not know - then the
    extract and STRASSENTYPEN have drifted apart.
    """
    spalten = ["osm_id", "highway", *MAXSPEED_SPALTEN, "name", "ref", "geometry"]
    roads = gpd.read_parquet(path, columns=spalten)
    fremd = sorted(set(roads["highway"].dropna()) - set(STRASSENTYPEN))
    if fremd:
        raise ValueError(f"unbekannte Straßentypen im Auszug: {fremd}")
    roads = roads.to_crs(metric_crs).reset_index(drop=True)
    if verbose:
        haupt = roads["highway"].isin(HAUPTSTRASSEN)
        print(f"Straßen: {zahl(len(roads))}, davon Hauptstraßen: {zahl(haupt.sum())}")
    return roads


def hat_maxspeed(ways):
    """True where maxspeed, maxspeed:forward or :backward is set. Missing columns are skipped."""
    treffer = pd.Series(False, index=ways.index)
    for spalte in MAXSPEED_SPALTEN:
        if spalte in ways.columns:
            treffer |= ways[spalte].notna()
    return treffer


def _komponenten(n, a, b):
    """Connected components of n nodes and the edges a[i]-b[i], labelled 0, 1, ...

    Label propagation with pointer jumping instead of scipy: scipy only comes with
    the old Mapillary SDK, which is due to go.
    """
    label = np.arange(n)
    while True:
        kleiner = np.minimum(label[a], label[b])
        neu = label.copy()
        np.minimum.at(neu, a, kleiner)
        np.minimum.at(neu, b, kleiner)
        neu = neu[neu]
        if np.array_equal(neu, label):
            return np.unique(label, return_inverse=True)[1]
        label = neu


def abschnitte(ways):
    """Section label per way: connected ways that share their name, else their ref.

    Two ways are connected when they share an end node. Ways without name and ref
    form sections among themselves. Expects LineStrings, as the GDAL OSM driver
    writes them.
    """
    n = len(ways)
    if n == 0:
        return np.array([], dtype=np.int64)
    schluessel = ways["name"].fillna(ways["ref"]).fillna("").to_numpy()
    geometrien = ways.geometry.values
    anfang = shapely.get_coordinates(shapely.get_point(geometrien, 0))
    ende = shapely.get_coordinates(shapely.get_point(geometrien, -1))
    enden = pd.DataFrame({
        "weg": np.r_[np.arange(n), np.arange(n)],
        "x": np.r_[anfang[:, 0], ende[:, 0]],
        "y": np.r_[anfang[:, 1], ende[:, 1]],
        "schluessel": np.r_[schluessel, schluessel],
    })
    erster = enden.groupby(["x", "y", "schluessel"])["weg"].transform("min").to_numpy()
    weg = enden["weg"].to_numpy()
    kante = weg != erster
    return _komponenten(n, weg[kante], erster[kante])


# --- 2. Assignment to roads --------------------------------------------------


def _naechste(baum, punkte, max_m):
    """Position of the nearest geometry in `baum` and its distance; -1 / inf beyond max_m.

    Exact ties go to the lowest position, so a rerun picks the same road.
    """
    (ip, ig), abstand = baum.query_nearest(punkte, max_distance=max_m, return_distance=True, all_matches=True)
    paare = pd.DataFrame({"p": ip, "g": ig, "d": abstand}).sort_values(["p", "d", "g"]).drop_duplicates("p")
    position = np.full(len(punkte), -1, dtype=np.int64)
    distanz = np.full(len(punkte), np.inf)
    position[paare["p"].to_numpy()] = paare["g"].to_numpy()
    distanz[paare["p"].to_numpy()] = paare["d"].to_numpy()
    return position, distanz


def naechste_hauptstrasse(points, roads, max_m, naeher_als_m=NAEHER_ALS_M):
    """Position in `roads` of the main road each point belongs to, -1 where none.

    A point belongs to the main road nearest to it, at most `max_m` away, unless
    another road is more than `naeher_als_m` closer: then the point is on that road.
    At a junction the main road keeps the point, on the side street a few metres
    further it does not. `roads` must be in a metric CRS.
    """
    if roads.crs is None or not roads.crs.is_projected:
        raise ValueError("roads braucht ein metrisches CRS")
    punkte = points.geometry.to_crs(roads.crs).values
    alle = shapely.STRtree(roads.geometry.values)
    haupt_position = np.flatnonzero(roads["highway"].isin(HAUPTSTRASSEN).to_numpy())
    haupt = shapely.STRtree(roads.geometry.values[haupt_position])

    _, d_alle = _naechste(alle, punkte, max_m)
    h, d_haupt = _naechste(haupt, punkte, max_m)
    with np.errstate(invalid="ignore"):
        gehoert = (h >= 0) & (d_haupt - d_alle <= naeher_als_m)
    return np.where(gehoert, haupt_position[np.maximum(h, 0)], -1)


def drop_near_motorways(signs, roads, radius_m=AUTOBAHN_ABSTAND_M, verbose=True):
    """Drop the signs within `radius_m` of a motorway or motorway link."""
    autobahnen = roads[roads["highway"].isin(AUTOBAHNEN)]
    abstand = campaign.distance_to_nearest(signs, autobahnen, radius_m, metric_crs=roads.crs)
    behalten = signs[abstand == np.inf]
    if verbose:
        print(f"an einer Autobahn (bis {radius_m:.0f} m): {zahl(len(signs) - len(behalten))}")
    return behalten


def zahl(n):
    """An integer with dots between the thousands, as in German."""
    return f"{int(n):,}".replace(",", ".")


def tempo(values):
    """Speed in km/h from the Mapillary class, e.g. 50 from ...-limit-50--g1."""
    return values.str.extract(_TEMPO_AUS_ZEICHEN, expand=False).astype(int)


# --- 3. Accidents ------------------------------------------------------------


def _sha256(path):
    pruefsumme = hashlib.sha256()
    with open(path, "rb") as datei:
        for block in iter(lambda: datei.read(1024 * 1024), b""):
            pruefsumme.update(block)
    return pruefsumme.hexdigest()


def sync_unfaelle(folder, verbose=True):
    """Fetch the current accident file from data.vizsim.de, unless it is here already.

    latest.json names the file with its date (`datei`) and its SHA-256; the file is
    kept under that name, so a run can say which state it counted. Returns the path
    and latest.json. A download whose checksum does not match is thrown away.
    """
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    antwort = requests.get(UNFALL_URL + "latest.json", timeout=60)
    antwort.raise_for_status()
    latest = antwort.json()
    pfad = folder / latest["datei"]

    if pfad.exists() and _sha256(pfad) == latest["sha256"]:
        if verbose:
            print(f"{pfad.name}: aktuell")
        return pfad, latest

    tmp = pfad.with_name(pfad.name + ".tmp")
    with requests.get(UNFALL_URL + latest["datei"], stream=True, timeout=60) as download:
        download.raise_for_status()
        with open(tmp, "wb") as datei:
            for block in download.iter_content(chunk_size=1024 * 1024):
                datei.write(block)
    if _sha256(tmp) != latest["sha256"]:
        tmp.unlink()
        raise RuntimeError(f"{latest['datei']}: Prüfsumme stimmt nicht mit latest.json überein")
    tmp.replace(pfad)
    if verbose:
        print(f"{pfad.name}: geladen ({pfad.stat().st_size / 1e6:.1f} MB)")
    return pfad, latest


def load_unfaelle(path, jahre=UNFALL_JAHRE, verbose=True):
    """The accidents of `jahre` (first and last year), one row each.

    Raises when a state is missing in one of the years: then the counts would
    silently compare a year with that state to one without.
    """
    unfaelle = gpd.read_parquet(path, columns=UNFALL_SPALTEN)
    unfaelle = unfaelle[unfaelle["UJAHR"].between(*jahre)].reset_index(drop=True)
    laender = unfaelle.groupby("UJAHR")["ULAND"].nunique().reindex(range(jahre[0], jahre[1] + 1), fill_value=0)
    luecken = laender[laender < BUNDESLAENDER]
    if not luecken.empty:
        raise RuntimeError(f"nicht alle Länder in den Jahren {luecken.to_dict()} - Zählung nicht vergleichbar")
    if verbose:
        print(f"Unfälle {jahre[0]}–{jahre[1]}: {zahl(len(unfaelle))}")
    return unfaelle


# --- 4. Tasks ----------------------------------------------------------------


def prioritaet(unfaelle, stufen=PRIO_AB_UNFAELLE):
    """Accident count -> MapRoulette priority; below the smallest threshold NA."""
    prio = pd.Series(pd.NA, index=unfaelle.index, dtype="Int64")
    # Ascending, so that the largest threshold reached wins.
    for schwelle, stufe in sorted(stufen):
        prio = prio.mask(unfaelle >= schwelle, stufe)
    return prio


def abschnitt_aufgaben(ways, signs, unfaelle, verbose=True):
    """One row per section with a sign and enough accidents, ready for the task text.

    `ways`: the main-road ways without maxspeed, with a column `abschnitt` (label
    from `abschnitte`) and the CRS of the roads. `signs`: the signs on those ways,
    with `abschnitt`, `id`, `kmh`, `first_seen_at` and `last_seen_at`.
    `unfaelle`: the accidents on them, with `abschnitt` and `UKATEGORIE`.

    The task name (`id`) is the smallest OSM way id of the section, so that the
    next round finds the task again as long as that way exists. The geometry is the
    section as a line, merged where the ways meet, in EPSG:4326.
    """
    alle = pd.Index(np.unique(ways["abschnitt"]), name="abschnitt")
    zaehlung = pd.DataFrame({
        "unfaelle": unfaelle.groupby("abschnitt").size(),
        "unfaelle_schwer": unfaelle[unfaelle["UKATEGORIE"] <= 2].groupby("abschnitt").size(),
        "zeichen": signs.groupby("abschnitt").size(),
    }).reindex(alle, fill_value=0).fillna(0).astype(int)
    zaehlung["prio"] = prioritaet(zaehlung["unfaelle"])
    mit_zeichen = zaehlung["zeichen"] > 0
    auswahl = zaehlung[mit_zeichen & zaehlung["prio"].notna()].copy()
    if verbose:
        print(
            f"Abschnitte ohne maxspeed: {zahl(len(zaehlung))}, mit Zeichen: {zahl(mit_zeichen.sum())}, "
            f"davon mit mindestens {min(s for s, _ in PRIO_AB_UNFAELLE)} Unfällen: {zahl(len(auswahl))}"
        )

    # Details only for the sections that become tasks - a few hundred of ~85,000.
    teil = ways[ways["abschnitt"].isin(auswahl.index)]
    teil = teil.assign(
        laenge=teil.geometry.length,
        osm_nummer=teil["osm_id"].astype("int64"),
        rang=teil["highway"].map(HAUPTSTRASSEN.index),
    )
    gruppen = teil.groupby("abschnitt")
    auswahl["km"] = gruppen["laenge"].sum() / 1000
    auswahl["wege"] = gruppen.size()
    auswahl["id"] = gruppen["osm_nummer"].min().astype(str)
    auswahl["highway"] = np.array(HAUPTSTRASSEN)[gruppen["rang"].min().reindex(auswahl.index).to_numpy()]
    # first() skips missing values: the first name in row order, else the first ref.
    strasse = gruppen["name"].first().fillna(gruppen["ref"].first()).reindex(auswahl.index)
    auswahl["strasse"] = strasse.astype(object).where(strasse.notna(), None)

    linien = gruppen["geometry"].agg(lambda g: shapely.line_merge(shapely.multilinestrings(list(g))))
    auswahl = gpd.GeoDataFrame(auswahl, geometry=linien.reindex(auswahl.index).to_numpy(), crs=ways.crs)
    # Map links point to a spot on the section itself, not to a centroid beside it.
    mitte = auswahl.geometry.representative_point().to_crs(4326)
    auswahl["lat"], auswahl["lon"] = mitte.y.round(6).to_numpy(), mitte.x.round(6).to_numpy()

    gewaehlt = signs[signs["abschnitt"].isin(auswahl.index)].sort_values(
        ["last_seen_at", "id"], ascending=[False, True]
    )
    auswahl["zeichen_ids"] = (
        gewaehlt.groupby("abschnitt")["id"].agg(lambda ids: [str(i) for i in ids]).reindex(auswahl.index)
    )
    auswahl["tempo"] = gewaehlt.groupby("abschnitt")["kmh"].agg(
        lambda k: "/".join(str(t) for t in sorted(set(k)))
    ).reindex(auswahl.index)

    # Six decimals are about 10 cm - enough for a task, and shorter than the
    # 15 digits the reprojection leaves.
    auswahl = auswahl.to_crs(4326)
    auswahl.geometry = shapely.transform(auswahl.geometry.values, lambda xy: np.round(xy, 6))
    return auswahl.sort_values(["prio", "unfaelle"], ascending=[True, False]).reset_index()


def zeichen_liste(aufgaben, signs, bilder, max_zeichen=MAX_ZEICHEN_JE_AUFGABE):
    """Per task the signs for its text: value, sightings and newest image, at most `max_zeichen`.

    `bilder` is the result of campaign.newest_image_ids (index = feature id).
    """
    nach_id = signs.assign(id=signs["id"].astype(str)).set_index("id")
    listen = []
    for ids in aufgaben["zeichen_ids"]:
        eintraege = []
        for zeichen_id in ids[:max_zeichen]:
            zeile = nach_id.loc[zeichen_id]
            bild = bilder.loc[zeichen_id] if zeichen_id in bilder.index else None
            eintraege.append({
                "id": zeichen_id,
                "value": zeile["value"],
                "kmh": int(zeile["kmh"]),
                "first_seen_at": zeile["first_seen_at"],
                "last_seen_at": zeile["last_seen_at"],
                "image_id": bild["image_id"] if bild is not None and pd.notna(bild["image_id"]) else None,
                "image_captured_at": bild["image_captured_at"] if bild is not None else pd.NaT,
            })
        listen.append(eintraege)
    return listen


# --- 5. Task text ------------------------------------------------------------


def _km_text(km):
    return f"{km:.1f}".replace(".", ",")


def _monat(datum):
    return pd.Timestamp(datum).strftime("%m/%Y")


def _zeichen_zeile(zeichen):
    gesehen = f"gesehen {_monat(zeichen['first_seen_at'])} bis {_monat(zeichen['last_seen_at'])}"
    url = campaign.bild_url(zeichen["image_id"], f"&trafficSign[]={zeichen['value']}")
    if not url:
        return f"- **Tempo {zeichen['kmh']}** · {gesehen} · kein Mapillary-Bild verfügbar"
    aufnahme = zeichen["image_captured_at"]
    aufnahme_text = f" (Aufnahme {aufnahme.strftime('%d.%m.%Y')})" if pd.notna(aufnahme) else ""
    return f"- **Tempo {zeichen['kmh']}** · {gesehen} · [Mapillary-Bild]({url}){aufnahme_text}"


def _instruction(row):
    br = campaign.BR
    strasse = f"**{row['strasse']}**" if pd.notna(row["strasse"]) else "**unbenannten Straße**"
    schwer = row["unfaelle_schwer"]
    schwer_text = f", davon {schwer} mit Getöteten oder Schwerverletzten" if schwer else ""
    zeichen = row["zeichen_liste"]
    weitere = len(row["zeichen_ids"]) - len(zeichen)
    zeilen = "\n".join(_zeichen_zeile(z) for z in zeichen)
    if weitere > 0:
        zeilen += f"\n- … und {weitere} weitere"
    anzahl = len(row["zeichen_ids"])
    erkannt = "ein Tempo-Schild" if anzahl == 1 else f"{anzahl} Tempo-Schilder"
    lat, lon = row["lat"], row["lon"]
    osb_url = f"https://www.openstreetbrowser.org/#map=16/{lat}/{lon}&basemap=osm-mapnik&categories=car_maxspeed"
    unfallkarte_url = f"https://vizsim.github.io/unfallkarte/?p={lat},{lon},16,U,||||,,ysk"
    return f"""
### 🚦 Aufgabe: Tempolimit für diesen Straßenabschnitt eintragen

Auf diesem Abschnitt der {strasse} ({_km_text(row['km'])} km, `highway={row['highway']}`) fehlt in OSM `maxspeed`. Mapillary hat hier {erkannt} erkannt. Auf dem Abschnitt gab es {UNFALL_JAHRE[0]}–{UNFALL_JAHRE[1]} **{row['unfaelle']} Unfälle mit Personenschaden**{schwer_text}.

Bitte trage `maxspeed` für den **ganzen Abschnitt** ein, nicht nur am Schild. Wo kein Schild steht, gilt innerorts meist 50 und außerorts 100. Achte auf Zusatzzeichen: Eine Uhrzeit unter dem Schild gehört in `maxspeed:conditional`.

---

### 🪧 Erkannte Schilder

{zeilen}

---

### 🗺️ Karte

- 🗺️ In [**openstreetbrowser (maxspeed)**]({osb_url}) ansehen{br}
(Zeigt die `maxspeed`-Angaben der Umgebung.)

- 🗺️ In der [**„Unfallkarte“**]({unfallkarte_url}) ansehen

---

### ✍️ Hinweise/Beispiele zum Tagging:

- **Mit Schild:**{br}
  `maxspeed=70`{br}
  Optional: `source:maxspeed=sign`

- **Ohne Schild (innerorts/außerorts):**{br}
  `maxspeed=50` + `maxspeed:type=DE:urban`{br}
  `maxspeed=100` + `maxspeed:type=DE:rural`

- **Zeitabhängig:**{br}
  `maxspeed:conditional=30 @ (22:00-06:00)`

- **Richtungsbezogen (abhängig von der Way-Richtung):**{br}
  `maxspeed:forward=70`{br}
  `maxspeed:backward=100`

- Baustellen oder falsch erkannte Schilder gerne als „Not an Issue“ markieren.

---

{QUELLENVERMERK}
"""


def aufgabe(row):
    """MapRoulette properties of one task, for campaign.build_maproulette_geojson.

    Expects the columns of abschnitt_aufgaben plus `zeichen_liste` from zeichen_liste.
    """
    neuestes = next((z for z in row["zeichen_liste"] if z["image_id"]), None)
    return {
        "priority": int(row["prio"]),
        "prioritaet": PRIO_TEXT[int(row["prio"])],
        "unfaelle": int(row["unfaelle"]),
        "unfaelle_schwer": int(row["unfaelle_schwer"]),
        "strasse": row["strasse"] if pd.notna(row["strasse"]) else None,
        "laenge_km": round(float(row["km"]), 2),
        "tempo": row["tempo"],
        "image_id": neuestes["image_id"] if neuestes else None,
        "instruction": _instruction(row),
    }
