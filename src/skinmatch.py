"""Ghép từng trang phục (ảnh) với nhóm câu thoại riêng của nó trên trang ``<Tàu>/Quotes``.

Hai trang đặt tên trang phục rất khác nhau: thư viện ảnh dùng *mã chủ đề trong tên file* (Wedding,
Christmas, Spring, RaceQueen, Hot Springs...), còn mục thoại dùng *tên chính thức* (Starlight Oath,
Reindeer Master, Blooming Peony...). Vì vậy việc ghép đi qua nhiều lớp, từ chắc chắn tới phỏng đoán:

1. Trang phục mặc định <-> nhóm "Default".
2. Biến thể (ví dụ "Hot SpringsCN" là bản CN của "Hot Springs") dùng chung nhóm với bản gốc.
3. Tên (hoặc tên phụ) trùng khớp hoàn toàn.
4. Giống nhau về từ ngữ (có từ đồng nghĩa: Wedding = Oath).
5. Theo thứ tự xuất hiện: cả hai trang đều liệt kê theo thứ tự phát hành. Các phần đã ghép chắc
   chắn làm "mốc"; giữa hai mốc ghép tuần tự nếu số lượng khớp nhau, còn đoạn cuối cùng (sau mốc
   cuối) ghép tuần tự và coi phần dư là các trang phục mới nhất chưa có thoại. Những ghép này là
   PHỎNG ĐOÁN và được đánh dấu rõ trong bảng chẩn đoán.
"""
from __future__ import annotations

import re

from .models import Quote, Skin, norm

_STOP = {
    "the", "of", "a", "an", "and", "in", "to", "skin", "permanently", "available", "limited",
    "event",
}
# Quy ước chung của Azur Lane: trang phục "Wedding" chính là trang phục thề ước "Oath"
_SYNONYMS = {"wedding": "oath"}
MIN_TOKEN_SCORE = 0.6
_VARIANT_SUFFIX = re.compile(r"^(cn|jp|en|kr|tw|alt|b|v?\d{1,2})$")


def is_default(name: str) -> bool:
    return norm(name) in ("default", "defaultskin")


def tokens(name: str) -> set[str]:
    words = re.findall(r"[^\W_]+", name.casefold())
    return {_SYNONYMS.get(w, w) for w in words if len(w) >= 2 and w not in _STOP}


def pretty_name(name: str) -> str:
    """'RaceQueen' -> 'Race Queen', 'Hot SpringsCN' -> 'Hot Springs CN' (tên lấy từ tên file ảnh)."""
    spaced = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", name.replace("_", " "))
    return re.sub(r"\s+", " ", spaced).strip() or name


def strip_parenthetical(name: str) -> str:
    """'Starlight Oath (Oath Skin)' -> 'Starlight Oath'."""
    return re.sub(r"\s*\([^)]*\)\s*$", "", name).strip() or name


def quote_groups(quotes: list[Quote]) -> list[str]:
    """Tên các nhóm trang phục có câu thoại, theo thứ tự xuất hiện."""
    groups: list[str] = []
    for q in quotes:
        if q.skin not in groups:
            groups.append(q.skin)
    return groups


def find_variants(skins: list[Skin]) -> dict[int, tuple[int, str]]:
    """Trang phục nào là biến thể của trang phục đứng trước nó: {chỉ số biến thể: (chỉ số gốc, hậu tố)}."""
    keys = [norm(s.name) for s in skins]
    found: dict[int, tuple[int, str]] = {}
    for j, skin in enumerate(skins):
        if is_default(skin.name):
            continue
        for i in range(j):
            if i in found or is_default(skins[i].name) or not keys[i]:
                continue
            if keys[j].startswith(keys[i]) and len(keys[j]) > len(keys[i]):
                rest = keys[j][len(keys[i]):]
                if _VARIANT_SUFFIX.match(rest):
                    found[j] = (i, rest.upper())
                    break
    return found


def _score(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))


def match_skins_with_method(skins: list[Skin], groups: list[str]) -> list[tuple[str | None, str]]:
    """Như ``match_skins`` nhưng kèm cách ghép: default | name | words | order | variant | "" (không ghép)."""
    n = len(skins)
    result: list[str | None] = [None] * n
    method: list[str] = [""] * n
    used: set[str] = set()
    variants = find_variants(skins)

    def assign(i: int, group: str, how: str) -> None:
        result[i] = group
        method[i] = how
        used.add(group)

    def names(i: int) -> list[str]:
        return [skins[i].name, *skins[i].aliases]

    # 1) trang phục mặc định
    for i, skin in enumerate(skins):
        if is_default(skin.name):
            for g in groups:
                if is_default(g) and g not in used:
                    assign(i, g, "default")
                    break

    open_skins = [i for i in range(n) if result[i] is None and not is_default(skins[i].name) and i not in variants]

    # 2) trùng tên hoàn toàn (kể cả tên phụ)
    for i in list(open_skins):
        keys = {norm(x) for x in names(i) if norm(x)}
        for g in groups:
            if g not in used and not is_default(g) and norm(g) in keys:
                assign(i, g, "name")
                break
    open_skins = [i for i in open_skins if result[i] is None]

    # 3) giống nhau về từ ngữ: chọn cặp điểm cao nhất trước
    pairs: list[tuple[float, int, int, str]] = []
    for i in open_skins:
        for gi, g in enumerate(groups):
            if g in used or is_default(g):
                continue
            score = max((_score(tokens(x), tokens(g)) for x in names(i)), default=0.0)
            if score >= MIN_TOKEN_SCORE:
                pairs.append((score, -abs(gi - i), i, g))
    for _score_value, _closeness, i, g in sorted(pairs, key=lambda t: (-t[0], -t[1])):
        if result[i] is None and g not in used:
            assign(i, g, "words")
    open_skins = [i for i in open_skins if result[i] is None]

    # 4) theo thứ tự, giữa các "mốc" đã ghép chắc chắn
    if open_skins:
        group_index = {g: gi for gi, g in enumerate(groups)}
        anchors = sorted(
            (i, group_index[result[i]]) for i in range(n)
            if result[i] is not None and not is_default(skins[i].name) and i not in variants
        )
        s_bounds = [-1] + [a for a, _ in anchors] + [n]
        g_bounds = [-1] + [b for _, b in anchors] + [len(groups)]
        open_set = set(open_skins)
        for k in range(len(s_bounds) - 1):
            seg_skins = [i for i in range(s_bounds[k] + 1, s_bounds[k + 1]) if i in open_set]
            seg_groups = [
                gi for gi in range(g_bounds[k] + 1, g_bounds[k + 1])
                if groups[gi] not in used and not is_default(groups[gi])
            ]
            if not seg_skins or not seg_groups:
                continue
            is_last = k == len(s_bounds) - 2
            if len(seg_skins) == len(seg_groups) or is_last:
                for i, gi in zip(seg_skins, seg_groups):
                    assign(i, groups[gi], "order")

    # 5) biến thể dùng chung nhóm với bản gốc
    for j, (base, _suffix) in variants.items():
        result[j] = result[base]
        method[j] = "variant" if result[base] is not None else ""

    return list(zip(result, method))


def match_skins(skins: list[Skin], groups: list[str]) -> list[str | None]:
    """Với mỗi trang phục, trả về tên nhóm câu thoại riêng của nó (hoặc None nếu không có)."""
    return [group for group, _how in match_skins_with_method(skins, groups)]


def skin_labels(skins: list[Skin], matched: list[str | None]) -> list[str]:
    """Tên hiển thị thân thiện: ưu tiên tên chính thức từ mục thoại, nếu không thì làm đẹp tên file."""
    variants = find_variants(skins)
    labels: list[str] = []
    for i, skin in enumerate(skins):
        base, suffix = variants.get(i, (i, ""))
        group = matched[base] if base < len(matched) else None
        if is_default(skin.name):
            label = "Default"
        elif group and not is_default(group):
            label = strip_parenthetical(group)
        else:
            label = pretty_name(skins[base].name)
        labels.append(f"{label} ({suffix})" if suffix else label)
    return labels


_HOW_LABEL = {
    "words": "  [khớp theo từ ngữ]",
    "order": "  [ĐOÁN theo thứ tự - kiểm tra lại]",
    "variant": "  [biến thể, dùng chung thoại với bản gốc]",
}


def describe_mapping(skins: list[Skin], quotes: list[Quote]) -> list[str]:
    """Bảng ghép trang phục <-> nhóm thoại dạng văn bản (cho dòng lệnh / chẩn đoán)."""
    groups = quote_groups(quotes)
    matched = match_skins_with_method(skins, groups)
    labels = skin_labels(skins, [g for g, _ in matched])
    counts = {g: sum(1 for q in quotes if q.skin == g) for g in groups}
    voiced = {g: sum(1 for q in quotes if q.skin == g and q.audio_url) for g in groups}
    lines = []
    for skin, label, (group, how) in zip(skins, labels, matched):
        extra = f"  (tên phụ: {', '.join(skin.aliases)})" if skin.aliases else ""
        if group is None:
            lines.append(f"  {skin.name!r:22} -> (không có thoại riêng){extra}")
        else:
            lines.append(
                f"  {skin.name!r:22} -> {group!r}: {counts[group]} câu, {voiced[group]} có giọng"
                f"{_HOW_LABEL.get(how, '')}{extra}"
            )
        if label != skin.name:
            lines[-1] += f"  => hiển thị là {label!r}"
    used = {g for g, _ in matched if g}
    leftovers = [g for g in groups if g not in used]
    if leftovers:
        lines.append("  Nhóm thoại CHƯA ghép với trang phục nào: " + ", ".join(repr(g) for g in leftovers))
    return lines
