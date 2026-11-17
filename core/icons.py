from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon, QImage, QPainter, QPixmap


def _icon_image() -> QImage:
    """24x24 픽셀 아이콘: 짙은 그린 바탕 + 크림 테두리 + 트리 + 별."""
    from widget.sprites import sprite_image
    img = QImage(24, 24, QImage.Format_ARGB32)
    img.fill(0)
    p = QPainter(img)
    p.fillRect(1, 0, 22, 24, QColor("#f5ead0"))
    p.fillRect(0, 1, 24, 22, QColor("#f5ead0"))
    p.fillRect(2, 2, 20, 20, QColor("#154436"))
    p.fillRect(2, 18, 20, 4, QColor("#ffffff"))
    tree = sprite_image("tree")
    p.drawImage(3, 1, tree.scaled(17, 21))
    p.end()
    return img


def make_app_icon() -> QIcon:
    """바이너리 파일 없이 코드로 그리는 앱/트레이 아이콘 (최근접 확대)."""
    base = _icon_image()
    icon = QIcon()
    for size in (24, 48, 72, 96, 144, 192):
        icon.addPixmap(QPixmap.fromImage(base.scaled(size, size, Qt.IgnoreAspectRatio, Qt.FastTransformation)))
    return icon
