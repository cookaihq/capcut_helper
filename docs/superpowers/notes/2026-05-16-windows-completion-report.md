# capcut_helper Windows 完工 — 执行报告

> **执行日期**：2026-05-16
> **执行方式**：superpowers:subagent-driven-development，串行 dispatch implementer + spec reviewer + 必要时 code quality reviewer
> **Plan**：[`docs/superpowers/plans/2026-05-16-capcut-helper-windows-completion.md`](../plans/2026-05-16-capcut-helper-windows-completion.md)
> **Spec**：[`docs/superpowers/specs/2026-05-16-capcut-helper-windows-completion-design.md`](../specs/2026-05-16-capcut-helper-windows-completion-design.md)
> **基线 → HEAD**：`c37838a` → `2d1f4b5`（11 个 commit，未 push 到 origin）

---

## 1. Task 状态总览

| # | 任务 | 状态 | Commit |
|---|---|---|---|
| 1 | A：在 Windows 端到端跑现有 zip 打包 + spec fixup | **done**（脚本部分）/ **pending**（用户手动 UI 矩阵） | — |
| 2 | D spike：定位剪映 Win 自定义草稿目录存储位置 | **done**（Case 1，找到了） | — |
| 3 | D 实现：`_read_windows_custom_draft_path` + 单测 + README 删限制条 | **done** | `b1eee9c` |
| 4 | C：创建 `scripts/capcut_helper.iss` | **done**（含 mojibake fix） | `7c51177` + `2d1f4b5` |
| 5 | C：改造 `scripts/build_win.ps1` 接 ISCC（Step 5.1 代码） | **done** | `6d35592` |
| 5.2/3/4 | C：build 实跑 + 安装包安装 + 卸载验证 | **paused**（等用户装 Inno Setup 6） | — |
| 6 | C：`update_checker._asset_name_for_tag` `.zip → .exe` | **done** | `164b37e` |
| 7 | C：README「Windows 分发」+「一次性准备」改写 | **done** | `a597368` |
| 8 | B：`release.sh → release_mac.sh` 重命名 + .gitignore 注释同步 | **done** | `24c8500` |
| 9 | B：`release_mac.sh` 加 release 复用 + remote tag skip 逻辑 | **done** | `d3c34fd` |
| 10 | B：新增 `scripts/release_win.ps1` | **done**（含对称 cleanup 提示 fix） | `330686a` + `2d1f4b5` |
| 11 | B：README「每次发版」+「打包分发」+「已知限制」重写 | **done** | `22f9794` |
| 12 | bump 0.1.3 + 真发版联调 | **skipped**（用户决定 out of scope） | — |

附加 commit：
- `b61a4fa chore: gitignore .claude/`（执行前清理仓库 dirty 状态）
- `2d1f4b5 fix: 修最终 review 三处问题`（.iss mojibake + release_win.ps1 对称 + .gitignore 注释；详见 §4）

---

## 2. Task 1（A）测试矩阵实测结果

### 2.1 自动化部分（subagent 跑完）

`pwsh -ExecutionPolicy Bypass -File scripts/build_win.ps1`：**一次跑通，无需 spec fixup**。

| 项 | 结果 |
|---|---|
| 三阶段（前端 / PyInstaller / Compress-Archive）全部成功 | ✅ |
| `dist/capcut_helper/capcut_helper.exe` 产出 | ✅ 14,707,201 bytes |
| `dist/capcut_helper-x64-v0.1.2.zip` 产出（tag v0.1.2 来自 `git describe`） | ✅ 46,919,459 bytes |
| `_internal/pymediainfo/MediaInfo.dll` 进 bundle | ✅ 7,906,176 bytes |
| `_internal/pyJianYingDraft/assets/{draft_content_template.json,draft_meta_info.json}` 进 bundle | ✅ |
| `_internal/frontend/dist/{assets,index.html}` 进 bundle | ✅ |
| `_internal/webview/` 进 bundle | ✅ |
| 1,122 个文件总计在 `_internal/` 里 | ✅ |
| smoke launch（启动 5s+）：进程存活 + 监听 127.0.0.1:9527 | ✅ 端口已 listen；HTTP 探活在 8s 超时内未返回（cold start 行为，非致命） |
| Application 事件日志：与 capcut_helper 相关的错误 | ✅ 无 |

PyInstaller 期间 3 条警告（**全部非致命，与 spec §4.2 风险点无关**）：
- `UIAutomationCore_VCID140_X64.dll required via ctypes not found`（pywin32 probing，大多数系统无影响）
- `Hidden import 'pycparser.lextab' / 'yacctab' / 'tzdata' not found`（这些库延迟生成或可选）
- `Failed to collect submodules for 'webview.platforms.android'`（桌面端构建，预期）

**结论**：`capcut_helper_win.spec` **无需 fixup**。spec §4.2 列出的 5 个高风险 fixup 点（libmediainfo / WebView2 / pyJianYingDraft 模板 / pystray / PIL）**全部由原有 spec 配置自然覆盖**——这一收益归功于 tray-mode plan Task 9 当时主动加的 `collect_all("webview")` + `pystray._win32` + `PIL._tkinter_finder` hidden import。

### 2.2 用户手动矩阵（plan §Step 1.3 共 10 项 + 1 个补充项）

**状态**：**pending**——需要用户在 Windows 上手工跑完一次。subagent 无 GUI 视觉能力，无法替代。

待勾项（来自 spec §4.1，搬到本报告便于用户填）：

```
[ ] 双击 dist/capcut_helper/capcut_helper.exe → 主窗口 + 任务栏 + 托盘图标
[ ] 三个 Tab（活动 / 草稿 / 设置）能切
[ ] 「设置 → 选择目录」能弹 Windows 文件夹选择对话框
[ ] 「设置 → 自动探测」返回剪映目录（D spike 后应优先返回 D:\test_drafts\JianyingPro Drafts，
    若该目录已删可还原默认 %LOCALAPPDATA%\JianyingPro\User Data\Projects\com.lveditor.draft）
[ ] 点窗口 × / Alt+F4 → 窗口消失、任务栏 / Alt+Tab 消失、托盘图标保留
[ ] 关窗后 curl http://127.0.0.1:9527/api/v1/health 仍 200
[ ] 托盘左键 → 窗口出现
[ ] 托盘右键 → 菜单含 v0.1.2 / 打开面板 / 检查更新 / 退出
[ ] 菜单「退出」→ 全消失、端口释放、托盘图标无 zombie
[ ] POST 真实 timeline spec 到 /api/v1/draft，草稿能完整生成
[ ] reveal_in_os("D:\\some\\existing\\path") → 资源管理器弹出且选中
```

> ⚠️ smoke 阶段发现 cold-start 时 `/api/v1/health` 在 8s 内未返回。若手动跑「关窗后 curl 仍 200」这一项遇到第一次超时，**retry 一次**——可能只是首请求延迟。如果 retry 仍超时，那是真问题，需要排查。

---

## 3. Task 2（D spike）调研结论

### 3.1 候选位置探查

按 spec §5.1 优先级跑了候选 1 + 候选 2 + （快速浏览）注册表：

| 候选 | 命中？ | 备注 |
|---|---|---|
| `%LOCALAPPDATA%\JianyingPro\User Data\Preferences\` 下任意文件 | ❌ `Preferences/` 目录不存在 | — |
| `%LOCALAPPDATA%\JianyingPro\User Data\Config\globalSetting`（INI） | ✅ **命中** | `[General]` 段第 62 行 `currentCustomDraftPath=...` |
| `%APPDATA%\JianyingPro\` | — | 未需检（前一项已命中） |
| HKCU 注册表 `Software\JianyingPro` | — | 未需检 |
| ProcMon 兜底 | — | 未需 |

### 3.2 验证手段（MD5 前后对比）

| 阶段 | `globalSetting` MD5 | `currentCustomDraftPath` 值 |
|---|---|---|
| 改路径前 | `B666180E245A2884F4EF6EAD8EF0A7FF` | `C:\\Users\\y\\AppData\\Local\\JianyingPro\\User Data\\Projects\\com.lveditor.draft`（默认） |
| 用户在剪映 UI 把草稿目录改为 `D:\test_drafts` 并保存退出后 | `8E15B607C460556E1D516F3848C2CEB7` | `D:\\test_drafts\\JianyingPro Drafts` |

MD5 变化 + 值变化 → 确认剪映 Win 版**确实**把用户自定义草稿目录写入此文件。

### 3.3 关键发现

1. **存储格式是 INI，不是 JSON**（plan Step 3.1 假定 JSON，调研推翻该假设）
2. **Key 名与 macOS 完全相同**：`currentCustomDraftPath`（macOS 是 `GlobalSettings.History.currentCustomDraftPath` 在 plist 里；Windows 是同名 key 在 INI `[General]` 段下）
3. **值的转义格式有两种**：
   - 用户手改的路径：双反斜杠 `D:\\test_drafts\\JianyingPro Drafts`
   - 程序自动写入的默认值：正斜杠 `C:/Users/y/AppData/Local/JianyingPro/User Data/VideoRecord`
   - 实现需双向兼容（已在 `bridge.py:55` 用 `raw.replace("\\\\", "\\")` 处理，正斜杠路径在 `Path.is_dir()` 检验时 Windows 原生兼容）
4. **JianyingPro 行为副作用**：用户给定 `D:\test_drafts`，剪映自动在末尾追加 `\JianyingPro Drafts` 子目录。读出来的是已追加版本。实现不关心这个细节——只读字段值 + 校验目录存在。

### 3.4 实现的差异（vs. plan 假定）

| Plan 假定 | 实际 | 实现调整 |
|---|---|---|
| `Preferences/draft.json` JSON 文件 | `Config/globalSetting` INI 文件 | 改用 `configparser` 而非 `json` |
| `{"customPath": "<path>"}` JSON 字段 | `[General].currentCustomDraftPath=<path>` INI key | `parser.get("General", "currentCustomDraftPath", fallback=None)` |
| 异常列表：`FileNotFoundError, PermissionError, json.JSONDecodeError, ValueError, KeyError, OSError` | 异常列表：`OSError, configparser.Error, UnicodeDecodeError` | configparser 的错误体系不同；`parser.read()` 对不存在文件**静默返回 `[]`**，靠 `fallback=None` 兜住 |
| 未处理路径转义 | 加 `\\\\ → \\` 转义还原 | INI 反斜杠转义是关键，否则路径错 |

测试用例数从 plan 计划的 3 个（happy / missing_file / invalid_json）扩到 4 个：加了 `dir_missing`（INI 里写了一个已不存在的目录，验证回退到默认路径的契约）。所有 4 个均带 `@pytest.mark.skipif(sys.platform != "win32")`。

实际在 Windows 上验证函数返回真实数据：
```
>>> _read_windows_custom_draft_path()
'D:\\test_drafts\\JianyingPro Drafts'
```

---

## 4. 偏离 Plan 的决策记录

### 4.1 Task 3：plan 假定 JSON，实际是 INI

**决策**：spike 输出推翻 plan Step 3.1 的 JSON 假定，改用 `configparser`。
**理由**：实测数据为准；strict 遵守 plan 会写出无法工作的代码。
**影响**：实现保留了相同的 *接口* (`_read_windows_custom_draft_path() -> Optional[str]`)、相同的 *契约*（任何异常返回 None）、相同的 *测试用例数量级*（3 → 4），仅替换内部解析手段。

### 4.2 Task 3：补丁式修复一个 pre-existing 测试

**决策**：在 `test_native_bridge.py::test_detect_draft_root_windows_path` 加 `monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "no_jianying_config"))`。
**理由**：Task 3 接通 `_read_windows_custom_draft_path` 进 `detect_draft_root` 后，原 Win 测试在本机会读到真实 JianyingPro 配置（含 D spike 写入的 `D:\test_drafts\JianyingPro Drafts`），断言失败。一行 isolation 修复 + 1 行注释，最小侵入。
**影响**：测试在 dev 机器和 CI 上行为一致，不会因开发机配置漂移而 flaky。

### 4.3 Task 4：plan 假定 GUID 是占位符，subagent 实际生成

**决策**：用 `[guid]::NewGuid().ToString().ToUpper()` 生成并固化为 `93743588-BDCB-48B4-B57A-FEDBEBB0ADDC`。
**理由**：plan Step 4.1 明示让 subagent 生成。
**注意**：**此 GUID 一旦发版，永远不能改**。改 GUID = 新应用，旧装机无法自动升级。该 GUID 写在 `scripts/capcut_helper.iss:2`。

### 4.4 Task 4 → fix commit：UTF-8 BOM mojibake

**问题**：Task 4 spec reviewer pass 后，code quality reviewer 提出「ISCC 6.x 在没 BOM 时可能乱码中文 `卸载` / `立即启动`」。我决定加 BOM。第一次尝试使用 `Get-Content -Raw` + `WriteAllText`，**PS 5.1 的 `Get-Content -Raw` 用系统默认 codepage（CP936，中文 Windows）解码**而非 UTF-8，造成 UTF-8 bytes 被 CP936 误解，再以 UTF-8 写回，形成双重编码 mojibake（`卸载` → `鍗歌浇`，`立即启动` → `绔嬪嵆鍚姩`，含 PUA 区码点已无法 round-trip）。

**最终 review 才捕捉到**（byte 级 CP936 反查）。修复在 `2d1f4b5`：用 `Write` 工具重写正确 UTF-8 + `[System.Text.Encoding]::UTF8` 显式解码 + `UTF8Encoding($true)` 编码加 BOM。

**教训（保留在本报告供未来调用）**：PS 5.1 + 中文 Windows 上**绝对不要**用 `Get-Content -Raw | WriteAllText` 做 UTF-8 round-trip。应该：
```powershell
$text = [System.IO.File]::ReadAllText($path, [System.Text.Encoding]::UTF8)
[System.IO.File]::WriteAllText($path, $text, (New-Object System.Text.UTF8Encoding($true)))
```

### 4.5 Task 5：用户决定 Step 5.2/5.3/5.4 paused

**决策**：本机未装 Inno Setup 6。用户在执行前选择「Pause Task 5 verify until I install it」。
**影响**：build_win.ps1 经 PowerShell PSParser 静态语法校验通过，但 **ISCC 阶段从未跑过**。一旦用户装 Inno Setup 6 后，需要：
1. 跑 `pwsh -ExecutionPolicy Bypass -File scripts/build_win.ps1`，确认产出 `dist/capcut_helper-x64-v0.1.2.exe`
2. 双击安装包跑安装向导，验 SmartScreen 弹窗 + 默认安装路径 + 「立即启动」勾选项工作
3. 看 Start Menu 是否生成「capcut_helper」+「卸载 capcut_helper」两个快捷方式且**中文正确**（验证 §4.4 的 BOM fix）
4. 卸载 → 确认 `%LOCALAPPDATA%\Programs\capcut_helper` 被删干净

### 4.6 Task 9 → 引出 Task 10：cleanup 提示需要 cross-platform 感知

**决策**：code quality reviewer 在 Task 9 指出：当 `REMOTE_TAG_EXISTS=1`（Windows 先推了 tag），Mac 端 POST release 失败时旧的提示「git push origin :refs/tags/$TAG && git tag -d $TAG」会**删掉 Windows 推的 tag**。加 `if/else` 让提示根据是否本端推 tag 区分。
**影响**：在 Task 9 commit 内 amend 修复 (`d3c34fd`)，Task 10 实现 release_win.ps1 时**同步对称这个 fix**。最终 review 阶段发现 Task 10 没 mirror 完整（只有 if 没 else），在 `2d1f4b5` 补齐。

### 4.7 Task 12 out of scope

**决策**：用户在执行前选择「Out of scope — stop after Task 11」。
**影响**：不真发 v0.1.3 release。下次正常 bump-发版时自然走一遍 mac/win 双端流程即可顺带验 release reuse 逻辑。

### 4.8 命名一致性自维约束

**plan Self-Review §「Type / 命名 一致性」明示**：Task 5 (build_win.ps1) + Task 10 (release_win.ps1) 须用**相同的 PowerShell 正则 `'"(\d+\.\d+\.\d+)"'`**。code quality reviewer 在 Task 5 建议改成 `'^__version__\s*=\s*"(\d+\.\d+\.\d+)"'` 锚定第一行更严格。**因 plan 明示一致性约束而拒绝**该建议——若改则得改两处，且属于纯防御性强化，不属于本 plan scope。归入 §5 follow-up。

### 4.9 跳过部分 code quality review

**决策**：Task 6（2 行 `.zip → .exe` swap）+ Task 10（实质是 release_mac.sh 的端口移植，Mac 版刚做过 review）+ Task 11（纯 README rewrite）跳过 code quality review，仅做 spec compliance review。
**理由**：subagent-driven-development skill 推荐每 task 两阶段 review，但对极小变更或刚 review 过的"port-only"变更，code quality review 边际收益低；保留 spec compliance review 即可保障对 plan 的忠实度。
**风险**：最终 cross-cutting review 抓到了 release_win.ps1 的 cleanup-hint 对称性 gap，证明跳过 Task 10 quality review 有代价；但 final review 兜住了。

---

## 5. Follow-up（未完事项）

### 5.1 阻塞性（用户必须做）

1. **跑 Task 1 §Step 1.3 手动 UI 测试矩阵**（10+ 项见 §2.2）。binary 在 `dist/capcut_helper/capcut_helper.exe`。
2. **装 [Inno Setup 6](https://jrsoftware.org/isdl.php)**，跑 Task 5 §Step 5.2/5.3/5.4 验证：
   - `pwsh -ExecutionPolicy Bypass -File scripts/build_win.ps1` 出 `.exe` 安装包
   - 双击安装包跑完整向导
   - 验证 Start Menu 中文快捷方式正确（验证 §4.4 BOM fix）
   - 从「设置 → 应用」卸载，验证清干净

### 5.2 可选硬化（plan 未要求，但 review 阶段提出）

| 来源 | 内容 | 优先级 |
|---|---|---|
| Task 5 quality review | `build_win.ps1` + `release_win.ps1` 的版本号正则 anchor 化（`'^__version__\s*=\s*"(\d+\.\d+\.\d+)"'`） | 低（当前 `__init__.py` 单行不会撞） |
| Task 5 quality review | `build_win.ps1` Stage 1（npm install/build）+ Stage 2（uv run pyinstaller）添加 `if ($LASTEXITCODE -ne 0) { throw ... }` —— 当前 native exec 非 0 不会被 `$ErrorActionPreference="Stop"` 截获，PyInstaller 失败会进 ISCC 阶段报误导性错 | 中（**真发版时遇到才会暴露**） |
| Task 9 quality review | `release_mac.sh` 的 UPLOAD_URL python heredoc 用 unquoted `<<PY` shell 插值 `$RELEASE_JSON` —— 若 GitHub 响应里 release body 含 `'''` 序列会破。**Task 9 的 reuse 路径把响应内容范围从 self-built payload 扩到任意第三方写入，攻击面变大**。修法：改 `printf '%s' "$RELEASE_JSON" \| python3 -c '...'` stdin 传递 | 中（**第三方在 release body 写 markdown 时可能触发**） |
| Task 3 quality review | 加一个 `forward-slash` 路径形式的 `_read_windows_custom_draft_path` 测试（如 `C:/Users/foo/drafts`） | 低（实现已隐式支持，且 dev 机已验证） |
| Task 3 quality review | spec 末尾追加「实现笔记」记录 spike outcome（plan Step 2.5 Case 1 说 "记录"，实际记录手段是 commit message + docstring） | 低（**本报告已替代承担该角色**） |

### 5.3 预先已存在、本 plan 不修

| 项 | 说明 |
|---|---|
| `backend/tests/test_update_api.py::test_update_check_returns_envelope` **在 Windows 上失败** | 测试硬编码 `_VALID_RESPONSE` 含 `.dmg` 资产名 + 断言 `download_url != None`。Win32 上 `_asset_name_for_tag` 返回 `.exe` 后 mismatch，`download_url=None`。**Task 6 修了 update_checker 后失败模式从「.zip vs .dmg mismatch」变成「.exe vs .dmg mismatch」——结果一样失败**。建议把该测试 parametrize 成两个 (darwin/win32) 用例 |
| `backend/tests/test_downloader.py::test_downloads_files_into_dest_dir` Win 上失败 | 环境/网络相关，预存在 |
| `backend/tests/test_e2e_draft.py::test_full_draft_creation_flow` Win 上失败 | 环境/codec 相关，预存在 |

### 5.4 真正发版时一并验证

下次 bump (e.g. v0.1.3) 时按 plan §Step 12.2-12.4 自然走一遍 win-先发 + mac-后发（或反过来），既能验：
- `release_win.ps1` 端到端（**当前从未真跑过**）
- `release_mac.sh` reuse 逻辑端到端
- 同一 release 下挂两个资产 (`.dmg` + `.exe`)
- update_checker 在线下载 .exe 链路

---

## 6. 测试结果汇总

| 测试套件 | 结果 | 备注 |
|---|---|---|
| `backend/tests/test_native_bridge.py` | **16/16 pass** | 含 4 个新 Win-only D 测试 + 1 个 pre-existing Win 测试的 LOCALAPPDATA 隔离 patch |
| `backend/tests/test_update_checker.py` | **12/12 pass** | 含 Task 6 改的 `test_asset_name_for_tag_on_win32` 期望 `.exe` |
| 触动代码全套 | **28/28 pass** | |
| Backend 全套 | 81 pass / 1 skip / 3 fail | 3 个失败均 pre-existing 且与本 PR 无关（详见 §5.3） |
| PowerShell 静态语法（`build_win.ps1`, `release_win.ps1`） | OK | 通过 `[System.Management.Automation.PSParser]::Tokenize` |
| Bash 静态语法（`release_mac.sh`） | OK | `bash -n` |

---

## 7. 文件清单

### 新增

- `scripts/capcut_helper.iss` — Inno Setup 安装包脚本（UTF-8 BOM）
- `scripts/release_win.ps1` — Windows 发版自动化（UTF-8 BOM）
- `docs/superpowers/notes/2026-05-16-windows-completion-report.md` —— 本报告

### 重命名

- `scripts/release.sh` → `scripts/release_mac.sh`

### 修改

- `backend/app/native/bridge.py`：+1 import + 1 function + detect_draft_root 接入
- `backend/tests/test_native_bridge.py`：+4 tests + 1 pre-existing test LOCALAPPDATA isolation patch
- `backend/app/services/update_checker.py`：1 行 `.zip → .exe`
- `backend/tests/test_update_checker.py`：1 行期望值
- `scripts/build_win.ps1`：整段重写（git describe → __version__ + Compress-Archive → ISCC）
- `scripts/release_mac.sh`：加 release reuse + remote tag skip + conditional cleanup 提示
- `README.md`：「Windows 分发」/「一次性准备」/「每次发版」/「打包成 .app 分发 → 打包分发」/「已知限制」共 5 处更新
- `.gitignore`：+ `.claude/` ignore + PAT 注释从 release.sh 同步到 release_mac.sh + release_win.ps1

### 不动

- `backend/capcut_helper_win.spec`（Task 1 build 一次通过，无需 fixup）
- 全部 Mac 端 build/release 现有路径
- `bridge.py` 原 macOS plist 读取路径
- frontend 全部
