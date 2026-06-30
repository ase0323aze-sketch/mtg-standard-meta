"""Moxfield アダプタ: 公開 API でスタンダードのデッキを収集する。

robots.txt は /swagger のみ Disallow。検索 API と公開デッキ取得は許可されている。
個人利用・低頻度（月2回）・リクエスト間にウェイトを入れて礼儀正しくアクセスする。
"""
from __future__ import annotations

import time

import requests

from collect.base import DeckRecord, USER_AGENT, normalize_colors, guess_archetype

SEARCH_URL = "https://api2.moxfield.com/v2/decks/search"
DECK_URL = "https://api2.moxfield.com/v3/decks/all/{id}"
REQUEST_GAP = 0.8  # 秒。連続リクエストの間隔


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json"})
    return s


def _fetch_deck(sess: requests.Session, public_id: str) -> DeckRecord | None:
    r = sess.get(DECK_URL.format(id=public_id), timeout=25)
    if r.status_code != 200:
        return None
    d = r.json()
    boards = d.get("boards", {})
    cards: list[tuple[int, str, str]] = []
    for board_key, board_name in (("mainboard", "main"), ("sideboard", "side")):
        for entry in boards.get(board_key, {}).get("cards", {}).values():
            q = int(entry.get("quantity", 0))
            name = entry.get("card", {}).get("name")
            if q and name:
                cards.append((q, name, board_name))
    if not cards:
        return None
    colors = normalize_colors(d.get("colorIdentity", []) or [])
    name = d.get("name", "(no name)")
    return DeckRecord(
        source="moxfield",
        source_deck_id=public_id,
        name=name,
        colors=colors,
        fmt=d.get("format", "standard"),
        url=f"https://moxfield.com/decks/{public_id}",
        archetype=guess_archetype(colors, name, d.get("hubs") or None),
        event_date=(d.get("lastUpdatedAtUtc") or "")[:10] or None,
        cards=cards,
    )


def collect(limit: int = 30, page_size: int = 32) -> list[DeckRecord]:
    """更新日時の新しい順にスタンダードデッキを limit 件収集する。
    60 枚ちょうど（正規構築）のものだけ残す。"""
    sess = _session()
    out: list[DeckRecord] = []
    page = 1
    while len(out) < limit:
        r = sess.get(
            SEARCH_URL,
            params={"fmt": "standard", "pageSize": page_size, "pageNumber": page,
                    "sortType": "updated", "sortDirection": "Descending"},
            timeout=25,
        )
        if r.status_code != 200:
            print(f"  [moxfield] 検索失敗 status={r.status_code}")
            break
        data = r.json().get("data", [])
        if not data:
            break
        for meta in data:
            if len(out) >= limit:
                break
            if meta.get("mainboardCount") != 60:
                continue  # 構築済み60枚のみ
            time.sleep(REQUEST_GAP)
            rec = _fetch_deck(sess, meta.get("publicId"))
            if rec and rec.main_count() == 60:
                out.append(rec)
                print(f"  [moxfield] {len(out)}/{limit} {rec.archetype:<12} {rec.name[:40]}")
        page += 1
        time.sleep(REQUEST_GAP)
    return out
