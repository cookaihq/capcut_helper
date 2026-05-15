#!/usr/bin/env bash
# 构建 capcut_helper macOS arm64 .app bundle 并打可分发 dmg。
# 用法（从任意位置）: bash capcut_helper/scripts/build_mac.sh
set -euo pipefail

# 切到 capcut_helper/（项目根）
cd "$(cd "$(dirname "$0")" && pwd)/.."

# 读取版本号（来源唯一：backend/app/__init__.py::__version__）
VERSION=$(grep -oE '"[0-9]+\.[0-9]+\.[0-9]+"' backend/app/__init__.py | head -1 | tr -d '"')
if [ -z "$VERSION" ]; then
  echo "✗ 无法从 backend/app/__init__.py 解析 __version__"
  exit 1
fi
DMG_NAME="capcut_helper-arm64-v${VERSION}.dmg"

echo "→ 1/3 安装/构建前端"
( cd frontend && npm install && npm run build )

echo "→ 2/3 PyInstaller 打包 .app"
( cd backend && uv run pyinstaller --clean --noconfirm \
    --distpath=../dist --workpath=../build \
    capcut_helper.spec )

echo "→ 3/3 hdiutil 打可分发 dmg"
( cd dist && \
  rm -rf dmg-staging && \
  mkdir -p dmg-staging && \
  cp -R capcut_helper.app dmg-staging/ && \
  ln -sf /Applications dmg-staging/Applications && \
  hdiutil create -volname "capcut_helper" \
                 -srcfolder dmg-staging \
                 -ov -format UDZO \
                 "$DMG_NAME" && \
  rm -rf dmg-staging )

echo ""
echo "构建完成："
echo "  .app: $(pwd)/dist/capcut_helper.app"
echo "  dmg:  $(pwd)/dist/${DMG_NAME}"
