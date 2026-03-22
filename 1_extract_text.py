#!/usr/bin/env python3
"""
Step 1: PDFから全文テキストを抽出し、1つのファイルに結合する

出力:
  gijiroku_all.txt  - 全会期のテキスト（ヘッダー付き）

使い方:
  python3 1_extract_text.py

依存:
  pip install pymupdf
"""

import re
import sys
from pathlib import Path

try:
    import fitz
except ImportError:
    print("PyMuPDF が必要です: pip install pymupdf", file=sys.stderr)
    sys.exit(1)

GIJIROKU_DIR = Path(__file__).parent / "gijiroku"
OUTPUT_PATH  = Path(__file__).parent / "gijiroku_all.txt"

_ZEN_TO_HAN = str.maketrans("０１２３４５６７８９", "0123456789")
GENGOU_BASE = {"明治": 1868, "大正": 1912, "昭和": 1926, "平成": 1989, "令和": 2019}


def wareki_to_seireki(gengou: str, nen: int) -> int:
    return GENGOU_BASE.get(gengou, 0) + nen - 1


def normalize_year_num(s: str) -> int:
    s = s.strip().translate(_ZEN_TO_HAN)
    return 1 if s == "元" else int(s)


def parse_japanese_date(text: str):
    text = text.translate(_ZEN_TO_HAN)
    m = re.search(
        r"(明治|大正|昭和|平成|令和)\s*(元|\d+)\s*年\s*(\d+)\s*月\s*(\d+)\s*日", text
    )
    if not m:
        return None
    year = wareki_to_seireki(m.group(1), normalize_year_num(m.group(2)))
    return f"{year:04d}-{int(m.group(3)):02d}-{int(m.group(4)):02d}"


def extract_metadata(page1: str) -> dict:
    t = page1.translate(_ZEN_TO_HAN)

    meta = dict(nendo=None, kai=None, session_type=None, date_start=None, date_end=None)

    m = re.search(r"(明\s*治|大\s*正|昭\s*和|平\s*成|令\s*和)\s*(元|\d+)\s*年", t)
    if m:
        gengou = m.group(1).replace(" ", "")
        num    = normalize_year_num(m.group(2))
        meta["nendo"] = f"{gengou}{m.group(2).strip()}年"

    m = re.search(r"第\s*(\d+)\s*回", t)
    if m:
        meta["kai"] = int(m.group(1))

    if "定例会" in t:
        meta["session_type"] = "定例会"
    elif "臨時会" in t:
        meta["session_type"] = "臨時会"

    _DATE_PAT = r"(?:明治|大正|昭和|平成|令和)\s*(?:元|\d+)\s*年\s*\d+\s*月\s*\d+\s*日"
    m_s = re.search(r"自\s*(" + _DATE_PAT + r")", t)
    m_e = re.search(r"至\s*(" + _DATE_PAT + r")", t)
    if m_s:
        meta["date_start"] = parse_japanese_date(m_s.group(1))
    if m_e:
        meta["date_end"]   = parse_japanese_date(m_e.group(1))

    if meta["date_start"] is None:
        dates = re.findall(
            r"((?:明\s*治|大\s*正|昭\s*和|平\s*成|令\s*和)\s*(?:元|\d+)\s*年\s*\d+\s*月\s*\d+\s*日)", t
        )
        for d in dates:
            parsed = parse_japanese_date(d.replace(" ", ""))
            if parsed:
                meta["date_start"] = parsed
                meta["date_end"]   = parsed
                break

    return meta


def extract_text(pdf_path: Path):
    """(page1_text, full_text)。スキャンPDFは ("", "")。"""
    try:
        doc   = fitz.open(str(pdf_path))
        pages = [page.get_text() for page in doc]
        doc.close()
        if not pages:
            return "", ""
        page1 = pages[0]
        if sum(c.isprintable() for c in page1) / max(len(page1), 1) < 0.5:
            return "", ""
        return page1, "\n".join(pages)
    except Exception as e:
        print(f"  [ERR] {e}", file=sys.stderr)
        return "", ""


def make_header(filename: str, meta: dict) -> str:
    nendo   = meta["nendo"]   or "年度不明"
    kai     = f"第{meta['kai']}回" if meta["kai"] else "回不明"
    stype   = meta["session_type"] or "種別不明"
    d_start = meta["date_start"] or "?"
    d_end   = meta["date_end"]   or "?"

    date_str = d_start if d_start == d_end else f"{d_start}〜{d_end}"
    return f"\n\n==== {nendo} {kai} {stype} {date_str} ====\n"


def main():
    pdf_files = sorted(GIJIROKU_DIR.glob("*.pdf"))
    print(f"対象: {len(pdf_files)} ファイル")

    ok = skip = 0
    chunks = []

    for i, pdf in enumerate(pdf_files, 1):
        print(f"[{i:3d}/{len(pdf_files)}] {pdf.name:<45}", end="", flush=True)

        page1, full = extract_text(pdf)

        if not full.strip():
            print("【スキャンPDF - スキップ】")
            skip += 1
            continue

        meta   = extract_metadata(page1)
        header = make_header(pdf.name, meta)
        chunks.append(header + full.strip())

        print(f"{meta['nendo'] or '?'} {meta['session_type'] or '?'}  {meta['date_start'] or '?'}")
        ok += 1

    OUTPUT_PATH.write_text("\n".join(chunks), encoding="utf-8")

    size_mb = OUTPUT_PATH.stat().st_size / 1024 / 1024
    print()
    print(f"完了  抽出: {ok} 件 / スキャンPDF: {skip} 件")
    print(f"  → {OUTPUT_PATH}  ({size_mb:.1f} MB)")


if __name__ == "__main__":
    main()
