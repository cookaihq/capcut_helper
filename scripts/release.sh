#!/usr/bin/env bash
# capcut_helper 发版自动化脚本：bump 版本号后，一条命令完成 push → tag → 构建 → 发 GitHub release。
#
# 用法（从任意位置）：
#   bash capcut_helper/scripts/release.sh                 # 不带 release notes
#   bash capcut_helper/scripts/release.sh notes.md        # 用 notes.md 作 release body
#
# 前置条件：
#   1. `git remote get-url origin` 指向 GitHub 仓库（HTTPS 远端，无论凭据如何）
#   2. 项目根存在 `.github-token` 文件，内容是有 `contents:write` 权限的 PAT
#      （已 .gitignore；生成路径：GitHub Settings → Developer settings → Personal access tokens）
#   3. `backend/app/__init__.py::__version__` 已 bump 到本次要发的版本号
#   4. 工作树干净（无未提交/未暂存改动）
#
# 失败时不会留下半成品：tag 已推但 release 创建失败 → 删 tag 后重跑即可。

set -euo pipefail

# 切到项目根（脚本在 scripts/ 下）
cd "$(cd "$(dirname "$0")" && pwd)/.."

NOTES_FILE="${1:-}"

# ---------- 前置检查 ----------

if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "✗ 工作树有未提交改动，先 commit 或 stash 再发版"
  exit 1
fi

if [ ! -f .github-token ]; then
  cat <<'EOF'
✗ 缺 .github-token 文件（项目级，应已加入 .gitignore）

生成步骤：
  GitHub Settings → Developer settings → Personal access tokens → Fine-grained tokens
  Repository access: 只勾 cookaihq/capcut_helper
  Permissions → Repository → Contents: Read and write
  把生成的 token 字符串保存到项目根的 .github-token 文件里
EOF
  exit 1
fi
TOKEN=$(tr -d '[:space:]' < .github-token)
if [ -z "$TOKEN" ]; then
  echo "✗ .github-token 文件为空"
  exit 1
fi

VERSION=$(grep -oE '"[0-9]+\.[0-9]+\.[0-9]+"' backend/app/__init__.py | head -1 | tr -d '"')
if [ -z "$VERSION" ]; then
  echo "✗ 无法从 backend/app/__init__.py 解析 __version__"
  exit 1
fi
TAG="v$VERSION"
DMG_NAME="capcut_helper-arm64-v${VERSION}.dmg"
echo "→ 准备发 $TAG"

if git rev-parse "$TAG" >/dev/null 2>&1; then
  echo "✗ 本地已有 tag $TAG。删除后重跑：git tag -d $TAG"
  exit 1
fi
if git ls-remote --tags origin "refs/tags/$TAG" 2>/dev/null | grep -q "$TAG"; then
  echo "✗ origin 上已有 tag $TAG（这个版本号已发过）。bump __version__ 后再来"
  exit 1
fi

# 读 owner/repo（从 origin URL）
ORIGIN_URL=$(git remote get-url origin)
REPO_PATH=$(echo "$ORIGIN_URL" | sed -E 's#.*github\.com[:/]([^/]+/[^/.]+)(\.git)?$#\1#')
if [ -z "$REPO_PATH" ] || ! [[ "$REPO_PATH" =~ ^[^/]+/[^/]+$ ]]; then
  echo "✗ 无法从 origin URL 解析 owner/repo: $ORIGIN_URL"
  exit 1
fi
echo "→ 仓库 $REPO_PATH"

if [ -n "$NOTES_FILE" ] && [ ! -f "$NOTES_FILE" ]; then
  echo "✗ release notes 文件不存在: $NOTES_FILE"
  exit 1
fi

# ---------- 跑测试 ----------

echo "→ 跑后端测试"
( cd backend && uv run pytest -q )
echo "→ 跑前端测试"
( cd frontend && npm run test --silent )

# ---------- 构建 ----------

echo "→ 构建 .app + .dmg"
bash scripts/build_mac.sh
if [ ! -f "dist/$DMG_NAME" ]; then
  echo "✗ 构建未产出 dist/$DMG_NAME"
  exit 1
fi

# ---------- Git 推送 ----------

echo "→ git push main"
git push origin main
echo "→ git tag $TAG"
git tag "$TAG"
echo "→ git push tag"
git push origin "$TAG"

# ---------- 创建 GitHub release ----------

echo "→ 创建 GitHub release"
RELEASE_PAYLOAD=$(python3 - "$TAG" "$NOTES_FILE" <<'PY'
import json, sys
tag = sys.argv[1]
notes_file = sys.argv[2]
body = ""
if notes_file:
    with open(notes_file, "r", encoding="utf-8") as f:
        body = f.read()
print(json.dumps({
    "tag_name": tag,
    "name": tag,
    "body": body,
    "draft": False,
    "prerelease": False,
}))
PY
)

RELEASE_JSON=$(curl -sf -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Accept: application/vnd.github+json" \
  -H "Content-Type: application/json" \
  "https://api.github.com/repos/$REPO_PATH/releases" \
  -d "$RELEASE_PAYLOAD") || {
    echo "✗ 创建 release 失败（curl 退出码非零）"
    echo "  已推送的 tag $TAG 需要手动清理：git push origin :refs/tags/$TAG && git tag -d $TAG"
    exit 1
}

UPLOAD_URL=$(python3 - <<PY
import json, sys
data = json.loads('''$RELEASE_JSON''')
print(data["upload_url"].split("{")[0])
PY
)

if [ -z "$UPLOAD_URL" ]; then
  echo "✗ release 响应里没拿到 upload_url，响应原文："
  echo "$RELEASE_JSON"
  exit 1
fi

# ---------- 上传 dmg 资产 ----------

echo "→ 上传 $DMG_NAME"
ASSET_JSON=$(curl -sf -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/x-apple-diskimage" \
  --data-binary @"dist/$DMG_NAME" \
  "${UPLOAD_URL}?name=$DMG_NAME") || {
    echo "✗ 上传资产失败。release 已创建但缺资产，需要手动在 web UI 上传或重传。"
    echo "  release 页：https://github.com/$REPO_PATH/releases/tag/$TAG"
    exit 1
}

# ---------- 完成 ----------

echo ""
echo "✓ 发布完成"
echo "  release: https://github.com/$REPO_PATH/releases/tag/$TAG"
echo "  下载链接: https://github.com/$REPO_PATH/releases/download/$TAG/$DMG_NAME"
