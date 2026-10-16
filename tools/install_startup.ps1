# ログオン時に kotoba-desktop を起動するよう、スタートアップフォルダにショートカットを置く。
# 先に `uv tool install --editable .` で kotoba-desktop.exe を作っておく。
#
#   powershell -ExecutionPolicy Bypass -File tools\install_startup.ps1          # 登録
#   powershell -ExecutionPolicy Bypass -File tools\install_startup.ps1 -Remove  # 解除
param([switch]$Remove)

$ErrorActionPreference = "Stop"
$shortcut = Join-Path ([Environment]::GetFolderPath("Startup")) "kotoba-desktop.lnk"

if ($Remove) {
    if (Test-Path $shortcut) {
        Remove-Item $shortcut
        Write-Host "解除しました: $shortcut"
    } else {
        Write-Host "登録されていません"
    }
    return
}

$exe = Join-Path $env:USERPROFILE ".local\bin\kotoba-desktop.exe"
if (-not (Test-Path $exe)) {
    $command = Get-Command kotoba-desktop -ErrorAction SilentlyContinue
    if (-not $command) {
        throw "kotoba-desktop.exe が見つかりません。先に 'uv tool install --editable .' を実行してください"
    }
    $exe = $command.Source
}

$shell = New-Object -ComObject WScript.Shell
$link = $shell.CreateShortcut($shortcut)
$link.TargetPath = $exe
$link.WorkingDirectory = Split-Path $exe
$link.Description = "kotoba-desktop（音声入力）"
$link.Save()
Write-Host "登録しました: $shortcut -> $exe"
