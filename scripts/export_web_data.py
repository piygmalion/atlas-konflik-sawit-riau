#!/usr/bin/env python3
"""
Ekspor workbook/CSV workspace -> website/data/*.json|geojson
Jalankan berkala setelah update workbook:

  python website/scripts/export_web_data.py
"""

from __future__ import annotations

import csv
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path

try:
    import openpyxl
except ImportError as exc:
    raise SystemExit("openpyxl diperlukan: pip install openpyxl") from exc

try:
    from shapely.geometry import mapping, shape
    from shapely.ops import transform as shp_transform

    HAS_SHAPELY = True
except ImportError:
    HAS_SHAPELY = False

HERE = Path(__file__).resolve()
SITE = HERE.parents[1]
_candidates = [SITE.parent, SITE]
ROOT = next(
    (
        p
        for p in _candidates
        if (p / "Master_List_Objek_Agrinas_Satgas_Riau.xlsx").exists()
        or (p / "master_list_objek_agrinas_satgas_riau.csv").exists()
    ),
    SITE.parent,
)
OUT = SITE / "data"
OUT.mkdir(parents=True, exist_ok=True)

RIAU_BBOX = (100.0, -1.2, 103.6, 2.6)
RIAU_ADM2_RAW = [
    "bengkalis",
    "dumai",
    "kota dumai",
    "indragiri hilir",
    "indragiri hulu",
    "kampar",
    "kepulauan meranti",
    "kuantan singingi",
    "pelalawan",
    "pekanbaru",
    "kota pekanbaru",
    "rokan hilir",
    "rokan hulu",
    "siak",
]


def clean(v):
    if v is None:
        return None
    if isinstance(v, float) and v != v:
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
    headers = [str(h).strip() if h else f"col_{i}" for i, h in enumerate(rows[header_row - 1])]
    out = []
    for row in rows[header_row:]:
        if all(v is None or str(v).strip() == "" for v in row):
            continue
        out.append({headers[i]: clean(row[i] if i < len(row) else None) for i in range(len(headers))})
    return out


def write_json(name: str, payload, compact: bool = False):
    path = OUT / name
    if compact:
        path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    else:
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


def norm_name(s: str | None) -> str:
    if not s:
        return ""
    t = str(s).lower()
    t = t.replace("kabupaten", " ").replace("kab.", " ").replace("kota", " ")
    t = t.replace("kepulauan", "kep").replace("kep.", "kep")
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


RIAU_ADM2_NAMES = {norm_name(x) for x in RIAU_ADM2_RAW}


def slug(s: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (s or "unknown").lower()).strip("-")


def parse_bbox(text: str | None):
    if not text:
        return None
    t = str(text).lower().replace("–", "-").replace("—", "-")
    m = re.search(
        r"lon\s*(-?\d+(?:\.\d+)?)\s*-\s*(-?\d+(?:\.\d+)?)\s*;\s*lat\s*(-?\d+(?:\.\d+)?)\s*-\s*(-?\d+(?:\.\d+)?)",
        t,
    )
    if m:
        xs = sorted([float(m.group(1)), float(m.group(2))])
        ys = sorted([float(m.group(3)), float(m.group(4))])
        return xs[0], ys[0], xs[1], ys[1]
    nums = [to_float(x) for x in re.split(r"[,;\s]+", t) if to_float(x) is not None]
    if len(nums) >= 4:
        xs = sorted([nums[0], nums[2]])
        ys = sorted([nums[1], nums[3]])
        return xs[0], ys[0], xs[1], ys[1]
    return None


def geom_centroid_lonlat(geom: dict):
    if not geom:
        return None, None
    if HAS_SHAPELY:
        try:
            c = shape(geom).centroid
            return float(c.x), float(c.y)
        except Exception:
            pass
    coords = []

    def walk(node):
        if isinstance(node, (list, tuple)) and node and isinstance(node[0], (int, float)):
            coords.append((float(node[0]), float(node[1])))
        elif isinstance(node, (list, tuple)):
            for child in node:
                walk(child)

    walk(geom.get("coordinates"))
    if not coords:
        return None, None
    return sum(x for x, _ in coords) / len(coords), sum(y for _, y in coords) / len(coords)


def in_riau_bbox(lon: float | None, lat: float | None) -> bool:
    if lon is None or lat is None:
        return False
    minx, miny, maxx, maxy = RIAU_BBOX
    return minx - 0.3 <= lon <= maxx + 0.3 and miny - 0.3 <= lat <= maxy + 0.3


def simplify_geometry(geom: dict, tolerance: float = 0.004):
    if not geom:
        return geom
    if HAS_SHAPELY:
        try:
            g = shape(geom)
            if g.is_empty:
                return geom
            simple = g.simplify(tolerance, preserve_topology=True)
            if simple.is_empty:
                return geom
            return mapping(simple)
        except Exception:
            return geom
    return geom


def export_kab_kota():
    clusters = read_csv("cluster_kabkota_agrinas.csv")
    risiko = sheet_rows("TABEL_KONFLIK_AGRARIA_SAWIT_RIAU.xlsx", "Peta_Risiko_Sawit_Kab")
    risiko_map = {}
    for r in risiko:
        kab = r.get("Kabupaten_Kota")
        if kab is not None and str(kab).strip():
            risiko_map[str(kab).lower()] = r

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
        records.append(
            {
                "id": slug(kab),
                "kab_kota": kab,
                "shape_name": None,
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
                "n_kasus": 0,
                "risiko_register": {
                    "skor": to_float(risk.get("Skor_Risiko_Sawit")),
                    "level": risk.get("Level_Risiko"),
                    "kasus_ops": to_float(risk.get("Jumlah_Kasus_Ops_Sawit")),
                    "jumlah_lp": to_float(risk.get("Jumlah_LP")),
                    "driver_utama": risk.get("Driver_Utama"),
                    "rekomendasi": risk.get("Rekomendasi"),
                },
            }
        )
    return records


def match_kab_record(records: list[dict], name: str):
    n = norm_name(name)
    for rec in records:
        rn = norm_name(rec.get("kab_kota"))
        if not rn:
            continue
        if n == rn or n in rn or rn in n:
            return rec
    return None


def export_adm2_choropleth(kab_records: list[dict]):
    src = ROOT / "tmp" / "spatial" / "idn_adm2_simplified.geojson"
    features = []
    if not src.exists():
        write_json("adm2_riau.geojson", {"type": "FeatureCollection", "features": []}, compact=True)
        return []

    raw = json.loads(src.read_text(encoding="utf-8"))
    used = set()
    for f in raw.get("features", []):
        shape_name = (f.get("properties") or {}).get("shapeName")
        n = norm_name(shape_name)
        if n not in RIAU_ADM2_NAMES and not any(n == x or x in n or n in x for x in RIAU_ADM2_NAMES):
            continue
        lon, lat = geom_centroid_lonlat(f.get("geometry"))
        if not in_riau_bbox(lon, lat):
            continue
        rec = match_kab_record(kab_records, shape_name)
        if not rec:
            continue
        used.add(rec["id"])
        rec["shape_name"] = shape_name
        if lon and lat and (not rec.get("lon") or not rec.get("lat")):
            rec["lon"], rec["lat"] = lon, lat
        skor = rec.get("skor_komposit") or 0
        risk_skor = (rec.get("risiko_register") or {}).get("skor")
        features.append(
            {
                "type": "Feature",
                "geometry": f.get("geometry"),
                "properties": {
                    "id": rec["id"],
                    "nama": rec["kab_kota"],
                    "shape_name": shape_name,
                    "skor": skor,
                    "skor_risiko": risk_skor,
                    "level_risiko": (rec.get("risiko_register") or {}).get("level"),
                    "kategori": rec.get("kategori_peta"),
                    "polres": rec.get("polres_proksi"),
                    "n_kasus": rec.get("n_kasus") or 0,
                    "layer": "choropleth",
                },
            }
        )

    write_json("adm2_riau.geojson", {"type": "FeatureCollection", "features": features}, compact=True)
    print(f"    choropleth polygons: {len(features)} (matched kab ids: {len(used)})")
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
    records = [
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
        for r in rows
    ]
    write_json("objek_agrinas.json", {"total": len(records), "records": records})
    return records


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


def attach_kasus_counts(kab_records: list[dict], kasus: list[dict]):
    for rec in kab_records:
        n = 0
        for k in kasus:
            if match_wilayah_py(k.get("kab_kota"), rec.get("kab_kota")) or match_wilayah_py(
                k.get("polres"), rec.get("polres_proksi")
            ):
                n += 1
        rec["n_kasus"] = n


def match_wilayah_py(a, b) -> bool:
    if not a or not b:
        return False
    na, nb = norm_name(a), norm_name(b)
    aliases = {
        "rokan hulu": ["rohul"],
        "rokan hilir": ["rohil"],
        "indragiri hulu": ["inhu"],
        "indragiri hilir": ["inhil"],
        "kuantan singingi": ["kuansing"],
        "kepulauan meranti": ["meranti", "kep meranti"],
    }
    bag_a = {na}
    bag_b = {nb}
    for canon, als in aliases.items():
        if na == canon or any(x in na for x in als) or canon in na:
            bag_a |= {canon, *als}
        if nb == canon or any(x in nb for x in als) or canon in nb:
            bag_b |= {canon, *als}
    return any(x in y or y in x for x in bag_a for y in bag_b if x and y)


def export_spatial_layers(kab_records: list[dict]):
    features = []

    # Titik objek Agrinas
    path = ROOT / "proksi_peta_titik_agrinas.geojson"
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

    # Koridor dari bbox teks; fallback envelope dari anggota kab
    koridor_n = 0
    for k in read_csv("proksi_peta_koridor_agrinas.csv"):
        bbox = parse_bbox(k.get("bbox_approx"))
        if not bbox:
            members = re.split(r"[;,]", k.get("anggota_kab") or "")
            pts = []
            for m in members:
                rec = match_kab_record(kab_records, m.strip())
                if rec and rec.get("lon") is not None and rec.get("lat") is not None:
                    pts.append((rec["lon"], rec["lat"]))
            if len(pts) >= 1:
                xs = [p[0] for p in pts]
                ys = [p[1] for p in pts]
                pad = 0.25 if len(pts) == 1 else 0.15
                bbox = (min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad)
        if not bbox:
            continue
        minx, miny, maxx, maxy = bbox
        koridor_n += 1
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

    # Densitas kasus (proksi ke centroid kab)
    densitas_n = 0
    for rec in kab_records:
        if rec.get("lon") is None or rec.get("lat") is None:
            continue
        n = int(rec.get("n_kasus") or 0)
        if n <= 0:
            continue
        densitas_n += 1
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [rec["lon"], rec["lat"]]},
                "properties": {
                    "id": rec["id"],
                    "nama": rec["kab_kota"],
                    "n_kasus": n,
                    "weight": n,
                    "skor": rec.get("skor_komposit"),
                    "level_risiko": (rec.get("risiko_register") or {}).get("level"),
                    "layer": "densitas_kasus",
                },
            }
        )

    geo = {"type": "FeatureCollection", "features": features}
    write_json("layers.geojson", geo, compact=True)
    print(f"    layers: objek={sum(1 for f in features if f['properties']['layer']=='objek_titik')} "
          f"koridor={koridor_n} densitas={densitas_n}")
    return geo


def export_gfw_overlay():
    src = ROOT / "tmp" / "spatial" / "gfw_oilpalm_riau.geojson"
    features = []
    if src.exists():
        raw = json.loads(src.read_text(encoding="utf-8"))
        for f in raw.get("features", []):
            props = f.get("properties") or {}
            geom = simplify_geometry(f.get("geometry"), tolerance=0.005)
            features.append(
                {
                    "type": "Feature",
                    "geometry": geom,
                    "properties": {
                        "name": props.get("name") or props.get("company"),
                        "company": props.get("company"),
                        "group": props.get("group_comp"),
                        "area_ha": props.get("area_ha"),
                        "type": props.get("type"),
                        "hgu": props.get("po_hgu"),
                        "layer": "gfw_konsesi",
                    },
                }
            )
    write_json("gfw_konsesi.geojson", {"type": "FeatureCollection", "features": features}, compact=True)
    print(f"    gfw polygons: {len(features)} (shapely={HAS_SHAPELY})")
    return features


def bucket_jenis(jenis: str | None, kategori: str | None) -> str:
    t = f"{jenis or ''} {kategori or ''}".lower()
    if "situasional" in t or "agrinas" in t or "kso" in t:
        return "Situasional KSO/Agrinas"
    if "sengketa" in t or "lahan" in t or "okupasi" in t or "plasma" in t:
        return "Sengketa lahan"
    if "ekonomi" in t:
        return "Ekonomi"
    if "kekerasan" in t or "bentrok" in t or "demo" in t or "unjuk" in t:
        return "Aksi / kekerasan"
    return "Lainnya"


def years_from_kasus(tahun) -> list[str]:
    if tahun is None:
        return []
    found = re.findall(r"20\d{2}", str(tahun))
    return sorted(set(found))


def export_analytics(polres: list[dict], objek: list[dict], kasus: list[dict]):
    from collections import Counter

    # 1) Polres komponen for small-multiples / grouped bars
    polres_komponen = [
        {
            "polres": p.get("polres"),
            "label": str(p.get("polres") or "").replace("Polres ", ""),
            "peringkat": p.get("peringkat"),
            "skor": p.get("skor"),
            "kategori": p.get("kategori"),
            "komponen": p.get("komponen") or {},
        }
        for p in polres
    ]

    # 2) Agrinas layer flow (nodes + links)
    layer_order = [
        "A. Pengelola",
        "B. Eks pengelola",
        "C. Mitra KSO",
        "D. Eks lahan (via KSO)",
        "E. Gelombang 1 Satgas",
        "F. Objek kawasan",
    ]
    layer_counts = {k: 0 for k in layer_order}
    for o in objek:
        lap = o.get("lapisan") or "Lainnya"
        if lap not in layer_counts:
            layer_counts[lap] = 0
        layer_counts[lap] += 1

    nodes = [{"id": k, "label": k, "value": layer_counts.get(k, 0)} for k in layer_order if layer_counts.get(k, 0)]
    links = []

    def add_link(src, tgt, value, note=""):
        if value > 0:
            links.append({"source": src, "target": tgt, "value": int(value), "note": note})

    a = layer_counts.get("A. Pengelola", 0)
    b = layer_counts.get("B. Eks pengelola", 0)
    c = layer_counts.get("C. Mitra KSO", 0)
    d = layer_counts.get("D. Eks lahan (via KSO)", 0)
    e = layer_counts.get("E. Gelombang 1 Satgas", 0)
    f = layer_counts.get("F. Objek kawasan", 0)
    add_link("A. Pengelola", "C. Mitra KSO", min(a * 8, c) or a, "pengelola → mitra operasional")
    add_link("B. Eks pengelola", "C. Mitra KSO", min(b * 2, max(c - a, 0)) or min(b, c), "eks pengelola → mitra/KSO")
    add_link("C. Mitra KSO", "D. Eks lahan (via KSO)", min(c, d), "mitra → eks lahan via KSO")
    add_link("A. Pengelola", "E. Gelombang 1 Satgas", min(a, e) or (1 if a and e else 0), "jalur satgas")
    add_link("C. Mitra KSO", "E. Gelombang 1 Satgas", max(e - a, 0), "mitra dalam gelombang 1")
    add_link("D. Eks lahan (via KSO)", "F. Objek kawasan", min(d, f) or (1 if f else 0), "eks lahan ↔ objek kawasan")

    try:
        konsesi = json.loads((OUT / "konsesi.json").read_text(encoding="utf-8"))
    except Exception:
        konsesi = {"atlas_match": {"records": []}, "kepmenhut_36_2025": {"records": []}}

    atlas_rows = []
    for r in konsesi.get("atlas_match", {}).get("records", []):
        status = "cocok" if "cocok" in str(r.get("status") or "").lower() else (r.get("status") or "lain")
        konflik = (
            "ada di konflik"
            if str(r.get("ada_di_konflik_polda") or "").lower() in {"ya", "true", "1"}
            else "tidak di konflik"
        )
        atlas_rows.append(
            {
                "atlas_nama": r.get("atlas_nama"),
                "nama_lokal": r.get("nama_lokal"),
                "status_match": status,
                "konflik": konflik,
                "tahun": r.get("tahun"),
                "area_ha": r.get("area_ha"),
            }
        )

    atlas_flow_links = []
    match_c = Counter(r["status_match"] for r in atlas_rows)
    for st, n in match_c.items():
        atlas_flow_links.append({"source": "Nusantara Atlas", "target": st, "value": n})
    conf_c = Counter((r["status_match"], r["konflik"]) for r in atlas_rows)
    for (st, conf), n in conf_c.items():
        atlas_flow_links.append({"source": st, "target": conf, "value": n})

    kepmen_by_status = {}
    kepmen_records = []
    for r in konsesi.get("kepmenhut_36_2025", {}).get("records", []):
        st = r.get("status") or "Tidak diketahui"
        kepmen_by_status[st] = kepmen_by_status.get(st, 0) + 1
        kepmen_records.append(r)

    kepmen_buckets = {"Berproses": 0, "Ditolak": 0, "Campuran": 0, "Lainnya": 0}
    for st, n in kepmen_by_status.items():
        s = st.lower()
        if "campuran" in s:
            kepmen_buckets["Campuran"] += n
        elif "ditolak" in s and "berproses" not in s:
            kepmen_buckets["Ditolak"] += n
        elif "berproses" in s:
            kepmen_buckets["Berproses"] += n
        else:
            kepmen_buckets["Lainnya"] += n

    years = ["2024", "2025", "2026"]
    series_keys = ["Situasional KSO/Agrinas", "Sengketa lahan", "Ekonomi", "Aksi / kekerasan", "Lainnya"]
    timeline = {y: {k: 0 for k in series_keys} for y in years}
    timeline_polres = {}
    for k in kasus:
        ys = years_from_kasus(k.get("tahun")) or ["2026"]
        bucket = bucket_jenis(k.get("jenis"), k.get("kategori"))
        pol = str(k.get("polres") or "Lain/Polda").replace("Polres ", "")
        for y in ys:
            if y not in timeline:
                timeline[y] = {kk: 0 for kk in series_keys}
            timeline[y][bucket] = timeline[y].get(bucket, 0) + 1
            timeline_polres.setdefault(y, {})
            timeline_polres[y][pol] = timeline_polres[y].get(pol, 0) + 1

    years = sorted(timeline.keys())
    payload = {
        "polres_komponen": polres_komponen,
        "agrinas_flow": {"nodes": nodes, "links": links, "counts": layer_counts},
        "atlas_flow": {"links": atlas_flow_links, "records": atlas_rows},
        "timeline": {
            "years": years,
            "categories": series_keys,
            "by_jenis": timeline,
            "by_polres": timeline_polres,
        },
        "kepmenhut": {
            "buckets": [{"label": k, "value": v} for k, v in kepmen_buckets.items() if v],
            "by_status_raw": [
                {"label": k, "value": v} for k, v in sorted(kepmen_by_status.items(), key=lambda x: -x[1])
            ],
            "records": kepmen_records,
            "total": len(kepmen_records),
        },
    }
    write_json("analytics.json", payload)
    print(f"    analytics: polres={len(polres_komponen)} timeline_years={years} kepmen={len(kepmen_records)}")
    return payload


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
            "bbox_riau": list(RIAU_BBOX),
            "center": [101.45, 0.55],
            "zoom": 8,
            "counts": counts,
            "layers": [
                {"id": "choropleth", "label": "Choropleth kab/kota", "default": True},
                {"id": "koridor", "label": "Koridor spasial", "default": True},
                {"id": "densitas_kasus", "label": "Densitas kasus", "default": True},
                {"id": "objek_titik", "label": "Titik objek Agrinas", "default": True},
                {"id": "gfw_konsesi", "label": "Konsesi GFW (overlay)", "default": False},
            ],
            "views": ["peta", "analisis", "cerita", "data"],
            "sumber": [
                "TABEL_KONFLIK_AGRARIA_SAWIT_RIAU",
                "Master_List_Objek_Agrinas_Satgas_Riau",
                "Ranking_Potensi_Konflik_Per_Polres",
                "cluster_kabkota_agrinas",
                "idn_adm2_simplified (choropleth)",
                "gfw_oilpalm_riau (overlay)",
                "Tabulasi_Kepmenhut_36_2025",
                "Nusantara Atlas / GFW (cocokan)",
            ],
            "update_command": "python website/scripts/export_web_data.py",
            "catatan": (
                "Choropleth memakai batas ADM2; koridor dari bbox proksi; densitas kasus dipetakan ke centroid kab; "
                "overlay GFW disederhanakan. Bukan batas legal HGU/IUP."
            ),
        },
    )


def main():
    print(f"ROOT = {ROOT}")
    print(f"OUT  = {OUT}")
    kab_records = export_kab_kota()
    polres = export_polres()
    objek = export_objek()
    kasus = export_kasus()
    attach_kasus_counts(kab_records, kasus)
    write_json("kab_kota.json", {"updated": True, "records": kab_records})
    adm = export_adm2_choropleth(kab_records)
    # rewrite kab after shape_name/n_kasus filled
    write_json("kab_kota.json", {"updated": True, "records": kab_records})
    export_perusahaan()
    export_konsesi_atlas()
    geo = export_spatial_layers(kab_records)
    gfw = export_gfw_overlay()
    export_analytics(polres, objek, kasus)
    counts = {
        "kab_kota": len(kab_records),
        "polres": len(polres),
        "objek_agrinas": len(objek),
        "kasus_konflik": len(kasus),
        "choropleth": len(adm),
        "fitur_spasial": len(geo["features"]),
        "gfw_konsesi": len(gfw),
    }
    export_meta(counts)
    print("Selesai. Refresh website untuk melihat data terbaru.")


if __name__ == "__main__":
    main()
