#!/usr/bin/env python3
"""
国会議員別 TF-IDF 特徴語抽出スクリプト

入力:
  kokkai_all.txt      (全会議テキスト: 1_format.py の出力)
  meetings/*.json     (発言者メタデータ取得用: 0_fetch.py の出力)

出力:
  output/speakers_meta.json    発話者一覧・統計
  output/tfidf_words.csv       単語レベル TF-IDF（長形式）
  output/tfidf_categories.csv  カテゴリレベルスコア（長形式）

使い方:
  pip install fugashi unidic-lite scikit-learn
  python3 kokkai/analyze_speakers.py

設定:
  MIN_UTTERANCES  … この数未満の発話セグメントを持つ話者を除外（デフォルト: 10）
  TOP_N_WORDS     … 1話者あたり上位何語を出力するか（デフォルト: 200）
"""

import re
import json
import csv
import unicodedata
import sys
from collections import defaultdict, Counter
from pathlib import Path

INPUT_TXT    = Path(__file__).parent / "kokkai_all.txt"
MEETINGS_DIR = Path(__file__).parent / "meetings"
OUTPUT_DIR   = Path(__file__).parent / "output"

MIN_UTTERANCES = 10   # 宮古島（50）より少ない：国会は1会期あたり発言が少ない議員も多い
TOP_N_WORDS    = 200

STOPWORDS = {
    # 汎用動詞・形式語
    '言う', 'つく', '此れ', '其れ', '其の', '此の', '成る', '有る', '居る', '致す',
    '掛かる', '受ける', '関する', '行う', '行なう', '出る', '入る',
    '見る', '置く', '来る', '対する', '付く', '取る', '当たる', '係る', '伴う',
    '図る', '向ける', '与える', '設ける', '基づく', '求める',
    # 汎用動詞
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
    # 国会共通ノイズ
    '議長', '副議長', '委員長', '議員', '大臣', '委員', '委員会',
    '衆議院', '参議院', '国会', '両院', '本会議', '分科会',
    '内閣', '政府', '行政', '国務', '国務大臣',
    '提案', '審議', '採決', '可決', '否決',
    '議案', '法案', '説明', '質問', '答弁', '質疑',
    '討論', '開会', '閉会', '休憩', '再開', '賛成', '反対',
    '異議', '日程', '進行', '報告', '承認', '同意', '発言',
    # 年号・時制
    '年度', '今年', '来年', '昨年', '本年', '元年',
    '明治', '大正', '昭和', '平成', '令和',
    '午前', '午後',
    # 行政共通語
    '事業', '施設', '計画', '支援', '管理', '地域', '今後',
    '職員', '本当', '理解', '部分', '利用', '整備',
    '促進', '推進', '検討', '協力', '実現', '確認', '把握',
    '活用', '強化', '改善', '充実', '向上', '確保', '適切',
    '国民', '国内', '制度', '措置', '対応', '必要',
    # 接続詞・副詞
    '及び', '並びに', 'または', 'あるいは', 'もしくは',
    'について', 'において', 'による', 'ついて', 'おいて', 'よる',
}

# 国会向けカテゴリ定義
CATEGORY_WORDS: dict[str, set[str]] = {
    '社会保障・福祉': {
        '年金', '介護', '保険', '生活保護', '生活', '障害', '障碍', '雇用', '賃金', '労働',
        '保育', '育児', '産休', '育休', '子育て', '世帯', '扶養', '老人', '高齢',
        '就労', '就職', '失業', '求職', '派遣', '非正規', '正規', '最低賃金',
        '福祉', '介護保険', '国民健康保険', '後期高齢者', '医療費', '自己負担',
        '孤独', '孤立', '貧困', '格差', '不平等',
    },
    '医療・健康': {
        '病院', '医師', '患者', '診療', '接種', '感染', '療養', '難病', '衛生',
        '外科', '内科', '精神科', '認知症', '癌', 'がん', '糖尿病', '透析',
        '薬', '医薬品', '薬価', '処方', '治療', '手術', '入院', '救急',
        '看護', '看護師', '介護士', '医療従事者', '地域医療', '在宅医療',
        'ワクチン', 'コロナ', '感染症', '健康保険', '予防接種',
        '精神', '精神保健', '自殺', '自死', '精神障害',
    },
    '教育・科学技術': {
        '学校', '教育', '授業', '教師', '教員', '学力', '学習', '入学', '卒業',
        '大学', '高校', '中学', '小学', '幼稚園', '保育園', '義務教育',
        '奨学金', '授業料', '教科書', '学習指導', '不登校', 'いじめ',
        '研究', '科学', '技術', 'ＩＴ', 'ＡＩ', 'デジタル', 'サイバー',
        '宇宙', '原子力', '核融合', 'イノベーション', '特許', '知財',
        '国立大学', '私立大学', '大学院', '博士', '研究者', '科研費',
    },
    '国土・インフラ・交通': {
        '道路', '鉄道', '新幹線', '港湾', '空港', '橋', 'トンネル', '高速道路',
        '国道', '県道', '市道', '河川', 'ダム', '治水', '上水道', '下水道',
        '電力', '電気', 'ガス', '水道', '通信', 'インフラ', '老朽化',
        '建設', '土木', '工事', '整備', '維持管理', '公共工事',
        '都市計画', '土地利用', '区画整理', '住宅', '公営住宅', '空き家',
        '交通', '路線', 'バス', 'タクシー', '離島', '過疎',
    },
    '農業・食料': {
        '農業', '農家', '農地', '農村', '農産物', '食料', '食糧', '食品',
        '米', '小麦', '野菜', '果物', '畜産', '酪農', '漁業', '水産',
        '漁港', '養殖', '魚', '農薬', '肥料', '農機', '収穫', '栽培',
        '食料安全保障', '自給率', '農林水産', 'ＪＡ', '農協',
        '有機農業', 'ＧＡＰ', 'ＨＡＣＣＰ', '輸入', '輸出', '関税',
    },
    '経済・産業・雇用': {
        '経済', '景気', 'ＧＤＰ', '成長', '物価', 'インフレ', 'デフレ',
        '企業', '中小企業', '大企業', '産業', '製造業', 'サービス業',
        '輸出', '輸入', '貿易', '為替', '円安', '円高', '金融',
        '銀行', '日銀', '金利', '株式', '投資', '融資', '補助金',
        '起業', 'スタートアップ', '雇用', '就業', '働き方', '副業',
        '観光', '宿泊', 'インバウンド', '消費', '需要', '供給',
    },
    '環境・エネルギー': {
        '環境', '気候', '温暖化', 'ＣＯ２', '二酸化炭素', '排出', '削減',
        '脱炭素', 'カーボンニュートラル', '再生可能エネルギー', '太陽光',
        '風力', '水素', '原発', '原子力', '核', '放射線', '放射能',
        '廃棄物', 'リサイクル', '廃プラ', 'マイクロプラスチック',
        '森林', '海洋', '生物多様性', '絶滅危惧', '自然保護',
        '台風', '洪水', '土砂', '津波', '地震', '災害', '防災',
        '避難', '復興', '被災',
    },
    '財政・税制': {
        '予算', '決算', '歳出', '歳入', '財政', '財源', '国債', '赤字',
        '税金', '税率', '消費税', '所得税', '法人税', '相続税', '固定資産税',
        '増税', '減税', '課税', '非課税', '税制改正',
        '補助金', '交付金', '給付金', '助成金', '奨励金',
        '社会保障費', '医療費', '年金費', '防衛費', '公共事業費',
        '財政健全化', 'プライマリーバランス', '国庫', '歳費',
    },
    '行政・議会運営': {
        '法律', '法案', '条例', '政令', '省令', '通達', '告示',
        '閣議', '閣議決定', '行政改革', '規制改革', '規制緩和',
        '選挙', '投票', '当選', '落選', '議席', '定数', '区割り',
        '選挙制度', '比例代表', '小選挙区', '参議院選', '衆議院選',
        '憲政', '議会', '民主主義', '三権分立',
        '公務員', '国家公務員', '地方公務員', '人件費', '給与',
        '地方分権', '地方自治', '都道府県', '市区町村',
        '情報公開', '個人情報', '行政手続き', 'ＤＸ',
    },
    '安全保障・外交・防衛': {
        '防衛', '自衛隊', '日米同盟', '在日米軍', '基地', '沖縄',
        '安全保障', '集団的自衛権', '専守防衛', '抑止力',
        '外交', '外務', '首脳会談', '条約', '協定', 'ＯＤＡ',
        '中国', '北朝鮮', '韓国', 'ロシア', 'アメリカ', '米国',
        '核', '核抑止', 'ミサイル', '弾道ミサイル', '迎撃',
        '拉致', '拉致問題', '領土', '尖閣', '竹島', '北方領土',
        '国連', 'ＮＡＴＯほ', '平和', '戦争', '紛争',
    },
    '憲法・司法・人権': {
        '憲法', '改憲', '護憲', '憲法改正', '九条', '第九条',
        '基本的人権', '人権', '差別', 'ヘイト', 'ヘイトスピーチ',
        '性差別', 'ジェンダー', '女性活躍', '選択的夫婦別姓',
        'ＬＧＢＴ', '同性婚', 'パートナーシップ',
        '裁判', '裁判所', '司法', '検察', '警察', '逮捕', '捜査',
        '死刑', '冤罪', '再審', '違憲', '合憲', '最高裁',
        '外国人', '在日', '難民', '移民', '永住', '帰化',
    },
    '地方・地域振興': {
        '地方', '地域', '過疎', '過疎化', '人口減少', '少子化', '高齢化',
        '移住', '定住', 'UIJターン', '地方創生', '地域活性化',
        '離島', '中山間', '農山村', '地方都市', '地方経済',
        '市区町村', '都道府県', '知事', '市長', '村長',
        '地域おこし', 'ふるさと', 'コミュニティ', '自治会', '町内会',
    },
}


def normalize_name(name: str) -> str:
    name = unicodedata.normalize('NFKC', name)
    name = re.sub(r'[\s\u3000]+', '', name)
    return name


def parse_speaker_marker(marker: str) -> tuple:
    """
    '議長（額賀福志郎君）'   → ('議長', '額賀福志郎')
    '内閣総理大臣（岸田文雄君）' → ('内閣総理大臣', '岸田文雄')
    '山田太郎君'             → (None, '山田太郎')
    """
    marker = marker.strip()

    m = re.match(r'^(.+?)（(.+?)君）\s*$', marker)
    if m:
        return m.group(1).strip(), m.group(2).strip()

    m = re.match(r'^(.+?)君\s*$', marker)
    if m:
        return None, m.group(1).strip()

    return None, marker


def parse_utterances(text: str) -> dict:
    """
    ◎マーカーで発話者と発言内容を分割する。

    Returns:
        { norm_name → { 'raw_name', 'role', 'utterances' } }
    """
    speaker_data: dict = defaultdict(lambda: {
        'utterances': [],
        'raw_name':   '',
        'role':       None,
    })

    current_key: str | None = None
    current_buf: list[str]  = []

    def flush():
        if current_key and current_buf:
            content = '\n'.join(current_buf).strip()
            if content:
                speaker_data[current_key]['utterances'].append(content)

    for line in text.split('\n'):
        if line.startswith('◎'):
            marker = line[1:].strip()
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


def load_speaker_meta_from_meetings(meetings_dir: Path) -> dict:
    """
    meetings/*.json から発言者のメタデータを収集する。

    Returns:
        { norm_name → { 'party': str, 'role': str } }
    """
    meta: dict = {}

    for jf in sorted(meetings_dir.glob("*.json")):
        try:
            meeting = json.loads(jf.read_text(encoding="utf-8"))
        except Exception:
            continue

        for speech in meeting.get("speechRecord", []):
            speaker = (speech.get("speaker") or "").strip()
            if not speaker:
                continue

            # 末尾の「君」を除去して正規化
            base = speaker[:-1] if speaker.endswith("君") else speaker
            norm = normalize_name(base)

            if norm not in meta:
                meta[norm] = {
                    'party': (speech.get("speakerGroup") or "").strip(),
                    'role':  (speech.get("speakerRole")  or "").strip(),
                }
            elif not meta[norm]['party']:
                # 後から party 情報が取れた場合は補完
                group = (speech.get("speakerGroup") or "").strip()
                if group:
                    meta[norm]['party'] = group

    return meta


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
        if '-' in base:
            continue
        if base in STOPWORDS:
            continue
        if re.match(r'^[0-9０-９\s・]+$', base):
            continue
        if re.match(r'^[ぁ-ん]+$', base):
            continue
        if re.match(r'^[ァ-ヴー]+$', base):
            continue
        if re.search(r'[a-zA-Z]', base):
            continue
        if base.endswith('君'):
            continue

        words.append(base)

    return words


def compute_tfidf(speaker_tokens: dict) -> tuple[dict, dict]:
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
    except ImportError:
        print("[ERR] scikit-learn が必要です: pip install scikit-learn", file=sys.stderr)
        sys.exit(1)

    word_counts  = {k: Counter(v) for k, v in speaker_tokens.items()}
    speaker_keys = list(speaker_tokens.keys())
    docs         = [' '.join(speaker_tokens[k]) for k in speaker_keys]

    vectorizer = TfidfVectorizer(
        analyzer='word',
        token_pattern=r'[^\s]+',
        sublinear_tf=True,
        min_df=2,
        max_df=0.6,
        norm='l2',
    )
    matrix        = vectorizer.fit_transform(docs)
    feature_names = vectorizer.get_feature_names_out()

    tfidf: dict = {}
    for i, speaker in enumerate(speaker_keys):
        row = matrix[i].toarray()[0]
        tfidf[speaker] = {
            feature_names[j]: float(row[j])
            for j in row.nonzero()[0]
        }

    return tfidf, word_counts


def compute_category_scores(tfidf: dict, word_counts: dict) -> dict:
    result: dict = {}
    for speaker in tfidf:
        result[speaker] = {}
        for category, cat_words in CATEGORY_WORDS.items():
            matched = [
                (w, tfidf[speaker][w], word_counts[speaker].get(w, 0))
                for w in cat_words
                if w in tfidf[speaker]
            ]
            score     = sum(s for _, s, _ in matched)
            top_words = [w for w, _, _ in sorted(matched, key=lambda x: -x[1])[:5]]
            result[speaker][category] = {
                'score':      round(score, 6),
                'word_count': len(matched),
                'top_words':  top_words,
            }
    return result


def main():
    if not INPUT_TXT.exists():
        print(f"[ERR] {INPUT_TXT} が見つかりません", file=sys.stderr)
        sys.exit(1)

    OUTPUT_DIR.mkdir(exist_ok=True)

    # 1. APIデータから発言者メタデータを収集
    print("発言者メタデータ収集中（meetings/*.json）...")
    api_meta = load_speaker_meta_from_meetings(MEETINGS_DIR)
    print(f"  メタデータ収集: {len(api_meta)} 名")

    # 2. 発話パース
    print("議事録テキスト読み込み・発話分割中...")
    text         = INPUT_TXT.read_text(encoding='utf-8')
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
    CHUNK_SIZE = 2000

    for i, (speaker_key, info) in enumerate(filtered.items(), 1):
        raw_name = info['raw_name']
        print(f"  [{i:3d}/{len(filtered)}] {raw_name}", flush=True)

        all_tokens: list[str] = []
        for utterance in info['utterances']:
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

    # 7. 発言者メタデータ整形
    def get_speaker_meta(speaker_key: str, info: dict) -> dict:
        m = api_meta.get(speaker_key, {})
        return {
            'name':   info['raw_name'],
            'party':  m.get('party', ''),
            'role':   info.get('role') or m.get('role', ''),
        }

    # 8-A. speakers_meta.json
    print("speakers_meta.json 出力中...")
    speakers_meta = []
    for speaker_key, info in filtered.items():
        meta    = get_speaker_meta(speaker_key, info)
        n_utts  = len(info['utterances'])
        n_words = len(speaker_tokens.get(speaker_key, []))
        speakers_meta.append({
            'id':              speaker_key,
            'name':            meta['name'],
            'role':            meta['role'],
            'party':           meta['party'],
            'utterance_count': n_utts,
            'total_words':     n_words,
        })

    speakers_meta.sort(key=lambda x: -x['utterance_count'])

    (OUTPUT_DIR / 'speakers_meta.json').write_text(
        json.dumps(speakers_meta, ensure_ascii=False, indent=2),
        encoding='utf-8',
    )
    print(f"  → {OUTPUT_DIR}/speakers_meta.json  ({len(speakers_meta)} 話者)")

    # 8-B. tfidf_words.csv
    print("tfidf_words.csv 出力中...")
    words_path = OUTPUT_DIR / 'tfidf_words.csv'
    word_rows  = []

    for speaker_key, info in filtered.items():
        meta   = get_speaker_meta(speaker_key, info)
        scores = tfidf.get(speaker_key, {})
        counts = word_counts.get(speaker_key, Counter())

        top_words = sorted(scores.items(), key=lambda x: -x[1])[:TOP_N_WORDS]

        for rank, (word, score) in enumerate(top_words, 1):
            word_rows.append({
                'speaker_id':      speaker_key,
                'name':            meta['name'],
                'role':            meta['role'],
                'party':           meta['party'],
                'utterance_count': len(info['utterances']),
                'word':            word,
                'tfidf':           round(score, 6),
                'count':           counts[word],
                'rank':            rank,
            })

    with open(words_path, 'w', encoding='utf-8', newline='') as f:
        fieldnames = [
            'speaker_id', 'name', 'role', 'party',
            'utterance_count', 'word', 'tfidf', 'count', 'rank',
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
        meta = get_speaker_meta(speaker_key, info)
        cats = cat_scores.get(speaker_key, {})

        for category, vals in cats.items():
            cat_rows.append({
                'speaker_id':      speaker_key,
                'name':            meta['name'],
                'role':            meta['role'],
                'party':           meta['party'],
                'utterance_count': len(info['utterances']),
                'category':        category,
                'score':           round(vals['score'], 6),
                'word_count':      vals['word_count'],
                'top_words':       ','.join(vals['top_words']),
            })

    with open(cat_path, 'w', encoding='utf-8', newline='') as f:
        fieldnames = [
            'speaker_id', 'name', 'role', 'party',
            'utterance_count', 'category', 'score', 'word_count', 'top_words',
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(cat_rows)

    print(f"  → {OUTPUT_DIR}/tfidf_categories.csv  ({len(cat_rows)} 行)")

    print()
    print("=" * 50)
    print("完了")
    print(f"  話者数:          {len(speakers_meta)}")
    print(f"  単語行数:        {len(word_rows)}")
    print(f"  カテゴリ行数:    {len(cat_rows)}")
    print()
    print("サンプル（上位3話者の特徴語 TOP5）:")
    for sp in speakers_meta[:3]:
        sid  = sp['id']
        top5 = sorted(tfidf.get(sid, {}).items(), key=lambda x: -x[1])[:5]
        words_str = ', '.join(f"{w}({s:.4f})" for w, s in top5)
        print(f"  {sp['name']}  [{sp['role']}] : {words_str}")


if __name__ == '__main__':
    main()
