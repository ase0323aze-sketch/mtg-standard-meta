"""MTGJSON の foreignData から「英語名 → 公式日本語名」の対応表を作る。

機械翻訳ではなく、各カードに収録された公式日本語カード名を使う。
生成物 jp_names.json は analyze.py / build_showcase.py が読み込み、
サイトに公開する JSON へ日本語名を焼き込むために使う（英語名は MTGA
インポート用に別途保持する）。

    python build_jp_map.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from cardpool import DATA_DIR

OUT = Path(__file__).parent / "jp_names.json"

# MTGJSON の日本語名は「漢字（かな）」のルビ（フリガナ）を含むことがある。
# 例: 聖（せい）なる鋳（ちゅう）造（ぞう）所（しょ） → 聖なる鋳造所
_FURIGANA = re.compile(r"（[^（）]*）")


def strip_furigana(name: str) -> str:
    return _FURIGANA.sub("", name).strip()

# 基本土地など foreignData が無い場合のフォールバック
BASIC_JP = {
    "Swamp": "沼", "Island": "島", "Plains": "平地", "Mountain": "山",
    "Forest": "森", "Wastes": "荒地",
    "Snow-Covered Swamp": "冠雪の沼", "Snow-Covered Island": "冠雪の島",
    "Snow-Covered Plains": "冠雪の平地", "Snow-Covered Mountain": "冠雪の山",
    "Snow-Covered Forest": "冠雪の森",
}


def build() -> dict[str, str]:
    m: dict[str, str] = {}
    for path in sorted(DATA_DIR.glob("*.json")):
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        data = doc.get("data")
        if not isinstance(data, dict):
            continue
        for c in data.get("cards", []):
            en = c.get("name")
            if not en or en in m:
                continue
            for f in (c.get("foreignData") or []):
                if f.get("language") == "Japanese" and f.get("name"):
                    m[en] = strip_furigana(f["name"])
                    break
    for en, jp in BASIC_JP.items():
        m.setdefault(en, jp)
    return m


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    m = build()
    OUT.write_text(json.dumps(m, ensure_ascii=False, indent=0), encoding="utf-8")
    print(f"日本語名 {len(m)} 件を書き出し: {OUT}")


if __name__ == "__main__":
    main()
