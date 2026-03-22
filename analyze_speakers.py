#!/usr/bin/env python3
"""
議員別 TF-IDF 特徴語抽出スクリプト

入力:
  gijiroku_all.txt                          (全会期議事録テキスト)
  miyakojima_council_members_20years.json   (議員プロフィール)

出力:
  output/speakers_meta.json    発話者一覧・統計
  output/tfidf_words.csv       単語レベル TF-IDF（長形式）
  output/tfidf_categories.csv  カテゴリレベルスコア（長形式）

使い方:
  pip install fugashi unidic-lite scikit-learn
  python3 analyze_speakers.py

設定:
  MIN_UTTERANCES  … この数未満の発話セグメントを持つ話者を除外（デフォルト: 50）
  TOP_N_WORDS     … 1話者あたり上位何語を出力するか（デフォルト: 200）
"""

import re
import json
import csv
import math
import unicodedata
import sys
from collections import defaultdict, Counter
from pathlib import Path

# ─── ファイルパス ─────────────────────────────────────────
INPUT_TXT    = Path("gijiroku_all.txt")
MEMBERS_JSON = Path("miyakojima_council_members_20years.json")
OUTPUT_DIR   = Path("output")

# ─── 設定 ────────────────────────────────────────────────
MIN_UTTERANCES = 50   # これ未満の発話セグメント数の話者を除外
TOP_N_WORDS    = 200  # 1話者あたりの出力単語数上限

# ─── ストップワード（ユーザー定義 + 議会共通ノイズ）───────────
STOPWORDS = {
    # ユーザー定義
    '言う', 'つく', '此れ', '其れ', '其の', '此の', '成る', '有る', '居る', '致す',
    '掛かる', '受ける', '関する', '行う', '行なう', '元年', '因る', '出る', '入る',
    '見る', '置く', '来る', '対する', '付く', '取る', '当たる', '係る', '伴う',
    '図る', '向ける', '与える', '設ける', '基づく', '求める', '休憩', '質疑',
    '議決', '議案', '請け負い', '一貫', '子供', '道路',
    # 汎用動詞・形式語
    'する', 'ある', 'いる', 'なる', 'れる', 'られる', 'ない',
    '思う', '考える', 'おける', 'でる', 'みる', 'くる', 'いく', 'もらう',
    'できる', 'おる', 'いただく', '頂く', 'ございます', 'おります',
    '申し上げる', '申す', '存じる',
    # 指示語
    'この', 'その', 'あの', 'これ', 'それ', 'あれ',
    'ここ', 'そこ', 'あそこ', 'こちら', 'そちら', 'あちら',
    # 形式名詞
    'こと', 'もの', 'ため', 'よう', 'わけ', 'はず',
    'ところ', 'とき', '場合', '方', '上', '中', '内', '以上',
    '以下', '以内', '以外', '程度', '関係', '問題', '状況',
    # 議会共通ノイズ（全話者に等しく出る）
    '議長', '市長', '議員', '宮古島', '宮古島市', '会議', '議会',
    '副議長', '委員', '委員会', '提案', '審議', '採決', '可決',
    '説明', '質問', '答弁', '討論', '一般質問', '定例会', '臨時会',
    '市議会', '開会', '閉会', '再開', '賛成', '反対', '異議',
    '日程', '進行', '報告', '承認', '同意',
    # 年号・時制・手続き語
    '年度', '今年', '来年', '昨年', '本年', '本市',
    '明治', '大正', '昭和', '平成', '令和',
    '午前', '午後', '無し', '有り', '多数', '発言', '出席', '欠席',
    # 議長・議事進行専用語
    '終結', '挙手', '演壇', '開議', '暫時', '直ちに', '採択',
    '事項', '案件', '結果', '内容', '実施', '対応', '必要',
    '以上', '以下', '本件', '当該', '各種', '各位',
    # 行政共通語（ほぼ全話者に出現して TF-IDF を汚染する語）
    '事業', '施設', '計画', '支援', '管理', '行政', '地域', '今後',
    '職員', '本当', '理解', '部分', '伺い', '利用', '整備',
    '促進', '推進', '検討', '協力', '実現', '確認', '把握',
    '活用', '強化', '改善', '充実', '向上', '確保', '適切',
    '市民', '市内', '住民', '区域', '行為', '制度', '措置',
    # 接続詞・副詞残り
    '及び', '並びに', 'または', 'あるいは', 'もしくは',
    'について', 'において', 'による', 'ついて', 'おいて', 'よる',
}

# ─── カテゴリ定義 ─────────────────────────────────────────
CATEGORY_WORDS: dict[str, set[str]] = {
    '暮らし・福祉': {
        '介護', '住宅', '住居', '世帯', '老人', '子育て', '保育', '障害', '保護', '保障',
        '雇用', '賃金', '家賃', '就労', '助成', '定住', '入居', '民泊', '家族', '家庭',
        '引っ越し', '休業', '不妊', '育成', '療養', '難病', '慰謝', '賠償', '弁償',
        '世代', '人権', '尊厳', '民宿', '扶養', '勤務', '労働', '労務', '生命',
        '社協', '義捐', '見舞金', '移住', '傍聴', '給与', '給付', '給料', '年金',
        '生活', '就農', '空き家', '民間', '人口', '人材', '受給', '福祉',
    },
    '医療・健康': {
        '病院', '医師', '患者', '診療', '接種', '感染', '療養', '難病', '衛生', '外科',
        '内科', '視力', '肝炎', '腎臓', '病気', '痛み', '認知', '不妊', 'ｐｃｒ',
        '疾患', '抗原', '白血球', '皮膚', '健診', '防疫', '障害', '虐待',
        '予防', '感覚', '疎通', '産後', '口蹄', '感染症',
    },
    '子ども・教育': {
        '子育て', '学力', '学校', '学童', '生徒', '教室', '保育', '学級', '校長',
        '学区', '学園', '児童', '休校', '小児', '授業', '卒業', '学術', '教科', '教職員',
        '入学', '中学', '大学', '高校', '校区', '校舎', '図書', '園児', '休園',
        '学年', '文教', '奨励', '講座', '研修', '人材',
    },
    'まちづくり・インフラ': {
        '建築', '施工', '工期', '水道', '排水', '電気', '建設', '下水', '港湾',
        '空港', '電柱', '交通', '駐車', '大橋', '架橋', '浚渫', '埋め立て',
        '工務', '工区', '工法', '工場', '改修', '改築', '改良', '外構', '建て替え',
        '景観', '都市', '用排水', '取水', '水源', '水質', '水域', '水門',
        '農道', '市道', '路線', '幹線', '跡地', '再建', '整備',
        '電力', '電源', '燃料', '灯油', '水量', '浄水', '浄化', '汚泥',
        'ｌｅｄ', 'ｌｃｄ', 'ｉｃｔ', 'ｉｔ', 'ｄｘ',
        '構造', '構想', '構築', '造成', '埠頭', '丘陵', '基盤', '基礎',
        '底盤', '地盤', '土工', '残土', '破砕', '転圧', '型枠', '設備',
        '断水', '用地', '敷設', '入札', '工事',
        '立方', '数量', '約款', '延長', '建物', '土砂', '丸太',
    },
    '農業・水産業': {
        '農家', '漁業', '漁港', '養殖', '畜産', '農道', '牧場', '農薬', '甘蔗', '牡蠣',
        '製糖', '農業', '農地', '農振', '農村', '農漁業', '農都', '農山村', '漁協',
        '生産', '生乳', '肥料', '肥育', '栽培', '耕土', '圃場',
        '山羊', '藻類', '珊瑚', '糖価', '糖度', '和牛',
        '蕎麦', 'ｇａｐ', 'ｈａｃｃｐ', '食肉', '精肉', '食料', '食材', '飼料',
        '耳標', '水産', '海産',
    },
    '観光・産業': {
        '観光', '宿泊', '民泊', '商工', '市場', '産業', '物価', '製造', '飲食',
        '物産', '物流', '輸送', '物品', '景観', '周遊', '旅客', '旅費',
        '航空', '航路', 'ｊｔａ', '法人', '営業', '店舗', '購買', '購入',
        '売り払い', '売却', '売買', '工芸', '楽園', '記念',
        '運動', '大会', '競技', '球団', '球場', '野球', '祭り', '祭場',
        '祝賀', '祝辞', '演奏', '朗読', '映画', '音楽', '音声', '音響',
        '表彰', '受章', '叙勲', '民宿', '受け入れ',
    },
    '環境・防災': {
        '台風', '津波', '避難', '災害', '防災', '排出', '汚染', '廃棄', '炭素', '珊瑚',
        '噴火', '噴出', '地震', '洪水', '冠水', '大雨', '雨量', '雨水', '暴風',
        '断層', '断水', '雨漏り', '防火', '消火', '消防', '警報', '警戒',
        '防犯', '防止', '防除', '脱炭', '太陽', '風力', '蓄電', '発電', '充電',
        '省エネ', '酸化', '汚泥', '汚濁', '瓦礫', '飛散', '軽石',
        '漂着', '漂流', '海岸', '山間', '崖下', '陥没', '土砂', '破損',
        '損害', '被災', '被害', '流用', '廃止', '廃校', '除草',
    },
    '財政・税金': {
        '税金', '赤字', '予算', '補助', '歳出', '収入', '財務', '補償', '減税', '黒字',
        '財団', '税制', '税額', '課税', '増税', '納税', '納入', '納品',
        '補填', '補充', '補強', '補欠', '補佐',
        '収支', '収納', '収穫', '収集', '債務', '債権', '償却', '有償', '無償',
        '金融', '金利', '銀行', '公債', '公庫', '起債', '返済', '返還',
        '追認', '還付', '還元', '繰り越し', '繰り入れ', '繰り上げ',
        '剰余', '予備', '積立', '資産', '資格', '資材', '充当', '充用',
        '加算', '概算', '計算', '精算', '清算', '賦課', '賃借',
        '分担', '割合', '組み替え', '減額', '増額', '減価', '減免',
        '減給', '滞納', '不納', '分納', '前払い', '買収',
        '損益', '損傷', '見積もり', '随契', '随意', '発注', '委託',
        '入札', '落札', '競争', '選定', 'ｐｆｉ', '補修', '補助金',
    },
    '行政・議会運営': {
        '市議', '市政', '議場', '選任', '投票', '議席', '条例', '決議', '陳情',
        '請願', '答申', '動議', '勧告', '告発', '告知', '通告', '訓示', '訓告',
        '辞職', '辞任', '辞退', '解任', '解散', '解明', '解消',
        '市制', '市営', '市有', '市税', '市道', '首長', '部長',
        '課長', '部会', '部局', '役員', '役割', '役職',
        '認定', '認可', '承諾', '合意', '決裁', '流会',
        '閉庁', '閉鎖', '開示', '開発', '開票', '開通', '開所', '開札',
        '人事', '人件', '人材', '人勧', '任命', '任期', '任務', '任用',
        '再任', '昇任', '退職', '退任', '免除', '選考', '選択',
        '施政', '施策', '行財政', '政権', '政府', '政党',
        '公募', '公職', '公務', '公報', '公益', '公社', '公立', '公約',
        '会派', '会場', '会長', '広域',
        '起案', '起用', '記入', '記名', '謄本', '誤字', '付帯', '付則',
        '専決', '専任', '専門', '所管', '所定', '所在',
        '審理', '裁判', '裁定', '裁決', '裁量', '判決', '起訴', '被告',
        '声明', '謝罪', '嘆願', '陳述', '陳謝',
        '研修', '出張', '随契', '随意', '指令', '指示', '策定',
        '規格', '規模', '規程', '規約', '方式', '方向', '形成', '統一', '統合',
        '連合', '連携', '連帯', '連絡', '連結', '連盟', '職務', '職種',
        '互選', '選挙', '当選', '落選', '得票', '否決', '賛否', '表決',
    },
    '安全保障・基地問題': {
        '基地', '軍事', '弾薬', '自衛', '駐屯', '艦隊', '射撃', '火薬', '実弾',
        '軍人', '軍属', '艦船', '兵力', '兵士', '戦争', '戦略', '戦没', '軍艦',
        '爆撃', '殺傷', '火傷', '防衛', '有事', '海兵', '海軍',
        '空軍', '陸上', '米軍', '米国', '米兵', '在沖', '在日', '日米',
        'ｅｅｚ', '領海', '領土', '領有', '拉致', '遺骨', '遺体',
        '遺跡', '追悼', '遺棄', '陣地', '誤発', '賠償',
    },
}

# ─── ユーティリティ ───────────────────────────────────────

# 議事録テキストと議員 JSON で異なる異体字の対応表
_KANJI_VARIANTS = str.maketrans({
    '德': '徳',   # U+5FB7 → U+5FB3
    '榮': '栄',   # U+69AE → U+6804
    '惠': '恵',   # U+60E0 → U+6075
    '穗': '穂',
    '廣': '広',
    '燁': '耀',
    '滿': '満',
    '壽': '寿',
})


def normalize_name(name: str) -> str:
    """名前の正規化: 全角スペース除去、NFKC 正規化、異体字統一"""
    name = unicodedata.normalize('NFKC', name)
    name = re.sub(r'[\s\u3000]+', '', name)
    name = name.translate(_KANJI_VARIANTS)
    return name


def parse_speaker_marker(marker: str) -> tuple:
    """
    '議長（佐久本洋介君）'  → ('議長', '佐久本洋介')
    '農林水産部長（松原清光君）' → ('農林水産部長', '松原清光')
    '島尻 誠君'            → (None, '島尻 誠')
    '仲里タカ子君'          → (None, '仲里タカ子')
    """
    marker = marker.strip()

    # ROLE（NAME君）パターン
    m = re.match(r'^(.+?)（(.+?)君）\s*$', marker)
    if m:
        return m.group(1).strip(), m.group(2).strip()

    # NAME君パターン
    m = re.match(r'^(.+?)君\s*$', marker)
    if m:
        return None, m.group(1).strip()

    # 君なし（念のため）
    return None, marker


# ─── 発話パース ───────────────────────────────────────────

def parse_utterances(text: str) -> dict:
    """
    ◎ マーカーで発話者と発言内容を分割する。

    Returns:
        {
          norm_name: {
            'raw_name': str,
            'role': str | None,
            'utterances': [str, ...],   # 発話セグメントのリスト
          }
        }
    """
    speaker_data: dict = defaultdict(lambda: {
        'utterances': [],
        'raw_name': '',
        'role': None,
    })

    current_key: str | None = None
    current_buf: list[str] = []

    def flush():
        if current_key and current_buf:
            content = '\n'.join(current_buf).strip()
            if content:
                speaker_data[current_key]['utterances'].append(content)

    for line in text.split('\n'):
        if line.startswith('◎'):
            marker = line[1:].strip()
            # 「君」を含まない ◎ 行はセクション見出し（例: ◎出席議員）なので無視
            if '君' not in marker:
                continue

            flush()
            current_buf = []

            role, raw_name = parse_speaker_marker(marker)
            norm = normalize_name(raw_name)

            current_key = norm
            if not speaker_data[norm]['raw_name']:
                speaker_data[norm]['raw_name'] = raw_name
            if role and not speaker_data[norm]['role']:
                speaker_data[norm]['role'] = role
        else:
            if current_key is not None:
                current_buf.append(line)

    flush()
    return dict(speaker_data)


# ─── 議員メタデータ ───────────────────────────────────────

def load_members(json_path: Path) -> dict:
    """
    最新期のプロフィールで議員データを返す。

    Returns:
        { normalize_name → {name, kana, gender, party, faction, terms} }
    """
    data = json.loads(json_path.read_text(encoding='utf-8'))
    members: dict = {}

    for member in data['members']:
        norm = normalize_name(member['name'])
        terms = member.get('terms', [])
        latest = terms[-1] if terms else {}
        term_numbers = [t['term'] for t in terms]

        members[norm] = {
            'name':    member['name'],
            'kana':    member.get('kana', ''),
            'gender':  member.get('gender', ''),
            'party':   latest.get('party', '-'),
            'faction': latest.get('faction', '-'),
            'terms':   term_numbers,
        }

    return members


# ─── 形態素解析 ───────────────────────────────────────────

def build_tokenizer():
    try:
        import fugashi
        tagger = fugashi.Tagger()
        print("  形態素解析エンジン: fugashi (MeCab/unidic-lite)")
        return tagger
    except ImportError:
        print("[ERR] fugashi が必要です: pip install fugashi unidic-lite", file=sys.stderr)
        sys.exit(1)


def tokenize(text: str, tagger) -> list[str]:
    """名詞（固有名詞・普通名詞）を原形で返す。2_extract_features.py と同様の方針。"""
    words = []
    for word in tagger(text):
        pos  = word.feature.pos1
        pos2 = word.feature.pos2
        base = word.feature.lemma or word.surface

        if pos != '名詞':
            continue
        if pos2 in {'非自立可能', '接尾辞', '数詞', '助数詞相当語'}:
            continue
        if not base or len(base) < 2:
            continue
        # unidic-lite が "語彙素-助数詞" 形式を返すことがある → ハイフン以降を除去して判定
        if '-' in base:
            continue
        if base in STOPWORDS:
            continue
        # 数字のみ
        if re.match(r'^[0-9０-９\s・]+$', base):
            continue
        # ひらがなのみ
        if re.match(r'^[ぁ-ん]+$', base):
            continue
        # カタカナのみ（読み仮名ノイズ）
        if re.match(r'^[ァ-ヴー]+$', base):
            continue
        # ASCII（半角）はノイズとして除外。全角 ASCII（ｉｔ, ｄｘ 等）は残す
        if re.search(r'[a-zA-Z]', base):
            continue
        # 「〇君」形式の名前断片（議事録で他の議員を指す表現）を除外
        if base.endswith('君'):
            continue

        words.append(base)

    return words


# ─── TF-IDF 計算 ─────────────────────────────────────────

def compute_tfidf(
    speaker_tokens: dict[str, list[str]]
) -> tuple[dict, dict]:
    """
    sklearn TfidfVectorizer で話者ごとの TF-IDF を計算。
    - sublinear_tf=True : log(1+tf) で高頻度語を抑制
    - min_df=2          : 1人にしか出ない語を除外
    - max_df=0.6        : 60%超の話者に出る語（汎用語）を除外
    - L2 正規化         : 話者間でスコアが比較可能

    Returns:
        tfidf      : { speaker_key → { word → score } }
        word_counts: { speaker_key → Counter }
    """
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
    except ImportError:
        print("[ERR] scikit-learn が必要です: pip install scikit-learn", file=sys.stderr)
        sys.exit(1)

    word_counts = {k: Counter(v) for k, v in speaker_tokens.items()}
    speaker_keys = list(speaker_tokens.keys())

    # 各話者のトークンをスペース区切り文字列に変換
    docs = [' '.join(speaker_tokens[k]) for k in speaker_keys]

    vectorizer = TfidfVectorizer(
        analyzer='word',
        token_pattern=r'[^\s]+',
        sublinear_tf=True,   # log(1+tf) で高頻度語を抑制
        min_df=2,            # 2話者以上に出る語のみ
        max_df=0.6,          # 60%超の話者に出る語は汎用語として除外
        norm='l2',           # L2 正規化で話者間比較を可能に
    )
    matrix = vectorizer.fit_transform(docs)
    feature_names = vectorizer.get_feature_names_out()

    tfidf: dict = {}
    for i, speaker in enumerate(speaker_keys):
        row = matrix[i].toarray()[0]
        tfidf[speaker] = {
            feature_names[j]: float(row[j])
            for j in row.nonzero()[0]
        }

    return tfidf, word_counts


# ─── カテゴリスコア計算 ───────────────────────────────────

def compute_category_scores(
    tfidf: dict,
    word_counts: dict,
) -> dict:
    """
    カテゴリスコア = そのカテゴリ内単語の TF-IDF を合算。

    Returns:
        { speaker_key → { category → { score, word_count, top_words } } }
    """
    result: dict = {}
    for speaker in tfidf:
        result[speaker] = {}
        for category, cat_words in CATEGORY_WORDS.items():
            matched = [
                (w, tfidf[speaker][w], word_counts[speaker].get(w, 0))
                for w in cat_words
                if w in tfidf[speaker]
            ]
            score = sum(s for _, s, _ in matched)
            top_words = [w for w, _, _ in sorted(matched, key=lambda x: -x[1])[:5]]
            result[speaker][category] = {
                'score':      round(score, 6),
                'word_count': len(matched),
                'top_words':  top_words,
            }
    return result


# ─── メイン ──────────────────────────────────────────────

def main():
    if not INPUT_TXT.exists():
        print(f"[ERR] {INPUT_TXT} が見つかりません", file=sys.stderr)
        sys.exit(1)
    if not MEMBERS_JSON.exists():
        print(f"[ERR] {MEMBERS_JSON} が見つかりません", file=sys.stderr)
        sys.exit(1)

    OUTPUT_DIR.mkdir(exist_ok=True)

    # 1. 議員メタデータ読み込み
    print("議員メタデータ読み込み中...")
    members = load_members(MEMBERS_JSON)
    print(f"  議員数: {len(members)}")

    # 2. 発話パース
    print("議事録テキスト読み込み・発話分割中...")
    text = INPUT_TXT.read_text(encoding='utf-8')
    speaker_data = parse_utterances(text)
    print(f"  発話者候補数（フィルタ前）: {len(speaker_data)}")

    # 3. MIN_UTTERANCES フィルタ
    filtered = {
        k: v for k, v in speaker_data.items()
        if len(v['utterances']) >= MIN_UTTERANCES
    }
    print(f"  発話者数（{MIN_UTTERANCES}セグメント以上）: {len(filtered)}")

    # 4. 形態素解析
    print("形態素解析中...")
    tagger = build_tokenizer()

    speaker_tokens = {}
    CHUNK_SIZE = 2000  # 一度に処理する文字数（segfault 対策）

    for i, (speaker_key, info) in enumerate(filtered.items(), 1):
        raw_name = info['raw_name']
        print(f"  [{i:3d}/{len(filtered)}] {raw_name}", flush=True)

        all_tokens: list[str] = []
        for utterance in info['utterances']:
            # 長い発話は CHUNK_SIZE 文字ずつ分割して処理
            for start in range(0, max(1, len(utterance)), CHUNK_SIZE):
                chunk = utterance[start:start + CHUNK_SIZE]
                all_tokens.extend(tokenize(chunk, tagger))

        speaker_tokens[speaker_key] = all_tokens

    # 5. TF-IDF 計算
    print("TF-IDF 計算中...")
    tfidf, word_counts = compute_tfidf(speaker_tokens)

    # 6. カテゴリスコア計算
    print("カテゴリスコア計算中...")
    cat_scores = compute_category_scores(tfidf, word_counts)

    # 7. 議員メタデータとのマッチング
    def get_member_meta(speaker_key: str, info: dict) -> dict:
        """議員JSONと照合し、メタ情報を返す。未登録はロールで補完。"""
        if speaker_key in members:
            m = members[speaker_key]
            return {
                'name':    m['name'],
                'kana':    m['kana'],
                'gender':  m['gender'],
                'party':   m['party'],
                'faction': m['faction'],
                'terms':   m['terms'],
                'role':    info.get('role') or '議員',
                'in_member_json': True,
            }
        else:
            return {
                'name':    info['raw_name'],
                'kana':    '',
                'gender':  '',
                'party':   '',
                'faction': '',
                'terms':   [],
                'role':    info.get('role') or '不明',
                'in_member_json': False,
            }

    # ─── 出力 ────────────────────────────────────────────────

    # 8-A. speakers_meta.json
    print("speakers_meta.json 出力中...")
    speakers_meta = []
    for speaker_key, info in filtered.items():
        meta = get_member_meta(speaker_key, info)
        n_utterances = len(info['utterances'])
        n_words = len(speaker_tokens.get(speaker_key, []))
        speakers_meta.append({
            'id':              speaker_key,
            **meta,
            'utterance_count': n_utterances,
            'total_words':     n_words,
        })

    # utterance_count 降順でソート
    speakers_meta.sort(key=lambda x: -x['utterance_count'])

    (OUTPUT_DIR / 'speakers_meta.json').write_text(
        json.dumps(speakers_meta, ensure_ascii=False, indent=2),
        encoding='utf-8',
    )
    print(f"  → {OUTPUT_DIR}/speakers_meta.json  ({len(speakers_meta)} 話者)")

    # 8-B. tfidf_words.csv
    print("tfidf_words.csv 出力中...")
    words_path = OUTPUT_DIR / 'tfidf_words.csv'
    word_rows = []

    for speaker_key, info in filtered.items():
        meta = get_member_meta(speaker_key, info)
        scores = tfidf.get(speaker_key, {})
        counts = word_counts.get(speaker_key, Counter())

        # TF-IDF スコア降順に TOP_N_WORDS 語
        top_words = sorted(scores.items(), key=lambda x: -x[1])[:TOP_N_WORDS]

        for rank, (word, score) in enumerate(top_words, 1):
            word_rows.append({
                'speaker_id':      speaker_key,
                'name':            meta['name'],
                'role':            meta['role'],
                'gender':          meta['gender'],
                'party':           meta['party'],
                'faction':         meta['faction'],
                'terms':           ','.join(str(t) for t in meta['terms']),
                'utterance_count': len(info['utterances']),
                'word':            word,
                'tfidf':           round(score, 6),
                'count':           counts[word],
                'rank':            rank,
            })

    with open(words_path, 'w', encoding='utf-8', newline='') as f:
        fieldnames = [
            'speaker_id', 'name', 'role', 'gender', 'party', 'faction',
            'terms', 'utterance_count', 'word', 'tfidf', 'count', 'rank',
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(word_rows)

    print(f"  → {OUTPUT_DIR}/tfidf_words.csv  ({len(word_rows)} 行)")

    # 8-C. tfidf_categories.csv
    print("tfidf_categories.csv 出力中...")
    cat_path = OUTPUT_DIR / 'tfidf_categories.csv'
    cat_rows = []

    for speaker_key, info in filtered.items():
        meta = get_member_meta(speaker_key, info)
        cats = cat_scores.get(speaker_key, {})

        for category, vals in cats.items():
            cat_rows.append({
                'speaker_id':      speaker_key,
                'name':            meta['name'],
                'role':            meta['role'],
                'gender':          meta['gender'],
                'party':           meta['party'],
                'faction':         meta['faction'],
                'terms':           ','.join(str(t) for t in meta['terms']),
                'utterance_count': len(info['utterances']),
                'category':        category,
                'score':           round(vals['score'], 6),
                'word_count':      vals['word_count'],
                'top_words':       ','.join(vals['top_words']),
            })

    with open(cat_path, 'w', encoding='utf-8', newline='') as f:
        fieldnames = [
            'speaker_id', 'name', 'role', 'gender', 'party', 'faction',
            'terms', 'utterance_count', 'category', 'score', 'word_count', 'top_words',
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(cat_rows)

    print(f"  → {OUTPUT_DIR}/tfidf_categories.csv  ({len(cat_rows)} 行)")

    # 完了サマリー
    print()
    print("=" * 50)
    print("完了")
    print(f"  話者数:          {len(speakers_meta)}")
    print(f"  単語行数:        {len(word_rows)}")
    print(f"  カテゴリ行数:    {len(cat_rows)}")
    print()
    print("サンプル（上位3話者の特徴語 TOP5）:")
    for sp in speakers_meta[:3]:
        sid = sp['id']
        top5 = sorted(tfidf.get(sid, {}).items(), key=lambda x: -x[1])[:5]
        words_str = ', '.join(f"{w}({s:.4f})" for w, s in top5)
        print(f"  {sp['name']}  [{sp['role']}] : {words_str}")


if __name__ == '__main__':
    main()
