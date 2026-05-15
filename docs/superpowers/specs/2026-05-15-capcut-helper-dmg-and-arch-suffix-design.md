# capcut_helper DMG 打包 + 文件名加架构/版本后缀 — 设计文档

> 创建日期：2026-05-15
> 状态：brainstorming 完成，待写实现计划
> 范围：把分发产物从 `capcut_helper.zip` 换成 `capcut_helper-arm64-v<version>.dmg`；update_checker 改用动态资产名匹配；删了重发 v0.1.0。
> 前置：版本号与更新提示已落地（`docs/superpowers/specs/2026-05-15-capcut-helper-version-and-update-design.md`），release.sh 自动化已就绪，v0.1.0 release 已发出（包含旧名 `capcut_helper.zip`）。

## 1. 项目目标

- **从 .zip 换到 .dmg**：macOS 用户最熟悉的安装包形式，双击挂载 → 拖 .app 到 Applications 一气呵成
- **文件名带架构 + 版本号**：`capcut_helper-arm64-v0.1.0.dmg`，资产文件离开 GitHub 上下文（被同事单独转发）也能从文件名读出是哪个版本、哪个架构
- **update_checker 适配新命名约定**：版本号嵌进文件名后，资产名必须随每次发布的 tag 动态构造，不能再用单一 hardcode 常量

## 2. 范围

### 2.1 核心范围（本 spec）

- `scripts/build_mac.sh`：读 `__version__`，用 `hdiutil` 产 `dist/capcut_helper-arm64-v<version>.dmg`
- `scripts/release.sh`：把 6 处 `capcut_helper.zip` 改为 `capcut_helper-arm64-v$VERSION.dmg`（VERSION 变量已存在，直接复用）
- `backend/app/integrations/github_releases.py`：重构。`ReleaseRaw` 不再带 `download_url` 单字段，改成 `assets: list[ReleaseAsset]`；`fetch_latest_release` 签名去掉 `asset_name` 参数
- `backend/app/services/update_checker.py`：`ASSET_NAME` 常量 → `_asset_name_for_tag(tag)` 函数；`check_for_update` 取 `raw.assets` 遍历找匹配
- 测试更新：adapter 5 个测试 + service 7 个测试改断言；新增「资产名不匹配 → download_url=None」case
- `README.md`：分发指引从 zip 解压改成 dmg 挂载；发版小节文件名同步
- 之前的 `docs/superpowers/specs/2026-05-15-capcut-helper-packaging-design.md`：§2.1 加 DMG，§2.2 去掉「不做 DMG / 安装器」（原 non-goal，现规范化为正式产物）
- v0.1.0 删了重发：删 GitHub release + 远端 tag + 本地 tag，新规范从重发的 v0.1.0 起生效

### 2.2 非目标

- **universal2 / Intel Mac**：包装 spec §2.2 已明确仅 macOS arm64，本 spec 沿用
- **DMG 美化**：不做背景图、不调窗口大小、不定位图标，YAGNI；`hdiutil` 默认布局够用
- **代码签名 / 公证**：沿用包装 spec 立场，未签名 + 用户首次绕 Gatekeeper
- **向后兼容旧 `capcut_helper.zip`**：v0.1.0 删了重发，无遗留用户
- **同时发 .dmg + .zip**：YAGNI；.dmg 内已含 .app，.zip 再压一层无价值
- **GitHub Actions / CI**：发版仍走本地 `bash scripts/release.sh`

## 3. 现状索引（grep 出来的 hardcode 点位）

发版前 `capcut_helper.zip` 在 6 处出现：

```
scripts/build_mac.sh:18       ( cd dist && ditto -c -k ... capcut_helper.zip )
scripts/build_mac.sh:23       echo "  zip:  ... capcut_helper.zip"
scripts/release.sh:91         if [ ! -f dist/capcut_helper.zip ]; then
scripts/release.sh:92         echo "✗ 构建未产出 dist/capcut_helper.zip"
scripts/release.sh:152        echo "→ 上传 capcut_helper.zip"
scripts/release.sh:156        --data-binary @dist/capcut_helper.zip \
scripts/release.sh:157        "${UPLOAD_URL}?name=capcut_helper.zip") || {
scripts/release.sh:168        echo "  下载链接: ... capcut_helper.zip"
backend/app/services/update_checker.py:9   ASSET_NAME = "capcut_helper.zip"
README.md:57                  调 GitHub API 创建 release → 上传 `capcut_helper.zip` 资产
README.md:62                  zip 资产名必须是 `capcut_helper.zip`
README.md:73                  - `dist/capcut_helper.zip` —— 分发用
README.md:77                  把 `dist/capcut_helper.zip` 发给对方
```

全部需要替换或移除。新代码完成后 `grep -rn 'capcut_helper\.zip' backend/ frontend/ scripts/ README.md` 应当返回零结果（历史 spec/plan 文档保留为历史记录，不动）。

## 4. DMG 构建

### 4.1 工具选择

**用 `hdiutil`（macOS 内置）**。

| 方案 | 依赖 | 美化能力 | 是否够用 |
|---|---|---|---|
| `hdiutil` | 系统自带 | 基础（无背景图/窗口布局/图标定位） | ✅ |
| `create-dmg` | brew install + Node | 高 | 用不到 |
| `dmgbuild` | pip install | 中 | 用不到 |

DMG 需求很简单：双击挂载 → 看到 .app 和 Applications 软链 → 拖 .app 到 Applications。`hdiutil` + 一个临时 staging 目录就能做到。

### 4.2 build_mac.sh 末尾改造

替换原来的 `ditto -c -k ... capcut_helper.zip` 那一步：

```bash
VERSION=$(grep -oE '"[0-9]+\.[0-9]+\.[0-9]+"' backend/app/__init__.py | head -1 | tr -d '"')
DMG_NAME="capcut_helper-arm64-v${VERSION}.dmg"

( cd dist && \
  mkdir -p dmg-staging && \
  cp -R capcut_helper.app dmg-staging/ && \
  ln -sf /Applications dmg-staging/Applications && \
  hdiutil create -volname "capcut_helper" \
                 -srcfolder dmg-staging \
                 -ov -format UDZO \
                 "$DMG_NAME" && \
  rm -rf dmg-staging )
```

逐行说明：
- `VERSION` 从 `__version__` 解析（同 release.sh 做法，保持唯一来源）
- `mkdir dmg-staging` 临时区平铺 .app + Applications 软链
- `ln -sf /Applications dmg-staging/Applications` 创建到系统 `/Applications` 的软链——dmg 挂载后用户可视化拖拽
- `hdiutil create -format UDZO` UDZO 是 zlib 压缩格式，体积接近 zip
- `-ov` 覆盖已存在 dmg（重跑 build 时不报错）
- `rm -rf dmg-staging` 清理

输出：`dist/capcut_helper-arm64-v<version>.dmg`（产物路径自带版本号，不需要 release.sh 改名）。

### 4.3 同步改的两行 echo

build_mac.sh 末尾：

```bash
echo "构建完成："
echo "  .app: $(pwd)/dist/capcut_helper.app"
echo "  dmg:  $(pwd)/dist/${DMG_NAME}"
```

## 5. release.sh 改动

VERSION 变量在脚本里已经从 `__version__` 解析过（用来打 tag），直接复用。新增一个 `DMG_NAME` 变量集中管理：

```bash
DMG_NAME="capcut_helper-arm64-v${VERSION}.dmg"
```

6 处 hardcode 替换为：
- 构建后检查文件存在：`if [ ! -f "dist/$DMG_NAME" ]; then`
- 上传 curl：`--data-binary @dist/$DMG_NAME` + `?name=$DMG_NAME`
- 错误消息和成功提示里的字符串同步改

## 6. update_checker 重构（核心变更）

### 6.1 为什么重构

`update_checker.ASSET_NAME` 之前是常量 `"capcut_helper.zip"`。新约定下资产名 `capcut_helper-arm64-v0.2.0.dmg` 里嵌着版本号——版本号只能从查到的 release 的 `tag_name` 取，因此不能再是编译期常量。

最小修改方案：把字符串改成 f-string 模板？不行——模板替换发生时机比 fetch 早。

干净方案：**adapter 不再做资产过滤，returning 所有 assets；service 拿 tag 后构造期望名、自己 filter**。这等价于把"命名约定"的知识从 adapter 移到 service——位置正确（adapter 不该知道业务命名）。

### 6.2 adapter 改动

`backend/app/integrations/github_releases.py`:

```python
from dataclasses import dataclass

@dataclass
class ReleaseAsset:
    name: str
    download_url: str


@dataclass
class ReleaseRaw:
    tag_name: str
    release_url: str
    notes: str
    assets: list[ReleaseAsset]   # 改：原来是 download_url: str | None


class GitHubReleaseError(Exception):
    ...


async def fetch_latest_release(owner: str, repo: str) -> ReleaseRaw:   # 签名变：去掉 asset_name
    """GET https://api.github.com/repos/{owner}/{repo}/releases/latest

    任何错误（网络异常、超时、HTTP 非 2xx、JSON 解析失败、缺 tag_name）→ 抛 GitHubReleaseError。
    成功时返回 ReleaseRaw，含全部 assets。命名匹配交给上层。
    """
    url = f"https://api.github.com/repos/{owner}/{repo}/releases/latest"
    # HTTP + JSON parse + tag_name 校验 部分保持不变（继续抛 GitHubReleaseError）：
    # - httpx.HTTPError → 'network: ...'
    # - resp.status_code != 200 → 'http {code}'
    # - resp.json() ValueError → 'invalid json: ...'
    # - 缺 tag_name 或非 str → 'missing tag_name'

    assets = [
        ReleaseAsset(name=a.get("name", ""), download_url=a.get("browser_download_url", ""))
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

### 6.3 service 改动

`backend/app/services/update_checker.py`:

```python
from packaging.version import InvalidVersion, Version

from app.integrations.github_releases import GitHubReleaseError, fetch_latest_release
from app.schemas.update import UpdateInfo

GITHUB_OWNER = "cookaihq"
GITHUB_REPO = "capcut_helper"
# ASSET_NAME 常量已移除；改用 _asset_name_for_tag()


def _asset_name_for_tag(tag: str) -> str:
    """根据 release tag 构造期望的资产名。tag 形如 'v0.2.0'。"""
    return f"capcut_helper-arm64-{tag}.dmg"


def _strip_v_prefix(tag: str) -> str:
    return tag[1:] if tag.startswith("v") else tag


def _is_newer(latest: str, current: str) -> bool:
    try:
        return Version(latest) > Version(current)
    except InvalidVersion:
        return latest != current


async def check_for_update(current_version: str) -> UpdateInfo:
    try:
        raw = await fetch_latest_release(GITHUB_OWNER, GITHUB_REPO)
    except GitHubReleaseError as e:
        return UpdateInfo(current_version=current_version, has_update=False, error=str(e))

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

### 6.4 schemas / API 端点 / 前端：无改动

`schemas/update.py::UpdateInfo` 形状不变（依然有 `download_url: str | None`）。
`api/update.py` 不变。
`frontend/src/components/UpdateBanner.jsx` 不变（已经处理 `download_url == null` 的 disabled 状态）。
`frontend/src/api/client.js` 不变。

这一层的稳定性是本次重构最大的好处——重构边界控制在 backend 内部，前端零改动。

## 7. 测试改动

### 7.1 `backend/tests/test_github_releases.py`

旧 5 个测试都依赖 `asset_name` 参数 + `ReleaseRaw.download_url`。改：

- 移除 `fetch_latest_release(...)` 调用的 `asset_name` 入参
- 断言改为 `raw.assets`（list 长度、每项 name/download_url）
- `test_fetch_latest_release_missing_asset` **改造**为 `test_fetch_latest_release_empty_assets`：response 中 `assets: []` → 返回的 `raw.assets == []`，其他字段照常。理由：原测试在测 adapter 的资产 filter 行为（已移到 service），不再适用本文件；改造后这条仍然守住「adapter 能正确处理 assets 字段为空数组的情况」这个 parse 边界，比删掉更有意义

### 7.2 `backend/tests/test_update_checker.py`

- `_release(...)` 工厂改为构造 `ReleaseRaw(assets=[ReleaseAsset(...)])` 而非 `download_url=...`
- 工厂默认资产名要跟 `_asset_name_for_tag(tag)` 匹配（这样默认情况下 download_url 找得到）
- 新增测试 `test_no_matching_asset_returns_none_download_url`：tag 是 `v0.2.0` 但 assets 里是 `capcut_helper-arm64-v0.2.0.zip`（错后缀） → `info.has_update=True`，`info.download_url is None`
- 现有 7 个测试断言保持，逻辑无大改

### 7.3 `backend/tests/test_update_api.py`

`_VALID_RESPONSE` 里的 asset name 要跟 `_asset_name_for_tag("v0.2.0")` 匹配（即 `capcut_helper-arm64-v0.2.0.dmg`），不然 happy-path 测试会跑到「资产名不匹配」分支拿到 `download_url=None`。

### 7.4 grep 校验

实现完成后跑：

```bash
grep -rn 'capcut_helper\.zip' backend/ frontend/ scripts/ README.md
```

应当无输出（历史 spec/plan 文档不在 grep 范围内）。

## 8. v0.1.0 处理

按删了重发流程，分两步：

### 8.1 删除旧的

```bash
# 1. 删 GitHub release（API 调用，需要 token）
RELEASE_ID=$(curl -s -H "Authorization: Bearer $(cat .github-token)" \
  https://api.github.com/repos/cookaihq/capcut_helper/releases/tags/v0.1.0 | \
  python3 -c "import sys, json; print(json.load(sys.stdin)['id'])")
curl -X DELETE -H "Authorization: Bearer $(cat .github-token)" \
  "https://api.github.com/repos/cookaihq/capcut_helper/releases/$RELEASE_ID"

# 2. 删远端 tag
git push origin :refs/tags/v0.1.0

# 3. 删本地 tag
git tag -d v0.1.0
```

验证：
- `git ls-remote --tags origin | grep v0.1.0` 无输出
- `curl -s https://api.github.com/repos/cookaihq/capcut_helper/releases/tags/v0.1.0` 返回 `{"message":"Not Found",...}`

### 8.2 实现所有改动 → 重发

实现 §3-7 → commit → `bash scripts/release.sh` → 新 v0.1.0 release 自带 `capcut_helper-arm64-v0.1.0.dmg`。

## 9. README 改动

### 9.1 「发版」小节

文件名相关引用从 `capcut_helper.zip` 改为 `capcut_helper-arm64-v0.1.0.dmg`。「硬编码约定」那段说明改：

> **版本号约定**：tag 必须 `v` + SemVer（`update_checker._strip_v_prefix` 按这个格式解析）；
> dmg 资产名必须是 `capcut_helper-arm64-v<version>.dmg`（`scripts/build_mac.sh` 产物名 + `services/update_checker.py::_asset_name_for_tag()` 按 tag 模板构造该名）。脚本已硬编码这两个约定，按它来就行。

### 9.2 「打包成 .app 分发」小节

产物清单从 zip 改为 dmg。

### 9.3 「分发给同事」小节

操作步骤从「解压 zip → 拖 app」改为：

> 把 `dist/capcut_helper-arm64-v<version>.dmg` 发给对方，请对方：
>
> 1. 双击 dmg 挂载
> 2. 把 `capcut_helper.app` 拖到弹出窗口里的 `Applications` 软链上
> 3. **首次打开**：右键 → 打开 → 弹窗里再点「打开」（绕 Gatekeeper）
> 4. 后续步骤同前（草稿目录授权、设置）

## 10. 包装 spec 增量修订

修改 `docs/superpowers/specs/2026-05-15-capcut-helper-packaging-design.md`:

- §2.1：明确产物从 zip 切到 dmg；构建脚本产物名带架构 + 版本号
- §2.2：删除「DMG / 安装器」这一条 non-goal 项（已经做了）
- §3 工具与产物：加 hdiutil 这一行；产物路径从 `dist/capcut_helper.zip` 改为 `dist/capcut_helper-arm64-v<version>.dmg`

不要新增章节，只就地修订。

## 11. 验收标准

1. `bash scripts/build_mac.sh` 跑通，产出 `dist/capcut_helper-arm64-v0.1.0.dmg`
2. `open dist/capcut_helper-arm64-v0.1.0.dmg` 能挂载、看到 `.app` 和 `Applications` 软链
3. `cd backend && uv run pytest` 全绿（数量比之前多 1：新增的「资产名不匹配」用例）
4. 前端 `npm run test` 全绿（前端无变化，应当零回归）
5. `grep -rn 'capcut_helper\.zip' backend/ frontend/ scripts/ README.md` 无输出
6. 旧 v0.1.0 已从 GitHub 删除（`https://github.com/cookaihq/capcut_helper/releases/tag/v0.1.0` 404 直到重发）
7. 重发后 `https://github.com/cookaihq/capcut_helper/releases/tag/v0.1.0` 资产仅含 `capcut_helper-arm64-v0.1.0.dmg`
8. 把 `__version__` 临时改成 `0.1.1` 跑构建，产出文件名 `capcut_helper-arm64-v0.1.1.dmg`（验证版本号联动），完后还原 `0.1.0`

## 12. 已知后续项（不在本 spec）

- universal2 / Intel Mac：等需求出现再扩展 `build_mac.sh` 用 `lipo`、`_asset_name_for_tag` 加多平台变体
- Windows .exe / .msi：spec §2.2 一直是 non-goal
- DMG 美化（背景图 / 窗口布局）：需要用户反馈说 DMG 不够直观再做
