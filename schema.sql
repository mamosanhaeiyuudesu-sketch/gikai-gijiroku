-- 宮古島市議会 議事録データベース スキーマ

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS sessions (
    session_id    TEXT PRIMARY KEY,   -- 例: "H25-6-rinji", "R6-5-teirei"
    session_type  TEXT NOT NULL,      -- 定例会 / 臨時会 / 委員会
    session_name  TEXT,               -- 例: "平成25年第6回宮古島市議会臨時会"
    session_date  TEXT NOT NULL,      -- 開会日 (ISO 8601: YYYY-MM-DD)
    close_date    TEXT,               -- 閉会日 (複数日会議)
    year          INTEGER NOT NULL,
    term          INTEGER,            -- 議員期 (1〜6)
    source_file   TEXT                -- PDFファイル名
);

CREATE TABLE IF NOT EXISTS bills (
    bill_id       TEXT PRIMARY KEY,   -- 例: "H25-6-報告18"
    session_id    TEXT NOT NULL REFERENCES sessions(session_id),
    bill_number   TEXT NOT NULL,      -- 例: "報告第18号"
    bill_title    TEXT NOT NULL,
    proposer      TEXT,               -- 提案者 (市長 / 議員 / 委員会)
    result        TEXT,               -- 承認/可決/同意/否決/継続審査/選挙
    result_method TEXT                -- 異議なし/挙手多数/投票 等
);

CREATE TABLE IF NOT EXISTS utterances (
    utterance_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      TEXT NOT NULL REFERENCES sessions(session_id),
    bill_id         TEXT REFERENCES bills(bill_id),  -- NULL = 議事手続き
    seq             INTEGER NOT NULL,                 -- 発言順序
    date            TEXT,                             -- 複数日会議での発言日
    speaker_name    TEXT NOT NULL,                    -- 正規化済み氏名
    speaker_name_raw TEXT,                            -- PDF原文の氏名表記
    speaker_role    TEXT,            -- 議員/議長/副議長/市長/副市長/教育長/部長/課長/事務局/その他
    speaker_party   TEXT,            -- JSON参照 (最新期)
    speaker_faction TEXT,            -- JSON参照 (最新期)
    speaker_gender  TEXT,            -- JSON参照
    speaker_term    INTEGER,         -- 当該会議時点の期
    utterance_type  TEXT,            -- 質問/答弁/討論/説明/動議/挨拶/進行/その他
    content         TEXT NOT NULL
);

-- 検索用インデックス
CREATE INDEX IF NOT EXISTS idx_utterances_session  ON utterances(session_id);
CREATE INDEX IF NOT EXISTS idx_utterances_speaker  ON utterances(speaker_name);
CREATE INDEX IF NOT EXISTS idx_utterances_type     ON utterances(utterance_type);
CREATE INDEX IF NOT EXISTS idx_utterances_bill     ON utterances(bill_id);
CREATE INDEX IF NOT EXISTS idx_bills_session       ON bills(session_id);
