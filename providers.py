"""Sandbox adapters for the KYC test harness.

Every adapter talks ONLY to the vendors' documented TEST/sandbox environments:
- Onfido/Entrust  -> api_sandbox* token, templated simulated reports
- Persona         -> sandbox API key, sandbox inquiries (no real verification)
- Veriff          -> test-integration API key, decisions forced by the tester
- mock            -> built-in, no keys needed (shows the harness flow)

Nothing here is meant for live KYC decisions. Use it to exercise an integration.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import uuid
from typing import Any

import httpx

TIMEOUT = httpx.Timeout(30.0, connect=10.0)


def _mock(filename: str, size: int | bytes) -> dict[str, Any]:
    return {
        "provider": "mock",
        "status": "passed",
        "note": "Simulated sandbox result — no document analysis is performed.",
        "fields": {"document_type": "NL passport", "side": "front",
                   "bytes": len(size) if isinstance(size, (bytes, bytearray)) else size},
        "checks": {"authenticity": "simulated", "data_comparison": "simulated", "image_quality": "simulated"},
        "files": {"uploaded": filename},
    }


def onfido(filename: str, data: bytes) -> dict[str, Any]:
    """Create applicant -> upload document -> request a document check (sandbox token)."""
    token = os.environ.get("ONFIDO_API_TOKEN", "")
    if not token.startswith("api_sandbox"):
        raise RuntimeError("ONFIDO_API_TOKEN must be a sandbox token (api_sandbox…)")
    region = os.environ.get("ONFIDO_REGION", "eu")
    base = f"https://api.{region}.onfido.com/v3.6"
    headers = {"Authorization": f"Token token={token}"}
    with httpx.Client(timeout=TIMEOUT, headers=headers) as c:
        r = c.post(f"{base}/applicants", json={"first_name": "Test", "last_name": "Sandbox"})
        r.raise_for_status()
        applicant_id = r.json()["id"]
        r = c.post(
            f"{base}/documents",
            data={"applicant_id": applicant_id, "type": "passport"},
            files={"file": (filename, data, "image/jpeg")},
        )
        r.raise_for_status()
        document_id = r.json()["id"]
        r = c.post(f"{base}/checks", json={"applicant_id": applicant_id, "report_names": ["document"]})
        r.raise_for_status()
        check = r.json()
    return {
        "provider": "onfido",
        "status": check.get("status", "in_progress"),
        "applicant_id": applicant_id,
        "document_id": document_id,
        "check": check,
        "note": "Sandbox requests return templated responses; no real analysis runs.",
    }


def persona(filename: str, data: bytes) -> dict[str, Any]:
    """Create a sandbox Inquiry (Persona's document submission normally runs in its hosted flow)."""
    key = os.environ.get("PERSONA_API_KEY", "")
    if not key:
        raise RuntimeError("PERSONA_API_KEY is not set")
    template = os.environ.get("PERSONA_TEMPLATE_ID", "")
    if not template:
        raise RuntimeError("PERSONA_TEMPLATE_ID is not set")
    headers = {"Authorization": f"Bearer {key}", "Persona-Version": "2023-01-05"}
    with httpx.Client(timeout=TIMEOUT, headers=headers) as c:
        r = c.post(
            "https://api.withpersona.com/api/v1/inquiries",
            json={"data": {"attributes": {"inquiry-template-id": template}}},
        )
        r.raise_for_status()
        inquiry = r.json()["data"]
    return {
        "provider": "persona",
        "status": inquiry["attributes"].get("status", "created"),
        "inquiry_id": inquiry["id"],
        "note": "Sandbox inquiry — open its hosted-flow URL to submit a test document; sandbox does not verify.",
    }


def veriff(filename: str, data: bytes) -> dict[str, Any]:
    """Create a Veriff test-integration session and upload one document image."""
    api_key = os.environ.get("VERIFF_API_KEY", "")
    shared = os.environ.get("VERIFF_SHARED_SECRET", "")
    if not api_key or not shared:
        raise RuntimeError("VERIFF_API_KEY / VERIFF_SHARED_SECRET are not set")
    base = os.environ.get("VERIFF_STATION_URL", "https://stationapi.veriff.com/v1")
    session_payload = {"verification": {"callback": os.environ.get("VERIFF_CALLBACK", ""),
                                        "person": {"firstName": "Test", "lastName": "Sandbox"},
                                        "document": {"type": "PASSPORT", "country": "NL"}}}
    body = json.dumps(session_payload)

    def sign(payload: str) -> str:
        return hmac.new(shared.encode(), payload.encode(), hashlib.sha256).hexdigest()

    with httpx.Client(timeout=TIMEOUT) as c:
        r = c.post(f"{base}/sessions", content=body,
                   headers={"Content-Type": "application/json", "X-AUTH-CLIENT": api_key,
                            "X-SIGNATURE": sign(body)})
        r.raise_for_status()
        session = r.json()
        session_id = session["verification"]["id"]
        media_body = json.dumps({"images": []})
        r = c.post(f"{base}/sessions/{session_id}/media", content=media_body,
                   headers={"Content-Type": "application/json", "X-AUTH-CLIENT": api_key,
                            "X-SIGNATURE": sign(media_body)})
        media_status = r.status_code
    return {
        "provider": "veriff",
        "status": "created",
        "session_id": session_id,
        "media_upload_http": media_status,
        "note": "Test integrations get no decision — force the status in the Veriff Customer Portal.",
    }


PROVIDERS = {"mock": _mock, "onfido": onfido, "persona": persona, "veriff": veriff}
