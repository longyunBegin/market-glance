#!/bin/bash
# Install Market Glance for the current macOS user (no admin privileges required).
set -euo pipefail

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "ERROR: 此安装脚本仅适用于 macOS。" >&2
  exit 1
fi

SRC="$(cd "$(dirname "$0")/.." && pwd -P)"
PYTHON_BIN="$(command -v python3 || true)"
if [[ -z "$PYTHON_BIN" ]]; then
  echo "ERROR: 未找到 python3；请先安装 Python 3.9 或更新版本。" >&2
  exit 1
fi
if ! "$PYTHON_BIN" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)'; then
  echo "ERROR: 需要 Python 3.9 或更新版本；当前版本为 $("$PYTHON_BIN" --version 2>&1)。" >&2
  exit 1
fi

SUPPORT_DIR="$HOME/Library/Application Support/Market Glance"
APP_DIR="$SUPPORT_DIR/app"
LOG_DIR="$SUPPORT_DIR/logs"
AGENTS_DIR="$HOME/Library/LaunchAgents"
DOMAIN="gui/$(id -u)"
WEB_PLIST="$AGENTS_DIR/io.market-glance.web.plist"
FETCH_PLIST="$AGENTS_DIR/io.market-glance.fetch.plist"

mkdir -p "$APP_DIR" "$LOG_DIR" "$AGENTS_DIR"
chmod 700 "$SUPPORT_DIR" "$LOG_DIR"

# Stop old agents before replacing their executable files.
launchctl bootout "$DOMAIN" "$WEB_PLIST" 2>/dev/null || true
launchctl bootout "$DOMAIN" "$FETCH_PLIST" 2>/dev/null || true

for file in server.py fetch.py alpaca_data.py config_model.py market_calendar.py config.example.json index.html; do
  cp -f "$SRC/$file" "$APP_DIR/$file"
done
rm -rf "$APP_DIR/assets"
cp -R "$SRC/assets" "$APP_DIR/assets"
rm -rf "$APP_DIR/chrome-extension"
cp -R "$SRC/chrome-extension" "$APP_DIR/chrome-extension"
cp -f "$SRC/macos/run-with-keychain.sh" "$APP_DIR/run-with-keychain.sh"
chmod 700 "$APP_DIR/run-with-keychain.sh"
rm -rf "$APP_DIR/macos"
mkdir -p "$APP_DIR/macos"
cp -R "$SRC/macos/widget" "$APP_DIR/macos/widget"
cp -f "$SRC/macos/install-widget.sh" "$APP_DIR/macos/install-widget.sh"
chmod 700 "$APP_DIR/macos/install-widget.sh"

# Keep existing app settings; on first install use the checkout's private config if present,
# otherwise start with the public example configuration.
if [[ ! -f "$APP_DIR/config.json" ]]; then
  if [[ -f "$SRC/config.json" ]]; then
    cp "$SRC/config.json" "$APP_DIR/config.json"
  else
    cp "$APP_DIR/config.example.json" "$APP_DIR/config.json"
  fi
fi
chmod 600 "$APP_DIR/config.json"

"$PYTHON_BIN" - "$APP_DIR" "$AGENTS_DIR" "$LOG_DIR" "$PYTHON_BIN" "$HOME" <<'PY'
import os
import plistlib
import sys
from pathlib import Path

app_dir, agents_dir, log_dir, python_bin, home = sys.argv[1:]
path = os.path.dirname(python_bin) + ":/usr/bin:/bin:/usr/sbin:/sbin"
environment = {
    "HOME": home,
    "MARKET_GLANCE_PYTHON": python_bin,
    "PATH": path,
    "PYTHONUNBUFFERED": "1",
}
wrapper = str(Path(app_dir) / "run-with-keychain.sh")
common = {
    "WorkingDirectory": app_dir,
    "EnvironmentVariables": environment,
    "ProcessType": "Background",
}
agents = [
    {
        "Label": "io.market-glance.web",
        "ProgramArguments": ["/bin/bash", wrapper, str(Path(app_dir) / "server.py")],
        "RunAtLoad": True,
        "KeepAlive": True,
        "StandardOutPath": str(Path(log_dir) / "web.log"),
        "StandardErrorPath": str(Path(log_dir) / "web-error.log"),
    },
    {
        "Label": "io.market-glance.fetch",
        "ProgramArguments": ["/bin/bash", wrapper, str(Path(app_dir) / "fetch.py")],
        "RunAtLoad": True,
        "StartInterval": 60,
        "StandardOutPath": "/dev/null",
        "StandardErrorPath": str(Path(log_dir) / "fetch-error.log"),
    },
]
for agent in agents:
    agent.update(common)
    destination = Path(agents_dir) / (agent["Label"] + ".plist")
    destination.write_bytes(plistlib.dumps(agent, fmt=plistlib.FMT_XML, sort_keys=True))
    destination.chmod(0o644)
PY

launchctl bootstrap "$DOMAIN" "$WEB_PLIST"
launchctl bootstrap "$DOMAIN" "$FETCH_PLIST"

PORT="$(PYTHONPATH="$APP_DIR" "$PYTHON_BIN" -c 'from config_model import load_config; import sys; print(load_config(sys.argv[1])["www_port"])' "$APP_DIR/config.json")"
"$PYTHON_BIN" - "$APP_DIR/chrome-extension/popup.js" "$PORT" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
source = "const API_PORT = 8090;"
script = path.read_text(encoding="utf-8")
if source not in script:
    raise SystemExit("ERROR: Chrome 扩展端口模板不存在。")
path.write_text(script.replace(source, f"const API_PORT = {int(sys.argv[2])};"), encoding="utf-8")
PY
if command -v xcodebuild >/dev/null 2>&1; then
  bash "$APP_DIR/macos/install-widget.sh" "$PORT"
else
  echo "未检测到 Xcode；看板和 Chrome 扩展已安装，小组件可稍后运行："
  echo "bash \"$APP_DIR/macos/install-widget.sh\" $PORT"
fi
URL="http://127.0.0.1:$PORT"
ready=0
for _ in $(seq 1 30); do
  if /usr/bin/curl --silent --fail "$URL/" >/dev/null; then
    ready=1
    break
  fi
  sleep 0.5
done
if [[ "$ready" != "1" ]]; then
  echo "ERROR: 看板服务未能启动；请查看 $LOG_DIR/web-error.log。" >&2
  exit 1
fi
/usr/bin/open "$URL"
echo "Market Glance 已安装并启动：$URL"
echo "登录后会自动启动；本地配置和缓存位于：$SUPPORT_DIR"
echo "Chrome 工具栏扩展位于：$APP_DIR/chrome-extension"
echo "首次使用：在 Chrome 打开 chrome://extensions，启用开发者模式并加载此文件夹。"
