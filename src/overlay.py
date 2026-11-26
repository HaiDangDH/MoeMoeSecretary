"""Cửa sổ linh vật: không viền, nền trong suốt, kéo thả, phím tắt, hiệu ứng lơ lửng.

Tiết kiệm tài nguyên:
- Hoàn toàn hướng sự kiện; chỉ có MỘT timer (~33 ms ≈ 30 FPS) và chỉ chạy khi bật
  hiệu ứng lơ lửng, tắt hẳn khi người dùng tắt.
- Chỉ giữ duy nhất pixmap của trang phục đang hiển thị; đổi trang phục là giải
  phóng pixmap cũ rồi gọi gc.collect().
- Vùng nền trong suốt (alpha = 0) tự cho chuột xuyên qua trên Windows (cửa sổ
  "layered"); ảnh đã được làm sạch viền gần-trong-suốt ở bước tạo cache.
- Độ mờ vẽ thẳng bằng ``QPainter.setOpacity`` (chỉ nhân vật mờ đi, bong bóng thoại vẫn rõ chữ).
- Hover Mode: cả cửa sổ cho chuột xuyên qua (``winutil.set_click_through``); mọi sự kiện chuột
  còn lọt tới đây cũng bị bỏ qua để không kéo / phát thoại / mở menu nhầm.
- Một lần nhấn chuột trái được phân loại đúng MỘT trong ba loại, không bao giờ hai:
    * nhấp  : nhả chuột trước 1.5 s và không kéo   -> ``clicked``
    * giữ   : giữ yên >= 1.5 s (timer 1 lần)        -> ``long_pressed`` (nhả ra không tính là nhấp)
    * kéo   : di chuyển quá ngưỡng kéo của hệ thống -> dời cửa sổ, huỷ timer giữ
"""
from __future__ import annotations

import gc
import math
import time

from PySide6.QtCore import QPoint, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QGuiApplication, QImage, QPainter, QPixmap, QPixmapCache
from PySide6.QtWidgets import QApplication, QWidget

from .config import OPACITY_MAX, OPACITY_MIN
from .winutil import set_click_through

FLOAT_INTERVAL_MS = 33  # ~30 FPS
FLOAT_PERIOD_S = 3.6
HOLD_MS = 1500  # giữ chuột trái đủ lâu thì tính là "nhấn giữ"

# Phím tắt (khi cửa sổ nhân vật đang được chọn)
_KEY_ACTIONS = {
    "j": "next_skin",
    "k": "prev_skin",
    "t": "toggle_top",
    "s": "toggle_flip",
    "f": "toggle_float",
}


class MascotWindow(QWidget):
    clicked = Signal()  # nhấp chuột trái (không kéo, không giữ lâu)
    long_pressed = Signal()  # giữ chuột trái >= HOLD_MS mà không kéo
    interacted = Signal()  # bất kỳ thao tác chuột trái nào (nhấn / kéo / nhả) -> để reset bộ đếm "rảnh"
    context_requested = Signal(QPoint)  # nhấp chuột phải -> vị trí toàn màn hình
    moved = Signal()  # vị trí thay đổi (để bong bóng thoại bám theo)
    action_requested = Signal(str)  # next_skin | prev_skin | toggle_top | toggle_flip | toggle_float
    quit_requested = Signal()

    def __init__(self, on_top: bool = True) -> None:
        flags = Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool
        if on_top:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        super().__init__(None, flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setWindowTitle("Moe Moe Secretary")

        self._pixmap: QPixmap | None = None
        self._opacity = 1.0
        self._hover_mode = False
        self._base = QPoint(100, 100)  # vị trí gốc (chưa cộng độ lệch lơ lửng)
        self._dy = 0
        self._amp = 4.0

        self._floating = False
        self._t0 = 0.0
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.TimerType.CoarseTimer)
        self._timer.setInterval(FLOAT_INTERVAL_MS)
        self._timer.timeout.connect(self._tick)

        self._press_global: QPoint | None = None
        self._drag_offset = QPoint()
        self._dragging = False
        self._hold_fired = False  # nhấn giữ đã kích hoạt -> lần nhả chuột này KHÔNG phải một cú nhấp
        self._hold_timer = QTimer(self)
        self._hold_timer.setSingleShot(True)
        self._hold_timer.setInterval(HOLD_MS)
        self._hold_timer.timeout.connect(self._on_hold)

    @staticmethod
    def _drag_threshold() -> int:
        """Ngưỡng (px) để coi là đang kéo; dùng chung cho kéo thả và huỷ nhấn giữ."""
        return max(1, QApplication.startDragDistance())

    def _reset_press(self) -> None:
        self._hold_timer.stop()
        self._press_global = None
        self._dragging = False
        self._hold_fired = False

    def is_pressed(self) -> bool:
        """Đang giữ chuột trái trên nhân vật (nhấn / kéo dở)?"""
        return self._press_global is not None

    def shutdown(self) -> None:
        """Dừng mọi timer (gọi khi thoát ứng dụng)."""
        self._timer.stop()
        self._hold_timer.stop()

    # ------------------------------------------------------------------ ảnh
    def has_image(self) -> bool:
        return self._pixmap is not None

    def set_image(self, image: QImage, dpr: float = 1.0) -> None:
        """Thay ảnh hiển thị; giữ nguyên điểm "chân" (giữa-đáy) của nhân vật."""
        old = self._pixmap
        anchor = None
        if old is not None:
            anchor = QPoint(self._base.x() + self.width() // 2, self._base.y() + self.height())

        pixmap = QPixmap.fromImage(image)
        pixmap.setDevicePixelRatio(dpr)
        size = QSize(max(1, round(pixmap.width() / dpr)), max(1, round(pixmap.height() / dpr)))

        self._pixmap = pixmap
        self.setFixedSize(size)
        if anchor is not None:
            self._base = QPoint(anchor.x() - size.width() // 2, anchor.y() - size.height())
        self._amp = max(3.0, size.height() * 0.01)
        self._apply_pos()
        self.update()

        # Giải phóng bộ nhớ của trang phục cũ
        old = None  # noqa: F841
        QPixmapCache.clear()
        gc.collect()

    def place_default(self) -> None:
        """Đặt nhân vật ở góc dưới bên phải màn hình chính."""
        area = QGuiApplication.primaryScreen().availableGeometry()
        self._base = QPoint(area.right() - self.width() - 40, area.bottom() - self.height() - 10)
        self._apply_pos()

    def anchor_rect(self):
        return self.frameGeometry()

    # ------------------------------------------------------------ độ mờ
    def set_opacity(self, value: float) -> None:
        """Độ trong suốt của nhân vật: 1.0 = rõ nét, 0.1 = gần như vô hình."""
        value = min(OPACITY_MAX, max(OPACITY_MIN, float(value)))
        if value != self._opacity:
            self._opacity = value
            self.update()

    # ------------------------------------------------------- Hover Mode
    @property
    def hover_mode(self) -> bool:
        return self._hover_mode

    def set_hover_mode(self, on: bool) -> None:
        """Bật: chuột xuyên qua nhân vật xuống ứng dụng bên dưới. Tắt: tương tác bình thường."""
        self._hover_mode = on
        self._reset_press()  # huỷ thao tác kéo / nhấp / nhấn giữ đang dở
        set_click_through(self, on)

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        if self._hover_mode:  # Qt vừa tạo lại cửa sổ gốc (đổi cờ...) -> áp lại cờ xuyên chuột
            set_click_through(self, True)

    # ------------------------------------------------------------ lơ lửng
    def set_floating(self, on: bool) -> None:
        self._floating = on
        if on:
            self._t0 = time.monotonic()
            self._timer.start()
        else:
            self._timer.stop()
            if self._dy:
                self._dy = 0
                self._apply_pos()

    def _tick(self) -> None:
        phase = 2 * math.pi * (time.monotonic() - self._t0) / FLOAT_PERIOD_S
        dy = round(self._amp * math.sin(phase))
        if dy != self._dy:  # chỉ di chuyển cửa sổ khi thực sự đổi pixel
            self._dy = dy
            self._apply_pos()

    def _apply_pos(self) -> None:
        self.move(self._base.x(), self._base.y() + self._dy)

    def moveEvent(self, event) -> None:  # noqa: N802
        super().moveEvent(event)
        self.moved.emit()

    # --------------------------------------------------------------- vẽ
    def paintEvent(self, _event) -> None:  # noqa: N802
        if self._pixmap is None:
            return
        painter = QPainter(self)
        if self._opacity < 1.0:
            painter.setOpacity(self._opacity)
        painter.drawPixmap(0, 0, self._pixmap)
        painter.end()

    # ----------------------------------------------------------- chuột
    def mousePressEvent(self, event) -> None:  # noqa: N802
        if self._hover_mode:  # phòng khi chuột vẫn lọt tới (API xuyên chuột lỗi)
            event.ignore()
            return
        button = event.button()
        if button == Qt.MouseButton.LeftButton:
            self._press_global = event.globalPosition().toPoint()
            self._drag_offset = self._press_global - self.pos()
            self._dragging = False
            self._hold_fired = False
            self._hold_timer.start()  # sau HOLD_MS mà chưa nhả / chưa kéo -> long_pressed
            self.interacted.emit()
            # Nhấp vào nhân vật để nhận tiêu điểm bàn phím (cho phím tắt J/K/T/S/F)
            self.activateWindow()
            self.setFocus(Qt.FocusReason.MouseFocusReason)
        elif button == Qt.MouseButton.MiddleButton:
            self.quit_requested.emit()
        event.accept()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._hover_mode:
            event.ignore()
            return
        if self._press_global is None or not (event.buttons() & Qt.MouseButton.LeftButton):
            return
        current = event.globalPosition().toPoint()
        if not self._dragging and (current - self._press_global).manhattanLength() >= self._drag_threshold():
            self._dragging = True
            self._hold_timer.stop()  # đang kéo cửa sổ -> tuyệt đối không được kích hoạt nhấn giữ
            self.interacted.emit()
        if self._dragging:
            actual = current - self._drag_offset
            self._base = QPoint(actual.x(), actual.y() - self._dy)
            self._apply_pos()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self._hover_mode:
            event.ignore()
            return
        button = event.button()
        if button == Qt.MouseButton.LeftButton:
            # Nhấp thật sự = có nhấn xuống, không kéo, và nhấn giữ chưa kích hoạt (nếu đã kích hoạt
            # thì lần nhả này không được cộng vào bộ đếm nhấp)
            was_click = self._press_global is not None and not self._dragging and not self._hold_fired
            self._reset_press()
            self.interacted.emit()
            if was_click:
                self.clicked.emit()
        elif button == Qt.MouseButton.RightButton:
            self.context_requested.emit(event.globalPosition().toPoint())
        event.accept()

    # ------------------------------------------------------- bàn phím
    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape.value:
            self.quit_requested.emit()
            return
        blocked = (
            Qt.KeyboardModifier.ControlModifier
            | Qt.KeyboardModifier.AltModifier
            | Qt.KeyboardModifier.MetaModifier
        )
        if not (event.modifiers() & blocked) and not event.isAutoRepeat():
            action = _KEY_ACTIONS.get(event.text().lower())
            if action:
                self.action_requested.emit(action)
                return
        super().keyPressEvent(event)  # Alt+F4 và các phím hệ thống đi tiếp

    def _on_hold(self) -> None:
        """Hết HOLD_MS: nếu vẫn đang giữ chuột trái tại chỗ thì phát tín hiệu nhấn giữ (đúng một lần)."""
        if self._hover_mode or self._press_global is None or self._dragging or self._hold_fired:
            return
        self._hold_fired = True
        self.long_pressed.emit()

    def closeEvent(self, event) -> None:  # noqa: N802  (Alt+F4)
        self._hold_timer.stop()
        self.quit_requested.emit()
        event.accept()
