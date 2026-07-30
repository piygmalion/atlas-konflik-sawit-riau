"""FastAPI — serving API + trigger sync ke Supabase."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import __version__
from .config import Settings, get_settings
from .manifest import PATH_TO_DATASET, SERVING_MANIFEST
from .sync import (
    fetch_all_dataset_meta,
    fetch_dataset,
    latest_sync_run,
    list_local_datasets,
    sync_serving_to_supabase,
)

app = FastAPI(
    title="Atlas Konflik Sawit Riau API",
    description=(
        "Backend serving layer yang terhubung ke Supabase. "
        "Frontend bisa baca lewat API ini atau langsung PostgREST Supabase."
    ),
    version=__version__,
)

_cfg0 = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cfg0.cors_origin_list or ["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


def _settings() -> Settings:
    return get_settings()


def require_sync_key(
    x_api_key: Annotated[str | None, Header()] = None,
    settings: Settings = Depends(_settings),
) -> None:
    expected = settings.sync_api_key
    if not expected:
        # Tanpa SYNC_API_KEY, izinkan hanya jika Supabase service role sudah set
        # (pemakaian lokal). Tetap tolak request tanpa header di produksi jika key di-set.
        return
    if not x_api_key or x_api_key != expected:
        raise HTTPException(status_code=401, detail="X-API-Key tidak valid")


@app.get("/health")
def health(settings: Settings = Depends(_settings)) -> dict[str, Any]:
    return {
        "ok": True,
        "version": __version__,
        "supabase_configured": settings.supabase_configured,
        "data_dir": str(settings.data_path),
        "datasets_defined": len(SERVING_MANIFEST),
    }


@app.get("/api/v1/datasets")
def list_datasets(settings: Settings = Depends(_settings)) -> dict[str, Any]:
    local = list_local_datasets(settings.data_path)
    remote: list[dict[str, Any]] = []
    remote_error = None
    if settings.supabase_configured:
        try:
            remote = fetch_all_dataset_meta(settings=settings)
        except Exception as exc:  # noqa: BLE001
            remote_error = str(exc)
    return {
        "manifest": SERVING_MANIFEST,
        "path_map": PATH_TO_DATASET,
        "local": local,
        "remote": remote,
        "remote_error": remote_error,
    }


@app.get("/api/v1/datasets/{name}")
def get_dataset(
    name: str,
    source: Annotated[str, Query(description="supabase|local|auto")] = "auto",
    settings: Settings = Depends(_settings),
) -> JSONResponse:
    if name not in SERVING_MANIFEST:
        raise HTTPException(404, detail=f"Dataset tidak dikenal: {name}")

    prefer_remote = source in {"supabase", "auto"} and settings.supabase_configured
    if prefer_remote:
        try:
            row = fetch_dataset(name, settings=settings)
            if row and row.get("payload") is not None:
                return JSONResponse(
                    content=row["payload"],
                    headers={
                        "X-Atlas-Source": "supabase",
                        "X-Atlas-Dataset": name,
                        "X-Atlas-Checksum": row.get("checksum") or "",
                        "X-Atlas-Synced-At": row.get("synced_at") or "",
                    },
                )
            if source == "supabase":
                raise HTTPException(404, detail=f"Belum ada di Supabase: {name}")
        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001
            if source == "supabase":
                raise HTTPException(502, detail=f"Gagal baca Supabase: {exc}") from exc

    path = settings.data_path / SERVING_MANIFEST[name]
    if not path.is_file():
        raise HTTPException(404, detail=f"File lokal hilang: {path.name}")
    payload = json_load(path)
    return JSONResponse(
        content=payload,
        headers={
            "X-Atlas-Source": "local",
            "X-Atlas-Dataset": name,
        },
    )


def json_load(path) -> Any:
    import json

    return json.loads(path.read_text(encoding="utf-8"))


@app.get("/api/v1/path/{path:path}")
def get_by_web_path(
    path: str,
    source: Annotated[str, Query()] = "auto",
    settings: Settings = Depends(_settings),
) -> JSONResponse:
    """Alias path frontend: data/kasus.json → dataset kasus."""
    key = path if path.startswith("data/") else f"data/{path}"
    dataset = PATH_TO_DATASET.get(key)
    if not dataset:
        raise HTTPException(404, detail=f"Path tidak terdaftar: {key}")
    return get_dataset(dataset, source=source, settings=settings)


@app.post("/api/v1/sync")
def trigger_sync(
    _: None = Depends(require_sync_key),
    settings: Settings = Depends(_settings),
    trigger_source: Annotated[str, Query()] = "api",
    only: Annotated[str | None, Query(description="Comma-separated dataset keys")] = None,
) -> dict[str, Any]:
    if not settings.supabase_configured:
        raise HTTPException(
            503,
            detail="Supabase belum dikonfigurasi (SUPABASE_URL / SERVICE_ROLE_KEY)",
        )
    only_list = [x.strip() for x in only.split(",") if x.strip()] if only else None
    try:
        result = sync_serving_to_supabase(
            settings=settings,
            trigger_source=trigger_source,
            only=only_list,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, detail=str(exc)) from exc
    return result


@app.get("/api/v1/sync/latest")
def sync_latest(settings: Settings = Depends(_settings)) -> dict[str, Any]:
    if not settings.supabase_configured:
        return {"configured": False, "run": None}
    try:
        run = latest_sync_run(settings=settings)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, detail=str(exc)) from exc
    return {"configured": True, "run": run}
