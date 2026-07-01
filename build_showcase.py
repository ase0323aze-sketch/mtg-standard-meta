"""固定お題リストで複数デッキを生成し、Web ビューア用 JSON に書き出す。

自動更新（run_update.ps1）から呼ばれ、現メタを注入した「AI おすすめデッキ」を
docs/data/decks.json として公開する。Gemini API はローカル実行時に回すので、
GitHub Pages 側は静的 JSON を読むだけでよい。

    python build_showcase.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import analyze
import store
from build_deck import get_client, generate_deck
from cardpool import load_pool, filter_pool
from jpnames import JpNames

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

OUT = Path(__file__).parent / "docs" / "data" / "decks.json"

# 生成するお題リスト（title は画面表示名、colors は色制限 / None は全色）
THEMES = [
    {"title": "現メタ最強候補", "colors": None,
     "theme": "現環境で最も安定して勝てる完成度の高いデッキ。上位メタに五分以上戦える構築"},
    {"title": "メタに刺すアグロ", "colors": None,
     "theme": "コントロールが多い現環境を、軽いクロックと火力で素早く殴り切るアグロ"},
    {"title": "受け切りコントロール", "colors": None,
     "theme": "除去と打ち消しで相手を捌き切り、強力な勝ち筋で蓋をするコントロール"},
    {"title": "ローグ好みの変則コンボ", "colors": None,
     "theme": "意表を突く2〜3枚のコンボや変則的な勝ち筋で決める、ローグ好みのデッキ"},
]


def main() -> None:
    pool_all = load_pool()
    conn = store.connect()
    meta_context = analyze.meta_context_text(conn)
    snapshot = analyze._latest_snapshot(conn, analyze.DEFAULT_SOURCE)
    conn.close()

    client = get_client()
    jp = JpNames()
    decks = []
    for i, spec in enumerate(THEMES, 1):
        print(f"\n=== [{i}/{len(THEMES)}] {spec['title']} ===")
        pool = filter_pool(pool_all, spec["colors"])
        try:
            d = generate_deck(client, pool, spec["theme"], spec["colors"],
                              meta_context=meta_context)
        except Exception as e:
            print(f"  生成失敗: {e}")
            continue
        main = [e for e in d.get("maindeck", []) if int(e.get("count", 0)) > 0]
        for e in main:                       # 表示用の公式日本語名を付与（name は英語のまま=MTGA用）
            e["jp"] = jp.get(e["name"])
        decks.append({
            "title": spec["title"],
            "theme": spec["theme"],
            "archetype": d.get("archetype", ""),
            "strategy": d.get("strategy", ""),
            "colors": d.get("colors", ""),
            "total": d.get("total", 0),
            "maindeck": main,
            "mtga": d.get("mtga", ""),
            "fixed": d.get("_fixed", ""),
        })
        print(f"  → {d.get('archetype')} ({d.get('total')}枚)")

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "snapshot": snapshot,
        "meta_aware": bool(meta_context),
        "decks": decks,
    }
    jp.save()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n書き出し: {OUT}（{len(decks)} デッキ）")


if __name__ == "__main__":
    main()
