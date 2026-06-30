"""MTGTop8 アダプタ: 大会上位デッキを収集する（メタ品質の本命）。

robots.txt なし・サーバ描画 HTML。format ページ→イベント→デッキの順にたどる。
- アーキタイプ名はサイトがラベル付けしている（例: "Izzet Prowess"）のでそれを使う
- デッキリストの行（div.deck_line）はカード行と順位表の両方に使われるため、
  カード名をローカルのカードプールと照合して確実に分離する
- サイドボード境界は div.O14 の "SIDEBOARD" マーカーで判定する
"""
from __future__ import annotations

import re
import time

import requests
from bs4 import BeautifulSoup

from collect.base import DeckRecord, USER_AGENT, normalize_colors, BASIC_LANDS
from cardpool import load_pool

BASE = "https://www.mtgtop8.com/"
FORMAT_URL = BASE + "format?f=ST"
REQUEST_GAP = 1.0

_CARD_LINE = re.compile(r"^(\d{1,2})\s+(.*)$")

# カード名→色（プールから1回だけ構築）
_POOL_COLORS: dict[str, str] | None = None
_POOL_NAMES: set[str] | None = None


def _pool():
    global _POOL_COLORS, _POOL_NAMES
    if _POOL_COLORS is None:
        pool = load_pool()
        _POOL_COLORS = {c.name: c.colors for c in pool}
        _POOL_NAMES = set(_POOL_COLORS)
    return _POOL_COLORS, _POOL_NAMES


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT})
    return s


def _event_ids(sess: requests.Session, max_events: int) -> list[str]:
    r = sess.get(FORMAT_URL, timeout=25)
    soup = BeautifulSoup(r.text, "lxml")
    ids: list[str] = []
    for a in soup.find_all("a", href=True):
        m = re.search(r"event\?e=(\d+)", a["href"])
        if m and m.group(1) not in ids:
            ids.append(m.group(1))
        if len(ids) >= max_events:
            break
    return ids


def _event_decks(sess: requests.Session, event_id: str) -> list[tuple[str, str]]:
    """(deck_id, archetype) の一覧を返す。"""
    r = sess.get(f"{BASE}event?e={event_id}&f=ST", timeout=25)
    soup = BeautifulSoup(r.text, "lxml")
    seen: dict[str, str] = {}
    for a in soup.find_all("a", href=True):
        m = re.search(r"[?&]d=(\d+)", a["href"])
        text = a.get_text(strip=True)
        if m and text and text != "→":
            seen.setdefault(m.group(1), text)
    return list(seen.items())


def _deck_cards(sess: requests.Session, event_id: str, deck_id: str):
    """デッキの (cards, colors) を返す。cards は [(qty, name, board)]。"""
    _, names = _pool()
    colors_map, _ = _pool()
    r = sess.get(f"{BASE}event?e={event_id}&d={deck_id}&f=ST", timeout=25)
    soup = BeautifulSoup(r.text, "lxml")
    cards: list[tuple[int, str, str]] = []
    board = "main"
    color_set: set[str] = set()
    # deck_line（カード行）と O14（SIDEBOARD 見出し）を文書順に走査
    for el in soup.find_all("div", class_=["deck_line", "O14"]):
        classes = el.get("class") or []
        if "O14" in classes and "SIDEBOARD" in el.get_text(" ", strip=True).upper():
            board = "side"
            continue
        if "deck_line" not in classes:
            continue
        t = el.get_text(" ", strip=True)
        m = _CARD_LINE.match(t)
        if not m:
            continue
        name = m.group(2).strip()
        if name in names or name in BASIC_LANDS:
            qty = int(m.group(1))
            cards.append((qty, name, board))
            if board == "main":
                color_set.update(colors_map.get(name, ""))
    return cards, normalize_colors(color_set)


def collect(limit: int = 30, max_events: int = 8) -> list[DeckRecord]:
    sess = _session()
    out: list[DeckRecord] = []
    for event_id in _event_ids(sess, max_events):
        time.sleep(REQUEST_GAP)
        for deck_id, archetype in _event_decks(sess, event_id):
            if len(out) >= limit:
                return out
            time.sleep(REQUEST_GAP)
            cards, colors = _deck_cards(sess, event_id, deck_id)
            main = sum(q for q, _, b in cards if b == "main")
            if main < 60:
                continue  # 取得失敗 or 不完全
            rec = DeckRecord(
                source="mtgtop8",
                source_deck_id=f"{event_id}-{deck_id}",
                name=archetype,
                colors=colors,
                url=f"{BASE}event?e={event_id}&d={deck_id}&f=ST",
                archetype=archetype,
                event=event_id,
                cards=cards,
            )
            out.append(rec)
            print(f"  [mtgtop8] {len(out)}/{limit} {colors:<5} {archetype[:30]:<30} main={main}")
    return out
