#!/usr/bin/env python3
"""Matching & Overlay Engine — geo-gated entity resolution + dossier mart.

Menulis silver staging + gold dossier.json. Aturan: nama cocok + wilayah beda
⇒ status conflict/rejected, bukan confirmed.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve()
SITE = HERE.parents[1]
DATA = SITE / "data"
SILVER = DATA / "silver"
ROOT = SITE.parent

sys.path.insert(0, str(HERE.parent))
from company_normalize import load_alias_table, norm_company, norm_company_display, resolve_canonical  # noqa: E402

# Rough Riau bounding box (lon_min, lat_min, lon_max, lat_max)
RIAU_BBOX = (99.5, -1.8, 104.0, 2.9)
NON_RIAU_RE = re.compile(
    r"\b(KALIMANTAN|KALBAR|KALTENG|KALTIM|KALSEL|SULAWESI|PAPUA|JAWA\s?BARAT|"
    r"JAWA\s?TIMUR|JAWA\s?TENGAH|MALUKU|BALI|NTB|NTT)\b",
    re.I,
)

META_SUMBER = [
    {
        "sumber_id": "bps_2021",
        "nama": "Direktori BPS Riau 2021",
        "akses": "terbuka",
        "tipe_data": "tabular",
        "kredibilitas": "tinggi",
        "grain": "1 baris / perusahaan",
        "path_sot": "daftar_perusahaan_sawit_riau_gabungan.csv",
        "refresh_cadence": "tahunan",
        "status": "active",
    },
    {
        "sumber_id": "disbun_riau",
        "nama": "Disbun Riau (statistik agregat)",
        "akses": "terbuka",
        "tipe_data": "tabular",
        "kredibilitas": "sedang",
        "grain": "agregat kab/prov",
        "path_sot": "stubs/disbun_riau_agregat.csv",
        "refresh_cadence": "tahunan",
        "status": "planned",
        "notes": "Stub terbuka — ganti isi saat statistik Disbun tersedia",
    },
    {
        "sumber_id": "gfw_greenpeace",
        "nama": "GFW / Greenpeace oil palm concessions",
        "akses": "terbuka",
        "tipe_data": "spasial",
        "kredibilitas": "tinggi",
        "grain": "1 poligon / gfwid",
        "path_sot": "tabulasi_konsesi_sawit_gfw_bbox_riau.csv",
        "refresh_cadence": "periodik",
        "status": "active",
    },
    {
        "sumber_id": "nusantara_atlas",
        "nama": "Nusantara Atlas",
        "akses": "terbuka",
        "tipe_data": "spasial",
        "kredibilitas": "tinggi",
        "grain": "1 baris / konsesi Atlas",
        "path_sot": "tabulasi_konsesi_sawit_nusantara_atlas_riau.csv",
        "refresh_cadence": "periodik",
        "status": "active",
    },
    {
        "sumber_id": "fwi_hutan",
        "nama": "Peta Hutan FWI",
        "akses": "terbuka",
        "tipe_data": "spasial",
        "kredibilitas": "sedang",
        "grain": "layer tutupan",
        "path_sot": "stubs/fwi_hutan_layer.csv",
        "refresh_cadence": "periodik",
        "status": "planned",
        "notes": "Stub terbuka — path layer/geopackage menyusul",
    },
    {
        "sumber_id": "atr_bpn",
        "nama": "ATR/BPN Kanwil (IUP tanpa HGU)",
        "akses": "tertutup",
        "tipe_data": "tabular",
        "kredibilitas": "tinggi",
        "grain": "1 baris / IUP",
        "path_sot": "stubs/atr_bpn_iup.csv",
        "refresh_cadence": "ad-hoc",
        "status": "planned",
        "notes": "Stub tertutup — butuh akses Kanwil",
    },
    {
        "sumber_id": "pemprov_riau",
        "nama": "Pemprov Riau daftar perusahaan",
        "akses": "tertutup",
        "tipe_data": "tabular",
        "kredibilitas": "tinggi",
        "grain": "1 baris / perusahaan",
        "path_sot": "stubs/pemprov_riau_perusahaan.csv",
        "refresh_cadence": "ad-hoc",
        "status": "planned",
        "notes": "Stub tertutup — butuh daftar resmi Pemprov",
    },
    {
        "sumber_id": "kepmenhut_36_2025",
        "nama": "Kepmenhut 36/2025 subjek 110A/B",
        "akses": "tertutup",
        "tipe_data": "tabular",
        "kredibilitas": "tinggi",
        "grain": "1 subjek / record_id",
        "path_sot": "tabulasi_konsesi_sawit_kepmenhut_36_2025_riau_rapi.csv",
        "refresh_cadence": "ad-hoc",
        "status": "active",
    },
    {
        "sumber_id": "walhi_investigasi",
        "nama": "Investigasi spesifik WALHI",
        "akses": "tertutup",
        "tipe_data": "spasial",
        "kredibilitas": "sedang",
        "grain": "kasus investigasi",
        "path_sot": "stubs/walhi_investigasi.csv",
        "refresh_cadence": "ad-hoc",
        "status": "planned",
        "notes": "Stub tertutup — investigasi kasus-by-kasus",
    },
    {
        "sumber_id": "objek_enriched",
        "nama": "Objek Agrinas enriched + geo override",
        "akses": "tertutup",
        "tipe_data": "tabular",
        "kredibilitas": "tinggi",
        "grain": "1 objek / OBJ-###",
        "path_sot": "master_list_objek_agrinas_enriched.csv",
        "refresh_cadence": "berkala",
        "status": "active",
        "notes": "SoT preferensi export objek (override MULTI)",
    },
    {
        "sumber_id": "polda_konflik",
        "nama": "Daftar Konflik Polda Riau",
        "akses": "tertutup",
        "tipe_data": "tabular",
        "kredibilitas": "tinggi",
        "grain": "1 entri / kasus",
        "path_sot": "master_kasus_sawit_riau_gold.csv",
        "refresh_cadence": "berkala",
        "status": "active",
    },
    {
        "sumber_id": "agrinas_satgas",
        "nama": "Master List Objek Agrinas–Satgas",
        "akses": "tertutup",
        "tipe_data": "tabular",
        "kredibilitas": "tinggi",
        "grain": "1 objek / OBJ-###",
        "path_sot": "master_list_objek_agrinas_satgas_riau.csv",
        "refresh_cadence": "berkala",
        "status": "active",
    },
]


def _load_json(path: Path):
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _dump(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  write {path.relative_to(SITE.parent)}")


def perusahaan_id_for(nama: str) -> str:
    """Stable unique id: norm key + short hash of original nama (hindari bentrok unique index)."""
    raw = (nama or "").strip()
    if not raw:
        return ""
    key = norm_company(raw) or "X"
    h = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:8]
    return f"PER-{key[:48]}-{h}"


def in_riau_bbox(lon, lat) -> bool | None:
    try:
        lon_f = float(lon)
        lat_f = float(lat)
    except (TypeError, ValueError):
        return None
    return RIAU_BBOX[0] <= lon_f <= RIAU_BBOX[2] and RIAU_BBOX[1] <= lat_f <= RIAU_BBOX[3]


def text_non_riau(*parts: str | None) -> bool:
    blob = " ".join(str(p) for p in parts if p)
    return bool(NON_RIAU_RE.search(blob))


RIAU_KAB_HINTS = (
    "bengkalis",
    "dumai",
    "indragiri",
    "inhu",
    "inhil",
    "kampar",
    "meranti",
    "kuantan",
    "kuansing",
    "pelalawan",
    "pekanbaru",
    "rokan",
    "rohul",
    "rohil",
    "siak",
    "riau",
)


def kab_in_riau(kab: str | None) -> bool:
    t = re.sub(r"[^a-z0-9]+", " ", str(kab or "").lower()).strip()
    if not t or text_non_riau(t):
        return False
    return any(h in t for h in RIAU_KAB_HINTS)


def match_id_for(left_source: str, left_id: str, right_source: str, right_id: str) -> str:
    raw = f"{left_source}|{left_id}|{right_source}|{right_id}"
    return "bem-" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def decide_status(nama_ok: bool, geo_ok: bool | None, evidence_conflict: bool) -> str:
    if evidence_conflict or (nama_ok and geo_ok is False):
        return "conflict" if nama_ok else "rejected"
    if not nama_ok:
        return "rejected"
    if geo_ok is None:
        return "warning"
    return "confirmed"


def enrich_perusahaan(per_payload: dict, alias_map: dict) -> dict:
    records = []
    for r in per_payload.get("records") or []:
        nama = r.get("nama") or ""
        canon = r.get("nama_kanonik") or resolve_canonical(nama, alias_map) or nama
        row = dict(r)
        # PK dim_perusahaan = nama (unik); id diturunkan dari nama, bukan kanonik
        row["perusahaan_id"] = perusahaan_id_for(nama)
        row["nama_normalized"] = norm_company_display(canon or nama)
        row.setdefault("provinsi_hint", "RIAU")
        row.setdefault("kab_list", [])
        records.append(row)
    out = dict(per_payload)
    out["records"] = records
    out["total"] = len(records)
    return out


def build_fact_gfw(gfw_payload: dict, alias_map: dict) -> dict:
    records = []
    for r in gfw_payload.get("records") or []:
        gfwid = r.get("gfwid")
        if not gfwid:
            continue
        raw = r.get("company") or r.get("name") or ""
        lon, lat = r.get("lon"), r.get("lat")
        bbox_ok = in_riau_bbox(lon, lat)
        records.append(
            {
                "gfwid": gfwid,
                "company_raw": raw,
                "nama_kanonik": resolve_canonical(raw, alias_map) or norm_company_display(raw),
                "area_ha": r.get("area_ha"),
                "lon": lon,
                "lat": lat,
                "in_riau_bbox": bbox_ok,
                "payload": r,
            }
        )
    return {"total": len(records), "records": records}


def build_fact_sk36(penertiban: dict, alias_map: dict) -> dict:
    sk = (penertiban.get("normalized") or {}).get("sk36_2025_110a") or {}
    records = []
    for r in sk.get("records") or []:
        rid = r.get("record_id")
        if not rid:
            continue
        nama = r.get("nama") or ""
        records.append(
            {
                "record_id": rid,
                "nama": nama,
                "nama_kanonik": resolve_canonical(nama, alias_map) or norm_company_display(nama),
                "no": r.get("no"),
                "prioritas": r.get("prioritas"),
                "status_proses": r.get("status_proses"),
                "rasio_ditolak": r.get("rasio_ditolak"),
                "payload": r,
            }
        )
    return {"total": len(records), "records": records}


def build_matches(
    *,
    perusahaan_by_norm: dict[str, dict],
    gfw_by_id: dict[str, dict],
    gfw_by_norm: dict[str, list[dict]],
    atlas_full: list[dict],
    atlas_match: list[dict],
    gfw_bps: list[dict],
) -> list[dict]:
    out: dict[str, dict] = {}

    def upsert(row: dict) -> None:
        mid = row["match_id"]
        prev = out.get(mid)
        if prev is None:
            out[mid] = row
            return
        # Prefer stricter (conflict > warning > confirmed) when merging
        rank = {"rejected": 0, "conflict": 1, "warning": 2, "confirmed": 3}
        if rank.get(row["status"], 9) < rank.get(prev["status"], 9):
            out[mid] = row

    # A) GFW ↔ BPS from gfw_match_bps (Fondasi 2: 126)
    for r in gfw_bps:
        gfwid = r.get("gfwid")
        nama_bps = r.get("nama_bps") or r.get("nama_kanonik") or ""
        if not gfwid or not nama_bps:
            continue
        gfw = gfw_by_id.get(gfwid)
        geo_ok = gfw.get("in_riau_bbox") if gfw else None
        conflict_txt = text_non_riau(
            r.get("nama_bps"), r.get("company"), r.get("name"), r.get("catatan")
        )
        # Blueprint false-match: name OK but location outside Riau
        if conflict_txt:
            geo_ok = False
        status = decide_status(True, geo_ok, conflict_txt)
        mid = match_id_for("gfw", gfwid, "bps", perusahaan_id_for(nama_bps) or norm_company(nama_bps))
        upsert(
            {
                "match_id": mid,
                "left_source": "gfw",
                "left_id": gfwid,
                "right_source": "bps",
                "right_id": perusahaan_id_for(nama_bps) or norm_company(nama_bps),
                "nama_score": 1.0,
                "geo_ok": geo_ok,
                "status": status,
                "match_type": "gabungan_gfw" if status == "confirmed" else "gfw_bbox",
                "human_verified": False,
                "evidence": {
                    "nama_bps": nama_bps,
                    "company_gfw": r.get("company") or r.get("name"),
                    "in_riau_bbox": geo_ok,
                    "source": "gfw_match_bps",
                },
            }
        )

    # B) Atlas ↔ GFW from atlas_match + classify vs gabungan
    atlas_gfw: dict[str, str] = {}
    for r in atlas_match:
        atlas_key = r.get("atlas_uid") or r.get("atlas_nama") or r.get("match_id")
        gfwid = r.get("gfwid")
        if atlas_key and gfwid:
            atlas_gfw[str(atlas_key).lower()] = gfwid
            atlas_gfw[norm_company(r.get("atlas_nama") or "")] = gfwid

        nama = r.get("atlas_nama") or r.get("nama_kanonik") or ""
        nkey = norm_company(nama)
        in_gabungan = nkey in perusahaan_by_norm or norm_company(r.get("nama_kanonik") or "") in perusahaan_by_norm
        gfw = gfw_by_id.get(gfwid) if gfwid else None
        geo_ok = gfw.get("in_riau_bbox") if gfw else None
        conflict_txt = text_non_riau(nama, r.get("status"), r.get("match_method"))
        if conflict_txt:
            geo_ok = False

        if gfwid and in_gabungan:
            mtype = "gabungan_gfw"
            nama_ok = True
        elif gfwid and not in_gabungan:
            mtype = "gfw_only"
            nama_ok = True
        elif not gfwid and in_gabungan:
            mtype = "gabungan_only"
            nama_ok = True
            # atlas_match tanpa gfwid: geo dari status sumber / default warning
            geo_ok = None
        else:
            mtype = "not_found"
            nama_ok = False

        # Existing status strings may already encode bbox-only
        st_raw = str(r.get("status") or r.get("match_method") or "").lower()
        if "bbox" in st_raw and gfwid:
            mtype = "gfw_bbox"

        status = decide_status(nama_ok, geo_ok if gfwid else None, conflict_txt)
        if mtype == "not_found":
            status = "rejected"
        if mtype == "gabungan_only" and not conflict_txt and not gfwid:
            # Tanpa koordinat GFW — biarkan warning (antrian review), jangan confirmed palsu
            status = "warning"
            geo_ok = None

        left_id = str(r.get("match_id") or atlas_key or nama)
        right_id = gfwid or ("nogfw:" + nkey)
        mid = match_id_for("atlas", left_id, "gfw" if gfwid else "none", right_id)
        upsert(
            {
                "match_id": mid,
                "left_source": "atlas",
                "left_id": left_id,
                "right_source": "gfw" if gfwid else "none",
                "right_id": right_id,
                "nama_score": 1.0 if nama_ok else 0.0,
                "geo_ok": geo_ok,
                "status": status,
                "match_type": mtype if mtype != "not_found" else "atlas_gfw",
                "human_verified": False,
                "evidence": {
                    "atlas_nama": nama,
                    "gfwid": gfwid,
                    "in_gabungan": in_gabungan,
                    "source_status": r.get("status"),
                    "source": "atlas_match",
                },
            }
        )

    # C) Atlas full without prior match → try name join to GFW / gabungan
    for r in atlas_full:
        atlas_id = r.get("atlas_id")
        if not atlas_id:
            continue
        nama = r.get("nama_perusahaan") or r.get("nama_kanonik") or ""
        nkey = norm_company(nama)
        if not nkey:
            continue
        # skip if already covered via atlas_match left_id containing atlas_id
        already = any(
            m.get("left_source") == "atlas"
            and (
                m.get("left_id") == atlas_id
                or (m.get("evidence") or {}).get("atlas_nama")
                and norm_company((m.get("evidence") or {}).get("atlas_nama")) == nkey
            )
            for m in out.values()
        )
        if already:
            continue

        in_gabungan = nkey in perusahaan_by_norm or norm_company(r.get("nama_kanonik") or "") in perusahaan_by_norm
        gfw_hits = gfw_by_norm.get(nkey) or []
        kab = r.get("kabupaten") or ""
        conflict_txt = text_non_riau(nama, kab, r.get("grup"))

        if gfw_hits:
            gfw = gfw_hits[0]
            gfwid = gfw["gfwid"]
            geo_ok = gfw.get("in_riau_bbox")
            if conflict_txt:
                geo_ok = False
            mtype = "gabungan_gfw" if in_gabungan else "gfw_only"
            status = decide_status(True, geo_ok, conflict_txt)
            mid = match_id_for("atlas", atlas_id, "gfw", gfwid)
            upsert(
                {
                    "match_id": mid,
                    "left_source": "atlas",
                    "left_id": atlas_id,
                    "right_source": "gfw",
                    "right_id": gfwid,
                    "nama_score": 0.9,
                    "geo_ok": geo_ok,
                    "status": status,
                    "match_type": mtype,
                    "human_verified": False,
                    "evidence": {
                        "atlas_nama": nama,
                        "kabupaten": kab,
                        "source": "atlas_full_name_join",
                    },
                }
            )
        elif in_gabungan:
            mid = match_id_for("atlas", atlas_id, "bps", perusahaan_by_norm[nkey].get("perusahaan_id") or nkey)
            # Name join tanpa GFW: pakai kab Riau sebagai proksi geo (bukan poligon GFW).
            if conflict_txt:
                geo_ok = False
                status = "conflict"
                geo_basis = "non_riau_text"
            elif kab_in_riau(kab):
                geo_ok = True
                status = "confirmed"
                geo_basis = "kab_riau"
            else:
                geo_ok = None
                status = "warning"
                geo_basis = "kab_unknown"
            upsert(
                {
                    "match_id": mid,
                    "left_source": "atlas",
                    "left_id": atlas_id,
                    "right_source": "bps",
                    "right_id": perusahaan_by_norm[nkey].get("perusahaan_id") or nkey,
                    "nama_score": 0.85,
                    "geo_ok": geo_ok,
                    "status": status,
                    "match_type": "gabungan_only",
                    "human_verified": False,
                    "evidence": {
                        "atlas_nama": nama,
                        "kabupaten": kab,
                        "source": "atlas_full_gabungan",
                        "geo_basis": geo_basis,
                    },
                }
            )
        else:
            mid = match_id_for("atlas", atlas_id, "none", "nf")
            upsert(
                {
                    "match_id": mid,
                    "left_source": "atlas",
                    "left_id": atlas_id,
                    "right_source": "none",
                    "right_id": "not_found",
                    "nama_score": 0.0,
                    "geo_ok": None,
                    "status": "rejected",
                    "match_type": "not_found",
                    "human_verified": False,
                    "evidence": {"atlas_nama": nama, "source": "atlas_full_unmatched"},
                }
            )

    return list(out.values())


def build_dossier(
    *,
    matches: list[dict],
    atlas_full: list[dict],
    perusahaan_by_norm: dict[str, dict],
    gfw_by_id: dict[str, dict],
    kasus: list[dict],
    sk36: list[dict],
) -> dict:
    konflik_by_norm: dict[str, list[str]] = {}
    for k in kasus:
        nama = k.get("perusahaan") or ""
        key = norm_company(nama)
        if not key:
            continue
        konflik_by_norm.setdefault(key, []).append(k.get("id") or "")

    sk36_by_norm: dict[str, dict] = {}
    for r in sk36:
        key = norm_company(r.get("nama_kanonik") or r.get("nama") or "")
        if key:
            sk36_by_norm[key] = r

    # Index best match per atlas left_id
    best_by_atlas: dict[str, dict] = {}
    for m in matches:
        if m.get("left_source") != "atlas":
            continue
        lid = m["left_id"]
        prev = best_by_atlas.get(lid)
        rank = {"confirmed": 0, "warning": 1, "conflict": 2, "rejected": 3}
        if prev is None or rank.get(m["status"], 9) < rank.get(prev["status"], 9):
            best_by_atlas[lid] = m

    records = []
    for r in atlas_full:
        atlas_id = r.get("atlas_id")
        if not atlas_id:
            continue
        nama = r.get("nama_perusahaan") or ""
        canon = r.get("nama_kanonik") or norm_company_display(nama)
        nkey = norm_company(canon or nama)
        m = best_by_atlas.get(atlas_id) or best_by_atlas.get(r.get("match_id") or "")
        # fallback: find by evidence nama
        if not m:
            for cand in matches:
                if cand.get("left_source") == "atlas" and norm_company(
                    (cand.get("evidence") or {}).get("atlas_nama") or ""
                ) == nkey:
                    m = cand
                    break

        gfwid = None
        status_match = "not_found"
        if m:
            if m.get("right_source") == "gfw":
                gfwid = m.get("right_id")
            status_match = m.get("match_type") or m.get("status")
            if m.get("status") == "conflict":
                status_match = "conflict"

        legal = None
        sk = sk36_by_norm.get(nkey)
        if sk:
            legal = f"sk36:{sk.get('status_proses') or 'terdaftar'}"
        elif nkey in perusahaan_by_norm:
            legal = "master_list"

        konflik_ids = konflik_by_norm.get(nkey) or []
        gfw = gfw_by_id.get(gfwid) if gfwid else None

        risiko = "rendah"
        if m and m.get("status") == "conflict":
            risiko = "tinggi"
        elif konflik_ids:
            risiko = "tinggi"
        elif m and m.get("status") == "warning":
            risiko = "sedang"
        elif sk and str(sk.get("prioritas") or "").lower().find("tinggi") >= 0:
            risiko = "sedang"

        records.append(
            {
                "dossier_id": f"DOS-{atlas_id}",
                "nama": nama,
                "nama_kanonik": canon,
                "kab": r.get("kabupaten"),
                "luas_loss_ha": r.get("hutan_tersisa_ha"),
                "gambut_ha": r.get("luas_gambut_ha"),
                "legal_status": legal,
                "konflik": ",".join(x for x in konflik_ids if x) or None,
                "tautan_atlas": atlas_id,
                "gfwid": gfwid,
                "status_match": status_match,
                "risiko": risiko,
                "human_verified": False,
                "luas_ha": r.get("luas_ha"),
                "area_gfw_ha": gfw.get("area_ha") if gfw else None,
                "match_status": m.get("status") if m else "rejected",
                "geo_ok": m.get("geo_ok") if m else None,
            }
        )

    return {
        "total": len(records),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "grain": "1 baris / konsesi Atlas (protokol OSINT langkah 7)",
        "fields": [
            "nama",
            "kab",
            "luas_loss_ha",
            "gambut_ha",
            "legal_status",
            "konflik",
            "tautan_atlas",
            "gfwid",
            "status_match",
            "risiko",
        ],
        "records": records,
    }


def enrich_alias(alias_payload: dict, gfw_by_norm: dict[str, list[dict]]) -> dict:
    records = []
    for r in alias_payload.get("records") or []:
        row = dict(r)
        key = norm_company(r.get("nama_kanonik") or r.get("nama_mentah") or "")
        hits = gfw_by_norm.get(key) or []
        if hits:
            geo = hits[0].get("in_riau_bbox")
            row["match_method"] = row.get("match_method") or "alias_table"
            row["geo_validated"] = bool(geo) if geo is not None else None
            if geo is False:
                row["rejected_reason"] = "gfw_centroid_outside_riau_bbox"
        else:
            row.setdefault("match_method", "alias_table")
            row.setdefault("geo_validated", None)
            row.setdefault("rejected_reason", None)
        records.append(row)
    out = dict(alias_payload)
    out["records"] = records
    out["total"] = len(records)
    return out


def main() -> int:
    print("=== build_entity_matches (Matching & Overlay Engine) ===")
    SILVER.mkdir(parents=True, exist_ok=True)

    alias_map = load_alias_table(ROOT / "dim_perusahaan_alias.csv")
    per = _load_json(DATA / "perusahaan.json") or {"records": []}
    alias = _load_json(DATA / "perusahaan_alias.json") or {"records": []}
    gfw = _load_json(DATA / "konsesi_gfw_full.json") or {"records": []}
    kons = _load_json(DATA / "konsesi.json") or {}
    pen = _load_json(DATA / "penertiban.json") or {}
    kasus = (_load_json(DATA / "kasus.json") or {}).get("records") or []

    per_enriched = enrich_perusahaan(per, alias_map)
    fact_gfw = build_fact_gfw(gfw, alias_map)
    fact_sk36 = build_fact_sk36(pen, alias_map)

    gfw_by_id = {r["gfwid"]: r for r in fact_gfw["records"]}
    gfw_by_norm: dict[str, list[dict]] = {}
    for r in fact_gfw["records"]:
        for key in filter(None, [norm_company(r.get("nama_kanonik")), norm_company(r.get("company_raw"))]):
            gfw_by_norm.setdefault(key, []).append(r)

    perusahaan_by_norm: dict[str, dict] = {}
    for r in per_enriched["records"]:
        for key in filter(None, [norm_company(r.get("nama")), norm_company(r.get("nama_kanonik"))]):
            perusahaan_by_norm[key] = r

    alias_enriched = enrich_alias(alias, gfw_by_norm)

    atlas_full = (kons.get("atlas_full") or {}).get("records") or []
    atlas_match = (kons.get("atlas_match") or {}).get("records") or []
    gfw_bps = (kons.get("gfw_match_bps") or {}).get("records") or []

    matches = build_matches(
        perusahaan_by_norm=perusahaan_by_norm,
        gfw_by_id=gfw_by_id,
        gfw_by_norm=gfw_by_norm,
        atlas_full=atlas_full,
        atlas_match=atlas_match,
        gfw_bps=gfw_bps,
    )

    # Hard invariant: confirmed ⇒ geo_ok is not False
    bad_confirmed = [m for m in matches if m["status"] == "confirmed" and m.get("geo_ok") is False]
    if bad_confirmed:
        print(f"FAIL: {len(bad_confirmed)} confirmed with geo_ok=false", file=sys.stderr)
        return 1

    dossier = build_dossier(
        matches=matches,
        atlas_full=atlas_full,
        perusahaan_by_norm=perusahaan_by_norm,
        gfw_by_id=gfw_by_id,
        kasus=kasus,
        sk36=fact_sk36["records"],
    )

    # Merge perusahaan_id into gold perusahaan.json (additive)
    _dump(DATA / "perusahaan.json", per_enriched)
    _dump(DATA / "perusahaan_alias.json", alias_enriched)

    # Sync nama_kanonik back onto gold GFW table (UI Data tab)
    gfw_out = dict(gfw)
    gfw_recs = []
    by_id = {r["gfwid"]: r for r in fact_gfw["records"]}
    for r in gfw.get("records") or []:
        row = dict(r)
        fg = by_id.get(row.get("gfwid"))
        if fg:
            row["nama_kanonik"] = fg.get("nama_kanonik") or row.get("nama_kanonik")
        elif not row.get("nama_kanonik"):
            raw = row.get("company") or row.get("name") or ""
            row["nama_kanonik"] = resolve_canonical(raw, alias_map) or norm_company_display(raw)
        gfw_recs.append(row)
    gfw_out["records"] = gfw_recs
    gfw_out["total"] = len(gfw_recs)
    _dump(DATA / "konsesi_gfw_full.json", gfw_out)

    # Serving-facing subset: exclude pure not_found (tetap di silver untuk audit)
    entity_ui = []
    for m in matches:
        if m.get("match_type") == "not_found" or (
            m.get("status") == "rejected" and m.get("right_source") == "none"
        ):
            continue
        entity_ui.append(
            {
                "match_id": m.get("match_id"),
                "left_source": m.get("left_source"),
                "left_id": m.get("left_id"),
                "right_source": m.get("right_source"),
                "right_id": m.get("right_id"),
                "status": m.get("status"),
                "match_type": m.get("match_type"),
                "nama_score": m.get("nama_score"),
                "geo_ok": m.get("geo_ok"),
                "human_verified": m.get("human_verified"),
                "evidence": m.get("evidence"),
            }
        )

    confirmed_geo = sum(
        1
        for m in entity_ui
        if m.get("status") == "confirmed" and m.get("geo_ok") is True
    )
    match_quality = {
        "n_bridge_all": len(matches),
        "n_serving": len(entity_ui),
        "n_not_found_excluded": len(matches) - len(entity_ui),
        "confirmed_geo_ok": confirmed_geo,
        "rate_serving": round(100.0 * confirmed_geo / max(len(entity_ui), 1), 1),
        "rate_bridge_all": round(100.0 * confirmed_geo / max(len(matches), 1), 1),
        "target_pct": 75.0,
        "pass": (100.0 * confirmed_geo / max(len(entity_ui), 1)) >= 75.0,
        "note": (
            "Metrik C7 = confirmed∧geo_ok / serving matches (not_found atlas_full "
            "tetap di silver/bridge, tidak dihitung di denominator UI)."
        ),
    }

    _dump(SILVER / "meta_sumber.json", {"total": len(META_SUMBER), "records": META_SUMBER})
    _dump(SILVER / "fact_gfw_konsesi.json", fact_gfw)
    _dump(SILVER / "fact_penertiban_sk36.json", fact_sk36)
    _dump(SILVER / "bridge_entity_match.json", {"total": len(matches), "records": matches})
    _dump(SILVER / "mart_dossier_kasus.json", dossier)
    _dump(DATA / "dossier.json", dossier)
    _dump(DATA / "entity_matches.json", {"total": len(entity_ui), "records": entity_ui})

    try:
        from write_ingest_runs import build_ingest_runs

        ingest_payload = build_ingest_runs(META_SUMBER)
    except Exception as exc:
        print(f"WARN: write_ingest_runs: {exc}")
        ingest_payload = None

    # Status histogram
    hist: dict[str, int] = {}
    for m in matches:
        hist[m["status"]] = hist.get(m["status"], 0) + 1
    mtype: dict[str, int] = {}
    for m in matches:
        mtype[m.get("match_type") or "?"] = mtype.get(m.get("match_type") or "?", 0) + 1
    # Keep meta.counts in sync for integration artifacts
    meta_path = DATA / "meta.json"
    if meta_path.exists():
        meta = _load_json(meta_path) or {}
        counts = dict(meta.get("counts") or {})
        counts["dossier"] = dossier["total"]
        counts["entity_matches"] = len(entity_ui)
        counts["gfw_bbox_full"] = len(gfw_recs)
        meta["counts"] = counts
        methodology = dict(meta.get("methodology") or {})
        methodology["match_quality"] = match_quality
        planned = [s for s in META_SUMBER if s.get("status") == "planned"]
        active = [s for s in META_SUMBER if s.get("status") == "active"]
        methodology["sumber_catalog"] = {
            "n_active": len(active),
            "n_planned": len(planned),
            "planned_ids": [s.get("sumber_id") for s in planned],
            "stubs_dir": "stubs/",
            "note": (
                "Sumber planned punya path_sot stub di stubs/; "
                "jangan dihitung sebagai data operasional sampai status=active."
            ),
        }
        if ingest_payload:
            methodology["ingest_run"] = {
                "generated_at": ingest_payload.get("generated_at"),
                "n": ingest_payload.get("total"),
                "success": sum(
                    1 for r in ingest_payload.get("records") or [] if r.get("status") == "success"
                ),
                "partial": sum(
                    1 for r in ingest_payload.get("records") or [] if r.get("status") == "partial"
                ),
                "failed": sum(
                    1 for r in ingest_payload.get("records") or [] if r.get("status") == "failed"
                ),
            }
        meta["methodology"] = methodology
        _dump(meta_path, meta)

    print(f"matches={len(matches)} serving={len(entity_ui)} status={hist} types={mtype}")
    print(
        f"match_quality serving={match_quality['rate_serving']}% "
        f"bridge_all={match_quality['rate_bridge_all']}% pass={match_quality['pass']}"
    )
    print(f"dossier={dossier['total']} gfw_facts={fact_gfw['total']} sk36={fact_sk36['total']}")
    print("RESULT: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
