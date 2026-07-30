#!/usr/bin/env python3
"""
Apply data-quality fixes from the DQ remediation plan (Fase 1–4).
Works on serving JSON + root CSV when XLSX workbooks are absent.

  python website/scripts/apply_dq_fixes.py
"""

from __future__ import annotations

import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve()
SITE = HERE.parents[1]
DATA = SITE / "data"
ROOT = SITE.parent if (SITE.parent / "master_list_objek_agrinas_satgas_riau.csv").exists() else SITE

sys.path.insert(0, str(HERE.parent))
from company_normalize import (  # noqa: E402
    load_alias_table,
    norm_company,
    norm_company_display,
    resolve_canonical,
)

NULLISH = {"", "none", "null", "nan", "-", "n/a", "na"}


def is_null(v) -> bool:
    if v is None:
        return True
    if isinstance(v, float) and v != v:
        return True
    if isinstance(v, str):
        return v.strip().lower() in NULLISH
    return False


def write_csv(path: Path, rows: list[dict], fieldnames: list[str] | None = None):
    if not rows:
        return
    fields = fieldnames or list(rows[0].keys())
    # union all keys
    for r in rows:
        for k in r:
            if k not in fields:
                fields.append(k)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k) for k in fields})
    print(f"  wrote {path.name} ({len(rows)} rows)")


def write_json(path: Path, payload):
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  wrote {path.name}")


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


# ─── Fase 1: kasus ───────────────────────────────────────────────────────────

NIHIL_RE = re.compile(r"historikonflik\s*nihil|nihil\s*nihil", re.I)
LP_RE = re.compile(r"LP\s*/?\s*[A-Z0-9/\.\-]+", re.I)


def classify_tipe(rec: dict) -> str:
    """Operasional hanya jika ada jejak LP; selain itu Potensi/register."""
    has_lp = (not is_null(rec.get("nomor_lp"))) or bool(
        LP_RE.search(str(rec.get("status") or "")) or LP_RE.search(str(rec.get("nomor_lp") or ""))
    )
    existing = str(rec.get("tipe_entri") or "").strip().lower()
    if has_lp:
        return "Kasus operasional"
    if existing.startswith("potensi"):
        return "Potensi/register"
    # Label lama 'Kasus operasional' tanpa LP → turunkan ke potensi agar DQ jujur
    return "Potensi/register"


def normalize_ws(v):
    if is_null(v):
        return None
    return re.sub(r"[ \t]+", " ", str(v).replace("\r", "")).strip()


def fix_kasus():
    print("Fase 1: kasus")
    path = DATA / "kasus.json"
    payload = load_json(path)
    records = payload.get("records") or []
    cleaned = []
    dropped_noise = 0
    flagged = 0
    for r in records:
        if is_null(r.get("id")):
            continue
        rec = dict(r)
        uraian = str(rec.get("uraian") or "")
        is_noise = bool(NIHIL_RE.search(uraian))
        if is_noise:
            # Drop from serving (do not feed Polres skor); keep in sidecar CSV archive
            dropped_noise += 1
            continue
        rec["tipe_entri"] = classify_tipe(rec)
        rec["nomor_lp"] = normalize_ws(rec.get("nomor_lp"))
        rec["status"] = normalize_ws(rec.get("status"))
        rec["upaya"] = normalize_ws(rec.get("upaya"))
        rec["uraian"] = normalize_ws(rec.get("uraian"))
        # Extract LP from status if nomor_lp empty
        if is_null(rec.get("nomor_lp")) and rec.get("status"):
            m = LP_RE.search(str(rec["status"]))
            if m:
                rec["nomor_lp"] = m.group(0).replace(" ", "")
        # Operational without LP → explicit flag
        if rec["tipe_entri"] == "Kasus operasional" and is_null(rec.get("nomor_lp")):
            rec["tanpa_lp"] = True
            rec["tanpa_lp_alasan"] = "Tidak tercantum nomor LP di sumber register"
        else:
            rec["tanpa_lp"] = False
            rec["tanpa_lp_alasan"] = None
        # Minimal status for operasional
        if rec["tipe_entri"] == "Kasus operasional" and is_null(rec.get("status")):
            if not is_null(rec.get("upaya")):
                rec["status"] = "Dalam penanganan (inferred dari upaya)"
            else:
                rec["status"] = "Status belum terdokumentasi di sumber"
        if rec["tipe_entri"] == "Kasus operasional" and is_null(rec.get("upaya")):
            rec["upaya"] = "Belum terdokumentasi di sumber terbuka"
        # completeness flags
        need = ["id", "polres", "kab_kota", "tipe_entri"]
        if rec["tipe_entri"] == "Kasus operasional":
            need += ["nomor_lp", "status"]
        missing = [f for f in need if is_null(rec.get(f)) and not (f == "nomor_lp" and rec.get("tanpa_lp"))]
        rec["dq_flags"] = {
            "missing": missing,
            "completeness": round(100.0 * (len(need) - len(missing)) / len(need), 1),
        }
        rec["status_verifikasi"] = "ok"
        cleaned.append(rec)
        flagged += 1

    write_json(path, {"total": len(cleaned), "records": cleaned})
    # Canonical CSV for future export fallback (flatten nested)
    csv_rows = []
    for r in cleaned:
        row = {k: v for k, v in r.items() if k != "dq_flags"}
        dq = r.get("dq_flags") or {}
        row["dq_completeness"] = dq.get("completeness")
        row["dq_missing"] = ",".join(dq.get("missing") or [])
        # tahun lists
        if isinstance(row.get("tahun_disebut"), list):
            row["tahun_disebut"] = ",".join(row["tahun_disebut"])
        if isinstance(row.get("tahun_kejadian"), list):
            row["tahun_kejadian"] = ",".join(row["tahun_kejadian"])
        csv_rows.append(row)
    write_csv(ROOT / "master_kasus_sawit_riau.csv", csv_rows)
    # Coverage note
    mapped = sum(1 for r in cleaned if not is_null(r.get("polres")) and "lintas" not in str(r.get("polres") or "").lower())
    print(f"    serving={len(cleaned)} dropped_noise={dropped_noise} mapped_polres~={mapped}")
    return cleaned


# ─── Fase 2: cocokan + SK36 ──────────────────────────────────────────────────

def fix_cocokan():
    print("Fase 2a: cocokan Atlas↔GFW")
    path = ROOT / "cocokan_atlas_gabungan_gfw.csv"
    rows = load_csv(path)
    if not rows:
        print("    skip: CSV missing")
        return []
    out = []
    for i, r in enumerate(rows, 1):
        rec = dict(r)
        atlas = (rec.get("atlas_nama") or rec.get("atlas_name") or "").strip()
        gfwid = (rec.get("gfwid") or "").strip()
        uid = (rec.get("atlas_uid") or rec.get("uid") or "").strip()
        # stable match_id
        base = uid or norm_company(atlas) or f"row{i}"
        gpart = gfwid or "nogfw"
        rec["match_id"] = f"{base}__{gpart}"
        rec["atlas_uid"] = uid or None
        rec["match_method"] = rec.get("match_method") or rec.get("status_kecocokan") or "name_match"
        conf = rec.get("match_confidence")
        if is_null(conf):
            status = str(rec.get("status_kecocokan") or "").lower()
            if "kuat" in status or "exact" in status:
                conf = "high"
            elif "lemah" in status or "partial" in status:
                conf = "low"
            else:
                conf = "medium"
        rec["match_confidence"] = conf
        # nama_kanonik for atlas side
        from company_normalize import resolve_canonical, load_alias_table

        amap = load_alias_table(ROOT / "dim_perusahaan_alias.csv")
        rec["nama_kanonik"] = resolve_canonical(atlas or rec.get("nama_lokal"), amap)
        out.append(rec)
    # ensure unique match_id
    seen = Counter(r["match_id"] for r in out)
    for r in out:
        if seen[r["match_id"]] > 1:
            # disambiguate by row content hash
            r["match_id"] = f"{r['match_id']}__{norm_company(r.get('name') or r.get('nama_lokal') or '')[:20] or 'x'}"
    # second pass uniqueness
    c2 = Counter(r["match_id"] for r in out)
    for i, r in enumerate(out):
        if c2[r["match_id"]] > 1:
            r["match_id"] = f"{r['match_id']}__{i}"
    write_csv(path, out)
    # also refresh konsesi.json atlas_match if present
    kons_path = DATA / "konsesi.json"
    if kons_path.exists():
        kons = load_json(kons_path)
        kons["atlas_match"] = {
            "total": len(out),
            "records": [
                {
                    "match_id": r.get("match_id"),
                    "atlas_nama": r.get("atlas_nama"),
                    "atlas_uid": r.get("atlas_uid"),
                    "gfwid": r.get("gfwid"),
                    "tahun": r.get("atlas_tahun"),
                    "tipe": r.get("atlas_tipe"),
                    "status": r.get("status_kecocokan"),
                    "match_method": r.get("match_method"),
                    "match_confidence": r.get("match_confidence"),
                    "nama_lokal": r.get("nama_lokal"),
                    "area_ha": _to_float(r.get("area_ha")),
                    "ada_di_bps": r.get("ada_di_bps"),
                    "ada_di_konflik_polda": r.get("ada_di_konflik_polda"),
                    "nama_kanonik": r.get("nama_kanonik"),
                }
                for r in out
            ],
        }
        # kepmenhut: prefer rapi only (already)
        write_json(kons_path, kons)
    print(f"    cocokan rows={len(out)} unique_match_id={len({r['match_id'] for r in out})}")
    return out


def _to_float(v):
    if is_null(v):
        return None
    try:
        return float(str(v).replace(",", ""))
    except ValueError:
        return None


def fix_sk36_penertiban():
    print("Fase 2b: penertiban SK36 composite keys")
    path = DATA / "penertiban.json"
    if not path.exists():
        print("    skip: penertiban.json missing")
        return
    pen = load_json(path)
    sk = ((pen.get("normalized") or {}).get("sk36_2025_110a") or {}).get("records") or []
    if not sk:
        # try rebuild from kepmenhut rapi CSV
        kep = load_csv(ROOT / "tabulasi_konsesi_sawit_kepmenhut_36_2025_riau_rapi.csv")
        rebuilt = []
        for i, r in enumerate(kep, 1):
            nama = r.get("Nama subjek hukum") or r.get("nama")
            if not nama:
                continue
            rebuilt.append(
                {
                    "no": i,
                    "nama": nama,
                    "dimohon_ha": _to_float(r.get("Luas permohonan (ha)")),
                    "berproses_ha": _to_float(r.get("Luas berproses (ha)")),
                    "ditolak_ha": _to_float(r.get("Luas ditolak (ha)")),
                    "status_proses": r.get("Status permohonan") or "tidak_diketahui",
                    "rasio_ditolak": None,
                    "prioritas": r.get("Implikasi"),
                    "record_id": f"sk36-{i}",
                }
            )
        sk = rebuilt

    # Explode rows that conflate statuses into composite-keyed rows
    out = []
    for i, r in enumerate(sk, 1):
        base = dict(r)
        statuses = []
        if not is_null(base.get("dimohon_ha")) and float(base.get("dimohon_ha") or 0) > 0:
            statuses.append(("dimohon", base.get("dimohon_ha")))
        if not is_null(base.get("berproses_ha")) and float(base.get("berproses_ha") or 0) > 0:
            statuses.append(("berproses", base.get("berproses_ha")))
        if not is_null(base.get("ditolak_ha")) and float(base.get("ditolak_ha") or 0) > 0:
            statuses.append(("ditolak", base.get("ditolak_ha")))
        if not statuses:
            statuses = [(base.get("status_proses") or "tidak_diketahui", None)]
        # If already has unique no+nama and we just need record_id:
        # Prefer one row per original with status_proses derived from dominant ha
        if len(statuses) == 1:
            st, ha = statuses[0]
            rec = dict(base)
            rec["status_proses"] = st
            rec["no"] = int(base.get("no") or i)
            rec["record_id"] = f"sk36-{rec['no']}-{st}"
            out.append(rec)
        else:
            # keep single row but set status_proses to multi-label and unique record_id by nama
            dominant = max(statuses, key=lambda x: float(x[1] or 0))
            rec = dict(base)
            rec["status_proses"] = dominant[0]
            rec["status_proses_all"] = "|".join(s for s, _ in statuses)
            rec["no"] = int(base.get("no") or i)
            rec["record_id"] = f"sk36-{norm_company(rec.get('nama'))[:40] or i}-{rec['no']}"
            out.append(rec)

    # Deduplicate by record_id; if collision, suffix
    seen = {}
    final = []
    for rec in out:
        rid = rec["record_id"]
        if rid in seen:
            seen[rid] += 1
            rec["record_id"] = f"{rid}-{seen[rid]}"
        else:
            seen[rid] = 1
        final.append(rec)

    # Also renumber no uniquely within file
    for i, rec in enumerate(final, 1):
        rec["no_partition"] = rec.get("no")
        rec["no"] = i
        if not rec.get("record_id"):
            rec["record_id"] = f"sk36-{i}-{rec.get('status_proses')}"

    pen.setdefault("normalized", {})["sk36_2025_110a"] = {
        "total": len(final),
        "records": final,
        "pk": "record_id",
        "note": "Composite identity via record_id; no is sequential after DQ fix",
    }
    write_json(path, pen)
    write_csv(ROOT / "tabulasi_sk36_2025_110a_riau_dq.csv", final)
    print(f"    sk36 records={len(final)} unique_record_id={len({r['record_id'] for r in final})}")

    # Deprecate parsial: rewrite from rapi if both exist
    rapi = ROOT / "tabulasi_konsesi_sawit_kepmenhut_36_2025_riau_rapi.csv"
    parsial = ROOT / "tabulasi_konsesi_sawit_kepmenhut_36_2025_riau_parsial.csv"
    if rapi.exists():
        rows = load_csv(rapi)
        # ensure unique no
        for i, r in enumerate(rows, 1):
            r["no"] = str(i)
        write_csv(parsial, rows)
        print(f"    kepmenhut parsial synced from rapi ({len(rows)} rows)")


# ─── Fase 3: objek geo grain ─────────────────────────────────────────────────

KAB_CANON = [
    "Bengkalis",
    "Dumai",
    "Indragiri Hilir",
    "Indragiri Hulu",
    "Kampar",
    "Kepulauan Meranti",
    "Kuantan Singingi",
    "Pelalawan",
    "Pekanbaru",
    "Rokan Hilir",
    "Rokan Hulu",
    "Siak",
]

KAB_ALIASES = {
    "rohul": "Rokan Hulu",
    "rokan hulu": "Rokan Hulu",
    "rohil": "Rokan Hilir",
    "rokan hilir": "Rokan Hilir",
    "inhu": "Indragiri Hulu",
    "indragiri hulu": "Indragiri Hulu",
    "inhil": "Indragiri Hilir",
    "indragiri hilir": "Indragiri Hilir",
    "kuansing": "Kuantan Singingi",
    "kuantan singingi": "Kuantan Singingi",
    "meranti": "Kepulauan Meranti",
    "kepulauan meranti": "Kepulauan Meranti",
    "kep meranti": "Kepulauan Meranti",
    "bengkalis": "Bengkalis",
    "dumai": "Dumai",
    "kota dumai": "Dumai",
    "kampar": "Kampar",
    "pelalawan": "Pelalawan",
    "pekanbaru": "Pekanbaru",
    "kota pekanbaru": "Pekanbaru",
    "siak": "Siak",
}

POLRES_FOR_KAB = {
    "Rokan Hulu": "Polres Rokan Hulu",
    "Rokan Hilir": "Polres Rokan Hilir",
    "Indragiri Hulu": "Polres Indragiri Hulu",
    "Indragiri Hilir": "Polres Indragiri Hilir",
    "Kuantan Singingi": "Polres Kuantan Singingi",
    "Pelalawan": "Polres Pelalawan",
    "Bengkalis": "Polres Bengkalis",
    "Kampar": "Polres Kampar",
    "Siak": "Polres Siak",
    "Dumai": "Polres Dumai",
    "Pekanbaru": "Polresta Pekanbaru",
    "Kepulauan Meranti": "Polres Kepulauan Meranti",
}

# Approximate centroids for priority mapping (proksi)
KAB_CENTROID = {
    "Rokan Hulu": (100.55, 0.88),
    "Rokan Hilir": (100.85, 1.85),
    "Indragiri Hulu": (102.35, -0.35),
    "Indragiri Hilir": (103.0, -0.35),
    "Kuantan Singingi": (101.55, -0.55),
    "Pelalawan": (102.0, 0.25),
    "Bengkalis": (102.1, 1.45),
    "Kampar": (101.25, 0.35),
    "Siak": (102.05, 0.85),
    "Dumai": (101.45, 1.68),
    "Pekanbaru": (101.45, 0.52),
    "Kepulauan Meranti": (102.4, 0.95),
}


def parse_kab_list(text: str | None) -> list[str]:
    if is_null(text):
        return []
    t = str(text)
    # split on / , ; dan
    parts = re.split(r"[/;,]|\s+dan\s+|\s+\+\s+", t)
    found = []
    for p in parts:
        n = re.sub(r"\b(kab\.?|kabupaten|kota)\b", " ", p.lower())
        n = re.sub(r"[^a-z0-9\s]", " ", n)
        n = re.sub(r"\s+", " ", n).strip()
        if not n:
            continue
        # direct alias
        if n in KAB_ALIASES:
            kab = KAB_ALIASES[n]
            if kab not in found:
                found.append(kab)
            continue
        for alias, kab in KAB_ALIASES.items():
            if alias in n or n in alias:
                if kab not in found:
                    found.append(kab)
                break
    return found


def fix_objek():
    print("Fase 3: objek kab_primary + mappable")
    csv_path = ROOT / "master_list_objek_agrinas_satgas_riau.csv"
    rows = load_csv(csv_path)
    if not rows:
        print("    skip: master list missing")
        return []
    out = []
    for r in rows:
        rec = dict(r)
        kabs = parse_kab_list(rec.get("kab_kota"))
        if len(kabs) == 1:
            rec["kab_primary"] = kabs[0]
            rec["kab_list"] = kabs[0]
        elif len(kabs) > 1:
            rec["kab_primary"] = "MULTI"
            rec["kab_list"] = "|".join(kabs)
        else:
            # broad / unknown
            raw = str(rec.get("kab_kota") or "").lower()
            if "provinsi" in raw or "multi" in raw or "riau" in raw:
                rec["kab_primary"] = "MULTI"
                rec["kab_list"] = ""
            else:
                rec["kab_primary"] = "MULTI"
                rec["kab_list"] = ""
        kp = rec["kab_primary"]
        rec["polres_primary"] = POLRES_FOR_KAB.get(kp) if kp != "MULTI" else None
        prio = str(rec.get("prioritas") or "").lower()
        mappable = kp != "MULTI" and prio in {"tinggi", "kritis", "sedang"}
        # also allow tinggi even if MULTI if list has kabs — map to first
        if not mappable and prio in {"tinggi", "kritis"} and kabs:
            rec["kab_primary"] = kabs[0]
            rec["kab_list"] = "|".join(kabs)
            rec["polres_primary"] = POLRES_FOR_KAB.get(kabs[0])
            mappable = True
        # Kritis/Tinggi: jika MULTI tapi kab_list ada, pakai kab pertama sebagai primary agregat
        if (
            str(rec.get("kab_primary")) == "MULTI"
            and prio in {"tinggi", "kritis"}
            and rec.get("kab_list")
        ):
            first = str(rec["kab_list"]).split("|")[0].strip()
            if first and first in POLRES_FOR_KAB:
                rec["kab_primary"] = first
                rec["polres_primary"] = POLRES_FOR_KAB.get(first)
                mappable = True
        rec["mappable"] = "ya" if mappable else "tidak"
        out.append(rec)
    write_csv(csv_path, out)

    # Update objek_agrinas.json
    records = []
    for r in out:
        records.append(
            {
                "id": r.get("id"),
                "nama": r.get("nama_kanonik"),
                "tipe_badan": r.get("tipe_badan"),
                "lapisan": r.get("lapisan"),
                "lapisan_semua": r.get("lapisan_semua"),
                "peran": r.get("peran"),
                "klaster": r.get("klaster"),
                "kab_kota": r.get("kab_kota"),
                "kab_primary": r.get("kab_primary"),
                "kab_list": r.get("kab_list"),
                "polres_primary": r.get("polres_primary"),
                "mappable": r.get("mappable"),
                "luas_disebut": r.get("luas_disebut"),
                "status_kredibilitas": r.get("status_kredibilitas"),
                "prioritas": r.get("prioritas"),
                "kaitan_agrinas": r.get("kaitan_agrinas"),
                "cro_regional": r.get("cro_regional"),
                "mitra_pair": r.get("mitra_pair") or None,
                "ada_di_bps": r.get("ada_di_bps"),
                "ada_di_konflik_polda": r.get("ada_di_konflik_polda"),
                "sumber": r.get("sumber"),
            }
        )
    write_json(DATA / "objek_agrinas.json", {"total": len(records), "records": records})
    n_primary = sum(1 for r in records if not is_null(r.get("kab_primary")))
    n_map = sum(1 for r in records if r.get("mappable") == "ya")
    print(f"    objek={len(records)} kab_primary={n_primary} mappable={n_map}")

    expand_spatial_points(records)
    return records


def expand_spatial_points(objek_records: list[dict]):
    """Add proksi points for mappable high-priority objek not already in layers."""
    print("Fase 3b: expand spatial points")
    geo_path = ROOT / "proksi_peta_titik_agrinas.geojson"
    layers_path = DATA / "layers.geojson"
    existing = {"type": "FeatureCollection", "features": []}
    if geo_path.exists():
        existing = load_json(geo_path)
    feats = existing.get("features") or []
    existing_names = {
        norm_company(str((f.get("properties") or {}).get("nama") or ""))
        for f in feats
    }
    existing_ids = {
        str((f.get("properties") or {}).get("id") or "")
        for f in feats
    }

    # Keep non-centroid features; append new ones
    new_feats = list(feats)
    n_add = 0
    seq = 100
    for r in objek_records:
        if r.get("mappable") != "ya":
            continue
        prio = str(r.get("prioritas") or "").lower()
        if prio not in {"tinggi", "kritis"}:
            continue
        key = norm_company(r.get("nama"))
        if key in existing_names:
            continue
        kab = r.get("kab_primary")
        if kab not in KAB_CENTROID:
            continue
        lon, lat = KAB_CENTROID[kab]
        # slight jitter by id hash so points don't stack
        h = sum(ord(c) for c in (r.get("id") or key)) % 17
        lon = lon + (h - 8) * 0.01
        lat = lat + ((h % 7) - 3) * 0.01
        seq += 1
        oid = r.get("id") or f"OBJ-AUTO-{seq}"
        if oid in existing_ids:
            oid = f"{oid}-PT"
        new_feats.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [lon, lat]},
                "properties": {
                    "id": oid,
                    "nama": r.get("nama"),
                    "kab_kota": kab,
                    "tipe": "Objek Agrinas (proksi kab)",
                    "prioritas": "P1" if prio == "kritis" else "P2",
                    "catatan": "Centroid kab proksi dari DQ Fase 3 — bukan koordinat resmi",
                    "polres_proksi": r.get("polres_primary"),
                    "sumber": "DQ expand dari master_list mappable",
                    "layer": "objek_titik",
                    "objek_id": r.get("id"),
                },
            }
        )
        existing_names.add(key)
        n_add += 1
        if n_add >= 40:
            break

    existing["features"] = new_feats
    write_json(geo_path, existing)

    # Rebuild layers with unique ids
    if layers_path.exists():
        layers = load_json(layers_path)
        other = [
            f
            for f in (layers.get("features") or [])
            if (f.get("properties") or {}).get("layer") != "objek_titik"
        ]
        titik = []
        for f in new_feats:
            props = dict(f.get("properties") or {})
            props["layer"] = "objek_titik"
            titik.append({"type": "Feature", "geometry": f.get("geometry"), "properties": props})
        all_feats = titik + other
        seen_ids: dict[str, int] = {}
        for f in all_feats:
            props = f.setdefault("properties", {})
            fid = str(props.get("id") or "feat")
            n = seen_ids.get(fid, 0)
            if n:
                props["id"] = f"{fid}-{n + 1}"
            seen_ids[fid] = n + 1
        layers["features"] = all_feats
        layers["schema_by_layer"] = {
            "objek_titik": ["id", "nama", "kab_kota", "prioritas", "polres_proksi", "layer"],
            "koridor": ["id", "nama", "anggota_kab", "geom_source", "layer"],
            "densitas_kasus": ["id", "nama", "n_kasus", "level_risiko", "layer"],
        }
        write_json(layers_path, layers)
    print(f"    spatial points total={len(new_feats)} added~={n_add}")


# ─── Fase 4: alias + company flags ───────────────────────────────────────────

def build_alias_and_match():
    print("Fase 4: dim_perusahaan_alias + flags")
    perusahaan = load_csv(ROOT / "daftar_perusahaan_sawit_riau_gabungan.csv")
    gfw = load_csv(ROOT / "tabulasi_konsesi_sawit_gfw_bbox_riau.csv")
    atlas = load_csv(ROOT / "tabulasi_konsesi_sawit_nusantara_atlas_riau.csv")
    match_bps = load_csv(ROOT / "tabulasi_konsesi_sawit_gfw_match_bps_riau.csv")

    aliases = []
    seen = set()

    def add_alias(mentah, kanonik, sumber, confidence="high"):
        if not mentah:
            return
        key = (norm_company(mentah), norm_company(kanonik or mentah))
        if not key[0] or key in seen:
            return
        seen.add(key)
        aliases.append(
            {
                "nama_mentah": mentah.strip(),
                "nama_kanonik": (kanonik or mentah).strip(),
                "sumber": sumber,
                "confidence": confidence,
            }
        )

    for r in perusahaan:
        nama = r.get("nama_perusahaan")
        add_alias(nama, norm_company_display(nama), "bps_gabungan", "high")
        raw = r.get("nama_mentah_bps")
        if raw:
            for part in re.split(r"[;|]", raw):
                add_alias(part.strip(), nama, "bps_mentah", "high")

    for r in gfw:
        add_alias(r.get("company"), norm_company_display(r.get("company")), "gfw", "medium")
        add_alias(r.get("name"), norm_company_display(r.get("company") or r.get("name")), "gfw_name", "low")

    for r in atlas:
        add_alias(r.get("nama_perusahaan"), norm_company_display(r.get("nama_perusahaan")), "atlas", "medium")

    for r in match_bps:
        add_alias(r.get("company"), r.get("nama_bps_match") or r.get("nama_bps"), "gfw_bps_match", "high")
        add_alias(r.get("name"), r.get("nama_bps_match") or r.get("nama_bps"), "gfw_bps_match", "medium")

    # Seed known expansions
    seeds = [
        ("PTPN V", "PERKEBUNAN NUSANTARA V", "seed"),
        ("PTP N V", "PERKEBUNAN NUSANTARA V", "seed"),
        ("PT PERKEBUNAN NUSANTARA V", "PERKEBUNAN NUSANTARA V", "seed"),
        ("INTI INDOSAWIT SUBUR", "INTI INDOSAWIT SUBUR", "seed"),
        ("PT. INTI INDO SAWIT SUBUR", "INTI INDOSAWIT SUBUR", "seed"),
        ("IVO MAS TUNGGAL", "IVO MAS TUNGGAL", "seed"),
        ("PT. IVO MAS TUNGGAL", "IVO MAS TUNGGAL", "seed"),
        ("KARYA TAMA BAKTI MULYA", "KARYA TAMA BAKTI MULYA", "seed"),
        ("KTBM", "KARYA TAMA BAKTI MULYA", "seed"),
        ("ALAM SARI LESTARI", "ALAM SARI LESTARI", "seed"),
        ("PT. ALAM SARI LESTARI", "ALAM SARI LESTARI", "seed"),
    ]
    for a, b, s in seeds:
        add_alias(a, b, s, "high")

    alias_path = ROOT / "dim_perusahaan_alias.csv"
    write_csv(alias_path, aliases, ["nama_mentah", "nama_kanonik", "sumber", "confidence"])
    amap = load_alias_table(alias_path)

    # Annotate GFW match + full with nama_kanonik
    for r in gfw:
        r["nama_kanonik"] = resolve_canonical(r.get("company") or r.get("name"), amap)
    write_csv(ROOT / "tabulasi_konsesi_sawit_gfw_bbox_riau.csv", gfw)

    for r in match_bps:
        r["nama_kanonik"] = resolve_canonical(
            r.get("nama_bps_match") or r.get("company") or r.get("name"), amap
        )
    write_csv(ROOT / "tabulasi_konsesi_sawit_gfw_match_bps_riau.csv", match_bps)

    for r in atlas:
        r["nama_kanonik"] = resolve_canonical(r.get("nama_perusahaan"), amap)
    write_csv(ROOT / "tabulasi_konsesi_sawit_nusantara_atlas_riau.csv", atlas)

    # Update perusahaan.json with gfw/atlas flags
    gfw_keys = {norm_company(r.get("nama_kanonik") or r.get("company")) for r in gfw}
    atlas_keys = {norm_company(r.get("nama_kanonik") or r.get("nama_perusahaan")) for r in atlas}
    per_out = []
    for r in perusahaan:
        nama = r.get("nama_perusahaan")
        canon = resolve_canonical(nama, amap)
        key = norm_company(canon)
        per_out.append(
            {
                "no": r.get("no"),
                "nama": nama,
                "nama_kanonik": canon,
                "sumber": r.get("sumber"),
                "ada_di_bps": r.get("ada_di_bps"),
                "ada_di_konflik_polda": r.get("ada_di_konflik_polda"),
                "ada_di_gfw": "Ya" if key in gfw_keys else "Tidak",
                "ada_di_atlas": "Ya" if key in atlas_keys else "Tidak",
                "status_nama": r.get("status_nama"),
                "catatan": r.get("catatan"),
            }
        )
    write_json(DATA / "perusahaan.json", {"total": len(per_out), "records": per_out})
    # also update gabungan csv flags
    for r, p in zip(perusahaan, per_out):
        r["nama_kanonik"] = p["nama_kanonik"]
        r["ada_di_gfw"] = p["ada_di_gfw"]
        r["ada_di_atlas"] = p["ada_di_atlas"]
    write_csv(ROOT / "daftar_perusahaan_sawit_riau_gabungan.csv", perusahaan)

    overlap = len(gfw_keys & atlas_keys)
    print(f"    aliases={len(aliases)} gfw∩atlas_kanonik={overlap}")

    # Refresh gfw_match_bps in konsesi.json with nama_kanonik
    kons_path = DATA / "konsesi.json"
    if kons_path.exists():
        kons = load_json(kons_path)
        kons["gfw_match_bps"] = {
            "total": len(match_bps),
            "records": [
                {
                    "nama_bps": r.get("nama_bps_match"),
                    "nama_kanonik": r.get("nama_kanonik"),
                    "company": r.get("company"),
                    "name": r.get("name"),
                    "group": r.get("group_comp"),
                    "type": r.get("type"),
                    "legal": r.get("po_legalst"),
                    "hgu": r.get("po_hgu"),
                    "area_ha": _to_float(r.get("area_ha")),
                    "gfwid": r.get("gfwid"),
                }
                for r in match_bps
            ],
        }
        # kepmenhut from rapi only
        kep = load_csv(ROOT / "tabulasi_konsesi_sawit_kepmenhut_36_2025_riau_rapi.csv")
        if kep:
            kons["kepmenhut_36_2025"] = {
                "total": len(kep),
                "records": [
                    {
                        "nama": r.get("Nama subjek hukum"),
                        "luas_permohonan_ha": _to_float(r.get("Luas permohonan (ha)")),
                        "luas_berproses_ha": _to_float(r.get("Luas berproses (ha)")),
                        "luas_ditolak_ha": _to_float(r.get("Luas ditolak (ha)")),
                        "status": r.get("Status permohonan"),
                        "kelengkapan": r.get("Kelengkapan data"),
                        "implikasi": r.get("Implikasi"),
                    }
                    for r in kep
                ],
            }
        write_json(kons_path, kons)

    # Update konsesi_gfw_full nama_kanonik
    gfw_full_path = DATA / "konsesi_gfw_full.json"
    if gfw_full_path.exists():
        gf = load_json(gfw_full_path)
        for r in gf.get("records") or []:
            r["nama_kanonik"] = resolve_canonical(r.get("company") or r.get("name"), amap)
        write_json(gfw_full_path, gf)

    return overlap


def update_meta_counts(kasus):
    meta_path = DATA / "meta.json"
    if not meta_path.exists():
        return
    meta = load_json(meta_path)
    counts = meta.get("counts") or {}
    counts["kasus_konflik"] = len(kasus)
    objek = load_json(DATA / "objek_agrinas.json").get("records") or []
    counts["objek_agrinas"] = len(objek)
    layers = load_json(DATA / "layers.geojson") if (DATA / "layers.geojson").exists() else {}
    counts["fitur_spasial"] = len(layers.get("features") or [])
    lintas = sum(
        1
        for r in kasus
        if "lintas" in str(r.get("polres") or "").lower() or "lintas" in str(r.get("kab_kota") or "").lower()
    )
    mapped = len(kasus) - lintas
    counts["entri_terpetakan"] = mapped
    counts["entri_tidak_terpetakan"] = lintas
    meta["counts"] = counts
    meta["catatan"] = (
        "Choropleth ADM2; koridor = hull titik objek (default off); densitas centroid (default off); "
        f"coverage {mapped}/{lintas} setelah DQ; skor = indeks liputan+objek+register. "
        "Bukan batas legal HGU/IUP."
    )
    meta["update_command"] = (
        "python website/scripts/apply_dq_fixes.py && python website/scripts/export_web_data.py"
    )
    meth = meta.get("methodology") or {}
    meth["dq_note"] = (
        "DQ plan applied: noise kasus dropped; tanpa_lp flag; kab_primary pada objek; "
        "match_id cocokan; sk36 record_id; company alias."
    )
    meth["disclaimer"] = (
        "Indeks liputan+objek+register terbuka — bukan vonis operasional. "
        f"Setelah DQ: {mapped}/{lintas} entri terpetakan/tidak. "
        "Kalibrasi ulang dengan rekap LP/SPKT 36 bulan resmi."
    )
    meta["methodology"] = meth
    from datetime import datetime, timezone

    meta["updated_at"] = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    write_json(meta_path, meta)

    # Keep polres.coverage in sync with meta (UI historically read polres.coverage first)
    polres_path = DATA / "polres.json"
    if polres_path.exists():
        pol = load_json(polres_path)
        cov = pol.get("coverage") or {}
        cov["total_entri_terpetakan"] = mapped
        cov["entri_tidak_terpetakan"] = lintas
        pol["coverage"] = cov
        write_json(polres_path, pol)


def main():
    print(f"ROOT={ROOT}")
    print(f"DATA={DATA}")
    kasus = fix_kasus()
    fix_cocokan()
    fix_sk36_penertiban()
    fix_objek()
    overlap = build_alias_and_match()
    update_meta_counts(kasus)
    print(f"Done. company overlap kanonik~={overlap}")


if __name__ == "__main__":
    main()
