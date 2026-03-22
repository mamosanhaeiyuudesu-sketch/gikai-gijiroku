#!/usr/bin/env python3
"""
Step 5: sessions/ 内の各ファイルを OpenAI Vector Store にアップロードし
        会期名 → file_id の対応表 miyako-file-ids.json を生成する

前提:
  - 4_split_sessions.py を実行済みで sessions/ が存在すること
  - vectorstore_id.txt が存在すること (3_upload_vectorstore.py で作成)
    または --vs-id オプションで直接指定すること

使い方:
  export OPENAI_API_KEY=sk-...
  python3 5_upload_sessions.py
  python3 5_upload_sessions.py --vs-id vs_xxxx   # VS ID を直接指定

出力:
  miyako-file-ids.json  (会期名 → file_id の対応表)

再実行:
  すでに miyako-file-ids.json があれば未処理のファイルだけアップロードします。
"""

import argparse
import json
import sys
import time
from pathlib import Path

try:
    from openai import OpenAI
except ImportError:
    print("openai が必要です: pip install openai", file=sys.stderr)
    sys.exit(1)

SESSIONS_DIR  = Path(__file__).parent / "sessions"
VS_ID_PATH    = Path(__file__).parent / "vectorstore_id.txt"
MAPPING_PATH  = Path(__file__).parent / "miyako-file-ids.json"


def load_mapping() -> dict:
    if MAPPING_PATH.exists():
        return json.loads(MAPPING_PATH.read_text(encoding="utf-8"))
    return {}


def save_mapping(mapping: dict):
    MAPPING_PATH.write_text(
        json.dumps(mapping, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def session_name_from_filename(filename: str) -> str:
    """'令和元年第6回臨時会.txt' → '令和元年第6回臨時会'"""
    return Path(filename).stem


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--vs-id", help="Vector Store ID (省略時は vectorstore_id.txt から読む)")
    args = parser.parse_args()

    # Vector Store ID の取得
    if args.vs_id:
        vs_id = args.vs_id.strip()
    elif VS_ID_PATH.exists():
        vs_id = VS_ID_PATH.read_text(encoding="utf-8").strip()
    else:
        print(
            "[ERR] Vector Store ID が不明です。\n"
            "  --vs-id vs_xxxx で指定するか、\n"
            "  先に 3_upload_vectorstore.py を実行して vectorstore_id.txt を作成してください。",
            file=sys.stderr,
        )
        sys.exit(1)

    if not SESSIONS_DIR.exists():
        print(f"[ERR] {SESSIONS_DIR} が見つかりません。先に 4_split_sessions.py を実行してください。", file=sys.stderr)
        sys.exit(1)

    session_files = sorted(SESSIONS_DIR.glob("*.txt"))
    if not session_files:
        print(f"[ERR] {SESSIONS_DIR} に .txt ファイルがありません。", file=sys.stderr)
        sys.exit(1)

    client = OpenAI()
    mapping = load_mapping()

    already_done = set(mapping.keys())
    targets = [f for f in session_files if session_name_from_filename(f.name) not in already_done]

    print(f"Vector Store: {vs_id}")
    print(f"対象ファイル: {len(session_files)} 件 (未処理: {len(targets)} 件)")
    print()

    for i, fpath in enumerate(targets, 1):
        session_name = session_name_from_filename(fpath.name)
        print(f"[{i}/{len(targets)}] {session_name}  ({fpath.stat().st_size / 1024:.1f} KB) ", end="", flush=True)

        # ── Files API にアップロード ──────────────────────────────
        with open(fpath, "rb") as f:
            file_obj = client.files.create(file=(fpath.name, f, "text/plain"), purpose="assistants")
        file_id = file_obj.id
        print(f"→ {file_id}  ", end="", flush=True)

        # ── Vector Store にアタッチ ───────────────────────────────
        client.vector_stores.files.create(vector_store_id=vs_id, file_id=file_id)
        print("✓")

        mapping[session_name] = file_id
        save_mapping(mapping)  # 1件ごとに保存（途中失敗に備える）

        # レート制限を避けるため少し待機
        if i < len(targets):
            time.sleep(0.3)

    print()
    print(f"完了: {len(mapping)} 件の対応表を保存しました")
    print(f"  → {MAPPING_PATH}")
    print()
    print("検索時の使い方:")
    print('  mapping = json.load(open("miyako-file-ids.json"))')
    print('  file_id = mapping["令和3年第9回定例会"]')
    print('  # filters={"type": "eq", "key": "file_id", "value": file_id}')


if __name__ == "__main__":
    main()
