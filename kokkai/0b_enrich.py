#!/usr/bin/env python3
"""
Step 0b: meeting_list で取得したJSONファイル（発言テキストなし）を
         meeting API で全文取得して上書きする

使い方:
  python3 kokkai/0b_enrich.py

依存:
  pip install requests
"""

import json
import sys
import time
from pathlib import Path

try:
    import requests
except ImportError:
    print("requests が必要です: pip install requests", file=sys.stderr)
    sys.exit(1)

API_BASE  = "https://kokkai.ndl.go.jp/api"
SAVE_DIR  = Path(__file__).parent.parent / "kokkai_data" / "meetings"
SLEEP_SEC = 0.5


def fetch_full_meeting(issue_id: str):
    params = {
        "issueID":       issue_id,
        "recordPacking": "json",
    }
    try:
        resp = requests.get(f"{API_BASE}/meeting", params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        print(f"  [ERR] {issue_id}: {e}", file=sys.stderr)
        return None
    except json.JSONDecodeError as e:
        print(f"  [ERR] JSONパース失敗 {issue_id}: {e}", file=sys.stderr)
        return None

    records = data.get("meetingRecord", [])
    return records[0] if records else None


def has_speech_text(meeting: dict) -> bool:
    """発言テキストが1件でも含まれているか確認する"""
    for speech in meeting.get("speechRecord", []):
        if speech.get("speech"):
            return True
    return False


def main():
    json_files = sorted(SAVE_DIR.glob("*.json"))

    if not json_files:
        print(f"[ERR] {SAVE_DIR} にJSONファイルが見つかりません。", file=sys.stderr)
        sys.exit(1)

    # 発言テキストが未取得のファイルだけ対象にする
    targets = []
    for jf in json_files:
        try:
            meeting = json.loads(jf.read_text(encoding="utf-8"))
        except Exception:
            targets.append(jf)
            continue
        if not has_speech_text(meeting):
            targets.append(jf)

    print(f"全 {len(json_files)} 件中、未取得: {len(targets)} 件")

    ok = error = skipped = 0

    for i, jf in enumerate(targets, 1):
        try:
            meeting = json.loads(jf.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"[{i:4d}/{len(targets)}] 読込エラー: {jf.name}: {e}")
            error += 1
            continue

        issue_id = meeting.get("issueID", "")
        print(f"[{i:4d}/{len(targets)}] {jf.name[:60]}", end="", flush=True)

        full = fetch_full_meeting(issue_id)
        if full is None:
            print(" [SKIP]")
            error += 1
            time.sleep(SLEEP_SEC)
            continue

        jf.write_text(json.dumps(full, ensure_ascii=False, indent=2), encoding="utf-8")
        n_speech = sum(1 for s in full.get("speechRecord", []) if s.get("speech"))
        print(f" 発言テキスト: {n_speech}件")
        ok += 1
        time.sleep(SLEEP_SEC)

    print()
    print(f"完了  更新: {ok} 件 / エラー: {error} 件 / スキップ: {skipped} 件")


if __name__ == "__main__":
    main()
