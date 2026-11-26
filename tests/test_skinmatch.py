"""Kiểm thử ghép trang phục <-> nhóm câu thoại riêng (dùng tên thật của Enterprise trên Wiki).

Chạy:  python -m tests.test_skinmatch      hoặc      pytest
"""
from __future__ import annotations

from src.models import Quote, ShipData, Skin
from src.scraper import merge_skins, parse_skins
from src.skinmatch import (
    describe_mapping, find_variants, match_skins, match_skins_with_method, pretty_name, quote_groups,
    skin_labels, strip_parenthetical, tokens,
)

# Tên mục thoại tiếng Anh của Enterprise trên trang /Quotes (theo thứ tự xuất hiện)
GROUPS = [
    "Default", "Starlight Oath", "Reindeer Master", "Blooming Peony", "Anniversary Ride",
    "Soaring Wings of Freedom", "Heroic Finery", "Wind Catcher", "Bon Voyage", "Diving Under Blue Skies",
]


def skins(*names, aliases=None):
    aliases = aliases or {}
    return [Skin(n, f"https://x/images/{i}.png", list(aliases.get(n, []))) for i, n in enumerate(names)]


def test_exact_names():
    sk = skins(*GROUPS)
    assert match_skins(sk, GROUPS) == GROUPS


def test_default_and_missing_voice():
    sk = skins("Default", "Starlight Oath", "Some Skin Without Voice")
    got = match_skins(sk, ["Default", "Starlight Oath"])
    assert got == ["Default", "Starlight Oath", None]


def test_punctuation_and_case_insensitive():
    sk = skins("Default", "starlight-oath", "WIND CATCHER!")
    assert match_skins(sk, GROUPS) == ["Default", "Starlight Oath", "Wind Catcher"]


def test_alias_matches_official_name():
    # Thư viện ảnh ghi "Oath"/"Christmas" nhưng mục thoại ghi tên chính thức
    sk = skins("Default", "Wedding", "Christmas", aliases={"Wedding": ["Starlight Oath"], "Christmas": ["Reindeer Master"]})
    assert match_skins(sk, GROUPS) == ["Default", "Starlight Oath", "Reindeer Master"]


def test_partial_word_overlap():
    sk = skins("Default", "Oath", "Soaring Wings", "Peony")
    assert match_skins(sk, GROUPS) == ["Default", "Starlight Oath", "Soaring Wings of Freedom", "Blooming Peony"]
    assert tokens("The Skin of Wings") == {"wings"}


def test_each_group_used_once():
    sk = skins("Default", "Oath", "Oath Special")
    got = match_skins(sk, GROUPS)
    assert got[1] == "Starlight Oath" and got[2] != "Starlight Oath"


def test_order_alignment_rules():
    groups = ["Default", "Alpha Gown", "Beta Dress"]
    # số lượng khớp -> ghép theo thứ tự
    assert match_skins(skins("Default", "Skin2", "Skin3"), groups) == ["Default", "Alpha Gown", "Beta Dress"]
    # dư trang phục ở cuối -> coi là bộ mới nhất chưa có thoại
    assert match_skins(skins("Default", "Skin2", "Skin3", "Skin4"), groups) == ["Default", "Alpha Gown", "Beta Dress", None]
    # dư nhóm thoại -> nhóm cuối chưa có ảnh
    assert match_skins(skins("Default", "Skin2"), groups) == ["Default", "Alpha Gown"]


def test_order_between_anchors_needs_equal_counts():
    groups = ["Default", "Alpha", "Mid One", "Mid Two", "Omega"]
    # mốc: Alpha và Omega khớp tên; giữa hai mốc có 1 trang phục nhưng 2 nhóm -> không đoán
    got = match_skins(skins("Default", "Alpha", "Xyz", "Omega"), groups)
    assert got == ["Default", "Alpha", None, "Omega"], got
    # giữa hai mốc có 2 trang phục và 2 nhóm -> ghép theo thứ tự
    got = match_skins(skins("Default", "Alpha", "Xyz", "Uvw", "Omega"), groups)
    assert got == ["Default", "Alpha", "Mid One", "Mid Two", "Omega"], got


def test_variants():
    sk = skins("Default", "Hot Springs", "Hot SpringsCN", "Wedding", "Wedding2", "Hotel")
    assert find_variants(sk) == {2: (1, "CN"), 4: (3, "2")}   # "Hotel" không phải biến thể của "Hot Springs"
    got = match_skins_with_method(sk, ["Default", "Bathing Under Sunny Skies", "Starlight Oath"])
    assert got[2] == ("Bathing Under Sunny Skies", "variant") or got[2][1] == "variant"
    assert got[2][0] == got[1][0] and got[4][0] == got[3][0]


def test_labels_and_pretty_names():
    assert pretty_name("RaceQueen") == "Race Queen" and pretty_name("Hot SpringsCN") == "Hot Springs CN"
    assert pretty_name("Hot_Springs") == "Hot Springs" and pretty_name("Highspeed Etoile") == "Highspeed Etoile"
    assert strip_parenthetical("Starlight Oath (Oath Skin)") == "Starlight Oath"
    sk = skins("Default", "Wedding", "RaceQueen", "RaceQueenCN")
    labels = skin_labels(sk, [ "Default", "Starlight Oath (Oath Skin)", None, None])
    assert labels == ["Default", "Starlight Oath", "Race Queen", "Race Queen (CN)"], labels


# Dữ liệu THẬT của Enterprise (từ kết quả chạy trên máy người dùng)
REAL_SKINS = ["Default", "Wedding", "Christmas", "Spring", "Roadtrip", "Bluray", "Party", "RaceQueen", "Travel",
              "Summer", "Hot Springs", "Hot SpringsCN", "Highspeed Etoile"]
REAL_GROUPS = ["Default", "Starlight Oath (Oath Skin)", "Reindeer Master", "Blooming Peony", "Anniversary Ride",
               "Soaring Wings of Freedom", "Heroic Finery", "Wind Catcher", "Bon Voyage", "Diving Under Blue Skies",
               "Bathing Under Sunny Skies"]


def test_real_enterprise_data():
    sk = skins(*REAL_SKINS)
    got = match_skins(sk, REAL_GROUPS)
    assert got == REAL_GROUPS + ["Bathing Under Sunny Skies", None], got   # 10 chính + biến thể CN + bộ mới không thoại
    methods = [h for _, h in match_skins_with_method(sk, REAL_GROUPS)]
    assert methods[:2] == ["default", "words"] and methods[11] == "variant" and methods[12] == ""
    labels = skin_labels(sk, got)
    assert labels[1] == "Starlight Oath" and labels[9] == "Diving Under Blue Skies"
    assert labels[11] == "Bathing Under Sunny Skies (CN)" and labels[12] == "Highspeed Etoile"
    quotes = [Quote("Login", "t", g, "a.ogg") for g in REAL_GROUPS]
    text = "\n".join(describe_mapping(sk, quotes))
    assert "CHƯA ghép" not in text and "ĐOÁN" in text


def test_methods_are_reported():
    sk = skins("Default", "Wedding", "Oath", "Skin3", aliases={"Wedding": ["Reindeer Master"]})
    got = match_skins_with_method(sk, ["Default", "Reindeer Master", "Starlight Oath", "Zzz Gown"])
    assert [h for _, h in got] == ["default", "name", "words", "order"], got
    text = "\n".join(describe_mapping(sk, [Quote("Login", "t", g, "a.ogg") for g in ["Default", "Reindeer Master", "Starlight Oath", "Zzz Gown"]]))
    assert "ĐOÁN theo thứ tự" in text and "khớp theo từ ngữ" in text
    assert "CHƯA ghép" not in text
    left = describe_mapping(skins("Default"), [Quote("Login", "t", "Default"), Quote("Login", "t", "Lonely Group")])
    assert "CHƯA ghép" in left[-1] and "Lonely Group" in left[-1]


def test_no_quotes_at_all():
    assert match_skins(skins("Default", "X"), []) == [None, None]
    assert quote_groups([]) == []


def test_quote_groups_order():
    qs = [Quote("a", "t", "Default"), Quote("b", "t", "Oath"), Quote("c", "t", "Default"), Quote("d", "t", "Peony")]
    assert quote_groups(qs) == ["Default", "Oath", "Peony"]


# ---------------------------------------------------------------- tên phụ lấy từ HTML
GALLERY = """
<div id="mw-content-text"><div class="tabber">
 <div class="tabbertab" title="Default">
   <p>Enterprise: Default</p>
   <img src="/images/thumb/a/ab/Enterprise.png/600px-Enterprise.png" data-file-height="1536">
 </div>
 <div class="tabbertab" title="Oath">
   <p>Enterprise: Oath</p>
   <ul><li><b>EN client</b>: Starlight Oath · Permanently available</li>
       <li><b>CN client</b>: 誓约的星光 · Limited</li><li>Obtained from: Wedding</li></ul>
   <img src="/images/thumb/f/f1/EnterpriseWedding.png/500px-EnterpriseWedding.png" data-file-height="1400">
 </div>
 <div class="tabbertab" title="Christmas">
   <ul><li>EN client: Reindeer Master Permanently available CN client: 驯鹿之主</li></ul>
   <img src="/images/thumb/c/c1/Enterprise_Reindeer_Master.png/500px-x.png" data-file-height="1400">
 </div>
</div></div>
"""


def test_aliases_extracted_from_html():
    got = parse_skins(GALLERY, "https://azurlane.koumakan.jp/wiki/Enterprise/Gallery", "Enterprise")
    by = {s.name: s for s in got}
    assert set(by) == {"Default", "Oath", "Christmas"}
    assert "Starlight Oath" in by["Oath"].aliases          # dòng "EN client"
    assert "Wedding" in by["Oath"].aliases                  # từ tên file EnterpriseWedding.png
    assert any("Reindeer Master" in a for a in by["Christmas"].aliases)
    assert "Oath" not in by["Oath"].aliases                 # không lặp lại chính tên nhãn
    # và việc ghép dùng được các tên phụ đó
    assert match_skins(got, GROUPS)[1:] == ["Starlight Oath", "Reindeer Master"]


def test_merge_unions_aliases():
    a = [Skin("Default", "u0"), Skin("Oath", "u1", ["Starlight Oath"])]
    b = [Skin("oath", "u9", ["Wedding"]), Skin("Default", "u0")]
    merged = merge_skins(a, b)
    assert [s.name for s in merged] == ["Default", "Oath"]
    assert merged[1].aliases == ["Starlight Oath", "Wedding"]


def test_old_cache_json_still_loads():
    old = {"name": "Enterprise", "wiki_title": "Enterprise",
           "skins": [{"name": "Default", "image_url": "u"}],
           "quotes": [{"event": "Login", "text": "Hi", "skin": "Default", "audio_url": None}]}
    ship = ShipData.from_json(old)
    assert ship.version == 1 and ship.skins[0].aliases == []
    again = ShipData.from_json(ship.to_json())
    assert again.version == 1 and again == ship
    assert ShipData("x", "x").version == 2  # dữ liệu mới luôn mang phiên bản hiện tại


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("OK  ", name)
    print("Tất cả kiểm thử ghép trang phục đã qua.")
