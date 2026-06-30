"""収集の共通基盤: 正規化済みデッキレコードと、アーキタイプ推定の軽量ヘルパ。

各サイトのアダプタ（moxfield.py 等）は、サイト固有の形式をここの DeckRecord に
変換して返す。これにより保存・解析側はサイトを意識しなくてよくなる。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


# 共通 User-Agent。AI 学習クローラと誤認されないよう、個人ツールであることを明示する。
USER_AGENT = "mtg-deckgen/0.1 (personal hobby deck research; contact: local user)"

WUBRG = "WUBRG"

# 基本土地（カードプールからは除外されるが、デッキリストには含まれる）
BASIC_LANDS = {"Swamp", "Island", "Plains", "Mountain", "Forest", "Wastes",
               "Snow-Covered Swamp", "Snow-Covered Island", "Snow-Covered Plains",
               "Snow-Covered Mountain", "Snow-Covered Forest"}


@dataclass
class DeckRecord:
    """1 つのデッキの正規化表現。"""
    source: str                       # "moxfield" / "mtgtop8" / ...
    source_deck_id: str               # サイト内の一意 ID（重複排除キー）
    name: str
    colors: str                       # 色識別子 "WUB" など（WUBRG 順）
    fmt: str = "standard"
    url: str = ""
    archetype: str = ""               # 推定 or サイト提供のアーキタイプ
    event: str | None = None          # 大会名（あれば）
    event_date: str | None = None     # 大会日 (YYYY-MM-DD)
    placement: str | None = None      # 順位（あれば）
    meta_share: float | None = None   # メタ占有率 %（あれば）
    win_rate: float | None = None     # 勝率 %（あれば）
    collected_at: str = field(default_factory=lambda: date.today().isoformat())
    # (quantity, card_name, board) board は "main" / "side"
    cards: list[tuple[int, str, str]] = field(default_factory=list)

    def main_count(self) -> int:
        return sum(q for q, _, b in self.cards if b == "main")


def normalize_colors(colors: list[str] | str) -> str:
    """色リスト/文字列を WUBRG 順の文字列にする。"""
    s = set(colors)
    return "".join(c for c in WUBRG if c in s)


# アーキタイプ推定用の代表カード→アーキタイプ辞書（軽量ヒューリスティック）。
# サイトがアーキタイプ名を直接持っている場合はそちらを優先し、これは fallback。
# キーは必ず WUBRG 順（normalize_colors の出力と一致させる）
_COLOR_GUILD = {
    "": "無色", "W": "白単", "U": "青単", "B": "黒単", "R": "赤単", "G": "緑単",
    "WU": "アゾリウス", "UB": "ディミーア", "WB": "オルゾフ", "UR": "イゼット",
    "BR": "ラクドス", "RG": "グルール", "WG": "セレズニア", "BG": "ゴルガリ",
    "WR": "ボロス", "UG": "シミック",
    "WUB": "エスパー", "UBR": "グリクシス", "BRG": "ジャンド", "WRG": "ナヤ", "WUG": "バント",
    "WBG": "アブザン", "WUR": "ジェスカイ", "UBG": "スゥルタイ", "WBR": "マルドゥ", "URG": "ティムール",
}

_KEYWORD_HINTS = [
    ("Prowess", "果敢"),
    ("Cori-Steel", "果敢"),
    ("Burn", "バーン"),
    ("Aggro", "アグロ"),
    ("Control", "コントロール"),
    ("Midrange", "ミッドレンジ"),
    ("Reanimator", "リアニメイト"),
    ("Tokens", "トークン"),
    ("Landfall", "上陸"),
]


def guess_archetype(colors: str, name: str, hubs: list | None = None) -> str:
    """色・デッキ名・サイト提供 hub からアーキタイプ名を推定する。
    hubs は文字列のリスト、または {"name": ...} の辞書リストのどちらも許容する。"""
    if hubs:
        labels = [h.get("name") if isinstance(h, dict) else h for h in hubs]
        labels = [s for s in labels if s]
        if labels:
            return ", ".join(labels)
    guild = _COLOR_GUILD.get(colors, colors or "無色")
    lowered = name.lower()
    for kw, label in _KEYWORD_HINTS:
        if kw.lower() in lowered:
            return f"{guild}{label}"
    return guild
