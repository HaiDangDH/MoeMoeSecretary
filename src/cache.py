"""Quản lý cache trên ổ cứng (``./cache/``) - mỗi nhân vật chỉ tải từ mạng một lần.

Cấu trúc::

    cache/
      index.json                  # tên người dùng gõ -> tiêu đề trang Wiki
      <Ship>/ship.json            # trang phục + câu thoại (UTF-8)
      <Ship>/skin_<hash>.png      # ảnh đã cắt viền trong suốt + thu nhỏ (<= 800 px cao)
      <Ship>/audio/<hash>.ogg     # giọng nói đã tải
      <Ship>/audio/voices_<hash>.json   # dấu mốc "bộ thoại này đã được tải trọn bộ" (xem preload_voices)

Ảnh gốc trên Wiki thường rất lớn (2000x2000+). Ảnh được thu nhỏ bằng Pillow
TRƯỚC khi lưu cache nên không bao giờ nạp ảnh khổng lồ lên giao diện/RAM.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

from .errors import AccessBlocked, NetworkError, ScraperError
from .models import ShipData, Skin, norm

log = logging.getLogger(__name__)

CACHE_MAX_HEIGHT = 800  # px - mục tiêu 600-800 px theo yêu cầu
ALPHA_CUTOFF = 10  # điểm ảnh gần như trong suốt -> trong suốt hẳn (để bấm xuyên qua)


def _slug(text: str) -> str:
    return re.sub(r"[^\w\-.]+", "_", text, flags=re.UNICODE).strip("_") or "ship"


def _short_hash(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:14]


def process_image(src: Path, dest: Path, max_height: int = CACHE_MAX_HEIGHT) -> None:
    """Cắt viền trong suốt, thu nhỏ cho vừa ``max_height`` rồi lưu PNG."""
    from PIL import Image  # nhập muộn: giảm thời gian khởi động

    with Image.open(src) as im:
        im = im.convert("RGBA")
        alpha = im.getchannel("A").point([0] * ALPHA_CUTOFF + list(range(ALPHA_CUTOFF, 256)))
        im.putalpha(alpha)
        bbox = alpha.getbbox()
        if bbox:
            im = im.crop(bbox)
        if im.height > max_height:
            width = max(1, round(im.width * max_height / im.height))
            im = im.resize((width, max_height), Image.Resampling.LANCZOS)
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(".tmp")
        im.save(tmp, format="PNG", compress_level=6)
    tmp.replace(dest)


@dataclass
class PreloadResult:
    """Kết quả một lần tải trước trọn bộ giọng nói."""

    total: int = 0
    downloaded: int = 0  # vừa tải mới
    cached: int = 0  # đã có sẵn trên ổ cứng
    missing: int = 0  # Wiki không có file này (không thể tải)
    failed: int = 0  # lỗi riêng của từng file
    complete: bool = False  # đã ghi dấu mốc -> lần sau bỏ qua hoàn toàn
    stopped: bool = False  # dừng giữa chừng vì không còn cần (đổi trang phục / thoát)
    network_error: bool = False  # mất mạng / bị chặn: chưa ghi dấu mốc, sẽ thử lại lần sau


class ShipCache:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self._index_path = root / "index.json"

    # -- index ---------------------------------------------------------
    def _read_index(self) -> dict[str, str]:
        try:
            return json.loads(self._index_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _write_index(self, index: dict[str, str]) -> None:
        self._index_path.write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")

    # -- ship.json -----------------------------------------------------
    def ship_dir(self, wiki_title: str) -> Path:
        return self.root / _slug(wiki_title)

    def find(self, query: str) -> ShipData | None:
        """Tìm trong cache theo tên người dùng gõ (không cần mạng)."""
        title = self._read_index().get(norm(query))
        if not title:
            return None
        path = self.ship_dir(title) / "ship.json"
        try:
            return ShipData.from_json(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError, KeyError, TypeError) as exc:
            log.warning("Cache hỏng (%s): %s", path, exc)
            return None

    def store(self, query: str, ship: ShipData) -> None:
        folder = self.ship_dir(ship.wiki_title)
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "ship.json").write_text(
            json.dumps(ship.to_json(), ensure_ascii=False, indent=1), encoding="utf-8"
        )
        index = self._read_index()
        for key in (query, ship.name, ship.wiki_title, ship.wiki_title.replace("_", " ")):
            index[norm(key)] = ship.wiki_title
        self._write_index(index)

    # -- ảnh / âm thanh ------------------------------------------------
    def skin_path(self, ship: ShipData, skin: Skin) -> Path:
        return self.ship_dir(ship.wiki_title) / f"skin_{_short_hash(skin.image_url)}.png"

    def raw_path(self, ship: ShipData, skin: Skin) -> Path:
        return self.skin_path(ship, skin).with_suffix(".raw")

    def audio_path(self, ship: ShipData, url: str) -> Path:
        ext = Path(url.split("?")[0]).suffix.lower() or ".ogg"
        if len(ext) > 6:
            ext = ".ogg"
        return self.ship_dir(ship.wiki_title) / "audio" / f"{_short_hash(url)}{ext}"

    # -- tải trước trọn bộ giọng nói ----------------------------------------
    def audio_ready(self, ship: ShipData, url: str) -> bool:
        try:
            return self.audio_path(ship, url).stat().st_size > 0
        except OSError:
            return False

    def _voice_marker(self, ship: ShipData, group: str) -> Path:
        # Khoá theo NHÓM THOẠI (không phải ảnh trang phục): nhiều trang phục có thể dùng chung một nhóm
        return self.ship_dir(ship.wiki_title) / "audio" / f"voices_{_short_hash(norm(group))}.json"

    @staticmethod
    def voice_signature(urls: Iterable[str]) -> str:
        return _short_hash("\n".join(sorted({u for u in urls if u})))

    def voices_preloaded(self, ship: ShipData, group: str, urls: Iterable[str]) -> bool:
        """Bộ thoại này đã từng được tải trọn bộ (và Wiki chưa thêm / đổi file nào kể từ đó)?"""
        urls = list(urls)
        try:
            data = json.loads(self._voice_marker(ship, group).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return False
        return isinstance(data, dict) and data.get("signature") == self.voice_signature(urls)

    def _mark_voices_preloaded(self, ship: ShipData, group: str, urls: list[str], result: PreloadResult) -> None:
        marker = self._voice_marker(ship, group)
        marker.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "group": group,
            "signature": self.voice_signature(urls),
            "total": result.total,
            "downloaded": result.downloaded,
            "missing": result.missing,
            "failed": result.failed,
            "time": int(time.time()),
        }
        tmp = marker.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(marker)  # ghi nguyên tử: không bao giờ để lại dấu mốc dở dang

    def preload_voices(
        self,
        ship: ShipData,
        group: str,
        urls: Iterable[str],
        scraper,
        should_continue: Callable[[], bool] = lambda: True,
        pause: float = 0.12,
    ) -> PreloadResult:
        """Tải toàn bộ file âm thanh của một nhóm thoại vào cache (chạy ở luồng nền).

        - Đã có dấu mốc khớp chữ ký danh sách URL -> bỏ qua hoàn toàn, không đụng tới mạng.
        - File đã có trên ổ cứng không tải lại; Wiki được hỏi URL thật theo lô (ít yêu cầu API).
        - Chỉ ghi dấu mốc khi đã thử HẾT các file. Mất mạng / 403 / bị dừng giữa chừng thì KHÔNG
          ghi, lần sau sẽ tiếp tục phần còn thiếu. Một file hỏng riêng lẻ không chặn dấu mốc (khi
          phát, file thiếu vẫn được tải theo yêu cầu).
        - ``should_continue()`` được kiểm tra trước mỗi file để dừng nhanh khi đổi trang phục / thoát.
        """
        urls = list(dict.fromkeys(u for u in urls if u))
        result = PreloadResult(total=len(urls))
        if self.voices_preloaded(ship, group, urls):
            result.cached, result.complete = len(urls), True
            return result

        pending = [u for u in urls if not self.audio_ready(ship, u)]
        result.cached = len(urls) - len(pending)

        if pending:
            if not should_continue():
                result.stopped = True
                return result
            try:
                real_urls = scraper.resolve_audio_urls(pending)
            except (AccessBlocked, NetworkError) as exc:
                log.info("Không tra được URL giọng nói của %s/%s: %r", ship.name, group, exc)
                result.network_error = True
                return result

            consecutive_errors = 0
            for url in pending:
                if not should_continue():
                    result.stopped = True
                    return result
                target = real_urls.get(url)
                if not target:
                    result.missing += 1
                    continue
                try:
                    scraper.download(target, self.audio_path(ship, url))
                    result.downloaded += 1
                    consecutive_errors = 0
                except AccessBlocked as exc:
                    log.info("Bị chặn khi tải giọng nói: %r", exc)
                    result.network_error = True
                    return result
                except NetworkError as exc:
                    result.failed += 1
                    consecutive_errors += 1
                    if consecutive_errors >= 3:  # nhiều lỗi liên tiếp: coi như mất mạng, đừng gõ cửa Wiki nữa
                        log.info("Ngừng tải trước giọng nói (lỗi liên tiếp): %r", exc)
                        result.network_error = True
                        return result
                except ScraperError as exc:
                    result.failed += 1
                    consecutive_errors = 0
                    log.info("Bỏ qua file giọng nói lỗi: %r", exc)
                time.sleep(pause)  # lịch sự với máy chủ Wiki

        result.complete = True
        try:
            self._mark_voices_preloaded(ship, group, urls, result)
        except OSError as exc:  # không ghi được dấu mốc: lần sau chỉ tốn một lượt kiểm tra file
            log.warning("Không ghi được dấu mốc giọng nói: %s", exc)
            result.complete = False
        log.info(
            "Đã tải trước giọng nói %s/%s: %d file (mới %d, sẵn có %d, thiếu %d, lỗi %d)",
            ship.name, group, result.total, result.downloaded, result.cached, result.missing, result.failed,
        )
        return result
