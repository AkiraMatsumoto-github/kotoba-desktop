# 配布用のアプリとインストーラーを作る。
#
#   powershell -ExecutionPolicy Bypass -File packaging\build.ps1 [-Version 0.1.0] [-SkipInstaller]
#
# 出力:
#   dist\kotoba-desktop\                       PyInstaller で固めたアプリ（フォルダごと動く）
#   dist\kotoba-desktop-<版>-setup.exe         インストーラー（Inno Setup 6 が要る）
#
# ビルド用の仮想環境は build\.venv に分ける（開発用の .venv で起動中のアプリとぶつからないように）。
param(
    [string]$Version = "",
    [switch]$SkipInstaller
)

$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot
Set-Location $root

if (-not $Version) {
    $Version = (Select-String -Path pyproject.toml -Pattern '^version = "(.+)"').Matches[0].Groups[1].Value
}
Write-Host "kotoba-desktop $Version をビルドします"

$env:UV_PROJECT_ENVIRONMENT = Join-Path $root "build\.venv"
uv sync --locked --no-dev --group build --no-editable
if ($LASTEXITCODE) { throw "uv sync に失敗しました" }

uv run --no-sync pyinstaller packaging\kotoba-desktop.spec --noconfirm --clean `
    --distpath dist --workpath build\pyinstaller
if ($LASTEXITCODE) { throw "PyInstaller に失敗しました" }

if ($SkipInstaller) { return }

$iscc = Get-Command iscc -ErrorAction SilentlyContinue
# 1 件だけだと文字列になり [0] が 1 文字目を指すので、@() で配列に保つ
$candidates = @(@(
    $(if ($iscc) { $iscc.Source }),
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
) | Where-Object { $_ -and (Test-Path $_) })
if (-not $candidates) {
    throw "Inno Setup 6 が見つかりません（winget install JRSoftware.InnoSetup）。-SkipInstaller でアプリだけ作れます"
}
& $candidates[0] "/DAppVersion=$Version" packaging\installer.iss
if ($LASTEXITCODE) { throw "インストーラーを作れません" }
Write-Host "できました: dist\kotoba-desktop-$Version-setup.exe"
