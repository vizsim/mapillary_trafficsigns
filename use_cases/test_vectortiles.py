"""Tests for vectortiles. tippecanoe is replaced here; the image smoke test runs the real one."""

import gzip
import json
import subprocess
from pathlib import Path

import pytest

import vectortiles

FEATURES = {
    "type": "FeatureCollection",
    "features": [
        {"type": "Feature", "properties": {"id": "1234"}, "geometry": {"type": "Point", "coordinates": [13.4, 52.5]}}
    ],
}


@pytest.fixture
def geojson_gz(tmp_path):
    path = tmp_path / "signs.geojson.gz"
    with gzip.open(path, "wt") as f:
        json.dump(FEATURES, f)
    return path


@pytest.fixture
def out_dir(tmp_path):
    path = tmp_path / "ts_output"
    path.mkdir()
    return path


def fake_tippecanoe(monkeypatch, exit_code=0):
    """Stands in for subprocess.run: records the call, writes the archive, can fail."""
    calls = []

    def run(cmd, check):
        target, source = Path(cmd[cmd.index("-o") + 1]), Path(cmd[-1])
        calls.append({"cmd": cmd, "target": target, "source": source, "content": source.read_text()})
        # tippecanoe leaves a file under the name it writes to, also when it fails.
        target.write_bytes(b"new archive" if exit_code == 0 else b"partial archive")
        if exit_code:
            raise subprocess.CalledProcessError(exit_code, cmd)
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(vectortiles.subprocess, "run", run)
    return calls


def test_tiles_the_unpacked_geojson_with_the_production_options(geojson_gz, out_dir, monkeypatch):
    calls = fake_tippecanoe(monkeypatch)
    output = out_dir / "signs_latest.pmtiles"

    vectortiles.geojson_gz_to_pmtiles(geojson_gz, output)

    (call,) = calls
    assert call["cmd"][0] == "tippecanoe"
    assert call["cmd"][call["cmd"].index("--force") + 1 : -1] == list(vectortiles.TIPPECANOE_OPTIONS)
    # Unpacked, because tippecanoe reads no .gz.
    assert call["source"].suffix == ".geojson" and json.loads(call["content"]) == FEATURES
    # Next to the target and ending in .pmtiles, or tippecanoe would write MBTiles.
    assert call["target"] == out_dir / "signs_latest.tmp.pmtiles"
    assert output.read_bytes() == b"new archive"
    assert sorted(p.name for p in out_dir.iterdir()) == ["signs_latest.pmtiles"]
    assert not call["source"].exists()


def test_a_failed_run_keeps_the_last_good_archive(geojson_gz, out_dir, monkeypatch):
    # Exit 110 is what tippecanoe returns for a tile it cannot make small enough.
    calls = fake_tippecanoe(monkeypatch, exit_code=110)
    output = out_dir / "signs_latest.pmtiles"
    output.write_bytes(b"last good archive")

    with pytest.raises(subprocess.CalledProcessError):
        vectortiles.geojson_gz_to_pmtiles(geojson_gz, output)

    assert output.read_bytes() == b"last good archive"
    assert sorted(p.name for p in out_dir.iterdir()) == ["signs_latest.pmtiles"]
    assert not calls[0]["source"].exists()


def test_a_missing_input_stops_before_tippecanoe(out_dir, monkeypatch):
    calls = fake_tippecanoe(monkeypatch)

    with pytest.raises(FileNotFoundError):
        vectortiles.geojson_gz_to_pmtiles(out_dir / "missing.geojson.gz", out_dir / "signs_latest.pmtiles")

    assert calls == []
    assert list(out_dir.iterdir()) == []


def test_no_limit_can_stop_a_dense_tile():
    # With --drop-rate=0, tippecanoe stops with exit 110 at a tile over 500 KB (ts
    # run of 16.06.2026) or over 200,000 features. The image smoke test tiles such a
    # tile with the real tippecanoe; this keeps the options from losing it.
    options = vectortiles.TIPPECANOE_OPTIONS
    assert "--drop-rate=0" in options
    assert "--no-tile-size-limit" in options and "--no-feature-limit" in options


@pytest.mark.parametrize("campaign", ["cycleway_complete_campaign", "cycleway_complete_marking_campaign"])
def test_the_radinfra_notebooks_tile_through_this_module(campaign):
    # Until November 2026 both notebooks carried a copy of the function, and fixes
    # had to go into each (todo #8). A copy coming back would call tippecanoe itself.
    notebook = json.loads((Path(__file__).parent / campaign / "radinfra_2_pmtiles.ipynb").read_text())
    code = "\n".join("".join(c["source"]) for c in notebook["cells"] if c["cell_type"] == "code")

    assert "vectortiles.geojson_gz_to_pmtiles(" in code
    assert "tippecanoe" not in code and "subprocess" not in code
