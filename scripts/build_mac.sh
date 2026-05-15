#!/usr/bin/env bash
# 构建 capcut_helper macOS arm64 .app bundle 并打分发用 zip。
# 用法（从任意位置）: bash capcut_helper/scripts/build_mac.sh
set -euo pipefail

# 切到 capcut_helper/（项目根）
cd "$(cd "$(dirname "$0")" && pwd)/.."

echo "→ 1/3 安装/构建前端"
( cd frontend && npm install && npm run build )

echo "→ 2/3 PyInstaller 打包 .app"
( cd backend && uv run pyinstaller --clean --noconfirm \
    --distpath=../dist --workpath=../build \
    capcut_helper.spec )

echo "→ 3/3 ditto 打可分发 zip（保留 .app 内符号链接）"
( cd dist && ditto -c -k --sequesterRsrc --keepParent capcut_helper.app capcut_helper.zip )

echo ""
echo "构建完成："
echo "  .app: $(pwd)/dist/capcut_helper.app"
echo "  zip:  $(pwd)/dist/capcut_helper.zip"
