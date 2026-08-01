#!/usr/bin/env python3
"""One-shot live Pages contract smoke check (read-only)."""
from __future__ import annotations

import json
import re
import sys
import urllib.request

BASE = "https://piygmalion.github.io/atlas-konflik-sawit-riau"


def get(path: str) -> bytes:
    with urllib.request.urlopen(BASE + path, timeout=90) as r:
        return r.read()


def main() -> int:
    errors: list[str] = []
    html = get("/").decode("utf-8")
    ver = re.search(r'atlas-asset-ver" content="([^"]+)"', html)
    scripts = re.findall(r'src="(js/[^"]+)"', html)
    print("asset_ver", ver.group(1) if ver else None)
    print("scripts", scripts)
    if not ver or ver.group(1) != "0dc3":
        errors.append(f"asset_ver expected 0dc3 got {ver.group(1) if ver else None}")
    if "js/app.js?v=0dc3" not in scripts:
        errors.append("app.js not on ?v=0dc3")
    if "enrichmentBlock" not in html:
        errors.append("missing enrichmentBlock in index")

    meta = json.loads(get("/data/meta.json"))
    c = meta.get("counts") or {}
    ids = [l.get("id") for l in (meta.get("layers") or [])]
    print("fitur_spasial", c.get("fitur_spasial"))
    print("hotspot", c.get("hotspot_verifikasi"), "in_layers", "hotspot_verifikasi" in ids)
    print("dossier", c.get("dossier"), "entity_matches", c.get("entity_matches"))
    if c.get("fitur_spasial") != 85:
        errors.append(f"fitur_spasial={c.get('fitur_spasial')}")
    if c.get("hotspot_verifikasi") != 15 or "hotspot_verifikasi" not in ids:
        errors.append("hotspot meta/layer mismatch")
    if c.get("dossier") != 436:
        errors.append(f"dossier count {c.get('dossier')}")
    if c.get("entity_matches") != 450:
        errors.append(f"entity_matches count {c.get('entity_matches')}")

    gfw = json.loads(get("/data/konsesi_gfw_full.json"))
    filled = sum(1 for r in gfw["records"] if r.get("nama_kanonik"))
    print("gfw_nama_kanonik", filled, "/", len(gfw["records"]))
    if filled != len(gfw["records"]):
        errors.append("gfw nama_kanonik incomplete on live")

    em = json.loads(get("/data/entity_matches.json"))
    dos = json.loads(get("/data/dossier.json"))
    print("live_entity", em.get("total"), "live_dossier", dos.get("total"))

    app = get("/js/app.js?v=0dc3").decode("utf-8")
    for name, needle in [
        ("findDossier", "function findDossier"),
        ("showDossier", "function showDossier"),
        ("hotspot_branch", 'layerId === "hotspot_verifikasi"'),
        ("ensureLazy", "function ensureLazyDatasets"),
        ("entity_boot", "entity_matches.json"),
        ("dossier_rank", "DATA.dossier"),
    ]:
        ok = needle in app
        print("app", name, "OK" if ok else "FAIL")
        if not ok:
            errors.append(f"app missing {name}")

    if errors:
        print("RESULT: FAIL")
        for e in errors:
            print(" -", e)
        return 1
    print("RESULT: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
