"""Sync website/data/* → Supabase serving_datasets."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import Settings, get_settings
from .manifest import SERVING_MANIFEST
from .supabase_client import get_supabase


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _content_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".geojson", ".topojson", ".json"}:
        return "application/json"
    return "application/octet-stream"


def load_local_payload(path: Path) -> dict[str, Any] | list[Any]:
    text = path.read_text(encoding="utf-8")
    return json.loads(text)


def checksum_payload(payload: Any) -> tuple[str, int]:
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    encoded = raw.encode("utf-8")
    return hashlib.sha256(encoded).hexdigest(), len(encoded)


def list_local_datasets(data_dir: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for dataset, filename in SERVING_MANIFEST.items():
        path = data_dir / filename
        exists = path.is_file()
        info: dict[str, Any] = {
            "dataset": dataset,
            "source_path": f"data/{filename}",
            "exists": exists,
        }
        if exists:
            payload = load_local_payload(path)
            digest, size = checksum_payload(payload)
            info.update({"checksum": digest, "byte_size": size})
        rows.append(info)
    return rows


def sync_serving_to_supabase(
    *,
    settings: Settings | None = None,
    trigger_source: str = "manual",
    only: list[str] | None = None,
) -> dict[str, Any]:
    """Upsert semua (atau subset) dataset serving ke Supabase."""
    cfg = settings or get_settings()
    data_dir = cfg.data_path
    if not data_dir.is_dir():
        raise FileNotFoundError(f"DATA_DIR tidak ditemukan: {data_dir}")

    client = get_supabase(cfg)
    started = _now_iso()

    run_ins = (
        client.table("sync_runs")
        .insert(
            {
                "started_at": started,
                "status": "running",
                "trigger_source": trigger_source,
                "message": f"Sync dari {data_dir}",
            }
        )
        .execute()
    )
    run_id = run_ins.data[0]["id"] if run_ins.data else None

    ok: list[str] = []
    failed: list[dict[str, str]] = []
    details: list[dict[str, Any]] = []

    targets = SERVING_MANIFEST.items()
    if only:
        wanted = set(only)
        targets = [(k, v) for k, v in SERVING_MANIFEST.items() if k in wanted]

    for dataset, filename in targets:
        path = data_dir / filename
        try:
            if not path.is_file():
                raise FileNotFoundError(f"File hilang: {path}")
            payload = load_local_payload(path)
            digest, size = checksum_payload(payload)
            row = {
                "dataset": dataset,
                "content_type": _content_type(path),
                "payload": payload,
                "checksum": digest,
                "byte_size": size,
                "source_path": f"data/{filename}",
                "updated_at": _now_iso(),
                "synced_at": _now_iso(),
            }
            client.table("serving_datasets").upsert(row, on_conflict="dataset").execute()
            ok.append(dataset)
            details.append(
                {
                    "dataset": dataset,
                    "status": "ok",
                    "byte_size": size,
                    "checksum": digest[:12],
                }
            )
        except Exception as exc:  # noqa: BLE001 — kumpulkan error per dataset
            failed.append({"dataset": dataset, "error": str(exc)})
            details.append({"dataset": dataset, "status": "failed", "error": str(exc)})

    if failed and ok:
        status = "partial"
    elif failed:
        status = "failed"
    else:
        status = "success"

    message = (
        f"{len(ok)} ok, {len(failed)} gagal"
        if failed
        else f"{len(ok)} dataset tersinkron"
    )
    finished = _now_iso()
    if run_id:
        client.table("sync_runs").update(
            {
                "finished_at": finished,
                "status": status,
                "datasets_ok": ok,
                "datasets_failed": [f["dataset"] for f in failed],
                "message": message,
                "meta": {"details": details, "data_dir": str(data_dir)},
            }
        ).eq("id", run_id).execute()

    return {
        "run_id": run_id,
        "status": status,
        "started_at": started,
        "finished_at": finished,
        "datasets_ok": ok,
        "datasets_failed": failed,
        "message": message,
        "details": details,
    }


def fetch_dataset(dataset: str, *, settings: Settings | None = None) -> dict[str, Any] | None:
    cfg = settings or get_settings()
    client = get_supabase(cfg)
    res = (
        client.table("serving_datasets")
        .select("dataset,content_type,payload,checksum,byte_size,source_path,updated_at,synced_at")
        .eq("dataset", dataset)
        .limit(1)
        .execute()
    )
    if not res.data:
        return None
    return res.data[0]


def fetch_all_dataset_meta(*, settings: Settings | None = None) -> list[dict[str, Any]]:
    cfg = settings or get_settings()
    client = get_supabase(cfg)
    res = (
        client.table("serving_datasets")
        .select("dataset,content_type,checksum,byte_size,source_path,updated_at,synced_at")
        .order("dataset")
        .execute()
    )
    return res.data or []


def latest_sync_run(*, settings: Settings | None = None) -> dict[str, Any] | None:
    cfg = settings or get_settings()
    client = get_supabase(cfg)
    res = (
        client.table("sync_runs")
        .select("*")
        .order("started_at", desc=True)
        .limit(1)
        .execute()
    )
    if not res.data:
        return None
    return res.data[0]
