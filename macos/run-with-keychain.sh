#!/bin/bash
# Load optional Alpaca credentials from the current user's login keychain, then run the app task.
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")" && pwd -P)"
PYTHON_BIN="${MARKET_GLANCE_PYTHON:-$(command -v python3)}"

if [[ -x /usr/bin/security ]]; then
  account="$(id -un)"
  key_id="$(/usr/bin/security find-generic-password -a "$account" -s "Market Glance Alpaca Key ID" -w 2>/dev/null || true)"
  secret_key="$(/usr/bin/security find-generic-password -a "$account" -s "Market Glance Alpaca Secret Key" -w 2>/dev/null || true)"
  if [[ -n "$key_id" && -n "$secret_key" ]]; then
    export APCA_API_KEY_ID="$key_id"
    export APCA_API_SECRET_KEY="$secret_key"
  fi
  unset key_id secret_key
fi

cd "$APP_DIR"
if [[ "${1##*/}" == "fetch.py" ]]; then
  log_file="$APP_DIR/../logs/fetch.log"
  if [[ -f "$log_file" ]] && [[ "$(/usr/bin/stat -f %z "$log_file" 2>/dev/null || echo 0)" -ge 1048576 ]]; then
    mv -f "$log_file" "$log_file.1"
  fi
  exec "$PYTHON_BIN" "$@" >>"$log_file" 2>&1
fi
exec "$PYTHON_BIN" "$@"
