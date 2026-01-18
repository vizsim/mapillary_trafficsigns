#!/usr/bin/env bash
set -euo pipefail
exec "$(dirname "$0")/run_worker_with_vpn.sh" mapillary-ts_worker
