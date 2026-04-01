#!/usr/bin/env python3
"""
Step 2: 全文テキストから会期・会議ごとの特徴語をTF-IDFで抽出する

入力:  kokkai_all.txt  (1_format.py の出力)
出力:  features.json   (会議ごとの特徴語リスト)

使い方:
  python3 kokkai/2_extract_features.py

依存:
  pip install fugashi unidic-lite scikit-learn
"""

import re
import json
import sys
from pathlib import Path

try:
    import fugashi
except ImportError:
    print("fugashi が必要です: pip install fugashi unidic-lite", file=sys.stderr)
    sys.exit(1)

from sklearn.feature_extraction.text import TfidfVectorizer

_DATA_DIR   = Path(__file__).parent.parent / "kokkai_data"
INPUT_PATH  = _DATA_DIR / "output" / "kokkai_all.txt"
OUTPUT_PATH = _DATA_DIR / "output" / "features.json"

TOP_N = 30

EXCLUDE_POS = {"助詞", "助動詞", "記号", "補助記号", "空白", "感動詞"}

STOPWORDS = {
    # 汎用動詞・形式語
    "する", "ある", "いる", "なる", "れる", "られる", "ない",
    "言う", "思う", "考える", "行う", "行なう", "関する", "おける",
    "つく", "でる", "みる", "くる", "いく", "もらう", "くれる",
    "できる", "おる", "いただく", "頂く", "ございます", "おります",
    "申し上げる", "申す", "存じる",
    # 指示語
    "この", "その", "あの", "これ", "それ", "あれ",
    "此れ", "其れ", "其の", "此の",
    "ここ", "そこ", "あそこ", "こちら", "そちら", "あちら",
    # 形式名詞
    "こと", "もの", "ため", "よう", "わけ", "はず",
    "ところ", "とき", "場合", "方", "上", "中", "内",
    "以上", "以下", "以内", "以外", "程度", "関係", "問題", "状況",
    # 国会共通ノイズ（全会議に等しく出る）
    "議長", "副議長", "委員長", "議員", "大臣", "大臣官房",
    "委員", "委員会", "分科会", "小委員会",
    "衆議院", "参議院", "国会", "両院", "本会議",
    "内閣", "政府", "行政", "国務", "国務大臣",
    "提案", "審議", "採決", "可決", "否決",
    "議案", "法案", "説明", "質問", "答弁", "質疑",
    "討論", "一般質疑", "開会", "閉会", "休憩", "再開",
    "賛成", "反対", "異議", "日程", "進行", "報告", "承認", "同意",
    "発言", "お答え", "先生", "大変",
    # 年号・時制
    "元年", "年度", "今年", "来年", "昨年", "本年",
    "明治", "大正", "昭和", "平成", "令和",
    "午前", "午後",
    # 接続詞・副詞
    "及び", "並びに", "または", "あるいは", "もしくは",
    "について", "において", "による", "ついて", "おいて", "よる",
    # 記号
    "○", "◎", "●", "■", "□", "△", "▲", "・",
}


def tokenize(text: str, tagger) -> list[str]:
    """名詞（普通名詞・固有名詞）のみ返す"""
    words = []
    for word in tagger(text):
        pos  = word.feature.pos1
        pos2 = word.feature.pos2
        pos3 = word.feature.pos3
        base = word.feature.lemma or word.surface

        if pos != "名詞":
            continue
        if pos2 in {"非自立可能", "接尾辞", "数詞"}:
            continue
        if pos3 == "人名":
            continue
        # 固有名詞でカタカナのみの語（辞書未登録の人名読み等）を除外
        if pos2 == "固有名詞" and re.match(r"^[ァ-ヴー]+$", base):
            continue
        if not base or len(base) < 2 or len(base) > 10:
            continue
        if base in STOPWORDS:
            continue
        if re.match(r"^[0-9０-９\s\-・]+$", base):
            continue
        if re.match(r"^[ぁ-ん]+$", base):
            continue
        if re.search(r"[a-zA-Z\-]", base):
            continue
        words.append(base)

    return words


def split_sessions(text: str) -> list[tuple[str, str]]:
    """
    kokkai_all.txt を会議ごとに分割する。
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
        print(
            f"[ERR] {INPUT_PATH} が見つかりません。先に 1_format.py を実行してください。",
            file=sys.stderr,
        )
        sys.exit(1)

    print("テキスト読み込み中...")
    text = INPUT_PATH.read_text(encoding="utf-8")

    sessions = split_sessions(text)
    print(f"会議数: {len(sessions)}")

    print("形態素解析中...")
    tagger = fugashi.Tagger()

    labels    = []
    tokenized = []

    for i, (label, content) in enumerate(sessions, 1):
        print(f"  [{i:4d}/{len(sessions)}] {label}", flush=True)
        words = tokenize(content, tagger)
        labels.append(label)
        tokenized.append(" ".join(words))

    print("TF-IDF 計算中...")
    vectorizer = TfidfVectorizer(
        analyzer="word",
        token_pattern=r"[^\s]+",
        max_features=10000,
        min_df=2,    # 2会議以上に出現する語のみ
        max_df=0.7,  # 70%以上の会議に出る語は汎用すぎるので除外
    )
    tfidf_matrix  = vectorizer.fit_transform(tokenized)
    feature_names = vectorizer.get_feature_names_out()

    result = {}
    for i, label in enumerate(labels):
        row         = tfidf_matrix[i].toarray()[0]
        top_indices = row.argsort()[::-1][:TOP_N]
        top_words   = [
            {"word": feature_names[j], "score": round(float(row[j]), 4)}
            for j in top_indices
            if row[j] > 0
        ]
        result[label] = top_words

    OUTPUT_PATH.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print()
    print(f"完了  → {OUTPUT_PATH}")

    first_label = list(result.keys())[0]
    print(f"\nサンプル ({first_label}):")
    for item in result[first_label][:10]:
        print(f"  {item['word']}  ({item['score']})")


if __name__ == "__main__":
    main()
