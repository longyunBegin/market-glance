#!/bin/bash
# Optional reverse SSH tunnel. Configure TUNNEL_CMD in /etc/default/market-glance-tunnel.
set -u

if [[ -z "${TUNNEL_CMD:-}" ]]; then
  echo "TUNNEL_CMD is not configured; set it before enabling market-glance-tunnel.service." >&2
  exit 2
fi

while true; do
  echo "$(date '+%H:%M:%S') tunnel connecting..."
  eval "$TUNNEL_CMD"
  status=$?
  echo "$(date '+%H:%M:%S') tunnel exited ($status), retry in 10s"
  sleep 10
done
