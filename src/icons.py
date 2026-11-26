"""Icon vẽ bằng code (QPainter) - không cần file ảnh đi kèm trong .exe."""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QIcon, QImage, QLinearGradient, QPainter, QPen, QPixmap, QPolygonF


def _star(cx: float, cy: float, outer: float, inner: float) -> QPolygonF:
    pts = []
    for i in range(10):
        radius = outer if i % 2 == 0 else inner
        angle = -math.pi / 2 + i * math.pi / 5
        pts.append(QPointF(cx + radius * math.cos(angle), cy + radius * math.sin(angle)))
    return QPolygonF(pts)


def make_image(size: int = 128) -> QImage:
    """Hình vuông bo góc màu xanh với ngôi sao trắng (cũng dùng làm hình tạm khi chưa tải được nhân vật)."""
    img = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    grad = QLinearGradient(0, 0, 0, size)
    grad.setColorAt(0.0, QColor("#5bb2ff"))
    grad.setColorAt(1.0, QColor("#2f5fd6"))
    margin = size * 0.04
    p.setBrush(QBrush(grad))
    p.setPen(QPen(QColor(255, 255, 255, 200), max(1.0, size * 0.025)))
    p.drawRoundedRect(QRectF(margin, margin, size - 2 * margin, size - 2 * margin), size * 0.22, size * 0.22)

    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("white"))
    p.drawPolygon(_star(size / 2, size * 0.53, size * 0.34, size * 0.14))
    p.end()
    return img


def make_icon(size: int = 64) -> QIcon:
    return QIcon(QPixmap.fromImage(make_image(size)))
