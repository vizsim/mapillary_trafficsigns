"""Gemeinsame Tile-Logik für die ts- und die mk-Pipeline.

Warum als Modul und nicht je Notebook: genau die Duplizierung hat den Vorfall
vom 26.08.2026 verursacht. Der Timeout-/Retry-Fix (6a6dd81) landete nur im
mk-Notebook, das ts-Notebook blieb fünf Wochen lang unrepariert, weil niemand
sah, dass es dieselbe Stelle zweimal gibt. Beide Notebooks importieren jetzt
von hier.

Zum Kernproblem: "Error parsing message with type 'vector_tile.tile'" heisst
NICHT, dass das Tile kaputt ist. Es heisst, dass im Body etwas ankam, das kein
MVT ist - Fehlerseite, Rate-Limit-Antwort, abgeschnittener oder noch
komprimierter Stream. Deshalb hier drei Dinge:

  1. pruefen, WAS zurueckkam, bevor der Parser es sieht
  2. den Grund im Klartext festhalten (Body-Ausschnitt statt nur "Fehler")
  3. wiederholen - eine kaputte Antwort ist fast nie eine Eigenschaft des
     Tiles, der naechste Versuch liefert meist ein sauberes MVT

Das Notebook entscheidet danach anhand von TileBatch.fail_ratio, ob ueberhaupt
exportiert wird. Ein Teilstand darf einen vollstaendigen nie ueberschreiben.
"""

from __future__ import annotations

import json
import os
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone

import geopandas as gpd
import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from tqdm import tqdm
from urllib3.util.retry import Retry
from vt2geojson.tools import vt_bytes_to_geojson

TILE_API = "https://tiles.mapillary.com/maps/vtp"

# Die beiden Pipelines unterscheiden sich nur hierin.
COVERAGE_TRAFFIC_SIGNS = ("mly_map_feature_traffic_sign", "traffic_sign")
COVERAGE_MAP_FEATURES = ("mly_map_feature_point", "point")

MVT_CONTENT_TYPES = {
    "application/x-protobuf",
    "application/vnd.mapbox-vector-tile",
    "application/octet-stream",
}

# Signaturen, die eindeutig KEIN MVT sind
BAD_MAGIC = [
    (b"\x1f\x8b", "gzip-Stream, nicht dekomprimiert"),
    (b"<", "HTML/XML-Fehlerseite"),
    (b"{", "JSON-Fehlerantwort"),
]


class TileError(Exception):
    """Tile nicht ladbar. `kind` gruppiert die Ursache fuers Log, `detail` beweist sie."""

    def __init__(self, kind: str, detail: str = ""):
        super().__init__(f"{kind} - {detail}" if detail else kind)
        self.kind = kind
        self.detail = detail


_thread_local = threading.local()


def get_session() -> requests.Session:
    """Eine Session pro Thread: Connection-Pooling + automatische Retries.

    Retry deckt Verbindungsabbrueche und 429/5xx ab (inklusive Retry-After).
    Was Retry NICHT kann: eine Antwort erkennen, die mit HTTP 200 kommt, aber
    kein MVT enthaelt - genau der Fall hier. Das macht load_tile().
    """
    session = getattr(_thread_local, "session", None)
    if session is None:
        retry = Retry(
            total=5,
            connect=3,
            read=3,
            status=5,
            status_forcelist=(408, 429, 500, 502, 503, 504),
            allowed_methods=frozenset(["GET"]),
            backoff_factor=2,  # 0s, 2s, 4s, 8s, 16s
            respect_retry_after_header=True,
            raise_on_status=False,
        )
        session = requests.Session()
        session.mount("https://", HTTPAdapter(max_retries=retry, pool_maxsize=16))
        _thread_local.session = session
    return session


def _snippet(response: requests.Response, limit: int = 300) -> str:
    """Lesbarer Ausschnitt des Bodys - das Beweisstueck fuer die Diagnose.

    Gibt IMMER etwas zurueck. Ein leeres detail waere genau der Zustand, den
    wir loswerden wollen: ein Fehler ohne Hinweis, woran er lag.
    """
    ctype = response.headers.get("Content-Type", "") or "?"
    body = response.content[:limit]
    if not body:
        return f"leerer Body (Content-Type {ctype}, Server {response.headers.get('Server', '?')})"
    if ctype.startswith(("application/json", "text/")):
        return body.decode("utf-8", "replace").replace("\n", " ").strip()
    return f"Content-Type {ctype}, erste Bytes {body[:64]!r}"


def fetch_tile_bytes(tile, token: str, coverage: str) -> bytes:
    """Tile-Bytes holen und validieren, BEVOR der Protobuf-Parser sie sieht."""
    url = f"{TILE_API}/{coverage}/2/{tile.z}/{tile.x}/{tile.y}?access_token={token}"
    response = get_session().get(url, timeout=(10, 60))

    if response.status_code != 200:
        raise TileError(f"HTTP {response.status_code}", _snippet(response))

    ctype = response.headers.get("Content-Type", "").split(";")[0].strip()
    if ctype and ctype not in MVT_CONTENT_TYPES:
        raise TileError(f"kein MVT (Content-Type {ctype})", _snippet(response))

    body = response.content
    if not body:
        return b""  # leeres Tile ist legitim, kein Fehler

    for magic, label in BAD_MAGIC:
        if body.startswith(magic):
            raise TileError(f"kein MVT ({label})", _snippet(response))

    # abgeschnittener Stream: nur pruefbar, wenn nicht transparent entpackt wurde
    declared = response.headers.get("Content-Length")
    if declared is not None and response.headers.get("Content-Encoding") is None:
        if len(body) != int(declared):
            raise TileError("abgeschnittene Antwort", f"{len(body)} von {declared} Bytes")

    return body


def load_tile(tile, token: str, coverage: str, layer: str, attempts: int = 4):
    """Tile laden und parsen, mit exponentiellem Backoff.

    Rueckgabe:
      (features, None)   -> Erfolg; leere Liste = Tile ohne Objekte
      (None, TileError)  -> nach `attempts` Versuchen endgueltig gescheitert
    """
    last_error = None
    for attempt in range(attempts):
        try:
            raw = fetch_tile_bytes(tile, token, coverage)
            if not raw:
                return [], None
            try:
                geojson = vt_bytes_to_geojson(raw, tile.x, tile.y, tile.z, layer=layer)
            except Exception as exc:
                raise TileError("MVT-Parsefehler", f"{exc} | erste Bytes {raw[:16]!r}")
            return geojson.get("features", []), None
        except TileError as exc:
            last_error = exc
        except requests.RequestException as exc:
            last_error = TileError(type(exc).__name__, str(exc)[:200])

        if attempt < attempts - 1:
            # Bei Rate-Limits bringt schnelles Nachfassen nichts - warten hilft.
            time.sleep(min(60, 5 * 2**attempt) + random.uniform(0, 3))

    return None, last_error


def tile_features_to_gdf(features, tile) -> gpd.GeoDataFrame:
    """Features eines Tiles in ein GeoDataFrame, mit den Konventionen beider Pipelines."""
    gdf = gpd.GeoDataFrame.from_features(features, crs="EPSG:4326")
    # Pin the id dtype: a later concat with a tile that lacks the column
    # would turn plain int64 into float64 and silently round every id
    # above 2**53. Nullable Int64 stays exact and NA-safe.
    if "id" in gdf.columns:
        gdf["id"] = gdf["id"].astype("Int64")
    # Vektorisiert statt .apply(fromtimestamp) pro Zeile: bei 1,4 Mio Zeilen
    # (DE-NW) ist das der Unterschied zwischen Sekunden und Millisekunden -
    # und fromtimestamp(NaN) wuerde den ganzen Tile-Batch abbrechen.
    for col in ("first_seen_at", "last_seen_at"):
        if col in gdf.columns:
            gdf[col] = pd.to_datetime(gdf[col], unit="ms", utc=True).dt.strftime("%Y-%m-%d")
    gdf["tile_x"] = tile.x
    gdf["tile_y"] = tile.y
    return gdf


@dataclass
class TileBatch:
    """Ergebnis eines Durchlaufs ueber alle Tiles eines Bundeslandes."""

    total: int
    gdfs: list = field(default_factory=list)
    failed: list = field(default_factory=list)  # [(tile, TileError)]
    errors: dict = field(default_factory=dict)  # Fehlerart -> Anzahl
    samples: dict = field(default_factory=dict)  # Fehlerart -> Beispiel-Body
    empty: int = 0
    recovered: int = 0  # im Nachlauf doch noch geholt
    rounds: int = 1  # Durchlaeufe inkl. Nachlaeufe
    aborted: str = ""  # gesetzt, wenn nach Fehlern in Folge abgebrochen wurde

    @property
    def fail_ratio(self) -> float:
        return len(self.failed) / self.total if self.total else 0.0

    def report(self, emit=print) -> None:
        """Ein Bericht statt 130.000 Einzelzeilen."""
        line = (
            f"   {self.total:,} Tiles | {len(self.gdfs):,} mit Daten | "
            f"{self.empty:,} leer | {len(self.failed):,} fehlgeschlagen "
            f"({self.fail_ratio:.1%})"
        )
        if self.recovered:
            line += f" | {self.recovered:,} im Nachlauf erholt"
        emit(line)
        if self.aborted:
            emit(f"   🛑 abgebrochen: {self.aborted}")
        # errors/samples stammen aus dem ERSTEN Durchlauf - das ist die
        # Diagnose, was zurueckkam. Ob es sich erholt hat, sagt `recovered`.
        for kind, count in sorted(self.errors.items(), key=lambda kv: -kv[1]):
            emit(f"   ↳ {count:>7,}x {kind}")
            if self.samples.get(kind):
                emit(f"              Beispiel: {self.samples[kind][:200]}")

    def write_failed(self, bundesland_id: str, input_folder: str, emit=print) -> None:
        """Fehlerliste rausschreiben, damit ein Nachlauf die Luecken schliessen kann."""
        if not self.failed:
            return
        fail_dir = os.path.join(input_folder, "failed")
        os.makedirs(fail_dir, exist_ok=True)
        fail_path = os.path.join(fail_dir, f"{bundesland_id}_failed_tiles.json")
        with open(fail_path, "w") as f:
            json.dump(
                [
                    {"z": t.z, "x": t.x, "y": t.y, "error": e.kind}
                    for t, e in self.failed
                    if t is not None
                ],
                f,
            )
        emit(f"   ↳ Fehlerliste für Nachlauf: {fail_path}")


def fetch_tiles(
    tiles, token, coverage, layer, max_workers=3, desc="", emit=print, abort_after=30
) -> TileBatch:
    """Alle Tiles eines Bundeslandes holen und zu GeoDataFrames verarbeiten.

    abort_after: nach so vielen Fehlern IN FOLGE wird abgebrochen und der Rest
    als "nicht versucht" verbucht. Manche Fehlerzustaende treffen jede Tile
    gleichermassen (z. B. HTTP 200 mit einer HTML-Seite statt MVT); 4 Versuche
    mit Backoff pro Tile wuerden den Lauf dann um Groessenordnungen verlaengern.
    Lieber nach Minuten aufgeben, die Reissleine greifen lassen und im Nachlauf
    pruefen, ob der Zustand vorbei ist.
    """
    batch = TileBatch(total=len(tiles))

    def process_tile(tile):
        features, error = load_tile(tile, token, coverage, layer)
        if error is not None:
            return tile, None, error
        if not features:
            return tile, None, None
        return tile, tile_features_to_gdf(features, tile), None

    def note(kind, detail):
        batch.errors[kind] = batch.errors.get(kind, 0) + 1
        batch.samples.setdefault(kind, detail)

    def record(future, tile):
        """Ergebnis verbuchen; Rueckgabe: war es ein Fehler?"""
        try:
            _, gdf_tile, error = future.result()
        except Exception as exc:
            kind = f"unerwartet: {type(exc).__name__}"
            note(kind, str(exc)[:200])
            batch.failed.append((tile, TileError(kind, str(exc)[:200])))
            return True
        if error is not None:
            batch.failed.append((tile, error))
            note(error.kind, error.detail)
            return True
        if gdf_tile is None:
            batch.empty += 1
        else:
            batch.gdfs.append(gdf_tile)
        return False

    consecutive = 0
    recorded = set()
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(process_tile, tile): tile for tile in tiles}
        # In Einreihungsreihenfolge verbuchen, nicht per as_completed: das
        # liefert bereits fertige Futures in beliebiger Reihenfolge, und "Fehler
        # in Folge" waere dann vom Zufall abhaengig. Der Pool arbeitet trotzdem
        # parallel weiter, nur die Buchhaltung ist geordnet.
        for future in tqdm(futures, total=len(futures), desc=desc):
            recorded.add(future)
            consecutive = consecutive + 1 if record(future, futures[future]) else 0
            if abort_after and consecutive >= abort_after:
                pending = [f for f in futures if f not in recorded and f.cancel()]
                top_kind = max(batch.errors.items(), key=lambda kv: kv[1])[0]
                batch.aborted = (
                    f"{consecutive} Fehler in Folge ({top_kind}) - "
                    f"{len(pending):,} Tiles nicht mehr versucht"
                )
                emit(f"   🛑 {desc}: {batch.aborted}")
                for f in pending:
                    recorded.add(f)
                    batch.failed.append((futures[f], TileError("nicht versucht", batch.aborted)))
                break

    # Beim Abbruch liefen bis zu max_workers Tiles noch - die sind jetzt fertig
    # und gehoeren mit verbucht, sonst gehen die Zahlen nicht auf.
    for future, tile in futures.items():
        if future not in recorded:
            record(future, tile)

    return batch


def reconnect_vpn(emit=print, timeout=180) -> bool:
    """Tunnel ueber die gluetun-Steuer-API neu verbinden.

    Nur aktiv, wenn GLUETUN_CONTROL_URL und GLUETUN_API_KEY gesetzt sind (siehe
    docker-compose.vpn.yml, Key in docker/.env). Ohne beides ein No-op.
    Rueckgabe: True, wenn danach eine andere Exit-IP gemeldet wird.
    """
    url = os.environ.get("GLUETUN_CONTROL_URL")
    key = os.environ.get("GLUETUN_API_KEY")
    if not url or not key:
        return False
    headers = {"X-API-Key": key}

    def public_ip():
        try:
            return requests.get(f"{url}/v1/publicip/ip", headers=headers, timeout=10).json().get("public_ip")
        except Exception:
            return None

    before = public_ip()
    try:
        requests.put(f"{url}/v1/vpn/status", json={"status": "stopped"}, headers=headers, timeout=10)
        time.sleep(3)
        requests.put(f"{url}/v1/vpn/status", json={"status": "running"}, headers=headers, timeout=10)
    except requests.RequestException as exc:
        emit(f"   ⚠️ VPN-Neustart fehlgeschlagen: {type(exc).__name__}: {str(exc)[:120]}")
        return False

    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(5)
        ip = public_ip()
        if ip and ip != before:
            emit(f"   🔌 VPN neu verbunden: Exit {before or '?'} -> {ip}")
            return True
    emit(f"   ⚠️ VPN nach Neustart nicht innerhalb von {timeout}s mit anderem Exit verbunden")
    return False


def fetch_tiles_with_retry(
    tiles,
    token,
    coverage,
    layer,
    max_workers=3,
    desc="",
    retry_rounds=1,
    retry_pause=300,
    emit=print,
) -> TileBatch:
    """Wie fetch_tiles, holt endgueltig gescheiterte Tiles aber nach einer Pause erneut.

    load_tile wiederholt im Sekundenabstand - das faengt Einzelaussetzer.
    Rate-Limits und VPN-Haenger dauern eher Minuten. Ohne diese Runde wuerde
    ein Bundesland mit 3 % offenen Tiles komplett verworfen (Reissleine) und
    eine Woche spaeter von vorn geholt, obwohl 97 % laengst da waren.
    """
    batch = fetch_tiles(tiles, token, coverage, layer, max_workers, desc, emit=emit)

    for round_no in range(1, retry_rounds + 1):
        retry_tiles = [tile for tile, _ in batch.failed if tile is not None]
        if not retry_tiles:
            break
        emit(
            f"   🔁 {len(retry_tiles):,} Tiles offen - Nachlauf {round_no}/{retry_rounds} "
            f"in {retry_pause // 60} min"
        )
        # Wurde wegen ungueltiger Antworten abgebrochen, liegt es am aktuellen
        # Exit, nicht an den Tiles - vor dem Nachlauf neu verbinden.
        if batch.aborted and "kein MVT" in batch.aborted:
            reconnect_vpn(emit)
        time.sleep(retry_pause)

        again = fetch_tiles(
            retry_tiles, token, coverage, layer, max_workers, f"{desc} retry-{round_no}", emit=emit
        )
        batch.gdfs.extend(again.gdfs)
        batch.empty += again.empty
        batch.recovered += len(retry_tiles) - len(again.failed)
        # Fehler ohne Tile-Referenz (unerwartete Exceptions) sind nicht
        # wiederholbar und bleiben stehen.
        batch.failed = again.failed + [f for f in batch.failed if f[0] is None]
        batch.rounds = round_no + 1
        if again.aborted:
            batch.aborted = f"auch im Nachlauf {round_no}: {again.aborted}"
            break

    return batch
