#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

SERVICE="${1:-}"
if [[ -z "$SERVICE" ]]; then
  echo "❌ Missing service name"
  exit 2
fi

DC="docker-compose -f docker/docker-compose.yml -f docker/docker-compose.vpn.yml"

$DC down --remove-orphans

echo "Starting gluetun..."
$DC up -d gluetun

echo "Waiting for VPN readiness..."
timeout 300 bash -c '
  until docker logs gluetun 2>&1 | grep -q "Initialization Sequence Completed"; do sleep 2; done
  until docker logs gluetun 2>&1 | grep -qi "dns.*ready"; do sleep 2; done
'

echo "VPN ready → starting $SERVICE"
$DC up --build "$SERVICE"
