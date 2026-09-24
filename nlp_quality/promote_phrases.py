"""Idempotently promote the validated phrase artifact to intent_phrases."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import mysql.connector
from config import DB_CONFIG


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--approved", type=Path, default=Path(__file__).with_name("approved_phrases.json"))
    parser.add_argument("--backup-dir", type=Path, default=Path(__file__).parent)
    parser.add_argument("--apply", action="store_true", help="Without this flag, validate and report only")
    args = parser.parse_args()
    approved = json.loads(args.approved.read_text(encoding="utf-8"))
    unique = {(row["intent"], row["phrase"]): row for row in approved}
    if len(unique) != len(approved):
        raise SystemExit("approved_phrases.json contains duplicate intent/phrase rows")

    connection = mysql.connector.connect(**DB_CONFIG)
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute("SELECT intent_name, phrase, source, added_at, added_by FROM intent_phrases ORDER BY id")
        before = cursor.fetchall()
        stamp = time.strftime("%Y%m%dT%H%M%S")
        backup_path = args.backup_dir / f"intent_phrases_pre_promotion_{stamp}.json"
        for row in before:
            if row.get("added_at") is not None:
                row["added_at"] = row["added_at"].isoformat()
        backup_path.write_text(json.dumps({"exported_at": stamp, "rows": before}, indent=2), encoding="utf-8")

        existing = {(row["intent_name"], row["phrase"]) for row in before}
        pending = [row for key, row in unique.items() if key not in existing]
        print(json.dumps({"approved": len(approved), "already_present": len(approved) - len(pending),
                          "pending": len(pending), "backup": str(backup_path), "apply": args.apply}, indent=2))
        if not args.apply:
            return
        cursor.executemany(
            "INSERT INTO intent_phrases (intent_name, phrase, source, added_by) VALUES (%s, %s, %s, %s)",
            [(row["intent"], row["phrase"], row["source"], row["added_by"]) for row in pending],
        )
        connection.commit()
        cursor.execute("SELECT COUNT(*) AS n FROM intent_phrases")
        final_count = cursor.fetchone()["n"]
        cursor.execute(
            "SELECT COUNT(*) AS n FROM intent_phrases WHERE added_by=%s",
            ("nlp-quality-2026-09-25",),
        )
        promoted_count = cursor.fetchone()["n"]
        if promoted_count != len(approved):
            raise RuntimeError(f"post-write verification failed: expected {len(approved)}, found {promoted_count}")
        print(json.dumps({"inserted": len(pending), "verified_promoted": promoted_count,
                          "final_phrase_count": final_count}, indent=2))
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
        connection.close()


if __name__ == "__main__":
    main()
