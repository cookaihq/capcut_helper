# capcut_helper

剪映外挂助手。本地 FastAPI 服务 + pywebview 桌面 GUI，支持把外部程序（如 ai-canvas）传来的时间线规格生成成剪映草稿。

详细设计：`docs/superpowers/specs/`。

## 仓库结构

- `backend/` —— FastAPI 后端，pytest 测试，pywebview 桌面壳入口
- `frontend/` —— React + Vite + Ant Design 5 GUI
- `scripts/` —— 构建/分发脚本
- `docs/` —— 设计文档（specs）+ 实现计划（plans）+ 调用方接入指南（CALLER_GUIDE）

## 开发

后端：

```bash
cd backend
uv sync
uv run pytest                  # 跑测试
uv run python -m app.main      # 启 pywebview 窗口（先 cd frontend && npm run build）
```

前端（开发态用 Vite dev server，自带 /api 代理到 127.0.0.1:9527）：

```bash
cd frontend
npm install
npm run dev                    # http://localhost:3176
npm run test                   # Vitest
```

## 运行行为

- **启动**：双击 `.app` / `.exe` → FastAPI 本地服务起来 + 状态栏 / 系统托盘出现图标 + 主窗口弹出
- **关闭窗口**（点 ×、Cmd+W、Alt+F4）：窗口隐藏到状态栏 / 托盘，FastAPI 服务**继续运行**，ai-canvas 等调用方仍可访问
- **打开面板**：左键点状态栏 / 托盘图标，或在菜单点「打开面板」
- **完整退出**（停止 FastAPI、释放端口）：
  - macOS：状态栏菜单「退出」、或 ⌘Q
  - Windows：托盘菜单「退出」

### 状态栏 / 托盘菜单

- v0.x.x（当前版本号，只读）
- 打开面板
- 检查更新...
- 退出

## 发版

### 一次性准备（只做一次）

1. 配 `origin` 远端到 GitHub 仓库（HTTPS 形式，凭据嵌 URL 或用系统 credential helper 都可以）
2. 在项目根放 `.github-token` 文件，内容是有 `contents:write` 权限的 fine-grained PAT（**已 gitignore**）
   - 生成路径：GitHub Settings → Developer settings → Personal access tokens → Fine-grained tokens
   - Repository access：只勾本仓库
   - Permissions → Repository → Contents：Read and write

### 每次发版

```bash
# 1. bump 版本号
vi backend/app/__init__.py        # 改 __version__ 为新版本，例如 "0.1.1"
git commit -am "chore: bump to 0.1.1"

# 2. 一条命令发布
bash scripts/release.sh                   # 不带 release notes
bash scripts/release.sh notes-0.1.1.md    # 用 markdown 文件作 release body
```

`scripts/release.sh` 会按顺序完成：跑测试 → 构建 .app/.dmg → push main → push tag `v0.1.1` →
调 GitHub API 创建 release → 上传 `capcut_helper-arm64-v<version>.dmg` 资产。失败时会指出已推 tag 怎么清理。

发布后，已装上旧版的同事下次启动 helper 时会自动看到「发现新版本 v0.1.1」横幅。

> **版本号约定**：tag 必须 `v` + SemVer（`update_checker._strip_v_prefix` 按这个格式解析）；
> dmg 资产名必须是 `capcut_helper-arm64-v<version>.dmg`（`scripts/build_mac.sh` 产物名 + `services/update_checker.py::_asset_name_for_tag()` 按 tag 模板构造该名）。脚本已硬编码这两个约定，按它来就行。

## 打包成 .app 分发

```bash
bash scripts/build_mac.sh
```

产物：

- `dist/capcut_helper.app` —— 双击运行
- `dist/capcut_helper-arm64-v<version>.dmg` —— 分发用，hdiutil 打 UDZO 压缩 dmg

## 分发给同事

把 `dist/capcut_helper-arm64-v<version>.dmg` 发给对方，请对方按以下步骤：

1. 双击 `capcut_helper-arm64-v<version>.dmg` 挂载
2. 在弹出的 Finder 窗口里把 `capcut_helper.app` 拖到旁边的 `Applications` 软链上
3. **首次打开**：因为未做代码签名，macOS 会拦截。**右键 → 打开 → 在弹窗里再点「打开」**，之后双击就行。或在「系统设置 → 隐私与安全」里允许。
4. **首次访问草稿目录时**，近版 macOS 会再弹一个文件夹访问权限提示（针对 `~/Movies` 或自定义草稿目录），点「允许」即可
5. 启动后第一次进 GUI，按「设置」标签里的「自动探测」找剪映草稿目录，或手动选择

应用窗口里的「活动」「草稿」「设置」三个标签——其中「设置」配剪映草稿根目录是首次必做的事。

### Windows 分发

把 `dist/capcut_helper-x64-v<version>.zip` 发给对方，请对方按以下步骤：

1. 解压 zip，得到 `capcut_helper/` 目录
2. 双击 `capcut_helper.exe`，**首次打开**：因为未做 EV 证书签名，Windows SmartScreen 会拦截，点「更多信息」→「仍要运行」
3. **前置依赖**：WebView2 Runtime。Win11 / 最新 Win10 默认预装；老 Win10 上若启动后窗口空白，从 https://developer.microsoft.com/microsoft-edge/webview2/ 下「Evergreen Standalone Installer」安装一次
4. 启动后第一次进 GUI，按「设置」标签里的「自动探测」找剪映草稿目录，或手动选择

## 已知限制

- 平台支持：macOS arm64（M 系列 Mac）和 Windows x64。Intel Mac 暂不支持，见 `docs/superpowers/specs/2026-05-15-capcut-helper-packaging-design.md` §9。
- Windows 端尚未在 Windows 机器上做端到端打包与回归测试；首次实机分发前需补一轮 `scripts/build_win.ps1` 验证 + 手动测试矩阵。
- 剪映 10.5+ 草稿编辑保存后会加密，capcut_helper 只能**新建**草稿、不能改剪映动过的草稿。详见 spec §2 实测约束。
- 状态栏 / 托盘图标当前为占位（mac 文字「剪映」、win PIL 动态画的占位图），正式图标 follow-up。
- 状态栏菜单「检查更新」会先打开面板再触发前端横幅 UI 处理；前端目前在启动时已自动检查，菜单点击不会强制重查（follow-up：前端监听 `capcut-helper:check-update` 自定义事件）。
- 异常退出（kill -9 / 系统强关）不做 graceful shutdown，正常退出请走状态栏「退出」或 macOS ⌘Q。
