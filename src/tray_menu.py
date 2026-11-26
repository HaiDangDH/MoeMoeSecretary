"""Menu chuột phải (trên nhân vật) và icon khay hệ thống dùng CHUNG một QMenu.

Vì cửa sổ nhân vật không có thanh tiêu đề, mọi điều khiển đều nằm ở đây. Các mục có
dấu tích (T / F / S) luôn được đồng bộ với trạng thái thật qua ``sync``.

Khi Hover Mode bật, chuột xuyên qua nhân vật nên không mở được menu chuột phải; icon khay hệ
thống (cùng menu này) và phím tắt toàn cục là hai đường để tắt lại.
"""
from __future__ import annotations

from PySide6.QtCore import QObject, QPoint, Signal
from PySide6.QtGui import QAction, QActionGroup, QIcon
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from .config import Config
from .locales import LANGUAGE_NAMES, format_duration, tr

OPACITY_LEVELS = (1.0, 0.8, 0.6, 0.4, 0.2)  # các mức trong menu (100% ... 20%)
IDLE_PRESETS = (0, 60, 300, 900, 1800, 3600)  # giây giữa các lần tự nói khi rảnh; 0 = tắt
_OPACITY_EPS = 0.005  # sai số khi so khớp mức đang dùng với giá trị trong config


class AppMenu(QObject):
    choose_ship = Signal()
    next_skin = Signal()
    prev_skin = Signal()
    top_toggled = Signal(bool)
    floating_toggled = Signal(bool)
    flip_toggled = Signal(bool)
    hover_toggled = Signal(bool)
    opacity_selected = Signal(float)  # 0.1 - 1.0
    idle_interval_selected = Signal(int)  # giây; 0 = tắt
    help_requested = Signal()
    language_selected = Signal(str)
    open_data = Signal()
    quit_requested = Signal()
    tray_clicked = Signal()  # nhấp trái vào icon khay -> đưa nhân vật lên trước

    def __init__(self, icon: QIcon, cfg: Config) -> None:
        super().__init__()
        self.menu = QMenu()
        self._hover_key = cfg.hover_hotkey  # hiển thị bên cạnh mục Hover Mode

        self._a_choose = self.menu.addAction("")
        self._a_choose.triggered.connect(lambda: self.choose_ship.emit())
        self.menu.addSeparator()

        self._a_next = self.menu.addAction("")
        self._a_next.triggered.connect(lambda: self.next_skin.emit())
        self._a_prev = self.menu.addAction("")
        self._a_prev.triggered.connect(lambda: self.prev_skin.emit())
        self.menu.addSeparator()

        self._a_top = self._checkable(self.top_toggled)
        self._a_float = self._checkable(self.floating_toggled)
        self._a_flip = self._checkable(self.flip_toggled)
        self._a_hover = self._checkable(self.hover_toggled)
        self.menu.addSeparator()

        self._m_opacity = self.menu.addMenu("")
        self._opacity_group = QActionGroup(self.menu)
        self._opacity_group.setExclusive(True)
        self._opacity_actions: dict[float, QAction] = {}
        for level in OPACITY_LEVELS:
            action = self._m_opacity.addAction(f"{round(level * 100)}%")
            action.setCheckable(True)
            action.setActionGroup(self._opacity_group)
            action.triggered.connect(lambda _checked=False, v=level: self.opacity_selected.emit(v))
            self._opacity_actions[level] = action

        self._m_idle = self.menu.addMenu("")
        self._idle_group = QActionGroup(self.menu)
        self._idle_group.setExclusive(True)
        self._idle_actions: dict[int, QAction] = {}
        for seconds in IDLE_PRESETS:
            action = self._m_idle.addAction("")  # chữ được đặt trong retranslate()
            action.setCheckable(True)
            action.setActionGroup(self._idle_group)
            action.triggered.connect(lambda _checked=False, v=seconds: self.idle_interval_selected.emit(v))
            self._idle_actions[seconds] = action

        self._m_lang = self.menu.addMenu("")
        self._lang_group = QActionGroup(self.menu)
        self._lang_group.setExclusive(True)
        self._lang_actions: dict[str, QAction] = {}
        for code, name in LANGUAGE_NAMES.items():
            action = self._m_lang.addAction(name)
            action.setCheckable(True)
            action.setActionGroup(self._lang_group)
            action.triggered.connect(lambda _checked=False, c=code: self.language_selected.emit(c))
            self._lang_actions[code] = action

        self._a_open = self.menu.addAction("")
        self._a_open.triggered.connect(lambda: self.open_data.emit())
        self._a_help = self.menu.addAction("")
        self._a_help.triggered.connect(lambda: self.help_requested.emit())
        self.menu.addSeparator()
        self._a_quit = self.menu.addAction("")
        self._a_quit.triggered.connect(lambda: self.quit_requested.emit())

        self.tray: QSystemTrayIcon | None = None
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = QSystemTrayIcon(icon)
            self.tray.setContextMenu(self.menu)
            self.tray.activated.connect(self._on_tray_activated)
            self.tray.show()

        self.retranslate()
        self.sync(cfg)

    # ------------------------------------------------------------------
    def _checkable(self, signal: Signal) -> QAction:
        action = self.menu.addAction("")
        action.setCheckable(True)
        action.triggered.connect(lambda checked, s=signal: s.emit(bool(checked)))
        return action

    def _on_tray_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.tray_clicked.emit()

    # ------------------------------------------------------------------
    def retranslate(self, ship_name: str = "") -> None:
        self._a_choose.setText(tr("menu.choose_ship"))
        self._a_next.setText(tr("menu.next_skin"))
        self._a_prev.setText(tr("menu.prev_skin"))
        self._a_top.setText(tr("menu.always_on_top"))
        self._a_float.setText(tr("menu.floating"))
        self._a_flip.setText(tr("menu.flip"))
        self._a_hover.setText(tr("menu.hover_mode", hotkey=self._hover_key))
        self._m_opacity.setTitle(tr("menu.opacity"))
        self._m_idle.setTitle(tr("menu.idle_voice"))
        for seconds, action in self._idle_actions.items():
            action.setText(tr("menu.idle_off") if seconds == 0 else format_duration(seconds))
        self._m_lang.setTitle(tr("menu.language"))
        self._a_open.setText(tr("menu.open_data"))
        self._a_help.setText(tr("menu.help"))
        self._a_quit.setText(tr("menu.quit"))
        self.set_tooltip(ship_name)

    def set_tooltip(self, ship_name: str) -> None:
        if self.tray is not None:
            self.tray.setToolTip(tr("tray.tooltip", name=ship_name or "..."))

    def sync(self, cfg: Config) -> None:
        """Đồng bộ dấu tích với cấu hình hiện tại (không phát signal)."""
        self._a_top.setChecked(cfg.always_on_top)
        self._a_float.setChecked(cfg.floating)
        self._a_flip.setChecked(cfg.flipped)
        for level, action in self._opacity_actions.items():
            action.setChecked(abs(level - cfg.opacity) < _OPACITY_EPS)  # mức lạ -> không mức nào được tích
        for seconds, action in self._idle_actions.items():
            action.setChecked(seconds == cfg.idle_voice_interval)  # giá trị tự đặt trong config -> không mục nào được tích
        for code, action in self._lang_actions.items():
            action.setChecked(code == cfg.language)
        if cfg.hover_hotkey != self._hover_key:  # người dùng vừa đổi phím tắt trong config.yaml
            self._hover_key = cfg.hover_hotkey
            self._a_hover.setText(tr("menu.hover_mode", hotkey=self._hover_key))

    def set_hover(self, on: bool) -> None:
        """Đồng bộ dấu tích Hover Mode (trạng thái này chỉ sống trong phiên chạy, không nằm trong cfg)."""
        self._a_hover.setChecked(on)

    def show_message(self, text: str) -> bool:
        """Thông báo của khay hệ thống (không đè lên bong bóng thoại); False nếu không có khay."""
        if self.tray is None:
            return False
        self.tray.showMessage("Moe Moe Secretary", text, QSystemTrayIcon.MessageIcon.Warning, 8000)
        return True

    def popup(self, global_pos: QPoint) -> None:
        self.menu.popup(global_pos)

    def hide_tray(self) -> None:
        if self.tray is not None:
            self.tray.hide()
