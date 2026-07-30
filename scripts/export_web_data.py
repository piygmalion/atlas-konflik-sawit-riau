#!/usr/bin/env python3
"""
Ekspor workbook/CSV workspace -> website/data/*.json|geojson
Jalankan berkala setelah update workbook:

  python website/scripts/export_web_data.py

Skema keluaran dirancang stabil agar frontend tidak perlu diubah tiap update.
"""

from __future__ import annotations

import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path

try:
    import openpyxl
except ImportError as exc:
    raise SystemExit("openpyxl diperlukan: pip install openpyxl") from exc

HERE = Path(__file__).resolve()
SITE = HERE.parents[1]  # website/ or repo root
# Prefer parent workspace if workbooks live there (local monorepo layout)
_candidates = [SITE.parent, SITE]
ROOT = next(
    (p for p in _candidates if (p / "Master_List_Objek_Agrinas_Satgas_Riau.xlsx").exists() or (p / "master_list_objek_agrinas_satgas_riau.csv").exists()),
    SITE.parent,
)
OUT = SITE / "data"
OUT.mkdir(parents=True, exist_ok=True)


def clean(v):
    if v is None:
        return None
    if isinstance(v, float) and v != v:  # NaN
        return None
    if isinstance(v, datetime):
        return v.date().isoformat()
    if isinstance(v, (int, float, bool)):
        return v
    s = str(v).strip()
    return s if s and s.lower() not in {"none", "null", "-"} else None


def read_csv(name: str) -> list[dict]:
    path = ROOT / name
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as f:
        return [{k: clean(v) for k, v in row.items()} for row in csv.DictReader(f)]


def sheet_rows(wb_name: str, sheet: str, header_row: int = 1) -> list[dict]:
    path = ROOT / wb_name
    if not path.exists():
        return []
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    if sheet not in wb.sheetnames:
        wb.close()
        return []
    ws = wb[sheet]
    rows = list(ws.iter_rows(values_only=True))
    wb.close()
    if len(rows) < header_row:
        return []
    headers = []
    for i, h in enumerate(rows[header_row - 1]):
        headers.append(str(h).strip() if h else f"col_{i}")
    out = []
    for row in rows[header_row:]:
        if all(v is None or str(v).strip() == "" for v in row):
            continue
        item = {headers[i]: clean(row[i] if i < len(row) else None) for i in range(len(headers))}
        out.append(item)
    return out


def write_json(name: str, payload):
    path = OUT / name
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  wrote {path.name} ({path.stat().st_size:,} bytes)")


def to_float(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).replace(",", ".").strip()
    m = re.search(r"-?\d+(?:\.\d+)?", s)
    return float(m.group(0)) if m else None


def export_kab_kota():
    clusters = read_csv("cluster_kabkota_agrinas.csv")
    risiko = sheet_rows("TABEL_KONFLIK_AGRARIA_SAWIT_RIAU.xlsx", "Peta_Risiko_Sawit_Kab")
    risiko_map = {}
    for r in risiko:
        kab = r.get("Kabupaten_Kota")
        if kab is not None and str(kab).strip():
            risiko_map[str(kab).lower()] = r

    features = []
    records = []
    for c in clusters:
        kab = c.get("kab_kota")
        lon = to_float(c.get("lon_centroid_proksi"))
        lat = to_float(c.get("lat_centroid_proksi"))
        risk = {}
        for key, val in risiko_map.items():
            if kab and (kab.lower() in key or key in kab.lower()):
                risk = val
                break
        rec = {
            "id": re.sub(r"[^a-z0-9]+", "-", (kab or "unknown").lower()).strip("-"),
            "kab_kota": kab,
            "cluster": c.get("cluster"),
            "skor_komposit": to_float(c.get("skor_komposit")),
            "kategori_peta": c.get("kategori_peta"),
            "sinyal_agrinas": to_float(c.get("sinyal_agrinas_0_5")),
            "sebaran": to_float(c.get("sebaran_0_5")),
            "kasus_konflik_agrinas": to_float(c.get("kasus_konflik_agrinas")),
            "luas_disebut_terbuka": c.get("luas_disebut_terbuka"),
            "klhk_korp_kh_2022_ha": to_float(c.get("klhk_korp_kh_2022_ha")),
            "objek_sinyal_utama": c.get("objek_sinyal_utama"),
            "hotspot_kecamatan": c.get("hotspot_kecamatan_perkiraan"),
            "polres_proksi": c.get("polres_proksi"),
            "ketidakpastian": c.get("ketidakpastian"),
            "lon": lon,
            "lat": lat,
            "catatan_peta": c.get("catatan_peta"),
            "risiko_register": {
                "skor": to_float(risk.get("Skor_Risiko_Sawit")),
                "level": risk.get("Level_Risiko"),
                "kasus_ops": to_float(risk.get("Jumlah_Kasus_Ops_Sawit")),
                "jumlah_lp": to_float(risk.get("Jumlah_LP")),
                "driver_utama": risk.get("Driver_Utama"),
                "rekomendasi": risk.get("Rekomendasi"),
            },
        }
        records.append(rec)
        if lon is not None and lat is not None:
            features.append(
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [lon, lat]},
                    "properties": {
                        "id": rec["id"],
                        "nama": kab,
                        "tipe": "kab_kota",
                        "kategori": rec["kategori_peta"],
                        "skor": rec["skor_komposit"],
                        "polres": rec["polres_proksi"],
                        "level_risiko": rec["risiko_register"]["level"],
                    },
                }
            )
    write_json("kab_kota.json", {"updated": True, "records": records})
    return features


def export_polres():
    rows = read_csv("ranking_potensi_konflik_per_polres.csv")
    records = []
    for r in rows:
        records.append(
            {
                "peringkat": int(to_float(r.get("peringkat")) or 0),
                "polres": r.get("polres"),
                "skor": to_float(r.get("skor")),
                "kategori": r.get("kategori"),
                "skor_osint": to_float(r.get("skor_osint_saja")),
                "skor_register": to_float(r.get("skor_register_saja")),
                "n_entri": to_float(r.get("n_entri_terpetakan")),
                "n_aksi_massa": to_float(r.get("n_aksi_massa")),
                "n_kekerasan": to_float(r.get("n_kekerasan")),
                "n_agrinas": to_float(r.get("n_agrinas_satgas_kso")),
                "n_recent": to_float(r.get("n_recent_2024plus")),
                "n_tabel_konflik": to_float(r.get("n_tabel_konflik_agraria")),
                "komponen": {
                    "liputan": to_float(r.get("komponen_liputan")),
                    "aksi": to_float(r.get("komponen_aksi")),
                    "objek": to_float(r.get("komponen_objek")),
                    "status": to_float(r.get("komponen_status")),
                    "adat": to_float(r.get("komponen_adat")),
                },
                "alasan": r.get("alasan_singkat"),
                "tahun": r.get("tahun_tercover"),
            }
        )
    write_json(
        "polres.json",
        {
            "model": {
                "kategori": {"PANTAU": "0-39", "WASPADA": "40-69", "PRIORITAS": "70-100"},
                "catatan": "Skor early-warning OSINT terbuka, bukan vonis operasional.",
            },
            "records": records,
        },
    )
    return records


def export_objek():
    rows = read_csv("master_list_objek_agrinas_satgas_riau.csv")
    records = []
    for r in rows:
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
                "luas_disebut": r.get("luas_disebut"),
                "status_kredibilitas": r.get("status_kredibilitas"),
                "prioritas": r.get("prioritas"),
                "kaitan_agrinas": r.get("kaitan_agrinas"),
                "cro_regional": r.get("cro_regional"),
                "mitra_pair": r.get("mitra_pair"),
                "ada_di_bps": r.get("ada_di_bps"),
                "ada_di_konflik_polda": r.get("ada_di_konflik_polda"),
                "sumber": r.get("sumber"),
            }
        )
    write_json("objek_agrinas.json", {"total": len(records), "records": records})
    return records


def export_titik_geojson(kab_features):
    path = ROOT / "proksi_peta_titik_agrinas.geojson"
    features = []
    if path.exists():
        raw = json.loads(path.read_text(encoding="utf-8"))
        for f in raw.get("features", []):
            props = {k: clean(v) for k, v in (f.get("properties") or {}).items()}
            features.append(
                {
                    "type": "Feature",
                    "geometry": f.get("geometry"),
                    "properties": {
                        "id": props.get("id"),
                        "nama": props.get("nama"),
                        "kab_kota": props.get("kab_kota"),
                        "tipe": props.get("tipe") or "objek",
                        "prioritas": props.get("prioritas"),
                        "catatan": props.get("catatan"),
                        "polres_proksi": props.get("polres_proksi"),
                        "sumber": props.get("sumber"),
                        "layer": "objek_titik",
                    },
                }
            )
    for f in kab_features:
        f2 = dict(f)
        f2["properties"] = dict(f["properties"])
        f2["properties"]["layer"] = "kab_centroid"
        features.append(f2)

    # koridor as bbox polygons if available
    for k in read_csv("proksi_peta_koridor_agrinas.csv"):
        bbox = k.get("bbox_approx")
        if not bbox:
            continue
        nums = [to_float(x) for x in re.split(r"[,;\s]+", bbox) if to_float(x) is not None]
        if len(nums) >= 4:
            minx, miny, maxx, maxy = nums[:4]
            features.append(
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [
                            [
                                [minx, miny],
                                [maxx, miny],
                                [maxx, maxy],
                                [minx, maxy],
                                [minx, miny],
                            ]
                        ],
                    },
                    "properties": {
                        "id": k.get("id"),
                        "nama": k.get("nama"),
                        "tipe": "koridor",
                        "anggota_kab": k.get("anggota_kab"),
                        "polres_proksi": k.get("polres_proksi"),
                        "karakter": k.get("karakter"),
                        "prioritas": k.get("prioritas_peta"),
                        "layer": "koridor",
                    },
                }
            )

    geo = {"type": "FeatureCollection", "features": features}
    write_json("layers.geojson", geo)
    return geo


def export_kasus():
    rows = sheet_rows("TABEL_KONFLIK_AGRARIA_SAWIT_RIAU.xlsx", "Master_Kasus_Sawit")
    records = []
    for r in rows:
        if not r.get("ID") and not r.get("Uraian_Singkat"):
            continue
        records.append(
            {
                "id": r.get("ID"),
                "sumber_dokumen": r.get("Sumber_Dokumen"),
                "polres": r.get("Wilayah_Polres"),
                "kab_kota": r.get("Kabupaten_Kota"),
                "tahun": r.get("Tahun_Referensi"),
                "nomor_lp": r.get("Nomor_LP"),
                "jenis": r.get("Jenis_Konflik"),
                "kategori": r.get("Kategori_Konflik"),
                "pihak": r.get("Pihak_Berkonflik"),
                "lokasi": r.get("Lokasi"),
                "uraian": r.get("Uraian_Singkat"),
                "upaya": r.get("Upaya_Dilakukan"),
                "status": r.get("Status_Keterangan"),
                "hambatan": r.get("Hambatan"),
                "perusahaan": r.get("Perusahaan_Terkait"),
                "tema": r.get("Kata_Kunci_Tema"),
                "tipe_entri": r.get("Tipe_Entri"),
                "indikator_sawit": r.get("Indikator_Sawit"),
            }
        )
    write_json("kasus.json", {"total": len(records), "records": records})
    return records


def export_perusahaan():
    rows = read_csv("daftar_perusahaan_sawit_riau_gabungan.csv")
    records = [
        {
            "no": r.get("no"),
            "nama": r.get("nama_perusahaan"),
            "sumber": r.get("sumber"),
            "ada_di_bps": r.get("ada_di_bps"),
            "ada_di_konflik_polda": r.get("ada_di_konflik_polda"),
            "status_nama": r.get("status_nama"),
            "catatan": r.get("catatan"),
        }
        for r in rows
        if r.get("nama_perusahaan")
    ]
    write_json("perusahaan.json", {"total": len(records), "records": records})


def export_konsesi_atlas():
    gfw = read_csv("tabulasi_konsesi_sawit_gfw_match_bps_riau.csv")
    atlas = read_csv("cocokan_atlas_gabungan_gfw.csv")
    kepmen = read_csv("tabulasi_konsesi_sawit_kepmenhut_36_2025_riau_rapi.csv")
    write_json(
        "konsesi.json",
        {
            "gfw_match_bps": {
                "total": len(gfw),
                "records": [
                    {
                        "nama_bps": r.get("nama_bps_match"),
                        "company": r.get("company"),
                        "name": r.get("name"),
                        "group": r.get("group_comp"),
                        "type": r.get("type"),
                        "legal": r.get("po_legalst"),
                        "hgu": r.get("po_hgu"),
                        "area_ha": to_float(r.get("area_ha")),
                        "gfwid": r.get("gfwid"),
                    }
                    for r in gfw
                ],
            },
            "atlas_match": {
                "total": len(atlas),
                "records": [
                    {
                        "atlas_nama": r.get("atlas_nama"),
                        "tahun": r.get("atlas_tahun"),
                        "tipe": r.get("atlas_tipe"),
                        "status": r.get("status_kecocokan"),
                        "nama_lokal": r.get("nama_lokal"),
                        "area_ha": to_float(r.get("area_ha")),
                        "ada_di_bps": r.get("ada_di_bps"),
                        "ada_di_konflik_polda": r.get("ada_di_konflik_polda"),
                    }
                    for r in atlas
                ],
            },
            "kepmenhut_36_2025": {
                "total": len(kepmen),
                "records": [
                    {
                        "nama": r.get("Nama subjek hukum"),
                        "luas_permohonan_ha": to_float(r.get("Luas permohonan (ha)")),
                        "luas_berproses_ha": to_float(r.get("Luas berproses (ha)")),
                        "luas_ditolak_ha": to_float(r.get("Luas ditolak (ha)")),
                        "status": r.get("Status permohonan"),
                        "kelengkapan": r.get("Kelengkapan data"),
                        "implikasi": r.get("Implikasi"),
                    }
                    for r in kepmen
                ],
            },
        },
    )


def export_meta(counts: dict):
    write_json(
        "meta.json",
        {
            "brand": "Atlas Konflik Sawit Riau",
            "subtitle": "Pemetaan spasial konflik, objek Agrinas–Satgas, dan celahan perizinan",
            "updated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
            "bbox_riau": [100.0, -1.2, 103.6, 2.6],
            "center": [101.45, 0.55],
            "zoom": 8,
            "counts": counts,
            "layers": [
                {"id": "kab_centroid", "label": "Kabupaten / Kota", "default": True},
                {"id": "objek_titik", "label": "Titik objek Agrinas", "default": True},
                {"id": "koridor", "label": "Koridor spasial", "default": True},
            ],
            "sumber": [
                "Inventarisasi_Sawit_Riau_v1.1",
                "TABEL_KONFLIK_AGRARIA_SAWIT_RIAU",
                "Master_List_Objek_Agrinas_Satgas_Riau",
                "Ranking_Potensi_Konflik_Per_Polres",
                "cluster_kabkota_proksi_peta_agrinas",
                "Tabulasi_Kepmenhut_36_2025",
                "Nusantara Atlas / GFW (cocokan)",
            ],
            "update_command": "python website/scripts/export_web_data.py",
            "catatan": (
                "Koordinat kab/kota dan titik objek bersifat proksi analisis OSINT, "
                "bukan batas legal HGU/IUP. Overlay ke Nusantara Atlas untuk bukti spasial satelit."
            ),
        },
    )


def main():
    print(f"ROOT = {ROOT}")
    print(f"OUT  = {OUT}")
    kab_features = export_kab_kota()
    polres = export_polres()
    objek = export_objek()
    kasus = export_kasus()
    export_perusahaan()
    export_konsesi_atlas()
    geo = export_titik_geojson(kab_features)
    counts = {
        "kab_kota": len(kab_features),
        "polres": len(polres),
        "objek_agrinas": len(objek),
        "kasus_konflik": len(kasus),
        "fitur_spasial": len(geo["features"]),
    }
    export_meta(counts)
    print("Selesai. Refresh website untuk melihat data terbaru.")


if __name__ == "__main__":
    main()
