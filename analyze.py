"""収集済みデッキを解析する（機能2）。

- アーキタイプ別シェア（メタ占有率の代理指標）
- 収集日スナップショット間のトレンド（シェアの増減）
- アーキタイプ別/全体の主要カード（staples）
- 解析結果を Web ビューア用 JSON (docs/data/meta.json) に書き出す

勝率について: MTGTop8 は「上位入賞での出現率」は分かるが真の勝率は持たない。
真の勝率はランク戦データ（Untapped.gg）が必要で現状未対応。ここでは
"メタ占有率（上位デッキ中の割合）" を提示する。
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import store

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

WEB_JSON = Path(__file__).parent / "docs" / "data" / "meta.json"
DEFAULT_SOURCE = "mtgtop8"  # 解析の主軸は大会データ。moxfield はノイズが多いので既定で除外


def _latest_snapshot(conn, source: str) -> str | None:
    row = conn.execute(
        "SELECT MAX(collected_at) FROM decks WHERE source=?", (source,)
    ).fetchone()
    return row[0] if row else None


def archetype_share(conn, source: str, collected_at: str) -> list[dict]:
    rows = conn.execute(
        """SELECT archetype, colors, COUNT(*) AS n
           FROM decks WHERE source=? AND collected_at=?
           GROUP BY archetype ORDER BY n DESC""",
        (source, collected_at),
    ).fetchall()
    total = sum(n for *_, n in rows) or 1
    return [
        {"archetype": a, "colors": c, "count": n, "share": round(100 * n / total, 1)}
        for a, c, n in rows
    ]


def staples(conn, source: str, collected_at: str, archetype: str | None = None,
            top: int = 15) -> list[dict]:
    """主要カード（基本土地を除く、メインデッキの採用デッキ数順）。"""
    q = """SELECT dc.name, COUNT(DISTINCT d.id) AS decks, SUM(dc.quantity) AS copies
           FROM deck_cards dc JOIN decks d ON d.id = dc.deck_id
           WHERE d.source=? AND d.collected_at=? AND dc.board='main'
             AND dc.name NOT IN ('Swamp','Island','Plains','Mountain','Forest')"""
    params = [source, collected_at]
    if archetype:
        q += " AND d.archetype=?"
        params.append(archetype)
    q += " GROUP BY dc.name ORDER BY decks DESC, copies DESC LIMIT ?"
    params.append(top)
    return [{"name": n, "decks": d, "copies": c}
            for n, d, c in conn.execute(q, params).fetchall()]


def trend(conn, source: str) -> dict:
    """収集日ごとのアーキタイプ件数（シェアの推移）。"""
    rows = conn.execute(
        """SELECT collected_at, archetype, COUNT(*) FROM decks
           WHERE source=? GROUP BY collected_at, archetype
           ORDER BY collected_at""",
        (source,),
    ).fetchall()
    by_day: dict[str, dict[str, int]] = defaultdict(dict)
    for day, arch, n in rows:
        by_day[day][arch] = n
    return by_day


def build_web_payload(conn, source: str) -> dict:
    from jpnames import JpNames
    jp = JpNames()

    def with_jp(lst: list[dict]) -> list[dict]:
        for s in lst:
            s["jp"] = jp.get(s["name"])
        return lst

    snap = _latest_snapshot(conn, source)
    shares = archetype_share(conn, source, snap) if snap else []
    archetypes = []
    for s in shares:
        decks = conn.execute(
            "SELECT url, event FROM decks WHERE source=? AND collected_at=? AND archetype=?",
            (source, snap, s["archetype"]),
        ).fetchall()
        archetypes.append({
            **s,
            "staples": with_jp(staples(conn, source, snap, s["archetype"], top=8)),
            "decks": [{"url": u, "event": e} for u, e in decks],
        })
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": source,
        "snapshot": snap,
        "total_decks": sum(s["count"] for s in shares),
        "archetypes": archetypes,
        "overall_staples": with_jp(staples(conn, source, snap, None, top=20)) if snap else [],
        "trend": trend(conn, source),
    }
    jp.save()
    return payload


def meta_context_text(conn, source: str = DEFAULT_SOURCE, top: int = 6) -> str:
    """デッキ生成プロンプトに差し込む現環境メタの要約テキストを返す。"""
    snap = _latest_snapshot(conn, source)
    if not snap:
        return ""
    shares = archetype_share(conn, source, snap)[:top]
    lines = [f"# 現在のスタンダード上位メタ（{snap} 時点 / 出典 {source} / 大会上位デッキ）"]
    for s in shares:
        st = staples(conn, source, snap, s["archetype"], top=5)
        names = ", ".join(c["name"] for c in st)
        lines.append(f"- {s['archetype']}（{s['colors']}）{s['share']}%  主要カード: {names}")
    return "\n".join(lines)


def print_summary(conn, source: str) -> None:
    snap = _latest_snapshot(conn, source)
    if not snap:
        print(f"{source} のデータがありません。先に collect_runner を実行してください。")
        return
    print(f"=== {source} メタ解析（{snap}） ===")
    shares = archetype_share(conn, source, snap)
    print(f"対象デッキ数: {sum(s['count'] for s in shares)}\n")
    print("アーキタイプ別シェア:")
    for s in shares:
        bar = "█" * int(s["share"] / 3)
        print(f"  {s['share']:4.1f}%  {s['colors']:<5} {s['archetype']:<22} ({s['count']}) {bar}")
    print("\n主要カード（採用デッキ数）:")
    for c in staples(conn, source, snap, None, top=15):
        print(f"  {c['decks']:2d}デッキ  {c['name']}")


def main() -> None:
    ap = argparse.ArgumentParser(description="メタ解析")
    ap.add_argument("--source", default=DEFAULT_SOURCE)
    ap.add_argument("--json", action="store_true", help="docs/data/meta.json に書き出す")
    args = ap.parse_args()

    conn = store.connect()
    print_summary(conn, args.source)
    if args.json:
        WEB_JSON.parent.mkdir(parents=True, exist_ok=True)
        payload = build_web_payload(conn, args.source)
        WEB_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nWeb 用 JSON を書き出し: {WEB_JSON}")
    conn.close()


if __name__ == "__main__":
    main()
