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

`scripts/release.sh` 会按顺序完成：跑测试 → 构建 .app/.zip → push main → push tag `v0.1.1` →
调 GitHub API 创建 release → 上传 `capcut_helper.zip` 资产。失败时会指出已推 tag 怎么清理。

发布后，已装上旧版的同事下次启动 helper 时会自动看到「发现新版本 v0.1.1」横幅。

> **版本号约定**：tag 必须 `v` + SemVer（`update_checker._strip_v_prefix` 按这个格式解析）；
> zip 资产名必须是 `capcut_helper.zip`（`scripts/build_mac.sh` 产物名 + `services/update_checker.py::ASSET_NAME` 匹配该名）。脚本已硬编码这两个约定，按它来就行。

## 打包成 .app 分发

```bash
bash scripts/build_mac.sh
```

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
