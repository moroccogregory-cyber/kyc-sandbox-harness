"""Package shim so the harness is importable as `kyc_harness.app:app` as well as `app:app`.

The real application lives in the repository-root `app.py` (that is what the Dockerfile runs).
This package only puts the repository root on `sys.path`, so the documented run modes both work
from the repo root and from anywhere else:

    .venv/bin/python -m uvicorn kyc_harness.app:app     # repo root / anywhere
    uvicorn app:app                                     # inside the repo root
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = str(Path(__file__).resolve().parent.parent)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
