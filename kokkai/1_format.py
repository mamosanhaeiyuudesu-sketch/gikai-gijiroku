#!/usr/bin/env python3
"""
Step 1: 取得済みJSONファイルを1つのテキストファイルに結合する

入力:  meetings/*.json  (0_fetch.py の出力)
出力:  kokkai_all.txt   (宮古島版 gijiroku_all.txt と同形式)

出力フォーマット:
  ==== 第213回 衆議院 本会議 第1号 2024-01-26 ====

  ◎議長（額賀福志郎君）
  　発言内容...

使い方:
  python3 kokkai/1_format.py

依存:
  （標準ライブラリのみ）
"""

import json
import re
import sys
from pathlib import Path

MEETINGS_DIR = Path(__file__).parent / "meetings"
OUTPUT_PATH  = Path(__file__).parent / "kokkai_all.txt"


def make_header(meeting: dict) -> str:
    """会議情報からヘッダー文字列を生成する"""
    session      = meeting.get("session", "?")
    house        = meeting.get("nameOfHouse", "?")
    meeting_name = meeting.get("nameOfMeeting", "?")
    issue        = meeting.get("issue", "?")
    date         = meeting.get("date", "?")

    return f"\n\n==== 第{session}回 {house} {meeting_name} {issue} {date} ====\n"


def format_speaker_marker(speech: dict) -> str:
    """
    発言者情報から ◎マーカー行を生成する。

    役職あり: ◎内閣総理大臣（岸田文雄君）
    役職なし: ◎山田太郎君
    """
    speaker  = (speech.get("speaker") or "").strip()
    role     = (speech.get("speakerRole") or "").strip()

    if not speaker:
        return "◎（発言者不明君）"

    # 「君」が既に含まれている場合はそのまま
    if speaker.endswith("君"):
        base = speaker[:-1]
    else:
        base = speaker

    if role:
        return f"◎{role}（{base}君）"
    else:
        return f"◎{base}君"


def format_meeting(meeting: dict) -> str:
    """1会議分のテキストを整形して返す"""
    header  = make_header(meeting)
    speeches = meeting.get("speechRecord", [])

    lines = [header]

    for speech in speeches:
        marker = format_speaker_marker(speech)
        text   = (speech.get("speech") or "").strip()

        lines.append(f"\n{marker}")
        if text:
            lines.append(text)

    return "\n".join(lines)


def parse_sort_key(path: Path) -> tuple:
    """
    ファイル名 YYYYMMDD_... から日付・会議番号を取り出してソートキーを返す。
    """
    name = path.stem  # 拡張子なし
    parts = name.split("_")

    date_str = parts[0] if parts else "00000000"
    # ファイル名末尾の issueID（数値部分）を副ソートキーとして使う
    m = re.search(r"(\d+)$", name)
    num = int(m.group(1)) if m else 0

    return (date_str, num)


def main():
    json_files = sorted(MEETINGS_DIR.glob("*.json"), key=parse_sort_key)

    if not json_files:
        print(
            f"[ERR] {MEETINGS_DIR} にJSONファイルが見つかりません。"
            "先に 0_fetch.py を実行してください。",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"対象: {len(json_files)} ファイル")

    chunks = []
    ok = error = 0

    for i, jf in enumerate(json_files, 1):
        print(f"[{i:4d}/{len(json_files)}] {jf.name:<70}", end="", flush=True)

        try:
            meeting = json.loads(jf.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"【読込エラー: {e}】")
            error += 1
            continue

        text = format_meeting(meeting)
        chunks.append(text)

        date  = meeting.get("date", "?")
        house = meeting.get("nameOfHouse", "?")
        mname = meeting.get("nameOfMeeting", "?")
        n_sp  = len(meeting.get("speechRecord", []))
        print(f"{date} {house} {mname}  発言{n_sp}件")
        ok += 1

    OUTPUT_PATH.write_text("\n".join(chunks), encoding="utf-8")

    size_mb = OUTPUT_PATH.stat().st_size / 1024 / 1024
    print()
    print(f"完了  整形: {ok} 件 / エラー: {error} 件")
    print(f"  → {OUTPUT_PATH}  ({size_mb:.1f} MB)")


if __name__ == "__main__":
    main()
