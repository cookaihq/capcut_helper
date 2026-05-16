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
