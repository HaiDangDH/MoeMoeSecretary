"""Đa ngôn ngữ siêu nhẹ: chỉ là một từ điển, không tốn tài nguyên.

Mặc định là Tiếng Việt (``vi``), có thể chuyển sang English (``en``).
Lời thoại gốc của nhân vật lấy từ Wiki được giữ nguyên, không dịch.
"""
from __future__ import annotations

DEFAULT_LANGUAGE = "vi"
LANGUAGE_NAMES = {"vi": "Tiếng Việt", "en": "English"}

_STRINGS: dict[str, dict[str, str]] = {
    # ---- Menu ---------------------------------------------------------
    "menu.choose_ship": {"vi": "Chọn nhân vật...", "en": "Choose character..."},
    "menu.next_skin": {"vi": "Trang phục tiếp theo [J]", "en": "Next skin [J]"},
    "menu.prev_skin": {"vi": "Trang phục trước [K]", "en": "Previous skin [K]"},
    "menu.always_on_top": {"vi": "Luôn hiển thị trên cùng [T]", "en": "Always on top [T]"},
    "menu.floating": {"vi": "Hiệu ứng lơ lửng [F]", "en": "Floating effect [F]"},
    "menu.flip": {"vi": "Lật ngang nhân vật [S]", "en": "Flip horizontally [S]"},
    "menu.hover_mode": {
        "vi": "Chế độ Hover - chuột xuyên qua [{hotkey}]",
        "en": "Hover mode - click-through [{hotkey}]",
    },
    "menu.opacity": {"vi": "Độ trong suốt", "en": "Opacity"},
    "menu.idle_voice": {"vi": "Thoại khi rảnh", "en": "Idle voice"},
    "menu.idle_off": {"vi": "Tắt", "en": "Off"},
    "menu.language": {"vi": "Ngôn ngữ", "en": "Language"},
    "menu.open_data": {"vi": "Mở thư mục dữ liệu", "en": "Open data folder"},
    "menu.help": {"vi": "Trợ giúp", "en": "Help"},
    "menu.quit": {"vi": "Thoát", "en": "Quit"},
    "tray.tooltip": {"vi": "Moe Moe Secretary - {name}", "en": "Moe Moe Secretary - {name}"},
    # ---- Hộp thoại chọn nhân vật --------------------------------------
    "dialog.title": {"vi": "Chọn nhân vật", "en": "Choose character"},
    "dialog.label": {
        "vi": "Nhập tên tàu (ví dụ: Enterprise, Belfast, New Jersey):",
        "en": "Enter a ship name (e.g. Enterprise, Belfast, New Jersey):",
    },
    "dialog.ok": {"vi": "Đổi ngay", "en": "Switch"},
    "dialog.cancel": {"vi": "Hủy", "en": "Cancel"},
    # ---- Trạng thái / thông báo --------------------------------------
    "status.loading_ship": {
        "vi": "Đang tải dữ liệu của {name}...",
        "en": "Loading data for {name}...",
    },
    "status.loading_skin": {
        "vi": "Đang tải trang phục: {name}...",
        "en": "Loading skin: {name}...",
    },
    "status.skin_changed": {
        "vi": "Đã đổi sang trang phục: {name}",
        "en": "Switched to skin: {name}",
    },
    "status.single_skin": {
        "vi": "Nhân vật này chỉ có một trang phục.",
        "en": "This character only has one skin.",
    },
    "status.ship_not_found": {
        "vi": "Không tìm thấy nhân vật trên Wiki, vui lòng kiểm tra lại tên",
        "en": "Character not found on the Wiki, please check the name",
    },
    "status.network_error": {
        "vi": "Không kết nối được tới Wiki. Vui lòng kiểm tra mạng rồi thử lại.",
        "en": "Could not reach the Wiki. Please check your connection and try again.",
    },
    "status.access_blocked": {
        "vi": "Wiki từ chối truy cập (lỗi 403). Có thể Wiki đang chặn ứng dụng tự động; xem file moe_moe_secretary.log hoặc thử lại sau.",
        "en": "The Wiki refused access (error 403). It may be blocking automated clients; see moe_moe_secretary.log or try again later.",
    },
    "status.no_image": {
        "vi": "Không tìm thấy hình ảnh của {name} trên Wiki.",
        "en": "No image of {name} was found on the Wiki.",
    },
    "status.no_quotes": {
        "vi": "Nhân vật này chưa có câu thoại trên Wiki.",
        "en": "No quotes for this character on the Wiki yet.",
    },
    "status.ship_ready": {
        "vi": "{name} đã sẵn sàng!",
        "en": "{name} is ready!",
    },
    "status.on_top_on": {
        "vi": "Đã bật: luôn hiển thị trên cùng",
        "en": "Always on top: on",
    },
    "status.on_top_off": {
        "vi": "Đã tắt: luôn hiển thị trên cùng",
        "en": "Always on top: off",
    },
    "status.floating_on": {"vi": "Đã bật hiệu ứng lơ lửng", "en": "Floating effect: on"},
    "status.floating_off": {"vi": "Đã tắt hiệu ứng lơ lửng", "en": "Floating effect: off"},
    "status.flip_on": {"vi": "Đã lật ngang nhân vật", "en": "Character flipped"},
    "status.flip_off": {"vi": "Đã trả lại hướng ban đầu", "en": "Original direction restored"},
    "status.opacity_changed": {
        "vi": "Độ trong suốt: {percent}%",
        "en": "Opacity: {percent}%",
    },
    "status.hover_on": {
        "vi": "Hover Mode: BẬT - chuột xuyên qua nhân vật. Nhấn {hotkey} để tắt.",
        "en": "Hover mode: ON - clicks pass through the character. Press {hotkey} to turn it off.",
    },
    "status.hover_on_tray": {
        "vi": "Hover Mode: BẬT - chuột xuyên qua nhân vật. Tắt bằng menu ở icon khay hệ thống.",
        "en": "Hover mode: ON - clicks pass through the character. Turn it off from the tray icon menu.",
    },
    "status.hover_off": {
        "vi": "Hover Mode: TẮT - đã nhận chuột trở lại.",
        "en": "Hover mode: OFF - the character reacts to the mouse again.",
    },
    "status.hover_unavailable": {
        "vi": "Không bật được Hover Mode: không có phím tắt {hotkey} lẫn icon khay hệ thống để tắt lại.",
        "en": "Cannot enable hover mode: neither the {hotkey} hotkey nor a tray icon is available to turn it off.",
    },
    "status.hotkey_failed": {
        "vi": "Không đăng ký được phím tắt {hotkey} (có thể đã bị ứng dụng khác dùng). Hãy đổi hover_hotkey trong config.yaml.",
        "en": "Could not register the {hotkey} hotkey (it may be used by another app). Change hover_hotkey in config.yaml.",
    },
    "status.idle_changed": {
        "vi": "Thoại khi rảnh: mỗi {time} không tương tác.",
        "en": "Idle voice: after {time} without interaction.",
    },
    "status.idle_off": {"vi": "Đã tắt thoại khi rảnh.", "en": "Idle voice turned off."},
    # ---- Cửa sổ Trợ giúp -----------------------------------------------
    "help.title": {"vi": "Trợ giúp - Moe Moe Secretary", "en": "Help - Moe Moe Secretary"},
    "help.close": {"vi": "Đóng", "en": "Close"},
    "help.intro": {
        "vi": "Các thao tác với nhân vật trên màn hình:",
        "en": "How to interact with the character on your screen:",
    },
    "help.click.t": {"vi": "Click chuột trái (1 lần)", "en": "Left click (once)"},
    "help.click.d": {
        "vi": "Tương tác cơ bản: nhân vật nói một câu thoại ngẫu nhiên.",
        "en": "Basic interaction: the character says a random line.",
    },
    "help.love.t": {"vi": "Click chuột trái liên tục 5 lần", "en": "Left click 5 times in a row"},
    "help.love.d": {
        "vi": "Kích hoạt lời thoại đặc biệt <b>Affinity (Love)</b>. Các lần click phải cách nhau dưới "
        "{gap} giây, nếu không bộ đếm quay về 0.",
        "en": "Triggers the special <b>Affinity (Love)</b> line. Clicks must be less than {gap} seconds "
        "apart, otherwise the counter resets.",
    },
    "help.hold.t": {"vi": "Nhấn giữ chuột trái (> 1.5 giây)", "en": "Press and hold left button (> 1.5 s)"},
    "help.hold.d": {
        "vi": "Kích hoạt lời thoại <b>Pledge</b> - luôn dùng thoại của <b>trang phục mặc định</b>, "
        "bất kể nhân vật đang mặc bộ nào. Nhả chuột sau đó không tính là một cú click.",
        "en": "Triggers the <b>Pledge</b> line - always the one from the <b>default skin</b>, whatever "
        "outfit is being worn. Releasing afterwards does not count as a click.",
    },
    "help.drag.t": {"vi": "Nhấn giữ chuột trái + di chuyển", "en": "Hold left button + move"},
    "help.drag.d": {
        "vi": "Kéo thả để đổi vị trí hiển thị của nhân vật trên màn hình.",
        "en": "Drag to move the character around the screen.",
    },
    "help.right.t": {"vi": "Click chuột phải", "en": "Right click"},
    "help.right.d": {
        "vi": "Mở bảng tuỳ chọn: đổi nhân vật, đổi trang phục, chỉnh độ trong suốt, cài đặt, trợ giúp, "
        "thoát ứng dụng. Menu này cũng nằm ở biểu tượng khay hệ thống.",
        "en": "Opens the options menu: change character, change skin, opacity, settings, help, quit. "
        "The same menu is available from the system tray icon.",
    },
    "help.hover.t": {"vi": "Phím tắt Hover Mode: {hotkey}", "en": "Hover Mode hotkey: {hotkey}"},
    "help.hover.d": {
        "vi": "Bật/tắt chế độ xuyên thấu chuột (chuột đi xuyên qua nhân vật xuống ứng dụng bên dưới). "
        "Nhân vật nói <b>Start mission</b> khi bật và <b>Return from mission</b> khi tắt. "
        "Phím tắt này hoạt động ở mọi ứng dụng; đổi bằng <i>hover_hotkey</i> trong config.yaml.",
        "en": "Toggles click-through mode (the mouse passes through the character to the app below). "
        "The character says <b>Start mission</b> when turned on and <b>Return from mission</b> when "
        "turned off. The hotkey works in any app; change it with <i>hover_hotkey</i> in config.yaml.",
    },
    "help.idle.t": {"vi": "Tự động nói khi rảnh", "en": "Automatic idle voice"},
    "help.idle.d": {
        "vi": "Sau <b>{time}</b> không tương tác, nhân vật tự nói lần lượt <b>Task</b>, <b>Mail</b>, "
        "<b>Commission</b> rồi lặp lại. Mọi thao tác (click, kéo, đổi trang phục, đổi nhân vật, "
        "Hover Mode...) đều đếm lại từ đầu. Chỉnh ở menu <i>Thoại khi rảnh</i> hoặc "
        "<i>idle_voice_interval</i> (giây) trong config.yaml.",
        "en": "After <b>{time}</b> without interaction, the character says <b>Task</b>, <b>Mail</b>, "
        "<b>Commission</b> in turn, then repeats. Any interaction (click, drag, changing skin or "
        "character, Hover Mode...) restarts the countdown. Adjust it in the <i>Idle voice</i> menu or "
        "with <i>idle_voice_interval</i> (seconds) in config.yaml.",
    },
    "help.idle.off": {
        "vi": "Đang <b>tắt</b>. Bật ở menu <i>Thoại khi rảnh</i> hoặc đặt <i>idle_voice_interval</i> "
        "(giây) trong config.yaml.",
        "en": "Currently <b>off</b>. Turn it on from the <i>Idle voice</i> menu or set "
        "<i>idle_voice_interval</i> (seconds) in config.yaml.",
    },
    "help.keys.t": {"vi": "Phím và chuột giữa", "en": "Keys and middle button"},
    "help.keys.d": {
        "vi": "Khi cửa sổ nhân vật đang được chọn: <b>J / K</b> đổi trang phục, <b>T</b> luôn trên cùng, "
        "<b>S</b> lật ngang, <b>F</b> lơ lửng, <b>Esc</b> hoặc <b>click chuột giữa</b> để thoát.",
        "en": "While the character window is focused: <b>J / K</b> change skin, <b>T</b> always on top, "
        "<b>S</b> flip, <b>F</b> floating, <b>Esc</b> or <b>middle click</b> to quit.",
    },
    # ---- Đơn vị thời gian --------------------------------------------
    "unit.hour": {"vi": "{n} giờ", "en": "{n} h"},
    "unit.minute": {"vi": "{n} phút", "en": "{n} min"},
    "unit.second": {"vi": "{n} giây", "en": "{n} s"},
    "status.language_changed": {
        "vi": "Đã chuyển sang Tiếng Việt",
        "en": "Language switched to English",
    },
    "status.config_reloaded": {
        "vi": "Đã áp dụng cấu hình mới",
        "en": "New configuration applied",
    },
}


class _State:
    language = DEFAULT_LANGUAGE


def set_language(lang: str) -> None:
    _State.language = lang if lang in LANGUAGE_NAMES else DEFAULT_LANGUAGE


def get_language() -> str:
    return _State.language


def tr(key: str, **kwargs) -> str:
    """Dịch một khóa sang ngôn ngữ hiện tại (thiếu bản dịch -> rơi về Tiếng Việt)."""
    entry = _STRINGS.get(key)
    if entry is None:
        return key
    text = entry.get(_State.language) or entry.get(DEFAULT_LANGUAGE) or key
    return text.format(**kwargs) if kwargs else text


def format_duration(seconds: int) -> str:
    """Số giây -> chuỗi dễ đọc theo ngôn ngữ hiện tại: 300 -> "5 phút", 90 -> "90 giây", 7200 -> "2 giờ"."""
    if seconds >= 3600 and seconds % 3600 == 0:
        return tr("unit.hour", n=seconds // 3600)
    if seconds >= 60 and seconds % 60 == 0:
        return tr("unit.minute", n=seconds // 60)
    return tr("unit.second", n=seconds)
