"""Generic steps of the MapRoulette campaigns: from Mapillary detections to tasks.

In one sentence: mirror the detections from data.vizsim.de, read the classes a
campaign is about, keep those seen long enough, measure the distance to what
OpenStreetMap already has, fetch the newest image of each detection and write
the tasks as GeoJSON for MapRoulette.

What differs per campaign - detection classes, OSM layer, task text - lives in
a module of its own:

    cw_campaign.py   both cycleway campaigns (traffic signs, road markings),
                     plus their weekly export for radinfra.de
    pc_campaign.py   pedestrian crossings (DE:350)

Split off cw_campaign.py when the pedestrian-crossing campaign became the first
other campaign to use these steps (#12 in docs/todo.md). The functions moved
as they were; cw_campaign re-exports them, so the cycleway notebooks still call
cw.load_features and so on.

The notebooks import it with

    import sys; sys.path.insert(0, "..")
    import campaign

The `..` works because nbconvert and the Jupyter kernel set the working
directory to the notebook's own directory - the same assumption the paths
`../../output/` and `../utils/` in the notebooks rely on. The sys.path line
goes away once the modules become an installable package (#14 in
docs/todo.md).
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

# --- Configuration ----------------------------------------------------------

DATA_URL = "https://data.vizsim.de/mapillary_trafficsigns/"

# Dateipraefix der beiden Datensaetze in output/.
PREFIX_ZEICHEN = "mapillary_traffic-signs"
PREFIX_MARKIERUNGEN = "mapillary_map-feature-points"

# Woher die beiden Datensaetze kommen und wie ihr Manifest heisst.
DATENQUELLE = {
    PREFIX_ZEICHEN: (DATA_URL, "ml-ts_metadata.json"),
    PREFIX_MARKIERUNGEN: ("https://data.vizsim.de/mapillary_map-feature-points/", "ml-mf_metadata.json"),
}

# Metrisches CRS fuer alle Abstandsrechnungen. UTM 33N wie im Vorgaenger-
# Notebook - am Westrand Deutschlands verzerrt das um gut 0,4 %, bei 30 m
# also gut 13 cm. Bewusst nicht gewechselt, damit ein Vergleich mit den alten
# Ergebnissen nur die fachlichen Aenderungen zeigt.
METRISCHES_CRS = 25833

GRAPH_URL = "https://graph.mapillary.com/"


# --- 1. Load the detections -------------------------------------------------


def sync_features(folder, prefix=PREFIX_ZEICHEN, verbose=True):
    """Aktuelle Parquets (pro Bundesland) nach `folder` spiegeln.

    Geladen wird nur, was lokal fehlt oder auf dem Server neuer ist. Die
    Metadatendatei listet die Bundeslaender des letzten Laufs und dient als
    Manifest - ohne sie wuerde ein Bundesland, das im letzten Lauf ausgefallen
    ist, still mit veralteten Daten mitlaufen.

    `prefix` waehlt den Datensatz. Ohne diesen Schritt rechnet ein Notebook auf
    dem, was zufaellig lokal liegt: beim Bau des Marking-Notebooks am
    20.09.2026 waren das Parquets vom 01.07., waehrend der Server den 17.09.
    hatte - elf Wochen Unterschied, ohne jeden Hinweis.
    """
    data_url, metadata_file = DATENQUELLE[prefix]
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)

    response = requests.get(data_url + metadata_file, timeout=60)
    response.raise_for_status()
    metadata = response.json()

    for state in sorted(metadata["bundeslaender"]):
        name = f"{prefix}_{state}_latest.parquet"
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

    # Das Manifest mitspiegeln, sonst ist der lokale Stand in sich widersprueclich:
    # Parquets vom Server, Metadatendatei von irgendwann. Genau das war am
    # 20.09.2026 der Fall - Parquets vom 17.09., ml-mf_metadata.json vom 01.07.
    # radinfra_1_export zieht aus dieser Datei das Datum fuer die veroeffentlichte README.
    manifest = folder / metadata_file
    tmp_manifest = manifest.with_name(metadata_file + ".tmp")
    tmp_manifest.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp_manifest.replace(manifest)

    if metadata.get("last_run_incomplete"):
        print(f"WARNUNG: unvollstaendig im letzten Lauf: {metadata['last_run_incomplete']}")
    return metadata


def load_features(
    folder,
    prefix=PREFIX_ZEICHEN,
    values=None,
    columns=None,
    expect_files=None,
    seen_after=None,
    first_seen_after=None,
    verbose=True,
):
    """Alle Bundesland-Parquets eines Datensatzes einlesen und verbinden.

    `prefix` waehlt den Datensatz: PREFIX_ZEICHEN fuer die Verkehrszeichen,
    PREFIX_MARKIERUNGEN fuer die Fahrbahnmarkierungen.

    Gefiltert und dedupliziert wird pro Datei, nicht erst nach dem
    Zusammenfuegen: die Dateien enthalten alle Zeichenklassen, die
    radverkehrsbezogenen sind davon ein Bruchteil. So liegt nie der gesamte
    Bundesdatensatz gleichzeitig im RAM - der ts-Lauf auf dem Server hat nur
    6 GB. `columns` schraenkt zusaetzlich ein, was ueberhaupt gelesen wird.

    `expect_files` ist der Vollstaendigkeits-Guard: fehlt eine Bundesland-Datei,
    fehlt sie auch im publizierten Ergebnis. Am 26.08.2026 ist genau das still
    durchgelaufen, deshalb hier ein Abbruch statt einer Warnung.

    `seen_after` / `first_seen_after` filtern schon beim Lesen, je Datei.
    Das spart nicht nur RAM - es bestimmt auch den Zeilenindex, und der wird
    beim Export zur Top-Level-id der GeoJSON-Features. Wer erst nach dem
    Zusammenfuegen filtert, bekommt dieselben Zeilen mit anderen ids.

    Bei doppelten ids gewinnt das erste Vorkommen in alphabetischer
    Dateireihenfolge; die Zeilenreihenfolge bleibt die der Dateien.
    """
    paths = sorted(glob.glob(str(Path(folder) / f"{prefix}_*.parquet")))
    if not paths:
        raise FileNotFoundError(f"Keine {prefix}-Parquets in {folder}")
    if expect_files is not None and len(paths) != expect_files:
        raise RuntimeError(
            f"nur {len(paths)} von {expect_files} Bundesland-Dateien in {folder} - nicht weiterverarbeiten"
        )

    frames = []
    gesehen = set()
    for path in paths:
        gdf = gpd.read_parquet(path, columns=columns)
        if values is not None:
            gdf = gdf[gdf["value"].isin(values)]
        # ISO-Datumsstrings lassen sich lexikografisch vergleichen.
        if seen_after is not None:
            gdf = gdf[gdf["last_seen_at"] > seen_after]
        if first_seen_after is not None:
            gdf = gdf[gdf["first_seen_at"] > first_seen_after]
        if gdf.empty:
            continue
        gdf = gdf.drop_duplicates(subset=["id"])
        neu = ~gdf["id"].isin(gesehen)
        if not neu.any():
            continue
        gesehen.update(gdf.loc[neu, "id"].tolist())
        frames.append(gdf.loc[neu].copy())

    if not frames:
        raise RuntimeError(f"keine Erkennungen der gesuchten Klassen in {prefix}-Parquets unter {folder}")

    signs = gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs=frames[0].crs)
    if verbose:
        print(f"{len(paths)} Dateien, {len(signs):,} Erkennungen".replace(",", "."))
    return signs


def count_expected_states(tile_cache_glob):
    """Zahl der Bundeslaender laut Tile-Cache, als Sollwert fuer `expect_files`.

    Gibt None zurueck, wenn kein Tile-Cache da ist (etwa auf einem Rechner, der
    nur die fertigen Parquets gespiegelt hat) - dann greift der Guard nicht.
    """
    treffer = len(glob.glob(str(tile_cache_glob)))
    return treffer or None


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

    Der Index wird wie bei `filter_stable_signs` bewusst nicht neu vergeben:
    GeoDataFrame.to_json() schreibt ihn als Top-Level-id der Features, und
    tippecanoe traegt die in die Vector Tiles.
    """
    inside = gpd.sjoin(points, boundary[["geometry"]].to_crs(points.crs), predicate="within", how="inner")
    inside = inside.drop(columns=["index_right"])
    if verbose:
        print(f"innerhalb der Grenze: {len(inside):,} von {len(points):,}".replace(",", "."))
    return inside


# --- 2. Time filters --------------------------------------------------------


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
    auftaucht, steht dort wirklich. `min_months=0` laesst alles durch.

    Der Index wird bewusst **nicht** neu vergeben. GeoDataFrame.to_json()
    schreibt ihn als Top-Level-`id` der Features, tippecanoe uebernimmt die in
    die Vector Tiles, und radinfra.de haengt daran. Ein Neudurchnummerieren
    wuerde die ids aller Features stillschweigend verschieben.
    """
    recent = signs[signs["last_seen_at"] > seen_after]
    if min_months > 0:
        # Unparsbare Daten werden NaT, die Differenz NaN, und NaN >= n ist
        # False - die Zeile faellt also raus. Bei min_months=0 soll dagegen
        # wirklich nichts wegfallen, deshalb hier gar nicht erst rechnen.
        stable = recent[months_seen(recent) >= min_months]
    else:
        stable = recent
    if verbose:
        print(
            f"zuletzt gesehen nach {seen_after}: {len(recent):,}  ->  "
            f"mind. {min_months} Monate Standzeit: {len(stable):,}".replace(",", ".")
        )
    return stable


# --- 3. Distances -----------------------------------------------------------


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


def dedupe_nearby(points, max_distance_m, metric_crs=METRISCHES_CRS, verbose=True):
    """Keep one point per group of points that lie within `max_distance_m` of each other.

    Groups are transitive: if A is close to B and B close to C, all three form
    one group, even when A and C are further apart. Per group the point last
    seen wins, then the one seen over the longest span, then the first in row
    order. Kept rows keep their index and their order.

    Made for the pedestrian crossings, where one crossing usually has a sign on
    each side of the road and should become one task, not two.
    """
    if points.index.has_duplicates:
        raise ValueError("points braucht einen eindeutigen Index")
    if len(points) < 2:
        return points

    geometrien = points.geometry.to_crs(metric_crs)
    links, rechts = geometrien.sindex.query(geometrien, predicate="dwithin", distance=max_distance_m)

    # Union-find over the pairs; every group ends up labelled with its lowest position.
    eltern = np.arange(len(points))

    def wurzel(i):
        while eltern[i] != i:
            eltern[i] = eltern[eltern[i]]
            i = eltern[i]
        return i

    for a, b in zip(links, rechts):
        ra, rb = wurzel(a), wurzel(b)
        if ra != rb:
            eltern[max(ra, rb)] = min(ra, rb)
    gruppe = np.array([wurzel(i) for i in range(len(points))])

    zuletzt = pd.to_datetime(points["last_seen_at"], errors="coerce")
    spanne = (zuletzt - pd.to_datetime(points["first_seen_at"], errors="coerce")).dt.days
    rang = pd.DataFrame(
        {
            "gruppe": gruppe,
            "zuletzt": zuletzt.to_numpy(),
            "spanne": spanne.to_numpy(),
            "position": np.arange(len(points)),
        }
    )
    gewinner = (
        rang.sort_values(["zuletzt", "spanne", "position"], ascending=[False, False, True], na_position="last")
        .drop_duplicates("gruppe")["position"]
        .to_numpy()
    )
    behalten = points.iloc[np.sort(gewinner)]
    if verbose:
        print(
            f"zusammengefasst (bis {max_distance_m:.0f} m Abstand): "
            f"{len(points):,} -> {len(behalten):,}".replace(",", ".")
        )
    return behalten


# --- 4. Newest Mapillary image ----------------------------------------------


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
        # Images of one capture (e.g. several cameras) share a timestamp, and the API
        # lists them in varying order. The id breaks the tie, so a rerun links the same image.
        neuestes = max(bilder, key=lambda bild: (bild["captured_at"], str(bild["id"])))
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


# --- 5. MapRoulette ---------------------------------------------------------


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


MAPROULETTE_API = "https://maproulette.org/api/v2/"

# MapRoulette's challenge states. Uploads are refused while it builds or deletes tasks.
CHALLENGE_STATUS = {
    0: "NA",
    1: "BUILDING",
    2: "FAILED",
    3: "READY",
    4: "PARTIALLY_LOADED",
    5: "FINISHED",
    6: "DELETING_TASKS",
}


def challenge_task_names(challenge_id, api_key):
    """Every task of a challenge as {name: status}, whatever its status.

    The name is the top-level `id` of the feature a task was built from - for
    these campaigns the Mapillary id of the detection.
    """
    response = requests.get(
        f"{MAPROULETTE_API}challenge/view/{challenge_id}", headers={"apiKey": api_key}, timeout=120
    )
    response.raise_for_status()
    return {str(f["properties"]["mr_taskName"]): f["properties"]["mr_taskStatus"] for f in response.json()["features"]}


def drop_known_task_names(tasks, names, verbose=True):
    """Drop the rows whose id is already the name of a task in the challenge.

    MapRoulette takes a feature with a known name as an update of that task, in
    place, instead of opening a new one. A detection whose task was closed as
    Fixed would come back as that closed task - that is, not at all.
    """
    bekannt = tasks["id"].astype(str).isin(list(names))
    if verbose:
        print(f"schon als Aufgabe in der Challenge (gleicher Name): {int(bekannt.sum())}")
    return tasks[~bekannt].reset_index(drop=True)


def _challenge_status(challenge_id, headers):
    response = requests.get(f"{MAPROULETTE_API}challenge/{challenge_id}", headers=headers, timeout=60)
    response.raise_for_status()
    return response.json().get("status")


def upload_tasks(challenge_id, collection, api_key, data_origin_date=None, verbose=True):
    """Add the tasks of `collection` to a MapRoulette challenge, then check they arrived.

    Replaces committing a GeoJSON, pushing it and "Rebuild tasks" from its URL on
    GitHub. Uses addFileTasks with removeUnmatched=false: the tasks already in the
    challenge stay as they are, open ones included.

    Refuses a challenge that is building or deleting tasks, and names the
    challenge already has (see drop_known_task_names). MapRoulette answers 204
    even when the import failed inside, so afterwards the challenge status and
    every uploaded name are checked; a gap raises.

    `data_origin_date` (YYYY-MM-DD) is the date of the data, shown in MapRoulette.
    Returns {name: status} of all tasks in the challenge after the upload.
    """
    headers = {"apiKey": api_key}
    namen = [str(f["id"]) for f in collection["features"]]
    if len(set(namen)) != len(namen):
        raise ValueError("doppelte Namen in den Aufgaben - MapRoulette legte nur eine davon an")
    if not namen:
        if verbose:
            print("keine Aufgaben - nichts hochgeladen")
        return challenge_task_names(challenge_id, api_key)

    status = _challenge_status(challenge_id, headers)
    if status in (1, 6):
        raise RuntimeError(f"Challenge {challenge_id} ist {CHALLENGE_STATUS[status]} - Upload abgelehnt")

    doppelt = sorted(set(namen) & challenge_task_names(challenge_id, api_key).keys())
    if doppelt:
        raise ValueError(
            f"{len(doppelt)} Namen gibt es in Challenge {challenge_id} schon (z. B. {doppelt[:3]}) "
            "- vorher drop_known_task_names"
        )

    params = {"lineByLine": "false", "removeUnmatched": "false"}
    if data_origin_date:
        params["dataOriginDate"] = data_origin_date
    datei = json.dumps(collection, ensure_ascii=False).encode("utf-8")
    response = requests.put(
        f"{MAPROULETTE_API}challenge/{challenge_id}/addFileTasks",
        params=params,
        headers=headers,
        # The file must come as the multipart field "json", with a file name.
        files={"json": ("tasks.geojson", datei, "application/json")},
        timeout=600,
    )
    response.raise_for_status()

    status = _challenge_status(challenge_id, headers)
    nachher = challenge_task_names(challenge_id, api_key)
    fehlend = [name for name in namen if name not in nachher]
    if status in (2, 4) or fehlend:
        raise RuntimeError(
            f"Upload nach Challenge {challenge_id} unvollständig: Status {CHALLENGE_STATUS.get(status, status)}, "
            f"{len(fehlend)} von {len(namen)} Aufgaben fehlen"
        )
    if verbose:
        print(
            f"{len(namen)} Aufgaben hochgeladen nach Challenge {challenge_id}, "
            f"Status jetzt {CHALLENGE_STATUS.get(status, status)}"
        )
    return nachher


# A hard line break in Markdown is two spaces at the end of the line. Kept as a
# constant instead of literal spaces: any editor that trims trailing whitespace
# removes them silently, and the note then runs on in MapRoulette from the link
# line instead of standing below it.
BR = "  "


def bild_zeile(image_url, aufnahme, was):
    """The image line of a task text, or a note when there is no image.

    `was` names what was detected, e.g. "das Zeichen" or "das Symbol".
    """
    if not image_url:
        return "- 📷 Kein Mapillary-Bild verfügbar."
    aufnahme_text = aufnahme.strftime("%d.%m.%Y") if pd.notna(aufnahme) else "unbekannt"
    return (
        f"- 📷 [**Mapillary-Bild anzeigen**]({image_url}){BR}\n"
        f"(Das ist die neueste Aufnahme, auf der {was} erkannt wurde: **{aufnahme_text}**.)"
    )


def bild_url(image_id, hervorhebung):
    """Link to the image in the Mapillary viewer; `hervorhebung` is the query
    string that highlights the detections, e.g. "&trafficSign[]=..."."""
    if not image_id:
        return None
    return f"https://www.mapillary.com/app/?pKey={image_id}&focus=photo{hervorhebung}"


def abstand_text(abstand, suchradius):
    """"ca. 27 m", or "mehr als 30 m" when nothing lay within `suchradius`."""
    if np.isfinite(abstand):
        return f"ca. {abstand:.0f} m"
    return f"mehr als {suchradius:.0f} m"


def build_maproulette_geojson(tasks, aufgabe):
    """GeoJSON FeatureCollection for the MapRoulette import.

    `aufgabe` turns one row into the task's MapRoulette properties - task text,
    image highlighting and links differ per campaign. Shared are the point
    geometry and the feature id, which is the Mapillary id of the detection
    and stays a string, as it exceeds 2**53.

    Expects the columns id and geometry (points); everything else is up to
    `aufgabe`.
    """
    tasks = tasks.to_crs(4326)
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "id": str(row["id"]),
                "geometry": row.geometry.__geo_interface__,
                "properties": aufgabe(row),
            }
            for _, row in tasks.iterrows()
        ],
    }


def write_geojson(collection, path, verbose=True):
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(collection, f, indent=2, ensure_ascii=False)
    tmp.replace(path)
    if verbose:
        print(f"{len(collection['features'])} Aufgaben -> {path} ({path.stat().st_size / 1e6:.1f} MB)")


# --- 6. Comparison with the previous round ----------------------------------


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
