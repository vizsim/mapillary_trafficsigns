#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

DC="docker-compose -f docker/docker-compose.yml -f docker/docker-compose.vpn.yml"

$DC down --remove-orphans

echo "Starting gluetun..."
$DC up -d gluetun

echo "Waiting for gluetun to be ready (VPN + DNS)..."

# Warte bis beide Strings irgendwann im Log auftauchen
timeout 300 bash -c '
  until docker logs gluetun 2>&1 | grep -q "Initialization Sequence Completed"; do
    sleep 2
  done
  until docker logs gluetun 2>&1 | grep -qi "dns.*ready"; do
    sleep 2
  done
'

echo "Gluetun is ready. Starting worker..."
$DC up --build mapillary-ts_worker
