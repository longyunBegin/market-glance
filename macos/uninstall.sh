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

WIDGET_APP="$HOME/Applications/Market Glance.app"
if [[ -d "$WIDGET_APP" ]]; then
  rm -rf "$WIDGET_APP"
fi

echo "Market Glance 自动启动项已移除。"
echo "原生行情小组件应用已从 ~/Applications 移除（如已固定到桌面，请从桌面移除残留小组件）。"
echo "本地配置、行情缓存和日志仍保留在：$HOME/Library/Application Support/Market Glance"
