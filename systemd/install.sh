#!/bin/bash
# Install Market Glance systemd units for this checkout.
set -euo pipefail

SRC="$(cd "$(dirname "$0")" && pwd -P)"
APP_DIR="$(cd "$SRC/.." && pwd -P)"
SYSTEMD_DIR="${SYSTEMD_DIR:-/etc/systemd/system}"
SYSTEMCTL_BIN="${SYSTEMCTL:-systemctl}"
ENABLE_TUNNEL="${ENABLE_TUNNEL:-0}"
START_FETCH="${START_FETCH:-1}"

if [[ "$APP_DIR" =~ [[:space:]] ]]; then
  echo "ERROR: 安装目录不能包含空白字符：$APP_DIR" >&2
  exit 1
fi
if [[ ! -f "$APP_DIR/config.json" ]]; then
  echo "ERROR: 缺少 config.json；请先从 config.example.json 复制并编辑。" >&2
  exit 1
fi

mkdir -p "$SYSTEMD_DIR"
APP_DIR_SED="$(printf '%s' "$APP_DIR" | sed 's/[&|]/\\&/g')"
tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT

for unit in market-glance-fetch.service market-glance-fetch.timer market-glance-www.service market-glance-tunnel.service market-glance-healthcheck.service market-glance-healthcheck.timer; do
  sed "s|@APP_DIR@|$APP_DIR_SED|g" "$SRC/$unit" > "$tmp_dir/$unit"
  install -m 0644 "$tmp_dir/$unit" "$SYSTEMD_DIR/$unit"
done
chmod 755 "$APP_DIR/healthcheck.sh" "$APP_DIR/tunnel.sh"
"$SYSTEMCTL_BIN" daemon-reload

# Proxy credentials are injected into the systemd manager environment only.
if [[ -n "${HTTPS_PROXY:-}" ]]; then
  "$SYSTEMCTL_BIN" set-environment \
    "https_proxy=${https_proxy:-}" "HTTPS_PROXY=${HTTPS_PROXY:-}" \
    "http_proxy=${http_proxy:-}" "HTTP_PROXY=${HTTP_PROXY:-}" \
    "all_proxy=${all_proxy:-}" "ALL_PROXY=${ALL_PROXY:-}"
  echo "proxy injected into systemd manager environment (memory only)"
else
  echo "WARN: 当前 shell 没有 HTTPS_PROXY，服务将无代理直连。"
fi

"$SYSTEMCTL_BIN" enable --now market-glance-fetch.timer market-glance-www.service market-glance-healthcheck.timer
"$SYSTEMCTL_BIN" restart market-glance-www.service

if [[ "$ENABLE_TUNNEL" == "1" ]]; then
  tunnel_env="/etc/default/market-glance-tunnel"
  if [[ ! -r "$tunnel_env" ]] || ! grep -Eq '^[[:space:]]*TUNNEL_CMD=.+$' "$tunnel_env"; then
    echo "ERROR: 启用隧道前，请在 $tunnel_env 配置 TUNNEL_CMD。" >&2
    exit 1
  fi
  "$SYSTEMCTL_BIN" enable --now market-glance-tunnel.service
else
  echo "可选隧道未启用（需要时以 ENABLE_TUNNEL=1 重跑安装）。"
fi

if [[ "$START_FETCH" == "1" ]]; then
  "$SYSTEMCTL_BIN" start market-glance-fetch.service || true
fi

echo "installed + enabled + started"
"$SYSTEMCTL_BIN" is-enabled market-glance-fetch.timer market-glance-www.service market-glance-healthcheck.timer
if [[ "$ENABLE_TUNNEL" == "1" ]]; then
  "$SYSTEMCTL_BIN" is-enabled market-glance-tunnel.service
fi
