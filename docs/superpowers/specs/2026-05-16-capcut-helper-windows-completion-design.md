# capcut_helper Windows 完工 — 设计文档

> 创建日期：2026-05-16
> 状态：brainstorming 完成，待写实现计划
> 范围：把 tray-mode spec 已经落地的 Windows 骨架补成「同事拿到 .exe 安装包能直接用 + 发版自动化对称 + 自定义草稿目录探测齐」。
> 前置：tray-mode spec / plan 已完成，`backend/capcut_helper_win.spec`、`scripts/build_win.ps1`、`app/native/_tray_windows.py`、`update_checker._asset_name_for_tag` 平台分支均已在 `main` 上；当前 Windows 路径产物为 `dist/capcut_helper-x64-v<version>.zip`、`_asset_name_for_tag` 返回 `.zip`。

## 1. 项目目标

把 Windows 端从「能打 zip 但没有在 Win 机器上端到端跑过 + 没发版脚本 + 草稿目录探测不全」收尾到「与 Mac 完全对称的可分发、可发版、可探测」状态。

## 2. 范围

### 2.1 核心范围

四项工作，按 §3 的顺序串行执行：

- **A**：在 Windows 机器上端到端验证现有 `scripts/build_win.ps1`，过程中暴露的 PyInstaller hidden imports / 资源文件 / 原生 DLL 问题就地修
- **D**：`bridge.py` 中 Windows 自定义草稿目录的 TODO——timebox spike + 找到则实现 + 单测
- **C**：把 Windows 分发格式从 zip 升级为 Inno Setup `.exe` 安装包；同步改 `update_checker._asset_name_for_tag`、`build_win.ps1`、README
- **B**：新增 `scripts/release_win.ps1` 镜像 release.sh；把 `scripts/release.sh` 重命名为 `release_mac.sh` 并加 release reuse 逻辑，让两端互不阻塞

### 2.2 非目标

- **WebView2 Runtime bootstrap**：Inno Setup 安装包不引导装 WebView2，依赖用户系统已有；老 Win10 / 隔离网络需求是 follow-up
- **EV 证书 / 代码签名**：与 Mac 一致绕过 SmartScreen，README 已说明
- **Windows ARM64**：与 Intel Mac 同等级别，没需求不做
- **正式托盘图标**：tray-mode spec 已 defer，本 spec 不动
- **开机自启动**：tray-mode spec 已 defer

## 3. 实施顺序与依赖

```
A → D → C → B
```

理由：

- **A 先**：没在 Windows 上跑过现有 .exe，下面三步都是在沙堆上盖楼。A 可能暴露 hidden imports / libmediainfo 等需要补的 spec 改动，先把 baseline 稳了再升级
- **D 第二**：纯后端单文件改动、与打包链路无关；spike 不依赖 A 的产物（开发态 `uv run python -m app.main` 就能验）；scope 独立先收
- **C 第三**：改资产命名约定，决定 B 上传啥
- **B 最后**：用 C 决定的最终资产名 `capcut_helper-x64-v<version>.exe`

## 4. A：Windows 端到端验证现有打包

**入口**：`pwsh -File scripts/build_win.ps1`，期望产出 `dist/capcut_helper/capcut_helper.exe`（zip 步骤在本节先不动，C 才把它换成 Inno Setup）。

### 4.1 手动测试矩阵

继承 tray-mode plan Task 13.2 的矩阵，外加端到端 ai-canvas 接入路径：

```
[ ] 双击 dist/capcut_helper/capcut_helper.exe → 主窗口弹 + 任务栏 + 托盘图标
[ ] 三个 Tab（活动 / 草稿 / 设置）能切
[ ] 「设置 → 选择目录」能弹 Windows 文件夹选择对话框（pywebview FOLDER_DIALOG）
[ ] 「设置 → 自动探测」返回 %LOCALAPPDATA%\JianyingPro\... 那个默认路径（D 完成后还要验自定义路径优先）
[ ] 点窗口 × / Alt+F4 → 窗口消失、任务栏 / Alt+Tab 消失、托盘图标保留
[ ] 关窗后 curl http://127.0.0.1:<port>/api/v1/health 仍 200
[ ] 托盘左键 → 窗口出现
[ ] 托盘右键 → 菜单含 v0.1.2 / 打开面板 / 检查更新 / 退出
[ ] 菜单「退出」→ 全消失、端口释放、托盘图标无 zombie（不需要 hover 才消失）
[ ] POST 一个真实 timeline spec 到 /api/v1/draft，草稿能完整生成（验 pyJianYingDraft 资源 + libmediainfo + 前端 dist 端到端打进 bundle）
[ ] reveal_in_os("D:\\some\\path") → 资源管理器弹出且选中该项（验 explorer /select, 行为）
```

### 4.2 预期高风险 fixup 点

按概率排：

1. **libmediainfo.dll**：PyInstaller 是否自动 picked up（pyJianYingDraft 依赖 pymediainfo，后者依赖 libmediainfo.dll）。若启动报「找不到 mediainfo」，在 `capcut_helper_win.spec` 显式 `binaries=[(<完整路径>, ".")]` 加进来
2. **WebView2 Runtime 缺失**：窗口白屏。README 已有说明，仅需在 A 测试时实测一次确认 README 描述准确
3. **pyJianYingDraft 模板路径**：`collect_data_files('pyJianYingDraft')` 是否覆盖到所有 JSON 模板。若打包后报模板找不到，调整为更全的 `collect_all('pyJianYingDraft')`
4. **pystray / PIL 子模块**：当前 spec 已加 `pystray._win32` + `PIL._tkinter_finder` hidden import。若打包后托盘启动报 import 错，按报错补
5. **PIL 中文字符**：托盘占位图字「剪」字体回落可能渲染方块。此为已知 cosmetic 问题，不作为 A 的阻塞项

### 4.3 fixup 工作流

发现一个 → 修一个 → 重 build → 重测。修在 `capcut_helper_win.spec` 上的 commit message 形如 `build(capcut_helper): win spec 补 <module> hidden import`。

### 4.4 退出条件

测试矩阵全勾。在 spec 实现笔记或 plan 完成后的 PR 描述里记录「在 Windows 11 x64 + commit `<sha>` 上验证通过」。

## 5. D：Windows 自定义草稿目录探测（spike）

### 5.1 调研步骤（timebox 1–2 小时）

1. 启动剪映 Windows 版（确认装了；若没装，跳过 D，留 TODO）
2. 在剪映「设置 → 草稿位置」改成已知自定义路径，例如 `D:\test_drafts`
3. 关闭剪映（让它把配置 flush 到磁盘）
4. 候选位置搜索（按优先级）：
   - `%LOCALAPPDATA%\JianyingPro\User Data\Preferences\` 下所有文件 — grep `test_drafts`
   - `%APPDATA%\JianyingPro\` 同理
   - HKCU 注册表 `Software\JianyingPro` — `reg query HKCU\Software /s /f "test_drafts"`
   - 兜底：Sysinternals ProcMon，过滤 path 包含 "JianyingPro" 且 operation 是 WriteFile / RegSetValue，重新跑步骤 1-3 观察写入路径

### 5.2 case 1：调研到了 → 实现

参考 `_read_macos_custom_draft_path`（`bridge.py:23-34`）写 `_read_windows_custom_draft_path`。下面的 `<具体子路径>` / `<具体字段>` 是 spike 输出的占位，实施时按 5.1 调研结果填实：

```python
def _read_windows_custom_draft_path() -> Optional[str]:
    """读剪映 Win 版自定义草稿目录配置；任何异常返回 None 让上层回退到默认。"""
    config_path = Path(os.environ["LOCALAPPDATA"]) / "JianyingPro" / "<具体子路径——spike 输出>"
    try:
        with config_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, PermissionError, json.JSONDecodeError, ValueError, KeyError):
        return None
    value = data.get("<具体字段——spike 输出>")
    if not isinstance(value, str) or not value:
        return None
    return value if Path(value).is_dir() else None
```

> 备注：若 spike 结果是注册表而非 JSON 文件，实现改用 `winreg.OpenKey(winreg.HKEY_CURRENT_USER, "...")` + `QueryValueEx`，异常列表同样吞 `FileNotFoundError` / `OSError`。

在 `detect_draft_root` 加 Windows 分支：

```python
def detect_draft_root(self) -> Optional[str]:
    if sys.platform == "darwin":
        custom = _read_macos_custom_draft_path()
        if custom is not None:
            return custom
    elif sys.platform == "win32":
        custom = _read_windows_custom_draft_path()
        if custom is not None:
            return custom
    # 回落到默认目录（不变）
    relative = _DRAFT_ROOT_RELATIVE.get(sys.platform)
    if relative is None:
        return None
    candidate = Path.home() / relative
    return str(candidate) if candidate.is_dir() else None
```

单测加到 `test_native_bridge.py`：
- `test_read_windows_custom_draft_path_happy`：monkeypatch 一个临时目录 + 写 JSON，断言读出来等于该目录
- `test_read_windows_custom_draft_path_missing_file`：指向不存在的文件，断言返回 `None`
- `test_read_windows_custom_draft_path_invalid_json`：写坏 JSON，断言返回 `None`

更新 README 「已知限制」：删除「Windows 剪映自定义草稿目录未实现自动探测」那条。

### 5.3 case 2：调研不到 → defer

- 保留 `bridge.py` 现有 TODO 注释（line 65-66）
- 保留 README「已知限制」里那条
- 在本 spec 末尾「实现笔记」追加：「spike 已尝试 X / Y / Z 候选位置，未定位到剪映 Win 版自定义路径存储；defer 到下次。」
- 不阻塞 C、B 的推进

## 6. C：Inno Setup 安装包升级

### 6.1 新增 `scripts/capcut_helper.iss`

```ini
[Setup]
AppId={{<实施时用 Inno Setup「Tools → Generate GUID」生成新 GUID 填入>}     ; 固定 GUID，第一次发版后永远别改（卸载/升级靠它定位）
AppName=capcut_helper
AppVersion={#VERSION}                              ; 命令行 /DVERSION= 注入
AppPublisher=cookaihq
DefaultDirName={localappdata}\Programs\capcut_helper   ; 用户级安装，免 UAC
DefaultGroupName=capcut_helper
PrivilegesRequired=lowest                          ; 不要求管理员
OutputDir=..\dist
OutputBaseFilename=capcut_helper-x64-v{#VERSION}   ; 产 capcut_helper-x64-vX.Y.Z.exe
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

**关键决策与理由**：

- **`PrivilegesRequired=lowest` + `{localappdata}\Programs\capcut_helper`**：不弹 UAC，普通用户能装。对齐 Slack / Discord / Telegram 风格。代价是写不进 `Program Files`，对内部工具不需要那个语义
- **固定 AppId GUID**：发布第一个 .exe 版本前生成（Inno Setup 内 Tools → Generate GUID），写死。**永远别改**——改了等于新应用，旧版不会被自动卸载升级
- **不创建桌面快捷方式**：开始菜单已足够，少污染桌面；后续如有反馈再加 `Tasks` 段 checkbox
- **`AppPublisher=cookaihq`**：与 Mac `bundle_identifier='com.cookaihq.capcut_helper'` 的 publisher 部分对齐

### 6.2 `scripts/build_win.ps1` 增量

- 步骤 1（前端构建）保留
- 步骤 2（PyInstaller）保留
- **删掉**步骤 3 的 `Compress-Archive` 段
- **新增**步骤 3：调用 ISCC.exe 编译 .iss
- **版本号来源从 `git describe` 改为读 `backend/app/__init__.py::__version__`**——与 Mac 脚本统一、且不依赖 tag 已 push

ISCC.exe 定位三段式：

```powershell
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

& $iscc /DVERSION=$version scripts/capcut_helper.iss
```

### 6.3 `update_checker.py` 改动

```python
if sys.platform == "win32":
    return f"capcut_helper-x64-{tag}.exe"   # was .zip
```

`test_update_checker.py::test_asset_name_for_tag_on_win32` 期望值同步改 `.exe`。

### 6.4 README 改动

- 「Windows 分发」章节从「解压 zip → 双击 .exe」改为：
  1. 双击 `capcut_helper-x64-v<version>.exe` 安装包
  2. **首次打开**：Windows SmartScreen 拦截，点「更多信息」→「仍要运行」
  3. 安装向导：选位置（默认 `%LOCALAPPDATA%\Programs\capcut_helper`）→ 完成
  4. 开始菜单找到 capcut_helper 启动
  5. **系统运行时依赖**（PyInstaller 已打 Python 进 bundle，**不需装 Python**；但下面两个 Windows 系统运行时需要在）：
     - WebView2 Runtime：Win11 / 近一年 Win10 默认预装；若启动后窗口白屏，从 https://developer.microsoft.com/microsoft-edge/webview2/ 下「Evergreen Standalone Installer」装一次
     - Visual C++ 2015-2022 Redistributable (x64)：绝大多数 Windows 机器自带；若启动报「丢失 VCRUNTIME140.dll」，从 https://aka.ms/vs/17/release/vc_redist.x64.exe 下载安装
- 新增「发版者一次性准备 — Windows」一段：本机装 Inno Setup 6（链接 https://jrsoftware.org/isdl.php），脚本会自动定位 ISCC.exe

## 7. B：`release_win.ps1` + Mac 端对称化

### 7.1 新增 `scripts/release_win.ps1`

主要步骤：

1. **前置检查**：
   - 工作树干净（`git diff --quiet` + `git diff --cached --quiet`）
   - `.github-token` 存在且非空
   - 解析 `backend/app/__init__.py::__version__` → `$version` / `$tag` / `$assetName`
   - 解析 `git remote get-url origin` → owner/repo（正则匹配 `github\.com[:/]([^/]+/[^/.]+?)(\.git)?$`）
   - 可选第一个参数 = notes 文件，存在性校验

2. **本地 tag 重复检查**：`git rev-parse $tag` 必须失败（本地没有）；remote 上有则记录 `$remoteTagExists = $true`

3. **测试**：`cd backend; uv run pytest -q` + `cd frontend; npm run test --silent`

4. **构建**：调 `scripts/build_win.ps1`；校验 `dist/$assetName` 存在

5. **push main + tag**（智能）：
   - 总是 `git push origin main`
   - 总是 `git tag $tag`（本地）
   - 仅当 `-not $remoteTagExists` 时 `git push origin $tag`；否则打印「remote 已有 tag $tag，复用 release」

6. **找或建 release**：
   - 先 `GET /repos/$repo/releases/tags/$tag`
   - 200 → 用返回的 `upload_url`、`html_url`
   - 404 → `POST /repos/$repo/releases` 创建（body 含 `tag_name`、`name`、`body`、`draft=false`、`prerelease=false`）

7. **上传 .exe 资产**：`POST $uploadUrl?name=$assetName`，`Content-Type: application/octet-stream`，`-InFile dist/$assetName`

8. **失败兜底**：tag 已 push 但 release/upload 挂了 → 打印清理命令 `git push origin :refs/tags/$tag; git tag -d $tag`

PowerShell 工具：
- `Invoke-RestMethod` 替 curl（JSON 自动 parse）
- `$ErrorActionPreference = "Stop"` + `try/catch` 处理 404 探测
- `git` 直接调

### 7.2 `release.sh` → `release_mac.sh` 重命名 + reuse 逻辑

把 Mac 端也升级为「先查 release 是否存在 / 复用 / 否则创建」，与 Win 行为对称——否则 Win 先发会导致 Mac 后发因 422 失败。

改动点：
- 重命名 `scripts/release.sh` → `scripts/release_mac.sh`（git mv）
- 在「创建 GitHub release」段（line 108-136）之前插入「先 GET /releases/tags/$TAG，200 则跳过 POST 复用响应」
- 同步本地 tag push 逻辑：若 remote 已有 tag，本地仅 `git tag` 不 push
- 不引入新工具依赖（仍是 curl + python3 JSON 解析）

### 7.3 README「每次发版」章节重写

```markdown
### 每次发版

两端可独立发，谁先发都行；第二个发的会复用同一个 release 只补传自己平台的资产。

**Mac 发版**：

bash scripts/release_mac.sh                   # 不带 release notes
bash scripts/release_mac.sh notes-0.1.3.md    # 用 markdown 文件作 release body

**Windows 发版**：

pwsh -File scripts/release_win.ps1                   # 不带 release notes
pwsh -File scripts/release_win.ps1 notes-0.1.3.md    # 用 markdown 文件作 release body
```

「一次性准备」加一条：发 Windows 版前本机需装 Inno Setup 6。

## 8. 资产命名 & 升级路径副作用

**最终资产名约定**（升级到 v0.1.3 / Inno Setup 之后）：

- Mac：`capcut_helper-arm64-v<version>.dmg`（不变）
- Win：`capcut_helper-x64-v<version>.exe`（从 .zip 切换）

**v0.1.2 → v0.1.3 一次性副作用**：

已经在用 v0.1.2 zip 版的 Windows 同事，他们运行中的 `_asset_name_for_tag` 还返回 `.zip`。v0.1.3 release 上传的是 `.exe`，因此 update 横幅会显示「发现新版本 v0.1.3」但 `download_url=None`（找不到匹配 `.zip` 资产），`release_url` 仍可用——用户点 release_url 跳到 GitHub 手动下 `.exe`。

这是一次性迁移阵痛，可接受。装上 v0.1.3 后 `_asset_name_for_tag` 就返回 `.exe`，后续 update 链路恢复正常。

不需要额外兼容代码——`update_checker` 现有「`download_url=None` 时只展示 release_url」的回退路径（GUI 已支持）覆盖此场景。

## 9. 测试策略

### 9.1 自动化测试（pytest）

- D 在 spike 成功时加 3 个 case 到 `test_native_bridge.py`（happy / file-missing / invalid-json）
- C 改 `test_update_checker.py::test_asset_name_for_tag_on_win32` 期望值 `.zip` → `.exe`
- A 不产生新单测，全靠手动矩阵
- B 不写单测——发版脚本是 IO heavy 的 shell glue，单测 ROI 太低

### 9.2 手动测试矩阵

- **A 阶段**：§4.1 的矩阵跑一次（直接双击 `dist/capcut_helper/capcut_helper.exe`）
- **C 阶段**：Inno Setup 安装包跑一次完整流程：双击 .exe → 安装到 `%LOCALAPPDATA%\Programs\capcut_helper` → 从开始菜单启动 → 走 §4.1 同款矩阵 → 然后从「设置 → 应用」卸载、确认彻底干净（开始菜单项 / 安装目录 / `HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall\` 下条目都被移除）
- **B 阶段**：bump 到 v0.1.3 → 先 Win 发再 Mac 发（或反过来）各试一次，确认两个资产都挂到同一 release 上

## 10. README 增量汇总

按本 spec 的 C / B / D 节落地后，README 共有以下更新点：

1. 「一次性准备」加 Windows 子项：装 Inno Setup 6
2. 「每次发版」拆 Mac / Windows 两段，路径分别 `release_mac.sh` / `release_win.ps1`
3. 「Windows 分发」章节从 zip 改为 .exe 安装包步骤
4. 「打包成 .app 分发」改为「打包分发」并加 Windows 子节
5. 「已知限制」：D spike 成功则删「Windows 自定义草稿目录未实现自动探测」那条；A 验证通过则删「Windows 端尚未在 Windows 机器上做端到端打包与回归测试」那条
6. 「版本号约定」section 把资产命名注释更新为双平台版本

## 11. 已知风险 / 后续项

- **`_replace_pywebview_quit_action`**（tray-mode spec §7.1）依赖 pywebview cocoa 内部菜单结构——本 Windows 完工不动它；pywebview 升级仍是 Mac 侧的回归风险点
- **Inno Setup AppId GUID 不可改**：发出第一个 .exe 版本后任何 GUID 修改都会导致旧版无法自动升级，需要新建 spec
- **D spike 失败概率不小**：剪映 Win 版配置文件结构没文档化。失败则保留 TODO + README 限制
- **用户端运行时依赖**：PyInstaller 已经把 Python 3.13 解释器和所有 Python 依赖打进 bundle，目标机**不需要装 Python**。但仍依赖以下两个系统级运行时：
  - **WebView2 Runtime**：pywebview 用 Edge Chromium 渲染前端。Win11 / 近一年的 Win10 默认预装；老 Win10 / 隔离企业内网可能缺，缺了双击 .exe 后窗口白屏。README 已有 fallback 链接（微软 Evergreen Standalone Installer）
  - **Visual C++ 2015-2022 Redistributable (x64)**：Python 3.13 是 VS 2022 编译，bootloader 链接 `vcruntime140.dll`。绝大多数 Windows 机器 Windows Update 推过；极端精简系统可能缺，缺了双击 .exe 会报「丢失 VCRUNTIME140.dll」。README 同样加 fallback 说明（微软官网 `vc_redist.x64.exe` 链接）
  - follow-up：Inno Setup `[Code]` 段检测 + 引导下载 WebView2 Runtime；`[Files]`+`[Run]` 段把 `vc_redist.x64.exe`（约 25MB）打进安装包静默执行。下次再做
- **企业内网 GitHub API 访问**：发版脚本依赖 `api.github.com` 可访问。若内网阻断需走代理，留 `HTTPS_PROXY` 环境变量给 Invoke-RestMethod 透传（PowerShell 默认支持）
- **PowerShell 版本兼容**：`release_win.ps1` 在 PowerShell 5.1（系统自带）和 PowerShell 7+ 都能跑，因为只用了 `Invoke-RestMethod` / 标准 cmdlet / 字符串操作；不依赖 ternary / pipeline chain 等 7+ 语法
