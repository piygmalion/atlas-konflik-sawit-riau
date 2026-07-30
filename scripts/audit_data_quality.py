#!/usr/bin/env python3
"""Audit null / completeness / duplicates for Atlas Konflik Sawit Riau tables."""

from __future__ import annotations

import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve()
SITE = HERE.parents[1] / "data"
_root_cand = HERE.parents[2]
ROOT = (
    _root_cand
    if (_root_cand / "master_list_objek_agrinas_satgas_riau.csv").exists()
    else HERE.parents[1]
)
OUT = ROOT / "tmp" / "data_quality_audit.json"
OUT.parent.mkdir(parents=True, exist_ok=True)

NULLISH = {"", "none", "null", "nan", "-", "n/a", "na", "n.a.", "tidak ada"}


def is_null(v) -> bool:
    if v is None:
        return True
    if isinstance(v, float) and v != v:
        return True
    if isinstance(v, str):
        return v.strip().lower() in NULLISH
    if isinstance(v, (list, dict)) and len(v) == 0:
        return True
    return False


def get_field(r: dict, f: str):
    if "." in f:
        a, b = f.split(".", 1)
        parent = r.get(a)
        if isinstance(parent, dict):
            return parent.get(b)
        return None
    return r.get(f)


def audit_records(name, records, pk_fields=None, dup_fields=None, important=None):
    pk_fields = pk_fields or []
    dup_fields = dup_fields or []
    important = important or []
    n = len(records)
    if n == 0:
        return {"table": name, "n": 0, "status": "EMPTY"}

    key_counts = Counter()
    null_counts = Counter()
    sample_types = {}
    for r in records:
        if not isinstance(r, dict):
            continue
        flat = {}
        for k, v in r.items():
            flat[k] = v
            if isinstance(v, dict):
                for kk, vv in v.items():
                    flat[f"{k}.{kk}"] = vv
        for k, v in flat.items():
            key_counts[k] += 1
            if is_null(v):
                null_counts[k] += 1
            else:
                sample_types.setdefault(k, type(v).__name__)

    fields = []
    for k in sorted(key_counts.keys()):
        present = key_counts[k]
        nulls = null_counts[k] + (n - present)
        fill = 100.0 * (n - nulls) / n if n else 0
        fields.append(
            {
                "field": k,
                "present": present,
                "nulls": nulls,
                "null_pct": round(100.0 * nulls / n, 1),
                "fill_pct": round(fill, 1),
                "type": sample_types.get(k, "null"),
                "important": k in important
                or any(k == i or k.startswith(i + ".") for i in important),
            }
        )

    uniqueness = []
    for fields_combo in list(pk_fields) + list(dup_fields):
        if isinstance(fields_combo, str):
            fields_combo = [fields_combo]
        vals = []
        null_pk = 0
        for r in records:
            parts = []
            bad = False
            for f in fields_combo:
                v = get_field(r, f)
                if is_null(v):
                    bad = True
                    break
                parts.append(str(v).strip().lower())
            if bad:
                null_pk += 1
                continue
            vals.append("|".join(parts))
        c = Counter(vals)
        dups = {k: v for k, v in c.items() if v > 1}
        uniqueness.append(
            {
                "fields": fields_combo,
                "role": "pk" if fields_combo in [[x] if isinstance(x, str) else x for x in pk_fields]
                or fields_combo in pk_fields
                or any(
                    fields_combo == ([x] if isinstance(x, str) else x) for x in pk_fields
                )
                else "dup_check",
                "non_null": len(vals),
                "null_or_missing": null_pk,
                "unique": len(c),
                "dup_groups": len(dups),
                "dup_rows": sum(v - 1 for v in dups.values()),
                "top_dups": sorted(([k, v] for k, v in dups.items()), key=lambda x: -x[1])[:8],
            }
        )

    imp = [
        f
        for f in fields
        if f["field"] in important
        or any(f["field"] == i or f["field"].startswith(i + ".") for i in important)
    ]
    avg_fill_imp = round(sum(f["fill_pct"] for f in imp) / len(imp), 1) if imp else None
    worst = sorted([f for f in fields if f["null_pct"] > 0], key=lambda x: -x["null_pct"])[:12]

    critical_nulls = [
        f
        for f in fields
        if f["important"] and f["null_pct"] > 0 and f["field"] in important
    ]

    return {
        "table": name,
        "n": n,
        "n_fields": len(fields),
        "avg_fill_important": avg_fill_imp,
        "fields": fields,
        "worst_nulls": worst,
        "critical_nulls": critical_nulls,
        "uniqueness": uniqueness,
        "important": important,
    }


def load_json_records(path: Path, keys=("records",)):
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return data
    for k in keys:
        if k in data and isinstance(data[k], list):
            return data[k]
    return []


def load_csv(path: Path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def norm(s: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


def main():
    audits = []

    kab = load_json_records(SITE / "kab_kota.json")
    audits.append(
        audit_records(
            "kab_kota.json",
            kab,
            pk_fields=["id", "kab_kota"],
            dup_fields=["polres_proksi", "cluster"],
            important=[
                "id",
                "kab_kota",
                "cluster",
                "skor_komposit",
                "kategori_peta",
                "polres_proksi",
                "lon",
                "lat",
                "n_kasus",
                "risiko_register.skor",
                "risiko_register.level",
            ],
        )
    )

    pol = load_json_records(SITE / "polres.json")
    audits.append(
        audit_records(
            "polres.json",
            pol,
            pk_fields=["polres", "peringkat"],
            important=[
                "peringkat",
                "polres",
                "skor",
                "kategori",
                "skor_osint",
                "skor_register",
                "n_entri",
                "komponen.liputan",
                "komponen.aksi",
                "komponen.objek",
                "komponen.status",
                "komponen.adat",
                "alasan",
            ],
        )
    )

    obj = load_json_records(SITE / "objek_agrinas.json")
    audits.append(
        audit_records(
            "objek_agrinas.json",
            obj,
            pk_fields=["id", "nama"],
            dup_fields=[["nama"], ["nama", "kab_kota"]],
            important=[
                "id",
                "nama",
                "tipe_badan",
                "lapisan",
                "klaster",
                "kab_kota",
                "prioritas",
                "status_kredibilitas",
                "kaitan_agrinas",
                "sumber",
            ],
        )
    )

    kas = load_json_records(SITE / "kasus.json")
    audits.append(
        audit_records(
            "kasus.json",
            kas,
            pk_fields=["id"],
            dup_fields=[["nomor_lp"], ["uraian"], ["lokasi", "perusahaan"]],
            important=[
                "id",
                "polres",
                "kab_kota",
                "tahun",
                "tipe_entri",
                "tema",
            ],
        )
    )

    per = load_json_records(SITE / "perusahaan.json")
    audits.append(
        audit_records(
            "perusahaan.json",
            per,
            pk_fields=["no", "nama"],
            dup_fields=[["nama"]],
            important=[
                "no",
                "nama",
                "sumber",
                "ada_di_bps",
                "ada_di_konflik_polda",
                "status_nama",
            ],
        )
    )

    kons = json.loads((SITE / "konsesi.json").read_text(encoding="utf-8"))
    for key, block in kons.items():
        if not isinstance(block, dict) or "records" not in block:
            continue
        recs = block["records"]
        sample = recs[0] if recs else {}
        if key == "gfw_match_bps":
            audits.append(
                audit_records(
                    f"konsesi.json::{key}",
                    recs,
                    pk_fields=["gfwid", "nama_bps"],
                    dup_fields=[["company"], ["nama_bps"], ["gfwid"]],
                    important=["nama_bps", "company", "name", "group", "area_ha", "gfwid"],
                )
            )
        elif key == "atlas_match":
            audits.append(
                audit_records(
                    f"konsesi.json::{key}",
                    recs,
                    pk_fields=["match_id"],
                    dup_fields=[["gfwid"], ["atlas_nama"]],
                    important=["match_id", "atlas_nama", "match_confidence", "status"],
                )
            )
        else:
            pks = [k for k in ["uid", "gfwid", "id", "no", "nama_perusahaan"] if k in sample][:2]
            dups = [[k] for k in ["uid", "nama_perusahaan", "company", "name"] if k in sample]
            imp = list(sample.keys())[:10]
            audits.append(
                audit_records(
                    f"konsesi.json::{key}",
                    recs,
                    pk_fields=pks,
                    dup_fields=dups,
                    important=imp,
                )
            )

    pen = json.loads((SITE / "penertiban.json").read_text(encoding="utf-8"))
    for key, block in (pen.get("normalized") or {}).items():
        if not isinstance(block, dict) or "records" not in block:
            continue
        recs = block["records"]
        sample = recs[0] if recs else {}
        cand = [k for k in ["record_id", "kab_kota", "nama", "nama_perusahaan", "no", "id", "peringkat"] if k in sample]
        pk = ["record_id"] if key == "sk36_2025_110a" and "record_id" in sample else cand[:2]
        if key == "gelombang1_27_pt":
            important = ["no", "perusahaan", "kabupaten"]
        elif key == "sk36_2025_110a":
            important = ["record_id", "nama", "no"]
        else:
            important = list(sample.keys())[:10]
        audits.append(
            audit_records(
                f"penertiban.json::{key}",
                recs,
                pk_fields=pk,
                dup_fields=[[c] for c in cand[:2] if c != "record_id"],
                important=important,
            )
        )

    gfw = load_json_records(SITE / "konsesi_gfw_full.json")
    audits.append(
        audit_records(
            "konsesi_gfw_full.json",
            gfw,
            pk_fields=["gfwid", "no"],
            dup_fields=[["company"], ["name"], ["gfwid"]],
            important=["no", "company", "name", "group", "area_ha", "gfwid", "lon", "lat"],
        )
    )

    layers = json.loads((SITE / "layers.geojson").read_text(encoding="utf-8"))
    layer_recs = []
    for f in layers.get("features") or []:
        p = dict(f.get("properties") or {})
        g = f.get("geometry") or {}
        p["_geom_type"] = g.get("type")
        p["_has_geom"] = g.get("coordinates") is not None
        layer_recs.append(p)
    audits.append(
        audit_records(
            "layers.geojson",
            layer_recs,
            pk_fields=["id"],
            dup_fields=[["nama"], ["id", "layer"]],
            important=["id", "nama", "kab_kota", "layer", "prioritas", "polres_proksi", "_geom_type", "_has_geom"],
        )
    )

    adm = json.loads((SITE / "adm2_riau.geojson").read_text(encoding="utf-8"))
    adm_recs = []
    for f in adm.get("features") or []:
        p = dict(f.get("properties") or {})
        p["_has_geom"] = f.get("geometry") is not None
        adm_recs.append(p)
    audits.append(
        audit_records(
            "adm2_riau.geojson",
            adm_recs,
            pk_fields=["id", "nama"],
            important=["id", "nama", "shape_name", "skor", "skor_risiko", "_has_geom"],
        )
    )

    ana = json.loads((SITE / "analytics.json").read_text(encoding="utf-8"))
    ana_summary = {"table": "analytics.json", "top_keys": list(ana.keys()), "sizes": {}}
    for k, v in ana.items():
        if isinstance(v, list):
            ana_summary["sizes"][k] = len(v)
            if v and isinstance(v[0], dict):
                audits.append(
                    audit_records(
                        f"analytics.json::{k}",
                        v,
                        pk_fields=[list(v[0].keys())[0]],
                        important=list(v[0].keys())[:10],
                    )
                )
        elif isinstance(v, dict):
            ana_summary["sizes"][k] = {
                kk: (len(vv) if isinstance(vv, list) else type(vv).__name__)
                for kk, vv in list(v.items())[:20]
            }
        else:
            ana_summary["sizes"][k] = type(v).__name__

    csv_specs = [
        (
            "master_list_objek_agrinas_satgas_riau.csv",
            ["id", "nama_kanonik"],
            [["nama_kanonik"]],
            ["id", "nama_kanonik", "kab_kota", "prioritas", "status_kredibilitas", "sumber"],
        ),
        (
            "ranking_potensi_konflik_per_polres.csv",
            ["peringkat", "polres"],
            [],
            ["peringkat", "polres", "skor", "kategori"],
        ),
        (
            "cluster_kabkota_agrinas.csv",
            ["kab_kota"],
            [["polres_proksi"]],
            ["kab_kota", "cluster", "skor_komposit", "lon_centroid_proksi", "lat_centroid_proksi"],
        ),
        (
            "daftar_perusahaan_sawit_riau_gabungan.csv",
            ["no", "nama_perusahaan"],
            [["nama_perusahaan"]],
            ["no", "nama_perusahaan", "sumber", "ada_di_bps", "ada_di_konflik_polda"],
        ),
        (
            "tabulasi_konsesi_sawit_nusantara_atlas_riau.csv",
            ["uid", "id"],
            [["nama_perusahaan"], ["uid"]],
            ["uid", "nama_perusahaan", "grup", "kabupaten", "luas_ha"],
        ),
        (
            "tabulasi_konsesi_sawit_gfw_bbox_riau.csv",
            ["gfwid"],
            [["company"], ["gfwid"], ["name"]],
            ["gfwid", "company", "name", "group", "area_ha"],
        ),
        (
            "tabulasi_konsesi_sawit_gfw_match_bps_riau.csv",
            ["gfwid"],
            [["nama_bps"], ["gfwid"]],
            ["gfwid", "nama_bps", "company", "area_ha"],
        ),
        ("tabulasi_konsesi_sawit_kepmenhut_36_2025_riau_rapi.csv", None, None, None),
        ("tabulasi_konsesi_sawit_kepmenhut_36_2025_riau_parsial.csv", None, None, None),
        ("cocokan_atlas_gabungan_gfw.csv", ["match_id"], [["gfwid"], ["atlas_nama"]], ["match_id", "atlas_nama", "match_confidence", "gfwid"]),
        ("tabulasi_perusahaan_konsesi_sawit_nusantara_atlas_riau.csv", None, None, None),
        ("tabulasi_grup_konsesi_sawit_nusantara_atlas_riau.csv", None, None, None),
    ]

    csv_audits = []
    for name, pks, dups, imp in csv_specs:
        path = ROOT / name
        if not path.exists():
            csv_audits.append({"table": name, "n": 0, "status": "MISSING"})
            continue
        rows = load_csv(path)
        sample = rows[0] if rows else {}
        if pks is None:
            cand = [
                k
                for k in [
                    "id",
                    "uid",
                    "gfwid",
                    "no",
                    "nama_perusahaan",
                    "nama",
                    "kab_kota",
                    "polres",
                    "grup",
                ]
                if k in sample
            ]
            pks = cand[:2] or ([list(sample.keys())[0]] if sample else [])
            dups = [[k] for k in cand[:3]]
            imp = list(sample.keys())[:10]
        csv_audits.append(
            audit_records(name, rows, pk_fields=pks, dup_fields=dups or [], important=imp or [])
        )

    # Cross checks — prefer canonical company keys when present
    try:
        sys.path.insert(0, str(HERE.parent))
        from company_normalize import norm_company as norm_co
    except Exception:
        norm_co = norm

    polres_kasus = Counter((r.get("polres") or "").strip() for r in kas)
    pn = Counter(norm(r.get("nama")) for r in per)
    gfw_companies = {
        norm_co(r.get("nama_kanonik") or r.get("company")) for r in gfw if (r.get("nama_kanonik") or r.get("company"))
    }
    atlas_path = ROOT / "tabulasi_konsesi_sawit_nusantara_atlas_riau.csv"
    atlas_companies = set()
    if atlas_path.exists():
        for r in load_csv(atlas_path):
            atlas_companies.add(norm_co(r.get("nama_kanonik") or r.get("nama_perusahaan")))

    layer_obj = [r for r in layer_recs if r.get("layer") == "objek_titik"]
    ops = [r for r in kas if str(r.get("tipe_entri") or "").lower().startswith("kasus")]
    cross = {
        "layers_objek_titik": len(layer_obj),
        "objek_total": len(obj),
        "kab_n": len(kab),
        "polres_n": len(pol),
        "kasus_n": len(kas),
        "kasus_ops_n": len(ops),
        "kasus_ops_lp_fill_pct": round(
            100.0 * sum(1 for r in ops if not is_null(r.get("nomor_lp")) or r.get("tanpa_lp")) / len(ops), 1
        )
        if ops
        else None,
        "kasus_ops_status_fill_pct": round(
            100.0 * sum(1 for r in ops if not is_null(r.get("status"))) / len(ops), 1
        )
        if ops
        else None,
        "kasus_polres_distinct": len([k for k in polres_kasus if k and not is_null(k)]),
        "kasus_polres_null": sum(v for k, v in polres_kasus.items() if is_null(k)),
        "kasus_nomor_lp_null": sum(1 for r in kas if is_null(r.get("nomor_lp"))),
        "kasus_uraian_null": sum(1 for r in kas if is_null(r.get("uraian"))),
        "kasus_perusahaan_null": sum(1 for r in kas if is_null(r.get("perusahaan"))),
        "kasus_kategori_null": sum(1 for r in kas if is_null(r.get("kategori"))),
        "kasus_jenis_null": sum(1 for r in kas if is_null(r.get("jenis"))),
        "objek_kab_primary_filled": sum(1 for r in obj if not is_null(r.get("kab_primary"))),
        "objek_kab_primary_single": sum(
            1 for r in obj if r.get("kab_primary") and str(r.get("kab_primary")) != "MULTI"
        ),
        "objek_kab_multi_or_broad": sum(1 for r in obj if str(r.get("kab_primary") or "") == "MULTI"),
        "objek_mitra_pair_null": sum(1 for r in obj if is_null(r.get("mitra_pair"))),
        "perusahaan_norm_dup_groups": sum(1 for v in pn.values() if v > 1),
        "perusahaan_norm_dup_rows": sum(v - 1 for v in pn.values() if v > 1),
        "gfw_companies": len(gfw_companies),
        "atlas_companies": len(atlas_companies),
        "company_name_overlap_norm": len(gfw_companies & atlas_companies),
    }

    # Grade each table
    def grade(a):
        if a.get("status") in {"EMPTY", "MISSING"}:
            return "F", "missing/empty"
        issues = []
        table = a.get("table") or ""
        for u in a.get("uniqueness", []):
            fields = u.get("fields") or []
            if len(fields) != 1 or u.get("dup_groups", 0) <= 0:
                continue
            f0 = fields[0]
            # gfwid may repeat on match tables (many-to-many); PK is match_id
            if f0 == "gfwid" and ("cocokan" in table or "atlas_match" in table):
                continue
            # sequential no may collide historically; prefer record_id
            if f0 == "no" and "sk36" in table:
                continue
            if f0 in {"id", "gfwid", "uid", "match_id", "record_id", "peringkat", "polres", "kab_kota"}:
                issues.append(f"dup {fields}:{u['dup_groups']} groups")
        crit = a.get("critical_nulls") or []
        high = [c for c in crit if c["null_pct"] >= 20]
        if high:
            issues.append(f"{len(high)} important fields >=20% null")
        fill = a.get("avg_fill_important")
        if fill is not None and fill < 70:
            issues.append(f"avg important fill {fill}%")
        if not issues:
            if fill is not None and fill >= 95:
                return "A", "bersih"
            return "B", "baik, null sekunder"
        if any(i.startswith("dup") for i in issues):
            return "D", "; ".join(issues)
        if fill is not None and fill < 60:
            return "D", "; ".join(issues)
        return "C", "; ".join(issues)

    overview = []
    for a in audits + csv_audits:
        g, note = grade(a)
        pk_dup = 0
        for u in a.get("uniqueness") or []:
            if len(u.get("fields", [])) == 1 and u["fields"][0] in {
                "id",
                "gfwid",
                "uid",
                "no",
                "peringkat",
                "polres",
                "kab_kota",
            }:
                pk_dup += u.get("dup_groups", 0)
        overview.append(
            {
                "table": a.get("table"),
                "n": a.get("n", 0),
                "status": a.get("status", "ok"),
                "avg_fill_important": a.get("avg_fill_important"),
                "pk_dup_groups": pk_dup,
                "grade": g,
                "note": note,
                "top_null_fields": [
                    f"{x['field']} {x['null_pct']}%" for x in (a.get("worst_nulls") or [])[:5]
                ],
            }
        )

    payload = {
        "serving": audits,
        "csv": csv_audits,
        "analytics_summary": ana_summary,
        "cross": cross,
        "overview": overview,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print("wrote", OUT)
    print("\n=== OVERVIEW ===")
    for o in overview:
        print(
            f"{o['grade']:1} | n={o['n']:4} | fill={str(o['avg_fill_important']):>5} | "
            f"pk_dup={o['pk_dup_groups']} | {o['table']} | {o['note']}"
        )
        if o["top_null_fields"]:
            print("     nulls:", "; ".join(o["top_null_fields"]))
    print("\n=== CROSS ===")
    print(json.dumps(cross, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
