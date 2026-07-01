"""公式日本語カード名の解決。

まず jp_names.json（MTGJSON foreignData 由来）を引き、無いものだけ Scryfall の
日本語印刷から補完してキャッシュする。日本語版が存在しないカードは英語名で返す。

    from jpnames import JpNames
    jp = JpNames()
    jp.get("Steam Vents")   # -> "蒸気孔"
    jp.save()               # 追記分を jp_names.json に永続化
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import requests

MAP_PATH = Path(__file__).parent / "jp_names.json"
UA = "mtg-deckgen/0.1 (personal hobby deck research)"
SCRYFALL = "https://api.scryfall.com/cards/search"


class JpNames:
    def __init__(self, online: bool = True):
        self.m: dict[str, str] = {}
        if MAP_PATH.exists():
            self.m = json.loads(MAP_PATH.read_text(encoding="utf-8"))
        self.online = online
        self.dirty = False

    def get(self, name: str) -> str:
        """公式日本語名を返す。無ければ英語名を返す。"""
        if name in self.m:
            return self.m[name]
        jp = self._scryfall(name) if self.online else None
        self.m[name] = jp or name          # 見つからなければ英語名をキャッシュ（再問い合わせ防止）
        self.dirty = True
        return self.m[name]

    def _scryfall(self, name: str) -> str | None:
        try:
            time.sleep(0.12)               # Scryfall への礼儀（~10req/s 制限）
            r = requests.get(
                SCRYFALL,
                params={"q": f'!"{name}" lang:ja'},
                headers={"User-Agent": UA, "Accept": "application/json"},
                timeout=15,
            )
            if r.status_code != 200:
                return None
            data = r.json().get("data", [])
            return data[0].get("printed_name") if data else None
        except Exception:
            return None

    def save(self) -> None:
        if self.dirty:
            MAP_PATH.write_text(
                json.dumps(self.m, ensure_ascii=False, indent=0), encoding="utf-8"
            )
            self.dirty = False
