#!/usr/bin/env bash
# Smoke test for the worker image: does everything a weekly run calls start?
# Fetches nothing and needs no credentials. Runs inside the image with the repo
# bind-mounted at /app, as on the server (docker/docker-compose.yml).
#
# CI runs it after building the image (.github/workflows/tests.yml). By hand:
#
#   docker build -f docker/Dockerfile.worker -t mapillary-worker .
#   docker run --rm -v "$PWD:/app" -w /app mapillary-worker bash scripts/smoke_test_worker_image.sh
set -euo pipefail
cd /app

echo "▶️  tippecanoe"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
cat >"$tmp/in.geojson" <<'EOF'
{"type": "FeatureCollection", "features": [
  {"type": "Feature", "properties": {"id": "1234"}, "geometry": {"type": "Point", "coordinates": [13.4, 52.5]}}
]}
EOF
# Same output format as radinfra_2_pmtiles: tippecanoe picks it by the extension.
tippecanoe -o "$tmp/out.pmtiles" --force --quiet --layer=default -Z7 -z12 "$tmp/in.geojson"
test -s "$tmp/out.pmtiles"
tippecanoe --version 2>&1 | head -1

echo "▶️  mapillary_pipeline"
python3 -m mapillary_pipeline --help >/dev/null

echo "▶️  nbconvert"
jupyter nbconvert --version

echo "▶️  imports of the campaign modules and the radinfra notebooks"
python3 - <<'EOF'
import ast
import importlib
import json
import sys
from pathlib import Path

# The notebooks find the modules through sys.path.insert(0, ".."), run from their
# own directory - that is use_cases/.
sys.path.insert(0, "use_cases")

modules = {p.stem for p in Path("use_cases").glob("*campaign.py") if not p.name.startswith("test_")}

# Every import of the notebooks the runner executes, including those inside
# functions (radinfra_2_pmtiles imports gzip, subprocess ... there).
for notebook in sorted(Path("use_cases").glob("*/radinfra_*.ipynb")):
    for cell in json.loads(notebook.read_text())["cells"]:
        if cell["cell_type"] != "code":
            continue
        # IPython magics and shell lines are no Python.
        source = "\n".join(l for l in "".join(cell["source"]).splitlines() if not l.lstrip().startswith(("%", "!")))
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Import):
                modules.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                modules.add(node.module)

for name in sorted(modules):
    importlib.import_module(name)
print(f"{len(modules)} modules import: {', '.join(sorted(modules))}")
EOF

echo "✅ worker image ok"
