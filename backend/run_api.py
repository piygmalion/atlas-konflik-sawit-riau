#!/usr/bin/env python3
"""Jalankan API lokal: uvicorn app.main:app"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import uvicorn

from app.config import get_settings


def main() -> None:
    cfg = get_settings()
    uvicorn.run(
        "app.main:app",
        host=cfg.api_host,
        port=cfg.api_port,
        reload=True,
    )


if __name__ == "__main__":
    main()
