"""Enrich objek_titik with perusahaan links for map preview / detail."""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "website"
DATA = WEB / "data"
SRC = ROOT / "proksi_peta_titik_agrinas.geojson"

# Explicit hotspot → company (canonical display names in perusahaan.json when possible)
TITIK_PERUSAHAAN = {
    "T01": "PT TORGANDA",
    "T02": "PT TORGANDA",
    "T03": "PT PALMA SATU KEBUN PALMA 2",
    "T04": "PT SEBERIDA SUBUR",
    "T05": "PT AGRINAS PALMA NUSANTARA",
    "T06": "PT DUTA PALMA NUSANTARA",
    "T07": "PT DUTA PALMA NUSANTARA",
    "T08": None,  # TNTN — no single company
    "T09": "PT CILIANDRA PERKASA",
    "T10": "PT SINAR SAWIT SEJAHTERA",
    "T11": "PT SINAR SAWIT SEJAHTERA",
    "T12": "PT TORGANDA",
    "T13": "PT AGRINAS PALMA NUSANTARA",
    "T14": "PT DUTA PALMA NUSANTARA",
    "T15": "PT SAILAN ANTAU BATUAH",
    "T16": "KOPTAN KAMPAR JAYA BERSAMA",
    "T17": "KSO KAMPAR",
    "T18": "KSO KAMPAR",
    "T19": "PT NSM",
    "T20": "PT AGRINAS PALMA NUSANTARA",
}


def norm(s: str) -> str:
    s = (s or "").upper()
    s = re.sub(r"\b(PT\.?|PERUSAHAAN|PERSEROAN)\b", " ", s)
    s = re.sub(r"[^A-Z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def best_company_match(hint: str, companies: list[dict]) -> str | None:
    if not hint:
        return None
    nh = norm(hint)
    if not nh:
        return None
    # exact / contained match against nama or nama_kanonik
    scored = []
    for r in companies:
        nama = r.get("nama") or ""
        kan = r.get("nama_kanonik") or ""
        for cand in (nama, kan):
            nc = norm(cand)
            if not nc:
                continue
            if nh == nc:
                return nama
            if nh in nc or nc in nh:
                scored.append((min(len(nh), len(nc)) / max(len(nh), len(nc)), nama))
    if scored:
        scored.sort(reverse=True)
        return scored[0][1]
    return hint.strip()


def extract_hint_from_nama(nama: str) -> str | None:
    if not nama:
        return None
    # "Place — Company" pattern
    for sep in ("—", "–", "-"):
        if sep in nama:
            right = nama.split(sep, 1)[1].strip()
            right = re.split(r"[/;]", right)[0].strip()
            if right and not right.lower().startswith("centroid"):
                return right
    if re.search(r"\bPT\b", nama, re.I):
        return nama
    return None


def resolve_perusahaan(props: dict, companies: list[dict], objek_by_id: dict) -> str | None:
    tid = str(props.get("id") or "")
    if tid in TITIK_PERUSAHAAN:
        hint = TITIK_PERUSAHAAN[tid]
        return best_company_match(hint, companies) if hint else None

    # Expanded OBJ-* already named after company / unit
    oid = props.get("objek_id") or tid
    objek = objek_by_id.get(str(oid))
    if objek:
        # Prefer explicit company-like nama
        nama = objek.get("nama") or ""
        if re.search(r"\bPT\b", nama, re.I) or objek.get("tipe_badan") in {"PT", "Perseroan"}:
            return best_company_match(nama, companies)
        if objek.get("klaster"):
            m = best_company_match(objek["klaster"], companies)
            if m:
                return m

    if props.get("perusahaan"):
        return best_company_match(str(props["perusahaan"]), companies)

    hint = extract_hint_from_nama(str(props.get("nama") or ""))
    if hint:
        return best_company_match(hint, companies)

    # OBJ auto points: nama is often the company
    nama = str(props.get("nama") or "")
    if re.search(r"\bPT\b", nama, re.I):
        return best_company_match(nama, companies)
    return None


def enrich_feature_props(props: dict, companies: list[dict], objek_by_id: dict) -> dict:
    out = dict(props)
    company = resolve_perusahaan(out, companies, objek_by_id)
    if company:
        out["perusahaan"] = company
    elif "perusahaan" in out and not out["perusahaan"]:
        out.pop("perusahaan", None)
    return out


def main():
    companies = load_json(DATA / "perusahaan.json").get("records") or []
    objek = load_json(DATA / "objek_agrinas.json").get("records") or []
    objek_by_id = {str(r.get("id")): r for r in objek}

    src = load_json(SRC)
    n = 0
    for f in src.get("features") or []:
        props = f.get("properties") or {}
        if str(props.get("prioritas") or "").upper() == "REF":
            continue
        enriched = enrich_feature_props(props, companies, objek_by_id)
        if enriched.get("perusahaan") and enriched.get("perusahaan") != props.get("perusahaan"):
            n += 1
        f["properties"] = enriched
    write_json(SRC, src)
    print(f"source geojson: set/updated perusahaan on ~{n} plottable features")

    layers_path = DATA / "layers.geojson"
    layers = load_json(layers_path)
    n2 = 0
    for f in layers.get("features") or []:
        props = f.get("properties") or {}
        if props.get("layer") != "objek_titik":
            continue
        enriched = enrich_feature_props(props, companies, objek_by_id)
        if enriched.get("perusahaan"):
            n2 += 1
        f["properties"] = enriched
    schema = layers.get("schema_by_layer") or {}
    cols = schema.get("objek_titik") or ["id", "nama", "kab_kota", "prioritas", "polres_proksi", "layer"]
    if "perusahaan" not in cols:
        # keep prioritas, add perusahaan after nama
        if "nama" in cols:
            i = cols.index("nama") + 1
            cols = cols[:i] + ["perusahaan"] + [c for c in cols[i:] if c != "perusahaan"]
        else:
            cols = cols + ["perusahaan"]
        schema["objek_titik"] = cols
        layers["schema_by_layer"] = schema
    write_json(layers_path, layers)
    print(f"layers.geojson objek_titik with perusahaan: {n2}")

    # also copy into website copy of source if any — N/A
    # sample T02
    for f in layers["features"]:
        p = f.get("properties") or {}
        if p.get("id") == "T02":
            print("T02 ->", p.get("perusahaan"), "| prioritas", p.get("prioritas"))
            break


if __name__ == "__main__":
    main()
