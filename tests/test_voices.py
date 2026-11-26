"""Kiểm thử phần thoại: nhận diện tên mục, tải trước trọn bộ + dấu mốc trong cache (không cần mạng/Qt).

Chạy:  python -m tests.test_voices      hoặc      pytest
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from src.cache import PreloadResult, ShipCache
from src.errors import AccessBlocked, NetworkError, ScraperError
from src.models import (
    VOICE_COMMISSION,
    VOICE_LOVE,
    VOICE_MAIL,
    VOICE_PLEDGE,
    VOICE_RETURN_MISSION,
    VOICE_START_MISSION,
    VOICE_TASK,
    ShipData,
    voice_category,
    voice_matches,
)


# ---------------------------------------------------------------- nhận diện tên mục
def test_voice_category_names():
    expected = {
        "Start mission": "start_mission", "Starting Mission": "start_mission", "Mission Start": "start_mission",
        "Return From Mission": "return_mission", "Return from mission": "return_mission",
        "Task": "task", "Task Reminder": "task", "Mission Reminder": "task",
        "Mail": "mail", "Mail Reminder": "mail",
        "Commission": "commission", "Commission Complete": "commission",
        "Affinity (Love)": "affinity_love", "Pledge": "pledge",
        # Những mục KHÔNG được nhầm vào nhóm nào
        "Task Complete": None, "Mission Complete": None, "Affinity (Crush)": None,
        "Affinity (Friendly)": None, "Secretary (Touch)": None, "Login": None, "": None,
        # "commission" chứa chữ "mission" nhưng không phải bắt đầu / kết thúc nhiệm vụ
        "Return From Commission": "commission",
    }
    for event, category in expected.items():
        assert voice_category(event) == category, (event, voice_category(event), category)


def test_voice_matches_case_and_keywords():
    assert voice_matches("starting MISSION", VOICE_START_MISSION)  # không phân biệt hoa/thường
    assert voice_matches("Mission Start", VOICE_START_MISSION)  # khớp từ khoá chuẩn
    assert voice_matches("affinity love", VOICE_LOVE)  # bỏ qua dấu câu
    assert voice_matches("Return from mission", VOICE_RETURN_MISSION)
    assert voice_matches("Mail Reminder", VOICE_MAIL) and voice_matches("Commission Complete", VOICE_COMMISSION)
    assert voice_matches("Pledge", VOICE_PLEDGE) and voice_matches("Task", VOICE_TASK)
    # Phải phân biệt được các mục gần giống nhau
    assert not voice_matches("Task Complete", VOICE_TASK)
    assert not voice_matches("Affinity (Crush)", VOICE_LOVE)
    assert not voice_matches("Starting Mission", VOICE_RETURN_MISSION)
    assert not voice_matches("Return From Commission", VOICE_RETURN_MISSION)
    assert not voice_matches("", VOICE_TASK) and not voice_matches("Task", [])


# ---------------------------------------------------------------- tải trước giọng nói
class FakeScraper:
    """Giả lập AzurLaneScraper: ghi lại các yêu cầu, có thể cài sẵn lỗi cho từng URL."""

    def __init__(self, missing=(), errors=None, resolve_error=None):
        self.missing, self.errors = set(missing), dict(errors or {})
        self.resolve_error = resolve_error
        self.resolve_calls: list[list[str]] = []
        self.downloads: list[str] = []

    def resolve_audio_urls(self, urls):
        self.resolve_calls.append(list(urls))
        if self.resolve_error:
            raise self.resolve_error
        return {u: "https://real/" + u.split(":", 1)[-1] for u in urls if u not in self.missing}

    def download(self, url, dest):
        key = "wikifile:" + url.removeprefix("https://real/")
        if key in self.errors:
            raise self.errors[key]
        self.downloads.append(key)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"ogg")


def _setup(tmp: str):
    cache = ShipCache(Path(tmp) / "cache")
    ship = ShipData(name="Nagato", wiki_title="Nagato")
    urls = [f"wikifile:Nagato_{i}.ogg" for i in range(5)]
    return cache, ship, urls


def test_preload_downloads_all_then_skips_forever():
    with tempfile.TemporaryDirectory() as tmp:
        cache, ship, urls = _setup(tmp)
        scraper = FakeScraper()
        res = cache.preload_voices(ship, "Default Skin", urls, scraper, pause=0)
        assert (res.total, res.downloaded, res.complete) == (5, 5, True)
        assert all(cache.audio_ready(ship, u) for u in urls)
        assert len(scraper.resolve_calls) == 1 and len(scraper.resolve_calls[0]) == 5  # tra URL một lượt

        # Lần sau (đổi lại trang phục...): có dấu mốc -> không đụng tới mạng, kể cả khi không có scraper
        res2 = cache.preload_voices(ship, "Default Skin", urls, None, pause=0)
        assert res2.complete and res2.cached == 5 and res2.downloaded == 0
        assert cache.voices_preloaded(ship, "default skin", urls)  # khoá nhóm không phân biệt hoa/thường


def test_preload_marker_is_per_group_and_tracks_new_files():
    with tempfile.TemporaryDirectory() as tmp:
        cache, ship, urls = _setup(tmp)
        cache.preload_voices(ship, "Default Skin", urls, FakeScraper(), pause=0)
        assert not cache.voices_preloaded(ship, "Wedding", urls)  # nhóm khác chưa từng tải

        # Wiki thêm một câu thoại mới -> chữ ký đổi -> chỉ tải phần còn thiếu
        more = urls + ["wikifile:Nagato_new.ogg"]
        assert not cache.voices_preloaded(ship, "Default Skin", more)
        scraper = FakeScraper()
        res = cache.preload_voices(ship, "Default Skin", more, scraper, pause=0)
        assert scraper.downloads == ["wikifile:Nagato_new.ogg"] and res.cached == 5 and res.complete


def test_preload_group_without_audio_is_marked_done_without_network():
    with tempfile.TemporaryDirectory() as tmp:
        cache, ship, _ = _setup(tmp)
        res = cache.preload_voices(ship, "Hot Springs", [], None, pause=0)  # scraper=None: không được dùng tới
        assert res.complete and res.total == 0
        assert cache.voices_preloaded(ship, "Hot Springs", [])


def test_preload_stops_without_marker_when_no_longer_wanted():
    with tempfile.TemporaryDirectory() as tmp:
        cache, ship, urls = _setup(tmp)
        scraper = FakeScraper()
        seen = []

        def keep_going():  # cho phép tải đúng 2 file rồi "người dùng đổi trang phục"
            seen.append(1)
            return len(scraper.downloads) < 2

        res = cache.preload_voices(ship, "Default Skin", urls, scraper, keep_going, pause=0)
        assert res.stopped and not res.complete and len(scraper.downloads) == 2
        assert not cache.voices_preloaded(ship, "Default Skin", urls)

        # Quay lại sau: tiếp tục phần còn thiếu (không tải lại 2 file đã có)
        scraper2 = FakeScraper()
        res2 = cache.preload_voices(ship, "Default Skin", urls, scraper2, pause=0)
        assert len(scraper2.downloads) == 3 and res2.complete and res2.cached == 2


def test_preload_network_failures_do_not_mark_done():
    with tempfile.TemporaryDirectory() as tmp:
        cache, ship, urls = _setup(tmp)
        # Chặn ngay lúc tra URL (403)
        res = cache.preload_voices(ship, "G", urls, FakeScraper(resolve_error=AccessBlocked("403")), pause=0)
        assert res.network_error and not res.complete
        # 3 lỗi mạng liên tiếp -> bỏ cuộc, không gõ cửa tiếp
        errors = {u: NetworkError("down") for u in urls}
        scraper = FakeScraper(errors=errors)
        res = cache.preload_voices(ship, "G", urls, scraper, pause=0)
        assert res.network_error and res.failed == 3 and not res.complete
        assert not cache.voices_preloaded(ship, "G", urls)


def test_preload_isolated_failures_and_missing_files_still_complete():
    with tempfile.TemporaryDirectory() as tmp:
        cache, ship, urls = _setup(tmp)
        scraper = FakeScraper(missing={urls[0]}, errors={urls[1]: ScraperError("quá lớn")})
        res = cache.preload_voices(ship, "G", urls, scraper, pause=0)
        # 1 file Wiki không có, 1 file lỗi riêng: không chặn dấu mốc (phát tới đâu tải theo yêu cầu tới đó)
        assert (res.missing, res.failed, res.downloaded, res.complete) == (1, 1, 3, True)
        assert cache.voices_preloaded(ship, "G", urls)


def test_preload_result_defaults():
    r = PreloadResult()
    assert not (r.complete or r.stopped or r.network_error)


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("OK  ", name)
    print("Tất cả kiểm thử thoại đã qua.")
