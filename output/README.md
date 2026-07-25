# Output data has moved

The processed Parquet datasets are **no longer stored in this repository** (each run
is ~150 MB and would bloat git history). They are published as downloadable files
instead:

| Dataset | Download |
| --- | --- |
| 🚦 Traffic sign detections | <https://data.vizsim.de/mapillary_trafficsigns/> |
| 🖌️ Map feature points (road markings) | <https://data.vizsim.de/mapillary_map-feature-points/> |

Files are named `mapillary_<dataset>_DE-<STATE>_latest.parquet` (one per German
federal state) and are refreshed automatically on a regular basis.

Data © Mapillary, redistributed under [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/).
