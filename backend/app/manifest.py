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
    "konsesi": "konsesi.json",
    "konsesi_gfw_full": "konsesi_gfw_full.json",
    "analytics": "analytics.json",
    "penertiban": "penertiban.json",
    "dq_report": "dq_report.json",
    "layers": "layers.geojson",
    "adm2": "adm2_riau.geojson",
    "gfw_konsesi": "gfw_konsesi.topojson",
}

# Path lokal relatif website/ → dataset key (untuk frontend remote map)
PATH_TO_DATASET: dict[str, str] = {
    f"data/{filename}": key for key, filename in SERVING_MANIFEST.items()
}
