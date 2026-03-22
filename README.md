# 宮古島市議会 議事録処理システム

宮古島市議会の議事録PDFをダウンロードし、テキスト抽出・分析・AI検索用データ構築を行うスクリプト群。

---

## パイプライン概要

```
0_download.py
│  → gijiroku/*.pdf
│
1_extract_text.py
│  → gijiroku_all.txt（全会期結合テキスト）
│
├─ 2_extract_features.py
│     → features.json（会期ごとのTF-IDFキーワード）
│
├─ 3_upload_vectorstore.py
│     → vectorstore_id.txt（OpenAI Vector Store ID）
│
├─ 4_split_sessions.py
│  │  → sessions/*.txt（会期ごとのテキストファイル）
│  │
│  └─ 5_upload_sessions.py
│        → miyako-file-ids.json（会期名 → OpenAI file_id マッピング）
│
└─ analyze_speakers.py（議員マスタ + gijiroku_all.txt を入力）
      → output/speakers_meta.json（発話者統計）
      → output/tfidf_words.csv（発話者×単語 TF-IDF）
      → output/tfidf_categories.csv（発話者×カテゴリ TF-IDF）
```

---

## ファイル構成

```
miyako/
├── 0_download.py            # PDFダウンロード
├── 1_extract_text.py        # テキスト抽出
├── 2_extract_features.py    # TF-IDF特徴量抽出
├── 3_upload_vectorstore.py  # Vector Storeアップロード
├── 4_split_sessions.py      # 会期ごとに分割
├── 5_upload_sessions.py     # 会期ファイルをOpenAIにアップロード
├── analyze_speakers.py      # 発話者分析
│
├── gijiroku/                # ダウンロードしたPDF（.gitignore対象）
├── sessions/                # 会期ごとのテキストファイル（.gitignore対象）
└── output/                  # 生成ファイル（.gitignore対象）
    ├── gijiroku_all.txt                         ← 1_extract_text.py
    ├── features.json                            ← 2_extract_features.py
    ├── vectorstore_id.txt                       ← 3_upload_vectorstore.py
    ├── miyako-file-ids.json                     ← 5_upload_sessions.py
    ├── speakers_meta.json                       ← analyze_speakers.py
    ├── tfidf_words.csv                          ← analyze_speakers.py
    ├── tfidf_categories.csv                     ← analyze_speakers.py
    └── miyakojima_council_members_20years.json  # 入力ファイル（手動配置）
```

---

## 各スクリプトの説明

### `0_download.py`
宮古島市の公式サイトから議事録PDFを一括ダウンロードする。

- 取得先: `https://www.city.miyakojima.lg.jp/gyosei/gikai/gijiroku.html`
- サーバー負荷軽減のため1秒間隔でダウンロード

### `1_extract_text.py`
PDFからテキストを抽出し、全会期を1ファイルに結合する。

- スキャンPDF（テキスト取得不可）は自動スキップ
- 元号（令和・平成・昭和等）を西暦に変換してヘッダーを付与

**出力フォーマット:**
```
==== 令和5年 第4回 定例会 2023-09-04〜2023-09-22 ====
（本文テキスト）
```

### `2_extract_features.py`
`gijiroku_all.txt` から会期ごとのTF-IDF特徴語を抽出する。

- 形態素解析: [Fugashi](https://github.com/polm/fugashi) + UniDic
- 議会用ストップワード（「議員」「質問」「答弁」等）を除外
- 各会期の上位30キーワードを抽出

### `3_upload_vectorstore.py`
`gijiroku_all.txt` をOpenAI Vector Storeにアップロードする。

- 環境変数 `OPENAI_API_KEY` が必要

### `4_split_sessions.py`
`gijiroku_all.txt` を会期ごとの個別ファイルに分割する。

- `==== ... ====` ヘッダーを区切りとして分割
- ファイル名例: `R5-4-定例会_2023-09-04.txt`

### `5_upload_sessions.py`
`sessions/` 内の会期ファイルをOpenAI Files APIへアップロードし、Vector Storeに追加する。

- すでにアップロード済みの会期はスキップ（再実行対応）
- 環境変数 `OPENAI_API_KEY` が必要

### `analyze_speakers.py`
議事録テキストを発話者ごとに集計し、TF-IDFで各議員の関心テーマを分析する。

- `gijiroku_all.txt` と `miyakojima_council_members_20years.json`（議員プロフィール）を入力
- 13カテゴリ（環境・防災、農業・水産業、観光 等）でスコアを集計
- **プロジェクトルートから実行すること**（相対パスを使用）

---

## セットアップ

```bash
pip install pymupdf fugashi unidic-lite requests beautifulsoup4 openai
```

OpenAI APIを使う場合:
```bash
export OPENAI_API_KEY="sk-..."
```

---

## 実行手順

```bash
python3 0_download.py
python3 1_extract_text.py
python3 2_extract_features.py
python3 3_upload_vectorstore.py
python3 4_split_sessions.py
python3 5_upload_sessions.py

# 発話者分析（別途実行）
python3 analyze_speakers.py
```
