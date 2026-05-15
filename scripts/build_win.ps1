# capcut_helper Windows x64 构建脚本。
# 用法（在 PowerShell 中、Windows 机器上）:
#   cd capcut_helper
#   powershell -ExecutionPolicy Bypass -File scripts/build_win.ps1
#
# 前置：node + npm + Python 3.11+ + uv 已安装。

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot/..

Write-Host "-> 1/3 安装/构建前端"
Push-Location frontend
npm install
npm run build
Pop-Location

Write-Host "-> 2/3 PyInstaller 打包"
Push-Location backend
uv run pyinstaller --clean --noconfirm `
    --distpath=../dist --workpath=../build `
    capcut_helper_win.spec
Pop-Location

Write-Host "-> 3/3 压缩 zip"
$tag = (git describe --tags --abbrev=0 2>$null)
if ([string]::IsNullOrEmpty($tag)) {
    $tag = "v0.0.0-dev"
}
$zipName = "capcut_helper-x64-$tag.zip"
$zipPath = "dist/$zipName"
if (Test-Path $zipPath) { Remove-Item $zipPath }
Compress-Archive -Path dist/capcut_helper/* -DestinationPath $zipPath

Write-Host ""
Write-Host "构建完成："
Write-Host "  EXE 目录: $(Resolve-Path dist/capcut_helper)"
Write-Host "  zip:      $(Resolve-Path $zipPath)"
