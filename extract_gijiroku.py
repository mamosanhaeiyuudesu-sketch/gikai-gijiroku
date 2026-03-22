#!/usr/bin/env python3
"""
宮古島市議会 議事録PDFを一括でSQLiteに取り込むスクリプト
対象: gijiroku/ 以下のPDFファイル

出力:
  gijiroku.db  - CloudFlare D1互換 SQLiteファイル
  gijiroku.sql - D1 import用 SQLダンプ (INSERT文)

使い方:
  python3 extract_gijiroku.py

依存:
  pip install pymupdf
"""

import re
import sqlite3
import sys
import os
from pathlib import Path

try:
    import fitz  # PyMuPDF
except ImportError:
    print("PyMuPDF が必要です: pip install pymupdf", file=sys.stderr)
    sys.exit(1)

# ── 設定 ──────────────────────────────────────────────────────
GIJIROKU_DIR = Path(__file__).parent / "gijiroku"
DB_PATH      = Path(__file__).parent / "gijiroku.db"
SQL_PATH     = Path(__file__).parent / "gijiroku.sql"

# ── 元号 → 西暦 ───────────────────────────────────────────────
GENGOU_BASE = {"明治": 1868, "大正": 1912, "昭和": 1926, "平成": 1989, "令和": 2019}

def wareki_to_seireki(gengou: str, nen: int) -> int:
    return GENGOU_BASE.get(gengou, 0) + nen - 1

_ZEN_TO_HAN = str.maketrans("０１２３４５６７８９", "0123456789")

def _normalize_year_num(s: str) -> int:
    """'元' → 1、全角数字 → 半角数字 → int"""
    s = s.strip().translate(_ZEN_TO_HAN)
    return 1 if s == "元" else int(s)

def parse_japanese_date(text: str):
    """「平成17年12月12日」「令和元年10月31日」「令和６年１月26日」→「YYYY-MM-DD」"""
    text = text.translate(_ZEN_TO_HAN)
    m = re.search(
        r"(明治|大正|昭和|平成|令和)\s*(元|\d+)\s*年\s*(\d+)\s*月\s*(\d+)\s*日", text
    )
    if not m:
        return None
    year = wareki_to_seireki(m.group(1), _normalize_year_num(m.group(2)))
    return f"{year:04d}-{int(m.group(3)):02d}-{int(m.group(4)):02d}"

# ── 第1ページからメタデータを抽出 ─────────────────────────────
def extract_metadata(page1: str) -> dict:
    """
    第1ページの構造:
      平成 17 年
      第３回宮古島市議会(定例会)会議録
      自 平成17年12月12日（月） 開会
      至 平成17年12月22日（木） 閉会
    """
    t = page1.translate(str.maketrans("０１２３４５６７８９", "0123456789"))

    meta = dict(gengou=None, nendo_num=None, nendo=None,
                kai=None, session_type=None, date_start=None, date_end=None)

    # 表紙は「令 和 ２ 年」「令和元年」のように文字間スペース・元年がある → 許容
    m = re.search(
        r"(明\s*治|大\s*正|昭\s*和|平\s*成|令\s*和)\s*(元|\d+)\s*年", t
    )
    if m:
        gengou_clean      = m.group(1).replace(" ", "")
        nendo_num         = _normalize_year_num(m.group(2))
        meta["gengou"]    = gengou_clean
        meta["nendo_num"] = nendo_num
        meta["nendo"]     = f"{gengou_clean}{m.group(2).strip()}年"

    m = re.search(r"第\s*(\d+)\s*回", t)
    if m:
        meta["kai"] = int(m.group(1))

    if "定例会" in t:
        meta["session_type"] = "定例会"
    elif "臨時会" in t:
        meta["session_type"] = "臨時会"

    # 複数日: 自〜至（元年対応）
    _DATE_PAT = r"(?:明治|大正|昭和|平成|令和)\s*(?:元|\d+)\s*年\s*\d+\s*月\s*\d+\s*日"
    m_s = re.search(r"自\s*(" + _DATE_PAT + r")", t)
    m_e = re.search(r"至\s*(" + _DATE_PAT + r")", t)
    if m_s:
        meta["date_start"] = parse_japanese_date(m_s.group(1))
    if m_e:
        meta["date_end"]   = parse_japanese_date(m_e.group(1))

    # 1日のみ（臨時会等）: 元号+年+月+日 のパターンを全て拾う
    if meta["date_start"] is None:
        dates = re.findall(
            r"((?:明\s*治|大\s*正|昭\s*和|平\s*成|令\s*和)\s*(?:元|\d+)\s*年\s*\d+\s*月\s*\d+\s*日)", t
        )
        # 年のみ表記は除外済み（月+日まで含むパターン）なので全て有効
        for d in dates:
            parsed = parse_japanese_date(d.replace(" ", ""))
            if parsed:
                meta["date_start"] = parsed
                meta["date_end"]   = parsed
                break

    return meta

# ── PDFテキスト抽出 ───────────────────────────────────────────
def extract_text(pdf_path: Path):
    """(page1_text, full_text) を返す。スキャンPDFは ("", "") を返す。"""
    try:
        doc = fitz.open(str(pdf_path))
        pages = [page.get_text() for page in doc]
        doc.close()
        if not pages:
            return "", ""
        page1 = pages[0]
        # バイナリゴミ判定: printable比率が低い = スキャンPDF
        if sum(c.isprintable() for c in page1) / max(len(page1), 1) < 0.5:
            return "", ""
        return page1, "\n".join(pages)
    except Exception as e:
        print(f"  [ERR] {e}", file=sys.stderr)
        return "", ""

# ── SQLiteスキーマ ────────────────────────────────────────────
SCHEMA = """\
CREATE TABLE IF NOT EXISTS gijiroku (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    filename     TEXT    NOT NULL UNIQUE,
    gengou       TEXT,
    nendo_num    INTEGER,
    nendo        TEXT,
    kai          INTEGER,
    session_type TEXT,
    date_start   TEXT,
    date_end     TEXT,
    content      TEXT,
    is_readable  INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_nendo      ON gijiroku(nendo);
CREATE INDEX IF NOT EXISTS idx_session    ON gijiroku(session_type);
CREATE INDEX IF NOT EXISTS idx_datestart  ON gijiroku(date_start);
"""

# ── SQLエスケープ ─────────────────────────────────────────────
def esc(v) -> str:
    if v is None:
        return "NULL"
    if isinstance(v, int):
        return str(v)
    return "'" + str(v).replace("'", "''") + "'"

# ── メイン ───────────────────────────────────────────────────
def main():
    pdf_files = sorted(GIJIROKU_DIR.glob("*.pdf"))
    print(f"対象: {len(pdf_files)} ファイル")

    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    conn.commit()

    sql_lines = [
        "-- 宮古島市議会 議事録 SQLダンプ (CloudFlare D1 import用)",
        "",
        SCHEMA.rstrip(),
        "",
    ]

    ok = skip = 0
    for i, pdf in enumerate(pdf_files, 1):
        print(f"[{i:3d}/{len(pdf_files)}] {pdf.name:<45}", end="", flush=True)

        page1, full = extract_text(pdf)
        readable = 1 if full.strip() else 0

        meta = extract_metadata(page1) if readable else \
               dict(gengou=None, nendo_num=None, nendo=None,
                    kai=None, session_type=None, date_start=None, date_end=None)

        tag = (
            f"{meta['nendo'] or '?'} 第{meta['kai'] or '?'}回 "
            f"{meta['session_type'] or '?'}  "
            f"{meta['date_start'] or '?'} ~ {meta['date_end'] or '?'}"
        ) if readable else "【スキャンPDF - テキスト不可】"
        print(tag)

        try:
            conn.execute(
                "INSERT OR IGNORE INTO gijiroku "
                "(filename,gengou,nendo_num,nendo,kai,session_type,"
                " date_start,date_end,content,is_readable) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (pdf.name, meta["gengou"], meta["nendo_num"], meta["nendo"],
                 meta["kai"], meta["session_type"],
                 meta["date_start"], meta["date_end"],
                 full if readable else None, readable),
            )
        except Exception as e:
            print(f"  [DB ERR] {e}", file=sys.stderr)

        sql_lines.append(
            "INSERT OR IGNORE INTO gijiroku "
            "(filename,gengou,nendo_num,nendo,kai,session_type,"
            "date_start,date_end,content,is_readable) VALUES ("
            + ",".join([
                esc(pdf.name), esc(meta["gengou"]), esc(meta["nendo_num"]),
                esc(meta["nendo"]), esc(meta["kai"]), esc(meta["session_type"]),
                esc(meta["date_start"]), esc(meta["date_end"]),
                esc(full if readable else None), esc(readable),
            ]) + ");"
        )

        if readable: ok += 1
        else: skip += 1

    conn.commit()
    conn.close()

    SQL_PATH.write_text("\n".join(sql_lines), encoding="utf-8")

    print()
    print(f"完了  テキスト抽出成功: {ok} 件 / スキャンPDF: {skip} 件")
    print(f"  SQLite → {DB_PATH}")
    print(f"  SQL    → {SQL_PATH}")

if __name__ == "__main__":
    main()

