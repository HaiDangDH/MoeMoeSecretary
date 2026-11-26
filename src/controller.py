"""Bộ điều khiển: nối giao diện, bộ thu thập, cache, âm thanh và cấu hình."""
from __future__ import annotations

import logging
import random
import threading
import time
from pathlib import Path
from typing import Iterable

from PySide6.QtCore import QFileSystemWatcher, QObject, Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QImage
from PySide6.QtWidgets import QApplication, QInputDialog

from . import config as cfgmod
from . import locales, paths
from .audio import VoicePlayer
from .bubble import BubbleWindow
from .cache import PreloadResult, ShipCache, process_image
from .config import Config
from .errors import AccessBlocked, NetworkError, NoImageError, ScraperError, ShipNotFound
from .help_dialog import HelpDialog
from .icons import make_icon, make_image
from .locales import tr
from .models import (
    SCHEMA_VERSION,
    VOICE_COMMISSION,
    VOICE_LOVE,
    VOICE_MAIL,
    VOICE_PLEDGE,
    VOICE_RETURN_MISSION,
    VOICE_START_MISSION,
    VOICE_TASK,
    Quote,
    ShipData,
    Skin,
    norm,
    voice_matches,
)
from .skinmatch import is_default, match_skins, quote_groups, skin_labels
from .overlay import MascotWindow
from .tray_menu import AppMenu
from .winutil import GlobalHotkey, apply_topmost
from .workers import Dispatcher

log = logging.getLogger(__name__)

BASE_HEIGHT = 600  # chiều cao (px) của nhân vật khi scale = 1.0
LOVE_CLICKS = 5  # nhấp chuột trái liên tiếp ngần này lần -> thoại "Affinity (Love)"
LOVE_CLICK_GAP = 1.2  # giây: hai lần nhấp liền kề cách nhau quá mức này thì chuỗi đếm về 0
_IDLE_CYCLE = (VOICE_TASK, VOICE_MAIL, VOICE_COMMISSION)  # thoại tự động khi rảnh, luân phiên theo vòng
SKIN_VOICE_DELAY_MS = 1100  # chờ thông báo "Đã đổi sang trang phục..." đọc xong rồi mới phát thoại riêng

_EVENT_PATTERNS = {
    "touch": ("secretary (idle)", "secretary (touch)", "details"),
    "greeting": ("login", "self introduction", "acquisition"),
    # Khi đổi trang phục: ưu tiên câu giới thiệu bộ đồ ("Acquisition"/"Ship Description")
    "skin": ("acquisition", "login", "self introduction", "ship description"),
}
_PRIORITY_KINDS = ("greeting", "skin")  # chọn theo thứ tự ưu tiên thay vì gộp tất cả


def _matches(event: str, pattern: str) -> bool:
    return event.strip().lower().startswith(pattern)


class Controller(QObject):
    def __init__(self, app: QApplication) -> None:
        super().__init__()
        self._app = app
        self.cfg: Config = cfgmod.load(paths.config_path())
        locales.set_language(self.cfg.language)

        self.cache = ShipCache(paths.cache_dir())
        self.player = VoicePlayer()
        self.dispatcher = Dispatcher(max_threads=2, parent=self)
        # Luồng riêng cho việc tải trước giọng nói: tải cả bộ thoại có thể kéo dài, không được chiếm
        # chỗ của việc tải ảnh nhân vật / trang phục ở hàng đợi chính.
        self.voice_dispatcher = Dispatcher(max_threads=1, parent=self)
        self._scraper = None
        self._scraper_lock = threading.Lock()

        # Trạng thái
        self.ship: ShipData | None = None
        self.skin_index = 0
        self._target_idx = 0
        self._skin_path: Path | None = None
        self._skin_groups: list[str | None] = []  # nhóm câu thoại riêng của từng trang phục
        self._skin_labels: list[str] = []  # tên hiển thị (ưu tiên tên chính thức từ mục thoại)
        self._skin_voice_token = 0
        self._ship_gen = 0
        self._skin_req = 0
        self._voice_token = 0
        self._click_streak = 0  # số lần nhấp liên tiếp (cho thoại Affinity (Love))
        self._last_click = 0.0
        self._idle_idx = 0  # đang tới lượt mục nào trong _IDLE_CYCLE
        self._closing = threading.Event()  # báo cho các luồng nền biết ứng dụng đang thoát
        self._wanted_voices: frozenset[tuple[str, str]] = frozenset()  # (wiki_title, nhóm) cần tải trước
        self._help: HelpDialog | None = None
        self._last_quote: Quote | None = None
        self._dialog_open = False
        self._quitting = False
        self._hover = False  # Hover Mode chỉ sống trong phiên chạy: mỗi lần mở luôn bắt đầu ở trạng thái TẮT

        # Giao diện
        self.icon = make_icon(64)
        self.mascot = MascotWindow(on_top=self.cfg.always_on_top)
        self.mascot.set_opacity(self.cfg.opacity)
        self.bubble = BubbleWindow(on_top=self.cfg.always_on_top)
        self.menu = AppMenu(self.icon, self.cfg)
        self.mascot.setWindowIcon(self.icon)

        self.mascot.clicked.connect(self.on_click)
        self.mascot.long_pressed.connect(self.on_long_press)
        self.mascot.interacted.connect(self._reset_idle)
        self.mascot.context_requested.connect(self.menu.popup)
        self.mascot.context_requested.connect(lambda _pos: self._reset_idle())
        self.mascot.moved.connect(self._follow_bubble)
        self.mascot.action_requested.connect(self._on_action)
        self.mascot.quit_requested.connect(self.quit)

        # Phím tắt toàn cục: luôn được hủy khi thoát (xem quit() và aboutToQuit)
        self.hotkey = GlobalHotkey(self._on_hotkey)
        app.aboutToQuit.connect(self.hotkey.unregister)

        self.menu.choose_ship.connect(self.choose_ship_dialog)
        self.menu.next_skin.connect(lambda: self.change_skin(+1))
        self.menu.prev_skin.connect(lambda: self.change_skin(-1))
        self.menu.top_toggled.connect(self.set_always_on_top)
        self.menu.floating_toggled.connect(self.set_floating)
        self.menu.flip_toggled.connect(self.set_flipped)
        self.menu.hover_toggled.connect(self.set_hover_mode)
        self.menu.opacity_selected.connect(self.set_opacity)
        self.menu.idle_interval_selected.connect(self.set_idle_interval)
        self.menu.language_selected.connect(self.set_language)
        self.menu.help_requested.connect(self.show_help)
        self.menu.open_data.connect(self.open_data_folder)
        self.menu.quit_requested.connect(self.quit)
        self.menu.tray_clicked.connect(self._bring_to_front)

        # Theo dõi config.yaml: lưu file là áp dụng ngay (hướng sự kiện, không polling)
        self._watcher = QFileSystemWatcher(self)
        self._reload_timer = QTimer(self)
        self._reload_timer.setSingleShot(True)
        self._reload_timer.setInterval(300)
        self._reload_timer.timeout.connect(self._reload_config)
        # Đếm thời gian không tương tác -> thoại tự động (xem _on_idle)
        self._idle_timer = QTimer(self)
        self._idle_timer.setSingleShot(True)
        self._idle_timer.timeout.connect(self._on_idle)

        self._watcher.fileChanged.connect(lambda _p: self._reload_timer.start())
        self._watcher.directoryChanged.connect(lambda _p: self._reload_timer.start())
        self._watch_config()

    # ================================================================ khởi động
    def start(self) -> None:
        self.mascot.set_image(make_image(180), 1.0)  # hình tạm trong lúc tải
        self.mascot.place_default()
        self.mascot.show()
        apply_topmost(self.mascot, self.cfg.always_on_top)
        self.mascot.set_floating(self.cfg.floating)
        self.menu.retranslate()
        self._register_hotkey()
        # Mở lại đúng nhân vật + trang phục đã lưu lần trước
        self.request_ship(self.cfg.ship_name, self.cfg.skin_name)
        self._reset_idle()

    def quit(self) -> None:
        if self._quitting:
            return
        self._quitting = True
        self._closing.set()  # các luồng nền (tải trước giọng nói...) tự dừng ở bước kế tiếp
        # Dừng MỌI timer trước khi đóng cửa sổ: không để timer nào bắn khi giao diện đang bị phá
        self._idle_timer.stop()
        self._reload_timer.stop()
        self.mascot.shutdown()
        if self._help is not None:
            self._help.close()
            self._help.deleteLater()
            self._help = None
        self.hotkey.unregister()  # trả lại phím tắt cho hệ thống
        self._persist_skin()
        self.player.shutdown()
        self.menu.hide_tray()
        self.bubble.hide_message()  # dừng cả timer tự ẩn của bong bóng, không chỉ ẩn cửa sổ
        self.mascot.hide()
        self.voice_dispatcher.shutdown(1200)  # bỏ hàng đợi tải giọng nói, chờ file đang tải dở
        self.dispatcher.wait_done(800)
        if self._scraper is not None:
            try:
                self._scraper.close()
            except Exception:  # noqa: BLE001
                pass
        self._app.quit()

    # ================================================================ tiện ích
    def say(self, text: str, persist: bool = False) -> None:
        self.bubble.show_message(text, self.mascot.anchor_rect(), persist=persist)

    def _follow_bubble(self) -> None:
        if self.bubble.isVisible():
            self.bubble.reposition(self.mascot.anchor_rect())

    def _bring_to_front(self) -> None:
        self.mascot.show()
        self.mascot.raise_()
        self.mascot.activateWindow()

    def _get_scraper(self):
        with self._scraper_lock:
            if self._scraper is None:
                from .scraper import AzurLaneScraper  # nhập muộn: giảm RAM lúc khởi động

                self._scraper = AzurLaneScraper()
            return self._scraper

    def _update(self, **changes) -> None:
        """Cập nhật cấu hình, đồng bộ menu và ghi lại config.yaml."""
        self.cfg = self.cfg.with_(**changes)
        self.menu.sync(self.cfg)
        try:
            cfgmod.save(paths.config_path(), self.cfg)
        except OSError as exc:
            log.warning("Không ghi được config.yaml: %s", exc)
        self._reset_idle()  # đổi cài đặt cũng là một tương tác; đồng thời áp dụng khoảng rảnh mới

    # ================================================================ tải nhân vật
    def request_ship(self, name: str, skin_name: str = "") -> None:
        """Tải nhân vật ``name`` rồi mặc trang phục ``skin_name`` ("" / không tìm thấy = mặc định)."""
        name = name.strip()
        if not name:
            return
        self._reset_idle()
        self._ship_gen += 1
        gen = self._ship_gen
        self.say(tr("status.loading_ship", name=name), persist=True)
        self.dispatcher.submit(
            lambda: self._job_load_ship(name, skin_name),
            on_done=lambda res: self._on_ship_loaded(gen, res),
            on_error=lambda exc: self._on_ship_error(gen, exc),
        )

    def _job_load_ship(self, name: str, skin_name: str = "") -> tuple[ShipData, int, Path]:  # luồng nền
        ship = self.cache.find(name)
        if ship is not None and ship.skins and ship.version < SCHEMA_VERSION:
            # Cache cũ chưa có tên phụ của trang phục: tải lại dữ liệu (ảnh đã cache vẫn dùng được)
            try:
                fresh = self._get_scraper().fetch_ship(name)
                if fresh.skins:
                    self.cache.store(name, fresh)
                    ship = fresh
            except ScraperError as exc:
                log.info("Không làm mới được cache cũ của %s, dùng bản cũ: %r", name, exc)
        if ship is None or not ship.skins:
            ship = self._get_scraper().fetch_ship(name)
            if not ship.skins:
                raise NoImageError(ship.name)
            self.cache.store(name, ship)

        idx = self._find_skin(ship, skin_name)
        if idx is None:
            idx = 0
        try:
            return ship, idx, self._ensure_skin_file(ship, ship.skins[idx])
        except ScraperError as exc:
            if idx == 0:
                raise
            # Ảnh của trang phục đã lưu không tải được (mất mạng, cache bị xoá...): về mặc định
            log.info("Không nạp được trang phục %r, dùng trang phục đầu tiên: %r", skin_name, exc)
            return ship, 0, self._ensure_skin_file(ship, ship.skins[0])

    @staticmethod
    def _find_skin(ship: ShipData, skin_name: str) -> int | None:
        """Vị trí trang phục theo tên (so khớp chuẩn hoá; ưu tiên tên chính, sau đó tên phụ)."""
        target = norm(skin_name)
        if not target:
            return None
        for i, skin in enumerate(ship.skins):
            if norm(skin.name) == target:
                return i
        for i, skin in enumerate(ship.skins):
            if target in {norm(a) for a in skin.aliases}:
                return i
        return None

    def _ensure_skin_file(self, ship: ShipData, skin: Skin) -> Path:  # luồng nền
        """Đảm bảo ảnh đã thu nhỏ có trong cache (tải về + xử lý nếu chưa có)."""
        dest = self.cache.skin_path(ship, skin)
        if dest.exists():
            return dest
        raw = self.cache.raw_path(ship, skin)
        self._get_scraper().download(skin.image_url, raw)
        try:
            process_image(raw, dest)
        finally:
            raw.unlink(missing_ok=True)
        return dest

    def _on_ship_loaded(self, gen: int, result) -> None:
        if gen != self._ship_gen:
            return  # đã có yêu cầu mới hơn
        ship, idx, path = result
        self.ship = ship
        self.skin_index = self._target_idx = idx
        self._last_quote = None
        self._idle_idx = 0  # đổi nhân vật: vòng thoại khi rảnh bắt đầu lại từ Task
        self._click_streak = 0
        self._skin_groups = match_skins(ship.skins, quote_groups(ship.quotes))
        self._skin_labels = skin_labels(ship.skins, self._skin_groups)
        for skin, label, group in zip(ship.skins, self._skin_labels, self._skin_groups):
            log.info("Trang phục %r (%s) -> thoại riêng: %r", skin.name, label, group)
        self._display(path)
        self.menu.set_tooltip(ship.name)
        # Ghi lại tên chuẩn của tàu và trang phục thật sự đang hiển thị (một lần ghi file)
        changes: dict[str, str] = {}
        if self.cfg.ship_name != ship.name:
            changes["ship_name"] = ship.name
        if self.cfg.skin_name != ship.skins[idx].name:
            changes["skin_name"] = ship.skins[idx].name
        if changes:
            self._update(**changes)
        self._reset_idle()
        self._ensure_voices()  # tải nền toàn bộ giọng của trang phục này + trang phục mặc định (nếu chưa)

        greeting = self._pick_quote("greeting")
        if greeting:
            self.say_quote(greeting)
        else:
            self.say(tr("status.ship_ready", name=ship.name))

    def _on_ship_error(self, gen: int, exc: Exception) -> None:
        if gen != self._ship_gen:
            return
        if isinstance(exc, ShipNotFound):
            self.say(tr("status.ship_not_found"))
        elif isinstance(exc, AccessBlocked):
            self.say(tr("status.access_blocked"))
        elif isinstance(exc, NetworkError):
            self.say(tr("status.network_error"))
        elif isinstance(exc, NoImageError):
            self.say(tr("status.no_image", name=str(exc)))
        else:
            log.error("Lỗi khi tải nhân vật: %r", exc)
            self.say(tr("status.network_error"))

    # ================================================================ hiển thị ảnh
    def _display(self, path: Path) -> None:
        """Nạp MỘT ảnh (trang phục đang xem) lên cửa sổ; ảnh cũ bị giải phóng."""
        image = QImage(str(path))
        if image.isNull():
            self.say(tr("status.no_image", name=self.ship.name if self.ship else ""))
            return
        self._skin_path = path
        dpr = self.mascot.devicePixelRatioF()
        target_h = max(32, round(BASE_HEIGHT * self.cfg.scale * dpr))
        if image.height() != target_h:
            image = image.scaledToHeight(target_h, Qt.TransformationMode.SmoothTransformation)
        if self.cfg.flipped:
            image = image.mirrored(True, False)
        self.mascot.set_image(image, dpr)

    # ================================================================ trang phục
    def _skin_label(self, idx: int) -> str:
        if 0 <= idx < len(self._skin_labels):
            return self._skin_labels[idx]
        return self.ship.skins[idx].name if self.ship else ""

    def change_skin(self, delta: int) -> None:
        ship = self.ship
        if ship is None:
            return
        count = len(ship.skins)
        if count < 2:
            self.say(tr("status.single_skin"))
            return
        self._show_skin((self._target_idx + delta) % count)

    def _show_skin(self, idx: int) -> None:
        """Chuyển tới trang phục ``idx``: dùng ảnh cache nếu có, không thì tải nền rồi mới đổi."""
        ship = self.ship
        if ship is None or not 0 <= idx < len(ship.skins):
            return
        self._reset_idle()
        self._target_idx = idx
        skin = ship.skins[idx]

        cached = self.cache.skin_path(ship, skin)
        if cached.exists():
            self._apply_skin(idx, cached)
            return

        self._skin_req += 1
        req, gen = self._skin_req, self._ship_gen
        self.say(tr("status.loading_skin", name=self._skin_label(idx)), persist=True)
        self.dispatcher.submit(
            lambda: self._ensure_skin_file(ship, skin),
            on_done=lambda path: self._on_skin_ready(gen, req, idx, path),
            on_error=lambda exc: self._on_skin_error(gen, req, exc),
        )

    def _on_skin_ready(self, gen: int, req: int, idx: int, path: Path) -> None:
        if gen != self._ship_gen or req != self._skin_req:
            return
        self._apply_skin(idx, path)

    def _on_skin_error(self, gen: int, req: int, exc: Exception) -> None:
        if gen != self._ship_gen or req != self._skin_req:
            return
        self._target_idx = self.skin_index
        if isinstance(exc, AccessBlocked):
            self.say(tr("status.access_blocked"))
        elif isinstance(exc, NetworkError):
            self.say(tr("status.network_error"))
        else:
            self.say(tr("status.no_image", name=""))

    def _apply_skin(self, idx: int, path: Path) -> None:
        if self.ship is None:
            return
        self.skin_index = self._target_idx = idx
        self._display(path)
        self._persist_skin()
        self._ensure_voices()  # lần đầu vào trang phục này -> tải nền cả bộ thoại; từng tải rồi -> bỏ qua
        self.say(tr("status.skin_changed", name=self._skin_label(idx)))
        if self.cfg.skin_voice:
            # Đổi trang phục liên tiếp: chỉ trang phục cuối cùng được phát thoại (token chống thoại cũ)
            self._skin_voice_token += 1
            token = self._skin_voice_token
            QTimer.singleShot(SKIN_VOICE_DELAY_MS, lambda: self._speak_for_skin(token))

    def _persist_skin(self) -> None:
        """Ghi tên trang phục đang mặc vào config.yaml (bỏ qua nếu không đổi)."""
        ship = self.ship
        if ship is None or not 0 <= self.skin_index < len(ship.skins):
            return
        if norm(self.cfg.ship_name) != norm(ship.name):
            return  # config đang trỏ sang tàu khác (đang tải): không ghi nhầm trang phục của tàu cũ
        name = ship.skins[self.skin_index].name
        if name != self.cfg.skin_name:
            self._update(skin_name=name)

    def _speak_for_skin(self, token: int) -> None:
        if self._quitting or token != self._skin_voice_token or self.ship is None:
            return
        quote = self._pick_quote("skin")
        if quote is not None:
            self.say_quote(quote)

    # ================================================================ câu thoại
    def on_click(self) -> None:
        """Nhấp chuột trái. Đủ LOVE_CLICKS lần liên tiếp (mỗi lần cách nhau <= LOVE_CLICK_GAP) -> Love."""
        self._reset_idle()
        now = time.monotonic()
        if now - self._last_click > LOVE_CLICK_GAP:
            self._click_streak = 0  # nghỉ quá lâu: chuỗi nhấp bị ngắt
        self._last_click = now
        self._click_streak += 1

        if self._click_streak >= LOVE_CLICKS:
            self._click_streak = 0
            # say_quote() ngắt tiếng nhấp trước đó (và loại luôn câu đang tải dở) nên giọng Love
            # luôn phát trọn vẹn, không chồng lên tiếng nhấp thường.
            if self.play_voice_category(VOICE_LOVE):
                return
            # Cả trang phục lẫn bản mặc định đều không có thoại Love: nhấp này xử lý như nhấp thường

        quote = self._pick_quote("touch")
        if quote is None:
            self.say(tr("status.no_quotes"))
            return
        self.say_quote(quote)

    def on_long_press(self) -> None:
        """Nhấn giữ chuột trái >= 1.5 s -> thoại Pledge của trang phục MẶC ĐỊNH (bất kể đang mặc bộ nào)."""
        self._reset_idle()
        self._click_streak = 0  # nhấn giữ ngắt chuỗi nhấp; lần nhả chuột sau đó cũng không tính là nhấp
        if not self.play_voice_category(VOICE_PLEDGE, force_default=True):
            self.say(tr("status.no_quotes"))

    def _group_quotes(self, group: str | None) -> list[Quote]:
        if self.ship is None or group is None:
            return []
        return [q for q in self.ship.quotes if q.skin == group]

    def _quotes_for_current_skin(self) -> list[Quote]:
        """Câu thoại RIÊNG của trang phục đang mặc (rỗng nếu trang phục này không có mục thoại riêng)."""
        if self.ship is None or self.skin_index >= len(self._skin_groups):
            return []
        return self._group_quotes(self._skin_groups[self.skin_index])

    def _default_quotes(self) -> list[Quote]:
        if self.ship is None:
            return []
        for skin, group in zip(self.ship.skins, self._skin_groups):
            if is_default(skin.name):
                return self._group_quotes(group)
        return []

    @staticmethod
    def _filter(quotes: list[Quote], kind: str) -> list[Quote]:
        patterns = _EVENT_PATTERNS[kind]
        if kind in _PRIORITY_KINDS:
            for pattern in patterns:
                hits = [q for q in quotes if _matches(q.event, pattern)]
                if hits:
                    return hits
            return []
        return [q for q in quotes if any(_matches(q.event, p) for p in patterns)]

    def _pick_quote(self, kind: str) -> Quote | None:
        """Chọn câu thoại theo ngữ cảnh, ưu tiên thoại riêng của trang phục đang mặc.

        - Trang phục có thoại riêng: chỉ dùng thoại của nó (không trộn với trang phục mặc định);
          thiếu loại thoại cần thiết thì lùi về thoại chạm của chính nó.
        - Trang phục không có mục thoại riêng: dùng thoại của trang phục mặc định
          (riêng khi đổi trang phục thì im lặng, vì đó không phải giọng của bộ đồ này).
        """
        if self.ship is None:
            return None
        own = self._quotes_for_current_skin()
        if own:
            pool = self._filter(own, kind)
            if not pool and kind in _PRIORITY_KINDS:
                pool = self._filter(own, "touch")
            if not pool and kind != "skin":
                pool = self._filter(self._default_quotes(), kind)
        elif kind == "skin":
            return None
        else:
            pool = self._filter(self._default_quotes(), kind)
        if not pool:
            return None
        candidates = [q for q in pool if q != self._last_quote] or pool
        return random.choice(candidates)

    def play_voice_category(
        self,
        category_names: Iterable[str],
        fallback_to_default: bool = True,
        force_default: bool = False,
    ) -> bool:
        """Phát một câu thoại thuộc mục ``category_names`` (hiện bong bóng + giọng nói).

        - ``category_names``: các tên mục chấp nhận được, ví dụ ``("Start mission", "Starting mission")``.
          So khớp không phân biệt hoa/thường và dấu câu, cộng khớp theo từ khoá chuẩn
          (xem ``models.voice_matches``).
        - ``force_default=True``: bỏ qua trang phục hiện tại, chỉ lấy thoại của trang phục MẶC ĐỊNH.
        - ``fallback_to_default=True``: trang phục hiện tại không có mục đó (hoặc mục đó không có file
          âm thanh) thì lấy của trang phục mặc định.

        Trả về True nếu đã phát / hiện được một câu; False nếu không tìm thấy gì (người gọi tự xử lý).
        """
        quote = self._pick_voice(tuple(category_names), fallback_to_default, force_default)
        if quote is None:
            return False
        self.say_quote(quote)
        return True

    def _pick_voice(self, names: tuple[str, ...], fallback_to_default: bool, force_default: bool) -> Quote | None:
        if self.ship is None or not names:
            return None
        default_hits = [q for q in self._default_quotes() if voice_matches(q.event, names)]
        if force_default:
            tiers = [default_hits]
        else:
            own_hits = [q for q in self._quotes_for_current_skin() if voice_matches(q.event, names)]
            tiers = [own_hits, default_hits] if fallback_to_default else [own_hits]
        if self.cfg.audio_volume > 0:
            # Ưu tiên câu CÓ file giọng: thoại của trang phục này -> của bản mặc định; chỉ khi không
            # đâu có giọng mới chịu hiện chữ không tiếng (thứ tự cũng theo trang phục -> mặc định)
            pools = [[q for q in tier if q.audio_url] for tier in tiers] + tiers
        else:
            pools = tiers  # đang tắt tiếng: có file giọng hay không không còn quan trọng
        for pool in pools:
            if pool:
                candidates = [q for q in pool if q != self._last_quote] or pool
                return random.choice(candidates)
        return None

    def say_quote(self, quote: Quote) -> None:
        """Hiện bong bóng thoại (giữ nguyên lời gốc) và phát giọng nói nếu bật."""
        self._last_quote = quote
        self.say(quote.text)

        self._voice_token += 1
        token = self._voice_token
        self.player.stop()
        ship, url, volume = self.ship, quote.audio_url, self.cfg.audio_volume
        if ship is None or not url or volume <= 0:
            return

        def job() -> None:  # luồng nền: tải (nếu chưa có) rồi phát
            path = self.cache.audio_path(ship, url)
            if not path.exists() or path.stat().st_size == 0:
                self._get_scraper().download(url, path)
            if token == self._voice_token:  # chưa có câu thoại mới hơn
                self.player.play(path, volume, still_current=lambda: token == self._voice_token)

        self.dispatcher.submit(job)

    # ================================================================ điều khiển
    def _on_action(self, action: str) -> None:
        self._reset_idle()
        if action == "next_skin":
            self.change_skin(+1)
        elif action == "prev_skin":
            self.change_skin(-1)
        elif action == "toggle_top":
            self.set_always_on_top(not self.cfg.always_on_top)
        elif action == "toggle_flip":
            self.set_flipped(not self.cfg.flipped)
        elif action == "toggle_float":
            self.set_floating(not self.cfg.floating)

    def set_always_on_top(self, on: bool, notify: bool = True) -> None:
        self._update(always_on_top=on)
        apply_topmost(self.mascot, on)
        apply_topmost(self.bubble, on)
        if notify:
            self.say(tr("status.on_top_on" if on else "status.on_top_off"))

    def set_floating(self, on: bool, notify: bool = True) -> None:
        self._update(floating=on)
        self.mascot.set_floating(on)  # tắt hẳn timer khi không dùng
        if notify:
            self.say(tr("status.floating_on" if on else "status.floating_off"))

    def set_flipped(self, on: bool, notify: bool = True) -> None:
        self._update(flipped=on)
        if self._skin_path is not None:
            self._display(self._skin_path)
        if notify:
            self.say(tr("status.flip_on" if on else "status.flip_off"))

    def set_opacity(self, value: float, notify: bool = True) -> None:
        value = round(min(cfgmod.OPACITY_MAX, max(cfgmod.OPACITY_MIN, float(value))), 2)
        self._update(opacity=value)  # ghi config.yaml ngay
        self.mascot.set_opacity(value)
        if notify:
            self.say(tr("status.opacity_changed", percent=round(value * 100)))

    def set_hover_mode(self, on: bool, notify: bool = True) -> None:
        """Hover Mode: chuột xuyên qua nhân vật. Chỉ bật khi còn đường tắt lại (phím tắt hoặc khay)."""
        if on and not (self.hotkey.registered or self.menu.tray is not None):
            self.menu.set_hover(False)  # trả dấu tích về TẮT
            self.say(tr("status.hover_unavailable", hotkey=self.cfg.hover_hotkey))
            return
        self._hover = on
        self.mascot.set_hover_mode(on)
        self.menu.set_hover(on)
        self._reset_idle()
        if not notify:
            return
        # Bật -> "Start mission"; tắt -> "Return from mission" (thiếu ở trang phục này thì lấy của bản mặc định)
        if self.play_voice_category(VOICE_START_MISSION if on else VOICE_RETURN_MISSION):
            return
        if not on:
            self.say(tr("status.hover_off"))
        elif self.hotkey.registered:
            self.say(tr("status.hover_on", hotkey=self.cfg.hover_hotkey))
        else:
            self.say(tr("status.hover_on_tray"))

    def _on_hotkey(self) -> None:
        self.set_hover_mode(not self._hover)

    def _register_hotkey(self) -> None:
        """(Đăng ký lại) phím tắt Hover Mode theo config; lỗi thì báo bằng thông báo khay."""
        if not self.hotkey.supported():
            return  # chạy thử trên hệ điều hành khác: vẫn bật/tắt được qua menu
        if self.hotkey.register(self.cfg.hover_hotkey):
            return
        text = tr("status.hotkey_failed", hotkey=self.cfg.hover_hotkey)
        if not self.menu.show_message(text):
            self.say(text)
        if self._hover and self.menu.tray is None:
            self.set_hover_mode(False)  # đang bật mà mất cả đường tắt -> tắt luôn để khỏi bị khóa

    # ================================================================ thoại khi rảnh
    def _reset_idle(self) -> None:
        """Đếm lại từ 0 khoảng không tương tác (mọi thao tác của người dùng đều gọi hàm này)."""
        if self._quitting:
            return
        seconds = self.cfg.idle_voice_interval
        if seconds <= 0:
            self._idle_timer.stop()
        else:
            self._idle_timer.start(seconds * 1000)  # start() khi đang chạy = khởi động lại từ đầu

    def _on_idle(self) -> None:
        """Hết khoảng rảnh: phát một mục trong vòng Task -> Mail -> Commission rồi hẹn lần sau."""
        if self._quitting:
            return
        if self.ship is not None and not self._dialog_open and not self.mascot.is_pressed():
            count = len(_IDLE_CYCLE)
            for step in range(count):  # mục nào cả hai bản đều thiếu thì bỏ qua, thử mục kế tiếp
                idx = (self._idle_idx + step) % count
                if self.play_voice_category(_IDLE_CYCLE[idx]):
                    self._idle_idx = (idx + 1) % count
                    break
        self._reset_idle()

    def set_idle_interval(self, seconds: int, notify: bool = True) -> None:
        seconds = 0 if seconds <= 0 else min(cfgmod.IDLE_VOICE_MAX, max(cfgmod.IDLE_VOICE_MIN, int(seconds)))
        self._update(idle_voice_interval=seconds)  # ghi config.yaml + khởi động lại bộ đếm
        self._refresh_help()
        if notify:
            if seconds == 0:
                self.say(tr("status.idle_off"))
            else:
                self.say(tr("status.idle_changed", time=locales.format_duration(seconds)))

    # ================================================================ tải trước giọng nói
    def _wanted_voice_groups(self) -> list[str]:
        """Các nhóm thoại cần có sẵn: của trang phục đang mặc (ưu tiên) rồi tới của bản mặc định."""
        ship = self.ship
        if ship is None:
            return []
        groups: list[str] = []
        if 0 <= self.skin_index < len(self._skin_groups) and self._skin_groups[self.skin_index]:
            groups.append(self._skin_groups[self.skin_index])  # type: ignore[arg-type]
        for skin, group in zip(ship.skins, self._skin_groups):
            if is_default(skin.name):
                if group and group not in groups:
                    groups.append(group)
                break
        return groups

    def _ensure_voices(self) -> None:
        """Bảo đảm bộ thoại của trang phục đang mặc và của bản mặc định đã (hoặc đang được) tải nền.

        Nhóm đã có dấu mốc "tải trọn bộ" thì tác vụ nền thoát ngay mà không đụng tới mạng. Mỗi nhóm chỉ
        có tối đa một tác vụ (key) - đổi trang phục liên tục không đẻ ra nhiều luồng tải trùng nhau.
        """
        ship = self.ship
        if ship is None or self._quitting or self.cfg.audio_volume <= 0:
            return  # tắt tiếng (audio_volume = 0) thì không tải file âm thanh nào
        groups = self._wanted_voice_groups()
        # Cập nhật "cái gì còn cần": tác vụ của trang phục mà người dùng đã bỏ đi sẽ tự dừng
        self._wanted_voices = frozenset((ship.wiki_title, g) for g in groups)
        for group in groups:
            urls = [q.audio_url for q in self._group_quotes(group) if q.audio_url]
            self.voice_dispatcher.submit(
                lambda g=group, u=urls: self._job_preload_voices(ship, g, u),
                on_done=lambda res, g=group: self._on_voices_preloaded(ship, g, res),
                on_error=lambda exc, g=group: log.info("Tải trước giọng nói %s/%s lỗi: %r", ship.name, g, exc),
                key=f"voices:{ship.wiki_title}:{group}",
            )

    def _job_preload_voices(self, ship: ShipData, group: str, urls: list[str]) -> PreloadResult:  # luồng nền
        wanted = (ship.wiki_title, group)

        def keep_going() -> bool:
            return not self._closing.is_set() and wanted in self._wanted_voices

        # Chỉ dựng bộ thu thập (nhập httpx / bs4) khi thật sự cần ra mạng
        need_network = bool(urls) and not self.cache.voices_preloaded(ship, group, urls) and any(
            not self.cache.audio_ready(ship, u) for u in urls
        )
        scraper = self._get_scraper() if need_network else None
        return self.cache.preload_voices(ship, group, urls, scraper, keep_going)

    def _on_voices_preloaded(self, ship: ShipData, group: str, result: object) -> None:
        if self._quitting or not isinstance(result, PreloadResult):
            return
        # Tác vụ vừa bị dừng vì lúc đó nhóm này không còn cần, nhưng giờ người dùng đã quay lại -> làm tiếp
        if result.stopped and self.ship is ship and (ship.wiki_title, group) in self._wanted_voices:
            self._ensure_voices()

    # ================================================================ trợ giúp
    def show_help(self) -> None:
        """Mở cửa sổ Trợ giúp (chỉ một cửa sổ duy nhất; bấm lại thì đưa nó lên trước)."""
        self._reset_idle()
        if self._help is None:
            self._help = HelpDialog(self.icon)
        self._help.refresh(self.cfg.hover_hotkey, self.cfg.idle_voice_interval, LOVE_CLICK_GAP)
        self._help.show_front()

    def _refresh_help(self) -> None:
        """Cửa sổ Trợ giúp đang mở: dựng lại chữ khi đổi ngôn ngữ / phím tắt / khoảng rảnh."""
        if self._help is not None and self._help.isVisible():
            self._help.refresh(self.cfg.hover_hotkey, self.cfg.idle_voice_interval, LOVE_CLICK_GAP)

    def set_language(self, lang: str, notify: bool = True) -> None:
        locales.set_language(lang)
        self._update(language=locales.get_language())
        self.menu.retranslate(self.ship.name if self.ship else "")
        self._refresh_help()
        if notify:
            self.say(tr("status.language_changed"))

    def choose_ship_dialog(self) -> None:
        if self._dialog_open:
            return
        self._dialog_open = True
        self._reset_idle()
        try:
            dialog = QInputDialog()
            dialog.setWindowTitle(tr("dialog.title"))
            dialog.setLabelText(tr("dialog.label"))
            dialog.setInputMode(QInputDialog.InputMode.TextInput)
            dialog.setTextValue(self.ship.name if self.ship else self.cfg.ship_name)
            dialog.setOkButtonText(tr("dialog.ok"))
            dialog.setCancelButtonText(tr("dialog.cancel"))
            dialog.setWindowIcon(self.icon)
            dialog.setMinimumWidth(440)
            dialog.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
            if dialog.exec():
                name = dialog.textValue().strip()
                if name:
                    self.request_ship(name)
        finally:
            self._dialog_open = False
            self._reset_idle()

    def open_data_folder(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(paths.app_dir())))

    # ================================================================ config.yaml tự áp dụng
    def _watch_config(self) -> None:
        path = paths.config_path()
        if path.exists() and str(path) not in self._watcher.files():
            self._watcher.addPath(str(path))
        folder = str(path.parent)
        if folder not in self._watcher.directories():
            self._watcher.addPath(folder)

    def _reload_config(self) -> None:
        if self._quitting:  # lần ghi config cuối cùng của quit() có thể đánh thức watcher: bỏ qua
            return
        path = paths.config_path()
        if not path.exists():  # đang được trình soạn thảo ghi lại
            return
        self._watch_config()
        new = cfgmod.load(path)
        if new == self.cfg:
            return  # chính chương trình vừa ghi, hoặc không đổi gì
        old, self.cfg = self.cfg, new

        locales.set_language(new.language)
        self.menu.retranslate(self.ship.name if self.ship else "")
        self.menu.sync(new)

        if old.always_on_top != new.always_on_top:
            apply_topmost(self.mascot, new.always_on_top)
            apply_topmost(self.bubble, new.always_on_top)
        if old.floating != new.floating:
            self.mascot.set_floating(new.floating)
        if (old.scale != new.scale or old.flipped != new.flipped) and self._skin_path is not None:
            self._display(self._skin_path)
        if old.opacity != new.opacity:
            self.mascot.set_opacity(new.opacity)
        if old.hover_hotkey != new.hover_hotkey:
            self._register_hotkey()
        if old.audio_volume <= 0 < new.audio_volume:
            self._ensure_voices()  # vừa bật tiếng lại: bù phần giọng nói chưa tải
        self._refresh_help()
        self._reset_idle()  # sửa config cũng là tương tác; đồng thời áp dụng idle_voice_interval mới

        current = norm(self.ship.name) if self.ship else ""
        if norm(new.ship_name) != norm(old.ship_name) and norm(new.ship_name) != current:
            self.request_ship(new.ship_name, new.skin_name)  # sẽ hiện "Đang tải dữ liệu của ..."
        elif new.skin_name != old.skin_name and self._select_skin_named(new.skin_name):
            pass  # đã hiện "Đã đổi sang trang phục: ..."
        else:
            self.say(tr("status.config_reloaded"))

    def _select_skin_named(self, skin_name: str) -> bool:
        """Đổi sang trang phục theo tên người dùng vừa sửa trong config; False nếu không có gì để đổi."""
        idx = self._find_skin(self.ship, skin_name) if self.ship else None
        if idx is None or idx == self._target_idx:
            return False
        self._show_skin(idx)
        return True
