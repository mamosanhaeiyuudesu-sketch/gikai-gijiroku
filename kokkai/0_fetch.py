#!/usr/bin/env python3
"""
Step 0: 国会会議録検索システムAPIから議事録を取得する

出力:
  meetings/YYYYMMDD_<院名>_<会議名>_<号>.json  - 会議ごとのJSONファイル

使い方:
  python3 kokkai/0_fetch.py [オプション]

例:
  # 第213回国会（衆議院）の本会議をすべて取得
  python3 kokkai/0_fetch.py --session 213 --house 衆議院 --meeting 本会議

  # 日付範囲で取得
  python3 kokkai/0_fetch.py --from 2024-01-01 --until 2024-06-30

  # 両院・全会議を取得（件数が多い場合は時間がかかる）
  python3 kokkai/0_fetch.py --session 213

依存:
  pip install requests
"""

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

try:
    import requests
except ImportError:
    print("requests が必要です: pip install requests", file=sys.stderr)
    sys.exit(1)

API_BASE   = "https://kokkai.ndl.go.jp/api"
SAVE_DIR   = Path(__file__).parent / "meetings"
MAX_RECORDS = 100    # APIの最大取得件数
SLEEP_SEC  = 0.5     # リクエスト間隔（秒）


def fetch_meetings(params: dict) -> list[dict]:
    """
    国会会議録APIから全件を取得して返す（ページネーション対応）。

    params: APIリクエストパラメータ（startRecord / maximumRecords は自動付与）
    """
    all_meetings = []
    start = 1

    while True:
        req_params = {
            **params,
            "maximumRecords": MAX_RECORDS,
            "startRecord":    start,
            "recordPacking":  "json",
        }

        try:
            resp = requests.get(f"{API_BASE}/meeting", params=req_params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as e:
            print(f"  [ERR] APIリクエスト失敗: {e}", file=sys.stderr)
            break
        except json.JSONDecodeError as e:
            print(f"  [ERR] JSONパース失敗: {e}", file=sys.stderr)
            break

        records = data.get("meetingRecord", [])
        all_meetings.extend(records)

        total   = int(data.get("numberOfRecords", 0))
        fetched = len(all_meetings)
        print(f"  取得中: {fetched}/{total} 件", flush=True)

        next_pos = data.get("nextRecordPosition")
        if not next_pos or fetched >= total:
            break

        start = int(next_pos)
        time.sleep(SLEEP_SEC)

    return all_meetings


def safe_filename(s: str) -> str:
    """ファイル名に使えない文字を除去する"""
    return re.sub(r'[\\/:*?"<>|]', "_", s).strip()


def save_meeting(meeting: dict) -> Path:
    """
    1会議分のJSONを保存する。

    ファイル名: YYYYMMDD_<院名>_<会議名>_<号>_<issueID>.json
    """
    date         = meeting.get("date", "00000000").replace("-", "")
    house        = safe_filename(meeting.get("nameOfHouse", "不明"))
    meeting_name = safe_filename(meeting.get("nameOfMeeting", "不明"))
    issue        = safe_filename(meeting.get("issue", ""))
    issue_id     = meeting.get("issueID", "")

    fname = f"{date}_{house}_{meeting_name}_{issue}_{issue_id}.json"
    path  = SAVE_DIR / fname

    path.write_text(json.dumps(meeting, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def main():
    parser = argparse.ArgumentParser(
        description="国会会議録APIから議事録を取得してJSONで保存する"
    )
    parser.add_argument("--session",  type=int,   help="国会回次（例: 213）")
    parser.add_argument("--house",    type=str,   help="院名（衆議院 / 参議院 / 両院）")
    parser.add_argument("--meeting",  type=str,   help="会議名（例: 本会議）")
    parser.add_argument("--from",     dest="from_date", type=str, help="検索開始日 YYYY-MM-DD")
    parser.add_argument("--until",    dest="until_date", type=str, help="検索終了日 YYYY-MM-DD")
    parser.add_argument("--speaker",  type=str,   help="発言者名")
    parser.add_argument("--any",      type=str,   help="フリーワード検索")
    args = parser.parse_args()

    # クエリパラメータ組み立て
    params: dict = {}
    if args.session:
        params["session"] = args.session
    if args.house:
        params["nameOfHouse"] = args.house
    if args.meeting:
        params["nameOfMeeting"] = args.meeting
    if args.from_date:
        params["from"] = args.from_date
    if args.until_date:
        params["until"] = args.until_date
    if args.speaker:
        params["speaker"] = args.speaker
    if args.any:
        params["any"] = args.any

    if not params:
        parser.error("検索条件を最低1つ指定してください（例: --session 213）")

    SAVE_DIR.mkdir(parents=True, exist_ok=True)
    print(f"保存先: {SAVE_DIR}")
    print(f"検索条件: {params}")

    print("APIから取得中...")
    meetings = fetch_meetings(params)

    if not meetings:
        print("該当する会議録が見つかりませんでした。")
        return

    print(f"\n{len(meetings)} 件の会議録を保存中...")
    saved = skipped = 0

    for meeting in meetings:
        issue_id = meeting.get("issueID", "")

        # 同一 issueID のファイルが存在すればスキップ
        existing = list(SAVE_DIR.glob(f"*_{issue_id}.json"))
        if existing:
            skipped += 1
            continue

        path = save_meeting(meeting)
        print(f"  保存: {path.name}")
        saved += 1

    print()
    print(f"完了  保存: {saved} 件 / スキップ（既存）: {skipped} 件")
    print(f"  → {SAVE_DIR}/")


if __name__ == "__main__":
    main()
