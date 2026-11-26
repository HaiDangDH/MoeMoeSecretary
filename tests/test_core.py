"""Kiểm thử ngoại tuyến (không cần mạng, không cần PySide6).

Chạy:  python -m tests.test_core      hoặc      pytest
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from src import config as cfgmod
from src import locales
from src.scraper import (
    _to_full_image_url,
    merge_skins,
    parse_quotes,
    parse_skins,
    title_candidates,
)

QUOTES_HTML = """
<html><body><h1 id="firstHeading">Enterprise/Quotes</h1>
<div id="mw-content-text"><div class="mw-parser-output">
<h3><span class="mw-headline" id="Default_Skin">Default Skin</span><span class="mw-editsection">[edit]</span></h3>
<table class="wikitable">
<tr><th>Event</th><th>VO</th><th>Transcription</th></tr>
<tr><td>Ship Description</td><td>Yorktown-class aircraft carrier, Hull Number CV-6!</td></tr>
<tr><td>Self Introduction</td>
    <td><a href="https://azurlane.netojuu.com/images/a/ab/Enterprise_Intro.ogg">Play</a>&#8204;</td>
    <td>I am Enterprise. "Grey Ghost" is one of my nicknames.<sup class="reference">[EN 1]</sup></td></tr>
<tr><td>Secretary (Touch)</td>
    <td><span class="mw-tmh-player"><audio src="//azurlane.netojuu.com/images/b/b1/Enterprise_Touch.ogg"></audio>Play</span></td>
    <td>What is it? Sortie time?</td></tr>
<tr><td>Secretary (Special Touch)</td>
    <td><a href="/wiki/File:Enterprise_Special.ogg">Play</a></td><td>What the...?!</td></tr>
</table>
<h3>Starlight Oath</h3>
<table class="wikitable"><tr><th>Event</th><th>VO</th><th>Transcription</th></tr>
<tr><td>Secretary (Idle) 1</td><td><a href="https://azurlane.netojuu.com/images/c/c1/Oath_Idle1.ogg">Play</a></td>
<td>Would you like to try my cooking tonight?</td></tr></table>

<h3>Default Skin</h3>
<table class="wikitable"><tr><th>Event</th><th>VO</th><th>Transcription</th></tr>
<tr><td>Self Introduction</td><td><a href="https://azurlane.netojuu.com/images/d/d1/CN_Intro.ogg">Play</a></td>
<td>我是约克城级航空母舰的企业。<br>I am Enterprise from the Yorktown-class.</td></tr></table>
<h3>誓约的星光 / Starlight Oath</h3>
<table class="wikitable"><tr><th>Event</th><th>VO</th><th>Transcription</th></tr>
<tr><td>Secretary (Touch)</td><td>Play</td><td>唔,这孩子也很中意你呢</td></tr></table>
<table class="wikitable"><tr><th>Note</th></tr><tr><td>không phải bảng thoại</td></tr></table>
</div></div></body></html>
"""

GALLERY_HTML = """
<html><body><div id="mw-content-text"><div class="mw-parser-output">
<div class="tabber">
  <div class="tabbertab" title="Default">
    <a class="image"><img src="/images/thumb/a/ab/Enterprise.png/600px-Enterprise.png"
        data-file-width="1024" data-file-height="1536"></a>
    <img src="/images/thumb/c/cd/EnterpriseBG.png/600px-EnterpriseBG.png" data-file-height="1536">
    <img src="/images/e/e1/Enterprise_chibi.png" data-file-height="900">
  </div>
  <div class="tabbertab" title="Starlight Oath">
    <img src="/images/thumb/f/f1/EnterpriseWedding.png/500px-EnterpriseWedding.png" data-file-height="1400">
  </div>
</div>
<article class="tabber__panel" data-title="Reindeer Master" id="Reindeer_Master-2">
  <img src="//azurlane.netojuu.com/images/thumb/9/99/EnterpriseChristmas.png/400px-EnterpriseChristmas.png"
       data-file-height="1500">
</article>
<img src="/images/thumb/x/xy/Eagle_Union_Icon.png/50px-Eagle_Union_Icon.png" data-file-height="50">
<img src="/images/thumb/s/s1/Star.png/20px-Star.png" data-file-height="20">
</div></div></body></html>
"""

NO_TABS_HTML = """
<html><body><div id="mw-content-text">
<img src="/images/thumb/a/ab/Enterprise.png/600px-Enterprise.png" data-file-height="1536">
<img src="/images/thumb/z/zz/Hornet.png/600px-Hornet.png" data-file-height="1536">
<img src="/images/thumb/a/ac/EnterpriseSkin2.png/600px-EnterpriseSkin2.png" data-file-height="1536">
</div></body></html>
"""


def test_quotes_english_group_only():
    quotes = parse_quotes(QUOTES_HTML, "https://azurlane.koumakan.jp/wiki/Enterprise/Quotes")
    texts = [q.text for q in quotes]
    assert len(quotes) == 5, texts
    assert all("我" not in t and "唔" not in t for t in texts)
    assert {q.skin for q in quotes} == {"Default", "Starlight Oath"}

    intro = next(q for q in quotes if q.event == "Self Introduction")
    assert "[EN 1]" not in intro.text and intro.text.endswith("nicknames.")
    assert intro.audio_url == "https://azurlane.netojuu.com/images/a/ab/Enterprise_Intro.ogg"

    touch = next(q for q in quotes if q.event == "Secretary (Touch)")
    assert touch.audio_url == "https://azurlane.netojuu.com/images/b/b1/Enterprise_Touch.ogg"

    special = next(q for q in quotes if q.event == "Secretary (Special Touch)")
    assert special.audio_url == "wikifile:Enterprise_Special.ogg"  # URL thật tìm qua API khi cần

    desc = next(q for q in quotes if q.event == "Ship Description")
    assert desc.audio_url is None


def test_skins_from_tabs():
    skins = parse_skins(GALLERY_HTML, "https://azurlane.koumakan.jp/wiki/Enterprise/Gallery", "Enterprise")
    names = [s.name for s in skins]
    assert names == ["Default", "Starlight Oath", "Reindeer Master"], names
    # ảnh luôn trỏ tới máy chủ ảnh (máy chủ trang bị Anubis chặn)
    assert skins[0].image_url == "https://azurlane.netojuu.com/images/a/ab/Enterprise.png"
    assert skins[2].image_url == "https://azurlane.netojuu.com/images/9/99/EnterpriseChristmas.png"


def test_skins_without_tabs():
    skins = parse_skins(NO_TABS_HTML, "https://azurlane.koumakan.jp/wiki/Enterprise", "Enterprise")
    assert [s.name for s in skins] == ["Default", "Skin2"], [s.name for s in skins]
    assert not any("Hornet" in s.image_url for s in skins)


def test_merge_and_thumb():
    a = parse_skins(GALLERY_HTML, "https://azurlane.koumakan.jp/", "Enterprise")
    b = parse_skins(NO_TABS_HTML, "https://azurlane.koumakan.jp/", "Enterprise")
    merged = merge_skins(b, a)
    assert merged[0].name == "Default"
    assert len({s.image_url for s in merged}) == len(merged)
    assert (
        _to_full_image_url("https://x.net/images/thumb/4/4c/Gear_Screen_EN.png/500px-Gear_Screen_EN.png")
        == "https://x.net/images/4/4c/Gear_Screen_EN.png"
    )


def test_fix_host():
    from src.scraper import fix_host

    assert fix_host("https://azurlane.koumakan.jp/images/a/ab/X.ogg") == "https://azurlane.netojuu.com/images/a/ab/X.ogg"
    assert fix_host("https://azurlane.netojuu.com/images/a/ab/X.ogg") == "https://azurlane.netojuu.com/images/a/ab/X.ogg"
    assert fix_host("https://azurlane.koumakan.jp/wiki/Enterprise") == "https://azurlane.koumakan.jp/wiki/Enterprise"


def test_title_candidates():
    assert title_candidates("new jersey")[0] == "new_jersey"
    assert "New_Jersey" in title_candidates("new jersey")
    assert title_candidates("Enterprise") == ["Enterprise"]


def test_config_roundtrip_utf8():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "config.yaml"
        first = cfgmod.load(path)  # chưa có file -> tạo mặc định
        assert path.exists() and first.ship_name == "Nagato" and first.language == "vi"
        # Mặc định của các tính năng mới
        assert first.skin_name == "" and first.opacity == 1.0 and first.hover_hotkey == "F12"
        assert first.idle_voice_interval == 300  # mặc định 5 phút

        changed = first.with_(ship_name="Saint Louis", scale=1.25, language="en",
                              floating=False, audio_volume=30, flipped=True, skin_voice=False,
                              skin_name="Starlight Oath: Kai (v2) 'x'", opacity=0.6,
                              hover_hotkey="Ctrl+Alt+H", idle_voice_interval=120)
        cfgmod.save(path, changed)
        assert cfgmod.load(path) == changed
        assert "Tiếng Việt" in path.read_text(encoding="utf-8")  # chú thích tiếng Việt giữ nguyên

        path.write_text("ship_name: yes\nscale: 99\naudio_volume: -5\nlanguage: fr\n", encoding="utf-8")
        bad = cfgmod.load(path)
        assert bad.scale == cfgmod.SCALE_MAX and bad.audio_volume == 0 and bad.language == "vi"
        assert bad.ship_name  # không rỗng


def test_config_opacity_skin_hotkey_validation():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "config.yaml"
        read = lambda text: (path.write_text(text, encoding="utf-8"), cfgmod.load(path))[1]  # noqa: E731

        # Độ mờ: kẹp trong 0.1 - 1.0, giá trị rác / nan -> mặc định
        assert read("opacity: 5\n").opacity == cfgmod.OPACITY_MAX
        assert read("opacity: 0\n").opacity == cfgmod.OPACITY_MIN
        assert read("opacity: 0.456\n").opacity == 0.46
        assert read("opacity: abc\n").opacity == 1.0
        assert read("opacity: .nan\n").opacity == 1.0

        # Phím tắt: chuẩn hoá hoa/thường; phím gõ chữ trần hoặc rác -> F12
        assert read("hover_hotkey: ctrl+alt+h\n").hover_hotkey == "Ctrl+Alt+H"
        assert read("hover_hotkey: H\n").hover_hotkey == "F12"
        assert read("hover_hotkey: Ctrl+\n").hover_hotkey == "F12"
        assert read("hover_hotkey: yes\n").hover_hotkey == "F12"  # YAML hiểu là True
        assert read("hover_hotkey: ''\n").hover_hotkey == "F12"

        # Thoại khi rảnh (giây): 0 = tắt, còn lại kẹp 10 - 86400; rác / .inf -> mặc định 300
        assert read("idle_voice_interval: 120\n").idle_voice_interval == 120
        assert read("idle_voice_interval: 0\n").idle_voice_interval == 0
        assert read("idle_voice_interval: -7\n").idle_voice_interval == 0
        assert read("idle_voice_interval: 3\n").idle_voice_interval == cfgmod.IDLE_VOICE_MIN
        assert read("idle_voice_interval: 999999\n").idle_voice_interval == cfgmod.IDLE_VOICE_MAX
        assert read("idle_voice_interval: abc\n").idle_voice_interval == 300
        assert read("idle_voice_interval: .inf\n").idle_voice_interval == 300
        assert read("ship_name: Belfast\n").idle_voice_interval == 300  # config cũ chưa có khóa này

        # Trang phục: bỏ khoảng trắng thừa, không ép về chuỗi "None"
        assert read("skin_name: '  Wedding '\n").skin_name == "Wedding"
        assert read("skin_name:\n").skin_name == ""
        assert read("ship_name: Belfast\n").skin_name == ""  # config cũ chưa có khóa này vẫn chạy


def test_hotkey_parsing():
    from src import keyspec

    hk = keyspec.parse_hotkey("F12")
    assert (hk.modifiers, hk.vk, hk.text) == (0, 0x7B, "F12")
    hk = keyspec.parse_hotkey(" control + SHIFT + f9 ")
    assert (hk.modifiers, hk.vk, hk.text) == (keyspec.MOD_CONTROL | keyspec.MOD_SHIFT, 0x78, "Ctrl+Shift+F9")
    assert keyspec.parse_hotkey("Win+Alt+Z").modifiers == keyspec.MOD_WIN | keyspec.MOD_ALT
    assert keyspec.parse_hotkey("Ctrl+PgDn").vk == 0x22
    assert keyspec.parse_hotkey("Pause") is not None

    for bad in ("", "+", "Ctrl+", "Ctrl+Alt", "F25", "H", "5", "Space", "Esc", "Home",
                "Ctrl+Ctrl+Ctrl", "Foo+F1", "Ctrl+Nope", None, 12):
        assert keyspec.parse_hotkey(bad) is None, bad
    assert keyspec.format_hotkey("alt+shift+q") == "Alt+Shift+Q"
    assert keyspec.format_hotkey("???") == "???"  # không hợp lệ: trả nguyên văn


def test_locales():
    locales.set_language("vi")
    assert locales.tr("menu.quit") == "Thoát"
    assert "Enterprise" in locales.tr("status.loading_ship", name="Enterprise")
    # Chuỗi của các tính năng mới phải có đủ vi/en và điền được tham số
    for lang in ("vi", "en"):
        locales.set_language(lang)
        assert "F12" in locales.tr("menu.hover_mode", hotkey="F12")
        assert "F12" in locales.tr("status.hover_on", hotkey="F12")
        assert "F12" in locales.tr("status.hotkey_failed", hotkey="F12")
        assert "80" in locales.tr("status.opacity_changed", percent=80)
        for key in ("menu.opacity", "status.hover_off", "status.hover_on_tray"):
            assert locales.tr(key) != key
    locales.set_language("vi")
    locales.set_language("en")
    assert locales.tr("menu.quit") == "Quit"
    locales.set_language("xx")
    assert locales.get_language() == "vi"
    assert locales.tr("không.có.khóa") == "không.có.khóa"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("OK  ", name)
    print("Tất cả kiểm thử đã qua.")
