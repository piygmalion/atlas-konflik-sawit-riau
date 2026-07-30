#!/usr/bin/env python3
"""Shared company-name normalization for GFW / Atlas / BPS / konflik matching."""

from __future__ import annotations

import csv
import re
from pathlib import Path

# Common legal / noise tokens stripped for matching
_STRIP_TOKENS = re.compile(
    r"\b(PT|CV|TBK|PERSERO|PERUSAHAAN|PERKEBUNAN|KEBUN|HOLDING|GROUP|GRUP)\b",
    re.I,
)

# Explicit alias expansions applied before token strip
_ALIAS_EXPAND = [
    (re.compile(r"\bPTP\s*N?\s*V\b", re.I), "PERKEBUNAN NUSANTARA V"),
    (re.compile(r"\bPTPN\s*V\b", re.I), "PERKEBUNAN NUSANTARA V"),
    (re.compile(r"\bPTPN\s*5\b", re.I), "PERKEBUNAN NUSANTARA V"),
    (re.compile(r"\bPERKEBUNAN\s+V\b", re.I), "PERKEBUNAN NUSANTARA V"),
    (re.compile(r"\bKTBM\b", re.I), "KARYA TAMA BAKTI MULYA"),
]


def expand_aliases(s: str) -> str:
    out = s
    for pat, repl in _ALIAS_EXPAND:
        out = pat.sub(repl, out)
    return out


def norm_company(s: str | None) -> str:
    """Aggressive alphanumeric key for overlap checks."""
    if s is None:
        return ""
    t = expand_aliases(str(s))
    t = t.upper()
    t = t.replace("PT.", "PT ").replace("CV.", "CV ")
    t = _STRIP_TOKENS.sub(" ", t)
    t = re.sub(r"[^A-Z0-9]+", "", t)
    return t


def norm_company_display(s: str | None) -> str:
    """Readable canonical form (spaces kept)."""
    if s is None:
        return ""
    t = expand_aliases(str(s).strip())
    t = t.upper()
    t = t.replace("PT.", "PT ").replace("CV.", "CV ")
    t = re.sub(r"[^A-Z0-9\s&]", " ", t)
    t = _STRIP_TOKENS.sub(" ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def load_alias_table(path: Path) -> dict[str, str]:
    """Map norm(nama_mentah) -> nama_kanonik."""
    if not path.exists():
        return {}
    out: dict[str, str] = {}
    with path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            raw = row.get("nama_mentah") or ""
            canon = row.get("nama_kanonik") or raw
            key = norm_company(raw)
            if key:
                out[key] = canon.strip()
            ckey = norm_company(canon)
            if ckey:
                out.setdefault(ckey, canon.strip())
    return out


def resolve_canonical(name: str | None, alias_map: dict[str, str] | None = None) -> str:
    if not name:
        return ""
    key = norm_company(name)
    if alias_map and key in alias_map:
        return alias_map[key]
    return norm_company_display(name) or str(name).strip()
