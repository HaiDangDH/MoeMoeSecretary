"""Đọc / ghi ``config.yaml`` (luôn dùng UTF-8).

File được ghi lại từ một mẫu có chú thích tiếng Việt để người dùng dễ chỉnh sửa
bằng Notepad. Chương trình theo dõi file này (QFileSystemWatcher) nên lưu file là
áp dụng ngay, không cần chạy lại.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, replace
from pathlib import Path

import yaml

from .keyspec import format_hotkey, parse_hotkey

log = logging.getLogger(__name__)

SUPPORTED_LANGUAGES = ("vi", "en")

SCALE_MIN, SCALE_MAX = 0.2, 2.0
OPACITY_MIN, OPACITY_MAX = 0.1, 1.0
IDLE_VOICE_MIN, IDLE_VOICE_MAX = 10, 86400  # giây; 0 = tắt hẳn

DEFAULT_SHIP = "Nagato"
DEFAULT_HOVER_HOTKEY = "F12"

_TEMPLATE = """\
# Moe Moe Secretary - Cấu hình (UTF-8)
# Lưu file này là chương trình tự áp dụng ngay, không cần mở lại.

# Tên tàu trên Azur Lane Wiki (ví dụ: Nagato, Enterprise, Belfast, New Jersey)
ship_name: {ship_name}

# Trang phục đang mặc của nhân vật trên (tên trang phục trên Wiki, ví dụ: Default).
# Chương trình tự ghi khi bạn đổi trang phục hoặc thoát; để trống = trang phục mặc định.
skin_name: {skin_name}

# Ngôn ngữ giao diện: vi (Tiếng Việt) hoặc en (English)
language: {language}

# Tỷ lệ kích thước nhân vật. 1.0 = cao khoảng 600 px (cho phép 0.2 - 2.0)
scale: {scale}

# Hiệu ứng lơ lửng nhẹ nhàng (true / false)
floating: {floating}

# Luôn hiển thị trên cùng các cửa sổ khác (true / false)
always_on_top: {always_on_top}

# Âm lượng giọng nói từ 0 đến 100 (0 = tắt tiếng, không tải file âm thanh)
audio_volume: {audio_volume}

# Tự phát câu thoại riêng của trang phục khi đổi trang phục [J]/[K] (true / false)
skin_voice: {skin_voice}

# Lật ngang hình ảnh nhân vật (true / false)
flipped: {flipped}

# Độ trong suốt của nhân vật: 1.0 = rõ nét hoàn toàn, 0.1 = gần như vô hình (cho phép 0.1 - 1.0)
opacity: {opacity}

# Phím tắt TOÀN CỤC bật/tắt Hover Mode (chuột xuyên qua nhân vật, không kéo/nhấp/mở menu được).
# Ví dụ: F12, Pause, Ctrl+Alt+H, Shift+F9. Phím chữ/số phải đi kèm Ctrl/Alt/Shift/Win.
# Phím này bị chiếm ở MỌI ứng dụng khi chương trình đang chạy; nếu trùng với ứng dụng khác
# thì đổi sang tổ hợp khác.
hover_hotkey: {hover_hotkey}

# Thoại tự động khi KHÔNG tương tác: sau ngần này GIÂY nhân vật tự nói lần lượt
# Task -> Mail -> Commission rồi lặp lại. 300 = 5 phút; 0 = tắt. Cho phép 10 - 86400.
idle_voice_interval: {idle_voice_interval}
"""


@dataclass(frozen=True)
class Config:
    ship_name: str = DEFAULT_SHIP
    skin_name: str = ""  # "" = trang phục mặc định (đầu danh sách)
    language: str = "vi"
    scale: float = 1.0
    floating: bool = True
    always_on_top: bool = True
    audio_volume: int = 50
    skin_voice: bool = True
    flipped: bool = False
    opacity: float = 1.0
    hover_hotkey: str = DEFAULT_HOVER_HOTKEY
    idle_voice_interval: int = 300

    def with_(self, **changes) -> "Config":
        return replace(self, **changes)


def _as_bool(value, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        v = value.strip().lower()
        if v in ("true", "yes", "on", "1", "bật"):
            return True
        if v in ("false", "no", "off", "0", "tắt"):
            return False
    if isinstance(value, (int, float)):
        return bool(value)
    return default


def _as_float(value, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default  # chặn nan / inf


def _as_int(value, default: int) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError, OverflowError):  # OverflowError: YAML ".inf"
        return default


def sanitize(raw: dict | None) -> Config:
    """Chuyển dict đọc từ YAML thành Config hợp lệ (giá trị sai -> mặc định)."""
    d = Config()
    raw = raw if isinstance(raw, dict) else {}

    ship = str(raw.get("ship_name") or d.ship_name).strip() or d.ship_name
    lang = str(raw.get("language") or d.language).strip().lower()
    if lang not in SUPPORTED_LANGUAGES:
        lang = d.language

    skin = raw.get("skin_name")
    skin = str(skin).strip() if skin is not None else d.skin_name

    scale = min(SCALE_MAX, max(SCALE_MIN, _as_float(raw.get("scale"), d.scale)))
    volume = min(100, max(0, _as_int(raw.get("audio_volume"), d.audio_volume)))
    opacity = round(min(OPACITY_MAX, max(OPACITY_MIN, _as_float(raw.get("opacity"), d.opacity))), 2)

    hotkey = str(raw.get("hover_hotkey") or d.hover_hotkey).strip()
    if parse_hotkey(hotkey) is None:
        log.warning("hover_hotkey %r không hợp lệ, dùng %s", hotkey, d.hover_hotkey)
        hotkey = d.hover_hotkey
    hotkey = format_hotkey(hotkey)  # dạng chuẩn: "ctrl+alt+h" -> "Ctrl+Alt+H"

    idle = _as_int(raw.get("idle_voice_interval"), d.idle_voice_interval)
    idle = 0 if idle <= 0 else min(IDLE_VOICE_MAX, max(IDLE_VOICE_MIN, idle))  # 0 = tắt; còn lại kẹp 10 - 86400

    return Config(
        ship_name=ship,
        skin_name=skin,
        language=lang,
        scale=scale,
        floating=_as_bool(raw.get("floating"), d.floating),
        always_on_top=_as_bool(raw.get("always_on_top"), d.always_on_top),
        audio_volume=volume,
        skin_voice=_as_bool(raw.get("skin_voice"), d.skin_voice),
        flipped=_as_bool(raw.get("flipped"), d.flipped),
        opacity=opacity,
        hover_hotkey=hotkey,
        idle_voice_interval=idle,
    )


def _yaml_str(value: str) -> str:
    """Chuỗi YAML an toàn (giữ nguyên Unicode)."""
    dumped = yaml.safe_dump(value, allow_unicode=True, default_flow_style=True, width=10_000)
    return dumped.splitlines()[0].removesuffix("...").strip() if dumped else '""'


def render(cfg: Config) -> str:
    return _TEMPLATE.format(
        ship_name=_yaml_str(cfg.ship_name),
        skin_name=_yaml_str(cfg.skin_name),
        language=cfg.language,
        scale=f"{cfg.scale:g}",
        floating=str(cfg.floating).lower(),
        always_on_top=str(cfg.always_on_top).lower(),
        audio_volume=cfg.audio_volume,
        skin_voice=str(cfg.skin_voice).lower(),
        flipped=str(cfg.flipped).lower(),
        opacity=f"{cfg.opacity:g}",
        hover_hotkey=_yaml_str(cfg.hover_hotkey),
        idle_voice_interval=cfg.idle_voice_interval,
    )


def save(path: Path, cfg: Config) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".yaml.tmp")
    tmp.write_text(render(cfg), encoding="utf-8")
    tmp.replace(path)


def load(path: Path) -> Config:
    """Đọc config; nếu chưa có file thì tạo file mặc định."""
    if not path.exists():
        cfg = Config()
        try:
            save(path, cfg)
        except OSError as exc:  # thư mục chỉ đọc...
            log.warning("Không tạo được %s: %s", path, exc)
        return cfg
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8-sig"))
    except (OSError, yaml.YAMLError) as exc:
        log.warning("Không đọc được %s: %s", path, exc)
        return Config()
    return sanitize(raw)
