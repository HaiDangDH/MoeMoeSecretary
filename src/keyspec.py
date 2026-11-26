"""Đọc chuỗi phím tắt kiểu ``"F12"`` / ``"Ctrl+Alt+H"`` thành mã Windows.

Module thuần Python (không phụ thuộc PySide6) nên dùng được cả trong ``config.py``
(kiểm tra giá trị người dùng gõ) lẫn ``winutil.py`` (đăng ký với ``RegisterHotKey``).

Quy ước:
- Các phần ngăn cách bằng ``+``; phần cuối là phím chính, các phần trước là phím bổ trợ
  (``Ctrl``, ``Alt``, ``Shift``, ``Win``). Không phân biệt hoa/thường.
- Chỉ F1-F24, Pause và ScrollLock được đứng một mình. Mọi phím khác (chữ, số, Space, Esc,
  mũi tên, Home...) BẮT BUỘC có phím bổ trợ, vì phím tắt toàn cục sẽ chặn phím đó ở mọi
  ứng dụng khác (đứng một mình thì không ai gõ chữ hay bấm Esc được nữa).
"""
from __future__ import annotations

from dataclasses import dataclass

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008

_MODIFIERS = {"ctrl": MOD_CONTROL, "alt": MOD_ALT, "shift": MOD_SHIFT, "win": MOD_WIN}
_MODIFIER_ORDER = ("ctrl", "alt", "shift", "win")  # thứ tự hiển thị chuẩn
_MODIFIER_ALIASES = {"control": "ctrl", "meta": "win", "super": "win", "windows": "win", "cmd": "win"}

_NAMED_KEYS = {
    "escape": 0x1B, "pause": 0x13, "pageup": 0x21, "pagedown": 0x22, "end": 0x23, "home": 0x24,
    "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28, "insert": 0x2D, "delete": 0x2E,
    "numlock": 0x90, "scrolllock": 0x91, "space": 0x20, "tab": 0x09, "enter": 0x0D,
}
_BARE_OK = {"pause", "scrolllock"}  # phím có tên được phép đứng một mình (ngoài F1-F24)

_KEY_ALIASES = {
    "esc": "escape", "return": "enter", "ins": "insert", "del": "delete",
    "pgup": "pageup", "pgdn": "pagedown", "pgdown": "pagedown",
}
_DISPLAY = {"pageup": "PageUp", "pagedown": "PageDown", "numlock": "NumLock", "scrolllock": "ScrollLock"}


@dataclass(frozen=True)
class Hotkey:
    modifiers: int  # tổ hợp MOD_*
    vk: int  # mã phím ảo của Windows
    text: str  # dạng chuẩn để hiển thị / ghi vào config, ví dụ "Ctrl+Alt+H"


def _key_code(name: str) -> tuple[int, str, bool] | None:
    """(mã VK, tên hiển thị, có bắt buộc phím bổ trợ?) hoặc None nếu không hỗ trợ."""
    if len(name) == 1 and name.isascii() and name.isalnum():
        return ord(name.upper()), name.upper(), True
    if name.startswith("f") and name[1:].isdigit() and 1 <= int(name[1:]) <= 24:
        return 0x70 + int(name[1:]) - 1, f"F{int(name[1:])}", False
    name = _KEY_ALIASES.get(name, name)
    if name in _NAMED_KEYS:
        return _NAMED_KEYS[name], _DISPLAY.get(name, name.capitalize()), name not in _BARE_OK
    return None


def parse_hotkey(text: object) -> Hotkey | None:
    """Phân tích chuỗi phím tắt; trả về None nếu không hợp lệ."""
    if not isinstance(text, str):
        return None
    parts = [p.strip().lower() for p in text.split("+")]
    if not parts or any(not p for p in parts):
        return None

    mods: set[str] = set()
    for part in parts[:-1]:
        part = _MODIFIER_ALIASES.get(part, part)
        if part not in _MODIFIERS:
            return None
        mods.add(part)

    last = _MODIFIER_ALIASES.get(parts[-1], parts[-1])
    if last in _MODIFIERS:  # chỉ có phím bổ trợ, thiếu phím chính
        return None
    key = _key_code(last)
    if key is None:
        return None
    vk, key_label, needs_modifier = key
    if needs_modifier and not mods:
        return None

    ordered = [m for m in _MODIFIER_ORDER if m in mods]
    label = "+".join([m.capitalize() for m in ordered] + [key_label])
    flags = 0
    for m in ordered:
        flags |= _MODIFIERS[m]
    return Hotkey(modifiers=flags, vk=vk, text=label)


def format_hotkey(text: object) -> str:
    """Dạng chuẩn của phím tắt hợp lệ; không hợp lệ thì trả lại nguyên văn."""
    hk = parse_hotkey(text)
    return hk.text if hk else str(text)
