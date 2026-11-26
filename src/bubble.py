"""Bong bóng thoại: cửa sổ riêng, trong suốt, bấm xuyên qua, tự ẩn sau vài giây."""
from __future__ import annotations

import html

from PySide6.QtCore import QPointF, QRect, QRectF, Qt, QTimer
from PySide6.QtGui import (
    QColor, QFont, QGuiApplication, QPainter, QPainterPath, QPen, QTextDocument, QTextOption,
)
from PySide6.QtWidgets import QWidget

MAX_TEXT_WIDTH = 300
PAD = 12
RADIUS = 12
TAIL_H = 12
TAIL_HALF_W = 9
BORDER = 2


class BubbleWindow(QWidget):
    def __init__(self, on_top: bool = True) -> None:
        flags = (
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus
            | Qt.WindowType.WindowTransparentForInput
        )
        if on_top:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        super().__init__(None, flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)

        font = QFont()
        font.setFamilies(["Segoe UI", "Arial", "Tahoma"])
        font.setPointSizeF(10.5)

        self._doc = QTextDocument(self)
        self._doc.setDefaultFont(font)
        option = QTextOption()
        option.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        self._doc.setDefaultTextOption(option)
        self._doc.setDocumentMargin(0)

        self._body_h = 0
        self._tail_x = 0
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)

    # ------------------------------------------------------------------
    def show_message(self, text: str, anchor: QRect, persist: bool = False) -> None:
        """Hiện ``text`` phía trên ``anchor`` (hình chữ nhật của nhân vật)."""
        text = text.strip()
        if not text:
            return
        self._doc.setTextWidth(MAX_TEXT_WIDTH)
        self._doc.setHtml(f'<div style="color:#222233;">{html.escape(text)}</div>')
        self._doc.setTextWidth(MAX_TEXT_WIDTH)
        ideal = min(float(MAX_TEXT_WIDTH), self._doc.idealWidth())
        self._doc.setTextWidth(ideal + 1)
        size = self._doc.size()

        body_w = int(size.width()) + 2 * PAD + 2 * BORDER
        self._body_h = int(size.height()) + 2 * PAD + 2 * BORDER
        self.setFixedSize(body_w, self._body_h + TAIL_H)

        self._timer.stop()
        if not persist:
            self._timer.start(min(12000, max(3500, 70 * len(text))))
        self.reposition(anchor)
        if not self.isVisible():
            self.show()
        self.raise_()
        self.update()

    def reposition(self, anchor: QRect) -> None:
        screen = QGuiApplication.screenAt(anchor.center()) or QGuiApplication.primaryScreen()
        area = screen.availableGeometry()
        w, h = self.width(), self.height()
        x = anchor.center().x() - w // 2
        y = anchor.top() - h + 8
        x = max(area.left() + 4, min(x, area.right() - w - 4))
        y = max(area.top() + 4, min(y, area.bottom() - h - 4))
        self.move(x, y)
        margin = RADIUS + TAIL_HALF_W + BORDER
        self._tail_x = max(margin, min(anchor.center().x() - x, w - margin))
        self.update()

    def hide_message(self) -> None:
        self._timer.stop()
        self.hide()

    # ------------------------------------------------------------------
    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        body = QRectF(BORDER / 2, BORDER / 2, self.width() - BORDER, self._body_h - BORDER)
        path = QPainterPath()
        path.addRoundedRect(body, RADIUS, RADIUS)
        tail = QPainterPath()
        base_y = body.bottom() - 0.5
        tail.moveTo(QPointF(self._tail_x - TAIL_HALF_W, base_y))
        tail.lineTo(QPointF(self._tail_x, base_y + TAIL_H - BORDER))
        tail.lineTo(QPointF(self._tail_x + TAIL_HALF_W, base_y))
        tail.closeSubpath()
        shape = path.united(tail)

        p.fillPath(shape, QColor(255, 255, 255, 242))
        p.setPen(QPen(QColor(110, 130, 190), BORDER))
        p.drawPath(shape)

        p.translate(PAD + BORDER, PAD + BORDER)
        self._doc.drawContents(p)
        p.end()
