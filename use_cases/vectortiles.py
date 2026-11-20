"""Vector tiles for radinfra.de: a gzipped GeoJSON in, a PMTiles archive out.

Both radinfra_2_pmtiles notebooks (traffic signs and markings) call
geojson_gz_to_pmtiles. Until November 2026 each carried its own copy of this
function, and every fix had to go into both (docs/todo.md #8).

tippecanoe is compiled into the worker image (docker/Dockerfile.worker). The tests
replace it; scripts/smoke_test_worker_image.sh runs the real one in the image.
"""

from __future__ import annotations

import gzip
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

# Based on the configuration of tordans. The inputs are points, and none of them is
# ever dropped: every detection shows on every zoom level.
TIPPECANOE_OPTIONS = (
    "--layer=default",
    # 6 would be all of Germany on a laptop screen, 8 a little less than a state.
    "--minimum-zoom=7",
    # Precise enough for points; maps overzoom beyond it. tippecanoe's own guess
    # (--smallest-maximum-zoom-guess) was not precise enough.
    "--maximum-zoom=12",
    # These three only change lines and polygons.
    "--simplify-only-low-zooms",
    "--no-tiny-polygon-reduction-at-maximum-zoom",
    "--no-simplification-of-shared-nodes",
    # No dropping, not even of the densest features (-rg, --drop-densest-as-needed).
    "--drop-rate=0",
    # No 500 KB cap per tile. With --drop-rate=0 tippecanoe has no other way out
    # when a tile gets too dense: it stops with exit 110 ("could not make tile small
    # enough"), as in the ts run of 16.06.2026. Lossless; a dense tile gets bigger.
    "--no-tile-size-limit",
    "--read-parallel",
)


def geojson_gz_to_pmtiles(geojson_gz, output_pmtiles, *, tippecanoe="tippecanoe", options=TIPPECANOE_OPTIONS):
    """Tile the FeatureCollection in `geojson_gz` into `output_pmtiles`.

    tippecanoe reads no .gz, so the input is unpacked into a temporary .geojson
    first. The archive goes to `<stem>.tmp.pmtiles` and replaces `output_pmtiles`
    only after tippecanoe succeeded: a failed run leaves a file under the name it
    wrote to - tippecanoe a partial archive (tried 20.11.2026) - and the last good
    archive has to survive an abort, out of memory for instance. The temporary name
    must end in .pmtiles: tippecanoe picks the format by the extension and would
    write MBTiles (SQLite) without a word.
    """
    geojson_gz = Path(geojson_gz)
    output_pmtiles = Path(output_pmtiles)
    output_pmtiles.parent.mkdir(parents=True, exist_ok=True)
    if not geojson_gz.exists():
        raise FileNotFoundError(f"Input file not found: {geojson_gz}")

    tmp_out = output_pmtiles.with_name(output_pmtiles.stem + ".tmp.pmtiles")
    tmp_in = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", suffix=".geojson", delete=False) as tmp:
            tmp_in = Path(tmp.name)
            with gzip.open(geojson_gz, mode="rb") as src:
                shutil.copyfileobj(src, tmp)

        subprocess.run([tippecanoe, "-o", str(tmp_out), "--force", *options, str(tmp_in)], check=True)
        os.replace(tmp_out, output_pmtiles)
    finally:
        if tmp_in is not None:
            tmp_in.unlink(missing_ok=True)
        # What an aborted run leaves: the temporary archive and the journal next to
        # it (<target>-journal). The last three names are from earlier versions of
        # this function, which wrote to <name>.tmp.
        for leftover_name in (
            output_pmtiles.stem + ".tmp.pmtiles",
            output_pmtiles.stem + ".tmp.pmtiles-journal",
            output_pmtiles.name + ".tmp",
            output_pmtiles.name + ".tmp-journal",
            output_pmtiles.name + "-journal",
        ):
            (output_pmtiles.parent / leftover_name).unlink(missing_ok=True)

    print(f"✅ PMTiles created: {output_pmtiles}")
