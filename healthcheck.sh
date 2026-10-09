#!/bin/bash
# Restart the web service if its configured local port stops responding.
set -u
APP_DIR="$(cd "$(dirname "$0")" && pwd -P)"
PORT="$(python3 - "$APP_DIR/config.json" <<'PY'
import json
import sys
try:
    with open(sys.argv[1], encoding="utf-8") as stream:
        print(json.load(stream).get("www_port", 8090))
except Exception:
    print(8090)
PY
)"
if ! curl -fsS -m 10 -o /dev/null "http://127.0.0.1:${PORT}/"; then
  echo "$(date '+%F %T') 页面 :${PORT} 无响应，重启 market-glance-www.service"
  systemctl restart market-glance-www.service || true
fi
exit 0
