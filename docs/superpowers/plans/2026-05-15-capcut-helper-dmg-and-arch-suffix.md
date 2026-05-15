# capcut_helper DMG + 文件名加架构/版本后缀 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把分发产物从 `capcut_helper.zip` 切到 `capcut_helper-arm64-v<version>.dmg`；update_checker 从硬编码常量改为按 release tag 动态构造期望资产名；删了重发 v0.1.0。

**Architecture:** 后端 adapter 不再做资产 filter（返回所有 assets），service 按 tag 模板 `_asset_name_for_tag(tag) → f"capcut_helper-arm64-{tag}.dmg"` 自己 filter。build_mac.sh 用 hdiutil 产 dmg，release.sh 替换 6 处 hardcode 字符串。前端零改动。

**Tech Stack:** Python (pyJianYingDraft 不变) + bash + macOS `hdiutil` + GitHub Releases REST API。

**Spec 来源：** [docs/superpowers/specs/2026-05-15-capcut-helper-dmg-and-arch-suffix-design.md](../specs/2026-05-15-capcut-helper-dmg-and-arch-suffix-design.md)

---

## 文件结构总览

**后端改动（重构）：**
- `backend/app/integrations/github_releases.py` — `ReleaseRaw` 重构（`download_url: str | None` 字段移除，新增 `assets: list[ReleaseAsset]`）；`ReleaseAsset` 新增 dataclass；`fetch_latest_release` 签名去掉 `asset_name` 参数
- `backend/app/services/update_checker.py` — 移除 `ASSET_NAME` 常量；新增 `_asset_name_for_tag(tag)` 函数；`check_for_update` 改为迭代 `raw.assets` 找匹配

**后端测试更新：**
- `backend/tests/test_github_releases.py` — 改断言：`raw.assets` list 替代 `raw.download_url`；`fetch_latest_release` 调用去掉 `asset_name` 入参；`test_fetch_latest_release_missing_asset` 改造为 `test_fetch_latest_release_empty_assets`
- `backend/tests/test_update_checker.py` — `_release(...)` 工厂构造 `ReleaseRaw(assets=[ReleaseAsset(...)])`；默认 asset 名匹配 `_asset_name_for_tag(tag)`；新增 `test_no_matching_asset_returns_none_download_url`
- `backend/tests/test_update_api.py` — `_VALID_RESPONSE.assets[0].name` 改为 `capcut_helper-arm64-v0.2.0.dmg`

**脚本改动：**
- `scripts/build_mac.sh` — 第 3 步从 `ditto .zip` 改为 `hdiutil ... .dmg`；读 `__version__` 命名产物 `capcut_helper-arm64-v<version>.dmg`
- `scripts/release.sh` — 6 处 `capcut_helper.zip` 改为 `$DMG_NAME`（`capcut_helper-arm64-v$VERSION.dmg`）

**文档改动：**
- `README.md` — 「发版」「打包」「分发」三个小节
- `docs/superpowers/specs/2026-05-15-capcut-helper-packaging-design.md` — §2.1 / §2.2 / §3 增量修订

**前端：零改动**（UpdateBanner / StatusBar / client / bridge 都不动；`UpdateInfo` schema 形状不变）

---

## Task 1: 后端 adapter + service 重构（原子提交）

**Files:**
- Modify: `backend/app/integrations/github_releases.py`
- Modify: `backend/app/services/update_checker.py`
- Modify: `backend/tests/test_github_releases.py`
- Modify: `backend/tests/test_update_checker.py`
- Modify: `backend/tests/test_update_api.py`

**为什么放一个任务：** adapter `ReleaseRaw` 形状变化是 service 的契约变化。两边 + 三个测试文件必须同时落地，否则任意中间状态会让 pytest 整体红。

- [ ] **Step 1: 改造 adapter `github_releases.py`**

把文件整体改为：

```python
from dataclasses import dataclass

import httpx


_TIMEOUT = 5.0
_USER_AGENT = "capcut_helper"


@dataclass
class ReleaseAsset:
    name: str
    download_url: str


@dataclass
class ReleaseRaw:
    tag_name: str
    release_url: str
    notes: str
    assets: list[ReleaseAsset]


class GitHubReleaseError(Exception):
    """GitHub Releases API 调用失败或响应异常。统一兜底类型，供 service 层 catch。"""


async def fetch_latest_release(owner: str, repo: str) -> ReleaseRaw:
    """GET https://api.github.com/repos/{owner}/{repo}/releases/latest

    任何错误（网络异常、超时、HTTP 非 2xx、JSON 解析失败、缺 tag_name）→ 抛 GitHubReleaseError。
    成功时返回 ReleaseRaw，含全部 assets（命名匹配交给上层）。
    """
    url = f"https://api.github.com/repos/{owner}/{repo}/releases/latest"
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(url, headers={"User-Agent": _USER_AGENT})
    except httpx.HTTPError as e:
        raise GitHubReleaseError(f"network: {e}") from e

    if resp.status_code != 200:
        raise GitHubReleaseError(f"http {resp.status_code}")

    try:
        body = resp.json()
    except ValueError as e:
        raise GitHubReleaseError(f"invalid json: {e}") from e

    tag_name = body.get("tag_name")
    if not isinstance(tag_name, str) or not tag_name:
        raise GitHubReleaseError("missing tag_name")

    assets = [
        ReleaseAsset(name=a["name"], download_url=a["browser_download_url"])
        for a in (body.get("assets") or [])
        if isinstance(a.get("name"), str) and isinstance(a.get("browser_download_url"), str)
    ]

    return ReleaseRaw(
        tag_name=tag_name,
        release_url=body.get("html_url") or "",
        notes=body.get("body") or "",
        assets=assets,
    )
```

要点：
- `ReleaseAsset` 新增 dataclass
- `ReleaseRaw.download_url` 字段移除，新增 `assets: list[ReleaseAsset]`
- `fetch_latest_release(owner, repo)` 签名去掉 `asset_name`
- 列表推导式同时校验 `name` 和 `browser_download_url` 都是 str（防御缺字段 / null）
- 其他错误处理路径保持不变

- [ ] **Step 2: 改造 service `update_checker.py`**

把文件整体改为：

```python
from packaging.version import InvalidVersion, Version

from app.integrations.github_releases import GitHubReleaseError, fetch_latest_release
from app.schemas.update import UpdateInfo


GITHUB_OWNER = "cookaihq"
GITHUB_REPO = "capcut_helper"


def _asset_name_for_tag(tag: str) -> str:
    """根据 release tag 构造期望的资产名。tag 形如 'v0.2.0'。"""
    return f"capcut_helper-arm64-{tag}.dmg"


def _strip_v_prefix(tag: str) -> str:
    return tag[1:] if tag.startswith("v") else tag


def _is_newer(latest: str, current: str) -> bool:
    """SemVer 比较；任一不符合 PEP 440 时回退为字符串相等不等判断。"""
    try:
        return Version(latest) > Version(current)
    except InvalidVersion:
        return latest != current


async def check_for_update(current_version: str) -> UpdateInfo:
    try:
        raw = await fetch_latest_release(GITHUB_OWNER, GITHUB_REPO)
    except GitHubReleaseError as e:
        return UpdateInfo(
            current_version=current_version,
            has_update=False,
            error=str(e),
        )

    expected = _asset_name_for_tag(raw.tag_name)
    download_url = next(
        (a.download_url for a in raw.assets if a.name == expected),
        None,
    )

    latest = _strip_v_prefix(raw.tag_name)
    return UpdateInfo(
        current_version=current_version,
        latest_version=latest,
        has_update=_is_newer(latest, current_version),
        release_url=raw.release_url,
        download_url=download_url,
        notes=raw.notes,
    )
```

变化：
- `ASSET_NAME` 常量删除
- 新增 `_asset_name_for_tag(tag)` 函数
- `fetch_latest_release` 调用去掉第三个参数
- `download_url` 改为从 `raw.assets` 用 `next(...)` 找匹配

- [ ] **Step 3: 重写测试 `test_github_releases.py`**

把整个文件改为：

```python
import httpx
import pytest
import respx

from app.integrations.github_releases import (
    GitHubReleaseError,
    ReleaseAsset,
    ReleaseRaw,
    fetch_latest_release,
)


_VALID_RESPONSE = {
    "tag_name": "v0.2.0",
    "html_url": "https://github.com/cookaihq/capcut_helper/releases/tag/v0.2.0",
    "body": "## 更新内容\n- 新增了横幅",
    "assets": [
        {
            "name": "capcut_helper-arm64-v0.2.0.dmg",
            "browser_download_url": "https://github.com/cookaihq/capcut_helper/releases/download/v0.2.0/capcut_helper-arm64-v0.2.0.dmg",
        }
    ],
}


@respx.mock
async def test_fetch_latest_release_happy_path():
    respx.get("https://api.github.com/repos/cookaihq/capcut_helper/releases/latest").mock(
        return_value=httpx.Response(200, json=_VALID_RESPONSE)
    )
    raw = await fetch_latest_release("cookaihq", "capcut_helper")
    assert isinstance(raw, ReleaseRaw)
    assert raw.tag_name == "v0.2.0"
    assert raw.release_url == "https://github.com/cookaihq/capcut_helper/releases/tag/v0.2.0"
    assert raw.notes == "## 更新内容\n- 新增了横幅"
    assert raw.assets == [
        ReleaseAsset(
            name="capcut_helper-arm64-v0.2.0.dmg",
            download_url="https://github.com/cookaihq/capcut_helper/releases/download/v0.2.0/capcut_helper-arm64-v0.2.0.dmg",
        )
    ]


@respx.mock
async def test_fetch_latest_release_empty_assets():
    response = dict(_VALID_RESPONSE, assets=[])
    respx.get("https://api.github.com/repos/cookaihq/capcut_helper/releases/latest").mock(
        return_value=httpx.Response(200, json=response)
    )
    raw = await fetch_latest_release("cookaihq", "capcut_helper")
    assert raw.tag_name == "v0.2.0"
    assert raw.assets == []


@respx.mock
async def test_fetch_latest_release_missing_tag_name():
    bad = dict(_VALID_RESPONSE)
    del bad["tag_name"]
    respx.get("https://api.github.com/repos/cookaihq/capcut_helper/releases/latest").mock(
        return_value=httpx.Response(200, json=bad)
    )
    with pytest.raises(GitHubReleaseError, match="missing tag_name"):
        await fetch_latest_release("cookaihq", "capcut_helper")


@respx.mock
async def test_fetch_latest_release_404():
    respx.get("https://api.github.com/repos/cookaihq/capcut_helper/releases/latest").mock(
        return_value=httpx.Response(404, json={"message": "Not Found"})
    )
    with pytest.raises(GitHubReleaseError, match="http 404"):
        await fetch_latest_release("cookaihq", "capcut_helper")


@respx.mock
async def test_fetch_latest_release_network_error():
    respx.get("https://api.github.com/repos/cookaihq/capcut_helper/releases/latest").mock(
        side_effect=httpx.ConnectError("dns")
    )
    with pytest.raises(GitHubReleaseError, match="network"):
        await fetch_latest_release("cookaihq", "capcut_helper")
```

变化：
- 加 `ReleaseAsset` import
- `_VALID_RESPONSE.assets[0].name` 改为 `capcut_helper-arm64-v0.2.0.dmg`，url 同步
- `test_fetch_latest_release_happy_path`：断言整个 `assets` list
- `test_fetch_latest_release_missing_asset` → `test_fetch_latest_release_empty_assets`：mock `assets: []`，断言返回 `raw.assets == []`
- 全部 `fetch_latest_release(...)` 调用去掉第三个参数

- [ ] **Step 4: 重写测试 `test_update_checker.py`**

把整个文件改为：

```python
import pytest

from app.integrations.github_releases import (
    GitHubReleaseError,
    ReleaseAsset,
    ReleaseRaw,
)
from app.services import update_checker
from app.services.update_checker import _asset_name_for_tag, check_for_update


def _release(tag="v0.2.0", asset_name=None):
    """构造 ReleaseRaw。asset_name=None 时默认匹配 _asset_name_for_tag(tag)；
    传具体名字可以模拟「资产名不匹配」用例。"""
    name = asset_name if asset_name is not None else _asset_name_for_tag(tag)
    return ReleaseRaw(
        tag_name=tag,
        release_url="https://x/release",
        notes="notes",
        assets=[ReleaseAsset(name=name, download_url="https://x/asset")],
    )


async def _patch_fetch(monkeypatch, *, returns=None, raises=None):
    async def fake(owner, repo):
        if raises is not None:
            raise raises
        return returns
    monkeypatch.setattr(update_checker, "fetch_latest_release", fake)


async def test_has_update_when_remote_newer(monkeypatch):
    await _patch_fetch(monkeypatch, returns=_release(tag="v0.2.0"))
    info = await check_for_update("0.1.0")
    assert info.has_update is True
    assert info.latest_version == "0.2.0"
    assert info.current_version == "0.1.0"
    assert info.download_url == "https://x/asset"


async def test_no_update_when_versions_equal(monkeypatch):
    await _patch_fetch(monkeypatch, returns=_release(tag="v0.1.0"))
    info = await check_for_update("0.1.0")
    assert info.has_update is False
    assert info.latest_version == "0.1.0"


async def test_no_update_when_local_is_newer(monkeypatch):
    await _patch_fetch(monkeypatch, returns=_release(tag="v0.1.0"))
    info = await check_for_update("0.2.0")
    assert info.has_update is False


async def test_strips_v_prefix(monkeypatch):
    await _patch_fetch(monkeypatch, returns=_release(tag="v0.2.0"))
    info = await check_for_update("0.1.0")
    assert info.latest_version == "0.2.0"   # 不含 v


async def test_non_semver_fallback_to_string_inequality(monkeypatch):
    await _patch_fetch(monkeypatch, returns=_release(tag="release-2026-05"))
    info = await check_for_update("0.1.0")
    assert info.has_update is True


async def test_non_semver_equal_string_means_no_update(monkeypatch):
    await _patch_fetch(monkeypatch, returns=_release(tag="release-2026-05"))
    info = await check_for_update("release-2026-05")
    assert info.has_update is False


async def test_adapter_error_returns_no_update_with_error_field(monkeypatch):
    await _patch_fetch(monkeypatch, raises=GitHubReleaseError("network: dns"))
    info = await check_for_update("0.1.0")
    assert info.has_update is False
    assert info.error == "network: dns"
    assert info.current_version == "0.1.0"
    assert info.latest_version is None


async def test_no_matching_asset_returns_none_download_url(monkeypatch):
    """release 上传了错名的资产（如 .zip 而非 .dmg）→ has_update 仍 True，但 download_url=None"""
    await _patch_fetch(
        monkeypatch,
        returns=_release(tag="v0.2.0", asset_name="capcut_helper-arm64-v0.2.0.zip"),
    )
    info = await check_for_update("0.1.0")
    assert info.has_update is True
    assert info.latest_version == "0.2.0"
    assert info.download_url is None


async def test_empty_assets_returns_none_download_url(monkeypatch):
    """release 完全没传资产 → has_update 仍 True，download_url=None"""
    raw = ReleaseRaw(
        tag_name="v0.2.0",
        release_url="https://x/release",
        notes="notes",
        assets=[],
    )
    await _patch_fetch(monkeypatch, returns=raw)
    info = await check_for_update("0.1.0")
    assert info.has_update is True
    assert info.download_url is None
```

变化：
- import `ReleaseAsset` + `_asset_name_for_tag`
- `_release(...)` 工厂换成构造 `ReleaseRaw(assets=[ReleaseAsset(...)])`，默认名字匹配模板
- `_patch_fetch` 内部 `fake(owner, repo)` 签名去掉 `asset_name`
- 现有 7 个断言保持不变（assert `info.download_url == "https://x/asset"` 等）
- 新增 2 个 case：`test_no_matching_asset_returns_none_download_url`、`test_empty_assets_returns_none_download_url`

- [ ] **Step 5: 修改 `test_update_api.py` 的 `_VALID_RESPONSE`**

打开 `backend/tests/test_update_api.py`，找到 `_VALID_RESPONSE` 字典，把 `assets` 列表里 dict 的两个字段改名：

```python
_VALID_RESPONSE = {
    "tag_name": "v0.2.0",
    "html_url": "https://github.com/cookaihq/capcut_helper/releases/tag/v0.2.0",
    "body": "notes",
    "assets": [
        {
            "name": "capcut_helper-arm64-v0.2.0.dmg",
            "browser_download_url": "https://x/asset",
        }
    ],
}
```

下面 `test_update_check_returns_envelope` 里的断言 `assert data["download_url"] == "https://x/zip"` 改为：

```python
    assert data["download_url"] == "https://x/asset"
```

- [ ] **Step 6: 跑测试，确认全绿**

Run: `cd backend && uv run pytest -q`
Expected: 全套通过。具体到本任务影响的 4 个文件：
- `test_github_releases.py`：5 → 5 tests pass (`happy_path`, `empty_assets`, `missing_tag_name`, `404`, `network_error`)
- `test_update_checker.py`：7 → 9 tests pass (原 7 + `no_matching_asset` + `empty_assets`)
- `test_update_api.py`：2 → 2 tests pass

如果失败：检查 import 是否完整、签名是否同步改了 adapter + service + 测试。

- [ ] **Step 7: Commit**

```bash
git add backend/app/integrations/github_releases.py \
        backend/app/services/update_checker.py \
        backend/tests/test_github_releases.py \
        backend/tests/test_update_checker.py \
        backend/tests/test_update_api.py
git commit -m "$(cat <<'EOF'
refactor(capcut_helper): adapter 不再做资产 filter，service 按 tag 模板匹配

为支持新文件名 capcut_helper-arm64-v<version>.dmg（版本号嵌入文件名），
update_checker 不能再用单一 hardcode 常量做资产名匹配。重构：

- ReleaseRaw.download_url 字段移除，新增 assets: list[ReleaseAsset]
- fetch_latest_release 签名去掉 asset_name 参数
- update_checker ASSET_NAME 常量移除，新增 _asset_name_for_tag(tag) 函数
- check_for_update 自己迭代 raw.assets 找匹配
- 新增 2 测试：资产名不匹配 / 资产为空 → download_url=None

前端 UpdateInfo schema 形状不变，零改动。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: `build_mac.sh` 切到 hdiutil + DMG

**Files:**
- Modify: `scripts/build_mac.sh`

- [ ] **Step 1: 重写 build_mac.sh 末尾**

把整个文件改为：

```bash
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
```

要点：
- 顶端解析 `VERSION` + `DMG_NAME`，跟 release.sh 同样的解析方式
- 第 3 步用临时 staging 目录组织 dmg 内容（.app + Applications 软链）
- `hdiutil create -format UDZO` 是压缩格式
- `-ov` 让重跑能覆盖已存在 dmg
- 末尾 `rm -rf dmg-staging` 清理（开头也 `rm -rf` 一次保证重跑干净）
- 末尾两行 echo 同步改为打印 dmg 路径

- [ ] **Step 2: 跑构建烟测**

Run: `bash scripts/build_mac.sh`
Expected: 末尾输出 `dmg: <pwd>/dist/capcut_helper-arm64-v0.1.0.dmg`。

如果 PyInstaller 已经 cache 过：耗时 1-3 分钟。

- [ ] **Step 3: 烟测 dmg 可挂载**

Run: `open dist/capcut_helper-arm64-v0.1.0.dmg`
Expected: Finder 弹出挂载窗口，里面能看到 `capcut_helper.app` 和 `Applications` 软链图标。手动卸载（Finder 侧边栏右键 → 推出，或 `hdiutil detach /Volumes/capcut_helper`）。

- [ ] **Step 4: Commit**

```bash
git add scripts/build_mac.sh
git commit -m "$(cat <<'EOF'
build(capcut_helper): build_mac.sh 切到 hdiutil + DMG，文件名含版本号

产物从 dist/capcut_helper.zip 改为 dist/capcut_helper-arm64-v<version>.dmg。
版本号从 backend/app/__init__.py::__version__ 解析（同 release.sh）。
dmg 内含 .app + Applications 软链，挂载后用户拖即装。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: `release.sh` 替换文件名

**Files:**
- Modify: `scripts/release.sh`

- [ ] **Step 1: 引入 `DMG_NAME` 变量 + 替换 6 处 hardcode**

在 `scripts/release.sh` 中：

1. 在 `TAG="v$VERSION"` 后面（约第 49 行）加一行：

```bash
DMG_NAME="capcut_helper-arm64-v${VERSION}.dmg"
```

2. 把 6 处 `capcut_helper.zip` 字符串改为 `$DMG_NAME`：

| 行（旧） | 改为 |
|---|---|
| `if [ ! -f dist/capcut_helper.zip ]; then` | `if [ ! -f "dist/$DMG_NAME" ]; then` |
| `echo "✗ 构建未产出 dist/capcut_helper.zip"` | `echo "✗ 构建未产出 dist/$DMG_NAME"` |
| `echo "→ 上传 capcut_helper.zip"` | `echo "→ 上传 $DMG_NAME"` |
| `--data-binary @dist/capcut_helper.zip \` | `--data-binary @"dist/$DMG_NAME" \` |
| `"${UPLOAD_URL}?name=capcut_helper.zip") \|\| {` | `"${UPLOAD_URL}?name=$DMG_NAME") \|\| {` |
| `echo "  下载链接: https://github.com/$REPO_PATH/releases/download/$TAG/capcut_helper.zip"` | `echo "  下载链接: https://github.com/$REPO_PATH/releases/download/$TAG/$DMG_NAME"` |

另外，上传资产那个 curl 的 Content-Type 现在是 `application/zip`，要改成 `application/x-apple-diskimage`（dmg 的标准 MIME）：

| 旧 | 改为 |
|---|---|
| `-H "Content-Type: application/zip" \` | `-H "Content-Type: application/x-apple-diskimage" \` |

- [ ] **Step 2: bash 语法检查**

Run: `bash -n scripts/release.sh`
Expected: 无输出（语法 OK）。

- [ ] **Step 3: grep 校验**

Run: `grep -n 'capcut_helper\.zip' scripts/release.sh`
Expected: 无输出。

- [ ] **Step 4: Commit**

```bash
git add scripts/release.sh
git commit -m "$(cat <<'EOF'
build(capcut_helper): release.sh 跟随 DMG_NAME 变量

6 处 capcut_helper.zip 改为 $DMG_NAME（capcut_helper-arm64-v$VERSION.dmg），
上传 Content-Type 改 application/x-apple-diskimage。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: README 三个小节更新

**Files:**
- Modify: `README.md`

- [ ] **Step 1: 改「发版」小节**

找到 README.md 中 `## 发版` 小节，把其中提到 `capcut_helper.zip` 的所有内容改为 dmg 形式。具体替换：

第 57 行（约）：
```
旧: 调 GitHub API 创建 release → 上传 `capcut_helper.zip` 资产。失败时会指出已推 tag 怎么清理。
新: 调 GitHub API 创建 release → 上传 `capcut_helper-arm64-v<version>.dmg` 资产。失败时会指出已推 tag 怎么清理。
```

第 62 行（约）—— 末尾的「硬编码约定」说明段落：
```
旧: > zip 资产名必须是 `capcut_helper.zip`（`scripts/build_mac.sh` 产物名 + `services/update_checker.py::ASSET_NAME` 匹配该名）。脚本已硬编码这两个约定，按它来就行。
新: > dmg 资产名必须是 `capcut_helper-arm64-v<version>.dmg`（`scripts/build_mac.sh` 产物名 + `services/update_checker.py::_asset_name_for_tag()` 按 tag 模板构造该名）。脚本已硬编码这两个约定，按它来就行。
```

- [ ] **Step 2: 改「打包成 .app 分发」小节**

第 73 行（约）：
```
旧: - `dist/capcut_helper.zip` —— 分发用，用 Apple 推荐的 `ditto` 打包（保留符号链接）
新: - `dist/capcut_helper-arm64-v<version>.dmg` —— 分发用，hdiutil 打 UDZO 压缩 dmg
```

- [ ] **Step 3: 改「分发给同事」小节**

第 77 行（约）：
```
旧: 把 `dist/capcut_helper.zip` 发给对方，请对方按以下步骤：
新: 把 `dist/capcut_helper-arm64-v<version>.dmg` 发给对方，请对方按以下步骤：
```

之后的步骤列表（解压 zip → 拖 app），整段重写为：

```markdown
1. 双击 `capcut_helper-arm64-v<version>.dmg` 挂载
2. 在弹出的 Finder 窗口里把 `capcut_helper.app` 拖到旁边的 `Applications` 软链上
3. **首次打开**：因为未做代码签名，macOS 会拦截。**右键 → 打开 → 在弹窗里再点「打开」**，之后双击就行。或在「系统设置 → 隐私与安全」里允许。
4. **首次访问草稿目录时**，近版 macOS 会再弹一个文件夹访问权限提示（针对 `~/Movies` 或自定义草稿目录），点「允许」即可
5. 启动后第一次进 GUI，按「设置」标签里的「自动探测」找剪映草稿目录，或手动选择
```

- [ ] **Step 4: grep 校验**

Run: `grep -n 'capcut_helper\.zip' README.md`
Expected: 无输出。

- [ ] **Step 5: Commit**

```bash
git add README.md
git commit -m "$(cat <<'EOF'
docs(capcut_helper): README 三个小节切到 DMG 命名 + 分发步骤

发版/打包/分发小节都改为 capcut_helper-arm64-v<version>.dmg。
分发步骤从「解压 zip → 拖 app」改为「双击 dmg → 拖到 Applications 软链」。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: 包装 spec 增量修订

**Files:**
- Modify: `docs/superpowers/specs/2026-05-15-capcut-helper-packaging-design.md`

- [ ] **Step 1: §2.1 加 DMG**

定位到 `### 2.1 核心范围（本 spec）` 小节，把 "macOS arm64 `.app` bundle（PyInstaller）" 这条增补：

```
旧: - macOS arm64 `.app` bundle（PyInstaller）
新: - macOS arm64 `.app` bundle（PyInstaller），打成 `dist/capcut_helper-arm64-v<version>.dmg`（hdiutil UDZO 压缩，含 .app + Applications 软链）
```

- [ ] **Step 2: §2.2 删除「不做 DMG」**

定位到 `### 2.2 非目标`，找到 `**DMG / 安装器**：直接 zip \`.app\` 分发` 这一行，**整行删除**。

- [ ] **Step 3: §3 产物路径与工具说明**

定位到 `## 3. 工具与产物` 小节。两处改：

1. **工具**段落开头加一句关于 hdiutil：

```
现状: **工具**：PyInstaller。理由：pywebview + FastAPI + pyJianYingDraft 这种「Python + WebView + 资源文件」组合在 pywebview 官方文档与社区里几乎都是 PyInstaller。py2app 在 pywebview 场景实例少；Briefcase（BeeWare）一站式打包/签名/分发对「zip 一个 .app 给同事」属于过度方案。
改后: **工具**：PyInstaller（打 .app）+ `hdiutil`（macOS 内置，把 .app 打成 dmg）。理由：pywebview + FastAPI + pyJianYingDraft 这种「Python + WebView + 资源文件」组合在 pywebview 官方文档与社区里几乎都是 PyInstaller。py2app 在 pywebview 场景实例少；Briefcase（BeeWare）一站式打包/签名/分发对「dmg 一个 .app 给同事」属于过度方案。hdiutil 系统自带、零额外依赖，UDZO 压缩比与 zip 接近，dmg 本身又是 macOS 用户最熟悉的安装包格式。
```

2. **产物**那行：

```
旧: **产物**：`capcut_helper/dist/capcut_helper.app`（项目级 `dist/`，不是 `backend/dist/`——构建脚本通过 `--distpath=../dist --workpath=../build` 显式定位）。
新: **产物**：`capcut_helper/dist/capcut_helper.app` 和 `capcut_helper/dist/capcut_helper-arm64-v<version>.dmg`（项目级 `dist/`，不是 `backend/dist/`——构建脚本通过 `--distpath=../dist --workpath=../build` 显式定位）。
```

3. **分发**段落里 `ditto` 那段说明，**整段替换**为：

```
**分发**：直接发 `dist/capcut_helper-arm64-v<version>.dmg`。hdiutil UDZO 压缩，体积接近 zip。dmg 用户体验比 zip 优：双击挂载 → 拖 .app 到自带 Applications 软链 → 完成安装。
```

ditto 解释段（保留符号链接相关）全部删除（dmg 用 hdiutil，原 ditto 注意事项不再适用）。

- [ ] **Step 4: grep 校验**

Run: `grep -n 'capcut_helper\.zip\|ditto -c' docs/superpowers/specs/2026-05-15-capcut-helper-packaging-design.md`
Expected: 无输出（或仅匹配到「历史/原始决策」相关备注，如果有要逐条核对是否要保留）。

- [ ] **Step 5: Commit**

```bash
git add docs/superpowers/specs/2026-05-15-capcut-helper-packaging-design.md
git commit -m "$(cat <<'EOF'
docs(capcut_helper): packaging spec 增量修订——加入 DMG，去掉 non-goal

§2.1 产物加 dmg，§2.2 删除「不做 DMG / 安装器」non-goal 条，
§3 工具加 hdiutil、产物加 dmg 路径、分发段从 ditto+zip 改为 hdiutil+dmg。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: grep 终态校验（不 commit，只验证）

**Files:** 无改动

- [ ] **Step 1: 跑 grep**

Run:
```bash
grep -rn 'capcut_helper\.zip' backend/ frontend/ scripts/ README.md
```
Expected: 无输出。

如果命中行：检查是 (a) 历史 spec/plan 文档（这种 grep 范围已排除，命中说明范围不对）还是 (b) 真实代码遗漏（要回头补改）。

- [ ] **Step 2: 后端测试全绿**

Run: `cd backend && uv run pytest -q`
Expected: 全套通过。

- [ ] **Step 3: 前端测试全绿**

Run: `cd frontend && npm run test --silent`
Expected: 全套通过。

如有失败：阻塞，先回头修。

---

## Task 7: 删除 v0.1.0 release 和 tag

**Files:** 无代码改动；调 GitHub API + git 命令。

- [ ] **Step 1: 调 API 拿 release id 并删除**

Run:
```bash
TOKEN=$(cat .github-token)
RELEASE_ID=$(curl -s -H "Authorization: Bearer $TOKEN" \
  https://api.github.com/repos/cookaihq/capcut_helper/releases/tags/v0.1.0 | \
  python3 -c "import sys, json; print(json.load(sys.stdin)['id'])")
echo "Release ID: $RELEASE_ID"
curl -s -o /dev/null -w "%{http_code}\n" -X DELETE \
  -H "Authorization: Bearer $TOKEN" \
  "https://api.github.com/repos/cookaihq/capcut_helper/releases/$RELEASE_ID"
```

Expected:
- 第一条 echo 输出一个数字 ID
- 第二条 curl 输出 `204`（DELETE 成功）

- [ ] **Step 2: 删远端 tag**

Run: `git push origin :refs/tags/v0.1.0`
Expected: `- [deleted] v0.1.0`

- [ ] **Step 3: 删本地 tag**

Run: `git tag -d v0.1.0`
Expected: `Deleted tag 'v0.1.0' (was <sha>)`

- [ ] **Step 4: 验证全部清除**

Run:
```bash
git ls-remote --tags origin v0.1.0
git tag -l v0.1.0
curl -s -o /dev/null -w "%{http_code}\n" \
  https://api.github.com/repos/cookaihq/capcut_helper/releases/tags/v0.1.0
```
Expected:
- 第一条无输出
- 第二条无输出
- 第三条输出 `404`

- [ ] **Step 5: 不 commit**

本任务不动代码，只清远端状态。继续 Task 8。

---

## Task 8: 重发 v0.1.0

**Files:** 无代码改动；运行 release.sh。

前置：Task 1-7 全部完成，`__version__` 仍为 `"0.1.0"`，working tree clean。

- [ ] **Step 1: 验证前置**

Run:
```bash
git status              # 应当显示 working tree clean
grep __version__ backend/app/__init__.py  # 应当显示 0.1.0
git ls-remote --tags origin v0.1.0   # 应当无输出（已删）
```

如任一不满足：先回头修。

- [ ] **Step 2: 跑 release.sh**

Run: `bash scripts/release.sh`
Expected:
- 测试全绿
- build_mac.sh 成功（耗时 1-3 分钟）
- `git push origin main` 推送新增 5 个 commit（Task 1-5）
- `git tag v0.1.0` + `git push origin v0.1.0`
- curl 创建 release
- curl 上传 `capcut_helper-arm64-v0.1.0.dmg`
- 末尾打印 `✓ 发布完成` + release URL + 下载 URL

- [ ] **Step 3: 浏览器或 API 验证新 release**

Run:
```bash
curl -s https://api.github.com/repos/cookaihq/capcut_helper/releases/latest | \
  python3 -c "
import sys, json
d = json.load(sys.stdin)
print('tag:', d['tag_name'])
print('assets:')
for a in d['assets']:
    print(' -', a['name'], a.get('size'), 'bytes')
"
```

Expected:
```
tag: v0.1.0
assets:
 - capcut_helper-arm64-v0.1.0.dmg <size> bytes
```

资产数恰好 1 个，文件名是新格式。

- [ ] **Step 4: 不 commit**

release.sh 流程内部已经处理所有 push 和 release 创建。本任务不需要额外 commit。

---

## Task 9: 端到端验收

**Files:** 无改动；按 spec §11 走一遍。

- [ ] **Step 1: 验证临时 bump 后构建文件名联动**

Run:
```bash
# 临时改成 0.1.1
sed -i.bak 's/__version__ = "0.1.0"/__version__ = "0.1.1"/' backend/app/__init__.py
bash scripts/build_mac.sh 2>&1 | tail -3
# 检查产物
ls -la dist/capcut_helper-arm64-v0.1.1.dmg
# 还原
mv backend/app/__init__.py.bak backend/app/__init__.py
# 验证还原
grep __version__ backend/app/__init__.py
```

Expected:
- build_mac.sh 末尾打印 `dmg: <pwd>/dist/capcut_helper-arm64-v0.1.1.dmg`
- `ls` 列出该文件
- 还原后 `grep` 输出 `__version__ = "0.1.0"`

清理验证产物：`rm dist/capcut_helper-arm64-v0.1.1.dmg`。

- [ ] **Step 2: 验证 dmg 挂载体验**

Run: `open dist/capcut_helper-arm64-v0.1.0.dmg`
Expected: Finder 窗口弹出，含 `.app` 图标 + `Applications` 软链。手动卸载（`hdiutil detach /Volumes/capcut_helper`）。

- [ ] **Step 3: 验证 git 工作树干净**

Run: `git status`
Expected: `nothing to commit, working tree clean`

- [ ] **Step 4: 验证 grep 全 zero**

Run: `grep -rn 'capcut_helper\.zip' backend/ frontend/ scripts/ README.md`
Expected: 无输出

- [ ] **Step 5: 验证 GitHub release 页面**

人工打开 https://github.com/cookaihq/capcut_helper/releases/tag/v0.1.0
Expected: 看到 v0.1.0 release，资产列表只含 `capcut_helper-arm64-v0.1.0.dmg`（无旧 zip）。

- [ ] **Step 6: 全任务完成**

本任务不 commit。所有验收点 ✓ 即整个 spec 落地。

---

## 自检结论（plan 写完后自检）

- **Spec 覆盖：** spec §3（hardcode 索引）→ Tasks 1-5 覆盖；§4（DMG 构建）→ Task 2；§5（release.sh）→ Task 3；§6（update_checker 重构）→ Task 1；§7（测试）→ Task 1（合入大重构）；§8（v0.1.0 删了重发）→ Tasks 7+8；§9（README）→ Task 4；§10（包装 spec）→ Task 5；§11（验收）→ Task 9
- **占位符：** 无 TBD / TODO / "fill in later"
- **类型一致性：** `ReleaseAsset` 在 Task 1 step 1 定义并在 step 2/3/4/5 引用；`_asset_name_for_tag` 同样；`DMG_NAME` 变量在 Task 2 和 Task 3 中保持同名同语义
- **测试断言一致：** test_update_api.py 的 download_url 断言改为 `"https://x/asset"`，与 `_VALID_RESPONSE.assets[0].browser_download_url` 一致

---

## 关键依赖关系

```
Task 1 (后端重构) ──┐
Task 2 (build.sh)  ──┼─→ Task 6 (grep 校验 + 测试全绿)
Task 3 (release.sh) ─┤
Task 4 (README)    ──┤
Task 5 (spec)      ──┘
                     ↓
                  Task 7 (删 v0.1.0)
                     ↓
                  Task 8 (重发 v0.1.0)
                     ↓
                  Task 9 (验收)
```

Tasks 1-5 之间互相独立，可任意顺序（除非主分支强制 fast-forward 限制）。Tasks 6-9 必须按序。
