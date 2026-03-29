#!/usr/bin/env python3
"""
Step 4: kokkai_all.txt を会議ごとのファイルに分割する

入力:  kokkai_all.txt  (1_format.py の出力)
出力:  sessions/ ディレクトリ内の .txt ファイル群
       例: sessions/第213回_衆議院_本会議_第1号_2024-01-26.txt

使い方:
  python3 kokkai/4_split_sessions.py
"""

import re
import sys
from pathlib import Path

INPUT_PATH = Path(__file__).parent / "kokkai_all.txt"
OUTPUT_DIR = Path(__file__).parent / "sessions"

# ==== 第213回 衆議院 本会議 第1号 2024-01-26 ====
HEADER_RE = re.compile(r"^==== (.+?) \d{4}-\d{2}-\d{2} ====$")


def session_name_to_filename(name: str) -> str:
    """
    '第213回 衆議院 本会議 第1号' → '第213回_衆議院_本会議_第1号.txt'
    スペースをアンダースコアに変換してファイル名にする。
    """
    return name.replace(" ", "_") + ".txt"


def main():
    if not INPUT_PATH.exists():
        print(f"[ERR] {INPUT_PATH} が見つかりません。先に 1_format.py を実行してください。", file=sys.stderr)
        sys.exit(1)

    OUTPUT_DIR.mkdir(exist_ok=True)

    current_name: str | None = None
    current_lines: list[str] = []
    saved = 0
    skipped = 0

    def flush():
        nonlocal saved, skipped, current_name, current_lines
        if current_name is None:
            return
        filename = session_name_to_filename(current_name)
        out_path = OUTPUT_DIR / filename
        text = "".join(current_lines).strip()
        if text:
            out_path.write_text(text + "\n", encoding="utf-8")
            saved += 1
            print(f"  保存: {filename}  ({len(text):,} chars)")
        else:
            skipped += 1
        current_lines = []

    print(f"読み込み中: {INPUT_PATH}  ({INPUT_PATH.stat().st_size / 1024 / 1024:.1f} MB)")

    with open(INPUT_PATH, encoding="utf-8") as f:
        for line in f:
            m = HEADER_RE.match(line.rstrip("\n"))
            if m:
                flush()
                current_name = m.group(1)
                # ヘッダー行もファイルに含める
                current_lines = [line]
            else:
                current_lines.append(line)

    flush()  # 最後の会議

    print()
    print(f"完了: {saved} ファイル保存  ({skipped} スキップ)")
    print(f"  → {OUTPUT_DIR}/")


if __name__ == "__main__":
    main()
