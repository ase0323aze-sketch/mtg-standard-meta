# mtg_deckgen — Gemini に MTG スタンダードデッキを組ませるパイプライン

MTGJSON のカードプールを Gemini API に渡し、スタンダードのデッキを自動生成する。
生成結果は「実在カードか」「60枚ちょうどか」を機械的に検証してから MTGA 貼り付け形式で出力する。

## 構成
| ファイル | 役割 |
|---|---|
| `cardpool.py` | デスクトップの `mtg/*.json`（MTGJSON セット別ファイル）からスタンダード合法・全色のカードプールを構築。重複排除・基本土地/トークン除外。Excel/JSON 出力も可 |
| `build_deck.py` | カードプール＋お題を Gemini に渡してデッキ生成→検証→再試行→自動修復→MTGA 形式出力 |

## セットアップ
```powershell
# 依存はすでに venv に入っている。キーは keiba_prediction/.env から流用済み（mtg_deckgen/.env）
.\venv\Scripts\python.exe build_deck.py --theme "現環境で最強の全色デッキ"
```

`GEMINI_API_KEY` は `.env` から読む（競馬予想プロジェクトと同じ作法）。

## 使い方
```powershell
# 色制限なし（全4170枚から）
.\venv\Scripts\python.exe build_deck.py --theme "環境最強の完成されたデッキ"

# 色を絞る
.\venv\Scripts\python.exe build_deck.py --colors B  --theme "黒単ハンデス"
.\venv\Scripts\python.exe build_deck.py --colors UR --theme "イゼット果敢に有利を取るテンポ"

# 賢いモデルで（枚数ミス・幻覚が減る）
.\venv\Scripts\python.exe build_deck.py --model gemini-2.5-pro --theme "ローグ好み・ワンショットコンボ"

# カードプールを Excel / JSON で書き出す（他AIへの手渡し用）
.\venv\Scripts\python.exe cardpool.py --excel --json
```

出力は標準出力＋ `out_deck.txt`（MTGA の「デッキのインポート」にそのまま貼れる）。

## 検証・修復の仕組み
1. Gemini に JSON でデッキを返させる
2. `validate()` で「プールに実在するカードか」「同名4枚以下か」「合計60枚か」を判定
3. NG なら具体的なフィードバック（「63枚→3枚削れ」「存在しないカードを置換せよ」）を付けて再試行
4. それでもダメなら `auto_fix()` が幻覚カードを除去＋基本土地で60枚に補正し、必ず合法なリストを出す

## データについて
- カードプールは `mtg/*.json` の `legalities.standard == "Legal"` を信頼している。
  MTGJSON のファイルが古いと判定がズレることがある（新弾直後など）。
- BLB（ブルームバロウ）の JSON が未取得。Bandit's Talent 等を使いたい場合は
  `https://mtgjson.com/api/v5/BLB.json` を `mtg/` に追加すれば自動で取り込まれる。

## 今後の拡張案
- 複数デッキを一括生成してログ化（Claude案 vs Gemini案の自動比較・採点）
- マッチアップ相性の自動評価
- サイドボード生成（現状はメイン60枚のみ。BO1前提なら不要）
