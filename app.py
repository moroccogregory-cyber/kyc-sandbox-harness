"""KYC sandbox test harness — tiny FastAPI app.

Upload one image, pick a sandbox provider, see what the sandbox returns. Optional HTTP Basic
auth (HARNESS_USER / HARNESS_PASS). Degrades gracefully: without keys only the mock provider
works; the others explain which env var is missing.

Run:  uvicorn kyc_harness.app:app --host 0.0.0.0 --port 8899
"""
from __future__ import annotations

import base64
import json
import os
import secrets
import time
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials

try:  # package run (repo root): uvicorn kyc_harness.app:app
    from .providers import PROVIDERS
except ImportError:  # standalone repo (Dokploy): uvicorn app:app
    from providers import PROVIDERS

app = FastAPI(title="KYC sandbox harness", docs_url="/docs", redoc_url=None)
security = HTTPBasic(auto_error=False)
EVENTS: list[dict] = []
STATIC = Path(__file__).parent / "static"


def auth(creds: HTTPBasicCredentials | None = Depends(security)) -> None:
    user = os.environ.get("HARNESS_USER", "")
    password = os.environ.get("HARNESS_PASS", "")
    if not user or not password:
        return  # open (only for a throwaway sandbox harness)
    if creds is None or not (
        secrets.compare_digest(creds.username, user) and secrets.compare_digest(creds.password, password)
    ):
        raise HTTPException(401, "auth required", headers={"WWW-Authenticate": "Basic"})


@app.get("/health")
def health() -> dict:
    return {"ok": True, "providers": sorted(PROVIDERS)}


@app.get("/", response_class=HTMLResponse)
def index(_: None = Depends(auth)) -> str:
    return (STATIC / "index.html").read_text()


@app.get("/api/providers")
def providers(_: None = Depends(auth)) -> dict:
    return {"providers": sorted(PROVIDERS)}


@app.post("/api/verify")
async def verify(provider: str = Form(...), file: UploadFile = File(...), _: None = Depends(auth)) -> JSONResponse:
    fn = PROVIDERS.get(provider)
    if fn is None:
        raise HTTPException(400, f"unknown provider {provider!r}; choose one of {sorted(PROVIDERS)}")
    data = await file.read()
    if not data:
        raise HTTPException(400, "empty upload")
    try:
        result = fn(file.filename or "upload.jpg", data)
    except Exception as exc:  # noqa: BLE001 — surface the config/API error to the tester
        result = {"provider": provider, "status": "error", "error": str(exc)}
    EVENTS.append({"at": time.time(), "provider": provider, "result": result})
    return JSONResponse(result)


@app.post("/webhook/{provider}")
async def webhook(provider: str, request: Request) -> dict:
    """Tiny webhook sink: stores whatever the sandbox posts so the UI can show decisions."""
    raw = await request.body()
    try:
        payload = json.loads(raw or b"{}")
    except json.JSONDecodeError:
        payload = {"raw_b64": base64.b64encode(raw).decode()[:2000]}
    EVENTS.append({"at": time.time(), "provider": provider, "webhook": payload})
    return {"received": True}


@app.get("/api/events")
def events(_: None = Depends(auth)) -> dict:
    return {"events": EVENTS[-50:]}
