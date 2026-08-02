#!/usr/bin/env python3
"""Tulis silver/ingest_run.json dari meta_sumber + checksum SoT.

Dipanggil setelah build_entity_matches (atau standalone). Frontend tidak membaca
file ini; dipakai observability + sync_silver --integration.
"""

from __future__ import annotations

import csv
import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve()
SITE = HERE.parents[1]
DATA = SITE / "data"
SILVER = DATA / "silver"
ROOT = SITE.parent


def _sha12(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:12]


def _row_count(path: Path) -> int | None:
    if not path.exists():
        return None
    suffix = path.suffix.lower()
    if suffix == ".csv":
        with path.open(encoding="utf-8-sig", newline="") as f:
            return sum(1 for _ in csv.DictReader(f))
    if suffix == ".json":
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
        if isinstance(payload, dict) and isinstance(payload.get("records"), list):
            return len(payload["records"])
        if isinstance(payload, list):
            return len(payload)
        return 1
    if suffix in {".geojson", ".topojson"}:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
        feats = payload.get("features") if isinstance(payload, dict) else None
        return len(feats) if isinstance(feats, list) else None
    return None


def _load_meta_sumber() -> list[dict]:
    path = SILVER / "meta_sumber.json"
    if path.exists():
        return list((json.loads(path.read_text(encoding="utf-8")).get("records")) or [])
    # fallback: import registry
    import sys

    sys.path.insert(0, str(HERE.parent))
    from build_entity_matches import META_SUMBER

    return list(META_SUMBER)


def build_ingest_runs(meta_sumber: list[dict] | None = None) -> dict:
    now = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    records = []
    for src in meta_sumber or _load_meta_sumber():
        sid = src.get("sumber_id")
        if not sid:
            continue
        rel = src.get("path_sot")
        path = None
        if rel:
            for base in (ROOT, SITE):
                cand = base / rel
                if cand.exists():
                    path = cand
                    break
            if path is None:
                path = ROOT / rel
        exists = bool(path and path.exists())
        n = _row_count(path) if exists else None
        checksum = _sha12(path) if exists else None
        status_src = str(src.get("status") or "planned")
        is_stub = bool(rel and str(rel).replace("\\", "/").startswith("stubs/"))

        if status_src == "active" and exists and (n or 0) > 0:
            run_status = "success"
            notes = f"SoT OK ({rel})"
        elif status_src == "planned" and is_stub and exists:
            run_status = "partial"
            notes = f"Stub placeholder — menunggu SoT sungguhan ({rel})"
        elif status_src == "planned" and not exists:
            run_status = "partial"
            notes = "planned tanpa path_sot atau file hilang"
        elif status_src == "active" and not exists:
            run_status = "failed"
            notes = f"SoT aktif hilang: {rel}"
        else:
            run_status = "partial"
            notes = f"status={status_src} path={rel or '—'}"

        records.append(
            {
                "run_id": str(uuid.uuid4()),
                "sumber_id": sid,
                "started_at": now,
                "finished_at": now,
                "checksum": checksum,
                "row_count": n if n is not None else 0,
                "status": run_status,
                "notes": notes,
                "payload": {
                    "path_sot": rel,
                    "sumber_status": status_src,
                    "is_stub": is_stub,
                    "akses": src.get("akses"),
                },
            }
        )

    payload = {
        "generated_at": now,
        "total": len(records),
        "records": records,
    }
    SILVER.mkdir(parents=True, exist_ok=True)
    out = SILVER / "ingest_run.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    ok = sum(1 for r in records if r["status"] == "success")
    partial = sum(1 for r in records if r["status"] == "partial")
    failed = sum(1 for r in records if r["status"] == "failed")
    print(f"  wrote ingest_run.json n={len(records)} success={ok} partial={partial} failed={failed}")
    return payload


def main() -> int:
    build_ingest_runs()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
