"""収集したデッキを SQLite に保存する。

スナップショット方式: 同じデッキでも collected_at（収集日）が違えば別行として残す。
これにより「2026-06-01 と 2026-06-15 でメタがどう動いたか」を後から解析できる。
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from collect.base import DeckRecord

DB_PATH = Path(__file__).parent / "decks.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS decks (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    source        TEXT NOT NULL,
    source_deck_id TEXT NOT NULL,
    name          TEXT,
    archetype     TEXT,
    colors        TEXT,
    fmt           TEXT,
    url           TEXT,
    event         TEXT,
    event_date    TEXT,
    placement     TEXT,
    meta_share    REAL,
    win_rate      REAL,
    collected_at  TEXT NOT NULL,
    UNIQUE(source, source_deck_id, collected_at)
);
CREATE TABLE IF NOT EXISTS deck_cards (
    deck_id   INTEGER NOT NULL REFERENCES decks(id) ON DELETE CASCADE,
    quantity  INTEGER NOT NULL,
    name      TEXT NOT NULL,
    board     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_decks_collected ON decks(collected_at);
CREATE INDEX IF NOT EXISTS idx_decks_archetype ON decks(archetype);
CREATE INDEX IF NOT EXISTS idx_cards_name ON deck_cards(name);
"""


def connect(path: Path = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    return conn


def save_deck(conn: sqlite3.Connection, rec: DeckRecord) -> bool:
    """デッキを 1 件保存する。同一 (source, id, collected_at) は重複として無視。
    返り値: 新規保存できたら True。"""
    cur = conn.execute(
        """INSERT OR IGNORE INTO decks
           (source, source_deck_id, name, archetype, colors, fmt, url,
            event, event_date, placement, meta_share, win_rate, collected_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (rec.source, rec.source_deck_id, rec.name, rec.archetype, rec.colors,
         rec.fmt, rec.url, rec.event, rec.event_date, rec.placement,
         rec.meta_share, rec.win_rate, rec.collected_at),
    )
    if cur.rowcount == 0:
        return False  # 既に同日収集済み
    deck_id = cur.lastrowid
    conn.executemany(
        "INSERT INTO deck_cards (deck_id, quantity, name, board) VALUES (?,?,?,?)",
        [(deck_id, q, n, b) for q, n, b in rec.cards],
    )
    conn.commit()
    return True


def save_many(conn: sqlite3.Connection, recs: list[DeckRecord]) -> tuple[int, int]:
    """複数保存。(新規, スキップ) を返す。"""
    new = skipped = 0
    for r in recs:
        if save_deck(conn, r):
            new += 1
        else:
            skipped += 1
    return new, skipped


def stats(conn: sqlite3.Connection) -> str:
    total = conn.execute("SELECT COUNT(*) FROM decks").fetchone()[0]
    by_src = conn.execute(
        "SELECT source, COUNT(*) FROM decks GROUP BY source ORDER BY 2 DESC"
    ).fetchall()
    by_day = conn.execute(
        "SELECT collected_at, COUNT(*) FROM decks GROUP BY collected_at ORDER BY 1 DESC LIMIT 5"
    ).fetchall()
    lines = [f"保存デッキ総数: {total}"]
    lines.append("  source別: " + ", ".join(f"{s}={n}" for s, n in by_src))
    lines.append("  収集日別: " + ", ".join(f"{d}={n}" for d, n in by_day))
    return "\n".join(lines)
