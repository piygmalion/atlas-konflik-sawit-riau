#!/usr/bin/env python3
"""CLI: sync website/data → Supabase.

Contoh:
  python sync_serving.py
  python sync_serving.py --only meta,kasus,polres
  python sync_serving.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Pastikan package app bisa diimpor saat dijalankan dari backend/
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.config import get_settings  # noqa: E402
from app.sync import list_local_datasets, sync_serving_to_supabase  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync serving layer ke Supabase")
    parser.add_argument(
        "--only",
        help="Dataset dipisah koma (meta,kasus,...)",
        default=None,
    )
    parser.add_argument(
        "--trigger",
        default="cli",
        help="Label trigger_source di sync_runs",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Hanya daftar file lokal, tanpa tulis ke Supabase",
    )
    args = parser.parse_args()

    settings = get_settings()
    print(f"DATA_DIR: {settings.data_path}")
    print(f"Supabase configured: {settings.supabase_configured}")

    local = list_local_datasets(settings.data_path)
    missing = [r["dataset"] for r in local if not r["exists"]]
    present = [r for r in local if r["exists"]]
    print(f"Lokal: {len(present)} ada, {len(missing)} hilang")
    if missing:
        print("  hilang:", ", ".join(missing))

    if args.dry_run:
        print(json.dumps(local, indent=2, ensure_ascii=False))
        return 0

    if not settings.supabase_configured:
        print(
            "ERROR: Isi SUPABASE_URL dan SUPABASE_SERVICE_ROLE_KEY di backend/.env",
            file=sys.stderr,
        )
        return 2

    only = [x.strip() for x in args.only.split(",") if x.strip()] if args.only else None
    result = sync_serving_to_supabase(
        settings=settings,
        trigger_source=args.trigger,
        only=only,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["status"] in {"success", "partial"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
