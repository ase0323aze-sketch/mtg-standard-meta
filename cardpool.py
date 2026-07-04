"""
MTGJSON のセット別 JSON からスタンダード合法カードプールを構築するモジュール。

- 複数セットの data.cards を読み込み、カード名で重複排除する
- legalities.standard == "Legal" のものだけ残す
- 基本土地・トークンなどは除外する
- 全色対応。色で絞りたい場合は filter_pool() を使う

CLI:
    python cardpool.py            # プール枚数サマリを表示
    python cardpool.py --json     # cards.json を書き出す
    python cardpool.py --excel    # cardpool.xlsx を書き出す（Gemini への手渡し用）
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, asdict
from pathlib import Path

# Windows コンソール (cp932) でも日本語・カード名を化けさせない
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# JSON セットの置き場所（OneDrive デスクトップの mtg フォルダ）
DATA_DIR = Path(os.getenv("MTG_DATA_DIR", r"C:\Users\PC_User\OneDrive\デスクトップ\mtg"))

# プールから除外するカードタイプ（基本土地・トークン・裏面ダミーなど）
EXCLUDE_TYPES = {"Token", "Card"}
BASIC_SUPERTYPE = "Basic"

# 現行スタンダード収録セット（set code）。
# legalities.standard フラグは古い/広すぎるため信用せず、ここで環境を明示的に固定する。
# ここを1行編集すればプールが即座に正しい環境に揃う。
# 除外中: BIG(The Big Score=ボーナスシート/非合法), ALCI(アート集/0枚)
STANDARD_SETS = {
    "WOE", "LCI", "MKM", "OTJ", "DSK", "FDN", "DFT", "TDM", "FIN",
    "EOE", "OM1", "SPM", "TLA", "ECL", "TMT", "SOS", "MSH",
}

# WUBRG の並び順（表示用）
COLOR_ORDER = {"W": 0, "U": 1, "B": 2, "R": 3, "G": 4}


@dataclass
class Card:
    name: str
    mana_cost: str
    mana_value: float
    colors: str          # "WU" など。無色は ""
    type_line: str
    text: str
    rarity: str
    set_code: str

    def color_key(self) -> tuple:
        return tuple(sorted((COLOR_ORDER.get(c, 9) for c in self.colors)))


def _iter_set_files(data_dir: Path) -> list[Path]:
    files = sorted(p for p in data_dir.glob("*.json"))
    if not files:
        raise FileNotFoundError(f"JSON が見つかりません: {data_dir}")
    return files


def load_pool(data_dir: Path = DATA_DIR, sets: set[str] | None = None) -> list[Card]:
    """許可セットのカードのみを読み込み、重複排除済みのカードプールを返す。
    sets=None のときは現行スタンダード(STANDARD_SETS)。sets=set() で全セット。"""
    allowed = STANDARD_SETS if sets is None else sets
    by_name: dict[str, Card] = {}
    for path in _iter_set_files(data_dir):
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            # HTML を誤って保存したファイル等はスキップ
            print(f"  [skip] パース不可: {path.name}")
            continue
        data = doc.get("data")
        if not isinstance(data, dict):
            continue
        for c in data.get("cards", []):
            name = c.get("name")
            if not name or name in by_name:
                continue
            # セット許可リストで環境を固定（stale な legalities フラグは使わない）
            if allowed and c.get("setCode") not in allowed:
                continue
            # 明示的に禁止のカードだけは除外（空/未設定は新セット扱いで許可）
            if c.get("legalities", {}).get("standard") == "Banned":
                continue
            types = set(c.get("types", []))
            supertypes = set(c.get("supertypes", []))
            if types & EXCLUDE_TYPES or BASIC_SUPERTYPE in supertypes:
                continue
            by_name[name] = Card(
                name=name,
                mana_cost=c.get("manaCost", ""),
                mana_value=c.get("manaValue", 0.0),
                colors="".join(c.get("colors", [])),
                type_line=c.get("type", ""),
                text=(c.get("text", "") or "").replace("\n", " / "),
                rarity=c.get("rarity", ""),
                set_code=c.get("setCode", ""),
            )
    return sorted(by_name.values(), key=lambda x: (x.color_key(), x.mana_value, x.name))


def filter_pool(pool: list[Card], colors: str | None = None) -> list[Card]:
    """colors に含まれる色だけで構築可能なカードに絞る（無色は常に許可）。"""
    if not colors:
        return pool
    allowed = set(colors.upper())
    return [c for c in pool if set(c.colors) <= allowed]


def summarize(pool: list[Card]) -> str:
    by_color: dict[str, int] = {}
    for c in pool:
        key = c.colors or "(無色)"
        by_color[key] = by_color.get(key, 0) + 1
    lines = [f"総ユニークカード数: {len(pool)}"]
    for key in sorted(by_color, key=lambda k: -by_color[k]):
        lines.append(f"  {key:>6}: {by_color[key]}")
    return "\n".join(lines)


def export_json(pool: list[Card], out: Path) -> None:
    out.write_text(
        json.dumps([asdict(c) for c in pool], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"書き出し: {out} ({len(pool)} 枚)")


def export_excel(pool: list[Card], out: Path) -> None:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "Standard全カード"
    headers = ["カード名", "マナコスト", "MV", "色", "タイプ", "テキスト", "レアリティ", "セット"]
    ws.append(headers)
    for c in pool:
        ws.append([c.name, c.mana_cost, c.mana_value, c.colors or "無色",
                   c.type_line, c.text, c.rarity, c.set_code])
    wb.save(out)
    print(f"書き出し: {out} ({len(pool)} 枚)")


def main() -> None:
    ap = argparse.ArgumentParser(description="MTGJSON → Standard カードプール")
    ap.add_argument("--json", action="store_true", help="cards.json を書き出す")
    ap.add_argument("--excel", action="store_true", help="cardpool.xlsx を書き出す")
    ap.add_argument("--colors", help="色で絞る（例: WU, B, BUG）")
    args = ap.parse_args()

    pool = load_pool()
    if args.colors:
        pool = filter_pool(pool, args.colors)
    print(summarize(pool))

    here = Path(__file__).parent
    if args.json:
        export_json(pool, here / "cards.json")
    if args.excel:
        export_excel(pool, here / "cardpool.xlsx")


if __name__ == "__main__":
    main()
