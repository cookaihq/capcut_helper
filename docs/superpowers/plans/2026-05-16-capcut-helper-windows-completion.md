# capcut_helper Windows 完工 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 Windows 端从「能打 zip 但没在 Windows 机器上端到端跑过 + 没发版脚本 + 草稿目录探测不全」收尾到「与 Mac 完全对称的可分发 (.exe 安装包)、可自动发版、可探测自定义草稿目录」状态。

**Architecture:** 按 A → D → C → B 顺序串行：A 先在 Windows 机器跑通现有 zip 路径以暴露 PyInstaller hidden import / 原生 DLL 问题；D 是 `bridge.py` 一个独立的 spike + 实现；C 替换分发格式 zip → Inno Setup `.exe`，连带改 `update_checker._asset_name_for_tag` + `build_win.ps1` + README；B 新增 `release_win.ps1` 镜像 `release.sh` 逻辑，同时把 `release.sh` 重命名为 `release_mac.sh` 并加 release reuse 逻辑让两端互不阻塞。

**Tech Stack:** Python 3.13, PyInstaller, Inno Setup 6, PowerShell 5.1+, pywebview, FastAPI, pystray, pytest（后端测试），git (GitHub API via curl / Invoke-RestMethod)。

**Spec：** `docs/superpowers/specs/2026-05-16-capcut-helper-windows-completion-design.md`

---

## 文件结构

**新增**：
- `scripts/capcut_helper.iss` — Inno Setup 编译脚本，产 `capcut_helper-x64-v<version>.exe` 安装包
- `scripts/release_win.ps1` — Windows 发版自动化（镜像 release.sh，PowerShell）

**重命名**：
- `scripts/release.sh` → `scripts/release_mac.sh`

**修改**：
- `backend/capcut_helper_win.spec` — Task 1 期间按打包报错增补 hidden imports / binaries
- `backend/app/native/bridge.py` — D 实现 `_read_windows_custom_draft_path` + `detect_draft_root` Windows 分支（仅当 spike 成功）
- `backend/tests/test_native_bridge.py` — D 新增 3 个 Windows 自定义路径 case（仅当 spike 成功）
- `backend/app/services/update_checker.py` — C 把 Win 资产名从 `.zip` 改为 `.exe`
- `backend/tests/test_update_checker.py` — C 同步资产名测试期望值
- `scripts/build_win.ps1` — C 删 `Compress-Archive`、加 ISCC.exe 调用、版本号源从 `git describe` 改为 `__version__` 解析
- `scripts/release_mac.sh` — B 加 release 复用逻辑（先 GET /releases/tags 再决定 create vs reuse），加 remote-tag 探测后跳 push
- `README.md` — C + B + D + A 多处更新
- `backend/app/__init__.py` — Task 12 bump 到 `0.1.3`

---

## Task 1：A — 在 Windows 机器上端到端验证现有 zip 打包

**Files:**
- Run: `scripts/build_win.ps1`
- Modify (if needed): `backend/capcut_helper_win.spec`

本 task 不产生新代码（除非打包暴露需要补的 hidden import / binary）。目标是把 baseline 跑稳，C 才能在稳的地基上换 Inno Setup。

- [ ] **Step 1.1：跑现有 build_win.ps1**

```powershell
pwsh -ExecutionPolicy Bypass -File scripts/build_win.ps1
```

Expected：
- 3 个阶段（前端构建 / PyInstaller / Compress-Archive）按序无错
- 产出 `dist/capcut_helper/capcut_helper.exe` 和 `dist/capcut_helper-x64-v0.1.2.zip`（或 `v0.0.0-dev.zip`，取决于本地是否有 tag）

若 PyInstaller 阶段失败：根据报错（典型：`ModuleNotFoundError`、`hidden import not found`），跳到 Step 1.4 补 spec。

- [ ] **Step 1.2：直接双击未压缩的 .exe**

打开资源管理器到 `dist/capcut_helper/`，双击 `capcut_helper.exe`。

Expected：主窗口弹出。若窗口白屏，对照 spec §4.2 第 2 项确认 WebView2 Runtime；若启动报「丢失 VCRUNTIME140.dll」，对照 spec §11 第 1 项装 VC++ Redistributable。

- [ ] **Step 1.3：跑 spec §4.1 的 10 项手动测试矩阵**

按顺序勾选：

```
[ ] 双击 .exe → 主窗口 + 任务栏 + 托盘图标
[ ] 三个 Tab（活动 / 草稿 / 设置）能切
[ ] 「设置 → 选择目录」能弹 Windows 文件夹选择对话框
[ ] 「设置 → 自动探测」返回 %LOCALAPPDATA%\JianyingPro\... 默认路径
[ ] 点窗口 × / Alt+F4 → 窗口消失、任务栏 / Alt+Tab 消失、托盘图标保留
[ ] 关窗后 curl http://127.0.0.1:<port>/api/v1/health 仍 200
[ ] 托盘左键 → 窗口出现
[ ] 托盘右键 → 菜单含 v0.1.2 / 打开面板 / 检查更新 / 退出
[ ] 菜单「退出」→ 全消失、端口释放（netstat -ano | findstr :<port> 应无）、托盘图标无 zombie
[ ] POST 一个真实 timeline spec 到 /api/v1/draft（用 curl 或 ai-canvas），草稿能完整生成
[ ] reveal_in_os("D:\\some\\existing\\path") → 资源管理器弹出且选中该项
```

`<port>` 从启动日志 / 状态栏「检查更新」菜单旁的版本号附近 / 直接 `netstat -ano | findstr LISTENING | findstr 952` 判断（默认范围 9527+）。

- [ ] **Step 1.4：发现问题就地修（典型 fixup）**

典型场景与修法：

**场景 A：启动报 `ModuleNotFoundError: <module>`**

修 `backend/capcut_helper_win.spec` 的 `hiddenimports`，追加该模块：

```python
hiddenimports=pywebview_hiddenimports + [
    "pystray._win32",
    "PIL._tkinter_finder",
    "<新发现的模块>",     # ← 加在这里
],
```

**场景 B：草稿生成报「找不到 libmediainfo.dll」**

`pymediainfo` 的 DLL 通常装在 `<venv>\Lib\site-packages\pymediainfo\` 下。`capcut_helper_win.spec` 的 `Analysis(...)` 段加 `binaries`：

```python
import os
import pymediainfo
_mediainfo_dir = os.path.dirname(pymediainfo.__file__)

a = Analysis(
    ["app/main.py"],
    pathex=[],
    binaries=pywebview_binaries + [
        (os.path.join(_mediainfo_dir, "MediaInfo.dll"), "pymediainfo"),  # 路径以实际为准
    ],
    ...
)
```

实际 DLL 名 / 位置以 `pymediainfo` 包内文件为准（可能是 `MediaInfo.dll` 或 `libmediainfo.dll`）。

**场景 C：草稿生成报模板找不到（pyJianYingDraft 资源）**

把 `collect_data_files("pyJianYingDraft")` 替换为 `collect_all("pyJianYingDraft")`：

```python
from PyInstaller.utils.hooks import collect_all, collect_data_files

pywebview_datas, pywebview_binaries, pywebview_hiddenimports = collect_all("webview")
jianying_datas, jianying_binaries, jianying_hiddenimports = collect_all("pyJianYingDraft")  # ← 改这行

a = Analysis(
    ["app/main.py"],
    pathex=[],
    binaries=pywebview_binaries + jianying_binaries,
    datas=[
        ("../frontend/dist", "frontend/dist"),
        *pywebview_datas,
        *jianying_datas,
    ],
    hiddenimports=pywebview_hiddenimports + jianying_hiddenimports + [...],
    ...
)
```

每修一次重跑 Step 1.1 + 1.2 + 1.3 失败的那项。

- [ ] **Step 1.5：commit 每个 fixup**

每次 spec 修改单独 commit，message 形如：

```bash
git add backend/capcut_helper_win.spec
git commit -m "build(capcut_helper): win spec 补 <模块名> hidden import"
```

或：

```bash
git commit -m "build(capcut_helper): win spec 显式声明 libmediainfo binary"
```

- [ ] **Step 1.6：记录 A 完成状态**

把 Step 1.3 矩阵全勾后，**不需要 commit**——把测试结果记在最终 PR / merge commit 的描述里：

```
A 端到端验证通过：
- Host: Windows 11 x64 build <build号>
- Commit: <最后一个 fixup 的 SHA，或如果没 fixup 就是 Task 1 开始时的 HEAD SHA>
- 10 项测试矩阵全勾
```

---

## Task 2：D — Spike 剪映 Windows 版自定义草稿目录存储位置

**Files:** 无代码改动；输出是一段调研结论。

- [ ] **Step 2.1：确认剪映 Windows 版已安装**

```powershell
Get-ChildItem "$env:LOCALAPPDATA\JianyingPro" -ErrorAction SilentlyContinue | Select-Object -First 5
```

Expected：列出至少几个子目录（如 `User Data` / `app`）。若空 → 剪映 Win 版没装，跳到 Step 2.5（defer）。

- [ ] **Step 2.2：在剪映里设置自定义草稿路径**

手动：
1. 启动剪映
2. 设置 → 草稿位置 → 改为已知路径，例如 `D:\test_drafts`（先在 D 盘建该目录）
3. 应用 / 保存
4. **关闭剪映**（让它把配置 flush 到磁盘）

- [ ] **Step 2.3：搜索候选位置**

```powershell
# 候选 1：LOCALAPPDATA 下任意文件含 "test_drafts" 字符串
Get-ChildItem -Path "$env:LOCALAPPDATA\JianyingPro" -Recurse -File -ErrorAction SilentlyContinue |
    Select-String -Pattern "test_drafts" -List -ErrorAction SilentlyContinue |
    Select-Object Path, LineNumber

# 候选 2：APPDATA 下同
Get-ChildItem -Path "$env:APPDATA\JianyingPro" -Recurse -File -ErrorAction SilentlyContinue |
    Select-String -Pattern "test_drafts" -List -ErrorAction SilentlyContinue |
    Select-Object Path, LineNumber

# 候选 3：HKCU 注册表
reg query HKCU\Software /s /f "test_drafts" 2>$null

# 候选 4：HKLM（罕见但试一下）
reg query HKLM\Software /s /f "test_drafts" 2>$null
```

记录任何命中的 Path / RegKey + Pattern。

- [ ] **Step 2.4：（若 Step 2.3 全空）用 ProcMon 兜底**

1. 从 https://learn.microsoft.com/en-us/sysinternals/downloads/procmon 下载 ProcMon
2. 启动 ProcMon，Filter → Process Name = `JianyingPro.exe`、Operation = `WriteFile` OR `RegSetValue`
3. 启动剪映、改另一个自定义路径（如 `D:\test_drafts2`）、应用、关剪映
4. 在 ProcMon 里看 JianyingPro 写了哪些 Path/RegKey
5. 对其中可疑的几个文件，关剪映后 `Get-Content` 看是否含路径字符串

- [ ] **Step 2.5：分支决策**

**Case 1 — 找到了**（典型例子：`%LOCALAPPDATA%\JianyingPro\User Data\Preferences\Some.json` 的 `draftPath` 字段）：
- 记录 `<具体子路径>` 和 `<具体字段>`，继续 Task 3

**Case 2 — 没找到 / 剪映 Win 版没装**：
- 在 spec 末尾追加「实现笔记」（直接在文件末尾加一节）：
  ```markdown
  ## 实现笔记

  ### Task 2 D spike 结果（YYYY-MM-DD）
  尝试候选位置：%LOCALAPPDATA%\JianyingPro 文件搜索 / %APPDATA%\JianyingPro / HKCU 注册表 / ProcMon 监控。
  结论：[未找到 / 剪映未安装] → defer `_read_windows_custom_draft_path` 实现，保留 `bridge.py` 现有 TODO + README 已知限制那条。
  ```
- commit spec 修改：
  ```bash
  git add docs/superpowers/specs/2026-05-16-capcut-helper-windows-completion-design.md
  git commit -m "docs(capcut_helper): Task 2 D spike defer 实现 — 未定位到剪映 Win 配置存储"
  ```
- 跳到 Task 4（D 整体 defer，Task 3 不做）

---

## Task 3：D — 实现 `_read_windows_custom_draft_path`（仅当 Task 2 找到）

**Files:**
- Modify: `backend/app/native/bridge.py`
- Modify: `backend/tests/test_native_bridge.py`
- Modify: `README.md`

下面所有代码块中 `<具体子路径>` 和 `<具体字段>` 用 Task 2 的发现替换。示例假设结论是 `%LOCALAPPDATA%\JianyingPro\User Data\Preferences\draft.json` 的 `customPath` 字段（**真值以 spike 输出为准**）。

- [ ] **Step 3.1：写失败测试 — happy path**

在 `backend/tests/test_native_bridge.py` 末尾追加：

```python
import json
import sys

import pytest


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")
def test_read_windows_custom_draft_path_happy(monkeypatch, tmp_path):
    """配置文件存在且含合法路径 → 返回该路径。"""
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    # 创建 spike 调研到的配置文件结构
    config_dir = tmp_path / "JianyingPro" / "User Data" / "Preferences"   # ← spike 输出
    config_dir.mkdir(parents=True)
    draft_dir = tmp_path / "custom_drafts"
    draft_dir.mkdir()
    (config_dir / "draft.json").write_text(                              # ← spike 输出
        json.dumps({"customPath": str(draft_dir)})                       # ← spike 输出
    )

    from app.native.bridge import _read_windows_custom_draft_path
    assert _read_windows_custom_draft_path() == str(draft_dir)
```

- [ ] **Step 3.2：跑测试确认失败**

```bash
cd backend && uv run pytest tests/test_native_bridge.py::test_read_windows_custom_draft_path_happy -v
```

Expected: `ImportError: cannot import name '_read_windows_custom_draft_path'`

注意：此测试只在 Windows 上跑（`@pytest.mark.skipif`），Mac 上 skip。

- [ ] **Step 3.3：实现 `_read_windows_custom_draft_path`**

在 `backend/app/native/bridge.py` 顶部 import 区加（若已有则跳过）：

```python
import json
import os
```

在 `_read_macos_custom_draft_path` 函数下方（约 line 36 后）加：

```python
def _read_windows_custom_draft_path() -> Optional[str]:
    """读剪映 Win 版自定义草稿目录配置；任何异常返回 None 让上层回退到默认。"""
    localappdata = os.environ.get("LOCALAPPDATA")
    if not localappdata:
        return None
    # 路径与字段名以 spike 调研结果为准
    config_path = Path(localappdata) / "JianyingPro" / "User Data" / "Preferences" / "draft.json"
    try:
        with config_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, PermissionError, json.JSONDecodeError, ValueError, KeyError, OSError):
        return None
    value = data.get("customPath")
    if not isinstance(value, str) or not value:
        return None
    return value if Path(value).is_dir() else None
```

> 备注：若 Task 2 的结论是注册表而非 JSON，把 `with config_path.open(...)` 段换成 `winreg`：
> ```python
> import winreg
> try:
>     with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\JianyingPro") as key:
>         value, _ = winreg.QueryValueEx(key, "<字段名>")
> except (FileNotFoundError, OSError):
>     return None
> ```

- [ ] **Step 3.4：跑测试确认通过**

```bash
cd backend && uv run pytest tests/test_native_bridge.py::test_read_windows_custom_draft_path_happy -v
```

Expected: PASS

- [ ] **Step 3.5：写失败测试 — 文件不存在 & JSON 损坏**

在 `test_native_bridge.py` 继续追加：

```python
@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")
def test_read_windows_custom_draft_path_missing_file(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    from app.native.bridge import _read_windows_custom_draft_path
    assert _read_windows_custom_draft_path() is None


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")
def test_read_windows_custom_draft_path_invalid_json(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    config_dir = tmp_path / "JianyingPro" / "User Data" / "Preferences"
    config_dir.mkdir(parents=True)
    (config_dir / "draft.json").write_text("not a json {{{")

    from app.native.bridge import _read_windows_custom_draft_path
    assert _read_windows_custom_draft_path() is None
```

- [ ] **Step 3.6：跑测试确认通过（实现已覆盖）**

```bash
cd backend && uv run pytest tests/test_native_bridge.py -v
```

Expected: 3 个新测试全 PASS（实现的 `except` 已覆盖这两种异常）。Mac 上跑会全 skip。

- [ ] **Step 3.7：把 Windows 分支接进 `detect_draft_root`**

修改 `backend/app/native/bridge.py` 的 `detect_draft_root` 方法（约 line 59-70），替换为：

```python
def detect_draft_root(self) -> Optional[str]:
    """优先读剪映配置里的自定义草稿目录，读不到则回退到平台默认目录。"""
    if sys.platform == "darwin":
        custom = _read_macos_custom_draft_path()
        if custom is not None:
            return custom
    elif sys.platform == "win32":
        custom = _read_windows_custom_draft_path()
        if custom is not None:
            return custom
    relative = _DRAFT_ROOT_RELATIVE.get(sys.platform)
    if relative is None:
        return None
    candidate = Path.home() / relative
    return str(candidate) if candidate.is_dir() else None
```

同时删除 line 65-66 的 TODO 注释：

```python
# TODO: Windows 端剪映把自定义草稿目录存在哪个文件目前未确认，暂只回退默认路径
```

- [ ] **Step 3.8：跑全部 bridge 测试确认通过**

```bash
cd backend && uv run pytest tests/test_native_bridge.py -v
```

Expected: 全 PASS（含已有 mac 测试 + 3 个新 win 测试）

- [ ] **Step 3.9：更新 README「已知限制」**

打开 `README.md`，找到第 116 行附近的这条：

```markdown
- Windows 剪映自定义草稿目录未实现自动探测：若你在剪映设置里改过草稿目录，需在 capcut_helper「设置」标签手动选择（macOS 端已支持，见 `app/native/bridge.py` 实测说明）。
```

**整行删除**。

- [ ] **Step 3.10：commit**

```bash
git add backend/app/native/bridge.py backend/tests/test_native_bridge.py README.md
git commit -m "feat(capcut_helper): Windows 剪映自定义草稿目录探测 — 读 <Task 2 调研到的位置>"
```

commit message 里 `<...>` 替成具体描述，例如「读 %LOCALAPPDATA%\JianyingPro\User Data\Preferences\draft.json::customPath」。

---

## Task 4：C — 创建 `scripts/capcut_helper.iss`

**Files:**
- Create: `scripts/capcut_helper.iss`

- [ ] **Step 4.1：生成 AppId GUID**

```powershell
[guid]::NewGuid().ToString().ToUpper()
```

Expected: 输出一个形如 `8B4C3A7F-9E2D-4B6A-8F1C-5D7E9A0B2C4F` 的 GUID。**复制保存**——这就是写进 .iss 的 AppId，**永远别再生成新的**。

- [ ] **Step 4.2：创建 `scripts/capcut_helper.iss`**

用 Step 4.1 的 GUID 替换下面的 `<GUID>` 占位：

```ini
[Setup]
AppId={{<GUID>}
AppName=capcut_helper
AppVersion={#VERSION}
AppPublisher=cookaihq
DefaultDirName={localappdata}\Programs\capcut_helper
DefaultGroupName=capcut_helper
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=capcut_helper-x64-v{#VERSION}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
UninstallDisplayIcon={app}\capcut_helper.exe

[Files]
Source: "..\dist\capcut_helper\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\capcut_helper"; Filename: "{app}\capcut_helper.exe"
Name: "{group}\卸载 capcut_helper"; Filename: "{uninstallexe}"

[Run]
Filename: "{app}\capcut_helper.exe"; Description: "立即启动 capcut_helper"; Flags: nowait postinstall skipifsilent
```

注意 `AppId={{<GUID>}` —— Inno Setup 语法里 `{{` 转义成单个 `{`，结果实际值是 `{<GUID>}`。这是 Inno Setup 的强制格式，参考 https://jrsoftware.org/ishelp/index.php?topic=setup_appid 。

- [ ] **Step 4.3：visual 校验**

```bash
cat scripts/capcut_helper.iss
```

确认：
- `AppId={{<具体 GUID>}` 而非 `{{<GUID>}`
- `OutputBaseFilename=capcut_helper-x64-v{#VERSION}` 末尾**没有** `.exe`（Inno Setup 自动加扩展名）
- `Source: "..\dist\capcut_helper\*"` 用反斜杠

- [ ] **Step 4.4：commit**

```bash
git add scripts/capcut_helper.iss
git commit -m "build(capcut_helper): 新增 Inno Setup 安装包脚本"
```

---

## Task 5：C — 改造 `scripts/build_win.ps1` 接 ISCC.exe

**Files:**
- Modify: `scripts/build_win.ps1`

- [ ] **Step 5.1：整个替换 `scripts/build_win.ps1`**

```powershell
# capcut_helper Windows x64 构建脚本：PyInstaller onedir + Inno Setup 安装包。
# 用法（在 PowerShell 中、Windows 机器上）:
#   cd capcut_helper
#   pwsh -ExecutionPolicy Bypass -File scripts/build_win.ps1
#
# 前置：node + npm + Python 3.11+ + uv + Inno Setup 6 已安装。
# Inno Setup 6: https://jrsoftware.org/isdl.php
# 若 ISCC.exe 不在默认位置，设环境变量 ISCC_PATH 指向 ISCC.exe。

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot/..

# ---------- 读版本号（来源唯一：backend/app/__init__.py::__version__） ----------
$versionLine = Select-String -Path backend/app/__init__.py -Pattern '"(\d+\.\d+\.\d+)"' | Select-Object -First 1
if (-not $versionLine) {
    throw "无法从 backend/app/__init__.py 解析 __version__"
}
$version = $versionLine.Matches.Groups[1].Value
$installerName = "capcut_helper-x64-v$version.exe"

# ---------- 定位 ISCC.exe ----------
$iscc = $env:ISCC_PATH
if (-not $iscc -or -not (Test-Path $iscc)) {
    $candidate = "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
    if (Test-Path $candidate) { $iscc = $candidate }
}
if (-not $iscc) {
    $cmd = Get-Command ISCC -ErrorAction SilentlyContinue
    if ($cmd) { $iscc = $cmd.Source }
}
if (-not $iscc) {
    throw "找不到 ISCC.exe。装 Inno Setup 6 (https://jrsoftware.org/isdl.php)，或设环境变量 ISCC_PATH 指向 ISCC.exe"
}

Write-Host "-> 1/3 安装/构建前端"
Push-Location frontend
npm install
npm run build
Pop-Location

Write-Host "-> 2/3 PyInstaller 打包 onedir"
Push-Location backend
uv run pyinstaller --clean --noconfirm `
    --distpath=../dist --workpath=../build `
    capcut_helper_win.spec
Pop-Location

Write-Host "-> 3/3 Inno Setup 编译安装包"
& $iscc /DVERSION=$version scripts/capcut_helper.iss
if ($LASTEXITCODE -ne 0) {
    throw "ISCC.exe 编译失败，退出码 $LASTEXITCODE"
}

Write-Host ""
Write-Host "构建完成："
Write-Host "  EXE 目录:   $(Resolve-Path dist/capcut_helper)"
Write-Host "  安装包:     $(Resolve-Path "dist/$installerName")"
```

主要变更：
- 头部加版本号解析（解析 `backend/app/__init__.py::__version__`），不再 `git describe`
- 加 ISCC.exe 三段式定位
- 步骤 3 从 `Compress-Archive` 改为 `& $iscc /DVERSION=$version scripts/capcut_helper.iss`
- 末行打印的产物从 `.zip` 改为 `.exe`

- [ ] **Step 5.2：跑一次本地构建验证**

```powershell
pwsh -ExecutionPolicy Bypass -File scripts/build_win.ps1
```

Expected：
- 3 个阶段无错
- 末行打印 `安装包: <绝对路径>\dist\capcut_helper-x64-v0.1.2.exe`
- `Test-Path "dist/capcut_helper-x64-v0.1.2.exe"` 返回 `True`

若 ISCC 编译报「文件未找到」之类的错，检查 .iss 里的 Source 路径是否正确（相对 .iss 文件所在目录）。

- [ ] **Step 5.3：双击安装包验证安装流程**

```powershell
Start-Process "dist/capcut_helper-x64-v0.1.2.exe"
```

跟着向导：
- SmartScreen 拦截 → 「更多信息」→「仍要运行」
- 安装位置默认 `C:\Users\<user>\AppData\Local\Programs\capcut_helper`
- 完成 → 勾「立即启动 capcut_helper」→ 点 Finish

Expected：
- 安装无报错
- 主窗口弹出
- 开始菜单出现「capcut_helper」+「卸载 capcut_helper」两个快捷方式
- 重新跑 Task 1 §4.1 矩阵中的关键几项（双击启动 / 关窗 / 托盘菜单 / 退出）确认安装包版本行为与裸 .exe 一致

- [ ] **Step 5.4：验证卸载干净**

从「设置 → 应用」找 capcut_helper → 卸载 → 完成。

Expected：
- 开始菜单条目消失
- `Test-Path "$env:LOCALAPPDATA\Programs\capcut_helper"` 返回 `False`

- [ ] **Step 5.5：commit**

```bash
git add scripts/build_win.ps1
git commit -m "build(capcut_helper): build_win.ps1 接 ISCC.exe — zip → Inno Setup 安装包"
```

---

## Task 6：C — `update_checker._asset_name_for_tag` 改返 `.exe`

**Files:**
- Modify: `backend/app/services/update_checker.py:18`
- Modify: `backend/tests/test_update_checker.py`

- [ ] **Step 6.1：改测试期望值（先红）**

打开 `backend/tests/test_update_checker.py`，找到 `test_asset_name_for_tag_on_win32`，把期望值 `.zip` 改成 `.exe`：

```python
def test_asset_name_for_tag_on_win32(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    assert _asset_name_for_tag("v0.2.0") == "capcut_helper-x64-v0.2.0.exe"
```

- [ ] **Step 6.2：跑测试确认失败**

```bash
cd backend && uv run pytest tests/test_update_checker.py::test_asset_name_for_tag_on_win32 -v
```

Expected: FAIL，AssertionError 显示 actual 是 `.zip`、expected 是 `.exe`

- [ ] **Step 6.3：改实现**

修改 `backend/app/services/update_checker.py` 第 18 行：

```python
if sys.platform == "win32":
    return f"capcut_helper-x64-{tag}.exe"
```

- [ ] **Step 6.4：跑全部 update_checker 测试**

```bash
cd backend && uv run pytest tests/test_update_checker.py -v
```

Expected: 所有测试 PASS（darwin 测试不变、win32 测试现在符合新实现、unsupported_platform 不变）

- [ ] **Step 6.5：commit**

```bash
git add backend/app/services/update_checker.py backend/tests/test_update_checker.py
git commit -m "feat(capcut_helper): Windows update 资产名 .zip → .exe（对齐 Inno Setup 安装包）"
```

---

## Task 7：C — README「Windows 分发」+「发版者一次性准备」改写

**Files:**
- Modify: `README.md`

- [ ] **Step 7.1：替换「Windows 分发」整章节**

找到 `## 分发给同事` 下的 `### Windows 分发` 子章节（约 line 103-110），整个替换为：

```markdown
### Windows 分发

把 `dist/capcut_helper-x64-v<version>.exe` 安装包发给对方，请对方按以下步骤：

1. 双击 `capcut_helper-x64-v<version>.exe`
2. **首次打开**：因为未做 EV 证书签名，Windows SmartScreen 会拦截，点「更多信息」→「仍要运行」
3. 安装向导：选位置（默认 `%LOCALAPPDATA%\Programs\capcut_helper`，不需管理员）→ Next → 完成；可勾「立即启动」
4. 之后从开始菜单找「capcut_helper」启动
5. **系统运行时依赖**（PyInstaller 已把 Python 3.13 打进 bundle，**不需装 Python**；但下面两个 Windows 系统运行时需要在）：
   - **WebView2 Runtime**：Win11 / 近一年 Win10 默认预装；若启动后窗口白屏，从 https://developer.microsoft.com/microsoft-edge/webview2/ 下「Evergreen Standalone Installer」装一次
   - **Visual C++ 2015-2022 Redistributable (x64)**：绝大多数 Windows 机器自带；若启动报「丢失 VCRUNTIME140.dll」，从 https://aka.ms/vs/17/release/vc_redist.x64.exe 下载安装
6. 启动后第一次进 GUI，按「设置」标签里的「自动探测」找剪映草稿目录，或手动选择

卸载：「设置 → 应用 → capcut_helper → 卸载」，或开始菜单里点「卸载 capcut_helper」。
```

- [ ] **Step 7.2：「一次性准备」加 Windows 发版者子项**

找到 `### 一次性准备（只做一次）` 章节（约 line 36-42），在末尾加新子项 3：

```markdown
3. **发 Windows 版前**：本机装 [Inno Setup 6](https://jrsoftware.org/isdl.php)（免费），`scripts/build_win.ps1` 自动定位 `C:\Program Files (x86)\Inno Setup 6\ISCC.exe`。如装在非默认位置，设环境变量 `ISCC_PATH` 指向 ISCC.exe。
```

- [ ] **Step 7.3：commit**

```bash
git add README.md
git commit -m "docs(capcut_helper): README Windows 分发改为 Inno Setup 安装包步骤 + 运行时依赖说明"
```

---

## Task 8：B — `scripts/release.sh` 重命名为 `scripts/release_mac.sh`

**Files:**
- Rename: `scripts/release.sh` → `scripts/release_mac.sh`

- [ ] **Step 8.1：git mv**

```bash
git mv scripts/release.sh scripts/release_mac.sh
```

- [ ] **Step 8.2：检查脚本内部是否引用自己的名字**

```bash
grep -n "release.sh" scripts/release_mac.sh
```

Expected：仅匹配一行（行 11 的 `.github-token` 注释里有 `scripts/release.sh` 引用旧名）。

如有匹配，把那行注释里的 `scripts/release.sh` 改为 `scripts/release_mac.sh`：

打开 `scripts/release_mac.sh` 第 11 行附近：

```bash
#   1. `git remote get-url origin` 指向 GitHub 仓库（HTTPS 远端，无论凭据如何）
#   2. 项目根存在 `.github-token` 文件，内容是有 `contents:write` 权限的 PAT
#      （已 .gitignore；生成路径：GitHub Settings → Developer settings → Personal access tokens）
```

如该文件里其他位置（如顶部注释 `用法` 段）也提了 `scripts/release.sh`，一并改成 `scripts/release_mac.sh`。

`.gitignore` 里 `# scripts/release.sh 用的 GitHub PAT` 这行也改：

```
# scripts/release_mac.sh 用的 GitHub PAT（含发版权限，泄漏即被滥用）
.github-token
```

- [ ] **Step 8.3：commit**

```bash
git add scripts/release_mac.sh .gitignore
git commit -m "build(capcut_helper): release.sh → release_mac.sh（为 release_win.ps1 让出对称命名空间）"
```

---

## Task 9：B — `release_mac.sh` 加 release 复用逻辑

**Files:**
- Modify: `scripts/release_mac.sh`

让 Mac 端在 release 已存在时复用而非报错，使 Win 先发 / Mac 先发都能成立。

- [ ] **Step 9.1：把「remote tag 已存在」从「致命错」改成「跳过 push tag」**

找 `scripts/release_mac.sh` 中这段（约 line 62-65）：

```bash
if git ls-remote --tags origin "refs/tags/$TAG" 2>/dev/null | grep -q "$TAG"; then
  echo "✗ origin 上已有 tag $TAG（这个版本号已发过）。bump __version__ 后再来"
  exit 1
fi
```

替换为：

```bash
REMOTE_TAG_EXISTS=0
if git ls-remote --tags origin "refs/tags/$TAG" 2>/dev/null | grep -q "$TAG"; then
  echo "→ origin 上已有 tag $TAG（可能 Windows 端已发过），跳过 push tag、复用已存在的 release"
  REMOTE_TAG_EXISTS=1
fi
```

- [ ] **Step 9.2：让 push tag 步骤跳过 remote 已存在的情形**

找 `git push origin "$TAG"` 那段（约 line 99-104）：

```bash
echo "→ git push main"
git push origin main
echo "→ git tag $TAG"
git tag "$TAG"
echo "→ git push tag"
git push origin "$TAG"
```

改为：

```bash
echo "→ git push main"
git push origin main
echo "→ git tag $TAG"
git tag "$TAG"
if [ "$REMOTE_TAG_EXISTS" -eq 0 ]; then
  echo "→ git push tag"
  git push origin "$TAG"
else
  echo "→ 跳过 push tag（remote 已有）"
fi
```

- [ ] **Step 9.3：让创建 release 改为「先 GET 再决定」**

找 `# ---------- 创建 GitHub release ----------` 那段（约 line 106-136）整段，替换为：

```bash
# ---------- 找或建 GitHub release ----------

echo "→ 查询是否已有 release（可能 Windows 端先发过）"
EXISTING_RELEASE=$(curl -sf -H "Authorization: Bearer $TOKEN" \
                            -H "Accept: application/vnd.github+json" \
                            "https://api.github.com/repos/$REPO_PATH/releases/tags/$TAG" 2>/dev/null) || EXISTING_RELEASE=""

if [ -n "$EXISTING_RELEASE" ]; then
  echo "→ 复用已存在 release"
  RELEASE_JSON="$EXISTING_RELEASE"
else
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
fi

UPLOAD_URL=$(python3 - <<PY
import json
data = json.loads('''$RELEASE_JSON''')
print(data["upload_url"].split("{")[0])
PY
)

if [ -z "$UPLOAD_URL" ]; then
  echo "✗ release 响应里没拿到 upload_url，响应原文："
  echo "$RELEASE_JSON"
  exit 1
fi
```

- [ ] **Step 9.4：visual review**

```bash
cat scripts/release_mac.sh | grep -A 2 "REMOTE_TAG_EXISTS\|EXISTING_RELEASE\|复用"
```

Expected: 看到 3 处新逻辑（设置 REMOTE_TAG_EXISTS、跳过 push、复用 release）。

- [ ] **Step 9.5：commit**

```bash
git add scripts/release_mac.sh
git commit -m "build(capcut_helper): release_mac.sh 加 release 复用 + remote tag 跳过 push 逻辑（让 win/mac 谁先发都可）"
```

---

## Task 10：B — 新增 `scripts/release_win.ps1`

**Files:**
- Create: `scripts/release_win.ps1`

- [ ] **Step 10.1：创建 `scripts/release_win.ps1`**

```powershell
# capcut_helper Windows 发版自动化脚本：bump 版本号后，一条命令完成 push → tag → 构建 → 发 GitHub release。
#
# 用法（从任意位置，PowerShell）：
#   pwsh -File scripts/release_win.ps1                      # 不带 release notes
#   pwsh -File scripts/release_win.ps1 notes.md             # 用 notes.md 作 release body
#
# 前置条件：
#   1. `git remote get-url origin` 指向 GitHub 仓库（HTTPS 远端）
#   2. 项目根存在 `.github-token` 文件，内容是有 `contents:write` 权限的 PAT
#      （已 .gitignore；生成路径：GitHub Settings → Developer settings → Personal access tokens）
#   3. `backend/app/__init__.py::__version__` 已 bump 到本次要发的版本号
#   4. 工作树干净
#   5. 本机已装 Inno Setup 6（build_win.ps1 需要 ISCC.exe）
#
# 与 release_mac.sh 互操作：谁先发都行；后发的会复用已存在的 release、只补上传自己平台资产。

param(
    [Parameter(Position = 0)]
    [string]$NotesFile
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot/..

# ---------- 前置检查 ----------

git diff --quiet
$dirty1 = $LASTEXITCODE
git diff --cached --quiet
$dirty2 = $LASTEXITCODE
if ($dirty1 -ne 0 -or $dirty2 -ne 0) {
    throw "工作树有未提交改动，先 commit 或 stash 再发版"
}

if (-not (Test-Path .github-token)) {
    Write-Host "✗ 缺 .github-token 文件（项目级，应已加入 .gitignore）"
    Write-Host ""
    Write-Host "生成步骤："
    Write-Host "  GitHub Settings → Developer settings → Personal access tokens → Fine-grained tokens"
    Write-Host "  Repository access: 只勾 cookaihq/capcut_helper"
    Write-Host "  Permissions → Repository → Contents: Read and write"
    Write-Host "  把生成的 token 字符串保存到项目根的 .github-token 文件里"
    exit 1
}
$token = (Get-Content .github-token -Raw).Trim()
if ([string]::IsNullOrEmpty($token)) {
    throw ".github-token 文件为空"
}

$versionLine = Select-String -Path backend/app/__init__.py -Pattern '"(\d+\.\d+\.\d+)"' | Select-Object -First 1
if (-not $versionLine) {
    throw "无法从 backend/app/__init__.py 解析 __version__"
}
$version = $versionLine.Matches.Groups[1].Value
$tag = "v$version"
$assetName = "capcut_helper-x64-v$version.exe"
Write-Host "→ 准备发 $tag"

# 本地 tag 必须不存在
git rev-parse $tag 2>$null > $null
if ($LASTEXITCODE -eq 0) {
    throw "本地已有 tag $tag。删除后重跑：git tag -d $tag"
}

# remote tag 可以已存在（表示 Mac 端先发过）
$remoteTagLine = git ls-remote --tags origin "refs/tags/$tag" 2>$null
$remoteTagExists = -not [string]::IsNullOrEmpty($remoteTagLine)
if ($remoteTagExists) {
    Write-Host "→ origin 上已有 tag $tag（可能 Mac 端已发过），跳过 push tag、复用已存在的 release"
}

# 读 owner/repo
$originUrl = (git remote get-url origin).Trim()
if ($originUrl -notmatch 'github\.com[:/]([^/]+/[^/.]+?)(\.git)?$') {
    throw "无法从 origin URL 解析 owner/repo: $originUrl"
}
$repoPath = $Matches[1]
Write-Host "→ 仓库 $repoPath"

if ($NotesFile -and -not (Test-Path $NotesFile)) {
    throw "release notes 文件不存在: $NotesFile"
}

# ---------- 跑测试 ----------

Write-Host "→ 跑后端测试"
Push-Location backend
uv run pytest -q
if ($LASTEXITCODE -ne 0) { Pop-Location; throw "后端测试失败" }
Pop-Location

Write-Host "→ 跑前端测试"
Push-Location frontend
npm run test --silent
if ($LASTEXITCODE -ne 0) { Pop-Location; throw "前端测试失败" }
Pop-Location

# ---------- 构建 ----------

Write-Host "→ 构建 .exe 安装包"
& pwsh -ExecutionPolicy Bypass -File scripts/build_win.ps1
if ($LASTEXITCODE -ne 0) { throw "build_win.ps1 失败" }
if (-not (Test-Path "dist/$assetName")) {
    throw "构建未产出 dist/$assetName"
}

# ---------- Git push ----------

Write-Host "→ git push main"
git push origin main
if ($LASTEXITCODE -ne 0) { throw "git push main 失败" }

Write-Host "→ git tag $tag"
git tag $tag
if ($LASTEXITCODE -ne 0) { throw "git tag 失败" }

if (-not $remoteTagExists) {
    Write-Host "→ git push tag"
    git push origin $tag
    if ($LASTEXITCODE -ne 0) { throw "git push tag 失败" }
} else {
    Write-Host "→ 跳过 push tag（remote 已有）"
}

# ---------- 找或建 release ----------

$apiHeaders = @{
    "Authorization" = "Bearer $token"
    "Accept" = "application/vnd.github+json"
}

Write-Host "→ 查询是否已有 release"
$release = $null
try {
    $release = Invoke-RestMethod -Uri "https://api.github.com/repos/$repoPath/releases/tags/$tag" -Headers $apiHeaders -ErrorAction Stop
    Write-Host "→ 复用已存在 release"
} catch {
    if ($_.Exception.Response.StatusCode.value__ -eq 404) {
        Write-Host "→ 创建新 release"
        $body = ""
        if ($NotesFile) {
            $body = Get-Content $NotesFile -Raw
        }
        $payload = @{
            tag_name = $tag
            name = $tag
            body = $body
            draft = $false
            prerelease = $false
        } | ConvertTo-Json
        try {
            $release = Invoke-RestMethod -Uri "https://api.github.com/repos/$repoPath/releases" `
                -Headers $apiHeaders -Method POST -Body $payload -ContentType "application/json"
        } catch {
            Write-Host "✗ 创建 release 失败：$_"
            if (-not $remoteTagExists) {
                Write-Host "  已推送的 tag $tag 需要手动清理：git push origin :refs/tags/$tag; git tag -d $tag"
            }
            exit 1
        }
    } else {
        throw $_
    }
}

$uploadUrl = $release.upload_url -replace '\{[^}]+\}', ''

# ---------- 上传 .exe 资产 ----------

Write-Host "→ 上传 $assetName"
$uploadHeaders = @{
    "Authorization" = "Bearer $token"
    "Content-Type" = "application/octet-stream"
}
try {
    Invoke-RestMethod -Uri "${uploadUrl}?name=$assetName" `
        -Headers $uploadHeaders -Method POST -InFile "dist/$assetName" | Out-Null
} catch {
    Write-Host "✗ 上传资产失败：$_"
    Write-Host "  release 已创建但缺资产，需要手动在 web UI 上传或重传。"
    Write-Host "  release 页：https://github.com/$repoPath/releases/tag/$tag"
    exit 1
}

# ---------- 完成 ----------

Write-Host ""
Write-Host "✓ 发布完成"
Write-Host "  release: https://github.com/$repoPath/releases/tag/$tag"
Write-Host "  下载链接: https://github.com/$repoPath/releases/download/$tag/$assetName"
```

- [ ] **Step 10.2：语法 lint**

```powershell
pwsh -NoProfile -Command "Get-Command -Syntax (Resolve-Path scripts/release_win.ps1) | Out-Null"
```

Expected：无报错。

更直接的语法检查：

```powershell
$null = [System.Management.Automation.PSParser]::Tokenize((Get-Content scripts/release_win.ps1 -Raw), [ref]$null)
Write-Host "语法 OK"
```

- [ ] **Step 10.3：dry-check 前置检查段（不真发版）**

可选：在不真 push tag 的前提下，验证前置检查段能跑通。先确认 `.github-token` 存在、工作树干净，然后跑：

```powershell
# 模拟 dry-check 只跑前置 + 测试，不到构建/push 段
# （没有 --dry-run 选项，只能视觉 / 手动 Ctrl-C 中断在构建之前）
# 跳过此 step 也可，等 Task 12 真正发版时一并验证
```

- [ ] **Step 10.4：commit**

```bash
git add scripts/release_win.ps1
git commit -m "build(capcut_helper): 新增 release_win.ps1 — Windows 发版自动化（镜像 release_mac.sh）"
```

---

## Task 11：B — README「每次发版」章节重写 + 已知限制更新

**Files:**
- Modify: `README.md`

- [ ] **Step 11.1：替换「每次发版」章节**

找到 `### 每次发版` 段（约 line 44-58），整段替换为：

````markdown
### 每次发版

两端可独立发，谁先发都行；第二个发的会复用同一个 release 只补传自己平台的资产。

```bash
# 1. bump 版本号（任意一台机器都行）
vi backend/app/__init__.py        # 改 __version__ 为新版本，例如 "0.1.3"
git commit -am "chore: bump to 0.1.3"
git push                          # 让另一台机器能拿到 bump

# 2. 在 Mac 上发 dmg
bash scripts/release_mac.sh                   # 不带 release notes
bash scripts/release_mac.sh notes-0.1.3.md    # 用 markdown 文件作 release body

# 3. 在 Windows 上发 exe（在另一台 Win 机器上、先 git pull）
pwsh -File scripts/release_win.ps1                   # 不带 release notes
pwsh -File scripts/release_win.ps1 notes-0.1.3.md    # 用 markdown 文件作 release body
```

`scripts/release_mac.sh` 与 `scripts/release_win.ps1` 行为对称：跑测试 → 构建产物 → push main → push/复用 tag `v0.1.3` → 找或建 GitHub release → 上传自己平台的资产（`.dmg` / `.exe`）。失败时会指出已推 tag 怎么清理。

发布后，已装上旧版的同事下次启动 helper 时会自动看到「发现新版本 v0.1.3」横幅。

> **版本号 & 资产名约定**：tag 必须 `v` + SemVer（`update_checker._strip_v_prefix` 按这个格式解析）；资产名硬编码两个：
> - Mac：`capcut_helper-arm64-v<version>.dmg`（`scripts/build_mac.sh` 产物名 + `update_checker._asset_name_for_tag()` 在 darwin 分支返回）
> - Windows：`capcut_helper-x64-v<version>.exe`（Inno Setup `OutputBaseFilename` + `_asset_name_for_tag()` 在 win32 分支返回）
````

- [ ] **Step 11.2：删除「已知限制」中本 spec 已解决的两项**

打开 `README.md` 找到「已知限制」章节（约 line 113-120）。

删除这条（如 Task 1 §4.1 矩阵全勾）：

```markdown
- Windows 端尚未在 Windows 机器上做端到端打包与回归测试；首次实机分发前需补一轮 `scripts/build_win.ps1` 验证 + 手动测试矩阵。
```

如 Task 3 完成（D spike 成功），还要删（应已在 Task 3.9 删掉，本步骤是兜底检查）：

```markdown
- Windows 剪映自定义草稿目录未实现自动探测：若你在剪映设置里改过草稿目录，需在 capcut_helper「设置」标签手动选择（macOS 端已支持，见 `app/native/bridge.py` 实测说明）。
```

- [ ] **Step 11.3：更新「打包成 .app 分发」章节标题与内容**

把 `## 打包成 .app 分发`（约 line 80）改为：

````markdown
## 打包分发

### Mac

```bash
bash scripts/build_mac.sh
```

产物：

- `dist/capcut_helper.app` —— 双击运行
- `dist/capcut_helper-arm64-v<version>.dmg` —— 分发用，hdiutil 打 UDZO 压缩 dmg

### Windows

```powershell
pwsh -File scripts/build_win.ps1
```

产物：

- `dist/capcut_helper/capcut_helper.exe` —— 双击运行（调试 / 不走安装包时用）
- `dist/capcut_helper-x64-v<version>.exe` —— Inno Setup 安装包，分发给同事
````

- [ ] **Step 11.4：commit**

```bash
git add README.md
git commit -m "docs(capcut_helper): README 发版流程拆 mac/win 双端 + 删 Windows 已验证 / 草稿目录限制"
```

---

## Task 12：bump 0.1.3 + 真发版验证（**可选，等所有 Task 完成后再做**）

**Files:**
- Modify: `backend/app/__init__.py`

这一 task 真的会创建一个 v0.1.3 GitHub release，**只在确认前 11 个 task 都过了再做**。如果只是想验证脚本而暂时不真发版，可只做 Step 12.1 + 12.2 然后 Ctrl-C 中断在测试 / 构建之后。

- [ ] **Step 12.1：bump __version__**

```bash
vi backend/app/__init__.py        # 把 "0.1.2" 改成 "0.1.3"
git commit -am "chore: bump to 0.1.3"
git push
```

- [ ] **Step 12.2：选一台机器先发**

任选 Mac 或 Win 任一台。例如先在 Windows 上发：

```powershell
pwsh -File scripts/release_win.ps1
```

Expected：脚本走到末尾打印「✓ 发布完成」+ release URL。

- [ ] **Step 12.3：在另一台机器跑对应脚本验证「复用 release」逻辑**

切到 Mac（先 `git pull` 拿到 bump commit + tag），跑：

```bash
bash scripts/release_mac.sh
```

Expected：脚本打印「→ origin 上已有 tag v0.1.3，跳过 push tag、复用已存在的 release」+ 末尾打印 release URL。

去 GitHub 看 release 页 https://github.com/cookaihq/capcut_helper/releases/tag/v0.1.3 ，应该同时挂着两个资产：
- `capcut_helper-arm64-v0.1.3.dmg`
- `capcut_helper-x64-v0.1.3.exe`

- [ ] **Step 12.4：在 Windows 上下载安装新 release 验证 update 流程**

在 Windows 上，从 GitHub release 页下 `capcut_helper-x64-v0.1.3.exe`，双击安装（覆盖旧版）。启动后：

- [ ] 不再出现「发现新版本」横幅（因为已经是最新）
- [ ] 状态栏菜单显示 v0.1.3
- [ ] Task 1 §4.1 矩阵关键项再 smoke 一遍

- [ ] **Step 12.5：（如选了相反顺序）反过来验一次也行**

可选：再 bump 到 0.1.4、这次先 Mac 发再 Win 发，验证两个方向都对称。或者留到下次正常发版时自然验证。

---

## Self-Review

### Spec Coverage

按 spec 章节核对：

| Spec 节 | 实现 Task |
|---|---|
| §2.1 A 端到端验证 | Task 1（含 §4.1 矩阵 + §4.2 fixup 场景 A/B/C） |
| §2.1 D 草稿目录探测 | Task 2（spike）+ Task 3（实现） |
| §2.1 C Inno Setup 升级 | Task 4（.iss）+ Task 5（build_win.ps1）+ Task 6（update_checker）+ Task 7（README） |
| §2.1 B release_win.ps1 + Mac 对称化 | Task 8（rename）+ Task 9（reuse 逻辑）+ Task 10（release_win.ps1）+ Task 11（README） |
| §3 顺序 A→D→C→B | Task 编号顺序对齐 |
| §4.1 A 测试矩阵 10 项 | Task 1 Step 1.3 |
| §4.2 fixup 高风险点 | Task 1 Step 1.4（场景 A/B/C） |
| §5.1 D 调研步骤 | Task 2 Step 2.1–2.4 |
| §5.2 case 1 实现 | Task 3 |
| §5.3 case 2 defer | Task 2 Step 2.5 case 2 |
| §6.1 .iss 文件 | Task 4 Step 4.2 |
| §6.2 build_win.ps1 增量 | Task 5 Step 5.1 |
| §6.3 update_checker 改动 | Task 6 |
| §6.4 README Windows 分发 | Task 7 |
| §7.1 release_win.ps1 步骤 | Task 10 Step 10.1 |
| §7.2 release.sh 重命名 + reuse | Task 8 + Task 9 |
| §7.3 README 每次发版 | Task 11 Step 11.1 |
| §8 资产命名 & 升级路径 | Task 6（实现）+ Task 11.1（README 文档化） |
| §9.1 自动化测试 | Task 3.1/3.5（D 单测）+ Task 6.1（C 测试改动）|
| §9.2 手动测试矩阵 | Task 1.3（A）+ Task 5.3/5.4（C 安装包流程）+ Task 12（B 双端发版联调） |
| §10 README 增量汇总 | Task 7 + Task 11 |
| §11 已知风险 | spec 已记录，无对应 task action |

**Gap**：无。

### Placeholder Scan

- 无「TBD」「TODO」「implement later」「fill in details」类标记
- 无「add appropriate error handling」类模糊指令
- 每个代码 step 都附完整代码块
- Task 3 中的 `<具体子路径>` / `<具体字段>` 是显式 spike-output 占位，且在 Step 3.3 备注说明了 spike 输出在何处替换；Task 2 末尾还给出了占位填充示例，不属于「忘填」类 placeholder
- Task 4 的 AppId GUID 是真实 step (Step 4.1) 指导生成、随后写入；不属于「忘填」
- Task 12 标注「可选」+「等所有 Task 完成后再做」，意图明确

### Type / 命名 一致性

- 资产名：所有 task 一致用 `capcut_helper-x64-v<version>.exe`（Task 5、6、10 三处出现，命名一致）
- `__version__` 解析：Task 5 (build_win.ps1) + Task 10 (release_win.ps1) 用相同的 PowerShell 正则 `'"(\d+\.\d+\.\d+)"'`
- `$tag = "v$version"`：Task 10 一处出现，与 spec / Mac 脚本约定一致
- `_asset_name_for_tag` 签名：Task 6 改动单行返回值，未动签名
- `_read_windows_custom_draft_path` 签名 `() -> Optional[str]`：Task 3.3 实现与 Task 3.1 测试导入路径一致

无不一致项。
