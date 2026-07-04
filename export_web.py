"""ブラウザ内デッキ生成のための静的データを docs/data/ に書き出す。

- cards.json  : カードプール（名前/マナ/タイプ/短縮テキスト）。プロンプト構築と実在検証用
- jp_names.json: 英名→公式日本語名（表示用）

これらは公開して問題ない（秘密情報なし）。run_update.ps1 から毎回更新する。
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

from cardpool import load_pool

HERE = Path(__file__).parent
DATA = HERE / "docs" / "data"
TEXT_CAP = 160  # プロンプト肥大を抑えるためカードテキストを短縮


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    DATA.mkdir(parents=True, exist_ok=True)

    pool = load_pool()
    cards = [{
        "n": c.name,
        "m": c.mana_cost,
        "t": c.type_line,
        "c": c.colors,
        "x": (c.text[:TEXT_CAP] + "…") if len(c.text) > TEXT_CAP else c.text,
    } for c in pool]
    out_cards = DATA / "cards.json"
    out_cards.write_text(json.dumps(cards, ensure_ascii=False, separators=(",", ":")),
                         encoding="utf-8")
    print(f"cards.json: {len(cards)} 枚 / {out_cards.stat().st_size // 1024} KB")

    jp_src = HERE / "jp_names.json"
    if jp_src.exists():
        shutil.copyfile(jp_src, DATA / "jp_names.json")
        print(f"jp_names.json: {(DATA / 'jp_names.json').stat().st_size // 1024} KB")
    else:
        print("※ jp_names.json 未生成。先に build_jp_map.py を実行してください")


if __name__ == "__main__":
    main()
