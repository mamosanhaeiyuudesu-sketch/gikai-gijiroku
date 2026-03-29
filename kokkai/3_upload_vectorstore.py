#!/usr/bin/env python3
"""
Step 3: テキストを OpenAI Vector Store にアップロードする

入力:  kokkai_all.txt  (1_format.py の出力)
出力:  vectorstore_id.txt (作成された Vector Store の ID)

使い方:
  export OPENAI_API_KEY=sk-...
  python3 kokkai/3_upload_vectorstore.py

依存:
  pip install openai
"""

import sys
import time
from pathlib import Path

try:
    from openai import OpenAI
except ImportError:
    print("openai が必要です: pip install openai", file=sys.stderr)
    sys.exit(1)

INPUT_PATH  = Path(__file__).parent / "kokkai_all.txt"
ID_PATH     = Path(__file__).parent / "vectorstore_id.txt"

VECTOR_STORE_NAME = "国会会議録"


def main():
    if not INPUT_PATH.exists():
        print(f"[ERR] {INPUT_PATH} が見つかりません。先に 1_format.py を実行してください。")
        sys.exit(1)

    client = OpenAI()  # OPENAI_API_KEY 環境変数を使用

    # ── Vector Store 作成 ─────────────────────────────────────
    print(f"Vector Store 作成中: {VECTOR_STORE_NAME}")
    vs = client.vector_stores.create(name=VECTOR_STORE_NAME)
    vs_id = vs.id
    print(f"  → ID: {vs_id}")

    # ── ファイルアップロード ───────────────────────────────────
    print(f"ファイルアップロード中: {INPUT_PATH.name}  ({INPUT_PATH.stat().st_size / 1024 / 1024:.1f} MB)")
    with open(INPUT_PATH, "rb") as f:
        batch = client.vector_stores.file_batches.upload_and_poll(
            vector_store_id=vs_id,
            files=[("kokkai_all.txt", f, "text/plain")],
        )

    print(f"  ステータス: {batch.status}")
    print(f"  ファイル数: {batch.file_counts.completed} / {batch.file_counts.total}")

    if batch.status != "completed":
        print(f"[WARN] 完了していません: {batch.status}")

    # ── ID を保存 ─────────────────────────────────────────────
    ID_PATH.write_text(vs_id, encoding="utf-8")
    print()
    print(f"完了  Vector Store ID: {vs_id}")
    print(f"  → {ID_PATH}")
    print()
    print("次のステップ: このIDをフロントエンドの RAG クエリに使用してください")
    print(f'  例: client.responses.create(tools=[{{"type":"file_search","vector_store_ids":["{vs_id}"]}}], ...)')


if __name__ == "__main__":
    main()
