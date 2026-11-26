"""Kiểm thử luồng tải dữ liệu bằng Wiki giả lập (không cần mạng, không cần httpx).

Bộ giả lập mô phỏng đúng cách MediaWiki API chuẩn hoá tên, theo chuyển hướng, trả action=parse /
imageinfo / opensearch; và mô phỏng đúng tình hình thật: MỌI trang /wiki/... đều bị Anubis chặn (403).
Chạy:  python -m tests.test_scraper_flow      hoặc      pytest
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import src.scraper as sc
from src.errors import AccessBlocked, NetworkError, ShipNotFound
from src.scraper import API_URL, AzurLaneScraper, asset_headers, describe_response
from tests.test_core import GALLERY_HTML, QUOTES_HTML

ANUBIS = "<html><body>Making sure you're not a bot! Anubis could not load its JavaScript.</body></html>"
MAIN_HTML = '<div class="mw-parser-output"><p>Hull Number CV-6</p></div>'
NETOJUU = "https://azurlane.netojuu.com/images/"


def norm_title(t: str) -> str:  # đúng như MediaWiki: "_" -> " ", viết hoa chữ cái đầu
    t = t.replace("_", " ").strip()
    return t[:1].upper() + t[1:]


class FakeWiki:
    def __init__(self, pages, redirects=None, ship_pages=(), files=None):
        self.pages, self.redirects = pages, redirects or {}
        self.ship_pages, self.files = set(ship_pages), files or {}

    def handle(self, p: dict):
        action = p["action"]
        if action == "query":
            normalized, redirs, out, seen = [], [], [], set()
            for raw in p["titles"].split("|"):
                n = norm_title(raw)
                if n != raw:
                    normalized.append({"fromencoded": False, "from": raw, "to": n})
                final = n
                if p.get("redirects") and n in self.redirects:
                    final = self.redirects[n]
                    redirs.append({"from": n, "to": final})
                if final in seen:
                    continue
                seen.add(final)
                if final.startswith("File:"):
                    url = self.files.get(final[5:])
                    page = {"ns": 6, "title": final}
                    if url:
                        page.update(pageid=9, imageinfo=[{"url": url}])
                    else:
                        page["missing"] = True
                else:
                    page = {"ns": 0, "title": final}
                    if final in self.pages:
                        page["pageid"] = 1
                        if p.get("prop") == "templates" and final in self.ship_pages:
                            page["templates"] = [{"ns": 10, "title": "Template:Ship"}]
                    else:
                        page["missing"] = True
                out.append(page)
            q = {"pages": out}
            if normalized:
                q["normalized"] = normalized
            if redirs:
                q["redirects"] = redirs
            return 200, {"batchcomplete": True, "query": q}
        if action == "parse":
            t = norm_title(p["page"])
            t = self.redirects.get(t, t)
            if t in self.pages:
                return 200, {"parse": {"title": t, "pageid": 1, "text": self.pages[t]}}
            return 200, {"error": {"code": "missingtitle", "info": "The page you specified doesn't exist."}}
        if action == "opensearch":
            s = p["search"].lower()
            return 200, [p["search"], [t for t in self.pages if s in t.lower() and "/" not in t], [], []]
        return 400, {"error": {"code": "badaction"}}


class FakeResp:
    def __init__(self, status, text="", url="", headers=None):
        self.status_code, self.text, self.url = status, text, url
        self.headers = {k.lower(): v for k, v in (headers or {}).items()}

    def json(self):
        return json.loads(self.text)

    def read(self):
        return self.text.encode()

    def iter_bytes(self, _n):
        yield b"data"

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakeClient:
    def __init__(self, wiki=None, api_script=None, stream_status=200):
        self.wiki, self.api_script, self.stream_status = wiki, list(api_script or []), stream_status
        self.calls: list[tuple[str, dict]] = []
        self.streams: list[tuple[str, dict]] = []

    def get(self, url, params=None, headers=None):
        self.calls.append((url, dict(params or {})))
        if url != API_URL:  # mọi trang HTML đều bị Anubis chặn, như trên Wiki thật
            return FakeResp(403, ANUBIS, url, {"content-type": "text/html"})
        if self.api_script:
            status = self.api_script.pop(0)
            if status != 200:
                return FakeResp(status, "<html>error</html>", url, {"server": "cloudflare"})
        status, payload = self.wiki.handle(params)
        return FakeResp(status, json.dumps(payload), url)

    def stream(self, method, url, headers=None):
        self.streams.append((url, dict(headers or {})))
        return FakeResp(self.stream_status, "denied" if self.stream_status == 403 else "", url)

    def close(self):
        pass


def make_wiki() -> FakeWiki:
    pages = {
        "Enterprise": MAIN_HTML,
        "Enterprise/Quotes": QUOTES_HTML,
        "Enterprise/Gallery": GALLERY_HTML,
        "New Jersey": MAIN_HTML,
        "New Jersey/Quotes": QUOTES_HTML,
        "Dockyard": "<p>not a ship</p>",
        "Foo": MAIN_HTML,  # tàu mới: có Template:Ship nhưng chưa có /Quotes, /Gallery
    }
    return FakeWiki(
        pages, redirects={"Big E": "Enterprise"}, ship_pages={"Enterprise", "New Jersey", "Foo"},
        files={"Foo.png": NETOJUU + "a/ab/Foo.png", "Enterprise special.ogg": NETOJUU + "e/e1/Enterprise_Special.ogg"},
    )


def only_api(client: FakeClient) -> bool:
    return all(url == API_URL for url, _ in client.calls)


def test_fetch_full_flow_uses_only_api():
    client = FakeClient(make_wiki())
    ship = AzurLaneScraper(client=client).fetch_ship("enterprise")  # gõ chữ thường
    assert ship.name == "Enterprise" and ship.wiki_title == "Enterprise"
    assert [s.name for s in ship.skins] == ["Default", "Starlight Oath", "Reindeer Master"]
    assert all(s.image_url.startswith(NETOJUU) for s in ship.skins)
    assert len(ship.quotes) == 5 and any(q.audio_url for q in ship.quotes)
    assert only_api(client), "không được đụng tới trang /wiki/ (bị Anubis chặn)"


def test_multiword_and_redirect_names():
    client = FakeClient(make_wiki())
    ship = AzurLaneScraper(client=client).fetch_ship("new jersey")  # "New jersey" không tồn tại, "New Jersey" có
    assert ship.name == "New Jersey" and ship.wiki_title == "New_Jersey"
    assert AzurLaneScraper(client=FakeClient(make_wiki())).fetch_ship("Big E").name == "Enterprise"  # chuyển hướng


def test_new_ship_without_subpages_uses_image_fallback():
    ship = AzurLaneScraper(client=FakeClient(make_wiki())).fetch_ship("foo")
    assert ship.quotes == []
    assert [(s.name, s.image_url) for s in ship.skins] == [("Default", NETOJUU + "a/ab/Foo.png")]


def test_not_a_ship_or_unknown():
    for name in ("Dockyard", "Zzzz", "   "):
        try:
            AzurLaneScraper(client=FakeClient(make_wiki())).fetch_ship(name)
        except ShipNotFound:
            continue
        raise AssertionError(f"{name!r} phải ném ShipNotFound")


def test_403_not_retried_and_reported():
    class Blocked(FakeClient):
        def get(self, url, params=None, headers=None):
            self.calls.append((url, dict(params or {})))
            return FakeResp(403, ANUBIS, url, {"server": "anubis"})

    client = Blocked(make_wiki())
    try:
        AzurLaneScraper(client=client).fetch_ship("Enterprise")
    except AccessBlocked as exc:
        assert isinstance(exc, NetworkError) and "403" in str(exc) and "bot" in str(exc)
    else:
        raise AssertionError("phải ném AccessBlocked")
    assert len(client.calls) == 1, client.calls


def test_transient_5xx_retried_once():
    sc.RETRY_DELAY = 0
    client = FakeClient(make_wiki(), api_script=[503])  # lần gọi đầu 503, sau đó bình thường
    assert AzurLaneScraper(client=client).fetch_ship("Enterprise").name == "Enterprise"
    dead = FakeClient(make_wiki(), api_script=[503, 503])
    try:
        AzurLaneScraper(client=dead).fetch_ship("Enterprise")
    except NetworkError as exc:
        assert not isinstance(exc, AccessBlocked)
    else:
        raise AssertionError("phải ném NetworkError")


def test_download_resolves_wikifile_and_sends_referer():
    sc.RETRY_DELAY = 0
    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp) / "voice.ogg"
        client = FakeClient(make_wiki())
        AzurLaneScraper(client=client).download("wikifile:Enterprise_special.ogg", dest)
        assert dest.read_bytes() == b"data"
        url, headers = client.streams[0]
        assert url == NETOJUU + "e/e1/Enterprise_Special.ogg"
        assert headers["Referer"] == "https://azurlane.koumakan.jp/" and headers["Sec-Fetch-Dest"] == "audio"

        # URL cũ trỏ vào máy chủ trang -> tự sửa sang máy chủ ảnh
        client2 = FakeClient(make_wiki())
        AzurLaneScraper(client=client2).download("https://azurlane.koumakan.jp/images/a/ab/X.png", Path(tmp) / "x.raw")
        assert client2.streams[0][0] == NETOJUU + "a/ab/X.png"

        # file không có trên Wiki
        try:
            AzurLaneScraper(client=FakeClient(make_wiki())).download("wikifile:Khong_co.ogg", Path(tmp) / "n.ogg")
        except sc.ScraperError:
            pass
        else:
            raise AssertionError("phải báo lỗi")


def test_resolve_audio_urls_batches_requests():
    """Tải cả bộ thoại: tên file được hỏi API THEO LÔ, không phải mỗi file một yêu cầu."""
    files = {f"Voice {i}.ogg": NETOJUU + f"a/ab/Voice_{i}.ogg" for i in range(95)}
    wiki = FakeWiki({}, files=files)
    client = FakeClient(wiki)
    urls = [f"wikifile:Voice_{i}.ogg" for i in range(95)]
    urls += ["wikifile:Khong_co.ogg", "https://azurlane.koumakan.jp/images/a/ab/Real.ogg"]
    resolved = AzurLaneScraper(client=client).resolve_audio_urls(urls)

    assert len(client.calls) == 3  # 95 + 1 tên cần tra = 96 -> ceil(96 / 40) = 3 yêu cầu API (không phải 96)
    assert resolved["wikifile:Voice_7.ogg"] == NETOJUU + "a/ab/Voice_7.ogg"
    assert "wikifile:Khong_co.ogg" not in resolved  # file không có trên Wiki -> vắng mặt
    assert resolved["https://azurlane.koumakan.jp/images/a/ab/Real.ogg"] == NETOJUU + "a/ab/Real.ogg"  # sửa host
    assert len(resolved) == 96
    assert AzurLaneScraper(client=FakeClient(wiki)).resolve_audio_urls([]) == {}


def test_download_403():
    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp) / "x.raw"
        client = FakeClient(make_wiki(), stream_status=403)
        try:
            AzurLaneScraper(client=client).download(NETOJUU + "a/ab/E.png", dest)
        except AccessBlocked:
            pass
        else:
            raise AssertionError("phải ném AccessBlocked")
        assert len(client.streams) == 1 and not dest.exists()


def test_headers_and_describe():
    assert sc.USER_AGENT.startswith("Mozilla/5.0") and sc.USER_AGENT.endswith("MoeMoeSecretaryVN/1.0")
    assert asset_headers("https://x/a.ogg")["Sec-Fetch-Dest"] == "audio"
    assert asset_headers("https://x/a.png")["Sec-Fetch-Dest"] == "image"
    text = describe_response(FakeResp(403, "<html><body>Access denied</body></html>", "u", {"server": "x"}))
    assert "HTTP 403" in text and "server=x" in text and "Access denied" in text


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("OK  ", name)
    print("Tất cả kiểm thử luồng tải đã qua.")
