"""
カードプールを Gemini に渡して 60 枚のスタンダードデッキを構築させる。

競馬予想プロジェクトと同じ作法:
    from google import genai
    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    model  = "gemini-2.5-flash"

Gemini には JSON でデッキを返させ、こちらで「実在カードか」「枚数が正しいか」を
検証してから MTGA 貼り付け形式に変換する。存在しないカード・60枚未満は弾く。

使い方:
    python build_deck.py --theme "環境最強の全色デッキ"
    python build_deck.py --colors B --theme "黒単ハンデス"
    python build_deck.py --colors UR --theme "イゼット果敢に有利を取れるテンポ"
    python build_deck.py --model gemini-2.5-pro --theme "ローグ好み・ワンショットコンボ"
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types

from cardpool import load_pool, filter_pool, Card

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

DEFAULT_MODEL = "gemini-2.5-flash"
DECK_SIZE = 60
MAX_COPIES = 4  # 基本土地以外は 4 枚まで


def get_client() -> genai.Client:
    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise SystemExit(
            "GEMINI_API_KEY が設定されていません。"
            ".env に GEMINI_API_KEY=your_key を追加してください。"
        )
    return genai.Client(api_key=api_key)


def pool_to_prompt_block(pool: list[Card]) -> str:
    """カードプールを Gemini に渡すコンパクトなテキストにする。"""
    lines = []
    for c in pool:
        cost = c.mana_cost or "—"
        lines.append(f"{c.name} | {cost} | {c.type_line} | {c.text}")
    return "\n".join(lines)


BASIC_LANDS = {"Swamp", "Island", "Plains", "Mountain", "Forest", "Wastes"}


def build_prompt(theme: str, colors: str | None, pool: list[Card],
                 meta_context: str = "") -> str:
    color_line = f"使用色: {colors}（この色のみ）" if colors else "使用色: 制限なし（全色可）"
    meta_block = ""
    if meta_context:
        meta_block = (f"\n{meta_context}\n"
                      "↑ これが現環境の主要デッキです。これらに有利を取れる（または明確な"
                      "勝ち筋で上回れる）ことを意識して構築してください。\n")
    return f"""あなたは MTG スタンダードのトッププロのデッキビルダーです。
以下のカードプール（スタンダード合法・実在するカードのみ）から、{DECK_SIZE}枚ちょうどの
構築済みデッキを 1 つ作ってください。

# お題
{theme}
{color_line}
{meta_block}

# 厳守するルール
- 合計ちょうど {DECK_SIZE} 枚（土地を含む）。59枚や56枚は不可。
- 基本土地（Swamp/Island/Plains/Mountain/Forest）以外は同名 {MAX_COPIES} 枚まで。
- カード名は下のプールに存在する英語名と完全一致させること。存在しないカードは絶対に使わない。
- 土地は十分な枚数（通常 22〜26 枚程度）を入れること。

# 出力形式（厳守・JSON のみ。前後に文章を付けない）
# archetype と strategy は必ず日本語で書く。ただし maindeck の name は英語のまま。
{{
  "archetype": "デッキ名（日本語。例: ディミーア・コントロール）",
  "strategy": "このデッキの勝ち筋・戦い方・現環境への強みを日本語で3〜4文で分かりやすく",
  "maindeck": [
    {{"name": "カード名(英語・プールと完全一致)", "count": 4}},
    ...
  ]
}}

# 使用可能なカードプール（名前 | マナコスト | タイプ | テキスト）
{pool_to_prompt_block(pool)}
"""


def call_gemini(client: genai.Client, model: str, prompt: str) -> dict:
    resp = client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0.9,
            response_mime_type="application/json",
        ),
    )
    return json.loads(resp.text)


def validate(deck: dict, pool: list[Card]) -> tuple[bool, list[str]]:
    """デッキを検証し、(妥当か, 問題リスト) を返す。"""
    problems: list[str] = []
    names = {c.name for c in pool}
    main = deck.get("maindeck", [])

    total = 0
    seen: Counter[str] = Counter()
    for entry in main:
        name = entry.get("name", "")
        count = int(entry.get("count", 0))
        total += count
        seen[name] += count
        if name not in names and name not in BASIC_LANDS:
            problems.append(f"プールに存在しないカード: {name!r}")
        if name not in BASIC_LANDS and count > MAX_COPIES:
            problems.append(f"{name}: {count} 枚（上限 {MAX_COPIES} 超過）")

    if total != DECK_SIZE:
        problems.append(f"合計 {total} 枚（{DECK_SIZE} 枚であるべき）")

    return (len(problems) == 0), problems


def feedback_for(problems: list[str], total: int) -> str:
    """再試行用の明確で方向性のあるフィードバックを作る（累積させない）。"""
    msg = ["# 前回の問題（必ず直すこと）"] + [f"- {p}" for p in problems]
    if any("存在しない" in p for p in problems):
        msg.append("→ 存在しないカードは使うな。プールに完全一致する英語名のカードだけを使え。"
                   "怪しければそのカードを諦め、確実にプールにある別カードに置き換えよ。")
    if total > DECK_SIZE:
        msg.append(f"→ あなたは {total} 枚提出した。ちょうど {total - DECK_SIZE} 枚を削って 60 枚にせよ。")
    elif total < DECK_SIZE:
        msg.append(f"→ あなたは {total} 枚しか提出していない。ちょうど {DECK_SIZE - total} 枚（多くは土地）を足して 60 枚にせよ。")
    return "\n".join(msg)


def auto_fix(deck: dict, pool: list[Card]) -> dict:
    """最終手段: 実在しないカードを除去し、土地で 60 枚に補正して必ず合法化する。"""
    names = {c.name for c in pool}
    removed = []
    kept = []
    for e in deck.get("maindeck", []):
        if e.get("name") in names or e.get("name") in BASIC_LANDS:
            kept.append(e)
        else:
            removed.append(f"{e.get('name')} x{e.get('count')}")
    deck["maindeck"] = kept
    notes = []
    if removed:
        notes.append("存在しないカードを除去: " + ", ".join(removed))
    deck = normalize_to_60(deck)
    if deck.get("_normalized"):
        notes.append(deck["_normalized"])
    deck["_fixed"] = " / ".join(notes) if notes else ""
    return deck


def total_cards(deck: dict) -> int:
    return sum(int(e.get("count", 0)) for e in deck.get("maindeck", []))


def normalize_to_60(deck: dict) -> dict:
    """最終手段: 合計を 60 枚ちょうどに合わせる。
    多すぎる場合は 基本土地(多い順)→その他(多い順) の順に削る（基本土地が無くても必ず60枚に届く）。
    少なすぎる場合は基本土地を増やす。"""
    main = deck.get("maindeck", [])
    delta = total_cards(deck) - DECK_SIZE
    if delta == 0:
        return deck
    if delta > 0:                                  # 多い → 削る
        order = sorted(main, key=lambda e: (e.get("name") not in BASIC_LANDS, -int(e.get("count", 0))))
        for e in order:
            if delta <= 0:
                break
            cut = min(delta, int(e.get("count", 0)))
            e["count"] = int(e.get("count", 0)) - cut
            delta -= cut
        deck["maindeck"] = [e for e in main if int(e.get("count", 0)) > 0]
    else:                                          # 少ない → 基本土地を足す
        basics = [e for e in main if e.get("name") in BASIC_LANDS]
        if basics:
            max(basics, key=lambda e: e["count"])["count"] += -delta
        else:
            main.append({"name": "Wastes", "count": -delta})
    deck["_normalized"] = f"枚数を調整して {DECK_SIZE} 枚に補正"
    return deck


def to_mtga(deck: dict) -> str:
    lines = ["Deck"]
    for entry in deck.get("maindeck", []):
        if int(entry.get("count", 0)) > 0:
            lines.append(f"{entry['count']} {entry['name']}")
    return "\n".join(lines)


def generate_deck(client, pool: list[Card], theme: str, colors: str | None = None,
                  model: str = DEFAULT_MODEL, retries: int = 2,
                  meta_context: str = "", verbose: bool = True) -> dict:
    """1 つのデッキを生成し、検証・自動修復まで済ませた deck dict を返す。
    main() と build_showcase.py の共通エンジン。"""
    base_prompt = build_prompt(theme, colors, pool, meta_context)
    deck, prompt = None, base_prompt
    for attempt in range(1, retries + 2):
        if verbose:
            print(f"  [{attempt}回目] {model} 構築中...")
        deck = call_gemini(client, model, prompt)
        ok, problems = validate(deck, pool)
        if ok:
            break
        if verbose:
            print("  検証NG: " + "; ".join(problems))
        prompt = base_prompt + "\n\n" + feedback_for(problems, total_cards(deck))
    else:
        deck = auto_fix(deck, pool)
    deck.setdefault("theme", theme)
    deck["mtga"] = to_mtga(deck)
    deck["total"] = total_cards(deck)
    return deck


def main() -> None:
    ap = argparse.ArgumentParser(description="Gemini にスタンダードデッキを組ませる")
    ap.add_argument("--theme", required=True, help="デッキのお題")
    ap.add_argument("--colors", help="使用色を制限（例: B, UR, BUG）")
    ap.add_argument("--model", default=DEFAULT_MODEL, help=f"モデル（既定 {DEFAULT_MODEL}）")
    ap.add_argument("--retries", type=int, default=2, help="検証失敗時の再試行回数")
    ap.add_argument("--vs-meta", action="store_true",
                    help="収集済みの現環境メタを注入し、上位デッキに有利な構築にする")
    args = ap.parse_args()

    pool = filter_pool(load_pool(), args.colors)
    print(f"カードプール: {len(pool)} 枚 / お題: {args.theme}")

    meta_context = ""
    if args.vs_meta:
        import analyze
        import store
        conn = store.connect()
        meta_context = analyze.meta_context_text(conn)
        conn.close()
        if meta_context:
            print("現メタを注入:\n" + meta_context)
        else:
            print("※ メタデータ未収集。先に collect_runner を実行してください（通常生成で続行）")

    client = get_client()
    deck = generate_deck(client, pool, args.theme, args.colors,
                         args.model, args.retries, meta_context)

    print("\n" + "=" * 50)
    print(f"アーキタイプ: {deck.get('archetype')}")
    print(f"勝ち筋: {deck.get('strategy')}")
    if deck.get("_fixed"):
        print(f"自動修復: {deck['_fixed']}")
    print(f"合計: {deck['total']} 枚")
    print("=" * 50)
    print(deck["mtga"])

    out = Path(__file__).parent / "out_deck.txt"
    out.write_text(deck["mtga"], encoding="utf-8")
    print(f"\nMTGA 貼り付け用を書き出し: {out}")


if __name__ == "__main__":
    main()
