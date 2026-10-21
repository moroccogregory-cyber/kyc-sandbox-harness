"""Re-export of the root application so `uvicorn kyc_harness.app:app` works.

This file sits next to the root ``app.py`` and shares its module name, so when it is itself
imported as top-level ``app`` (cwd = this directory, which is exactly what ``uvicorn app:app``
from inside ``kyc_harness/`` does) a plain ``from app import app`` resolves back to this
half-initialised module. The root module is loaded explicitly by path in that case.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent


def _load_root_app():
    if str(_ROOT) not in sys.path:
        sys.path.insert(0, str(_ROOT))
    spec = importlib.util.spec_from_file_location("_kyc_harness_root_app", _ROOT / "app.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


try:
    from app import app  # noqa: F401  (package run: uvicorn kyc_harness.app:app)
except ImportError:  # imported as top-level `app` — cwd is this directory
    app = _load_root_app().app

__all__ = ["app"]
