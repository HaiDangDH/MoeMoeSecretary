"""Bộ thu thập dữ liệu chuyên biệt cho https://azurlane.koumakan.jp

Lấy: ảnh nhân vật (mặc định + trang phục), câu thoại và link giọng lồng tiếng.

Các hàm ``parse_*`` là hàm thuần (nhận chuỗi HTML, trả dữ liệu) nên có thể kiểm thử
mà không cần mạng. Cấu trúc trang có thể thay đổi theo thời gian, vì vậy mọi bước
đều có bộ chọn dự phòng (fallback) và không bao giờ ném lỗi chỉ vì thiếu một phần.

Chạy thử:  python -m src.scraper "Enterprise"   (thêm --dump <thư mục> để lưu HTML gốc)
"""
from __future__ import annotations

import logging
import re
import sys
import time
from pathlib import Path
from urllib.parse import quote, unquote, urljoin, urlparse

from bs4 import BeautifulSoup, FeatureNotFound, Tag

from .errors import AccessBlocked, NetworkError, ScraperError, ShipNotFound  # noqa: F401 (re-export)
from .models import VOICE_KEYS, Quote, ShipData, Skin, is_default_name, norm, voice_category

log = logging.getLogger(__name__)

BASE_URL = "https://azurlane.koumakan.jp"
# Các trang HTML (/wiki/...) của Wiki được bảo vệ bởi Anubis (thử thách JavaScript) nên client
# tự động không đọc được. MediaWiki API (/w/api.php) là giao diện chính thức để chương trình đọc
# Wiki và vẫn trả JSON bình thường -> toàn bộ dữ liệu được lấy qua API, không giải thử thách.
API_URL = BASE_URL + "/w/api.php"
IMAGE_HOST = "azurlane.netojuu.com"  # máy chủ ảnh/âm thanh
WIKI_HOST = "azurlane.koumakan.jp"
WIKIFILE_PREFIX = "wikifile:"  # "wikifile:Tên.ogg" = file trên Wiki, tìm URL thật qua API khi tải
# UA kiểu trình duyệt (nhiều Wiki/Cloudflare từ chối UA không có "Mozilla/5.0"), nhưng vẫn
# ghi rõ tên ứng dụng ở cuối để chủ Wiki nhận ra nếu cần.
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36 MoeMoeSecretaryVN/1.0"
)
PAGE_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
}
RESOLVE_BATCH = 40  # số tên file hỏi API mỗi lượt (MediaWiki cho tối đa 50 tiêu đề/yêu cầu)
RETRY_DELAY = 1.5  # giây, chỉ dùng cho lỗi tạm thời (429/5xx/mạng) - KHÔNG dùng cho 403


def asset_headers(url: str) -> dict[str, str]:
    """Header khi tải ảnh/âm thanh (trình duyệt luôn gửi Referer là trang Wiki)."""
    is_audio = bool(AUDIO_EXT.search(url))
    return {
        "Accept": "*/*" if is_audio else "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
        "Referer": BASE_URL + "/",
        "Sec-Fetch-Dest": "audio" if is_audio else "image",
        "Sec-Fetch-Mode": "no-cors",
        "Sec-Fetch-Site": "cross-site",
    }


def describe_response(resp) -> str:
    """Tóm tắt một phản hồi lỗi để ghi log (không gồm cookie)."""
    hdr = resp.headers
    parts = [f"HTTP {resp.status_code}"]
    for name in ("server", "cf-ray", "cf-mitigated", "content-type", "retry-after"):
        value = hdr.get(name)
        if value:
            parts.append(f"{name}={value}")
    try:
        body = re.sub(r"<[^>]+>", " ", resp.text[:4000])
        body = re.sub(r"\s+", " ", body).strip()[:200]
    except Exception:  # noqa: BLE001
        body = ""
    if body:
        parts.append(f"body='{body}'")
    return " | ".join(parts)


TIMEOUT = 20.0
MAX_DOWNLOAD_BYTES = 40 * 1024 * 1024

AUDIO_EXT = re.compile(r"\.(?:ogg|oga|opus|mp3|wav)(?:\?.*)?$", re.IGNORECASE)
IMAGE_EXT = re.compile(r"\.(?:png|webp|jpe?g)$", re.IGNORECASE)
# Ảnh phụ không phải ảnh nhân vật: icon, chibi, nền, banner...
_EXCLUDED_IMAGE = re.compile(
    r"(icon|chibi|banner|shopicon|wallpaper|_sd\b|background|"
    r"[_\-\s]bg\d*\.|BG\d*\.\w+$|dmg|damaged)",
    re.IGNORECASE,
)
_FOOTNOTE = re.compile(r"\s*\[(?:[A-Za-z0-9]+\s)?\d+\]")


# ======================================================================
# Phân tích HTML (hàm thuần)
# ======================================================================
def make_soup(html: str) -> BeautifulSoup:
    try:
        return BeautifulSoup(html, "lxml")
    except FeatureNotFound:  # thiếu lxml -> dùng bộ phân tích có sẵn
        return BeautifulSoup(html, "html.parser")


def _content_root(soup: BeautifulSoup) -> Tag | BeautifulSoup:
    return (
        soup.select_one("#mw-content-text")
        or soup.select_one(".mw-parser-output")
        or soup.select_one("#content")
        or soup
    )


def _clean_text(tag: Tag) -> str:
    """Lấy văn bản của một ô bảng: bỏ chú thích [EN 1], gộp khoảng trắng."""
    clone = BeautifulSoup(str(tag), "html.parser")
    for junk in clone.find_all(["sup", "style", "script"]):
        junk.decompose()
    for junk in clone.select(".reference, .mw-editsection, .audio-button"):
        junk.decompose()
    text = clone.get_text(" ", strip=True).replace("\u200c", "").replace("\u200b", "")
    text = _FOOTNOTE.sub("", text)
    return re.sub(r"\s+", " ", text).strip()


def _heading_text(tag: Tag) -> str:
    headline = tag.select_one(".mw-headline")
    if headline is not None:
        return re.sub(r"\s+", " ", headline.get_text(" ", strip=True))
    clone = BeautifulSoup(str(tag), "html.parser")
    for junk in clone.select(".mw-editsection"):
        junk.decompose()
    return re.sub(r"\s+", " ", clone.get_text(" ", strip=True))


def _skin_display_name(heading: str) -> str:
    """'誓约的星光 / Starlight Oath' -> 'Starlight Oath'; 'Default Skin' -> 'Default'."""
    name = heading.split("/")[-1].strip()
    name = re.sub(r"\s*\[.*?\]\s*$", "", name)
    if is_default_name(name) and norm(name) in ("default", "defaultskin"):
        return "Default"
    return name or "Default"


def fix_host(url: str) -> str:
    """Ảnh/âm thanh nằm ở máy chủ ảnh, không phải máy chủ trang (đang bị Anubis chặn)."""
    parts = urlparse(url)
    if parts.hostname == WIKI_HOST and parts.path.startswith("/images/"):
        return parts._replace(netloc=IMAGE_HOST, scheme="https").geturl()
    return url


def _audio_from_url(value: str, page_url: str) -> str | None:
    if not value:
        return None
    absolute = urljoin(page_url, value.strip())
    path = unquote(urlparse(absolute).path)
    if AUDIO_EXT.search(absolute) and "/wiki/File:" not in path:
        return fix_host(absolute)
    # Liên kết trang "File:Xxx.ogg": đánh dấu để tìm URL thật bằng API khi cần phát
    match = re.search(r"/wiki/(?:File|Tập_tin):(.+\.(?:ogg|oga|opus|mp3|wav))$", path, re.I)
    if match:
        return WIKIFILE_PREFIX + match.group(1)
    return None


def _find_audio(cell: Tag, page_url: str) -> str | None:
    candidates = [cell, *cell.find_all(True)]
    for el in candidates:
        for attr in ("href", "src", "data-src", "data-sound", "data-audio", "data-mwsrc"):
            url = _audio_from_url(el.get(attr, ""), page_url)
            if url:
                return url
    return None


def parse_quotes(html: str, page_url: str = BASE_URL) -> list[Quote]:
    """Phân tích trang ``<Ship>/Quotes``.

    Trang chứa lần lượt các nhóm ngôn ngữ (Anh, Trung, Nhật), mỗi nhóm lặp lại các
    mục "Default Skin" + từng trang phục. Chỉ lấy nhóm đầu tiên (bản tiếng Anh).
    """
    soup = make_soup(html)
    root = _content_root(soup)

    groups: list[list[Quote]] = [[]]
    seen_in_group: list[set[str]] = [set()]
    heading = "Default Skin"

    for el in root.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "table"]):
        if el.name != "table":
            heading = _heading_text(el)
            continue

        header_cells = [c.get_text(" ", strip=True).lower() for c in el.find_all("th")]
        if not any("transcription" in h or "event" in h for h in header_cells):
            continue  # không phải bảng câu thoại (ví dụ bảng chú thích)

        skin = _skin_display_name(heading)
        key = norm(skin)
        if key in seen_in_group[-1]:  # gặp lại tên trang phục -> sang nhóm ngôn ngữ kế
            groups.append([])
            seen_in_group.append(set())
        seen_in_group[-1].add(key)

        for tr in el.find_all("tr"):
            cells = tr.find_all("td", recursive=False) or tr.find_all("td")
            if len(cells) < 2:
                continue
            event = _clean_text(cells[0])
            text = _clean_text(cells[-1])
            if not event or not text:
                continue
            audio = None
            for cell in cells[1:-1] if len(cells) > 2 else []:
                audio = _find_audio(cell, page_url)
                if audio:
                    break
            groups[-1].append(Quote(event=event, text=text, skin=skin, audio_url=audio))

    return groups[0] if groups else []


# ----------------------------------------------------------------------
def _to_full_image_url(url: str) -> str:
    """.../images/thumb/a/ab/Name.png/300px-Name.png -> .../images/a/ab/Name.png"""
    url = url.split("?")[0]
    match = re.match(r"^(.*?/images)/thumb/(.+?)/[^/]+$", url)
    return fix_host(f"{match.group(1)}/{match.group(2)}" if match else url)


def _tab_panel(img: Tag) -> tuple[str | None, Tag | None]:
    """Tìm tab (trang phục) chứa ảnh: trả (tên tab, phần tử tab). Hỗ trợ Tabber cũ/mới."""
    for parent in img.parents:
        if not isinstance(parent, Tag) or parent.name in ("body", "html", "[document]"):
            break
        if parent.name not in ("div", "article", "section", "li"):
            continue
        for attr in ("data-title", "data-tab-title", "title"):
            value = parent.get(attr)
            if isinstance(value, str) and value.strip():
                return value.strip(), parent
        pid = parent.get("id")
        classes = " ".join(parent.get("class") or [])
        if isinstance(pid, str) and "tab" in classes and re.search(r"-\d+$", pid):
            return re.sub(r"-\d+$", "", pid).replace("_", " "), parent
    return None, None


def _int_attr(tag: Tag, name: str) -> int | None:
    try:
        return int(str(tag.get(name, "")).strip())
    except ValueError:
        return None


_ALIAS_END = (
    r"(?=\s*·|\s+(?:EN|CN|JP|KR) client|\s+Obtained from|\s+Cost|\s+Released|\s+Icons"
    r"|\s+Live2D|\s+Has ASMR|\s+Permanently available|\s+Limited|\s+Event limited|$)"
)


def _collect_aliases(panel: Tag | None, fname: str, ship_name: str, label: str) -> list[str]:
    """Tên phụ của một trang phục, dùng để ghép với mục câu thoại cùng trang phục.

    Nguồn: dòng "EN client: <tên chính thức>" trong khung thông tin, chú thích "<Tàu>: <Tên>",
    và tên file ảnh (bỏ tên tàu, tách chữ hoa). Không có nguồn nào cũng không sao.
    """
    aliases: list[str] = []

    def add(value: str) -> None:
        value = re.sub(r"\s+", " ", value).strip(" :·-–—")
        if 2 <= len(value) <= 60 and value != label and value not in aliases:
            aliases.append(value)

    if panel is not None:
        text = re.sub(r"\s+", " ", panel.get_text(" ", strip=True))
        for m in re.finditer(r"EN client\s*:?\s*(.+?)" + _ALIAS_END, text):
            add(m.group(1))
        for m in re.finditer(re.escape(ship_name) + r"\s*:\s*(.+?)" + _ALIAS_END, text):
            add(m.group(1))

    stem = fname.rsplit(".", 1)[0]
    stem = re.sub(r"^" + re.escape(ship_name.replace(" ", "")) + r"[_\s]*", "", stem, flags=re.I)
    stem = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", stem).replace("_", " ").strip()
    if stem and not re.fullmatch(r"(?:skin\s*)?\d*", stem, re.I):
        add(stem)
    return aliases


def parse_skins(html: str, page_url: str, ship_name: str) -> list[Skin]:
    """Tìm ảnh nhân vật theo từng trang phục trong một trang (trang chính hoặc /Gallery)."""
    soup = make_soup(html)
    root = _content_root(soup)
    ship_key = norm(ship_name)

    # (nhãn tab hoặc None, phần tử tab, tên file, url đầy đủ, chiều cao gốc hoặc 0, thứ tự)
    found: list[tuple[str | None, Tag | None, str, str, int, int]] = []
    for order, img in enumerate(root.find_all("img")):
        src = img.get("data-src") or img.get("src") or ""
        if "/images/" not in src:
            continue
        full = _to_full_image_url(urljoin(page_url, src))
        fname = unquote(full.rsplit("/", 1)[-1])
        if not IMAGE_EXT.search(fname) or _EXCLUDED_IMAGE.search(fname):
            continue
        height = _int_attr(img, "data-file-height") or 0
        if height and height < 500:  # biểu tượng nhỏ, huy hiệu phe, ngôi sao độ hiếm...
            continue
        label, panel = _tab_panel(img)
        found.append((label, panel, fname, full, height, order))

    skins: list[Skin] = []
    used_urls: set[str] = set()
    used_labels: set[str] = set()

    labelled = [f for f in found if f[0]]
    if labelled:
        by_label: dict[str, list[tuple[Tag | None, str, str, int, int]]] = {}
        for label, panel, fname, full, height, order in labelled:
            by_label.setdefault(label, []).append((panel, fname, full, height, order))
        for label, items in by_label.items():
            items.sort(key=lambda it: (-it[3], it[4]))  # cao nhất trước, rồi theo thứ tự trang
            panel, fname, full, _h, _o = items[0]
            name = "Default" if is_default_name(label) and norm(label) in (
                "default", "defaultskin") else label
            if full in used_urls or norm(name) in used_labels:
                continue
            used_urls.add(full)
            used_labels.add(norm(name))
            skins.append(Skin(name=name, image_url=full,
                              aliases=_collect_aliases(panel, fname, ship_name, name)))

    # Ảnh không nằm trong tab nào: chỉ nhận ảnh có tên file bắt đầu bằng tên tàu
    for label, _panel, fname, full, _h, _o in found:
        if label or full in used_urls:
            continue
        stem = norm(fname.rsplit(".", 1)[0])
        if not stem.startswith(ship_key):
            continue
        if norm("Default") not in used_labels:
            name = "Default"
        else:
            rest = fname.rsplit(".", 1)[0]
            rest = re.sub(r"^" + re.escape(ship_name.replace(" ", "")) + r"[_\s]*", "", rest, flags=re.I)
            name = re.sub(r"[_]+", " ", rest).strip() or f"Skin {len(skins) + 1}"
        if norm(name) in used_labels:
            continue
        used_urls.add(full)
        used_labels.add(norm(name))
        skins.append(Skin(name=name, image_url=full))

    # Đưa "Default" lên đầu
    skins.sort(key=lambda s: 0 if s.name == "Default" else 1)
    return skins


def merge_skins(*lists: list[Skin]) -> list[Skin]:
    """Gộp danh sách trang phục từ nhiều trang; trang phục trùng tên/ảnh thì gộp tên phụ."""
    merged: list[Skin] = []
    for lst in lists:
        for skin in lst:
            same = next(
                (m for m in merged if norm(m.name) == norm(skin.name) or m.image_url == skin.image_url),
                None,
            )
            if same is None:
                merged.append(Skin(skin.name, skin.image_url, list(skin.aliases)))
                continue
            for alias in skin.aliases:
                if alias != same.name and alias not in same.aliases:
                    same.aliases.append(alias)
    merged.sort(key=lambda s: 0 if s.name == "Default" else 1)  # sort ổn định
    return merged


def title_candidates(query: str) -> list[str]:
    base = re.sub(r"\s+", " ", query.strip())
    variants = [
        base,
        " ".join(w[:1].upper() + w[1:] for w in base.split(" ")),
        " ".join(w.capitalize() for w in base.split(" ")),
        base[:1].upper() + base[1:],
    ]
    out: list[str] = []
    for v in variants:
        v = v.replace(" ", "_")
        if v and v not in out:
            out.append(v)
    return out


_URL_SAFE = "()_,'!-:."


def _wiki_url(title: str, suffix: str = "") -> str:
    return BASE_URL + "/wiki/" + quote(title, safe=_URL_SAFE) + suffix


# ======================================================================
# Lấy dữ liệu qua mạng
# ======================================================================
class AzurLaneScraper:
    def __init__(self, client=None, dump_dir: Path | None = None) -> None:
        if client is None:
            client = self._make_client()
        self._client = client
        self._dump_dir = dump_dir

    @staticmethod
    def _make_client():
        import httpx  # nhập muộn để module vẫn kiểm thử được khi chưa cài httpx

        kwargs = dict(headers=PAGE_HEADERS, timeout=TIMEOUT, follow_redirects=True)
        try:
            return httpx.Client(http2=True, **kwargs)  # trình duyệt dùng HTTP/2
        except ImportError:  # chưa cài gói h2 -> dùng HTTP/1.1
            log.info("Không có gói h2, dùng HTTP/1.1")
            return httpx.Client(**kwargs)

    def close(self) -> None:
        self._client.close()

    # -- HTTP -----------------------------------------------------------
    def _get(self, url: str, params: dict | None = None, headers: dict | None = None):
        """GET; trả None nếu 404; ném AccessBlocked nếu 403; NetworkError nếu mạng/5xx lâu dài."""
        last_exc: Exception | None = None
        for attempt in range(2):
            if attempt:
                time.sleep(RETRY_DELAY)
            try:
                resp = self._client.get(url, params=params, headers=headers)
            except Exception as exc:  # httpx.HTTPError, ssl, dns...
                last_exc = exc
                continue
            code = resp.status_code
            if code == 404:
                return None
            if code == 403:
                # Không thử lại: gửi lại y hệt chỉ khiến bộ lọc bot nghi ngờ hơn.
                info = describe_response(resp)
                log.warning("Wiki từ chối (403) %s -> %s", url, info)
                raise AccessBlocked(info)
            if code >= 500 or code == 429:
                last_exc = ScraperError(describe_response(resp))
                continue
            if code >= 400:
                return None
            return resp
        raise NetworkError(str(last_exc))

    def _api(self, **params) -> dict | None:
        """Gọi MediaWiki API (JSON). Trả None nếu API báo lỗi nội dung (ví dụ trang không tồn tại)."""
        query = {"format": "json", "formatversion": 2, **params}
        resp = self._get(API_URL, params=query, headers={"Accept": "application/json"})
        if resp is None:
            return None
        try:
            data = resp.json()
        except ValueError:
            raise NetworkError("API không trả về JSON: " + describe_response(resp)) from None
        if isinstance(data, dict) and "error" in data:
            log.info("API báo lỗi %s: %s", params.get("action"), data["error"].get("code"))
            return None
        return data

    def _dump(self, name: str, html: str) -> None:
        if self._dump_dir:
            self._dump_dir.mkdir(parents=True, exist_ok=True)
            safe = re.sub(r"[^\w.-]+", "_", name)
            (self._dump_dir / f"{safe}.html").write_text(html, encoding="utf-8")

    def _parse_html(self, title: str) -> str | None:
        """HTML đã dựng sẵn của một trang (action=parse); None nếu trang không tồn tại."""
        data = self._api(
            action="parse", page=title, prop="text", redirects=1,
            disableeditsection=1, disablelimitreport=1,
        )
        if not data or "parse" not in data:
            return None
        html = data["parse"].get("text")
        if isinstance(html, dict):  # formatversion=1 trả {"*": ...}
            html = html.get("*")
        if isinstance(html, str):
            self._dump(title, html)
            return html
        return None

    # -- Tìm trang nhân vật --------------------------------------------
    @staticmethod
    def _existing_titles(data: dict | None, requested: list[str]) -> list[str]:
        """Từ kết quả ``action=query&titles=``: tiêu đề cuối (đã chuẩn hoá + theo chuyển hướng) của
        các trang CÓ tồn tại, đúng thứ tự yêu cầu, không trùng."""
        query = (data or {}).get("query", {})
        normalized = {n["from"]: n["to"] for n in query.get("normalized", [])}
        redirects = {r["from"]: r["to"] for r in query.get("redirects", [])}
        pages = {p.get("title"): p for p in query.get("pages", [])}
        found: list[str] = []
        for name in requested:
            title = normalized.get(name, name)
            title = redirects.get(title, title)
            page = pages.get(title)
            if page and not page.get("missing") and not page.get("invalid") and title not in found:
                found.append(title)
        return found

    def _is_ship(self, title: str) -> bool:
        """Trang tàu: dùng Template:Ship, hoặc có trang con /Quotes hoặc /Gallery."""
        data = self._api(
            action="query", titles=f"{title}|{title}/Quotes|{title}/Gallery",
            prop="templates", tltemplates="Template:Ship", redirects=1,
        )
        pages = ((data or {}).get("query") or {}).get("pages", [])
        for page in pages:
            if page.get("missing") or page.get("invalid"):
                continue
            if page.get("title") == title and page.get("templates"):
                return True
            if page.get("title", "").startswith(title + "/"):
                return True
        return False

    def _resolve(self, query: str) -> str:
        """Tên người dùng gõ -> tiêu đề trang tàu trên Wiki (có dấu cách), hoặc ném ShipNotFound."""
        query = query.replace("|", " ").strip()[:100]
        if not query:
            raise ShipNotFound(query)
        requested = [c.replace("_", " ") for c in title_candidates(query)]
        data = self._api(action="query", titles="|".join(requested), redirects=1)
        for title in self._existing_titles(data, requested):
            if self._is_ship(title):
                return title

        # Dự phòng: tìm kiếm gần đúng của Wiki
        found = self._api(action="opensearch", search=query, limit=5, namespace=0)
        if isinstance(found, list) and len(found) > 1:
            for title in found[1][:5]:
                if "/" not in title and self._is_ship(title):
                    return title
        raise ShipNotFound(query)

    def _file_urls(self, names: list[str]) -> dict[str, str]:
        """Tên file trên Wiki (không gồm 'File:') -> URL ảnh/âm thanh thật, qua API."""
        if not names:
            return {}
        titles = ["File:" + n.replace("_", " ") for n in names]
        data = self._api(action="query", titles="|".join(titles), prop="imageinfo", iiprop="url", redirects=1)
        query = (data or {}).get("query", {})
        normalized = {n["from"]: n["to"] for n in query.get("normalized", [])}
        redirects = {r["from"]: r["to"] for r in query.get("redirects", [])}
        pages = {p.get("title"): p for p in query.get("pages", [])}
        result: dict[str, str] = {}
        for name, title in zip(names, titles):
            final = redirects.get(normalized.get(title, title), normalized.get(title, title))
            info = (pages.get(final) or {}).get("imageinfo") or []
            if info and info[0].get("url"):
                result[name] = fix_host(info[0]["url"])
        return result

    def _default_image_fallback(self, title: str, display: str) -> list[Skin]:
        """Dự phòng cuối: tìm File:<Tên>.png bằng API."""
        names: list[str] = []
        for base in (title, display.replace(" ", ""), display.replace(" ", "_")):
            if f"{base}.png" not in names:
                names.append(f"{base}.png")
        urls = self._file_urls(names)
        for name in names:
            if name in urls:
                return [Skin(name="Default", image_url=urls[name])]
        return []

    # -- API chính ------------------------------------------------------
    def fetch_ship(self, query: str) -> ShipData:
        title = self._resolve(query)  # ví dụ "New Jersey"
        wiki_title = title.replace(" ", "_")
        page_url = _wiki_url(wiki_title)  # chỉ dùng để ghép link tương đối, không gọi tới

        quotes: list[Quote] = []
        html = self._parse_html(f"{title}/Quotes")
        if html:
            quotes = parse_quotes(html, page_url)

        skin_lists = []
        for page in (title, f"{title}/Gallery"):
            html = self._parse_html(page)
            if html:
                skin_lists.append(parse_skins(html, page_url, title))
        skins = merge_skins(*skin_lists)
        if not skins:
            skins = self._default_image_fallback(wiki_title, title)

        return ShipData(name=title, wiki_title=wiki_title, skins=skins, quotes=quotes)

    def resolve_audio_urls(self, urls: list[str]) -> dict[str, str]:
        """URL âm thanh trong cache (có thể là ``wikifile:Tên.ogg``) -> URL thật, tra THEO LÔ.

        Tải cả bộ thoại bằng ``download()`` từng file sẽ tốn một yêu cầu API cho mỗi file; hàm
        này gom tối đa ``RESOLVE_BATCH`` tên mỗi yêu cầu. URL không tìm thấy thì vắng mặt trong kết quả.
        Ném AccessBlocked / NetworkError như các hàm gọi mạng khác.
        """
        result: dict[str, str] = {}
        wiki_names: dict[str, str] = {}
        for url in urls:
            if url.startswith(WIKIFILE_PREFIX):
                wiki_names[url] = url[len(WIKIFILE_PREFIX):]
            elif url:
                result[url] = fix_host(url)  # URL thật sẵn rồi, không cần hỏi API

        names = list(dict.fromkeys(wiki_names.values()))
        found: dict[str, str] = {}
        for i in range(0, len(names), RESOLVE_BATCH):
            found.update(self._file_urls(names[i : i + RESOLVE_BATCH]))
        for url, name in wiki_names.items():
            if name in found:
                result[url] = found[name]
        return result

    def download(self, url: str, dest: Path) -> None:
        """Tải một file (ảnh/âm thanh) về ``dest`` (ghi tạm rồi đổi tên)."""
        if url.startswith(WIKIFILE_PREFIX):
            name = url[len(WIKIFILE_PREFIX):]
            real = self._file_urls([name]).get(name)
            if not real:
                raise ScraperError(f"Không tìm thấy file {name} trên Wiki")
            url = real
        url = fix_host(url)

        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(dest.suffix + ".part")
        last_exc: Exception | None = None
        for attempt in range(2):
            if attempt:
                time.sleep(RETRY_DELAY)
            try:
                total = 0
                with self._client.stream("GET", url, headers=asset_headers(url)) as resp:
                    if resp.status_code == 403:
                        resp.read()
                        info = describe_response(resp)
                        log.warning("Máy chủ ảnh/âm thanh từ chối (403) %s -> %s", url, info)
                        raise AccessBlocked(info)
                    if resp.status_code >= 400:
                        raise ScraperError(f"HTTP {resp.status_code}")
                    with open(tmp, "wb") as fh:
                        for chunk in resp.iter_bytes(64 * 1024):
                            total += len(chunk)
                            if total > MAX_DOWNLOAD_BYTES:
                                raise ScraperError("File quá lớn")
                            fh.write(chunk)
                tmp.replace(dest)
                return
            except AccessBlocked:
                tmp.unlink(missing_ok=True)
                raise  # không thử lại khi bị 403
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
        tmp.unlink(missing_ok=True)
        raise NetworkError(str(last_exc))


# ======================================================================
# Chạy thử từ dòng lệnh
# ======================================================================
def describe_voice_categories(quotes: list[Quote]) -> list[str]:
    """Các mục thoại "điều khiển" đã nhận diện được trong nhóm thoại mặc định (để kiểm chứng tên mục).

    Cũng liệt kê các mục CHƯA thuộc nhóm nào: nếu Wiki dùng tên khác với dự kiến thì nhìn là thấy,
    rồi bổ sung luật trong ``models._VOICE_RULES`` (luật) và hằng ``VOICE_*`` tương ứng.
    """
    default_group = next((q.skin for q in quotes if is_default_name(q.skin)), None)
    pool = [q for q in quotes if q.skin == default_group] if default_group is not None else []
    lines: list[str] = []
    for key in VOICE_KEYS:
        hits = [q for q in pool if voice_category(q.event) == key]
        if hits:
            names = ", ".join(sorted({q.event for q in hits}))
            audio = sum(1 for q in hits if q.audio_url)
            lines.append(f"    {key:<15} <- {names}  ({audio}/{len(hits)} có giọng)")
        else:
            lines.append(f"    {key:<15} <- (KHÔNG TÌM THẤY trong nhóm {default_group!r})")
    other = sorted({q.event for q in pool if voice_category(q.event) is None})
    if other:
        lines.append("    Chưa phân loại: " + ", ".join(other))
    return lines


def _main(argv: list[str]) -> int:
    import json

    args = [a for a in argv if not a.startswith("--")]
    dump = None
    if "--dump" in argv:
        i = argv.index("--dump")
        dump = Path(argv[i + 1]) if i + 1 < len(argv) else Path("dump")
        args = [a for a in args if a != str(dump)]
    name = args[0] if args else "Enterprise"
    scraper = AzurLaneScraper(dump_dir=dump)
    try:
        ship = scraper.fetch_ship(name)
    except ShipNotFound:
        print("Không tìm thấy nhân vật:", name)
        return 1
    except AccessBlocked as exc:
        print("Wiki từ chối truy cập (403):", exc)
        print("-> Chạy: python tools\\diagnose_wiki.py  rồi gửi kết quả để chẩn đoán.")
        return 3
    except NetworkError as exc:
        print("Lỗi mạng:", exc)
        return 2
    finally:
        scraper.close()
    print(f"{ship.name} ({ship.wiki_title}): {len(ship.skins)} trang phục, {len(ship.quotes)} câu thoại")
    for s in ship.skins:
        print("  skin:", s.name, "->", s.image_url)
    with_audio = sum(1 for q in ship.quotes if q.audio_url)
    print(f"  {with_audio}/{len(ship.quotes)} câu thoại có giọng nói")
    from .skinmatch import describe_mapping

    print("  Thoại riêng theo trang phục:")
    print("\n".join(describe_mapping(ship.skins, ship.quotes)))
    print("  Mục thoại điều khiển (Hover / thoại khi rảnh / click 5 lần / nhấn giữ):")
    print("\n".join(describe_voice_categories(ship.quotes)))
    print(json.dumps([q.__dict__ for q in ship.quotes[:3]], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
