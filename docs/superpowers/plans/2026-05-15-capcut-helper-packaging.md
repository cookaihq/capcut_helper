# capcut_helper 跨平台打包 Implementation Plan（Plan 3）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 Plan 1 + Plan 2 已完成的 dev-mode 桌面应用打成可双击运行的 macOS arm64 `.app`，加上分发用的 zip 和 README。

**Architecture:** 用 PyInstaller `.spec` 配置打包：源（`app/main.py`）+ Python 解释器 + 所有后端依赖 + 前端构建产物（`frontend/dist`）+ pyJianYingDraft 自带资源 + pywebview Mac 后端 hidden imports。运行时通过 `sys._MEIPASS` 解析 bundle 内资源路径；分发用 Apple 推荐的 `ditto` 打 zip（保留符号链接）。顺手修 Plan 2 final review flag 的 `reveal_in_os` 路径未归一化。

**Tech Stack:** PyInstaller 6.x（dev 依赖）、Python 3.13、pywebview 6.x、pyJianYingDraft 0.2.x、Vite 6（前端，已有）；shell 脚本 + `ditto`。

**Plan scope:** 这是 capcut_helper 的 **Plan 3（共 3 个）**。Plan 1（后端）+ Plan 2（桌面 GUI）已合入 `main`。本计划只覆盖设计文档 `capcut_helper/docs/superpowers/specs/2026-05-15-capcut-helper-packaging-design.md`：Mac arm64 .app、构建脚本、`reveal_in_os` normpath 修复、README。**非目标**（spec §2.2）：代码签名 / Apple 公证、DMG、Windows .exe、Intel Mac universal2、auto-update。

**前置说明：**
- 设计文档：`capcut_helper/docs/superpowers/specs/2026-05-15-capcut-helper-packaging-design.md`。
- git 提交身份已配置为 repo-local 的 cookaihq，正常 `git commit` 即可。
- 后端命令工作目录为 `capcut_helper/backend/`；前端命令工作目录为 `capcut_helper/frontend/`；shell 脚本工作目录为 `capcut_helper/`。
- pywebview / pyJianYingDraft / pymediainfo / pyobjc-* 的 PyInstaller 钩子由社区维护，**实测一定会冒出几个 hidden import 没收齐 / `libmediainfo.dylib` 没拾到**。Task 4 的「首次成功构建」步骤里有 troubleshooting checklist 兜底。
- 当前 `capcut_helper/.gitignore` 已存在（含 `.superpowers/`），本计划往里追加 `/build/` 和 `/dist/`。

---

## File Structure

```
capcut_helper/
├── .gitignore                       # 改：追加 /build/ /dist/
├── README.md                        # 新：项目级 README（开发者 + 分发说明）
├── scripts/
│   └── build_mac.sh                 # 新：一条命令的构建脚本
├── backend/
│   ├── pyproject.toml               # 改：dev 依赖加 pyinstaller
│   ├── capcut_helper.spec           # 新：PyInstaller spec 文件
│   ├── app/
│   │   ├── server.py                # 改：加 _resource_path 辅助函数
│   │   └── native/bridge.py         # 改：reveal_in_os 加 os.path.normpath
│   └── tests/
│       └── test_native_bridge.py    # 改：加 reveal_in_os 的 3 个测试
└── (运行时生成)
    ├── build/                       # gitignored, PyInstaller 中间产物
    └── dist/
        ├── capcut_helper.app/       # 主产物，可双击
        └── capcut_helper.zip        # 分发用，ditto 打包
```

---

## Task 1: 修 reveal_in_os 加路径归一化（TDD）

**Files:**
- Modify: `capcut_helper/backend/app/native/bridge.py`
- Test: `capcut_helper/backend/tests/test_native_bridge.py`

Plan 2 final review flag：`reveal_in_os` 接到 `${draftRoot}/${name}` 形式的正斜杠路径直接喂给 `explorer /select,` 不干净。改成先 `os.path.normpath` 归一化。

`os.path.normpath` 行为依宿主平台：Mac host 上是 posix 语义（折叠 `//` 和 `..`，不动 `/`），Windows host 上是 nt 语义（顺带把 `/` 转为 `\`）。测试用同一份 `os.path.normpath` 计算期望值，断言桥把 normpath 的结果传给了 subprocess，**与宿主平台无关**。

- [ ] **Step 1: 写失败测试**

在 `capcut_helper/backend/tests/test_native_bridge.py` 末尾追加（保留现有 4 个 detect_draft_root 测试不动）：

```python
import os
import subprocess
from unittest.mock import patch


def test_reveal_in_os_normalizes_path_on_darwin(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    bridge = NativeBridge()
    raw = "/Users/x/Movies//JianyingPro/../JianyingPro/draft"
    expected = os.path.normpath(raw)  # 同一份 normpath 算期望值，平台无关
    with patch.object(subprocess, "run") as mock_run:
        bridge.reveal_in_os(raw)
    mock_run.assert_called_once_with(["open", "-R", expected], check=False)


def test_reveal_in_os_normalizes_path_on_win32(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    bridge = NativeBridge()
    raw = "C:/Users/x/AppData/Local/JianyingPro/draft"
    expected = os.path.normpath(raw)
    with patch.object(subprocess, "run") as mock_run:
        bridge.reveal_in_os(raw)
    mock_run.assert_called_once_with(["explorer", "/select,", expected], check=False)


def test_reveal_in_os_unsupported_platform_does_nothing(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    bridge = NativeBridge()
    with patch.object(subprocess, "run") as mock_run:
        bridge.reveal_in_os("/foo/bar")
    mock_run.assert_not_called()
```

> 注：现有文件顶部已经 `import sys`，新追加测试不需要再加 import sys；新加 `import os`、`import subprocess`、`from unittest.mock import patch` 到文件顶部 import 区即可。

- [ ] **Step 2: 运行测试确认失败**

Run: `cd capcut_helper/backend && uv run pytest tests/test_native_bridge.py -v`
Expected: 3 个新测试中至少前 2 个 FAIL（桥还没用 normpath，传的是原始 path 字符串）。第 3 个测试可能 PASS（linux 分支本来就 no-op）也可能 FAIL（取决于现实现是否在 linux 上调过 subprocess）——按现状不会，所以这个测试可能直接 PASS，但 1/2 必失。

- [ ] **Step 3: 改 bridge.py**

把 `capcut_helper/backend/app/native/bridge.py` 整体替换为（diff 只动 import + `reveal_in_os` 方法体）：

```python
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

import webview

# 各平台剪映默认草稿目录（相对 Path.home()）
_DRAFT_ROOT_RELATIVE = {
    "darwin": "Movies/JianyingPro/User Data/Projects/com.lveditor.draft",
    "win32": "AppData/Local/JianyingPro/User Data/Projects/com.lveditor.draft",
}


class NativeBridge:
    """pywebview js_api 桥：暴露给前端 window.pywebview.api.* 的系统外壳操作。
    window 在 create_window 之后由 main.py 赋值。"""

    def __init__(self) -> None:
        self.window = None

    def pick_folder(self) -> Optional[str]:
        """打开文件夹选择对话框，返回选中目录路径；用户取消返回 None。"""
        result = self.window.create_file_dialog(webview.FOLDER_DIALOG)
        if not result:
            return None
        return result[0]

    def reveal_in_os(self, path: str) -> None:
        """在系统文件管理器里定位该路径。"""
        normalized = os.path.normpath(path)
        if sys.platform == "darwin":
            subprocess.run(["open", "-R", normalized], check=False)
        elif sys.platform == "win32":
            subprocess.run(["explorer", "/select,", normalized], check=False)

    def detect_draft_root(self) -> Optional[str]:
        """按平台推断剪映默认草稿目录，存在则返回路径字符串，否则 None。"""
        relative = _DRAFT_ROOT_RELATIVE.get(sys.platform)
        if relative is None:
            return None
        candidate = Path.home() / relative
        return str(candidate) if candidate.is_dir() else None
```

- [ ] **Step 4: 跑全套后端测试确认无回归**

Run: `cd capcut_helper/backend && uv run pytest -v`
Expected: 全部 PASS（约 41 passed = 38 原有 + 3 新增）

- [ ] **Step 5: Commit**

```bash
git add capcut_helper/backend/app/native/bridge.py capcut_helper/backend/tests/test_native_bridge.py
git commit -m "fix(capcut_helper): reveal_in_os 路径用 normpath 归一化"
```

---

## Task 2: server.py 加 _resource_path 兼容 PyInstaller 冻结

**Files:**
- Modify: `capcut_helper/backend/app/server.py`

冻结后 `__file__` 不指向源码树，当前 `_FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"` 在 .app 里会失效。加 `_resource_path` 辅助函数：dev 模式走源码树，冻结模式走 `sys._MEIPASS`。

此任务无新测试——`_resource_path` 在 dev 模式行为与原代码等价，现有 `test_api.py` 已经覆盖（mount 静态文件 + GET 路由不冲突等场景）；冻结模式只能靠 Task 5 手动冒烟验证。

- [ ] **Step 1: 改 server.py**

把 `capcut_helper/backend/app/server.py` 整体替换为：

```python
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.api.router import api_router
from app.core.config import load_config
from app.core.exceptions import register_exception_handlers


def _resource_path(rel: str) -> Path:
    """资源文件路径解析：
    - 开发模式：从源码树解析（server.py 在 backend/app/，上跳两级到 capcut_helper/）
    - PyInstaller 冻结后：从 sys._MEIPASS 解析（PyInstaller 在运行时把打进 bundle 的
      data files 解压/映射到这个目录）
    """
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / rel
    return Path(__file__).resolve().parents[2] / rel


# 前端构建产物目录
_FRONTEND_DIST = _resource_path("frontend/dist")


def create_app(port: int) -> FastAPI:
    app = FastAPI(title="capcut_helper")
    app.state.port = port
    app.state.version = __version__
    app.state.last_draft_request_at = None

    cfg = load_config()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_exception_handlers(app)
    app.include_router(api_router)

    # 先挂 API 路由，再挂前端静态文件到 /（StaticFiles 是兜底匹配）。
    # dist 不存在时（如只跑后端 pytest、还没构建前端）跳过，不影响后端测试。
    if _FRONTEND_DIST.is_dir():
        app.mount("/", StaticFiles(directory=str(_FRONTEND_DIST), html=True), name="frontend")

    return app
```

- [ ] **Step 2: 跑全套后端测试确认无回归**

Run: `cd capcut_helper/backend && uv run pytest -v`
Expected: 全部 PASS（约 41 passed，与 Task 1 后相同；`_resource_path` 在 dev 模式行为等价于原代码）

- [ ] **Step 3: Commit**

```bash
git add capcut_helper/backend/app/server.py
git commit -m "refactor(capcut_helper): server.py 加 _resource_path 兼容 PyInstaller 冻结"
```

---

## Task 3: PyInstaller 依赖 + capcut_helper.spec

**Files:**
- Modify: `capcut_helper/backend/pyproject.toml`
- Create: `capcut_helper/backend/capcut_helper.spec`

加 PyInstaller 到 dev 依赖；写 `.spec` 文件描述如何把后端 + 前端 + 资源打成 macOS .app bundle。

**重要前提**：Task 4 跑完整构建之前，本任务不实际触发 PyInstaller——只确认 spec 文件能被 Python 解析（语法对）。原因：实际 PyInstaller 构建依赖 `frontend/dist` 已存在，那是 Task 4 build 脚本做的事；本任务把构建配置准备好就行。

- [ ] **Step 1: 加 PyInstaller 到 dev 依赖**

`capcut_helper/backend/pyproject.toml`：在 `[dependency-groups] dev` 数组里追加 `"pyinstaller>=6.10"`。改完后 dev 组应为：

```toml
[dependency-groups]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24",
    "respx>=0.21",
    "pyinstaller>=6.10",
]
```

Run: `cd capcut_helper/backend && uv sync`
Expected: 成功安装 pyinstaller（连同 altgraph、macholib 等子依赖），无报错。

Run: `cd capcut_helper/backend && uv run pyinstaller --version`
Expected: 打印一个 6.x 版本号，例如 `6.11.1`。

- [ ] **Step 2: 写 capcut_helper.spec**

`capcut_helper/backend/capcut_helper.spec`：

```python
# -*- mode: python ; coding: utf-8 -*-
"""capcut_helper PyInstaller spec —— 产 macOS arm64 .app bundle。

用法（一般通过 scripts/build_mac.sh 调起）：
    cd capcut_helper/backend
    uv run pyinstaller --clean --noconfirm \
        --distpath=../dist --workpath=../build \
        capcut_helper.spec

前置：frontend/dist 必须先用 `npm run build` 构建好（build_mac.sh 已包含）。
"""

from PyInstaller.utils.hooks import collect_all, collect_data_files

# pywebview Mac 后端 hidden imports + 数据文件一次性收齐
pywebview_datas, pywebview_binaries, pywebview_hiddenimports = collect_all("pywebview")
# pyJianYingDraft 自带的模板等资源（如 DRAFT_META_TEMPLATE）
jianying_datas = collect_data_files("pyJianYingDraft")


a = Analysis(
    ["app/main.py"],
    pathex=[],
    binaries=pywebview_binaries,
    datas=[
        # (源路径相对 spec 所在目录, bundle 内目标路径)
        ("../frontend/dist", "frontend/dist"),
        *pywebview_datas,
        *jianying_datas,
    ],
    hiddenimports=pywebview_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="capcut_helper",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,            # GUI 应用，不带终端
    disable_windowed_traceback=False,
    target_arch=None,         # 跟随当前 host 架构（M 系列 Mac 上为 arm64）
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="capcut_helper",
)

app = BUNDLE(
    coll,
    name="capcut_helper.app",
    icon=None,
    bundle_identifier="com.cookaihq.capcut_helper",
    info_plist={
        "CFBundleName": "capcut_helper",
        "CFBundleDisplayName": "capcut_helper",
        "CFBundleIdentifier": "com.cookaihq.capcut_helper",
        "CFBundleVersion": "0.1.0",
        "CFBundleShortVersionString": "0.1.0",
        "NSHighResolutionCapable": True,
    },
)
```

- [ ] **Step 3: 验证 spec 文件语法**

Run: `cd capcut_helper/backend && uv run python -c "
import ast
with open('capcut_helper.spec') as f:
    ast.parse(f.read())
print('spec 语法 OK')
"`
Expected: 输出 `spec 语法 OK`，无 `SyntaxError`。（这只是 Python 层面的语法检查，spec 里 `Analysis`/`PYZ`/`EXE`/`COLLECT`/`BUNDLE` 等全局名要 PyInstaller 注入才能执行；语法 OK 是必要不充分条件，真正的执行在 Task 4。）

- [ ] **Step 4: Commit**

```bash
git add capcut_helper/backend/pyproject.toml capcut_helper/backend/uv.lock capcut_helper/backend/capcut_helper.spec
git commit -m "build(capcut_helper): 加 PyInstaller dev 依赖与 capcut_helper.spec"
```

---

## Task 4: 构建脚本 + .gitignore + 首次成功构建

**Files:**
- Create: `capcut_helper/scripts/build_mac.sh`
- Modify: `capcut_helper/.gitignore`

把整个构建流水线打成一条命令：装/构建前端 → PyInstaller 跑 `.spec` → ditto 打 zip。然后跑一次确认端到端能产出 `.app` 和 `.zip`。

- [ ] **Step 1: 写 build_mac.sh**

`capcut_helper/scripts/build_mac.sh`：

```bash
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
```

Run: `chmod +x capcut_helper/scripts/build_mac.sh`
Expected: 无输出，脚本变成可执行。

- [ ] **Step 2: 改 .gitignore**

把 `capcut_helper/.gitignore` 整体替换为：

```
# Visual-companion brainstorming session files (not source)
.superpowers/

# PyInstaller 构建产物（由 scripts/build_mac.sh 产生于项目根）
# 用前置 / 锚定到本 .gitignore 所在目录，避免误盖 frontend/dist
/build/
/dist/
```

- [ ] **Step 3: 端到端跑一次构建**

Run: `bash capcut_helper/scripts/build_mac.sh`
Expected: 三步都成功；最终打印 `.app` 和 `.zip` 路径；不报错。**构建可能要 1-3 分钟**（PyInstaller 第一次跑较慢）。

**troubleshooting checklist**（若构建失败）：
- `ModuleNotFoundError: pywebview.platforms.cocoa`（或类似 Cocoa 子模块）→ 在 `.spec` 的 `hiddenimports` 中显式追加该模块名，重跑。
- `libmediainfo.dylib not found`（运行时）→ 这条不在构建阶段暴露，构建会成功，Task 5 双击 .app 时才报。本任务的目标是构建成功 + 产物存在；运行问题留给 Task 5 排查。
- `frontend/dist not found` → 检查 Step 1 的前端构建是否真成功了。
- `uv: command not found` 或 `npm: command not found` → 检查 PATH，确认 uv 与 npm 都在当前 shell 可用。

- [ ] **Step 4: 验证产物存在**

Run: `ls -la capcut_helper/dist/`
Expected: 至少看到 `capcut_helper.app/` 和 `capcut_helper.zip`。

Run: `du -sh capcut_helper/dist/capcut_helper.app capcut_helper/dist/capcut_helper.zip`
Expected: `.app` 约 200-400 MB（含 Python 解释器、numpy、Pillow 等），`.zip` 约 70-150 MB（ditto 压缩比）。具体数值不严格，只要不是 KB 级（说明几乎是空的）就行。

Run: `file capcut_helper/dist/capcut_helper.app/Contents/MacOS/capcut_helper`
Expected: 输出含 `Mach-O 64-bit executable arm64`（架构对得上 M 系列 Mac）。

- [ ] **Step 5: Commit**

```bash
git add capcut_helper/scripts/build_mac.sh capcut_helper/.gitignore
git commit -m "build(capcut_helper): 加 build_mac.sh 脚本 + gitignore 构建产物"
```

---

## Task 5: README + 手动冒烟测试 + 跨机验证

**Files:**
- Create: `capcut_helper/README.md`

写一份项目级 README，覆盖：项目简介、开发者用法、分发流程、首次打开的 Gatekeeper 与权限提示说明。再人工跑完 spec §8 的完整冒烟测试清单。

- [ ] **Step 1: 写 README.md**

`capcut_helper/README.md`：

```markdown
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

\`\`\`bash
cd backend
uv sync
uv run pytest                  # 跑测试
uv run python -m app.main      # 启 pywebview 窗口（先 cd frontend && npm run build）
\`\`\`

前端（开发态用 Vite dev server，自带 /api 代理到 127.0.0.1:9527）：

\`\`\`bash
cd frontend
npm install
npm run dev                    # http://localhost:3176
npm run test                   # Vitest
\`\`\`

## 打包成 .app 分发

\`\`\`bash
bash scripts/build_mac.sh
\`\`\`

产物：

- `dist/capcut_helper.app` —— 双击运行
- `dist/capcut_helper.zip` —— 分发用，用 Apple 推荐的 `ditto` 打包（保留符号链接）

## 分发给同事

把 `dist/capcut_helper.zip` 发给对方，请对方按以下步骤：

1. 解压 zip，把 `capcut_helper.app` 拖到 `~/Applications` 或任意位置
2. **首次打开**：因为未做代码签名，macOS 会拦截。**右键 → 打开 → 在弹窗里再点「打开」**，之后双击就行。或在「系统设置 → 隐私与安全」里允许。
3. **首次访问草稿目录时**，近版 macOS 会再弹一个文件夹访问权限提示（针对 `~/Movies` 或自定义草稿目录），点「允许」即可
4. 启动后第一次进 GUI，按「设置」标签里的「自动探测」找剪映草稿目录，或手动选择

应用窗口里的「活动」「草稿」「设置」三个标签——其中「设置」配剪映草稿根目录是首次必做的事。

## 已知限制

- 仅 macOS arm64（M 系列 Mac）。Intel Mac / Windows 暂不支持，见 `docs/superpowers/specs/2026-05-15-capcut-helper-packaging-design.md` §9。
- 剪映 10.5+ 草稿编辑保存后会加密，capcut_helper 只能**新建**草稿、不能改剪映动过的草稿。详见 spec §2 实测约束。
```

> 注：上面 markdown 里的 \`\`\` 是实际代码块的转义形式，写到文件里时去掉反斜杠。这里因为这份 plan 本身是 markdown 嵌套展示，所以转义了。直接复制黏贴到 README.md 时把 `\`\`\`` 还原成 \`\`\` 即可。

- [ ] **Step 2: Commit README**

```bash
git add capcut_helper/README.md
git commit -m "docs(capcut_helper): 项目级 README 含开发/打包/分发流程"
```

- [ ] **Step 3: 人工冒烟测试（按以下清单逐项过）**

> 这是**人工**步骤，agentic worker 跑不动 GUI；记录每项结果，全过才能算 Task 5 完成。前置：Task 4 的 `dist/capcut_helper.app` 已存在。

1. **双击 .app**：在 Finder 里双击 `capcut_helper/dist/capcut_helper.app`。
   - 第一次会弹 Gatekeeper 警告（"无法打开...因为...开发者无法验证"）。**右键 → 打开 → 确认**。
   - 预期：弹出一个 900×640 的原生窗口，标题 `capcut_helper`，加载出 React GUI。

2. **三视图切换**：「活动 / 草稿 / 设置」三个 tab 都能切，没崩没白屏。
   - 预期：活动视图显示空状态文案（如果还没任务）；草稿视图根据 draft_root 是否配置显示对应文案。

3. **状态栏 / 端口可见**：顶部状态栏显示「服务运行中 · 端口 N」（N 是 9527-9536 间某个值，下一步要用）。

4. **后端可达**（在 Terminal 另开一个窗）：

   \`\`\`bash
   curl http://127.0.0.1:<上一步看到的端口>/api/v1/health
   \`\`\`

   预期：返回 JSON，含 `"service": "capcut_helper"`、`"port": N`、`"last_draft_request_at": null`。

5. **原生桥（选目录）**：进「设置」→ 点「选择目录」按钮。
   - 预期：弹出系统原生文件夹选择对话框（不是 web file input）。
   - 选一个目录（可以是任意已存在的临时目录）→ 路径回填到 `draft_root` 输入框 → 点「保存」→ 提示「已保存」。

6. **首次访问草稿目录权限**（若上一步选的是 `~/Movies` 下面的目录）：
   - 预期：macOS 弹「capcut_helper 想访问 Movies 文件夹的文件」类提示，点「允许」。
   - 若选的是其他位置（如 `/tmp/test_drafts`），可能没有这个提示，跳过即可。

7. **端到端导入（用 curl 模拟 ai-canvas）**：

   先在 Terminal 里准备一个简单 POST：

   \`\`\`bash
   PORT=<状态栏看到的端口>
   curl -X POST http://127.0.0.1:$PORT/api/v1/drafts \\
     -H 'Content-Type: application/json' \\
     -d '{
       "draft_name": "smoke_test",
       "canvas": {"width": 1920, "height": 1080, "fps": 30},
       "tracks": [{
         "type": "video",
         "segments": [{
           "material": {
             "url": "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/BigBuckBunny.mp4",
             "type": "video",
             "filename": "BigBuckBunny.mp4"
           },
           "timeline": {"start": 0, "duration": 5000000}
         }]
       }]
     }'
   \`\`\`

   预期：返回 `{"code":0,"message":"ok","data":{"task_id":"..."}}`。

   切回 GUI「活动」视图，1.5 秒内出现 `smoke_test` 卡片，依次走 `下载素材中` → `生成草稿中` → `已完成`（或 `失败` + 错误文本——网络问题就是失败，能看到 error 字段说明端到端通了）。

   若 `已完成`：点卡片上的「在访达打开」按钮，预期 Finder 打开并选中 `smoke_test` 草稿目录。

8. **关窗口**：直接关 .app 窗口，进程应自然退出（uvicorn 后台线程是 daemon，会跟着主线程一起死）。

- [ ] **Step 4: 跨机验证（可选但推荐）**

把 `dist/capcut_helper.zip` 通过 AirDrop / scp / 网盘传到**另一台 Mac**（最好是没装过 Python/uv 的同事机器）。对方按 README 「分发给同事」段的步骤解压打开。

如果没有第二台 Mac：在本机新建一个干净的 macOS 用户账号，登入后用 Finder 双击 `.app`（这个账号没装 uv/Node，能更接近真实分发环境）。

预期：所有 Step 3 的项目在第二台/第二账号上同样通过。

- [ ] **Step 5: 把冒烟结果记到 git commit message 里（不修改任何代码）**

冒烟结束后，做一个空 commit 记录验证状态：

\`\`\`bash
git commit --allow-empty -m "test(capcut_helper): Plan 3 .app 手动冒烟测试通过

涵盖 spec §8 全部 5 项:
- 双击打开窗口
- 三视图切换
- /health curl
- 原生桥(选目录)
- 端到端导入测试
跨机验证: <YES/NO> + 简述
"
\`\`\`

（如果有任何项失败，先回到 Task 3 / Task 4 修问题，不能用空 commit 假装通过。）

---

## Self-Review

**1. Spec 覆盖（设计文档 9 节逐项核对）：**

| spec 章节 | 对应 task |
|---|---|
| §1 项目目标（Mac arm64 .app） | Task 3+4 |
| §2.1 核心范围（.app、构建脚本、normpath 修复） | Task 1（normpath）、Task 3（spec）、Task 4（脚本） |
| §2.2 非目标（签名 / DMG / Windows / universal2 / auto-update） | 不实现，README 「已知限制」段引用 spec §9 |
| §3 工具与产物（PyInstaller、`.spec`、arm64-only、ditto） | Task 3（PyInstaller、.spec）、Task 4（ditto） |
| §4 Bundle 内容（datas、collect_all、collect_data_files） | Task 3（.spec 文件正是这套） |
| §5 运行时路径解析（`_resource_path`） | Task 2 |
| §6 构建脚本 + .spec BUNDLE 配置 + .gitignore | Task 3（.spec BUNDLE 全配齐）、Task 4（脚本 + gitignore） |
| §7 Plan 2 遗留 normpath | Task 1 |
| §8 冒烟测试（5 项 + 跨机验证） | Task 5 Step 3-4 |
| §9 已知风险 & 后续项（pywebview hidden imports / libmediainfo / 模板路径 / Windows / universal2 / 签名等） | Task 4 troubleshooting checklist；其他未来项不在本计划范围，由 README「已知限制」段标注 |

无遗漏。

**2. 占位符扫描：** 无 TBD / TODO。Task 5 Step 3 是「人工动作」明确标注且给出具体步骤，不是 placeholder。

**3. 类型/命名一致性：**
- `_resource_path(rel)` Task 2 定义，`_FRONTEND_DIST = _resource_path("frontend/dist")` 同任务调用一致。
- `.spec` 文件名 `capcut_helper.spec` 在 Task 3 Step 2 定义、Task 4 build_mac.sh Step 1 引用一致。
- `bundle_identifier='com.cookaihq.capcut_helper'` 在 Task 3 spec、README 内提及一致。
- `--distpath=../dist --workpath=../build` 在 Task 4 脚本里用，对应 `.gitignore` 加 `/build/` `/dist/`，路径关系自洽。
- Task 1 测试用 `os.path.normpath(raw)` 计算期望值，与 Task 1 Step 3 bridge.py 里 `normalized = os.path.normpath(path)` 一致——同一个函数，没漂移。
