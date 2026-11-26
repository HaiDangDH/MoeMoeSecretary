"""Đường dẫn an toàn khi chạy từ mã nguồn hoặc khi đã đóng gói bằng PyInstaller.

Khi chạy dưới dạng .exe (``sys.frozen``), thư mục gốc là thư mục chứa chính file
.exe (``Path(sys.executable).parent``) - KHÔNG dùng ``sys._MEIPASS`` vì đó là thư
mục tạm bị xoá mỗi lần thoát ứng dụng.
"""
from __future__ import annotations

import sys
from pathlib import Path


def app_dir() -> Path:
    """Thư mục gốc chứa ``config.yaml`` và ``cache/``."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    # src/paths.py -> thư mục dự án
    return Path(__file__).resolve().parent.parent


def config_path() -> Path:
    return app_dir() / "config.yaml"


def cache_dir() -> Path:
    path = app_dir() / "cache"
    path.mkdir(parents=True, exist_ok=True)
    return path
