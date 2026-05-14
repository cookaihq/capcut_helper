# capcut_helper 后端本地服务

剪映外挂助手的后端：FastAPI 本地服务，对外提供「从时间线规格新建剪映草稿」的 HTTP API。
设计文档见 `../docs/superpowers/specs/2026-05-14-capcut-helper-local-service-design.md`。

## 环境要求

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) 包管理

## 开发

```bash
uv sync                          # 安装依赖
uv run python -m app.main        # 启动服务（端口段 9527-9536 内自动选）
uv run pytest                    # 跑全部测试
uv run pytest tests/test_api.py  # 跑单个测试文件
```

## API

所有响应为 `{code, message, data}` 格式，前缀 `/api/v1`：

- `GET /health` — 健康检查 + 服务身份标识（端口发现用）
- `POST /drafts` — 提交时间线规格，返回 `task_id`
- `GET /tasks/{task_id}` — 查任务进度/状态/结果
- `GET /drafts` — 列出剪映草稿根目录下的草稿
- `GET /config` `PUT /config` — 读写配置（剪映草稿根目录、端口段、CORS 白名单）

## 配置

配置存在用户配置目录（由 `platformdirs` 决定，如 macOS 的 `~/Library/Application Support/capcut_helper/config.json`）。
首次使用需通过 `PUT /config` 设置 `draft_root`（剪映草稿根目录）。

## 已知约束

剪映 6+ 草稿文件加密，本服务只能**新建**草稿，不能读取/修改剪映已保存过的草稿。详见设计文档第 2 节。
