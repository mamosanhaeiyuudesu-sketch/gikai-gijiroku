#!/usr/bin/env python3
"""
SQLite → Cloudflare D1 データ移行スクリプト
wrangler d1 execute を使って分割バッチで挿入する
"""
import sqlite3
import subprocess
import sys
import os
import tempfile
import math

# 設定
SQLITE_DB = "gijiroku_all.db"
D1_DB_NAME = "miyako-gijiroku"
BATCH_SIZE = 100   # 1回のexecuteで送るINSERT文数
MAX_CONTENT = 8000  # D1のステートメントサイズ制限対策（文字数）

def esc(v):
    if v is None:
        return "NULL"
    return "'" + str(v).replace("'", "''") + "'"

def run_d1(sql_file: str, label: str = "", retries: int = 5):
    """wrangler d1 execute でSQLファイルを実行（リトライあり）"""
    import time
    cmd = [
        "wrangler", "d1", "execute", D1_DB_NAME,
        "--remote",
        "--file", sql_file,
    ]
    for attempt in range(1, retries + 1):
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            return True
        err = result.stderr[-300:]
        # リトライ可能なエラー
        if any(k in err for k in ["fetch failed", "Please retry", "timeout", "ETIMEDOUT", "ECONNRESET"]):
            wait = attempt * 5
            print(f"\n  [retry {attempt}/{retries}] {wait}s待機...", end=" ", flush=True)
            time.sleep(wait)
            continue
        # リトライ不可なエラー
        print(f"[!] エラー ({label}): {err}", file=sys.stderr)
        return False
    print(f"[!] リトライ上限超過 ({label})", file=sys.stderr)
    return False

def export_sessions(conn):
    rows = conn.execute("SELECT * FROM sessions ORDER BY session_date").fetchall()
    stmts = []
    for r in rows:
        vals = ", ".join(esc(v) for v in r)
        stmts.append(
            f"INSERT OR IGNORE INTO sessions VALUES ({vals});"
        )
    return stmts

def export_bills(conn):
    rows = conn.execute("SELECT * FROM bills ORDER BY session_id, bill_id").fetchall()
    stmts = []
    for r in rows:
        vals = ", ".join(esc(v) for v in r)
        stmts.append(
            f"INSERT OR IGNORE INTO bills VALUES ({vals});"
        )
    return stmts

def export_utterances(conn):
    # utterance_id も含めて全カラムを明示的にINSERT（冪等性のため）
    rows = conn.execute(
        "SELECT utterance_id, session_id, bill_id, seq, date, speaker_name, speaker_name_raw, "
        "speaker_role, speaker_party, speaker_faction, speaker_gender, "
        "speaker_term, utterance_type, content "
        "FROM utterances ORDER BY utterance_id"
    ).fetchall()
    stmts = []
    for r in rows:
        lst = list(r)
        # contentをMAX_CONTENTに切り詰め（D1の1ステートメントサイズ制限対策）
        if lst[-1] and len(lst[-1]) > MAX_CONTENT:
            lst[-1] = lst[-1][:MAX_CONTENT]
        vals = ", ".join(esc(v) for v in lst)
        stmts.append(
            "INSERT OR IGNORE INTO utterances "
            "(utterance_id, session_id, bill_id, seq, date, speaker_name, speaker_name_raw, "
            "speaker_role, speaker_party, speaker_faction, speaker_gender, "
            "speaker_term, utterance_type, content) "
            f"VALUES ({vals});"
        )
    return stmts

def execute_in_batches(stmts: list[str], label: str):
    total = len(stmts)
    batches = math.ceil(total / BATCH_SIZE)
    print(f"[+] {label}: {total}件 → {batches}バッチに分割", file=sys.stderr)

    for i in range(batches):
        chunk = stmts[i * BATCH_SIZE: (i + 1) * BATCH_SIZE]
        sql_content = "\n".join(chunk) + "\n"

        with tempfile.NamedTemporaryFile(mode="w", suffix=".sql", delete=False, encoding="utf-8") as f:
            f.write(sql_content)
            tmp_path = f.name

        try:
            batch_label = f"{label} batch {i+1}/{batches}"
            print(f"  [{i+1}/{batches}] 実行中...", end=" ", flush=True)
            ok = run_d1(tmp_path, batch_label)
            print("✓" if ok else "✗")
            if not ok:
                print(f"  失敗したSQL（先頭）: {sql_content[:200]}", file=sys.stderr)
                return False
        finally:
            os.unlink(tmp_path)

    return True

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-sessions", action="store_true")
    parser.add_argument("--skip-bills", action="store_true")
    parser.add_argument("--utterance-start-batch", type=int, default=1,
                        help="utterancesの開始バッチ番号（再開用）")
    args = parser.parse_args()

    if not os.path.exists(SQLITE_DB):
        print(f"[!] DBが見つかりません: {SQLITE_DB}", file=sys.stderr)
        sys.exit(1)

    conn = sqlite3.connect(SQLITE_DB)

    print("=== Cloudflare D1 データ移行 ===", file=sys.stderr)
    print(f"  ソース : {SQLITE_DB}", file=sys.stderr)
    print(f"  ターゲット: {D1_DB_NAME}", file=sys.stderr)

    if not args.skip_sessions:
        sessions_stmts = export_sessions(conn)
        ok = execute_in_batches(sessions_stmts, "sessions")
        if not ok:
            sys.exit(1)
    else:
        print("[skip] sessions", file=sys.stderr)

    if not args.skip_bills:
        bills_stmts = export_bills(conn)
        ok = execute_in_batches(bills_stmts, "bills")
        if not ok:
            sys.exit(1)
    else:
        print("[skip] bills", file=sys.stderr)

    # utterances（大量なので分割）
    utterances_stmts = export_utterances(conn)
    total = len(utterances_stmts)
    batches = math.ceil(total / BATCH_SIZE)
    start = args.utterance_start_batch - 1  # 0-indexed
    print(f"[+] utterances: {total}件 → {batches}バッチに分割 (batch {start+1}から開始)", file=sys.stderr)

    for i in range(start, batches):
        chunk = utterances_stmts[i * BATCH_SIZE: (i + 1) * BATCH_SIZE]
        sql_content = "\n".join(chunk) + "\n"

        with tempfile.NamedTemporaryFile(mode="w", suffix=".sql", delete=False, encoding="utf-8") as f:
            f.write(sql_content)
            tmp_path = f.name

        try:
            print(f"  [{i+1}/{batches}] 実行中...", end=" ", flush=True)
            ok = run_d1(tmp_path, f"utterances batch {i+1}/{batches}")
            print("✓" if ok else "✗")
            if not ok:
                print(f"  → 再開するには: --skip-sessions --skip-bills --utterance-start-batch {i+1}", file=sys.stderr)
                conn.close()
                sys.exit(1)
        finally:
            os.unlink(tmp_path)

    conn.close()
    print("\n=== 完了 ===", file=sys.stderr)

if __name__ == "__main__":
    main()
