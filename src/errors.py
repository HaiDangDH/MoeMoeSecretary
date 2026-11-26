"""Các lỗi dùng chung (module nhỏ, không kéo theo thư viện nặng khi import)."""
from __future__ import annotations


class ScraperError(Exception):
    """Lỗi chung của bộ thu thập."""


class ShipNotFound(ScraperError):
    """Không tìm thấy trang nhân vật trên Wiki."""


class NetworkError(ScraperError):
    """Không kết nối được (mất mạng, timeout, máy chủ lỗi)."""


class NoImageError(ScraperError):
    """Có trang nhân vật nhưng không tìm thấy hình ảnh."""


class AccessBlocked(NetworkError):
    """Wiki từ chối yêu cầu (HTTP 403): thường do bộ lọc bot / tường lửa của Wiki."""
