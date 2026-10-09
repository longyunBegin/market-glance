#!/bin/bash
# Build and install the native WidgetKit host app for the current macOS user.
set -euo pipefail

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "ERROR: WidgetKit 小组件只能在 macOS 上构建和安装。" >&2
  exit 1
fi

if ! command -v xcodebuild >/dev/null 2>&1; then
  echo "ERROR: 未找到 xcodebuild；请安装并打开 Xcode 后重试。" >&2
  exit 1
fi

PORT="${1:-8090}"
if [[ ! "$PORT" =~ ^[0-9]+$ ]] || (( PORT < 1024 || PORT > 65535 )); then
  echo "ERROR: 行情服务端口必须是 1024 到 65535 之间的整数。" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd -P)"
PROJECT_DIR="$SCRIPT_DIR/widget"
SUPPORT_DIR="$HOME/Library/Application Support/Market Glance"
DERIVED_DATA="$SUPPORT_DIR/widget-build"
DEST="$HOME/Applications/Market Glance.app"
BUILT_APP="$DERIVED_DATA/Build/Products/Release/MarketGlance.app"

if [[ ! -d "$PROJECT_DIR/MarketGlance.xcodeproj" ]]; then
  echo "ERROR: 未找到 WidgetKit Xcode 工程：$PROJECT_DIR/MarketGlance.xcodeproj" >&2
  exit 1
fi

mkdir -p "$HOME/Applications" "$SUPPORT_DIR"
xcodebuild \
  -project "$PROJECT_DIR/MarketGlance.xcodeproj" \
  -scheme MarketGlance \
  -configuration Release \
  -derivedDataPath "$DERIVED_DATA" \
  MARKET_GLANCE_API_PORT="$PORT" \
  CODE_SIGN_STYLE=Manual \
  CODE_SIGN_IDENTITY=- \
  build

if [[ ! -d "$BUILT_APP" ]]; then
  echo "ERROR: Xcode 构建完成，但没有生成预期的 MarketGlance.app。" >&2
  exit 1
fi

rm -rf "$DEST"
/usr/bin/ditto "$BUILT_APP" "$DEST"
/usr/bin/open -a "$DEST"
echo "Market Glance 原生小组件已安装：$DEST"
echo "请在 macOS 小组件图库中添加“Market Glance 行情”（macOS 14 或更新版本）。"
