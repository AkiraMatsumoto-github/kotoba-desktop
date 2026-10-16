"""exe とインストーラーのアイコン（.ico）を、トレイのアイコンと同じ絵で書き出す。

Segoe Fluent Icons（Windows 11 のフォント）が要るので、CI ではなく手元で作ってリポジトリに置く。

    uv run python packaging/make_icon.py packaging/kotoba-desktop.ico
"""

import struct
import sys
from pathlib import Path

from PySide6.QtCore import QBuffer, QIODevice
from PySide6.QtGui import QGuiApplication

from kotoba_desktop.ui.tray import make_pixmap

SIZES = (16, 24, 32, 48, 64, 128, 256)
COLOR = "#0078d4"  # 待機中の色


def png_bytes(size: int) -> bytes:
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    make_pixmap(COLOR, size).save(buffer, "PNG")
    return bytes(buffer.data().data())


def write_ico(path: Path) -> None:
    # PNG をそのまま格納する形式の ICO（Windows Vista 以降で読める）
    images = [png_bytes(size) for size in SIZES]
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = len(header) + 16 * len(images)
    entries = b""
    for size, data in zip(SIZES, images, strict=True):
        dim = 0 if size >= 256 else size  # 256 は 0 と書く決まり
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(header + entries + b"".join(images))


def main() -> None:
    app = QGuiApplication(sys.argv)  # noqa: F841  QPixmap と フォントに必要
    write_ico(Path(sys.argv[1]))


if __name__ == "__main__":
    main()
