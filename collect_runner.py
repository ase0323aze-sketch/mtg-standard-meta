"""収集ランナー: 有効な各ソースからデッキを集めて SQLite に保存する。

Windows タスクスケジューラから毎月1日・15日に呼ばれる想定のエントリポイント。

    python collect_runner.py                 # 全ソース既定件数
    python collect_runner.py --source moxfield --limit 50
"""
from __future__ import annotations

import argparse
import sys
import traceback

import store
from collect import moxfield, mtgtop8

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# 利用可能なソース。今後 goldfish / hareruya / untapped を追加していく。
SOURCES = {
    "mtgtop8": mtgtop8.collect,
    "moxfield": moxfield.collect,
}


def main() -> None:
    ap = argparse.ArgumentParser(description="デッキ収集ランナー")
    ap.add_argument("--source", choices=list(SOURCES) + ["all"], default="all")
    ap.add_argument("--limit", type=int, default=30, help="ソースあたりの収集件数")
    args = ap.parse_args()

    targets = SOURCES if args.source == "all" else {args.source: SOURCES[args.source]}
    conn = store.connect()

    for name, fn in targets.items():
        print(f"\n=== {name} 収集開始（最大 {args.limit} 件） ===")
        try:
            recs = fn(limit=args.limit)
            new, skipped = store.save_many(conn, recs)
            print(f"  → 取得 {len(recs)} / 新規保存 {new} / 既存スキップ {skipped}")
        except Exception:
            print(f"  [{name}] 収集中に例外:")
            traceback.print_exc()

    print("\n" + store.stats(conn))
    conn.close()


if __name__ == "__main__":
    main()
