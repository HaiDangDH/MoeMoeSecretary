"""Tiện ích riêng cho Windows: luôn-trên-cùng, click-through và phím tắt toàn cục.

Mọi hàm đều có đường lui cho hệ điều hành khác (khi chạy thử từ mã nguồn): dùng cờ của Qt
hoặc báo "không hỗ trợ", không bao giờ ném lỗi ra ngoài.
"""
from __future__ import annotations

import logging
import sys
from types import SimpleNamespace
from typing import Callable

from PySide6.QtCore import QAbstractNativeEventFilter, QCoreApplication, Qt, QTimer
from PySide6.QtWidgets import QWidget

from .keyspec import parse_hotkey

log = logging.getLogger(__name__)

_SWP_NOSIZE = 0x0001
_SWP_NOMOVE = 0x0002
_SWP_NOACTIVATE = 0x0010

_GWL_EXSTYLE = -20
_WS_EX_TRANSPARENT = 0x00000020  # chuột xuyên qua (chỉ có tác dụng với cửa sổ "layered" - Qt đã bật sẵn)

_WM_HOTKEY = 0x0312
_MOD_NOREPEAT = 0x4000  # giữ phím không bắn lặp lại
_HOTKEY_ID = 0x4D53  # id tuỳ ý trong khoảng 0x0000-0xBFFF dành cho ứng dụng
_ERROR_HOTKEY_ALREADY_REGISTERED = 1409

_api_cache: SimpleNamespace | None = None


def _api() -> SimpleNamespace:
    """Các hàm user32 cần dùng, khai báo kiểu một lần (chỉ gọi trên Windows).

    Dùng bản ``WinDLL`` riêng của module (``use_last_error``) để đọc được mã lỗi mà không
    đụng tới ``ctypes.windll.user32`` dùng chung với phần còn lại của chương trình.
    """
    global _api_cache
    if _api_cache is None:
        import ctypes
        from ctypes import wintypes

        dll = ctypes.WinDLL("user32", use_last_error=True)
        # Python 32-bit không có GetWindowLongPtrW (chỉ là macro) -> dùng GetWindowLongW
        get_long = getattr(dll, "GetWindowLongPtrW", None) or dll.GetWindowLongW
        set_long = getattr(dll, "SetWindowLongPtrW", None) or dll.SetWindowLongW
        get_long.argtypes = [wintypes.HWND, ctypes.c_int]
        get_long.restype = ctypes.c_ssize_t
        set_long.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
        set_long.restype = ctypes.c_ssize_t
        dll.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
        dll.RegisterHotKey.restype = wintypes.BOOL
        dll.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
        dll.UnregisterHotKey.restype = wintypes.BOOL
        _api_cache = SimpleNamespace(
            get_long=get_long, set_long=set_long,
            register=dll.RegisterHotKey, unregister=dll.UnregisterHotKey,
        )
    return _api_cache


def apply_topmost(widget: QWidget, on: bool) -> None:
    """Bật/tắt "luôn hiển thị trên cùng" mà không làm cửa sổ chớp tắt.

    Trên Windows dùng SetWindowPos(HWND_TOPMOST / HWND_NOTOPMOST). Hệ điều hành khác
    (khi chạy thử từ mã nguồn) dùng cờ của Qt.
    """
    if sys.platform == "win32" and widget.isVisible():
        try:
            import ctypes
            from ctypes import wintypes

            user32 = ctypes.windll.user32
            user32.SetWindowPos.argtypes = [
                wintypes.HWND, wintypes.HWND,
                ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT,
            ]
            user32.SetWindowPos.restype = wintypes.BOOL
            insert_after = -1 if on else -2  # HWND_TOPMOST / HWND_NOTOPMOST
            ok = user32.SetWindowPos(
                wintypes.HWND(int(widget.winId())), wintypes.HWND(insert_after),
                0, 0, 0, 0, _SWP_NOMOVE | _SWP_NOSIZE | _SWP_NOACTIVATE,
            )
            if ok:
                return
        except Exception as exc:  # rơi xuống cách dùng cờ Qt
            log.debug("SetWindowPos lỗi: %s", exc)

    was_visible = widget.isVisible()
    widget.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, on)
    if was_visible:
        widget.show()


def _set_ex_style(widget: QWidget, flag: int, on: bool) -> bool:
    """Bật/tắt một cờ extended-style của cửa sổ gốc; True nếu đọc lại thấy đúng như mong muốn."""
    try:
        from ctypes import wintypes

        api = _api()
        hwnd = wintypes.HWND(int(widget.winId()))
        style = api.get_long(hwnd, _GWL_EXSTYLE)
        wanted = (style | flag) if on else (style & ~flag)
        if wanted != style:
            api.set_long(hwnd, _GWL_EXSTYLE, wanted)
        return bool(api.get_long(hwnd, _GWL_EXSTYLE) & flag) == on
    except Exception as exc:  # rơi xuống cách dùng cờ Qt
        log.debug("Đổi extended-style lỗi: %s", exc)
        return False


def set_click_through(widget: QWidget, on: bool) -> None:
    """Cho chuột xuyên qua cả cửa sổ xuống ứng dụng bên dưới (Hover Mode).

    Trên Windows chỉ đổi cờ ``WS_EX_TRANSPARENT`` của cửa sổ đang hiển thị: không ẩn/hiện lại
    nên không chớp, không mất vị trí hay tiêu điểm. Nơi khác (hoặc khi gọi API lỗi) dùng cờ
    ``Qt.WindowTransparentForInput``, phải ``show()`` lại để có hiệu lực.

    Gọi lại nhiều lần với cùng giá trị là an toàn (``MascotWindow.showEvent`` dùng để áp lại
    sau khi Qt tạo lại cửa sổ gốc).
    """
    native_ok = sys.platform == "win32" and widget.isVisible() and _set_ex_style(widget, _WS_EX_TRANSPARENT, on)
    # Cờ Qt chỉ dùng khi cách gốc không dùng được; khi TẮT thì luôn gỡ cờ Qt còn sót (nếu có)
    flag = Qt.WindowType.WindowTransparentForInput
    qt_wanted = on and not native_ok
    if bool(widget.windowFlags() & flag) == qt_wanted:
        return  # đã đúng: tránh show() lại -> showEvent -> gọi lại vô hạn
    was_visible = widget.isVisible()
    widget.setWindowFlag(flag, qt_wanted)
    if was_visible:
        widget.show()


class GlobalHotkey(QAbstractNativeEventFilter):
    """Phím tắt toàn cục (nhấn ở bất kỳ ứng dụng nào) qua ``RegisterHotKey``.

    Đăng ký theo luồng giao diện (hWnd = NULL): Windows gửi ``WM_HOTKEY`` vào hàng đợi thông
    điệp của luồng, bộ lọc sự kiện gốc của Qt bắt được rồi gọi ``callback`` trên luồng giao
    diện (hoãn bằng ``QTimer.singleShot(0)`` để không xử lý nặng bên trong bộ lọc).

    Luôn gọi :meth:`unregister` khi thoát; hàm này idempotent nên gọi nhiều lần cũng được.
    """

    def __init__(self, callback: Callable[[], None]) -> None:
        super().__init__()
        self._callback = callback
        self._registered = False
        self._installed = False

    @staticmethod
    def supported() -> bool:
        return sys.platform == "win32"

    @property
    def registered(self) -> bool:
        return self._registered

    def register(self, spec: str) -> bool:
        """Đăng ký ``spec`` (ví dụ ``"F12"``), thay thế phím cũ; False nếu không đăng ký được."""
        self.unregister()
        hotkey = parse_hotkey(spec)
        app = QCoreApplication.instance()
        if hotkey is None or app is None or not self.supported():
            return False
        try:
            import ctypes

            if not _api().register(None, _HOTKEY_ID, hotkey.modifiers | _MOD_NOREPEAT, hotkey.vk):
                code = ctypes.get_last_error()
                if code == _ERROR_HOTKEY_ALREADY_REGISTERED:
                    log.warning("Phím tắt %s đã bị ứng dụng khác chiếm", hotkey.text)
                else:
                    log.warning("RegisterHotKey(%s) lỗi, mã %s", hotkey.text, code)
                return False
        except Exception:  # noqa: BLE001
            log.warning("Không đăng ký được phím tắt %s", hotkey.text, exc_info=True)
            return False
        self._registered = True
        app.installNativeEventFilter(self)
        self._installed = True
        return True

    def unregister(self) -> None:
        """Hủy đăng ký và gỡ bộ lọc (idempotent)."""
        if self._registered:
            self._registered = False
            try:
                _api().unregister(None, _HOTKEY_ID)
            except Exception as exc:  # noqa: BLE001
                log.debug("UnregisterHotKey lỗi: %s", exc)
        if self._installed:
            self._installed = False
            app = QCoreApplication.instance()
            if app is not None:
                app.removeNativeEventFilter(self)

    def nativeEventFilter(self, event_type, message):  # noqa: N802
        # Chạy cho MỌI thông điệp gốc của Qt: thoát sớm, tuyệt đối không ném lỗi.
        if not self._registered:
            return False, 0
        try:
            if bytes(event_type) == b"windows_generic_MSG":
                from ctypes import wintypes

                msg = wintypes.MSG.from_address(int(message))
                if msg.message == _WM_HOTKEY and msg.wParam == _HOTKEY_ID:
                    QTimer.singleShot(0, self._callback)
                    return True, 0
        except Exception as exc:  # noqa: BLE001
            log.debug("Lỗi khi đọc thông điệp phím tắt: %s", exc)
        return False, 0
