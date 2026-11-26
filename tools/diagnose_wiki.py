"""Chẩn đoán lỗi truy cập Azur Lane Wiki (ví dụ lỗi 403).

Chạy (trong môi trường đã cài requirements):   python tools\\diagnose_wiki.py
Kết quả được in ra màn hình và lưu vào wiki_diagnose.txt - hãy gửi nội dung file này.

Công cụ chỉ gửi vài yêu cầu GET/HEAD bình thường (mỗi kiểu một lần) để xem Wiki phản hồi
thế nào; nó KHÔNG cố vượt qua thử thách chống bot. Không có thông tin cá nhân hay cookie
nào được ghi lại.
"""
from __future__ import annotations

import platform
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402

from src.scraper import API_URL, BASE_URL, PAGE_HEADERS, USER_AGENT, AzurLaneScraper, asset_headers  # noqa: E402
from src.errors import ScraperError  # noqa: E402

OLD_UA = "MoeMoeSecretaryVN/1.0 (desktop mascot; fetches public wiki pages once and caches them)"
IMAGE_URL = "https://azurlane.netojuu.com/images/thumb/9/9b/ShipworkImage.png/350px-ShipworkImage.png"
SHOW = ("server", "cf-ray", "cf-mitigated", "content-type", "retry-after", "location", "via", "x-cache")

lines: list[str] = []


def out(text: str = "") -> None:
    print(text)
    lines.append(text)


def has_h2() -> bool:
    try:
        import h2  # noqa: F401
        return True
    except ImportError:
        return False


def probe(title: str, url: str, *, headers: dict, http2: bool, method: str = "GET") -> None:
    out(f"\n--- {title}")
    out(f"    {method} {url}")
    try:
        with httpx.Client(headers=headers, timeout=20, follow_redirects=True, http2=http2) as client:
            resp = client.request(method, url)
    except ImportError as exc:
        out(f"    (bỏ qua: {exc})")
        return
    except Exception as exc:  # noqa: BLE001
        out(f"    LỖI KẾT NỐI: {type(exc).__name__}: {exc}")
        return
    out(f"    -> HTTP {resp.status_code}  ({resp.http_version})  url cuối: {resp.url}")
    for name in SHOW:
        if name in resp.headers:
            out(f"       {name}: {resp.headers[name][:120]}")
    if method == "GET":
        text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", resp.text[:20000], flags=re.S | re.I)
        text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text)).strip()[:240]
        out(f"       nội dung: {text!r}")


def end_to_end(name: str) -> None:
    """Chạy đúng luồng của ứng dụng (qua API) và tóm tắt kết quả."""
    out(f"\n--- G. Luồng thật của ứng dụng: tải dữ liệu '{name}' qua API")
    scraper = AzurLaneScraper()
    try:
        ship = scraper.fetch_ship(name)
    except ScraperError as exc:
        out(f"    THẤT BẠI: {type(exc).__name__}: {exc}")
        return
    except Exception as exc:  # noqa: BLE001
        out(f"    LỖI: {type(exc).__name__}: {exc}")
        return
    finally:
        scraper.close()
    with_audio = sum(1 for q in ship.quotes if q.audio_url)
    out(f"    -> {ship.name}: {len(ship.skins)} trang phục, {len(ship.quotes)} câu thoại ({with_audio} có giọng nói)")
    for skin in ship.skins[:6]:
        out(f"       skin: {skin.name} -> {skin.image_url}")
    for quote in ship.quotes[:3]:
        out(f"       thoại [{quote.skin}/{quote.event}]: {quote.text[:70]!r}")
    from src.skinmatch import describe_mapping

    out("       Thoại riêng theo trang phục:")
    for line in describe_mapping(ship.skins, ship.quotes):
        out("   " + line)
    if not ship.skins:
        out("       (CHÚ Ý: không tìm thấy ảnh - có thể cần chỉnh bộ chọn; gửi file này kèm thư mục dump)")
    # thử tải thật ảnh đầu tiên (giống ứng dụng) để kiểm tra máy chủ ảnh
    if ship.skins:
        import tempfile

        scraper = AzurLaneScraper()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                dest = Path(tmp) / "test.raw"
                scraper.download(ship.skins[0].image_url, dest)
                out(f"       tải thử ảnh đầu tiên: OK ({dest.stat().st_size // 1024} KB)")
        except Exception as exc:  # noqa: BLE001
            out(f"       tải thử ảnh đầu tiên: THẤT BẠI {type(exc).__name__}: {exc}")
        finally:
            scraper.close()


def main() -> None:
    out(f"Thời gian : {datetime.now():%Y-%m-%d %H:%M:%S}")
    out(f"Python    : {platform.python_version()} ({platform.system()} {platform.release()})")
    out(f"httpx     : {httpx.__version__}   gói h2 (HTTP/2): {'có' if has_h2() else 'KHÔNG'}")
    out(f"UA mới    : {USER_AGENT}")

    page = f"{BASE_URL}/wiki/Enterprise"
    probe("A. UA cũ của ứng dụng, HTTP/1.1", page, headers={"User-Agent": OLD_UA}, http2=False)
    probe("B. Header kiểu trình duyệt, HTTP/1.1", page, headers=PAGE_HEADERS, http2=False)
    if has_h2():
        probe("C. Header kiểu trình duyệt, HTTP/2 (cách ứng dụng đang dùng)", page, headers=PAGE_HEADERS, http2=True)
    probe("D. MediaWiki API: thông tin site", f"{API_URL}?action=query&meta=siteinfo&format=json",
          headers=PAGE_HEADERS, http2=has_h2())
    probe("E. MediaWiki API: nội dung trang câu thoại",
          f"{API_URL}?action=parse&page=Enterprise/Quotes&prop=text&format=json&formatversion=2",
          headers=PAGE_HEADERS, http2=has_h2())
    probe("F. Máy chủ ảnh (HEAD, có Referer)", IMAGE_URL,
          headers={**PAGE_HEADERS, **asset_headers(IMAGE_URL)}, http2=has_h2(), method="HEAD")

    end_to_end("Enterprise")

    Path("wiki_diagnose.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    out("\nĐã lưu: wiki_diagnose.txt")


if __name__ == "__main__":
    main()
