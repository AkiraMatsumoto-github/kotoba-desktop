# PyInstaller の設定。packaging/build.ps1 から呼ばれる。
# 1 ファイルにまとめると起動のたびに 1 GB 近くを展開することになるので、フォルダ形式（onedir）で作る。

import importlib.util
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

ROOT = Path(SPECPATH).parent
ICON = ROOT / "packaging" / "kotoba-desktop.ico"  # packaging/make_icon.py で作る


def nvidia_bin(package: str) -> Path:
    spec = importlib.util.find_spec(f"nvidia.{package}")
    assert spec and spec.submodule_search_locations, f"nvidia.{package} が入っていません"
    return Path(next(iter(spec.submodule_search_locations))) / "bin"


# ctranslate2 の wheel には cuBLAS が無いので、nvidia-cublas-cu12 の DLL を同じ配置で入れる。
# 実行時は asr.register_cuda_dlls が _internal/nvidia/*/bin を検索パスに加える。
# 一緒に入る nvidia-cuda-nvrtc-cu12（約 180 MB）は認識で読み込まれないので入れない
binaries = [
    (str(nvidia_bin("cublas") / name), "nvidia/cublas/bin")
    for name in ("cublas64_12.dll", "cublasLt64_12.dll")
]
binaries += collect_dynamic_libs("ctranslate2")  # cudnn64_9.dll など

datas = [(str(ROOT / "src" / "kotoba_desktop" / "ui" / "Widget.qml"), "kotoba_desktop/ui")]
datas += collect_data_files("faster_whisper")  # 無音判定（Silero VAD）の onnx

a = Analysis(
    [str(ROOT / "packaging" / "launcher.py")],
    pathex=[str(ROOT / "src")],
    binaries=binaries,
    datas=datas,
    # Widget.qml の import QtQuick に要る QML プラグインを集めさせる
    hiddenimports=["PySide6.QtQuick"],
    excludes=["tkinter"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="kotoba-desktop",
    console=False,
    icon=str(ICON),
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="kotoba-desktop", upx=False)
