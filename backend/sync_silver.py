#!/usr/bin/env python3
"""Backfill silver tables dari gold staging lokal (+ upsert Supabase bila configured)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.config import get_settings  # noqa: E402
from app.supabase_client import get_supabase  # noqa: E402
from postgrest.exceptions import APIError  # noqa: E402

SILVER_SCHEMA_MISSING_MSG = (
    "SILVER_SCHEMA_MISSING: apply website/backend/supabase/migrations/"
    "002_silver_v1.sql, 003_silver_warehouse.sql, and 004_integration_schema.sql "
    "in Supabase SQL Editor, then re-run."
)


class SilverSchemaMissingError(Exception):
    """PostgREST PGRST205 — silver table/view not in schema cache."""


def _reraise_if_schema_missing(exc: BaseException) -> None:
    code = getattr(exc, "code", None)
    msg = str(exc)
    # PGRST205 = table missing; PGRST204 = column missing (004 not applied)
    if code in {"PGRST205", "PGRST204"} or "PGRST205" in msg or "PGRST204" in msg:
        raise SilverSchemaMissingError() from exc


def _load(data_dir: Path, name: str):
    path = data_dir / "silver" / f"{name}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    # fallback gold
    gold = data_dir / f"{name}.json"
    if gold.exists():
        return json.loads(gold.read_text(encoding="utf-8"))
    return None


def _boolish(v) -> bool | None:
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    s = str(v).strip().lower()
    if s in {"ya", "true", "1", "yes"}:
        return True
    if s in {"tidak", "false", "0", "no"}:
        return False
    return None


def upsert_rows(client, table: str, rows: list[dict], on_conflict: str) -> int:
    if not rows:
        return 0
    # chunk
    n = 0
    for i in range(0, len(rows), 200):
        chunk = rows[i : i + 200]
        try:
            client.table(table).upsert(chunk, on_conflict=on_conflict).execute()
        except APIError as exc:
            _reraise_if_schema_missing(exc)
            raise
        n += len(chunk)
    return n


def sync_silver_v1(client, data_dir: Path) -> dict:
    stats = {}
    alias = _load(data_dir, "dim_perusahaan_alias") or _load(data_dir, "perusahaan_alias")
    if alias:
        rows = [
            {
                "nama_mentah": r["nama_mentah"],
                "nama_kanonik": r["nama_kanonik"],
                "sumber": r.get("sumber"),
                "confidence": r.get("confidence"),
            }
            for r in (alias.get("records") or [])
            if r.get("nama_mentah") and r.get("nama_kanonik")
        ]
        stats["dim_perusahaan_alias"] = upsert_rows(client, "dim_perusahaan_alias", rows, "nama_mentah")

    kab = _load(data_dir, "dim_kab_kota") or json.loads((data_dir / "kab_kota.json").read_text(encoding="utf-8"))
    if kab:
        rows = []
        for r in kab.get("records") or []:
            rows.append(
                {
                    "id": r.get("id"),
                    "kab_kota": r.get("kab_kota"),
                    "cluster": r.get("cluster"),
                    "skor_komposit": r.get("skor_komposit"),
                    "kategori_peta": r.get("kategori_peta"),
                    "polres_proksi": r.get("polres_proksi"),
                    "verifikasi_status": r.get("verifikasi_status"),
                    "kepercayaan_sebaran": r.get("kepercayaan_sebaran"),
                    "rank_gfw": str(r.get("rank_gfw")) if r.get("rank_gfw") is not None else None,
                    "rank_sebaran": str(r.get("rank_sebaran")) if r.get("rank_sebaran") is not None else None,
                    "n_izin_2017": r.get("n_izin_2017"),
                    "payload": r,
                }
            )
        rows = [r for r in rows if r.get("id")]
        stats["dim_kab_kota"] = upsert_rows(client, "dim_kab_kota", rows, "id")

    desa = _load(data_dir, "desa_lock")
    if desa:
        rows = []
        for r in desa.get("records") or []:
            rows.append(
                {
                    "id": r.get("id"),
                    "kabupaten": r.get("kabupaten"),
                    "kecamatan": r.get("kecamatan"),
                    "desa": r.get("desa"),
                    "desa_utama": r.get("desa_utama"),
                    "lon": r.get("lon"),
                    "lat": r.get("lat"),
                    "kepercayaan": r.get("kepercayaan"),
                    "sent_scene": r.get("sent_scene"),
                    "payload": r,
                }
            )
        rows = [r for r in rows if r.get("id")]
        stats["desa_lock"] = upsert_rows(client, "desa_lock", rows, "id")

    izin = _load(data_dir, "izin_2017")
    if izin:
        rows = []
        for r in izin.get("records") or []:
            rows.append(
                {
                    "record_id": r.get("record_id"),
                    "kab_id": r.get("kab_id"),
                    "kab_kota": r.get("kab_kota"),
                    "nama_mentah": r.get("nama_mentah"),
                    "nama_kanonik": r.get("nama_kanonik"),
                    "izin_lokasi_ha": r.get("izin_lokasi_ha"),
                    "iup_ha": r.get("iup_ha"),
                    "pelepasan_kh_ha": r.get("pelepasan_kh_ha"),
                    "hgu_ha": r.get("hgu_ha"),
                    "vintage": r.get("vintage") or 2017,
                    "payload": r,
                }
            )
        rows = [r for r in rows if r.get("record_id")]
        stats["izin_2017"] = upsert_rows(client, "izin_2017", rows, "record_id")
    return stats


def sync_silver_warehouse(client, data_dir: Path, *, with_integration_cols: bool = False) -> dict:
    stats = {}
    polres = json.loads((data_dir / "polres.json").read_text(encoding="utf-8"))
    rows = [
        {
            "polres": r.get("polres"),
            "peringkat": r.get("peringkat"),
            "skor": r.get("skor"),
            "kategori": r.get("kategori"),
            "payload": r,
        }
        for r in (polres.get("records") or [])
        if r.get("polres")
    ]
    stats["dim_polres"] = upsert_rows(client, "dim_polres", rows, "polres")

    per = json.loads((data_dir / "perusahaan.json").read_text(encoding="utf-8"))
    rows = []
    for r in per.get("records") or []:
        if not r.get("nama"):
            continue
        row = {
            "nama": r.get("nama"),
            "nama_kanonik": r.get("nama_kanonik"),
            "sumber": r.get("sumber"),
            "ada_di_gfw": _boolish(r.get("ada_di_gfw")),
            "ada_di_atlas": _boolish(r.get("ada_di_atlas")),
            "ada_izin_2017": bool(r.get("ada_izin_2017")),
            "payload": r,
        }
        if with_integration_cols:
            row["perusahaan_id"] = r.get("perusahaan_id")
            row["nama_normalized"] = r.get("nama_normalized")
            row["provinsi_hint"] = r.get("provinsi_hint")
            row["kab_list"] = r.get("kab_list") if isinstance(r.get("kab_list"), list) else []
        rows.append(row)
    stats["dim_perusahaan"] = upsert_rows(client, "dim_perusahaan", rows, "nama")

    kasus = json.loads((data_dir / "kasus.json").read_text(encoding="utf-8"))
    rows = [
        {
            "id": r.get("id"),
            "tipe_entri": r.get("tipe_entri"),
            "kab_kota": r.get("kab_kota"),
            "polres": r.get("polres"),
            "tahun": str(r.get("tahun")) if r.get("tahun") is not None else None,
            "perusahaan": r.get("perusahaan"),
            "payload": r,
        }
        for r in (kasus.get("records") or [])
        if r.get("id")
    ]
    stats["fact_kasus"] = upsert_rows(client, "fact_kasus", rows, "id")

    kons = json.loads((data_dir / "konsesi.json").read_text(encoding="utf-8"))
    af = (kons.get("atlas_full") or {}).get("records") or []
    rows = [
        {
            "atlas_id": r.get("atlas_id"),
            "nama_perusahaan": r.get("nama_perusahaan"),
            "nama_kanonik": r.get("nama_kanonik"),
            "grup": r.get("grup"),
            "kabupaten": r.get("kabupaten"),
            "luas_ha": r.get("luas_ha"),
            "payload": r,
        }
        for r in af
        if r.get("atlas_id")
    ]
    stats["fact_konsesi_atlas"] = upsert_rows(client, "fact_konsesi_atlas", rows, "atlas_id")

    am = (kons.get("atlas_match") or {}).get("records") or []
    rows = [
        {
            "match_id": r.get("match_id"),
            "atlas_nama": r.get("atlas_nama"),
            "atlas_uid": r.get("atlas_uid"),
            "gfwid": r.get("gfwid"),
            "status": r.get("status"),
            "match_confidence": r.get("match_confidence"),
            "payload": r,
        }
        for r in am
        if r.get("match_id")
    ]
    stats["bridge_atlas_match"] = upsert_rows(client, "bridge_atlas_match", rows, "match_id")

    alias = _load(data_dir, "dim_perusahaan_alias") or _load(data_dir, "perusahaan_alias")
    if alias:
        rows = []
        for r in alias.get("records") or []:
            if not r.get("nama_mentah"):
                continue
            row = {
                "nama_mentah": r["nama_mentah"],
                "nama_kanonik": r["nama_kanonik"],
                "sumber": r.get("sumber"),
                "confidence": r.get("confidence"),
            }
            if with_integration_cols:
                row["match_method"] = r.get("match_method")
                row["geo_validated"] = _boolish(r.get("geo_validated"))
                row["rejected_reason"] = r.get("rejected_reason")
            rows.append(row)
        stats["bridge_alias"] = upsert_rows(client, "bridge_alias", rows, "nama_mentah")

    rantai_path = data_dir / "rantai_agrinas.json"
    if rantai_path.exists():
        payload = json.loads(rantai_path.read_text(encoding="utf-8"))
        try:
            client.table("mart_rantai_agrinas").upsert(
                [{"id": "baseline", "payload": payload}], on_conflict="id"
            ).execute()
        except APIError as exc:
            _reraise_if_schema_missing(exc)
            raise
        stats["mart_rantai_agrinas"] = 1
    return stats


def sync_integration(client, data_dir: Path) -> dict:
    """Sync Matching & Overlay Engine tables (migration 004)."""
    stats = {}

    meta = _load(data_dir, "meta_sumber")
    if meta:
        rows = [
            {
                "sumber_id": r["sumber_id"],
                "nama": r["nama"],
                "akses": r["akses"],
                "tipe_data": r["tipe_data"],
                "kredibilitas": r.get("kredibilitas"),
                "grain": r.get("grain"),
                "path_sot": r.get("path_sot"),
                "refresh_cadence": r.get("refresh_cadence"),
                "status": r.get("status") or "active",
                "payload": r,
            }
            for r in (meta.get("records") or [])
            if r.get("sumber_id")
        ]
        stats["meta_sumber"] = upsert_rows(client, "meta_sumber", rows, "sumber_id")

    gfw = _load(data_dir, "fact_gfw_konsesi")
    if gfw:
        rows = [
            {
                "gfwid": r["gfwid"],
                "company_raw": r.get("company_raw"),
                "nama_kanonik": r.get("nama_kanonik"),
                "area_ha": r.get("area_ha"),
                "lon": r.get("lon"),
                "lat": r.get("lat"),
                "in_riau_bbox": _boolish(r.get("in_riau_bbox")),
                "payload": r.get("payload") or r,
            }
            for r in (gfw.get("records") or [])
            if r.get("gfwid")
        ]
        stats["fact_gfw_konsesi"] = upsert_rows(client, "fact_gfw_konsesi", rows, "gfwid")

    sk36 = _load(data_dir, "fact_penertiban_sk36")
    if sk36:
        rows = [
            {
                "record_id": r["record_id"],
                "nama": r.get("nama"),
                "nama_kanonik": r.get("nama_kanonik"),
                "no": r.get("no"),
                "prioritas": r.get("prioritas"),
                "status_proses": r.get("status_proses"),
                "rasio_ditolak": r.get("rasio_ditolak"),
                "payload": r.get("payload") or r,
            }
            for r in (sk36.get("records") or [])
            if r.get("record_id")
        ]
        stats["fact_penertiban_sk36"] = upsert_rows(client, "fact_penertiban_sk36", rows, "record_id")

    bem = _load(data_dir, "bridge_entity_match")
    if bem:
        rows = [
            {
                "match_id": r["match_id"],
                "left_source": r["left_source"],
                "left_id": r["left_id"],
                "right_source": r["right_source"],
                "right_id": r["right_id"],
                "nama_score": r.get("nama_score"),
                "geo_ok": _boolish(r.get("geo_ok")),
                "status": r["status"],
                "match_type": r.get("match_type"),
                "human_verified": bool(r.get("human_verified")),
                "evidence": r.get("evidence") or {},
            }
            for r in (bem.get("records") or [])
            if r.get("match_id")
        ]
        stats["bridge_entity_match"] = upsert_rows(client, "bridge_entity_match", rows, "match_id")

    dossier = _load(data_dir, "mart_dossier_kasus")
    if not dossier:
        gold = data_dir / "dossier.json"
        if gold.exists():
            dossier = json.loads(gold.read_text(encoding="utf-8"))
    if dossier:
        rows = [
            {
                "dossier_id": r["dossier_id"],
                "nama": r.get("nama") or "",
                "nama_kanonik": r.get("nama_kanonik"),
                "kab": r.get("kab"),
                "luas_loss_ha": r.get("luas_loss_ha"),
                "gambut_ha": r.get("gambut_ha"),
                "legal_status": r.get("legal_status"),
                "konflik": r.get("konflik"),
                "tautan_atlas": r.get("tautan_atlas"),
                "gfwid": r.get("gfwid"),
                "status_match": r.get("status_match"),
                "risiko": r.get("risiko"),
                "human_verified": bool(r.get("human_verified")),
                "payload": r,
            }
            for r in (dossier.get("records") or [])
            if r.get("dossier_id")
        ]
        stats["mart_dossier_kasus"] = upsert_rows(client, "mart_dossier_kasus", rows, "dossier_id")

    ingest = _load(data_dir, "ingest_run")
    if ingest:
        rows = [
            {
                "run_id": r["run_id"],
                "sumber_id": r.get("sumber_id"),
                "started_at": r.get("started_at"),
                "finished_at": r.get("finished_at"),
                "checksum": r.get("checksum"),
                "row_count": r.get("row_count"),
                "status": r.get("status") or "partial",
                "notes": r.get("notes"),
                "payload": r.get("payload") or {},
            }
            for r in (ingest.get("records") or [])
            if r.get("run_id") and r.get("sumber_id")
        ]
        # insert (bukan upsert): tiap materialize = run baru
        n = 0
        for i in range(0, len(rows), 200):
            chunk = rows[i : i + 200]
            try:
                client.table("ingest_run").upsert(chunk, on_conflict="run_id").execute()
            except APIError as exc:
                _reraise_if_schema_missing(exc)
                raise
            n += len(chunk)
        stats["ingest_run"] = n

    return stats


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--warehouse", action="store_true", help="Juga sync Fase 3 warehouse tables")
    parser.add_argument(
        "--integration",
        action="store_true",
        help="Juga sync Matching Engine tables (migration 004)",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    settings = get_settings()
    data_dir = settings.data_path
    print(f"DATA_DIR={data_dir}")
    if args.dry_run:
        silver = data_dir / "silver"
        print(f"silver staging exists={silver.is_dir()} files={list(silver.glob('*.json')) if silver.is_dir() else []}")
        return 0

    if not settings.supabase_configured:
        print("FAIL: Supabase belum dikonfigurasi", file=sys.stderr)
        return 2

    client = get_supabase(settings)
    try:
        stats = sync_silver_v1(client, data_dir)
        print("silver v1:", stats)
        if args.warehouse:
            wstats = sync_silver_warehouse(
                client, data_dir, with_integration_cols=args.integration
            )
            print("silver warehouse:", wstats)
        if args.integration:
            istats = sync_integration(client, data_dir)
            print("silver integration:", istats)
    except SilverSchemaMissingError:
        print(SILVER_SCHEMA_MISSING_MSG, file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
