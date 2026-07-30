#!/usr/bin/env python3
"""Apply SQL migrations to Supabase via PostgREST rpc helper or psycopg if DATABASE_URL set.

Prefer SUPABASE_DB_URL / DATABASE_URL. Fallback: print SQL path for dashboard.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

HERE = Path(__file__).resolve().parent
load_dotenv(HERE / ".env")

MIG_DIR = HERE / "supabase" / "migrations"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", help="Specific migration filename")
    parser.add_argument("--print-only", action="store_true")
    args = parser.parse_args()

    files = sorted(MIG_DIR.glob("*.sql"))
    if args.file:
        files = [MIG_DIR / args.file]
    for f in files:
        if not f.exists():
            print(f"missing {f}", file=sys.stderr)
            return 2
        sql = f.read_text(encoding="utf-8")
        print(f"=== {f.name} ({len(sql)} chars) ===")
        if args.print_only:
            continue
        db_url = os.getenv("SUPABASE_DB_URL") or os.getenv("DATABASE_URL")
        if not db_url:
            print(
                "No SUPABASE_DB_URL/DATABASE_URL — paste SQL in Supabase SQL Editor:\n"
                f"  {f}",
                file=sys.stderr,
            )
            # Still success for CI/docs; caller may apply via dashboard
            continue
        try:
            import psycopg

            with psycopg.connect(db_url) as conn:
                conn.execute(sql)
                conn.commit()
            print(f"  applied {f.name}")
        except ImportError:
            print("psycopg not installed; pip install psycopg[binary]", file=sys.stderr)
            return 2
        except Exception as exc:
            print(f"FAIL apply {f.name}: {exc}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
