# capcut_helper 跨平台打包 — 设计文档（Plan 3）

> 创建日期：2026-05-15
> 状态：brainstorming 完成，待写实现计划
> 范围：把 Plan 1 + Plan 2 已完成的 dev-mode 桌面应用打成可分发的 Mac `.app`。
> 前置：Plan 1（后端本地服务）+ Plan 2（桌面 GUI）已合入 `main`，`uv run python -m app.main` 能正常起 pywebview 窗口。

## 1. 项目目标

把 `capcut_helper` 打包成可双击运行的 Mac `.app`，分发给小团队（自己 + 几个同事）使用，不需要他们的机器装 Python / uv / Node。

## 2. 范围

### 2.1 核心范围（本 spec）

- macOS arm64 `.app` bundle（PyInstaller）
- 一条命令的构建脚本：拉前端构建产物 + 跑 PyInstaller
- 顺手修掉 Plan 2 final review 里 flag 的 `reveal_in_os` Windows 路径分隔符未归一化

### 2.2 非目标

- **代码签名 / Apple 公证**：内部分发，用户首次打开手动绕过 Gatekeeper（README 说明）
- **DMG / 安装器**：直接 zip `.app` 分发
- **Windows .exe**：用户在 Mac 上、PyInstaller 不能交叉编译；同事也多为 Mac。真有 Windows 需求时再单独立计划（GitHub Actions 或借 Windows 机器）
- **auto-update**：手动重新分发新版本
- **Intel Mac（universal2）**：见 §9 已知后续项，不是简单的 flag 切换

## 3. 工具与产物

**工具**：PyInstaller。理由：pywebview + FastAPI + pyJianYingDraft 这种「Python + WebView + 资源文件」组合在 pywebview 官方文档与社区里几乎都是 PyInstaller。py2app 在 pywebview 场景实例少；Briefcase（BeeWare）一站式打包/签名/分发对「zip 一个 .app 给同事」属于过度方案。

**配置形式**：`.spec` 文件（不用 `--onefile` CLI 形式），便于声明 `datas` / `hiddenimports` / `BUNDLE` Mac `.app` 配置。

**产物**：`capcut_helper/dist/capcut_helper.app`（项目级 `dist/`，不是 `backend/dist/`——构建脚本通过 `--distpath=../dist --workpath=../build` 显式定位）。

**架构**：arm64-only（M 系列 Mac）。

**分发**：`zip -r capcut_helper.zip capcut_helper.app` 直接发给同事。首次打开因为未签名会弹 Gatekeeper 警告，需右键→打开或系统设置→隐私与安全里允许。README 写清楚。

## 4. Bundle 内容

PyInstaller 自动嵌入：
- Python 3.13 解释器
- 后端依赖：FastAPI、uvicorn、pywebview、pyobjc-*（Mac WKWebView 桥需要的 Cocoa 绑定）、pyJianYingDraft、Pillow、numpy、pymediainfo（含 `libmediainfo.dylib` 原生库）、httpx、platformdirs

通过 `.spec` 的 `datas=` 显式加入：
- `frontend/dist/`（React 构建产物），运行时挂在 FastAPI `StaticFiles`
- pyJianYingDraft 自带的资源文件（如 `DRAFT_META_TEMPLATE`），用 `collect_data_files('pyJianYingDraft')` 收集

通过 `collect_all('pywebview')` 兜底 pywebview 的所有子模块（macOS 后端 `pywebview.platforms.cocoa` 历来是 PyInstaller 易漏的 hidden import，`collect_all` 一并解决数据 + 模块）。

## 5. 运行时路径解析

冻结后 `__file__` 不再指向源码树。`server.py` 当前的：

```python
_FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
```

**在 .app 里会失效**。PyInstaller 暴露 `sys._MEIPASS`（bundle 数据根目录），改成：

```python
import sys
from pathlib import Path

def _resource_path(rel: str) -> Path:
    """开发模式下从源码树解析；冻结后从 PyInstaller bundle 解析。"""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / rel
    return Path(__file__).resolve().parents[2] / rel

_FRONTEND_DIST = _resource_path("frontend/dist")
```

`.spec` 里 `datas=[("../frontend/dist", "frontend/dist")]`（src 相对于 spec 所在目录 `backend/`，dst 是 bundle 内相对路径），运行时 `sys._MEIPASS / "frontend/dist"` 命中。

## 6. 构建脚本

`capcut_helper/scripts/build_mac.sh`：

```bash
#!/usr/bin/env bash
set -e
cd "$(dirname "$0")/.."   # → capcut_helper/

echo "→ 1/2 构建前端"
( cd frontend && npm install && npm run build )

echo "→ 2/2 PyInstaller 打包 .app"
( cd backend && uv run pyinstaller --clean --noconfirm \
    --distpath=../dist --workpath=../build \
    capcut_helper.spec )

echo "→ 产物: $(pwd)/dist/capcut_helper.app"
```

PyInstaller 加进 `backend/pyproject.toml` 的 `[dependency-groups] dev`（不污染运行时依赖）。`.spec` 文件落在 `backend/capcut_helper.spec`，要点：

- `Analysis(['app/main.py'], ...)`
- `datas` 含 frontend/dist + `collect_data_files('pyJianYingDraft')`
- `hiddenimports` + `collect_submodules('pywebview')` 或直接 `collect_all('pywebview')`
- `BUNDLE` 段输出 `.app`，`name='capcut_helper.app'`，`bundle_identifier='com.cookai.capcut_helper'`，`info_plist` 至少含 `CFBundleName='capcut_helper'`、`LSBackgroundOnly=False`

`capcut_helper/.gitignore` 加 `build/` 和 `dist/`（PyInstaller 在项目根产生这俩目录）。

## 7. Plan 2 遗留：Windows 路径归一化

Plan 2 final review flag 了 `app/native/bridge.py` 的 `reveal_in_os` 在 Windows 上接到 `${draftRoot}/${name}`（正斜杠）路径直接喂给 `explorer /select,` 不干净。修法：

```python
def reveal_in_os(self, path: str) -> None:
    normalized = os.path.normpath(path)  # Mac 上是 no-op，Windows 上 / → \
    if sys.platform == "darwin":
        subprocess.run(["open", "-R", normalized], check=False)
    elif sys.platform == "win32":
        subprocess.run(["explorer", "/select,", normalized], check=False)
```

加一个相应单测到 `tests/test_native_bridge.py`：monkeypatch `subprocess.run`，验证 mac/win 各传了 normalized 的路径。即使 Plan 3 暂不出 Windows 包，把这个修复在一起做。

## 8. 测试策略

**自动化**（pytest）：
- `reveal_in_os` 的 normpath 行为单测（mac 分支、win 分支各一个）

**手动冒烟**（每次打完 .app 必跑）：
1. 双击 `dist/capcut_helper.app` → 窗口能开（约 900×640）
2. 三视图（活动 / 草稿 / 设置）能切
3. 「设置」里「选择目录」能弹出系统文件夹选择对话框
4. 在另一个终端 `curl http://127.0.0.1:<打印出的端口>/api/v1/health` 确认服务可达且返回 `service: "capcut_helper"`
5. 用 ai-canvas 或 curl POST 一个真实时间线规格，验证草稿能完整生成（前端构建产物 + pyJianYingDraft 资源 + libmediainfo 都被打进去了的端到端确认）

**跨机器验证**（剥离开发机环境依赖）：
- `zip -r capcut_helper.zip capcut_helper.app`，scp 到另一台 Mac（最好是没装 Python/uv 的）解压双击。若没有第二台 Mac，可创建一个干净的 macOS 用户账号登入测试。

PyInstaller 自身的产物结构无法在 pytest 里验证——只能靠手动冒烟。

## 9. 已知风险 & 后续项

**实现阶段需验证**：
- pywebview 在 Mac 上的 hidden imports 是否完全被 `collect_all('pywebview')` 覆盖。若 .app 启动报 `ModuleNotFoundError`，按报错补 `hiddenimports`
- `libmediainfo.dylib`（pymediainfo 的原生依赖）是否被 PyInstaller 钩子自动 pick up。若不行，手动 `binaries=[(...)]`
- pyJianYingDraft 内部对自带模板路径的解析是否兼容 bundle 内的相对路径

**后续项（不在 Plan 3 范围）**：
- **Windows .exe**：用 GitHub Actions windows-latest runner 或 Windows 物理机/VM 构建；流程基本对称，但需单独立计划做实测
- **Intel Mac（universal2）**：不是简单 flag 切换。要求 numpy、Pillow、pyobjc、pymediainfo 等所有原生依赖都有 universal2 wheels。当 arm64 host 上现成 wheels 多为 arm64-only 时，可能需要 cross-arch 装包或重打。真有 Intel Mac 用户时单独评估
- **代码签名 + 公证**：内部分发先不做，未来若公开发布再补
- **DMG / 安装器**：同上
- **auto-update**：同上
