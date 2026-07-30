#!/usr/bin/env python3
"""Materialize gold serving blobs dari silver staging lokal (Fase 3).

Satu arah: bronze → (export) silver staging → materialize → gold.
Jangan edit manual file gold tanpa lewat materialize/export.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
SITE = HERE.parents[1]
DATA = SITE / "data"
SILVER = DATA / "silver"


def _copy_if(src_name: str, dest_name: str | None = None) -> bool:
    src = SILVER / src_name
    if not src.exists():
        return False
    dest = DATA / (dest_name or src_name)
    shutil.copy2(src, dest)
    print(f"  materialize {dest.name} <- silver/{src.name}")
    return True


def materialize_from_silver() -> int:
    if not SILVER.is_dir():
        print("Silver staging missing — jalankan export_web_data.py dulu", file=sys.stderr)
        return 2

    n = 0
    # Direct blob mirrors
    for name in ("desa_lock.json", "izin_2017.json", "rantai_agrinas.json"):
        if _copy_if(name):
            n += 1
    if _copy_if("dim_perusahaan_alias.json", "perusahaan_alias.json"):
        n += 1

    # Merge atlas_full into konsesi.json without touching atlas_match grain
    atlas_full_path = SILVER / "atlas_full.json"
    kons_path = DATA / "konsesi.json"
    if atlas_full_path.exists() and kons_path.exists():
        kons = json.loads(kons_path.read_text(encoding="utf-8"))
        kons["atlas_full"] = json.loads(atlas_full_path.read_text(encoding="utf-8"))
        kons_path.write_text(json.dumps(kons, ensure_ascii=False, indent=2), encoding="utf-8")
        print("  materialize konsesi.json::atlas_full dari silver")
        n += 1

    # Kab fields from silver dim
    kab_silver = SILVER / "dim_kab_kota.json"
    kab_path = DATA / "kab_kota.json"
    if kab_silver.exists() and kab_path.exists():
        silver_recs = {
            r.get("id"): r
            for r in (json.loads(kab_silver.read_text(encoding="utf-8")).get("records") or [])
            if r.get("id")
        }
        kab = json.loads(kab_path.read_text(encoding="utf-8"))
        for r in kab.get("records") or []:
            s = silver_recs.get(r.get("id"))
            if not s:
                continue
            for field in (
                "verifikasi_status",
                "kepercayaan_sebaran",
                "rank_gfw",
                "rank_sebaran",
                "n_izin_2017",
            ):
                if field in s:
                    r[field] = s.get(field)
        kab_path.write_text(json.dumps(kab, ensure_ascii=False, indent=2), encoding="utf-8")
        print("  materialize kab_kota additive fields dari silver")
        n += 1

    # Matching Engine dossier (silver → gold)
    dossier_silver = SILVER / "mart_dossier_kasus.json"
    if dossier_silver.exists():
        shutil.copy2(dossier_silver, DATA / "dossier.json")
        print("  materialize dossier.json <- silver/mart_dossier_kasus.json")
        n += 1

    print(f"materialize done ({n} artifacts)")
    # Contract gate
    sys.path.insert(0, str(HERE.parent))
    from validate_web_data import main as validate_main

    return validate_main()


def main() -> int:
    print(f"DATA={DATA}")
    print(f"SILVER={SILVER}")
    # Preferred path after full rebuild: re-run export (writes silver+gold atomically)
    # then re-apply silver→gold merge for safety.
    export = HERE.parent / "export_web_data.py"
    if export.exists():
        import runpy

        print("=== rebuild via export_web_data (bronze->silver staging->gold) ===")
        try:
            runpy.run_path(str(export), run_name="__main__")
        except SystemExit as exc:
            code = exc.code if isinstance(exc.code, int) else 1
            if code != 0:
                return code

    # Matching & Overlay Engine (additive integration layer)
    build_matches = HERE.parent / "build_entity_matches.py"
    if build_matches.exists():
        import runpy

        print("=== build_entity_matches (integration) ===")
        try:
            runpy.run_path(str(build_matches), run_name="__main__")
        except SystemExit as exc:
            code = exc.code if isinstance(exc.code, int) else 1
            if code != 0:
                return code

    return materialize_from_silver()


if __name__ == "__main__":
    raise SystemExit(main())
