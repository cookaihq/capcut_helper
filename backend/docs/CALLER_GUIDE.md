# capcut_helper 本地服务 — 调用方接入文档

本文档面向**调用 capcut_helper 本地服务的程序开发者**（首要是 `ai-canvas`，也包括其他想把素材导入剪映草稿的本地程序）。

## 1. 这个服务是做什么的

`capcut_helper` 是一个跑在用户本机的桌面应用，启动后在 localhost 起一个 HTTP 服务。调用方把一份「时间线规格」（画布参数 + 多轨道 + 每个片段的素材 URL 和时间位置）POST 给它，它就会：

1. 在剪映草稿根目录下新建一个草稿文件夹
2. 把所有素材 URL 并发下载进这个草稿文件夹（草稿自包含）
3. 用 pyJianYingDraft 把轨道和片段写进草稿
4. 完成后，用户可以直接在剪映里打开这个草稿继续编辑

整个过程是异步的：POST 立即返回一个 `task_id`，调用方轮询任务状态拿进度。

## 2. ⚠️ 必读：核心约束

| 约束 | 说明 |
|------|------|
| **只能新建草稿，不能改已有草稿** | 剪映 6+ 的草稿文件已加密。本服务只能从零创建草稿。用户一旦在剪映里打开并保存过某个草稿，本服务就再也无法读取或修改它。 |
| **时间单位是微秒（μs）** | 所有 `start` / `duration` 字段单位都是微秒。1 秒 = 1_000_000。 |
| **素材必须是可下载的 URL** | 服务端会去 `GET` 这些 URL。不支持本地文件路径、base64、data URI。 |
| **素材会被下载进草稿文件夹** | 草稿是自包含的。注意：草稿里记录的是绝对路径，把草稿文件夹整体移到别的机器路径会失效（「素材路径可移植」是后续扩展功能）。 |
| **导出成片由用户在剪映里做** | 本服务只负责把草稿做好，不负责导出视频。 |

## 3. 服务发现（端口探测）

服务**不绑定固定端口**：它从端口段 `9527–9536` 里挑第一个空闲端口。调用方需要自己探测：

1. 如果之前成功连过，先试上次记住的端口（建议存在你自己的 localStorage）
2. 否则依次 `GET http://localhost:<port>/api/v1/health`，`port` 从 9527 到 9536
3. 收到 200 且响应 `data.service === "capcut_helper"` 才算连上（避免误连到本机其他服务）
4. 连上后把端口记下来，下次优先用

> 服务端无法把端口写进你的浏览器 localStorage（origin 隔离），所以发现端口是调用方的职责。

```js
async function discoverPort() {
  const saved = localStorage.getItem('capcut_helper_port')
  const candidates = saved ? [Number(saved), ...range(9527, 9536)] : range(9527, 9536)
  for (const port of candidates) {
    try {
      const resp = await fetch(`http://localhost:${port}/api/v1/health`, { signal: AbortSignal.timeout(500) })
      const body = await resp.json()
      if (body?.data?.service === 'capcut_helper') {
        localStorage.setItem('capcut_helper_port', String(port))
        return port
      }
    } catch { /* 该端口没服务或不是它，继续试下一个 */ }
  }
  throw new Error('capcut_helper 本地服务未运行（端口段 9527-9536 都没找到）')
}
function range(a, b) { return Array.from({ length: b - a + 1 }, (_, i) => a + i) }
```

如果整段端口都探测不到，说明用户没启动 capcut_helper 桌面应用——提示用户去启动它。

## 4. 跨域（CORS）

服务端只对**白名单内的 origin** 放行跨域请求。默认白名单是 `http://localhost:3182` 和 `http://localhost:3183`（ai-canvas 的开发端口）。

如果你的页面跑在别的 origin（比如部署后的域名），需要让用户在 capcut_helper 桌面应用的设置里把你的 origin 加进 CORS 白名单，或通过 `PUT /api/v1/config` 写入（见 §5.5）。

## 5. API 详解

所有接口前缀 `/api/v1`，所有响应都是统一信封：

```json
{ "code": 0, "message": "ok", "data": <具体数据> }
```

`code` 为 `0` 表示成功，非 0 表示出错（错误码见 §7）。

### 5.1 `GET /health` — 健康检查 / 服务身份

用于端口探测。

响应 `data`：

```json
{ "service": "capcut_helper", "version": "0.1.0", "port": 9527 }
```

### 5.2 `POST /drafts` — 提交时间线规格，新建草稿

请求体是一份「时间线规格」（完整字段见 §6）。最小例子：

```json
{
  "draft_name": "我的视频",
  "canvas": { "width": 1920, "height": 1080, "fps": 30 },
  "tracks": [
    {
      "type": "video",
      "segments": [
        {
          "material": { "url": "https://example.com/clip1.mp4", "type": "video", "filename": "clip1.mp4" },
          "timeline": { "start": 0, "duration": 5000000 }
        },
        {
          "material": { "url": "https://example.com/clip2.mp4", "type": "video", "filename": "clip2.mp4" },
          "timeline": { "start": 5000000, "duration": 8000000 }
        }
      ]
    }
  ]
}
```

成功响应 `data`：

```json
{ "task_id": "3f2a9c1b8e7d4f60a1b2c3d4e5f6a7b8" }
```

拿到 `task_id` 后去轮询 §5.3。

校验失败返回 HTTP 422，`code` 为 `422`，`data` 是字段级错误详情。

```bash
curl -X POST http://localhost:9527/api/v1/drafts \
  -H 'Content-Type: application/json' \
  -d '{ "draft_name": "demo", "canvas": {"width":1920,"height":1080,"fps":30}, "tracks": [...] }'
```

### 5.3 `GET /tasks/{task_id}` — 查任务进度

响应 `data`：

```json
{
  "id": "3f2a9c1b8e7d4f60a1b2c3d4e5f6a7b8",
  "status": "downloading",
  "progress": 30,
  "result": null,
  "error": null
}
```

> 注意字段名：`POST /drafts` 返回的是 `data.task_id`，而这里任务对象里的字段叫 `data.id`——两者是同一个值。

`status` 取值与进度：

| status | progress | 含义 |
|--------|----------|------|
| `pending` | 0 | 任务已创建，还没开始 |
| `building` | 10 | 正在建空草稿文件夹 |
| `downloading` | 30 | 正在并发下载素材 |
| `building` | 70 | 正在写轨道和片段 |
| `done` | 100 | 完成，`result` 是草稿文件夹的绝对路径 |
| `failed` | — | 失败，`error` 是错误描述（会指出是哪个素材/哪一步出的问题） |

轮询到 `done` 或 `failed` 就停止。建议轮询间隔 1–2 秒。

未知 `task_id` 返回 HTTP 404，`code` 为 `1003`。

### 5.4 `GET /drafts` — 列出已建的草稿

返回剪映草稿根目录下的草稿文件夹名列表。草稿根目录未配置或不存在时返回空数组。

响应 `data`：`["我的视频", "另一个草稿", ...]`

### 5.5 `GET /config` / `PUT /config` — 读写配置

`GET /config` 响应 `data`：

```json
{
  "draft_root": "/Users/xxx/Movies/JianyingPro/...",
  "port_range": [9527, 9536],
  "cors_origins": ["http://localhost:3182", "http://localhost:3183"]
}
```

`PUT /config` 请求体是同样结构的完整配置对象（整体覆盖）。

- `draft_root`：剪映草稿根目录。**首次使用必须先设置它**，否则 `POST /drafts` 的任务会失败（`code` 1001）。一般引导用户在 capcut_helper 桌面应用里选目录，调用方通常不需要自己改。
- `cors_origins`：跨域白名单。如果你的页面 origin 不在默认白名单里，可以加进来。

## 6. 时间线规格字段说明

`POST /drafts` 请求体的完整结构：

```jsonc
{
  "draft_name": "我的视频",      // 必填，草稿文件夹名，不能含 / 或 \
  "allow_replace": false,        // 可选，默认 false。true=同名草稿直接覆盖；false=同名报冲突(code 1002)
  "canvas": {                    // 必填，画布参数
    "width": 1920,               // > 0
    "height": 1080,              // > 0
    "fps": 30                    // > 0，默认 30
  },
  "tracks": [                    // 必填，至少 1 条轨道
    {
      "type": "video",           // "video" | "audio" | "text"
      "segments": [              // 至少 1 个片段
        {
          // material：video/audio 轨道的片段必填；text 轨道的片段不需要
          "material": {
            "url": "https://...",      // 素材的可下载 URL
            "type": "video",           // "video" | "image" | "audio"
            "filename": "clip1.mp4"    // 文件名（决定下载后的文件名）
          },
          // timeline：必填，片段在时间线上的位置（微秒）
          "timeline": { "start": 0, "duration": 5000000 },
          // source：可选，从素材内部裁剪的范围（微秒）。不填则用整段素材
          "source": { "start": 0, "duration": 5000000 },
          // text：text 轨道的片段必填；video/audio 轨道不需要
          "text": { "content": "字幕内容", "style": {} }
        }
      ]
    }
  ]
}
```

字段校验规则：

- `draft_name`：非空，不能包含 `/` 或 `\`
- `canvas.width/height/fps`：都必须 > 0
- `timeline.start` / `source.start`：≥ 0；`timeline.duration` / `source.duration`：> 0
- `video` / `audio` 轨道的每个片段必须有 `material`
- `text` 轨道的每个片段必须有 `text`
- 同一个 `material.url` 在多个片段里复用时，服务端只会下载一次（按 URL 去重）

违反任何规则 → HTTP 422，`code` 422。

## 7. 错误码

| HTTP | code | 含义 | 怎么处理 |
|------|------|------|---------|
| 422 | 422 | 时间线规格非法 | `data` 里有字段级错误，修正请求体 |
| 400 | 1001 | 剪映草稿根目录未配置或不存在 | 引导用户在 capcut_helper 设置里选草稿目录 |
| 409 | 1002 | 草稿名重名且未允许覆盖 | 换个 `draft_name`，或带 `allow_replace: true` |
| 404 | 1003 | 任务不存在 | `task_id` 写错了，或服务重启过（任务是内存态，重启即丢） |
| 502 | 1004 | 素材下载失败 | 一般出现在任务的 `error` 字段里；检查素材 URL 是否可达 |

> 1001/1002/1004 这类业务错误，多数情况下不是 `POST /drafts` 直接返回的——`POST /drafts` 几乎总是先返回 `task_id`，真正的失败体现在轮询 `GET /tasks/{id}` 时 `status` 变成 `failed`、`error` 字段有描述。

## 8. 完整调用流程示例（JavaScript）

```js
// 1. 发现端口
const port = await discoverPort()              // 见 §3
const base = `http://localhost:${port}/api/v1`

// 2. 提交时间线规格
const spec = {
  draft_name: '我的视频',
  canvas: { width: 1920, height: 1080, fps: 30 },
  tracks: [{
    type: 'video',
    segments: [
      { material: { url: 'https://.../a.mp4', type: 'video', filename: 'a.mp4' },
        timeline: { start: 0, duration: 5_000_000 } },
      { material: { url: 'https://.../b.mp4', type: 'video', filename: 'b.mp4' },
        timeline: { start: 5_000_000, duration: 8_000_000 } },
    ],
  }],
}
const postResp = await fetch(`${base}/drafts`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(spec),
})
const postBody = await postResp.json()
if (postBody.code !== 0) throw new Error(postBody.message)
const taskId = postBody.data.task_id

// 3. 轮询任务直到 done / failed
while (true) {
  await new Promise(r => setTimeout(r, 1500))
  const taskResp = await fetch(`${base}/tasks/${taskId}`)
  const { data } = await taskResp.json()
  // data: { id, status, progress, result, error }
  updateProgressUI(data.status, data.progress)
  if (data.status === 'done') {
    console.log('草稿已生成:', data.result)   // 草稿文件夹绝对路径
    break
  }
  if (data.status === 'failed') {
    throw new Error('生成失败: ' + data.error)
  }
}
// 4. 提示用户：打开剪映即可看到这个新草稿
```

## 9. 服务没起来怎么办

- 端口段 `9527–9536` 全探测不到 → capcut_helper 桌面应用没启动，提示用户启动它
- `POST /drafts` 后任务一直 `failed` 且 `error` 提到「草稿根目录」→ 用户没在 capcut_helper 里设置剪映草稿目录
- 跨域被浏览器拦 → 你的页面 origin 不在 CORS 白名单，见 §4
