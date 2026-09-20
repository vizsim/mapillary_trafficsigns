"""Radweg-Kampagne: aus Mapillary-Verkehrszeichen MapRoulette-Aufgaben bauen.

Der Ablauf in einem Satz: Verkehrszeichen von data.vizsim.de holen, auf
radverkehrsbezogene Zeichen und laenger stehende Schilder filtern, die ohne
OSM-Radinfra in der Naehe heraussuchen, zu jedem das neueste Mapillary-Bild
besorgen und als GeoJSON fuer MapRoulette schreiben.

Das Notebook 1b_merge_mapillary-trafficsigns_osm-cycleways.ipynb ruft nur noch
diese Funktionen auf. Die Logik liegt hier, damit sie ohne Jupyter testbar ist
und spaeter als Skript laufen kann.

Unterschiede zum Vorgaenger 1_merge_mapillary-trafficsigns_osm-cycleways.ipynb
sind in 1b_unterschiede.md aufgefuehrt.
"""

from __future__ import annotations

import glob
import gzip
import hashlib
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from email.utils import parsedate_to_datetime
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import requests

# --- Konfiguration ----------------------------------------------------------

DATA_URL = "https://data.vizsim.de/mapillary_trafficsigns/"

# Mapillary-Klasse -> deutsche Verkehrszeichennummer.
# https://trafficsigns.osm-verkehrswende.org/DE?signs=DE:237 usw.
RADWEG_ZEICHEN = {
    "regulatory--bicycles-only--g1": 237,                      # Radweg
    "regulatory--shared-path-pedestrians-and-bicycles--g1": 240,  # gemeinsamer Geh- und Radweg
    "regulatory--dual-path-bicycles-and-pedestrians--g1": 241,    # getrennter Rad- und Gehweg
    "regulatory--dual-path-pedestrians-and-bicycles--g1": 241,    # dito, andere Anordnung
}

# Metrisches CRS fuer alle Abstandsrechnungen. UTM 33N wie im Vorgaenger-
# Notebook - am Westrand Deutschlands verzerrt das um gut 0,4 %, bei 30 m
# also gut 13 cm. Bewusst nicht gewechselt, damit ein Vergleich mit den alten
# Ergebnissen nur die fachlichen Aenderungen zeigt.
METRISCHES_CRS = 25833

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

GRAPH_URL = "https://graph.mapillary.com/"


# --- 1. Verkehrszeichen laden -----------------------------------------------


def sync_traffic_signs(folder, data_url=DATA_URL, verbose=True):
    """Aktuelle Parquets (pro Bundesland) nach `folder` spiegeln.

    Geladen wird nur, was lokal fehlt oder auf dem Server neuer ist.
    `ml-ts_metadata.json` listet die Bundeslaender des letzten Laufs und dient
    als Manifest - ohne das Manifest wuerde ein Bundesland, das im letzten Lauf
    ausgefallen ist, still mit veralteten Daten mitlaufen.
    """
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)

    response = requests.get(data_url + "ml-ts_metadata.json", timeout=60)
    response.raise_for_status()
    metadata = response.json()

    for state in sorted(metadata["bundeslaender"]):
        name = f"mapillary_traffic-signs_{state}_latest.parquet"
        local_path = folder / name

        head = requests.head(data_url + name, timeout=60)
        head.raise_for_status()
        remote_mtime = parsedate_to_datetime(head.headers["Last-Modified"]).timestamp()
        if local_path.exists() and local_path.stat().st_mtime >= remote_mtime:
            if verbose:
                print(f"{state}: aktuell")
            continue

        # Unter temporaerem Namen laden, damit ein Abbruch keine halbe Datei
        # hinterlaesst, die ein spaeterer Lauf fuer vollstaendig haelt.
        tmp_path = local_path.with_name(name + ".tmp")
        md5 = hashlib.md5()
        with requests.get(data_url + name, stream=True, timeout=60) as download:
            download.raise_for_status()
            etag = download.headers.get("ETag", "").strip('"')
            with open(tmp_path, "wb") as file_handle:
                for chunk in download.iter_content(chunk_size=1024 * 1024):
                    file_handle.write(chunk)
                    md5.update(chunk)

        # Der ETag ist bei diesen Dateien die MD5-Summe des Inhalts.
        if re.fullmatch(r"[0-9a-f]{32}", etag) and etag != md5.hexdigest():
            tmp_path.unlink()
            raise RuntimeError(f"{name}: Pruefsumme stimmt nicht mit dem Server ueberein")

        # Zeitstempel des Servers uebernehmen, damit der naechste Lauf die
        # Datei als aktuell erkennt.
        os.utime(tmp_path, (remote_mtime, remote_mtime))
        tmp_path.replace(local_path)
        if verbose:
            print(f"{state}: geladen ({local_path.stat().st_size / 1e6:.1f} MB)")

    if metadata.get("last_run_incomplete"):
        print(f"WARNUNG: unvollstaendig im letzten Lauf: {metadata['last_run_incomplete']}")
    return metadata


def load_traffic_signs(folder, values=None, verbose=True):
    """Alle Bundesland-Parquets einlesen und zu einem GeoDataFrame verbinden.

    Gefiltert wird pro Datei, nicht erst nach dem Zusammenfuegen: die Dateien
    enthalten alle Zeichenklassen, die vier Radwegzeichen sind davon ein
    Bruchteil. So liegt nie der gesamte Bundesdatensatz gleichzeitig im RAM.
    """
    paths = sorted(glob.glob(str(Path(folder) / "mapillary_traffic-signs_*.parquet")))
    if not paths:
        raise FileNotFoundError(f"Keine Verkehrszeichen-Parquets in {folder}")

    frames = []
    for path in paths:
        gdf = gpd.read_parquet(path)
        if values is not None:
            gdf = gdf[gdf["value"].isin(values)]
        frames.append(gdf)

    signs = gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs=frames[0].crs)
    signs = signs.drop_duplicates(subset=["id"]).reset_index(drop=True)
    if verbose:
        print(f"{len(paths)} Dateien, {len(signs):,} Zeichen".replace(",", "."))
    return signs


def load_boundary(path):
    """Landesgrenze aus einer (ggf. gzippten) GeoJSON-Datei lesen."""
    path = str(path)
    if not path.endswith(".gz"):
        return gpd.read_file(path)
    try:
        # GDALs virtuelles Dateisystem spart das Entpacken in den RAM.
        return gpd.read_file(f"/vsigzip/{path}", engine="pyogrio")
    except Exception:
        with gzip.open(path, "rt", encoding="utf-8") as f:
            return gpd.GeoDataFrame.from_features(json.load(f), crs="EPSG:4326")


def clip_to_boundary(points, boundary, verbose=True):
    """Punkte auf das Innere von `boundary` beschraenken.

    Die Parquets sind nach Zoom-14-Kacheln geschnitten, Kacheln am Rand ragen
    ueber die Grenze hinaus.
    """
    inside = gpd.sjoin(points, boundary[["geometry"]].to_crs(points.crs), predicate="within", how="inner")
    inside = inside.drop(columns=["index_right"]).reset_index(drop=True)
    if verbose:
        print(f"innerhalb der Grenze: {len(inside):,} von {len(points):,}".replace(",", "."))
    return inside


# --- 2. Zeitliche Filter ----------------------------------------------------


def months_seen(signs):
    """Zahl der Monate zwischen erster und letzter Sichtung, je Zeile.

    Zaehlt Kalendermonate wie der Vorgaenger (Jahresdifferenz * 12 plus
    Monatsdifferenz), nur vektorisiert statt per apply ueber jede Zeile.
    """
    first = pd.to_datetime(signs["first_seen_at"])
    last = pd.to_datetime(signs["last_seen_at"])
    return ((last.dt.year - first.dt.year) * 12 + (last.dt.month - first.dt.month)).abs()


def filter_stable_signs(signs, seen_after, min_months, verbose=True):
    """Nur Schilder behalten, die zuletzt nach `seen_after` und lange genug gesehen wurden.

    `min_months` siebt temporaere Beschilderung aus (Baustellen, Umleitungen):
    ein Schild, das ueber viele Monate hinweg immer wieder auf Bildern
    auftaucht, steht dort wirklich.
    """
    recent = signs[signs["last_seen_at"] > seen_after]
    stable = recent[months_seen(recent) >= min_months].reset_index(drop=True)
    if verbose:
        print(
            f"zuletzt gesehen nach {seen_after}: {len(recent):,}  ->  "
            f"mind. {min_months} Monate Standzeit: {len(stable):,}".replace(",", ".")
        )
    return stable


# --- 3. OSM-Radinfrastruktur ------------------------------------------------

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


def filter_cycle_infrastructure(ways, verbose=True):
    """Aus dem vorgefilterten OSM-Netz die Wege mit echter Radinfrastruktur ziehen.

    Fehlende Spalten werden uebersprungen statt einen KeyError zu werfen -
    welche Tags im Parquet landen, haengt an der osmconf-ini von Notebook 0.
    """
    treffer = ways["highway"] == "cycleway"
    genutzt = ["highway=cycleway"]

    for spalte in _RADINFRA_VORHANDEN:
        if spalte in ways.columns:
            treffer |= ways[spalte].notna() & (ways[spalte] != "no")
            genutzt.append(spalte)

    for spalte in _RADINFRA_DESIGNATED:
        if spalte in ways.columns:
            treffer |= ways[spalte] == "designated"
            genutzt.append(spalte)

    fehlend = [s for s in _RADINFRA_VORHANDEN + _RADINFRA_DESIGNATED if s not in ways.columns]
    radinfra = ways[treffer]
    if verbose:
        print(f"Radinfra: {len(radinfra):,} von {len(ways):,} Wegen".replace(",", "."))
        print(f"  genutzte Tags: {', '.join(genutzt)}")
        if fehlend:
            print(f"  nicht im Parquet: {', '.join(fehlend)}")
    return radinfra


def total_km(lines, metric_crs=METRISCHES_CRS):
    """Gesamtlaenge in Kilometern."""
    return lines.to_crs(metric_crs).geometry.length.sum() / 1000


# --- 4. Abstand zur naechsten Linie -----------------------------------------


def distance_to_nearest(points, lines, max_distance_m, metric_crs=METRISCHES_CRS):
    """Abstand jedes Punkts zur naechsten Linie, gedeckelt bei `max_distance_m`.

    Gibt eine Series auf dem Index von `points` zurueck; wo im Umkreis nichts
    liegt, steht inf.

    Die Linien werden nicht umprojiziert - davon gibt es Millionen. Stattdessen
    wandert ein Puffer um die paar tausend Punkte in das CRS der Linien, und
    nur die Treffer dieses Vorfilters werden danach metrisch nachgemessen.
    Das ersetzt die zwei getrennten Pufferlaeufe (25 m und 30 m) des
    Vorgaengers durch eine Zahl, aus der sich jede Schwelle ableiten laesst.
    """
    if points.index.has_duplicates:
        raise ValueError("points braucht einen eindeutigen Index")

    leer = pd.Series(np.inf, index=points.index, dtype="float64")
    if points.empty or lines.empty:
        return leer

    puffer = points.geometry.to_crs(metric_crs).buffer(max_distance_m).to_crs(lines.crs)
    paare = gpd.sjoin(
        gpd.GeoDataFrame(geometry=puffer, crs=lines.crs),
        lines[["geometry"]],
        predicate="intersects",
        how="inner",
    )
    if paare.empty:
        return leer

    # Nur die getroffenen Linien umprojizieren, nicht das ganze Netz.
    linien_m = lines.geometry.loc[paare["index_right"].unique()].to_crs(metric_crs)
    punkte_m = points.geometry.to_crs(metric_crs)

    links = gpd.GeoSeries(punkte_m.loc[paare.index].to_numpy(), crs=metric_crs)
    rechts = gpd.GeoSeries(linien_m.loc[paare["index_right"]].to_numpy(), crs=metric_crs)
    abstaende = pd.Series(links.distance(rechts, align=False).to_numpy(), index=paare.index)

    naechste = abstaende.groupby(level=0).min()
    leer.loc[naechste.index] = naechste.to_numpy()
    return leer


def assign_priority(distances, stufen=PRIO_AB_DISTANZ):
    """Abstand -> MapRoulette-Prioritaet; unterhalb der kleinsten Schwelle NA."""
    prio = pd.Series(pd.NA, index=distances.index, dtype="Int64")
    # Aufsteigend anwenden, damit die groesste passende Schwelle gewinnt.
    for schwelle, stufe in sorted(stufen):
        prio = prio.mask(distances >= schwelle, stufe)
    return prio


# --- 5. Neuestes Mapillary-Bild ---------------------------------------------


def load_token(path="../utils/config_mapillary_privat.json", key="ACCESS_TOKEN"):
    """Zugangsdaten aus der Umgebung oder der Config-Datei."""
    env = {"ACCESS_TOKEN": "MAPILLARY_ACCESS_TOKEN", "API_KEY_MAPROULETTE": "MAPROULETTE_API_KEY"}.get(key)
    if env and os.environ.get(env):
        return os.environ[env]
    with open(path) as f:
        return json.load(f)[key]


def _graph_session(token):
    session = requests.Session()
    session.headers.update({"Authorization": f"OAuth {token}"})
    return session


def _fetch_chunk(session, ids, versuche=4):
    """Eine Sammelabfrage mit Wiederholung bei Drosselung oder Serverfehler."""
    for versuch in range(versuche):
        try:
            response = session.get(
                GRAPH_URL,
                params={"ids": ",".join(ids), "fields": "id,images{id,captured_at}"},
                timeout=120,
            )
            if response.status_code in (429, 500, 502, 503, 504):
                raise requests.HTTPError(f"HTTP {response.status_code}")
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError):
            if versuch == versuche - 1:
                raise
            # Wartezeit verdoppeln: 1 s, 2 s, 4 s.
            time.sleep(2**versuch)
    return {}


def newest_image_ids(feature_ids, token, chunk_size=50, workers=8, max_fehlerquote=0.05, verbose=True):
    """Zu jeder Feature-ID das zuletzt aufgenommene Bild, in dem das Zeichen steckt.

    Rueckgabe: DataFrame mit Index = Feature-ID (str) und den Spalten
    `image_id` (str) und `image_captured_at` (datetime, UTC).

    Zwei Dinge macht diese Funktion anders als der Vorgaenger:

    1. Sie fragt `images{id,captured_at}` ab statt nur `images`. Ohne die
       Aufnahmezeit bleibt nur die Listenreihenfolge, und die ist willkuerlich:
       an 600 Bremer Radwegzeichen war das letzte Listenelement - das der
       Vorgaenger nahm - in 84 % der Faelle nicht das neueste Bild, in 21 %
       lag mehr als ein Monat dazwischen, in 10 % mehr als ein Jahr.
    2. Sie fragt bis zu `chunk_size` Features pro Request ab (`?ids=a,b,c`)
       statt eines pro Request. Gemessen an 200 Features: 30,5 s einzeln mit
       5 Threads gegenueber 1,9 s als Sammelabfrage mit 8 Threads.

    Bleiben mehr als `max_fehlerquote` der Features ohne Bild, wirft die
    Funktion - ein stilles Teilergebnis waere hier schlimmer als ein Abbruch,
    weil die fehlenden Aufgaben ohne Foto trotzdem plausibel aussehen.
    """
    ids = [str(i) for i in feature_ids]
    if not ids:
        return pd.DataFrame(columns=["image_id", "image_captured_at"]).rename_axis("id")

    chunks = [ids[i : i + chunk_size] for i in range(0, len(ids), chunk_size)]
    session = _graph_session(token)

    antworten = {}
    fehlgeschlagen = []
    fortschritt = _progress(chunks, desc="Mapillary-Bilder", verbose=verbose)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for chunk, ergebnis in zip(chunks, pool.map(lambda c: _safe(_fetch_chunk, session, c), chunks)):
            fortschritt()
            if ergebnis is None:
                fehlgeschlagen.extend(chunk)
            else:
                antworten.update(ergebnis)

    zeilen = {}
    for feature_id in ids:
        bilder = (antworten.get(feature_id) or {}).get("images", {}).get("data", [])
        if not bilder:
            continue
        neuestes = max(bilder, key=lambda bild: bild["captured_at"])
        # Die ID bleibt ein String: Mapillary-IDs uebersteigen 2**53, als Zahl
        # in einer Spalte mit Luecken wuerde pandas sie zu float64 runden.
        zeilen[feature_id] = (str(neuestes["id"]), neuestes["captured_at"])

    result = pd.DataFrame.from_dict(zeilen, orient="index", columns=["image_id", "captured_at_ms"])
    result["image_captured_at"] = pd.to_datetime(result.pop("captured_at_ms"), unit="ms", utc=True)
    result = result.reindex(ids).rename_axis("id")

    ohne_bild = int(result["image_id"].isna().sum())
    quote = ohne_bild / len(ids)
    if verbose:
        print(f"{len(ids) - ohne_bild:,} von {len(ids):,} Features mit Bild".replace(",", "."))
        if fehlgeschlagen:
            print(f"  {len(fehlgeschlagen)} Features in fehlgeschlagenen Sammelabfragen")
    if quote > max_fehlerquote:
        raise RuntimeError(
            f"{ohne_bild} von {len(ids)} Features ohne Bild ({quote:.1%}), "
            f"erlaubt sind {max_fehlerquote:.1%} - Abfrage nicht verwertbar"
        )
    return result


def _safe(fn, *args):
    try:
        return fn(*args)
    except Exception as fehler:  # noqa: BLE001 - die Bilanz zaehlt, nicht der Typ
        print(f"  Sammelabfrage fehlgeschlagen: {fehler}")
        return None


def _progress(items, desc, verbose):
    """tqdm wenn vorhanden, sonst eine Zeile pro 10 %."""
    if not verbose:
        return lambda: None
    try:
        from tqdm.auto import tqdm

        balken = tqdm(total=len(items), desc=desc)
        return balken.update
    except ImportError:
        zustand = {"n": 0}

        def tick():
            zustand["n"] += 1
            if zustand["n"] % max(1, len(items) // 10) == 0:
                print(f"  {desc}: {zustand['n']}/{len(items)}")

        return tick


# --- 6. MapRoulette ---------------------------------------------------------


def load_challenge_tasks(challenge_id, api_key, statuses_to_keep=None):
    """Bestehende Aufgaben einer Challenge als GeoDataFrame.

    `statuses_to_keep` sind die Zustaende, die eine Neuanlage blockieren
    sollen. Standard: alles ausser Fixed, Created und Skipped - eine als
    "false positive" oder "already fixed" markierte Stelle soll nicht in der
    naechsten Runde wieder auftauchen.
    """
    response = requests.get(
        f"https://maproulette.org/api/v2/challenge/view/{challenge_id}",
        headers={"apiKey": api_key},
        timeout=120,
    )
    response.raise_for_status()
    tasks = gpd.GeoDataFrame.from_features(response.json(), crs="EPSG:4326")
    if statuses_to_keep is None:
        tasks = tasks[~tasks["mr_taskStatus"].isin(["Fixed", "Created", "Skipped"])]
    else:
        tasks = tasks[tasks["mr_taskStatus"].isin(statuses_to_keep)]
    return tasks.reset_index(drop=True)


def drop_near_existing_tasks(signs, existing, radius_m=30.0, metric_crs=METRISCHES_CRS, verbose=True):
    """Schilder entfernen, zu denen es in `existing` schon eine Aufgabe gibt.

    Der Vorgaenger verschnitt den jeweiligen Puffer des Schildes (25 m oder
    30 m) mit den vorhandenen Aufgaben. Hier gilt fuer alle derselbe Radius,
    standardmaessig der groessere der beiden - lieber eine Aufgabe zu wenig
    als eine doppelte.
    """
    if existing.empty:
        return signs
    abstand = distance_to_nearest(signs, existing, radius_m, metric_crs=metric_crs)
    behalten = signs[abstand == np.inf]
    if verbose:
        print(f"bereits als Aufgabe vorhanden: {len(signs) - len(behalten):,}".replace(",", "."))
    return behalten.reset_index(drop=True)


# Markdown braucht zwei Leerzeichen am Zeilenende fuer einen harten Umbruch.
# Als Konstante statt als echte Leerzeichen im Quelltext: jeder Editor mit
# "trim trailing whitespace" entfernt sie sonst still, und der Hinweis schliesst
# in MapRoulette an die Linkzeile an, statt darunter zu stehen.
_BR = "  "


def _instruction(zeichen, abstand_m, aufnahme, image_url, tilda_url):
    aufnahme_text = aufnahme.strftime("%d.%m.%Y") if pd.notna(aufnahme) else "unbekannt"
    bild_zeile = (
        f"- 📷 [**Mapillary-Bild anzeigen**]({image_url}){_BR}\n"
        f"(Das ist die neueste Aufnahme, auf der das Zeichen erkannt wurde: **{aufnahme_text}**.)"
        if image_url
        else "- 📷 Kein Mapillary-Bild verfügbar."
    )
    return f"""
### 🚧 Aufgabe: Verkehrszeichen **DE:{zeichen}** überprüfen und Radinfra hinzufügen

Bitte schaue dir den Bereich rund um dieses erkannte Verkehrszeichen an. Vermutlich fehlt hier eine Radinfrastruktur, die du hinzufügen kannst. Die nächste OSM-Radinfra ist **{abstand_m}** entfernt.

---

### 🖼️ Bild & Karte

{bild_zeile}

- 🗺️ [**In radinfra.de bzw. TILDA ansehen**]({tilda_url}){_BR}
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


def build_maproulette_geojson(tasks):
    """GeoJSON-FeatureCollection fuer den MapRoulette-Import.

    Erwartet die Spalten id, VZ, dist_cw_m, prio, prio_text, image_id,
    image_captured_at und Punktgeometrie in EPSG:4326.
    """
    tasks = tasks.to_crs(4326)
    features = []

    for _, row in tasks.iterrows():
        lat, lon = round(row.geometry.y, 6), round(row.geometry.x, 6)

        image_id = row["image_id"] if pd.notna(row["image_id"]) else None
        image_url = (
            f"https://www.mapillary.com/app/?pKey={image_id}&focus=photo{_MAPILLARY_HIGHLIGHT}"
            if image_id
            else None
        )
        tilda_url = (
            f"https://tilda-geo.de/regionen/radinfra?map=17.4/{lat}/{lon}"
            "&config=pdqyyt.7h3d.16g9vk&v=2&data=mapillary-cycleway-traffic-signs"
        )

        abstand = row["dist_cw_m"]
        abstand_text = "mehr als 30 m" if not np.isfinite(abstand) else f"ca. {abstand:.0f} m"

        features.append(
            {
                "type": "Feature",
                "id": str(row["id"]),
                "geometry": row.geometry.__geo_interface__,
                "properties": {
                    "image_id": image_id,
                    "Verkehrzeichen": str(row["VZ"]),
                    "instruction": _instruction(
                        row["VZ"], abstand_text, row["image_captured_at"], image_url, tilda_url
                    ),
                    "priority": int(row["prio"]),
                    "name": row["prio_text"],
                },
            }
        )

    return {"type": "FeatureCollection", "features": features}


def write_geojson(collection, path, verbose=True):
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(collection, f, indent=2, ensure_ascii=False)
    tmp.replace(path)
    if verbose:
        print(f"{len(collection['features'])} Aufgaben -> {path} ({path.stat().st_size / 1e6:.1f} MB)")


# --- 7. Vergleich mit dem vorherigen Stand ----------------------------------


def read_geojson(path):
    """GeoJSON einlesen, oder None wenn die Datei nicht existiert.

    Gedacht fuer den Stand *vor* dem Schreiben: die Aufgabendatei traegt immer
    denselben Namen, weil MapRoulette einen festen Eingabepfad braucht. Wer
    hinterher vergleichen will, muss den alten Inhalt vorher in der Hand haben.
    """
    path = Path(path)
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def compare_task_sets(alt, neu_collection):
    """Zwei Aufgabenstaende gegeneinander stellen.

    `alt` ist entweder ein Pfad oder eine bereits eingelesene
    FeatureCollection (siehe `read_geojson`). Verglichen wird ueber die
    Feature-ID des Verkehrszeichens (das Feld `id` der GeoJSON-Features);
    zusaetzlich wird gezaehlt, wie oft ein anderes Bild verlinkt wird.
    """
    if not isinstance(alt, dict):
        alt = read_geojson(alt)
    if alt is None:
        raise FileNotFoundError("kein vorheriger Stand zum Vergleichen")

    alt_bilder = {str(f["id"]): f["properties"].get("image_id") for f in alt["features"]}
    neu_bilder = {str(f["id"]): f["properties"].get("image_id") for f in neu_collection["features"]}

    gemeinsam = alt_bilder.keys() & neu_bilder.keys()
    anderes_bild = [i for i in gemeinsam if str(alt_bilder[i]) != str(neu_bilder[i])]

    return {
        "alt": len(alt_bilder),
        "neu": len(neu_bilder),
        "gemeinsam": len(gemeinsam),
        "nur_alt": sorted(alt_bilder.keys() - neu_bilder.keys()),
        "nur_neu": sorted(neu_bilder.keys() - alt_bilder.keys()),
        "anderes_bild": sorted(anderes_bild),
    }


def print_comparison(vergleich):
    print(f"  vorher:          {vergleich['alt']:>6} Aufgaben")
    print(f"  neuer Lauf:      {vergleich['neu']:>6} Aufgaben")
    print(f"  gemeinsam:       {vergleich['gemeinsam']:>6}")
    print(f"  nur alt:         {len(vergleich['nur_alt']):>6}")
    print(f"  nur neu:         {len(vergleich['nur_neu']):>6}")
    print(f"  anderes Bild:    {len(vergleich['anderes_bild']):>6}  (von {vergleich['gemeinsam']} gemeinsamen)")
