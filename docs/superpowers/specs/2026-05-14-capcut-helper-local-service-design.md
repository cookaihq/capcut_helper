# capcut_helper 本地服务 — 设计文档

> 创建日期：2026-05-14
> 状态：Plan 1（后端本地服务）已实现并合入 main。2026-05-15 增补第 12 节「桌面 GUI 设计」（Plan 2）。
> 范围：核心功能（桌面端本地服务 + 新建草稿 API + 桌面 GUI）。两个扩展功能（素材位置归一、云端同步）各自单独立 spec。

## 1. 项目目标

`capcut_helper` 是一个跨平台桌面应用，启动后在本地起一个 FastAPI 服务，供其他程序（首要是同 monorepo 下的 `ai-canvas`）调用。核心用途：把网页里排好的时间线素材，按规格生成一个剪映草稿，素材自动下载进草稿文件夹，用户随后在剪映里打开继续编辑。

## 2. 背景与核心约束（实测证实）

操作剪映草稿使用 Python 库 [pyJianYingDraft](https://github.com/GuanYixuan/pyJianYingDraft)（仅支持剪映国内版）。

2026-05-14 在目标机器（macOS，剪映 10.5 / `VideoFusion-macOS.app`）上实测：

| 操作 | 结果 |
|------|------|
| pyJianYingDraft 新建明文草稿 → 剪映 10.5 打开 | ✅ 能正常打开 |
| 素材文件复制进草稿文件夹 → 剪映读取素材 | ✅ 正常 |
| 剪映编辑保存后 → pyJianYingDraft 再读取 | ❌ `draft_content.json` 被加密，`load_template()` 报 `JSONDecodeError` |
| 修改剪映动过的草稿 | ❌ 读不了，改无从谈起 |

**结论**：剪映 6+ 对草稿文件加密，社区截至 2026-02 未攻破。可行的工作流是**严格单向**的：

```
pyJianYingDraft 生成草稿  ──→  剪映打开/编辑  ──→  剪映保存（加密锁死）
        ✅ 通                                       ❌ 此后助手再也碰不了
```

其他平台/版本约束：pyJianYingDraft 的「模板模式」（读取并修改已有草稿）仅支持剪映 5.9 及以下；macOS 不支持自动导出成片（草稿需在 Windows 剪映导出）。这些不影响核心的「新建草稿」路径。

## 3. 范围

### 3.1 核心范围（本 spec）

- Python 桌面应用：pywebview + React GUI，跨平台（macOS + Windows）
- 本地 FastAPI 服务，固定默认端口，对外暴露业务 API
- 核心能力：**从时间线规格新建剪映草稿**
- 素材并发下载进草稿文件夹（自包含草稿）
- 桌面 GUI：三个视图（活动 / 草稿 / 设置）+ 常驻状态栏，详见第 12 节
- pywebview 原生桥：仅处理系统外壳操作（文件夹选择对话框、在访达/资源管理器打开、探测剪映草稿根目录）

### 3.2 非目标（不在本 spec）

- **追加/修改已有草稿**：实测不可行（见第 2 节），记为「已知受阻、等加密被攻破」，不实现
- **素材位置归一**：针对外部创建的草稿统一素材目录 —— 单独立 spec
- **云端同步**：草稿同步到用户自配的 S3/OSS —— 单独立 spec
- **自动导出成片**：剪映自身能力，助手不介入
- 时间线编排 UI：由用户自行在 `ai-canvas` 中实现，不属于本项目

## 4. 架构

**单进程结构（方案 A）**：一个 Python 进程。FastAPI 在固定端口监听，一肩挑两件事：

1. 托管打包好的 React GUI 静态文件（挂在 `/`）
2. 暴露 `/api/v1/...` 业务接口，供 ai-canvas 和 GUI **共用同一套 API**

pywebview 开一个原生窗口，指向 `http://localhost:<端口>/`。

**为什么是方案 A 而非「GUI 走 pywebview 桥」**：业务能力只实现一遍，GUI 跑通即等于对外 API 跑通（自己吃狗粮），不会出现两条路漂移；React GUI 可在普通浏览器里开发调试；只有一套传输层要维护。同进程 localhost 回环没有真实网络的可靠性问题。pywebview 桥只保留给 webview 干不了的原生系统操作。

## 5. 组件

| 组件 | 职责 |
|------|------|
| 本地服务（FastAPI） | HTTP 入口、CORS、托管 GUI、路由转发到 service |
| 时间线规格 schema | API 契约，ai-canvas 传入的 JSON 结构（Pydantic 定义） |
| 草稿构建 service | 把时间线规格翻译成 pyJianYingDraft 调用 |
| 素材下载器 | 把素材 URL 并发下载进草稿文件夹，按内容哈希去重 |
| 后台任务运行器 | 跑「建草稿 + 下素材」长任务，对外暴露进度 |
| jianying 集成层 | 包装 pyJianYingDraft（`create_draft`、`add_track`、`add_segment`、`save`） |
| 原生桥（pywebview js_api） | 系统外壳操作：文件夹选择框、在访达/资源管理器打开、探测剪映草稿根目录 |
| React GUI | pywebview 窗口内的监控/设置面板：活动、草稿、设置三视图 + 常驻状态栏，详见第 12 节 |
| 配置 | 端口段、剪映草稿根目录、CORS 白名单 |

## 6. 项目结构

```
capcut_helper/
├── backend/app/
│   ├── main.py            # 入口：起 FastAPI + pywebview 窗口
│   ├── server.py          # FastAPI app，挂 API + GUI 静态文件
│   ├── api/               # 路由处理（薄，转发给 service）
│   ├── services/          # 业务逻辑：草稿构建、素材下载
│   ├── integrations/jianying/  # pyJianYingDraft 包装
│   ├── schemas/           # Pydantic：时间线规格、响应
│   ├── core/              # 配置、异常、任务注册表
│   ├── native/            # pywebview js_api 桥（系统外壳操作）
│   └── tasks/             # 后台任务运行器
├── frontend/              # React + Vite GUI
├── tests/                 # 测试（含实测用的视频片段）
└── docs/
```

## 7. API 契约

所有响应包裹为 `{code, message, data}` 格式。

| 端点 | 作用 |
|------|------|
| `GET /api/v1/health` | 健康检查 + 服务身份标识，ai-canvas 探测端口时用（见 7.3） |
| `POST /api/v1/drafts` | 提交时间线规格，新建草稿 → 立即返回 `task_id` |
| `GET /api/v1/tasks/{task_id}` | 查任务进度/状态/结果（草稿路径） |
| `GET /api/v1/drafts` | 列出助手建过的草稿（GUI 展示用） |
| `GET /api/v1/config` `PUT /api/v1/config` | 读写配置（剪映草稿根目录、端口等） |

以上是 Plan 1 已交付的契约。Plan 2 会新增 `GET /api/v1/tasks`（列出所有任务）并扩展 `GET /api/v1/health`、`TaskState`，详见第 12.5 节。

### 7.1 时间线规格（`POST /api/v1/drafts` 请求体）

```jsonc
{
  "draft_name": "我的视频",
  "allow_replace": false,           // 草稿名重名时是否覆盖，默认 false
  "canvas": { "width": 1920, "height": 1080, "fps": 30 },
  "tracks": [
    {
      "type": "video",              // video | audio | text
      "segments": [
        {
          "material": {
            "url": "https://...",   // 远程素材 URL
            "type": "video",        // video | image | audio
            "filename": "clip1.mp4"
          },
          "timeline": { "start": 0, "duration": 9160000 },      // 时间线上的位置，单位微秒
          "source": { "start": 0, "duration": 9160000 },        // 素材内裁剪范围，可选
          "text": { "content": "...", "style": {} }             // text 轨道用，可选
        }
      ]
    }
  ]
}
```

响应：`{ "code": 0, "message": "ok", "data": { "task_id": "..." } }`

骨架定型为：**画布参数 + 多轨道，每轨道一串「素材 + 时间线位置 + 裁剪范围」的片段**。转场、特效、动画等字段在实现阶段按 pyJianYingDraft 能力增补。

### 7.2 任务状态（`GET /api/v1/tasks/{task_id}` 响应）

`data` 含：`status`（pending / downloading / building / done / failed）、`progress`（0–100）、`result`（成功时为草稿文件夹路径）、`error`（失败时为错误详情，含具体哪个素材失败）。

### 7.3 health 响应与端口发现

桌面端不绑死单一端口：从一个约定的小端口段（如 `9527–9536`）里挑，被占则顺延到下一个空闲端口。

`GET /api/v1/health` 的 `data` 返回**服务身份标识**：`{ "service": "capcut_helper", "version": "...", "port": <实际端口> }`。

ai-canvas 发现端口的流程：
1. 优先读自己 localStorage 里上次成功的端口，先试它
2. 没有或失败，则依次 `fetch` 端口段里每个端口的 `/api/v1/health`
3. 收到响应且 `data.service === "capcut_helper"` 才认定连上（避免误连到其他本地服务）
4. 连上后把端口写回 ai-canvas 自己的 localStorage，下次优先用

桌面端无法写浏览器 localStorage（origin 隔离），所以端口发现由网页侧主动探测完成，全程无需用户手动配置。仅当整个端口段都被占用这种极端情况，才回退到「桌面端 GUI 显眼展示端口 + 系统通知 + 用户在 ai-canvas 手动填端口」。

桌面端 GUI 额外记录「最近一次收到 ai-canvas 请求的时间」，据此显示「已连接 / 未连接」状态。

## 8. 数据流

一次导入发生了什么：

1. ai-canvas 排好时间线，点「导入剪映」→ `POST /api/v1/drafts`
2. 服务校验时间线规格 → 建一个后台任务 → **立即返回 `task_id`**（不阻塞）
3. 后台任务依次：
   1. 算出草稿文件夹路径（剪映草稿根目录下，名为 `draft_name`）
   2. `create_draft` 建空草稿（**注意顺序坑**：`create_draft(allow_replace=True)` 会 `rmtree` 整个文件夹，所以必须先建草稿、再下素材）
   3. 把所有素材 URL **并发下载**进草稿文件夹，按内容哈希去重
   4. 用文件夹内的本地路径构造 `VideoMaterial` / `AudioMaterial`，逐轨 `add_track`、逐段 `add_segment`
   5. `script.save()` 写出明文 `draft_content.json`
   6. 全程更新任务进度
4. ai-canvas 轮询 `GET /api/v1/tasks/{task_id}` 拿进度
5. 完成后剪映里出现新草稿，用户打开继续编辑；GUI 草稿列表同步刷新

## 9. 错误处理

| 场景 | 处理 |
|------|------|
| 端口被占 | 桌面端在约定端口段内自动顺延到下一个空闲端口（见 7.3）；ai-canvas 通过探测端口段的 `/health` 自动发现，无需手动配置。仅当整段都被占才回退到 GUI 显眼展示端口 + 系统通知 + 手动填端口 |
| 素材下载失败 | 单个素材重试 N 次，仍失败则整个任务失败，错误信息明确指出是哪个素材 |
| 草稿根目录未配置/不存在 | GUI 引导用户去设置里选目录（走原生文件夹对话框） |
| 时间线规格非法 | Pydantic 校验，返回 422 + 字段级错误 |
| 跨域 + 防滥用 | CORS origin 白名单（ai-canvas 的开发端口 + 部署域名，作为桌面端默认常量内置、GUI 可改）+ 服务只绑定 localhost。API 为 JSON 接口，浏览器对未知 origin 的跨域请求会被 preflight 预检拦下，故不再需要 token。残留风险：本机任意进程可调用 API，对个人/小团队工具可接受 |
| 草稿名重名 | 默认不覆盖，返回冲突错误；覆盖与否由调用方通过 `allow_replace` 显式指定 |
| 剪映已锁定/打开该草稿 | 检测草稿文件夹内的锁文件，提示用户先关闭剪映再重试 |

## 10. 测试策略

- **单元**：时间线规格 → pyJianYingDraft 调用的映射；素材下载器（去重、重试）
- **集成**：`POST /drafts` → 任务跑完 → 校验生成的 `draft_content.json` 结构正确（画布、轨道数、片段时间范围、素材路径指向文件夹内副本）
- **端到端**：生成的草稿用剪映实际打开确认能正常加载、素材不丢失
- **跨平台**：macOS / Windows 的路径处理、草稿根目录探测、打包各测一遍
- **GUI**：开发期直接在 Chrome 里连本地服务调试，跑通即说明对外 API 也跑通

## 11. 未决/后续

- 时间线规格的转场、特效、动画、关键帧等高级字段，在实现阶段按 pyJianYingDraft 实际能力增补
- 打包方案（PyInstaller / briefcase 等）在实现计划里定 —— 归入 Plan 3，本 spec 不展开
- 「追加/修改已有草稿」：等剪映草稿加密被社区攻破后再评估
- 扩展功能「素材位置归一」「云端同步」各自单独 brainstorming + spec

## 12. 桌面 GUI 设计（Plan 2）

> 2026-05-15 增补。本节细化第 5 节「React GUI」一行。对应实现计划 Plan 2（pywebview 桌面壳 + 原生桥 + React GUI）。跨平台打包是 Plan 3，不在本节范围。

### 12.1 定位

GUI 是一个**监控 / 设置面板**，不是创作工具。真正的时间线编排在 `ai-canvas` 里完成。GUI 自己**不发起导入任务**——它只展示后端状态、列出已建草稿、改配置。用户在这个面板里做的事：确认服务在跑、看导入任务的进度与结果、出问题时看错误、配置剪映草稿目录等。

### 12.2 技术栈与运行方式

- **技术栈**：React + Vite + Ant Design 5（与 `ai-canvas`、`ai-tools-web` 一致）。代码在新目录 `capcut_helper/frontend/`。
- **托管**：`frontend/` 构建出静态文件，后端 `server.py` 加 `StaticFiles` 挂载，把构建产物挂在 `/`。
- **启动**：`main.py` 重构——uvicorn 跑在后台守护线程；主线程先轮询 `/api/v1/health` 等服务就绪（带超时），再用 pywebview `create_window` 开原生窗口指向 `http://127.0.0.1:<端口>/`，然后 `webview.start()`（pywebview 要求在主线程跑 GUI 循环）。
- **通信**：GUI 与后端**只通过现有 `/api/v1` HTTP API 通信**——和 ai-canvas 共用同一套接口（设计文档方案 A，自己吃狗粮）。唯一例外是「系统外壳操作」走 pywebview js_api 桥（见 12.7）。
- **开发**：`frontend/` 可在普通浏览器跑 Vite dev server、连本地后端调试；js_api 桥在浏览器里不存在，开发期对桥调用做特性检测降级（见 12.7）。

### 12.3 整体布局

顶部标签页布局（窗口不大，3 个视图，顶部标签最省空间）：

```
┌─────────────────────────────────────────────────────────┐
│ ● 服务运行中 · 端口 9527        最近导入请求：2 分钟前    │ ← 常驻状态栏
├─────────────────────────────────────────────────────────┤
│ ⚠ 还没设置剪映草稿目录，导入会失败        [去设置]      │ ← 引导横幅（条件显示）
├─────────────────────────────────────────────────────────┤
│  [ 活动 ]   草稿    设置                                 │ ← 顶部标签
├─────────────────────────────────────────────────────────┤
│                                                         │
│                  当前标签的视图内容                      │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

- **常驻状态栏**（跨所有视图）：左侧「● 服务运行中 · 端口 N」——GUI 自己请求 `/api/v1/health` 即可得知；右侧「最近导入请求：X 前」或「尚无导入请求」——来自 `/health` 新增的 `last_draft_request_at` 字段（见 12.5）。
- **引导横幅**（条件显示）：启动时若 `GET /config` 的 `draft_root` 为空 → 调原生桥 `detect_draft_root()`。探测到 → 横幅「检测到剪映草稿目录：`<路径>`　[使用]　[手动选择]」，点「使用」即 `PUT /config` 写入；没探测到 → 横幅「⚠️ 还没设置剪映草稿目录，导入会失败　[去设置]」，点击跳到「设置」标签。`draft_root` 配置好后横幅消失。不锁死其他视图。
- **顶部标签**：活动 / 草稿 / 设置。默认停在「活动」。

### 12.4 三个视图

**视图 1 · 活动**（默认标签）：导入任务的监控 + 历史，合并了原 spec 的「任务进度」与「日志」。

- 挂载时每 ~1.5 秒轮询 `GET /api/v1/tasks`（见 12.5），视图卸载时清除定时器。
- 任务卡片列表，按 `created_at` 时间倒序。每张卡片显示草稿名 + 状态：
  - 进行中（`pending` / `downloading` / `building`）：显示当前阶段文字 + 进度条（用 `status` 和 `progress`）。
  - 已完成（`done`）：显示草稿文件夹路径 + 「在访达/资源管理器打开」按钮（走原生桥 `reveal_in_os`）。
  - 失败（`failed`）：红色显示 `error` 文本。
  - 每张卡片显示相对时间（来自 `created_at`）。
- 空状态：「还没有导入任务。在 ai-canvas 里排好时间线点导入，这里会显示进度。」

**视图 2 · 草稿**：列出剪映草稿根目录下的草稿。

- 挂载时 + 手动刷新按钮触发 `GET /api/v1/drafts`，拿到草稿文件夹名列表。
- 每行：草稿名 + 「在访达/资源管理器打开」按钮（原生桥 `reveal_in_os`，路径为 `draft_root/<名字>`）。
- 空状态两种：`draft_root` 未配置 → 「未配置剪映草稿目录」；已配置但目录下无草稿 → 「草稿根目录下还没有草稿」。（后端 `GET /drafts` 在 `draft_root` 无效时已返回空数组。）

**视图 3 · 设置**：读写后端配置。

- 挂载时 `GET /api/v1/config` 拉出表单：
  - `draft_root`：文本框 + 「选择目录」按钮（原生桥 `pick_folder`）+ 「自动探测」按钮（原生桥 `detect_draft_root`）。
  - `port_range`：起、止两个数字输入框；附提示「修改端口段需重启应用生效」。
  - `cors_origins`：可增删的字符串列表。
- 「保存」按钮 → `PUT /api/v1/config`；校验失败（HTTP 422）→ 表单内联报错。

### 12.5 Plan 2 需要的后端补充

GUI 暴露出 Plan 1 后端的几处缺口，Plan 2 一并补上（均走 pytest TDD，与 Plan 1 一致）：

1. **`GET /api/v1/tasks`** —— 新增接口，列出所有任务状态，按 `created_at` 时间倒序。`data` 为任务对象数组。
2. **`TaskState` 扩展** —— 增加 `draft_name` 和 `created_at` 字段。`POST /drafts` 路由创建任务时把 `spec.draft_name` 传入；`registry.create()` 记录 `created_at`。`to_dict()` 相应包含新字段。
3. **`GET /api/v1/health` 扩展** —— `data` 增加 `last_draft_request_at`（最近一次 `POST /drafts` 被调用的时间戳，无则为 `null`）。后端在 `POST /drafts` 处理时更新这个进程级时间戳。
4. **`server.py` 静态托管** —— 新增 `StaticFiles` 挂载，把 `frontend/` 构建产物挂在 `/`。
5. **`main.py` 重构** —— uvicorn 后台线程 + 主线程 pywebview 窗口（见 12.2）。
6. **`app/native/bridge.py`** —— 新增 pywebview js_api 桥类（见 12.7）。

### 12.6 数据流

纯轮询，GUI 是被动监控方：

- 「活动」视图：挂载时起 ~1.5s 间隔轮询 `GET /tasks`，卸载清除定时器。
- 「草稿」视图：挂载时 + 手动刷新触发 `GET /drafts`。
- 「设置」视图：挂载时 `GET /config`；保存时 `PUT /config`。
- 状态栏：挂载时 + 定期（数秒级）刷新 `GET /health`，保持「最近导入请求」时间新鲜。

### 12.7 原生桥接口（pywebview js_api）

`app/native/bridge.py` 定义一个类作为 `create_window` 的 `js_api`，方法在 JS 侧通过 `window.pywebview.api.<方法>()` 调用、返回值为 Promise：

| 方法 | 行为 | 返回 |
|------|------|------|
| `pick_folder()` | 调 pywebview `window.create_file_dialog(FOLDER_DIALOG)` 打开文件夹选择对话框 | 选中的目录路径字符串；用户取消则 `None` |
| `reveal_in_os(path)` | 在系统文件管理器里定位该路径（macOS `open`，Windows `explorer`） | 无 |
| `detect_draft_root()` | 按平台推断剪映默认草稿目录（如 macOS `~/Movies/JianyingPro/...`），检查目录是否存在 | 存在则返回路径字符串，否则 `None` |

前端对桥调用做特性检测：`window.pywebview` 不存在时（浏览器开发环境）相关按钮禁用或降级为手动输入，不报错。

### 12.8 错误处理

| 场景 | 处理 |
|------|------|
| 启动竞态期后端还没起 | GUI 显示「连接本地服务中…」并重试 `GET /health`，连上后进入主界面 |
| `GET /drafts` 草稿目录无效 | 后端已返回空数组，GUI 按 12.4 的空状态展示 |
| `PUT /config` 校验失败（422） | 表单内联展示字段级错误 |
| 原生桥用户取消选择 | `pick_folder` 返回 `None`，前端静默不动作 |
| 任务失败 | 「活动」视图卡片里红色展示 `error` 文本（无需额外处理） |

### 12.9 测试策略

- **后端 6 项补充**（12.5）：全走 pytest TDD，与 Plan 1 一致。`detect_draft_root` 的路径推断逻辑可单测；`pick_folder` / `reveal_in_os` 是薄 OS 调用，归为手动验证。
- **前端**：用 Vitest 测纯逻辑（相对时间格式化、任务卡片状态派生等）；UI 本身在 Chrome 连本地后端手动验证（与第 10 节「GUI 开发期在 Chrome 调试」一致）。
- **pywebview 集成**：开窗口 + 静态挂载 = 手动冒烟测试（启动应用，窗口打开，三视图可用）。
