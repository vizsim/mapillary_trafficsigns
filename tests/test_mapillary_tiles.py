"""Tests fuer mapillary_tiles - ohne Netz, ohne echten Parser.

Jeder Test hier beschreibt einen Fall, der real vorgekommen ist oder direkt
aus dem Vorfall vom 26.08.2026 folgt (Antworten ohne MVT-Inhalt wurden still
verworfen, der Export lief trotzdem).
"""

import time

import mercantile
import pytest

import mapillary_tiles as mt

TILE = mercantile.Tile(x=8472, y=5422, z=14)
COVERAGE, LAYER = mt.COVERAGE_TRAFFIC_SIGNS
MVT_HEADERS = {"Content-Type": "application/x-protobuf", "Content-Encoding": "gzip"}
GARBAGE = b"\x1a\xff\xff\xff\xff"  # beginnt wie ein MVT, ist aber keins
GOOD = b"\x1a\x00"


class FakeResponse:
    def __init__(self, status=200, content=b"", headers=None):
        self.status_code = status
        self.content = content
        self.headers = headers or {}


class FakeSession:
    """Liefert die Antworten der Reihe nach; die letzte wiederholt sich."""

    def __init__(self, *responses):
        self._responses = list(responses)
        self.calls = 0

    def get(self, url, timeout=None):
        self.calls += 1
        response = self._responses.pop(0) if len(self._responses) > 1 else self._responses[0]
        if isinstance(response, Exception):
            raise response
        return response


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(mt.time, "sleep", lambda seconds: None)


@pytest.fixture
def session(monkeypatch):
    def install(*responses):
        fake = FakeSession(*responses)
        monkeypatch.setattr(mt, "get_session", lambda: fake)
        return fake

    return install


@pytest.fixture
def parser(monkeypatch):
    """Ersetzt vt_bytes_to_geojson: GARBAGE wirft, alles andere liefert Features."""

    def install(features):
        def parse(raw, x, y, z, layer=None):
            if raw == GARBAGE:
                raise ValueError("Error parsing message with type 'vector_tile.tile'")
            return {"features": features}

        monkeypatch.setattr(mt, "vt_bytes_to_geojson", parse)

    return install


# --- Body-Validierung vor dem Parser ---------------------------------------


def test_leerer_body_ist_leeres_tile_kein_fehler(session):
    session(FakeResponse(200, b"", MVT_HEADERS))
    features, error = mt.load_tile(TILE, "t", COVERAGE, LAYER)
    assert features == [] and error is None


def test_html_body_wird_erkannt_und_nie_geparst(session, monkeypatch):
    session(FakeResponse(200, b"<html><body>Access denied</body></html>", {"Content-Type": "text/html"}))
    monkeypatch.setattr(mt, "vt_bytes_to_geojson", lambda *a, **k: pytest.fail("Parser darf HTML nie sehen"))
    _, error = mt.load_tile(TILE, "t", COVERAGE, LAYER, attempts=1)
    assert error.kind == "kein MVT (Content-Type text/html)"
    assert "Access denied" in error.detail


def test_json_fehler_hinter_protobuf_header(session):
    # Header behauptet MVT, Body ist eine JSON-Fehlermeldung
    session(FakeResponse(200, b'{"message":"Application request limit reached"}', MVT_HEADERS))
    _, error = mt.load_tile(TILE, "t", COVERAGE, LAYER, attempts=1)
    assert error.kind == "kein MVT (JSON-Fehlerantwort)"
    assert "request limit" in error.detail


def test_http_fehler_traegt_status_im_kind(session):
    session(FakeResponse(429, b"", {"Content-Type": "text/plain"}))
    _, error = mt.load_tile(TILE, "t", COVERAGE, LAYER, attempts=1)
    assert error.kind == "HTTP 429"
    assert error.detail  # nie leer - das war der alte Zustand


def test_abgeschnittene_antwort(session):
    session(FakeResponse(200, b"\x1a" * 10, {"Content-Type": "application/x-protobuf", "Content-Length": "100"}))
    _, error = mt.load_tile(TILE, "t", COVERAGE, LAYER, attempts=1)
    assert error.kind == "abgeschnittene Antwort"
    assert "10 von 100" in error.detail


# --- Wiederholung -----------------------------------------------------------


def test_parsefehler_wird_wiederholt_dann_erfolg(session, parser):
    fake = session(FakeResponse(200, GARBAGE, MVT_HEADERS), FakeResponse(200, GOOD, MVT_HEADERS))
    parser([{"type": "Feature"}])
    features, error = mt.load_tile(TILE, "t", COVERAGE, LAYER)
    assert error is None and len(features) == 1
    assert fake.calls == 2


def test_nach_allen_versuchen_fehler_mit_diagnose(session, parser):
    fake = session(FakeResponse(200, GARBAGE, MVT_HEADERS))
    parser([])
    features, error = mt.load_tile(TILE, "t", COVERAGE, LAYER, attempts=4)
    assert features is None
    assert error.kind == "MVT-Parsefehler"
    assert "vector_tile.tile" in error.detail and "erste Bytes" in error.detail
    assert fake.calls == 4


def test_netzwerkfehler_wird_klassifiziert(session):
    session(mt.requests.ConnectionError("Connection reset by peer"))
    _, error = mt.load_tile(TILE, "t", COVERAGE, LAYER, attempts=2)
    assert error.kind == "ConnectionError"


# --- Features -> GeoDataFrame ----------------------------------------------


def test_ids_bleiben_ueber_2_hoch_53_exakt_und_datum_wird_string():
    big = 2**53 + 1  # rundet als float64 auf 2**53
    features = [
        {"type": "Feature", "geometry": {"type": "Point", "coordinates": [9.0, 48.0]},
         "properties": {"id": big, "first_seen_at": 1_700_000_000_000, "last_seen_at": 1_700_086_400_000}},
        {"type": "Feature", "geometry": {"type": "Point", "coordinates": [9.1, 48.1]},
         "properties": {"id": 7, "first_seen_at": None, "last_seen_at": 1_700_000_000_000}},
    ]
    gdf = mt.tile_features_to_gdf(features, TILE)
    assert str(gdf["id"].dtype) == "Int64"
    assert int(gdf["id"].iloc[0]) == big
    assert gdf["first_seen_at"].iloc[0] == "2023-11-14"
    assert gdf["last_seen_at"].iloc[0] == "2023-11-15"
    assert gdf["first_seen_at"].isna().iloc[1]  # None darf den Batch nicht abbrechen
    assert (gdf["tile_x"] == TILE.x).all() and (gdf["tile_y"] == TILE.y).all()


# --- Batch ------------------------------------------------------------------


def _tiles(n):
    return [mercantile.Tile(x=8000 + i, y=5000, z=14) for i in range(n)]


def test_fetch_tiles_klassifiziert_daten_leer_fehler(monkeypatch):
    tiles = _tiles(3)
    outcomes = {
        tiles[0]: ([{"type": "Feature", "geometry": {"type": "Point", "coordinates": [1, 2]}, "properties": {"id": 1}}], None),
        tiles[1]: ([], None),
        tiles[2]: (None, mt.TileError("MVT-Parsefehler", "Muell")),
    }
    monkeypatch.setattr(mt, "load_tile", lambda tile, *a, **k: outcomes[tile])

    batch = mt.fetch_tiles(tiles, "t", COVERAGE, LAYER, max_workers=2)

    assert batch.total == 3 and len(batch.gdfs) == 1 and batch.empty == 1
    assert [t for t, _ in batch.failed] == [tiles[2]]
    assert batch.errors == {"MVT-Parsefehler": 1}
    assert batch.samples["MVT-Parsefehler"] == "Muell"
    assert batch.fail_ratio == pytest.approx(1 / 3)


def test_nachlauf_holt_gescheiterte_tiles_nach(monkeypatch):
    tiles = _tiles(4)
    rounds = []

    def fake_fetch(subset, token, coverage, layer, max_workers=3, desc="", **kwargs):
        rounds.append(list(subset))
        batch = mt.TileBatch(total=len(subset))
        if len(rounds) == 1:
            batch.gdfs.append("gdf-a")
            batch.empty = 1
            batch.failed = [(subset[2], mt.TileError("HTTP 503", "")), (subset[3], mt.TileError("HTTP 503", ""))]
            batch.errors = {"HTTP 503": 2}
        else:
            batch.gdfs.extend(["gdf-c", "gdf-d"])
        return batch

    monkeypatch.setattr(mt, "fetch_tiles", fake_fetch)
    log = []

    batch = mt.fetch_tiles_with_retry(tiles, "t", COVERAGE, LAYER, retry_rounds=1, retry_pause=0, emit=log.append)

    assert rounds[1] == tiles[2:]  # nur die gescheiterten werden erneut geholt
    assert batch.failed == [] and batch.recovered == 2 and batch.rounds == 2
    assert sorted(batch.gdfs) == ["gdf-a", "gdf-c", "gdf-d"]
    assert batch.errors == {"HTTP 503": 2}  # Diagnose des ersten Durchlaufs bleibt
    assert any("Nachlauf 1/1" in line for line in log)


def test_nachlauf_ueberspringt_wenn_nichts_offen(monkeypatch):
    calls = []
    monkeypatch.setattr(mt, "fetch_tiles", lambda *a, **k: calls.append(1) or mt.TileBatch(total=1))
    mt.fetch_tiles_with_retry(_tiles(1), "t", COVERAGE, LAYER, retry_rounds=2, retry_pause=0)
    assert len(calls) == 1


def test_report_ist_ein_bericht_kein_zeilenstrom():
    batch = mt.TileBatch(total=100, gdfs=["x"] * 90, empty=5, recovered=3)
    batch.failed = [(TILE, mt.TileError("HTTP 500", ""))] * 5
    batch.errors = {"HTTP 500": 8}
    batch.samples = {"HTTP 500": "<html>Bad Gateway"}
    lines = []
    batch.report(lines.append)
    assert lines[0] == "   100 Tiles | 90 mit Daten | 5 leer | 5 fehlgeschlagen (5.0%) | 3 im Nachlauf erholt"
    assert len(lines) == 3 and "Bad Gateway" in lines[2]


# --- Abbruch bei Fehlerserie ------------------------------------------------


def _slow_block(tile, *a, **k):
    # kurze echte Wartezeit, damit der Hauptthread die Fehlerserie sieht, bevor
    # der Pool alle Tiles durch hat (time.sleep ist in den Tests abgeschaltet)
    t = time.perf_counter()
    while time.perf_counter() - t < 0.003:
        pass
    return None, mt.TileError("kein MVT (Content-Type text/html)", "<!DOCTYPE html> ...")


def test_abbruch_nach_fehlern_in_folge_statt_stundenlangem_kriechen(monkeypatch):
    # 02.09.2026: HTML-Fehlerseite fuer jede Tile, 4 Versuche mit Backoff pro Tile
    # -> DE-BY haette ~100 h gebraucht. Jetzt: nach 10 Fehlern in Folge Schluss.
    tiles = _tiles(200)
    attempted = []
    monkeypatch.setattr(mt, "load_tile", lambda tile, *a, **k: attempted.append(tile) or _slow_block(tile))
    log = []

    batch = mt.fetch_tiles(tiles, "t", COVERAGE, LAYER, max_workers=2, emit=log.append, abort_after=10)

    assert "10 Fehler in Folge (kein MVT (Content-Type text/html))" in batch.aborted
    assert len(attempted) < 200  # der Rest wurde gar nicht erst angefragt
    assert len(batch.failed) == 200 and batch.fail_ratio == 1.0  # aber alles als fehlend verbucht
    assert len(batch.gdfs) + batch.empty + len(batch.failed) == batch.total
    assert any("🛑" in line and "nicht mehr versucht" in line for line in log)
    assert batch.samples["kein MVT (Content-Type text/html)"].startswith("<!DOCTYPE html>")


def test_erfolg_setzt_die_fehlerserie_zurueck(monkeypatch):
    tiles = _tiles(40)
    ok = ([{"type": "Feature", "geometry": {"type": "Point", "coordinates": [1, 2]}, "properties": {"id": 1}}], None)
    bad = (None, mt.TileError("HTTP 503", ""))
    monkeypatch.setattr(mt, "load_tile", lambda tile, *a, **k: bad if tile.x % 2 else ok)

    batch = mt.fetch_tiles(tiles, "t", COVERAGE, LAYER, max_workers=1, abort_after=3)

    assert batch.aborted == ""
    assert len(batch.gdfs) == 20 and len(batch.failed) == 20


def test_nachlauf_bricht_ab_wenn_fehlerserie_bleibt(monkeypatch):
    tiles = _tiles(50)
    monkeypatch.setattr(mt, "load_tile", _slow_block)
    log = []

    batch = mt.fetch_tiles_with_retry(
        tiles, "t", COVERAGE, LAYER, max_workers=2, retry_rounds=3, retry_pause=0, emit=log.append
    )

    assert batch.aborted.startswith("auch im Nachlauf 1:")
    assert batch.rounds == 2  # nach dem ersten erfolglosen Nachlauf ist Schluss, nicht erst nach drei
    assert batch.recovered == 0 and len(batch.failed) == 50
