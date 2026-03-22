#!/usr/bin/env python3
"""
Step 2: 全文テキストから会期別の特徴語をTF-IDFで抽出する

入力:  gijiroku_all.txt  (1_extract_text.py の出力)
出力:  features.json     (会期ごとの特徴語リスト)

使い方:
  python3 2_extract_features.py

依存:
  pip install fugashi unidic-lite scikit-learn
"""

import re
import json
import sys
from pathlib import Path
from collections import defaultdict

try:
    import fugashi
except ImportError:
    print("fugashi が必要です: pip install fugashi unidic-lite", file=sys.stderr)
    sys.exit(1)

from sklearn.feature_extraction.text import TfidfVectorizer

INPUT_PATH  = Path(__file__).parent / "gijiroku_all.txt"
OUTPUT_PATH = Path(__file__).parent / "features.json"

# 出力する特徴語の数
TOP_N = 30

# 除外する品詞（助詞・助動詞・記号・数詞など）
EXCLUDE_POS = {"助詞", "助動詞", "記号", "補助記号", "空白", "感動詞"}
# 除外する表層形（ストップワード）
STOPWORDS = {
    # 汎用動詞・形式語
    "する", "ある", "いる", "なる", "れる", "られる", "ない",
    "言う", "思う", "考える", "行う", "行なう", "関する", "おける",
    "つく", "でる", "みる", "くる", "いく", "もらう", "くれる",
    "できる", "おる", "いただく", "頂く", "ございます", "おります",
    "申し上げる", "申す", "存じる",
    # 指示語（古語含む）
    "この", "その", "あの", "これ", "それ", "あれ",
    "此れ", "其れ", "其の", "此の", "彼れ", "彼の",
    "ここ", "そこ", "あそこ", "こちら", "そちら", "あちら",
    # 形式名詞
    "こと", "もの", "ため", "よう", "わけ", "はず",
    "ところ", "とき", "場合", "方", "上", "中", "内", "以上",
    "以下", "以内", "以外", "程度", "関係", "問題", "状況",
    # 議会固有の常用語（全会期共通で出る）
    "議長", "市長", "議員", "宮古島", "宮古島市", "会議", "議会",
    "副議長", "委員", "委員会", "提案", "審議", "採決", "可決",
    "議案", "説明", "質問", "答弁", "討論", "一般質問", "定例会", "臨時会",
    "市議会", "開会", "閉会", "休憩", "再開", "賛成", "反対", "異議",
    "日程", "進行", "報告", "承認", "同意",
    # 年号・数詞ノイズ
    "元年", "年度", "今年", "来年", "昨年", "本年", "本市",
    # 記号・助詞残り
    "○", "◎", "●", "■", "□", "△", "▲", "・",
    "について", "において", "による", "ついて", "おいて", "よる",
    "及び", "並びに", "または", "あるいは", "もしくは",
}


def tokenize(text: str, tagger) -> list[str]:
    """テキストを形態素解析して名詞（普通名詞・固有名詞）のみ返す"""
    words = []
    for word in tagger(text):
        pos  = word.feature.pos1  # 品詞
        pos2 = word.feature.pos2  # 品詞細分類1
        base = word.feature.lemma or word.surface  # 原形

        # 名詞のみ（動詞・形容詞・助詞等はすべて除外）
        if pos != "名詞":
            continue
        # 非自立・接尾辞・数詞は除外
        if pos2 in {"非自立可能", "接尾辞", "数詞"}:
            continue
        if not base or len(base) < 2:
            continue
        if base in STOPWORDS:
            continue
        # 数字のみ・記号のみを除外
        if re.match(r"^[0-9０-９\s\-・]+$", base):
            continue
        # ひらがなのみを除外
        if re.match(r"^[ぁ-ん]+$", base):
            continue
        # カタカナのみ（人名読み仮名ノイズ）を除外
        if re.match(r"^[ァ-ヴー]+$", base):
            continue
        # ASCII混じり（OCRゴミ）を除外
        if re.search(r"[a-zA-Z\-]", base):
            continue
        # 元号名を除外
        if base in {"明治", "大正", "昭和", "平成", "令和"}:
            continue

        words.append(base)

    return words


def split_sessions(text: str) -> list[tuple[str, str]]:
    """
    gijiroku_all.txt を会期ごとに分割する
    returns: [(session_label, session_text), ...]
    """
    pattern = re.compile(r"(====.+?====)")
    parts   = pattern.split(text)

    sessions = []
    i = 1
    while i < len(parts) - 1:
        label   = parts[i].strip("= \n")
        content = parts[i + 1] if i + 1 < len(parts) else ""
        sessions.append((label, content))
        i += 2

    return sessions


def main():
    if not INPUT_PATH.exists():
        print(f"[ERR] {INPUT_PATH} が見つかりません。先に 1_extract_text.py を実行してください。")
        sys.exit(1)

    print("テキスト読み込み中...")
    text = INPUT_PATH.read_text(encoding="utf-8")

    sessions = split_sessions(text)
    print(f"会期数: {len(sessions)}")

    print("形態素解析中...")
    tagger = fugashi.Tagger()

    labels      = []
    tokenized   = []  # 各会期のトークンリスト（スペース区切り文字列）

    for i, (label, content) in enumerate(sessions, 1):
        print(f"  [{i:3d}/{len(sessions)}] {label}", flush=True)
        words = tokenize(content, tagger)
        labels.append(label)
        tokenized.append(" ".join(words))

    print("TF-IDF 計算中...")
    vectorizer = TfidfVectorizer(
        analyzer="word",
        token_pattern=r"[^\s]+",
        max_features=10000,
        min_df=2,      # 2会期以上に出現する語のみ
        max_df=0.7,    # 70%以上の会期に出る語は汎用すぎるので除外
    )
    tfidf_matrix = vectorizer.fit_transform(tokenized)
    feature_names = vectorizer.get_feature_names_out()

    result = {}
    for i, label in enumerate(labels):
        row    = tfidf_matrix[i].toarray()[0]
        # スコア上位N語を取得
        top_indices = row.argsort()[::-1][:TOP_N]
        top_words   = [
            {"word": feature_names[j], "score": round(float(row[j]), 4)}
            for j in top_indices
            if row[j] > 0
        ]
        result[label] = top_words

    OUTPUT_PATH.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    print()
    print(f"完了  → {OUTPUT_PATH}")
    print()
    # サンプル表示
    first_label = list(result.keys())[0]
    print(f"サンプル ({first_label}):")
    for item in result[first_label][:10]:
        print(f"  {item['word']}  ({item['score']})")


if __name__ == "__main__":
    main()
