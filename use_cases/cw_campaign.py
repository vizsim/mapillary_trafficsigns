"""Cycleway campaigns: MapRoulette tasks and the radinfra.de export.

Serves both cycleway campaigns:

    cycleway_complete_campaign/          traffic signs (DE:237, 240, 241, ...)
    cycleway_complete_marking_campaign/  road markings (bicycle symbol)

The name stays `cw_campaign`: both campaigns are about cycling infrastructure,
one finds it by traffic signs, the other by road markings. What is specific to
them lives here - the sign table, OSM cycling infrastructure, task texts, the
radinfra.de export and the README published with it.

The generic steps (loading, distances, newest image, MapRoulette GeoJSON) live
in campaign.py since the pedestrian-crossing campaign uses them too. They are
re-exported below, so the cycleway notebooks keep calling cw.load_features and
so on unchanged. The notebooks import this module with

    import sys; sys.path.insert(0, "..")
    import cw_campaign as cw

Why the notebooks look the way they do - feature ids, no sync in the server
notebook, image selection - is in the READMEs of both campaign folders.
"""

from __future__ import annotations

import gzip
import json
import re
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import requests

import campaign

# Re-exported for the cycleway notebooks, which call them as cw.<name>.
from campaign import (  # noqa: F401
    DATA_URL,
    DATENQUELLE,
    GRAPH_URL,
    METRISCHES_CRS,
    PREFIX_MARKIERUNGEN,
    PREFIX_ZEICHEN,
    clip_to_boundary,
    compare_task_sets,
    count_expected_states,
    distance_to_nearest,
    drop_near_existing_tasks,
    filter_stable_signs,
    load_boundary,
    load_challenge_tasks,
    load_features,
    load_token,
    months_seen,
    newest_image_ids,
    print_comparison,
    read_geojson,
    sync_features,
    write_geojson,
)

# --- Configuration ----------------------------------------------------------

# Fahrbahnmarkierungen der Marking-Kampagne: Mapillary-Klasse -> Bezeichnung.
MARKIERUNGEN = {
    "marking--discrete--symbol--bicycle": "Lane marking - symbol (bicycle)",
}

# Mapillary-Klasse -> (VZ-Code, Beschreibung). Eine Quelle fuer beide Straenge:
# maproulette_tasks baut daraus Aufgaben, radinfra_1_export den Datensatz
# fuer radinfra.de.
# https://trafficsigns.osm-verkehrswende.org/DE?signs=DE:237 usw.
ZEICHEN = {
    "regulatory--bicycles-only--g1": ("DE:237", "Radweg"),
    "regulatory--shared-path-pedestrians-and-bicycles--g1": ("DE:240", "Gemeinsamer Geh- und Radweg"),
    # DE:241-30 und DE:241-31 unterscheiden nur die Anordnung der Symbole.
    "regulatory--dual-path-bicycles-and-pedestrians--g1": ("DE:241", "Getrennter Geh- und Radweg"),
    "regulatory--dual-path-pedestrians-and-bicycles--g1": ("DE:241", "Getrennter Geh- und Radweg"),
    "regulatory--end-of-bicycles-only--g2": ("DE:244.2", "Ende Fahrradstraße"),
    "complementary--except-bicycles--g1": ("DE:1022-10", "Radfahrer frei"),
    "complementary--bike-route--g1": ("DE:1000-33", "Radverkehr im Gegenverkehr"),
}

# Untermenge fuer die MapRoulette-Kampagne: die Zeichen, die eine eigene
# Radinfrastruktur anordnen. Zusatzzeichen wie DE:1022-10 gehoeren nicht dazu -
# sie erlauben Radverkehr, ohne dass eine Radinfra fehlen muesste.
# Wert ist die nackte Nummer, weil die Aufgabentexte sie so einsetzen.
RADWEG_ZEICHEN = {
    value: int(ZEICHEN[value][0].removeprefix("DE:"))
    for value in (
        "regulatory--bicycles-only--g1",
        "regulatory--shared-path-pedestrians-and-bicycles--g1",
        "regulatory--dual-path-bicycles-and-pedestrians--g1",
        "regulatory--dual-path-pedestrians-and-bicycles--g1",
    )
}

# Ab welchem Abstand zur naechsten OSM-Radinfra welche MapRoulette-Prioritaet
# gilt (0 = High, 1 = Medium, 2 = Low). Schilder unterhalb der kleinsten
# Schwelle werden verworfen: dort ist schon Radinfra gemappt.
PRIO_AB_DISTANZ = ((30.0, 0), (25.0, 1))

PRIO_TEXT = {
    0: "🟩 Task mit hoher Wahrscheinlichkeit valide",
    1: "🟨 Task mit mittlerer Wahrscheinlichkeit valide",
    2: "🟥 Task mit eher geringer Wahrscheinlichkeit valide",
}

# Abstand, ab dem eine Autobahn in der Naehe das Schild unbrauchbar macht
# (Radwegschilder an Autobahnauffahrten sind fast immer Fehlerkennungen).
AUTOBAHN_ABSTAND_M = 30.0


# --- 1. OSM cycling infrastructure -----------------------------------------

# Spalten, in denen jeder Wert ausser "no" Radinfrastruktur bedeutet.
_RADINFRA_VORHANDEN = (
    "cycleway",
    "cycleway_left",
    "cycleway_right",
    "cycleway_both",
    "cycleway_lane",
    "cycleway_track",
)

# Spalten, in denen genau "designated" Radinfrastruktur bedeutet.
_RADINFRA_DESIGNATED = (
    "bicycle",
    "bicycle_forward",
    "bicycle_backward",
    "sidewalk_bicycle",
    "sidewalk_left_bicycle",
    "sidewalk_right_bicycle",
    "sidewalk_both_bicycle",
)


def filter_cycle_infrastructure(ways, designated_werte=("designated",), verbose=True):
    """Aus dem vorgefilterten OSM-Netz die Wege mit echter Radinfrastruktur ziehen.

    `designated_werte` legt fest, was in den bicycle-/sidewalk-Spalten als
    Radinfrastruktur zaehlt. Die Verkehrszeichen-Kampagne nimmt nur
    "designated", die Marking-Kampagne zusaetzlich "yes" - dort geht es um
    Fahrbahnmarkierungen, die auch auf freigegebenen Wegen liegen koennen.

    Fehlende Spalten werden uebersprungen statt einen KeyError zu werfen -
    welche Tags im Parquet landen, haengt an der osmconf-ini von Notebook 0.
    """
    designated_werte = list(designated_werte)
    treffer = ways["highway"] == "cycleway"
    genutzt = ["highway=cycleway"]

    for spalte in _RADINFRA_VORHANDEN:
        if spalte in ways.columns:
            treffer |= ways[spalte].notna() & (ways[spalte] != "no")
            genutzt.append(spalte)

    for spalte in _RADINFRA_DESIGNATED:
        if spalte in ways.columns:
            treffer |= ways[spalte].isin(designated_werte)
            genutzt.append(spalte)

    fehlend = [s for s in _RADINFRA_VORHANDEN + _RADINFRA_DESIGNATED if s not in ways.columns]
    radinfra = ways[treffer]
    if verbose:
        print(f"Radinfra: {len(radinfra):,} von {len(ways):,} Wegen".replace(",", "."))
        print(f"  genutzte Tags: {', '.join(genutzt)}")
        print(f"  als Radinfra gewertet: {', '.join(designated_werte)}")
        if fehlend:
            print(f"  nicht im Parquet: {', '.join(fehlend)}")
    return radinfra


def total_km(lines, metric_crs=METRISCHES_CRS):
    """Gesamtlaenge in Kilometern."""
    return lines.to_crs(metric_crs).geometry.length.sum() / 1000


# --- 2. MapRoulette tasks --------------------------------------------------


def assign_priority(distances, stufen=PRIO_AB_DISTANZ):
    """Abstand -> MapRoulette-Prioritaet; unterhalb der kleinsten Schwelle NA."""
    prio = pd.Series(pd.NA, index=distances.index, dtype="Int64")
    # Aufsteigend anwenden, damit die groesste passende Schwelle gewinnt.
    for schwelle, stufe in sorted(stufen):
        prio = prio.mask(distances >= schwelle, stufe)
    return prio


def _instruction_zeichen(zeichen, abstand_m, aufnahme, image_url, tilda_url):
    bild_zeile = campaign.bild_zeile(image_url, aufnahme, "das Zeichen")
    return f"""
### 🚧 Aufgabe: Verkehrszeichen **DE:{zeichen}** überprüfen und Radinfra hinzufügen

Bitte schaue dir den Bereich rund um dieses erkannte Verkehrszeichen an. Vermutlich fehlt hier eine Radinfrastruktur, die du hinzufügen kannst. Die nächste OSM-Radinfra ist **{abstand_m}** entfernt.

---

### 🖼️ Bild & Karte

{bild_zeile}

- 🗺️ [**In radinfra.de bzw. TILDA ansehen**]({tilda_url}){campaign.BR}
(Hinweis: Ist hilfreich um den aktuellen Stand der Radinfrastruktur vor Ort zu prüfen.)

---

### 📚 Nützliche Links

- 🛑 [**Traffic Sign Tool** – DE:{zeichen}](https://trafficsigns.osm-verkehrswende.org/DE?signs=DE:{zeichen})
- 🚴 [**OSM-Wiki: Radverkehrsanlagen kartieren**](https://wiki.openstreetmap.org/wiki/DE:Bicycle/Radverkehrsanlagen_kartieren)
- 📷 [**Chrome Browser plugin: Mapillary Traffic Sign & Image ID Copier**](https://chromewebstore.google.com/detail/mapillary-traffic-sign-im/eagencdgcmgechomeedlbkhfcihdjhdg)

---

Viel Erfolg beim Prüfen und Mappen! 🗺️
"""


# Zeichen, die im Mapillary-Viewer hervorgehoben werden sollen.
_HERVORHEBEN = (
    "regulatory--bicycles-only--g1",
    "regulatory--shared-path-pedestrians-and-bicycles--g1",
    "regulatory--dual-path-bicycles-and-pedestrians--g1",
    "regulatory--dual-path-pedestrians-and-bicycles--g1",
    "complementary--except-bicycles--g1",
    "complementary--bike-route--g1",
    "regulatory--pedestrians-only--g1",
)

_MAPILLARY_HIGHLIGHT = "".join(f"&trafficSign[]={v}" for v in _HERVORHEBEN)

# Die Marking-Kampagne hebt das Fahrrad-Symbol statt der Verkehrszeichen hervor.
_MAPILLARY_HIGHLIGHT_MARKIERUNG = "".join(f"&mapFeature[]={v}" for v in MARKIERUNGEN)

_INSTRUCTION_MARKIERUNG_LINKS = f"""
### 📚 Nützliche Links

- OSM-Wiki: [Radinfra auf der Fahrbahn (Übersicht)](https://wiki.openstreetmap.org/wiki/Template:DE:Map_Features:cycleway)
- OSM-Wiki: [Radverkehrsanlagen kartieren](https://wiki.openstreetmap.org/wiki/DE:Bicycle/Radverkehrsanlagen_kartieren)

---

### Kopiervorlage

- Schutzstreifen:{campaign.BR}
    `cycleway:[right|left|both]=lane`{campaign.BR}
    `cycleway:[right|left|both]:lane=advisory`

- Radfahrstreifen:{campaign.BR}
    `cycleway:[right|left|both]=lane`{campaign.BR}
    `cycleway:[right|left|both]:lane=exclusive`

- Piktogrammketten:{campaign.BR}
    `cycleway:[right|left|both]=shared_lane`{campaign.BR}
    `cycleway:[right|left|both]:lane=pictogram`
"""


def _instruction_markierung(abstand_m, aufnahme, image_url, tilda_url):
    bild_zeile = campaign.bild_zeile(image_url, aufnahme, "das Symbol")
    return f"""
### 🚧 Aufgabe: Erkanntes Fahrrad-Symbol überprüfen und Radinfra hinzufügen

Bitte schaue dir den Bereich rund um dieses erkannte Map Feature an. Vermutlich fehlt hier eine Radinfrastruktur, die du hinzufügen kannst. Die nächste OSM-Radinfra ist **{abstand_m}** entfernt.

---

### 🖼️ Bild & Karte

{bild_zeile}

- 🗺️ [**In radinfra.de bzw. TILDA ansehen**]({tilda_url}){campaign.BR}
(Hinweis: Ist hilfreich um den aktuellen Stand der Radinfrastruktur vor Ort zu prüfen.)

---
{_INSTRUCTION_MARKIERUNG_LINKS}
---

Viel Erfolg beim Prüfen und Mappen! 🗺️
"""


def _abstand_text(abstand, suchradius=None):
    """campaign.abstand_text, searched up to the largest priority threshold by default."""
    grenze = suchradius if suchradius is not None else max(s for s, _ in PRIO_AB_DISTANZ)
    return campaign.abstand_text(abstand, grenze)


def _tilda_url(lat, lon, daten):
    return (
        f"https://tilda-geo.de/regionen/radinfra?map=17.4/{lat}/{lon}"
        f"&config=pdqyyt.7h3d.16g9vk&v=2&data={daten}"
    )


def aufgabe_verkehrszeichen(row):
    """MapRoulette-Properties einer Aufgabe der Verkehrszeichen-Kampagne."""
    lat, lon = round(row.geometry.y, 6), round(row.geometry.x, 6)
    image_id = row["image_id"] if pd.notna(row["image_id"]) else None
    image_url = campaign.bild_url(image_id, _MAPILLARY_HIGHLIGHT)
    tilda_url = _tilda_url(lat, lon, "mapillary-cycleway-traffic-signs")

    return {
        "image_id": image_id,
        "Verkehrzeichen": str(row["VZ"]),
        "instruction": _instruction_zeichen(
            row["VZ"], _abstand_text(row["dist_cw_m"]), row["image_captured_at"], image_url, tilda_url
        ),
        "priority": int(row["prio"]),
        "name": row["prio_text"],
    }


def aufgabe_markierung(row):
    """MapRoulette-Properties einer Aufgabe der Marking-Kampagne."""
    lat, lon = round(row.geometry.y, 6), round(row.geometry.x, 6)
    image_id = row["image_id"] if pd.notna(row["image_id"]) else None
    image_url = campaign.bild_url(image_id, _MAPILLARY_HIGHLIGHT_MARKIERUNG)
    # Die Marking-Karte blendet zusaetzlich die Verkehrszeichen ein, damit man
    # Symbol und Beschilderung zusammen sieht.
    tilda_url = _tilda_url(lat, lon, "mapillary-cycleway-markings,mapillary-cycleway-traffic-signs")

    return {
        "image_id": image_id,
        "MapFeaturePoint": row["MapFeaturePoint"],
        "instruction": _instruction_markierung(
            _abstand_text(row["dist_cw_m"]), row["image_captured_at"], image_url, tilda_url
        ),
        "priority": int(row["prio"]),
        "name": row["prio_text"],
    }


def build_maproulette_geojson(tasks, aufgabe=aufgabe_verkehrszeichen):
    """campaign.build_maproulette_geojson, with the traffic-sign task text as default.

    The task texts expect the columns dist_cw_m, prio, prio_text, image_id and
    image_captured_at, plus VZ or MapFeaturePoint.
    """
    return campaign.build_maproulette_geojson(tasks, aufgabe)


# --- 3. Export for radinfra.de ----------------------------------------------

HINWEIS_EINMALIG = "Nur einmalig detektiert, ggf. temporär wie z.B. Baustelle."

HINWEIS_1000_33 = (
    "Das Zusatzzeichen 1000-33 zeigt an, dass mit Radverkehr aus beiden Richtungen zu rechnen ist. "
    "Es wird häufig genutzt, um Einbahnstraßen für Radfahrer im Gegenverkehr freizugeben oder auf kreuzenden Radverkehr hinzuweisen. "
    "In radinfra.de ist die Darstellung des jeweiligen Einsatzkontexts aktuell noch eingeschränkt."
)

ZEICHEN_1000_33 = "complementary--bike-route--g1"

# Spalten und Reihenfolge der veroeffentlichten GeoJSON. Verbraucher (radinfra.de,
# das pmtiles-Notebook) haengen daran - Reihenfolge nicht beilaeufig aendern.
EXPORT_SPALTEN = [
    "traffic_sign",
    "traffic_sign_description",
    "Hinweis",
    "first_seen_at",
    "last_seen_at",
    "id",
    "value",
    "geometry",
]


def add_sign_labels(signs):
    """Spalten `traffic_sign` (VZ-Code) und `traffic_sign_description` ergaenzen."""
    signs = signs.copy()
    signs["traffic_sign"] = signs["value"].map(lambda v: ZEICHEN[v][0] if v in ZEICHEN else None)
    signs["traffic_sign_description"] = signs["value"].map(lambda v: ZEICHEN[v][1] if v in ZEICHEN else None)
    return signs


def add_hinweis(signs):
    """Spalte `Hinweis` fuer die Anzeige in radinfra.de.

    Zwei Faelle: erste und letzte Sichtung am selben Tag (einmalige Erkennung,
    also moeglicherweise eine Baustelle), und das Zusatzzeichen DE:1000-33, das
    ohne Erklaerung leicht falsch gelesen wird. Unparsbare Daten werden NaT und
    damit NaN - die vergleichen sich nicht mit 0, es bleibt also leer.
    """
    signs = signs.copy()
    erste = pd.to_datetime(signs["first_seen_at"], errors="coerce")
    letzte = pd.to_datetime(signs["last_seen_at"], errors="coerce")
    tage = (letzte - erste).dt.days

    signs["Hinweis"] = np.where(tage == 0, HINWEIS_EINMALIG, "")

    ziel = signs["value"].eq(ZEICHEN_1000_33)
    belegt = signs["Hinweis"].str.strip().ne("")
    signs.loc[ziel & belegt, "Hinweis"] = signs.loc[ziel & belegt, "Hinweis"] + "\n" + HINWEIS_1000_33
    signs.loc[ziel & ~belegt, "Hinweis"] = HINWEIS_1000_33
    return signs


def write_geojson_gz(gdf, path, string_columns=("id", "image_id"), verbose=True):
    """Gezippte GeoJSON schreiben, mit den grossen ids als JSON-Strings.

    Mapillary-ids uebersteigen Number.MAX_SAFE_INTEGER (2**53). Als JSON-Zahl
    rundet sie jeder JavaScript-Verbraucher - MapLibre, tippecanoe, die Webkarte -
    auf den naechsten double, und die Mapillary-Links zeigen ins Leere.
    """
    export = gdf.copy()
    for spalte in string_columns:
        if spalte in export.columns:
            export[spalte] = export[spalte].astype("string")

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with gzip.open(tmp, "wt", encoding="utf-8") as f:
        f.write(export.to_json())
    tmp.replace(path)
    if verbose:
        print(f"{len(export):,} Features -> {path} ({path.stat().st_size / 1e6:.1f} MB)".replace(",", "."))


def assert_ids_are_strings(path, fenster=4_000_000, verbose=True):
    """Nachsehen, dass die ids als JSON-Strings auf der Platte liegen.

    Geprueft wird ein Fenster vom Dateianfang per Regex, nicht die ganze Datei
    per json.load: das baute eine zweite Kopie aller Features genau am RAM-Peak.

    Auf einen double gerundete Werte >= 2**53 sind immer gerade - eine
    ueberlebende ungerade id beweist also den exakten Wert.
    """
    with gzip.open(path, "rt", encoding="utf-8") as f:
        kopf = f.read(fenster)

    als_zahl = re.findall(r'"id":\s*(\d{15,})', kopf)
    als_string = re.findall(r'"id":\s*"(\d+)"', kopf)
    if als_zahl:
        raise AssertionError(f"{len(als_zahl)} ids als JSON-Zahl geschrieben - werden in JS gerundet")
    if not als_string:
        raise AssertionError("keine String-ids im Stichproben-Fenster gefunden - Export pruefen")

    gross = [i for i in als_string if int(i) >= 2**53]
    ungerade = [i for i in gross if int(i) % 2 == 1]
    if verbose:
        print(
            f"Stichprobe: {len(als_string)} ids, {len(gross)} >= 2^53, "
            f"{len(ungerade)} davon ungerade (Beweis exakter Werte)"
        )
    return len(als_string), len(gross), len(ungerade)


# --- README for the output folder -------------------------------------------

# Die Zeichen-SVGs stammen aus dem npm-Paket @osm-traffic-signs/converter
# (Repo osmberlin/osm-traffic-sign-tool), ausgeliefert ueber jsDelivr. Die
# Version ist bewusst gepinnt, denn npm-Releases sind unveraenderlich.
#
# Vorher zeigten die Links auf trafficsigns.osm-verkehrswende.org unter
# /_next/static/media/... - in diesen Pfaden steckt ein Next.js-Build-Hash, der
# sich bei jedem Deploy aendert. Genau deshalb lieferten irgendwann alle Bilder
# 404. Ein gepinntes npm-Artefakt kann so nicht kaputtgehen.
SVG_PKG_VERSION = "0.6.0"
SVG_BASE = (
    f"https://cdn.jsdelivr.net/npm/@osm-traffic-signs/converter@{SVG_PKG_VERSION}"
    "/dist/data-svgs/DE/svgs"
)

# Reihenfolge und Metadaten der README-Tabelle:
# (VZ-Code, Mapillary-Klasse, Bezeichnung, englische Bezeichnung, *Bild-Codes).
#
# Die deutsche Bezeichnung ist kein Anzeigetext, sondern ein Schluessel: sie
# steht als `traffic_sign_description` in der veroeffentlichten GeoJSON (die
# radinfra.de liest) und zaehlt die Tabelle darueber ab. Sie muss also mit
# ZEICHEN uebereinstimmen - die englische daneben ist frei uebersetzt und
# taucht nur in README und Grafik auf.
#
# Die letzten Felder sind die VZ-Codes der anzuzeigenden Zeichen - meist mit
# dem ersten identisch, DE:241 hat zwei Varianten. Bild-URLs werden daraus
# abgeleitet, nicht gepflegt.
README_ZEICHEN = [
    ("DE:237", "regulatory--bicycles-only--g1", "Radweg", "Cycle path", "DE:237"),
    (
        "DE:240",
        "regulatory--shared-path-pedestrians-and-bicycles--g1",
        "Gemeinsamer Geh- und Radweg",
        "Shared foot and cycle path",
        "DE:240",
    ),
    (
        "DE:241",
        "regulatory--dual-path-pedestrians-and-bicycles--g1`<br>`regulatory--dual-path-bicycles-and-pedestrians--g1",
        "Getrennter Geh- und Radweg",
        "Segregated foot and cycle path",
        "DE:241-31",
        "DE:241-30",
    ),
    ("DE:244.2", "regulatory--end-of-bicycles-only--g2", "Ende Fahrradstraße", "End of bicycle road", "DE:244.2"),
    ("DE:1022-10", "complementary--except-bicycles--g1", "Radfahrer frei", "Bicycles excepted", "DE:1022-10"),
    (
        "DE:1000-33",
        "complementary--bike-route--g1",
        "Radverkehr im Gegenverkehr",
        "Cycle traffic in both directions",
        "DE:1000-33",
    ),
]


# Zeichen je Lauf, als Vergleichswert fuer die Delta-Spalte der README.
# Anders als im coverage-Repo liegt die Datei nicht in git: ts_output/ ist
# ignoriert, veroeffentlicht wird ueber B2 (upload_outputs_to_b2.sh).
SIGN_HISTORY_FILENAME = "signs_history.json"
SIGN_HISTORY_URL = DATA_URL + "cycleway-campaign/" + SIGN_HISTORY_FILENAME

# The same for the markings, next to mk_output/ - counted per MapFeaturePoint
# label instead of per sign.
MARKING_HISTORY_FILENAME = "markings_history.json"
MARKING_HISTORY_URL = DATENQUELLE[PREFIX_MARKIERUNGEN][0] + "cycleway-campaign/" + MARKING_HISTORY_FILENAME

# Platzhalter fuer ein Delta ohne Vergleichswert - wie im coverage-README.
NO_VALUE = "—"


def sign_history_path(folder, filename=SIGN_HISTORY_FILENAME):
    return Path(folder) / filename


def _parse_history(daten):
    """`{"runs": [...]}` -> Liste der Laeufe; alles Unerwartete wird verworfen."""
    runs = daten.get("runs") if isinstance(daten, dict) else None
    if not isinstance(runs, list):
        return []
    return [run for run in runs if isinstance(run, dict) and run.get("date")]


def _merge_runs(*quellen):
    """Laeufe mehrerer Quellen nach Datum vereinigen; die spaetere Quelle gewinnt."""
    nach_datum = {}
    for runs in quellen:
        for run in runs:
            nach_datum[str(run["date"])] = run
    return [nach_datum[datum] for datum in sorted(nach_datum)]


def load_sign_history(folder, url=SIGN_HISTORY_URL, filename=SIGN_HISTORY_FILENAME, verbose=True):
    """Bisherige Laeufe in chronologischer Reihenfolge.

    Gelesen wird die lokale Datei *und* - sofern `url` gesetzt ist - die zuletzt
    veroeffentlichte; bei gleichem Datum gewinnt die lokale. Der Abgleich mit
    dem Server ist hier noetig, weil `ts_output/` nicht in git liegt: ein
    Branch-Wechsel oder ein frischer Container hat den Ordner leer (so
    geschehen am 16.09.2026). Ohne ihn begaenne die Historie still von vorn,
    und die Delta-Spalte waere eine Woche lang leer, ohne dass es auffiele.

    Fehlt oder bricht beides, ist das kein Fehler: dann entfallen nur die
    Deltas, der Lauf geht weiter.
    """
    vom_server = []
    if url:
        try:
            antwort = requests.get(url, timeout=60)
            if antwort.status_code != 404:
                antwort.raise_for_status()
                vom_server = _parse_history(antwort.json())
        except (requests.RequestException, ValueError) as fehler:
            if verbose:
                print(f"Historie vom Server nicht lesbar ({fehler}) - nur lokaler Stand")

    lokal = []
    pfad = sign_history_path(folder, filename)
    if pfad.exists():
        try:
            lokal = _parse_history(json.loads(pfad.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError) as fehler:
            if verbose:
                print(f"Historie {pfad} nicht lesbar ({fehler}) - Deltas entfallen")

    runs = _merge_runs(vom_server, lokal)
    if verbose:
        print(f"Historie: {len(runs)} Laeufe ({len(vom_server)} vom Server, {len(lokal)} lokal)")
    return runs


def latest_sign_counts(runs, before=None):
    """Zaehlungen des juengsten Laufs vor `before`, dazu dessen Datum.

    `before` ist das Datum des aktuellen Laufs. Ein Wiederholungslauf am selben
    Tag - etwa nach einem Abbruch - soll sich mit der Vorwoche vergleichen und
    nicht mit sich selbst; sonst stuenden ueberall Nullen.
    """
    passend = [run for run in runs if before is None or str(run["date"]) < str(before)]
    if not passend:
        return {}, None
    letzter = max(passend, key=lambda run: str(run["date"]))
    zeichen = letzter.get("zeichen")
    return (zeichen if isinstance(zeichen, dict) else {}), str(letzter["date"])


def append_sign_history(
    folder, run_date, counts, runs=None, filename=SIGN_HISTORY_FILENAME, url=SIGN_HISTORY_URL, verbose=True
):
    """Aktuellen Lauf in die Historie schreiben - ein Eintrag je Datum.

    Ein zweiter Lauf am selben Tag ersetzt den vorhandenen Eintrag, sonst waere
    die Referenz des naechsten Laufs der Rerun von heute und alle Deltas nahe
    null.

    `runs` ist der Stand aus `load_sign_history`. Ohne ihn wird neu geladen -
    auch vom Server, sonst wuerde der geschriebene Stand die dort liegenden
    Laeufe abschneiden.
    """
    pfad = sign_history_path(folder, filename)
    if runs is None:
        runs = load_sign_history(folder, url=url, filename=filename, verbose=False)
    nach_datum = {str(run["date"]): run for run in runs}
    nach_datum[str(run_date)] = {"date": str(run_date), "zeichen": dict(counts)}
    inhalt = {"runs": [nach_datum[datum] for datum in sorted(nach_datum)]}

    tmp = pfad.with_name(pfad.name + ".tmp")
    tmp.write_text(json.dumps(inhalt, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(pfad)
    if verbose:
        print(f"Historie aktualisiert: {pfad} ({len(inhalt['runs'])} Laeufe)")
    return pfad


def format_delta(current, previous):
    """Differenz mit Vorzeichen; ohne Vergleichswert NO_VALUE."""
    if previous is None:
        return NO_VALUE
    try:
        return f"{current - int(previous):+,}"
    except (TypeError, ValueError):
        return NO_VALUE


def svg_url(sign_id):
    """VZ-Code -> SVG-URL, z. B. "DE:1022-10" -> ".../DE_1022_10.svg".

    Bildet createSvgImportname() des Pakets nach: eckige Klammern werden zu
    "__", alles uebrige Nicht-Alphanumerische zu "_".
    """
    value_part = sign_id.split(":", 1)[-1]
    ident = value_part.replace("[", "__").replace("]", "__")
    ident = re.sub(r"[^a-zA-Z0-9_]", "_", ident)
    return f"{SVG_BASE}/DE_{ident}.svg"


# Files in ts_output/ as published on data.vizsim.de, for the README. Pinned
# against the includes in scripts/upload_outputs_to_b2.sh by a test, so a new
# output file cannot go unmentioned.
README_DATEIEN = [
    ("mapillary_trafficsigns_bicycle_latest.pmtiles", "vector tiles, layer `default`, zoom 7–12"),
    (
        "mapillary_trafficsigns_bicycle_latest.geojson.gz",
        "all signs as gzipped GeoJSON; Mapillary ids are strings, as they exceed 2<sup>53</sup>",
    ),
    ("signs_by_month.svg", "the chart below"),
    ("signs_history.json", "sign counts of every run — the basis of the Δ column"),
]
README_QUELLE = "https://github.com/vizsim/mapillary_trafficsigns/tree/main/use_cases/cycleway_complete_campaign"


def _files_section(dateien):
    """`## Files` section of a published README, from (name, content) pairs."""
    # The README is read on data.vizsim.de, right below the file listing of
    # its folder - not in the repository, which no longer holds these files.
    # Links are relative, so they work from the listing and from README.md.
    zeilen = "\n".join(f"| [`{name}`]({name}) | {inhalt} |" for name, inhalt in dateien)
    return f"""## Files

| File | Content |
| --- | --- |
{zeilen}

The file names stay the same from week to week, so links to them keep working."""


def build_readme(
    counts,
    stand,
    previous=None,
    previous_date=None,
    seit="2023-01-01",
    autobahn_abstand_m=30,
):
    """README-Text fuer ts_output/.

    `counts` zaehlt je `traffic_sign_description`, `stand` ist das Datum des
    Datensatzes als YYYY-MM-DD. `previous` ist dieselbe Zaehlung aus dem Lauf
    vom `previous_date` (beides aus `latest_sign_counts`); ohne sie bleibt die
    Delta-Spalte leer, statt Nullen vorzutaeuschen.

    Die deutsche Bezeichnung ist der Schluessel in beide Zaehlungen, angezeigt
    wird sie zusammen mit der englischen - siehe README_ZEICHEN.
    """
    previous = previous or {}
    zeilen = []
    for code, wording, beschreibung, english, *bilder in README_ZEICHEN:
        bild_md = " or ".join(f'<img src="{svg_url(s)}" width="40" alt="{s}">' for s in bilder)
        anzahl = counts.get(beschreibung, 0)
        zeilen.append(
            f"| {code} | {bild_md} | {beschreibung} | {english} | {anzahl:,} "
            f"| {format_delta(anzahl, previous.get(beschreibung))} | `{wording}` |"
        )

    # Die Summen zaehlen nur die Zeichen der Tabelle, nicht alles in `counts` -
    # sonst wichen Summe und Spalte voneinander ab, sobald eine Zeichenklasse
    # in den Daten auftaucht, die README_ZEICHEN (noch) nicht kennt.
    beschreibungen = [eintrag[2] for eintrag in README_ZEICHEN]
    gesamt = sum(counts.get(beschreibung, 0) for beschreibung in beschreibungen)
    gesamt_vorher = sum(previous.get(b, 0) for b in beschreibungen) if previous else None
    zeilen.append(
        f"| **Total** | | | | **{gesamt:,}** | **{format_delta(gesamt, gesamt_vorher)}** | |"
    )

    tabelle = "\n".join(
        [
            "| Code | Sign | Description (DE) | Description (EN) | Count | Δ | Mapillary class |",
            "|:-----|:----:|:-----------------|:-----------------|------:|--:|:----------------|",
            *zeilen,
        ]
    )

    eigenschaften = [f"| **Data created** | {stand} |"]
    if previous_date:
        eigenschaften.append(f"| **Previous run** | {previous_date} |")
        delta_hinweis = f"The Δ column shows the change since the previous run ({previous_date})."
    else:
        delta_hinweis = "The Δ column stays empty until a second run has been recorded."
    eigenschaften.extend(
        [
            f"| **Total signs** | {gesamt:,} |",
            f"| **Detections newer than** | {seit} |",
            f"| **Motorway exclusion** | {autobahn_abstand_m} m |",
        ]
    )
    eigenschaften_tabelle = "\n".join(["| Property | Value |", "|:---------|------:|", *eigenschaften])

    return f"""
# Bicycle Infrastructure Traffic Signs

Every traffic sign related to cycling infrastructure in Germany that Mapillary has
detected — the weekly export used by radinfra.de, updated every Wednesday. How it is
built is documented in the
[source repository]({README_QUELLE}).

{eigenschaften_tabelle}

Signs within {autobahn_abstand_m} m of a motorway are excluded — detections there are
overwhelmingly false positives.

{_files_section(README_DATEIEN)}

## Signs

{tabelle}

{delta_hinweis}

## Detections per month

![Signs per month](signs_by_month.svg)

Data © Mapillary, redistributed under [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/).
"""


# --- 4. Export of the markings for radinfra.de ------------------------------

# Spalten und Reihenfolge der veroeffentlichten Markierungs-GeoJSON.
EXPORT_SPALTEN_MARKIERUNGEN = [
    "MapFeaturePoint",
    "first_seen_at",
    "last_seen_at",
    "id",
    "value",
    "geometry",
]


def add_marking_label(features):
    """Spalte `MapFeaturePoint` mit der lesbaren Bezeichnung ergaenzen."""
    features = features.copy()
    features["MapFeaturePoint"] = features["value"].map(MARKIERUNGEN)
    return features


def filter_by_days_seen(features, min_days, verbose=True):
    """Nur Erkennungen behalten, zwischen deren erster und letzter Sichtung
    mehr als `min_days` Tage liegen.

    Die Marking-Kampagne rechnet in Tagen, die Verkehrszeichen-Kampagne in
    Monaten (`filter_stable_signs`) - beides gewachsen, beides beibehalten,
    damit die veroeffentlichten Staende vergleichbar bleiben.

    Der Index wird nicht neu vergeben, er wird beim Export zur Feature-id.
    """
    erste = pd.to_datetime(features["first_seen_at"], errors="coerce")
    letzte = pd.to_datetime(features["last_seen_at"], errors="coerce")
    uebrig = features[(letzte - erste).dt.days > min_days]
    if verbose:
        print(f"mehr als {min_days} Tage zwischen erster und letzter Sichtung: "
              f"{len(uebrig):,} von {len(features):,}".replace(",", "."))
    return uebrig


# Files in mk_output/ as published on data.vizsim.de - pinned against the
# upload script like README_DATEIEN.
README_DATEIEN_MARKIERUNGEN = [
    ("mapillary_markings_bicycle_latest.pmtiles", "vector tiles, layer `default`, zoom 7–12"),
    (
        "mapillary_markings_bicycle_latest.geojson.gz",
        "all markings as gzipped GeoJSON; Mapillary ids are strings, as they exceed 2<sup>53</sup>",
    ),
    ("markings_by_month.svg", "the chart below"),
    ("markings_history.json", "marking counts of every run — the basis of the Δ row"),
]
README_QUELLE_MARKIERUNGEN = (
    "https://github.com/vizsim/mapillary_trafficsigns/tree/main/use_cases/cycleway_complete_marking_campaign"
)


def build_readme_markierungen(
    counts, stand, previous=None, previous_date=None, seit="2023-01-01", min_days=180
):
    """README text for mk_output/, laid out like `build_readme` for ts_output/.

    `counts` and `previous` count per MapFeaturePoint label, as the history
    stores them (`latest_sign_counts`). Without `previous` the Δ row shows
    NO_VALUE instead of pretending nothing changed.
    """
    # Only the labels in MARKIERUNGEN count, as in build_readme - a class that
    # appears in one run's counts but not the other's would skew the delta.
    labels = list(MARKIERUNGEN.values())
    gesamt = sum(counts.get(label, 0) for label in labels)
    gesamt_vorher = sum(previous.get(label, 0) for label in labels) if previous else None

    eigenschaften = [f"| **Data created** | {stand} |"]
    if previous_date:
        eigenschaften.append(f"| **Previous run** | {previous_date} |")
    eigenschaften.extend(
        [
            f"| **Total markings** | {gesamt:,} |",
            f"| **Δ since previous run** | {format_delta(gesamt, gesamt_vorher)} |",
            f"| **Detections newer than** | {seit} |",
            f"| **First to last sighting** | more than {min_days} days |",
        ]
    )
    eigenschaften_tabelle = "\n".join(["| Property | Value |", "|:---------|------:|", *eigenschaften])

    klassen = ", ".join(f"`{klasse}`" for klasse in MARKIERUNGEN)
    return f"""
# Bicycle Road Markings

Every bicycle symbol painted on the road in Germany that Mapillary has detected
({klassen}) — the weekly export used by radinfra.de,
updated every Thursday. How it is built is documented in the
[source repository]({README_QUELLE_MARKIERUNGEN}).

{eigenschaften_tabelle}

Only markings seen over more than {min_days} days are included — a single sighting can
be a false detection or a temporary marking.

{_files_section(README_DATEIEN_MARKIERUNGEN)}

## Detections per month

![Markings per month](markings_by_month.svg)

Data © Mapillary, redistributed under [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/).
"""


def read_dataset_metadata(path):
    """ml-ts_metadata.json lesen; gibt (ml_data_from, processed_date, bundeslaender) zurueck.

    Fehlt die Datei - etwa auf einem Rechner, der nur die Parquets gespiegelt
    hat -, kommt (None, None, {}) zurueck.
    """
    path = Path(path)
    if not path.exists():
        return None, None, {}
    with open(path, encoding="utf-8") as f:
        meta = json.load(f)
    return meta.get("ml_data_from"), meta.get("processed_date"), meta.get("bundeslaender", {})


def dataset_stand(dates, fallback=None):
    """Juengstes Datum aus `dates` als YYYY-MM-DD, sonst `fallback` bzw. heute."""
    gueltig = [d for d in dates if d]
    if gueltig:
        try:
            return sorted(pd.to_datetime(gueltig))[-1].strftime("%Y-%m-%d")
        except (ValueError, TypeError):
            pass
    return fallback or datetime.now().strftime("%Y-%m-%d")
