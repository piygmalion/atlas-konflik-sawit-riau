#!/usr/bin/env python3
"""
Gate validasi serving layer website/data.
Exit non-zero jika PK duplikat atau meta counts tidak cocok.
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve()
SITE = HERE.parents[1] / "data"

NULLISH = {"", "none", "null", "nan", "-", "n/a", "na", "n.a."}


def is_null(v) -> bool:
    if v is None:
        return True
    if isinstance(v, float) and v != v:
        return True
    if isinstance(v, str):
        return v.strip().lower() in NULLISH
    return False


def load_records(name: str) -> list[dict]:
    path = SITE / name
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and isinstance(data.get("records"), list):
        return data["records"]
    return []


def dup_groups(values: list[str]) -> dict[str, int]:
    c = Counter(values)
    return {k: v for k, v in c.items() if v > 1}


def check_unique(label: str, records: list[dict], field: str, errors: list[str]):
    vals = []
    nulls = 0
    for r in records:
        v = r.get(field)
        if is_null(v):
            nulls += 1
            continue
        vals.append(str(v).strip().lower())
    dups = dup_groups(vals)
    if dups:
        top = sorted(dups.items(), key=lambda x: -x[1])[:5]
        errors.append(f"PK duplikat {label}.{field}: {len(dups)} grup (contoh {top})")
    if nulls and field in {"id", "gfwid", "uid"}:
        errors.append(f"{label}.{field}: {nulls} null (wajib terisi)")


def main() -> int:
    errors: list[str] = []
    warnings: list[str] = []

    if not SITE.exists():
        print(f"FAIL: data dir missing {SITE}", file=sys.stderr)
        return 2

    kasus = load_records("kasus.json")
    objek = load_records("objek_agrinas.json")
    kab = load_records("kab_kota.json")
    polres = load_records("polres.json")
    gfw = load_records("konsesi_gfw_full.json")
    perusahaan = load_records("perusahaan.json")

    check_unique("kasus", kasus, "id", errors)
    check_unique("objek", objek, "id", errors)
    check_unique("kab_kota", kab, "id", errors)
    check_unique("polres", polres, "polres", errors)
    check_unique("konsesi_gfw_full", gfw, "gfwid", errors)
    check_unique("perusahaan", perusahaan, "nama", errors)

    alias = load_records("perusahaan_alias.json")
    if alias:
        check_unique("perusahaan_alias", alias, "nama_mentah", errors)

    desa = load_records("desa_lock.json")
    if desa:
        check_unique("desa_lock", desa, "id", errors)

    izin = load_records("izin_2017.json")
    if izin:
        check_unique("izin_2017", izin, "record_id", errors)

    dossier = load_records("dossier.json")
    if dossier:
        check_unique("dossier", dossier, "dossier_id", errors)

    # Integration: bridge_entity_match — confirmed dilarang jika geo_ok=false
    bem_path = SITE / "silver" / "bridge_entity_match.json"
    if bem_path.exists():
        bem = json.loads(bem_path.read_text(encoding="utf-8"))
        bem_recs = bem.get("records") or []
        check_unique("bridge_entity_match", bem_recs, "match_id", errors)
        bad = [
            r
            for r in bem_recs
            if r.get("status") == "confirmed" and r.get("geo_ok") is False
        ]
        if bad:
            errors.append(
                f"bridge_entity_match: {len(bad)} baris status=confirmed dengan geo_ok=false"
            )
        meta_sumber = SITE / "silver" / "meta_sumber.json"
        if meta_sumber.exists():
            ms = json.loads(meta_sumber.read_text(encoding="utf-8"))
            n_ms = len(ms.get("records") or [])
            if n_ms < 11:
                errors.append(f"meta_sumber: expected ≥11 sumber blueprint, got {n_ms}")

    # Atlas uid from root CSV if present (optional hard check via konsesi kepmenhut names)
    kons_path = SITE / "konsesi.json"
    if kons_path.exists():
        kons = json.loads(kons_path.read_text(encoding="utf-8"))
        atlas = (kons.get("atlas_match") or {}).get("records") or []
        # match_id preferred; else atlas_nama+gfwid composite uniqueness if present
        if atlas and any(r.get("match_id") for r in atlas):
            check_unique("konsesi.atlas_match", atlas, "match_id", errors)
        atlas_full = (kons.get("atlas_full") or {}).get("records") or []
        if atlas_full:
            check_unique("konsesi.atlas_full", atlas_full, "atlas_id", errors)
            af_total = (kons.get("atlas_full") or {}).get("total")
            if af_total is not None and int(af_total) != len(atlas_full):
                errors.append(
                    f"konsesi.atlas_full.total={af_total} != len(records)={len(atlas_full)}"
                )
        sk36 = (
            json.loads((SITE / "penertiban.json").read_text(encoding="utf-8"))
            .get("normalized", {})
            .get("sk36_2025_110a", {})
            .get("records")
            or []
        )
        if sk36 and any(r.get("record_id") for r in sk36):
            check_unique("penertiban.sk36", sk36, "record_id", errors)
        elif sk36:
            # composite no|status_proses
            keys = []
            for r in sk36:
                no = r.get("no")
                st = r.get("status_proses") or "unknown"
                if is_null(no):
                    continue
                keys.append(f"{no}|{st}".lower())
            d = dup_groups(keys)
            if d:
                errors.append(f"PK duplikat penertiban.sk36 (no|status_proses): {len(d)} grup")

    # meta counts
    meta_path = SITE / "meta.json"
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        counts = meta.get("counts") or {}
        expected = {
            "kab_kota": len(kab),
            "polres": len(polres),
            "objek_agrinas": len(objek),
            "kasus_konflik": len(kasus),
            "gfw_bbox_full": len(gfw),
        }
        if alias:
            expected["perusahaan_alias"] = len(alias)
        if desa:
            expected["desa_lock"] = len(desa)
        if izin:
            expected["izin_2017"] = len(izin)
        if dossier:
            expected["dossier"] = len(dossier)
        if kons_path.exists():
            kons_meta = json.loads(kons_path.read_text(encoding="utf-8"))
            af = (kons_meta.get("atlas_full") or {}).get("records") or []
            if af:
                expected["atlas_full"] = len(af)
        for k, n in expected.items():
            if k in counts and int(counts[k]) != n:
                errors.append(f"meta.counts.{k}={counts[k]} != len(records)={n}")

        # Dual-grain: objek_titik must match layers.geojson point features
        layers_path = SITE / "layers.geojson"
        if layers_path.exists() and "objek_titik" in counts:
            layers = json.loads(layers_path.read_text(encoding="utf-8"))
            n_titik = sum(
                1
                for f in (layers.get("features") or [])
                if (f.get("properties") or {}).get("layer") == "objek_titik"
            )
            if int(counts["objek_titik"]) != n_titik:
                errors.append(
                    f"meta.counts.objek_titik={counts['objek_titik']} != "
                    f"layers objek_titik features={n_titik}"
                )
            if "hotspot_verifikasi" in counts:
                n_hs = sum(
                    1
                    for f in (layers.get("features") or [])
                    if (f.get("properties") or {}).get("layer") == "hotspot_verifikasi"
                )
                if int(counts["hotspot_verifikasi"]) != n_hs:
                    errors.append(
                        f"meta.counts.hotspot_verifikasi={counts['hotspot_verifikasi']} != "
                        f"layers hotspot_verifikasi={n_hs}"
                    )
        if "objek_mappable" in counts:
            n_map = sum(
                1
                for r in objek
                if str(r.get("mappable") or "").strip().lower() in {"ya", "true", "1", "yes"}
            )
            if int(counts["objek_mappable"]) != n_map:
                errors.append(
                    f"meta.counts.objek_mappable={counts['objek_mappable']} != "
                    f"objek mappable=ya count={n_map}"
                )

    # Kasus DQ thresholds (post Fase-1 friendly; warn before hard fail if still baseline)
    ops = [r for r in kasus if str(r.get("tipe_entri") or "").lower().startswith("kasus")]
    if ops:
        lp_null = sum(1 for r in ops if is_null(r.get("nomor_lp")) and not r.get("tanpa_lp"))
        rate = 100.0 * lp_null / len(ops)
        # Hard fail only if majority of operasional still missing LP AND no tanpa_lp flag
        if rate > 50:
            errors.append(
                f"kasus operasional tanpa nomor_lp (dan tanpa tanpa_lp): {rate:.1f}% "
                f"({lp_null}/{len(ops)}) — ambang max 50%"
            )
        elif rate > 30:
            warnings.append(f"kasus operasional nomor_lp null {rate:.1f}% (target ≤30%)")

    noise = [
        r
        for r in kasus
        if re.search(r"historikonflik\s*nihil|nihil\s*nihil", str(r.get("uraian") or ""), re.I)
        or str(r.get("status_verifikasi") or "").lower() == "noise"
    ]
    served_noise = [r for r in noise if str(r.get("status_verifikasi") or "").lower() != "noise"]
    # After cleanup, noise should be flagged or removed from serving
    if served_noise and len(served_noise) >= 5:
        warnings.append(f"{len(served_noise)} uraian placeholder nihil masih di serving tanpa flag noise")

    # objek kab_primary coverage (soft until Fase 3 complete)
    if objek and any("kab_primary" in r for r in objek):
        missing = sum(1 for r in objek if is_null(r.get("kab_primary")))
        pct = 100.0 * (len(objek) - missing) / len(objek)
        if pct < 90:
            warnings.append(f"objek.kab_primary fill {pct:.1f}% (target ≥90%)")

    print("=== validate_web_data ===")
    print(f"data: {SITE}")
    print(f"kasus={len(kasus)} objek={len(objek)} kab={len(kab)} polres={len(polres)} gfw={len(gfw)}")
    for w in warnings:
        print(f"WARN: {w}")
    if errors:
        for e in errors:
            print(f"FAIL: {e}", file=sys.stderr)
        print(f"RESULT: FAIL ({len(errors)} errors, {len(warnings)} warnings)")
        return 1
    print(f"RESULT: PASS ({len(warnings)} warnings)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
