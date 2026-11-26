"""Điểm vào của ứng dụng: ghi log, chống mở trùng, khởi tạo Qt."""
from __future__ import annotations

import logging
import logging.handlers
import os
import sys
import tempfile

from . import paths


def _setup_logging() -> None:
    # Khi đóng gói --windowed, sys.stdout/stderr là None -> tránh lỗi khi thư viện in ra
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115

    handlers: list[logging.Handler] = []
    try:
        handlers.append(
            logging.handlers.RotatingFileHandler(
                paths.app_dir() / "moe_moe_secretary.log",
                maxBytes=256 * 1024, backupCount=1, encoding="utf-8",
            )
        )
    except OSError:
        pass  # thư mục chỉ đọc: bỏ qua ghi log
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=handlers or [logging.NullHandler()],
    )

    def _hook(exc_type, exc, tb) -> None:
        logging.getLogger("uncaught").error("Lỗi chưa xử lý", exc_info=(exc_type, exc, tb))

    sys.excepthook = _hook


def main() -> int:
    _setup_logging()

    from PySide6.QtCore import QLockFile, Qt
    from PySide6.QtGui import QFont
    from PySide6.QtWidgets import QApplication

    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setApplicationName("Moe Moe Secretary")
    app.setQuitOnLastWindowClosed(False)  # còn icon khay hệ thống
    app.setFont(QFont("Segoe UI", 9))  # hiển thị tiếng Việt có dấu sắc nét

    # Chỉ cho phép một cửa sổ nhân vật tại một thời điểm
    lock = QLockFile(os.path.join(tempfile.gettempdir(), "MoeMoeSecretaryVN.lock"))
    if not lock.tryLock(100):
        return 0

    from .controller import Controller

    controller = Controller(app)
    controller.start()
    code = app.exec()
    lock.unlock()
    return code
