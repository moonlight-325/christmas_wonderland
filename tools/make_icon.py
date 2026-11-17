"""assets/icon.ico 생성 (PNG 내장 ICO). 실행: python tools/make_icon.py"""
import os
import struct
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from core.icons import _icon_image  # noqa: E402

SIZES = (16, 32, 48, 64, 128, 256)


def main():
    app = QApplication([])
    base = _icon_image()
    blobs = []
    for s in SIZES:
        img = base.scaled(s, s, Qt.IgnoreAspectRatio, Qt.FastTransformation)
        ba = QByteArray()
        buf = QBuffer(ba)
        buf.open(QIODevice.WriteOnly)
        img.save(buf, "PNG")
        blobs.append(bytes(ba))
    out = Path(__file__).resolve().parent.parent / "assets" / "icon.ico"
    header = struct.pack("<HHH", 0, 1, len(SIZES))
    offset = 6 + 16 * len(SIZES)
    entries = b""
    for s, data in zip(SIZES, blobs):
        entries += struct.pack("<BBBBHHII", s % 256, s % 256, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
    out.write_bytes(header + entries + b"".join(blobs))
    print("written", out, out.stat().st_size)


if __name__ == "__main__":
    main()
