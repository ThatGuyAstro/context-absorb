#!/usr/bin/env python3
from __future__ import annotations

import runpy
from pathlib import Path


if __name__ == "__main__":
    shared = Path(__file__).resolve().parents[3] / "shared" / "session_absorb_core.py"
    runpy.run_path(str(shared), run_name="__main__")
