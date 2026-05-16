# capcut_helper Windows x64 构建脚本：PyInstaller onedir + Inno Setup 安装包。
# 用法（在 PowerShell 中、Windows 机器上）:
#   cd capcut_helper
#   pwsh -ExecutionPolicy Bypass -File scripts/build_win.ps1
#
# 前置：node + npm + Python 3.11+ + uv + Inno Setup 6 已安装。
# Inno Setup 6: https://jrsoftware.org/isdl.php
# 若 ISCC.exe 不在默认位置，设环境变量 ISCC_PATH 指向 ISCC.exe。

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot/..

# ---------- 读版本号（来源唯一：backend/app/__init__.py::__version__） ----------
$versionLine = Select-String -Path backend/app/__init__.py -Pattern '"(\d+\.\d+\.\d+)"' | Select-Object -First 1
if (-not $versionLine) {
    throw "无法从 backend/app/__init__.py 解析 __version__"
}
$version = $versionLine.Matches.Groups[1].Value
$installerName = "capcut_helper-x64-v$version.exe"

# ---------- 定位 ISCC.exe ----------
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

Write-Host "-> 1/3 安装/构建前端"
Push-Location frontend
npm install
npm run build
Pop-Location

Write-Host "-> 2/3 PyInstaller 打包 onedir"
Push-Location backend
uv run pyinstaller --clean --noconfirm `
    --distpath=../dist --workpath=../build `
    capcut_helper_win.spec
Pop-Location

Write-Host "-> 3/3 Inno Setup 编译安装包"
& $iscc /DVERSION=$version scripts/capcut_helper.iss
if ($LASTEXITCODE -ne 0) {
    throw "ISCC.exe 编译失败，退出码 $LASTEXITCODE"
}

Write-Host ""
Write-Host "构建完成："
Write-Host "  EXE 目录:   $(Resolve-Path dist/capcut_helper)"
Write-Host "  安装包:     $(Resolve-Path "dist/$installerName")"
