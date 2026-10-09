#!/bin/bash
# Stop and remove the current user's Market Glance launch agents; keep local data intact.
set -euo pipefail

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "ERROR: 此卸载脚本仅适用于 macOS。" >&2
  exit 1
fi

DOMAIN="gui/$(id -u)"
AGENTS_DIR="$HOME/Library/LaunchAgents"
for label in io.market-glance.web io.market-glance.fetch; do
  plist="$AGENTS_DIR/$label.plist"
  launchctl bootout "$DOMAIN" "$plist" 2>/dev/null || true
  rm -f "$plist"
done

echo "Market Glance 自动启动项已移除。"
echo "本地配置、行情缓存和日志仍保留在：$HOME/Library/Application Support/Market Glance"
