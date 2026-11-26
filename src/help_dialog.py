"""Cửa sổ Trợ giúp: bảng tóm tắt thao tác chuột / phím tắt / thoại tự động.

- Không phải hộp thoại chặn (``show()``, không ``exec()``): nhân vật vẫn tương tác được khi đang mở.
- Luôn nổi lên trên (``WindowStaysOnTopHint``) để nhân vật "luôn trên cùng" không che mất.
- Đóng cửa sổ chỉ ẩn nó đi, không thoát ứng dụng (``WA_QuitOnClose`` tắt; ``app.py`` cũng đã
  đặt ``setQuitOnLastWindowClosed(False)`` vì còn icon khay hệ thống).
- Nội dung do ``refresh()`` dựng lại từ ``locales`` nên luôn khớp ngôn ngữ, phím tắt Hover Mode và
  thời gian "rảnh" hiện hành trong config.
"""
from __future__ import annotations

import html

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QDialog, QFrame, QHBoxLayout, QPushButton, QTextBrowser, QVBoxLayout

from .locales import format_duration, tr


class HelpDialog(QDialog):
    def __init__(self, icon: QIcon) -> None:
        flags = (
            Qt.WindowType.Dialog
            | Qt.WindowType.WindowCloseButtonHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        super().__init__(None, flags)  # không có parent: không dính vào cửa sổ nhân vật trong suốt
        self.setAttribute(Qt.WidgetAttribute.WA_QuitOnClose, False)
        self.setWindowIcon(icon)
        self.setMinimumSize(480, 420)
        self.resize(560, 580)

        self._browser = QTextBrowser(self)
        self._browser.setOpenLinks(False)
        self._browser.setFrameShape(QFrame.Shape.NoFrame)

        self._close_btn = QPushButton(self)
        self._close_btn.setDefault(True)
        self._close_btn.clicked.connect(self.close)

        bottom = QHBoxLayout()
        bottom.addStretch(1)
        bottom.addWidget(self._close_btn)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.addWidget(self._browser, 1)
        layout.addLayout(bottom)

    # ------------------------------------------------------------------
    def refresh(self, hotkey: str, idle_interval: int, click_gap: float) -> None:
        """Dựng lại toàn bộ chữ theo ngôn ngữ / config hiện hành."""
        self.setWindowTitle(tr("help.title"))
        self._close_btn.setText(tr("help.close"))
        self._browser.setHtml(self._build_html(hotkey, idle_interval, click_gap))

    @staticmethod
    def _build_html(hotkey: str, idle_interval: int, click_gap: float) -> str:
        idle_desc = (
            tr("help.idle.d", time=format_duration(idle_interval)) if idle_interval > 0 else tr("help.idle.off")
        )
        items = [
            (tr("help.click.t"), tr("help.click.d")),
            (tr("help.love.t"), tr("help.love.d", gap=f"{click_gap:g}")),
            (tr("help.hold.t"), tr("help.hold.d")),
            (tr("help.drag.t"), tr("help.drag.d")),
            (tr("help.right.t"), tr("help.right.d")),
            (tr("help.hover.t", hotkey=html.escape(hotkey)), tr("help.hover.d")),
            (tr("help.idle.t"), idle_desc),
            (tr("help.keys.t"), tr("help.keys.d")),
        ]
        body = "".join(
            f'<p style="margin:0 0 12px 0"><b style="font-size:10.5pt">{title}</b><br>{desc}</p>'
            for title, desc in items
        )
        return f'<p style="margin:0 0 12px 0">{tr("help.intro")}</p>{body}'

    def show_front(self) -> None:
        """Hiện (hoặc đưa lên trước nếu đang mở) - chỉ có một cửa sổ Trợ giúp duy nhất."""
        if self.isMinimized():
            self.showNormal()
        else:
            self.show()
        self.raise_()
        self.activateWindow()
