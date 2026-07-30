"""Manifest dataset serving yang di-sync ke Supabase."""

from __future__ import annotations

# dataset key → nama file di website/data/
SERVING_MANIFEST: dict[str, str] = {
    "meta": "meta.json",
    "kab_kota": "kab_kota.json",
    "polres": "polres.json",
    "objek_agrinas": "objek_agrinas.json",
    "kasus": "kasus.json",
    "perusahaan": "perusahaan.json",
    "perusahaan_alias": "perusahaan_alias.json",
    "konsesi": "konsesi.json",
    "konsesi_gfw_full": "konsesi_gfw_full.json",
    "analytics": "analytics.json",
    "penertiban": "penertiban.json",
    "dq_report": "dq_report.json",
    "desa_lock": "desa_lock.json",
    "izin_2017": "izin_2017.json",
    "rantai_agrinas": "rantai_agrinas.json",
    "dossier": "dossier.json",
    "layers": "layers.geojson",
    "adm2": "adm2_riau.geojson",
    "gfw_konsesi": "gfw_konsesi.topojson",
}

# Path lokal relatif website/ → dataset key (untuk frontend remote map)
PATH_TO_DATASET: dict[str, str] = {
    f"data/{filename}": key for key, filename in SERVING_MANIFEST.items()
}
