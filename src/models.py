"""Các cấu trúc dữ liệu dùng chung (có thể chuyển qua lại JSON để lưu cache)."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Callable, Iterable


SCHEMA_VERSION = 2  # 2: Skin.aliases (tên phụ để ghép trang phục với nhóm câu thoại riêng)


@dataclass
class Skin:
    name: str
    image_url: str  # ảnh gốc đầy đủ kích thước trên Wiki
    aliases: list[str] = field(default_factory=list)  # tên phụ: tên EN chính thức, tên trong chú thích...


@dataclass
class Quote:
    event: str  # ví dụ: "Secretary (Touch)"
    text: str  # lời thoại gốc (giữ nguyên)
    skin: str = "Default"  # tên trang phục (khớp với Skin.name theo chuẩn hoá)
    audio_url: str | None = None


@dataclass
class ShipData:
    name: str  # tên hiển thị, ví dụ "Enterprise"
    wiki_title: str  # tiêu đề trang Wiki, ví dụ "New_Jersey"
    skins: list[Skin] = field(default_factory=list)
    quotes: list[Quote] = field(default_factory=list)
    version: int = SCHEMA_VERSION

    # ------------------------------------------------------------------
    def to_json(self) -> dict:
        return asdict(self)

    @classmethod
    def from_json(cls, data: dict) -> "ShipData":
        return cls(
            name=data["name"],
            wiki_title=data["wiki_title"],
            skins=[Skin(**s) for s in data.get("skins", [])],
            quotes=[Quote(**q) for q in data.get("quotes", [])],
            version=int(data.get("version", 1)),  # bản cache cũ không có trường này
        )


def norm(text: str) -> str:
    """Chuẩn hoá tên trang phục để so khớp: chữ thường, bỏ ký tự không phải chữ/số."""
    return re.sub(r"[\W_]+", "", text.casefold())


def is_default_name(name: str) -> bool:
    n = norm(name)
    return n in ("default", "defaultskin", "") or n.startswith("default")


# ======================================================================
# Mục thoại "điều khiển" (khởi động / kết thúc nhiệm vụ, nhắc việc, tình cảm...)
# ======================================================================
# Wiki đặt tên mục khá tuỳ biến ("Starting Mission", "Mission Start", "Mail Reminder"...), nên
# không so khớp chuỗi cứng mà so khớp theo TỪ KHOÁ trên tên đã chuẩn hoá (norm: chữ thường, bỏ
# dấu cách / ngoặc). Dùng `python -m src.scraper "<Tàu>"` để xem mục nào đã được nhận diện.
VOICE_START_MISSION = ("Start mission", "Starting mission")
VOICE_RETURN_MISSION = ("Return from mission",)
VOICE_TASK = ("Task",)
VOICE_MAIL = ("Mail",)
VOICE_COMMISSION = ("Commission",)
VOICE_LOVE = ("Affinity (Love)",)
VOICE_PLEDGE = ("Pledge",)


def _has(n: str, *parts: str) -> bool:
    return all(p in n for p in parts)


def _has_any(n: str, *parts: str) -> bool:
    return any(p in n for p in parts)


# Thứ tự quan trọng: nhận diện mục đầu tiên khớp. Tham số n là tên mục đã chuẩn hoá bằng norm().
# Lưu ý "commission" chứa sẵn chữ "mission" nên các luật về "mission" phải loại nó ra.
_VOICE_RULES: dict[str, Callable[[str], bool]] = {
    "start_mission": lambda n: _has(n, "start", "mission")
    and not _has_any(n, "complete", "return", "reminder", "commission"),
    "return_mission": lambda n: _has(n, "return", "mission") and "commission" not in n,
    "task": lambda n: n in ("task", "taskreminder", "missionreminder"),  # KHÔNG gồm "Task Complete"
    "mail": lambda n: "mail" in n,  # "Mail", "Mail Reminder"
    "commission": lambda n: "commission" in n,  # "Commission", "Commission Complete"
    "affinity_love": lambda n: "love" in n and (n == "love" or _has_any(n, "affinity", "affection")),
    "pledge": lambda n: "pledge" in n or n in ("oath", "vow"),
}


VOICE_KEYS = tuple(_VOICE_RULES)  # các khoá nhóm, theo thứ tự ưu tiên nhận diện


def voice_category(event: str) -> str | None:
    """Khoá chuẩn ("start_mission", "task", "pledge"...) của một mục thoại, None nếu không thuộc nhóm nào."""
    n = norm(event)
    if not n:
        return None
    for key, rule in _VOICE_RULES.items():
        if rule(n):
            return key
    return None


def voice_matches(event: str, names: Iterable[str]) -> bool:
    """Mục thoại ``event`` có thuộc một trong các ``names`` không?

    Khớp khi (1) trùng tên hoàn toàn, không phân biệt hoa/thường và dấu câu; hoặc (2) cả hai
    cùng thuộc một nhóm từ khoá chuẩn (ví dụ "Starting Mission" ~ "Mission Start").
    """
    names = list(names)
    n = norm(event)
    if not n or not names:
        return False
    if n in {norm(x) for x in names}:
        return True
    category = voice_category(event)
    return category is not None and category in {voice_category(x) for x in names}
