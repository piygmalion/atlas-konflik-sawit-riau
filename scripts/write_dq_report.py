#!/usr/bin/env python3
"""Write website/data/dq_report.json from audit overview + validate summary."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve()
SITE = HERE.parents[1]
DATA = SITE / "data"
ROOT = SITE.parent if (SITE.parent / "master_list_objek_agrinas_satgas_riau.csv").exists() else SITE


def scrub_local_paths(text: str) -> str:
    """Remove machine-absolute paths from committed artifacts."""
    if not text:
        return text
    # Normalize separators then replace known roots with repo-relative labels
    out = text.replace("\\", "/")
    site_s = str(SITE).replace("\\", "/")
    root_s = str(ROOT).replace("\\", "/")
    data_s = str(DATA).replace("\\", "/")
    # Longest first
    for abs_path, label in (
        (data_s, "website/data"),
        (site_s, "website"),
        (root_s, "workspace"),
    ):
        if abs_path and abs_path in out:
            out = out.replace(abs_path, label)
    # Generic Windows user home leak
    import re

    out = re.sub(r"[A-Za-z]:/Users/[^/\s]+/", "~/ ", out)
    out = re.sub(r"/home/[^/\s]+/", "~/ ", out)
    return out


def main():
    # Run audit
    audit_script = HERE.parent / "audit_data_quality.py"
    subprocess.run([sys.executable, str(audit_script)], check=False)
    audit_path = ROOT / "tmp" / "data_quality_audit.json"
    audit = {}
    if audit_path.exists():
        audit = json.loads(audit_path.read_text(encoding="utf-8"))

    baseline_path = ROOT / "tmp" / "dq_baseline_2026-07-30.json"
    baseline = {}
    if baseline_path.exists():
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))

    # Validate
    val = subprocess.run(
        [sys.executable, str(HERE.parent / "validate_web_data.py")],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    overview = audit.get("overview") or []
    grades = {}
    for o in overview:
        grades[o.get("grade", "?")] = grades.get(o.get("grade", "?"), 0) + 1

    report = {
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "validate_exit_code": val.returncode,
        "validate_pass": val.returncode == 0,
        "validate_stdout": scrub_local_paths((val.stdout or "")[-2000:]),
        "validate_stderr": scrub_local_paths((val.stderr or "")[-2000:]),
        "grade_counts": grades,
        "overview": overview,
        "cross": audit.get("cross") or {},
        "baseline_cross": baseline.get("cross") or {},
        "notes": {
            "source_null_fields": [
                "ISPO / nomor_izin Atlas",
                "HGU attributes GFW",
                "mitra_pair objek (opsional)",
            ],
            "schema": "See website/data/SCHEMA.md",
        },
    }
    out = DATA / "dq_report.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {out} pass={report['validate_pass']} grades={grades}")
    return val.returncode


if __name__ == "__main__":
    raise SystemExit(main())
