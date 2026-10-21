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


def _mock(filename: str, size: int | bytes, first_name: str = "Test", last_name: str = "Sandbox",
          back: tuple[str, bytes] | None = None) -> dict[str, Any]:
    return {
        "provider": "mock",
        "status": "passed",
        "note": "Simulated sandbox result — no document analysis is performed.",
        "fields": {"document_type": "NL passport", "side": "front",
                   "bytes": len(size) if isinstance(size, (bytes, bytearray)) else size},
        "checks": {"authenticity": "simulated", "data_comparison": "simulated", "image_quality": "simulated"},
        "files": {"uploaded": filename, **({"uploaded_back": back[0]} if back else {})},
        "submitted_fields": {"first_name": first_name, "last_name": last_name},
    }


def onfido(filename: str, data: bytes, first_name: str = "Test", last_name: str = "Sandbox",
           back: tuple[str, bytes] | None = None) -> dict[str, Any]:
    """Create applicant -> upload document(s) -> request a document check (sandbox token)."""
    token = os.environ.get("ONFIDO_API_TOKEN", "")
    if not token.startswith("api_sandbox"):
        raise RuntimeError("ONFIDO_API_TOKEN must be a sandbox token (api_sandbox…)")
    region = os.environ.get("ONFIDO_REGION", "eu")
    base = f"https://api.{region}.onfido.com/v3.6"
    headers = {"Authorization": f"Token token={token}"}
    document_ids: list[str] = []
    with httpx.Client(timeout=TIMEOUT, headers=headers) as c:
        r = c.post(f"{base}/applicants", json={"first_name": first_name, "last_name": last_name})
        r.raise_for_status()
        applicant_id = r.json()["id"]
        r = c.post(
            f"{base}/documents",
            data={"applicant_id": applicant_id, "type": "passport", "side": "front"},
            files={"file": (filename, data, "image/jpeg")},
        )
        r.raise_for_status()
        document_ids.append(r.json()["id"])
        if back:
            r = c.post(
                f"{base}/documents",
                data={"applicant_id": applicant_id, "type": "passport", "side": "back"},
                files={"file": (back[0], back[1], "image/jpeg")},
            )
            r.raise_for_status()
            document_ids.append(r.json()["id"])
        r = c.post(f"{base}/checks", json={"applicant_id": applicant_id, "report_names": ["document"]})
        r.raise_for_status()
        check = r.json()
    return {
        "provider": "onfido",
        "status": check.get("status", "in_progress"),
        "applicant_id": applicant_id,
        "document_ids": document_ids,
        "check": check,
        "note": "Sandbox requests return templated responses; no real analysis runs.",
    }


def persona(filename: str, data: bytes, first_name: str = "Test", last_name: str = "Sandbox",
            back: tuple[str, bytes] | None = None) -> dict[str, Any]:
    """Create a sandbox Inquiry (Persona's document submission normally runs in its hosted flow)."""
    del filename, data, back  # Persona takes documents inside its hosted flow, not via upload
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
            json={"data": {"attributes": {"inquiry-template-id": template,
                                          "fields": {"name-first": first_name, "name-last": last_name}}}},
        )
        r.raise_for_status()
        inquiry = r.json()["data"]
    return {
        "provider": "persona",
        "status": inquiry["attributes"].get("status", "created"),
        "inquiry_id": inquiry["id"],
        "note": "Sandbox inquiry — documents go through its hosted flow (step 2), not this upload.",
    }


def veriff(filename: str, data: bytes, first_name: str = "Test", last_name: str = "Sandbox",
           back: tuple[str, bytes] | None = None) -> dict[str, Any]:
    """Create a Veriff test-integration session for the hosted flow."""
    del filename, data, back  # Veriff takes document images inside its hosted flow
    api_key = os.environ.get("VERIFF_API_KEY", "")
    shared = os.environ.get("VERIFF_SHARED_SECRET", "")
    if not api_key or not shared:
        raise RuntimeError("VERIFF_API_KEY / VERIFF_SHARED_SECRET are not set")
    base = os.environ.get("VERIFF_STATION_URL", "https://stationapi.veriff.com/v1")
    session_payload = {"verification": {"callback": os.environ.get("VERIFF_CALLBACK", ""),
                                        "person": {"firstName": first_name, "lastName": last_name},
                                        "document": {"type": "PASSPORT", "country": "NL"}}}
    body = json.dumps(session_payload)
    signature = hmac.new(shared.encode(), body.encode(), hashlib.sha256).hexdigest()
    with httpx.Client(timeout=TIMEOUT) as c:
        r = c.post(f"{base}/sessions", content=body,
                   headers={"Content-Type": "application/json", "X-AUTH-CLIENT": api_key,
                            "X-SIGNATURE": signature})
        r.raise_for_status()
        session_id = r.json()["verification"]["id"]
    return {
        "provider": "veriff",
        "status": "created",
        "session_id": session_id,
        "note": "Session created; the uploaded image is NOT sent to Veriff — document + selfie go "
                "through the hosted flow (step 2). Test integrations get no decision — force it "
                "in the Veriff Customer Portal.",
    }


def onfido_start_verification(first_name: str = "Test", last_name: str = "Sandbox") -> dict[str, Any]:
    """Create an Onfido applicant + SDK token for the hosted Web/Mobile SDK (selfie+liveness)."""
    token = os.environ.get("ONFIDO_API_TOKEN", "")
    if not token.startswith("api_sandbox"):
        raise RuntimeError("ONFIDO_API_TOKEN must be a sandbox token (api_sandbox…)")
    region = os.environ.get("ONFIDO_REGION", "eu")
    referrer = os.environ.get("ONFIDO_REFERRER", "https://*.sslip.io/*")
    base = f"https://api.{region}.onfido.com/v3.6"
    headers = {"Authorization": f"Token token={token}"}
    with httpx.Client(timeout=TIMEOUT, headers=headers) as c:
        r = c.post(f"{base}/applicants", json={"first_name": first_name, "last_name": last_name})
        r.raise_for_status()
        applicant_id = r.json()["id"]
        r = c.post(f"{base}/sdk_token", json={"applicant_id": applicant_id, "referrer": referrer})
        r.raise_for_status()
        sdk = r.json()
    return {
        "provider": "onfido",
        "flow": "hosted",
        "applicant_id": applicant_id,
        "sdk_token": sdk.get("token"),
        "note": "Mount Onfido's Web SDK with this sdk_token to run the sandbox selfie/liveness capture.",
    }


def persona_start_verification(first_name: str = "Test", last_name: str = "Sandbox",
                                 birthdate: str | None = None) -> dict[str, Any]:
    """Create a Persona sandbox Inquiry and return its hosted-flow URL."""
    key = os.environ.get("PERSONA_API_KEY", "")
    if not key:
        raise RuntimeError("PERSONA_API_KEY is not set")
    template = os.environ.get("PERSONA_TEMPLATE_ID", "")
    if not template:
        raise RuntimeError("PERSONA_TEMPLATE_ID is not set")
    headers = {"Authorization": f"Bearer {key}", "Persona-Version": "2023-01-05"}
    fields: dict[str, Any] = {"name-first": first_name, "name-last": last_name}
    if birthdate:
        fields["birthdate"] = birthdate
    with httpx.Client(timeout=TIMEOUT, headers=headers) as c:
        r = c.post(
            "https://api.withpersona.com/api/v1/inquiries",
            json={"data": {"attributes": {"inquiry-template-id": template, "fields": fields}}},
        )
        r.raise_for_status()
        inquiry = r.json()["data"]
    attrs = inquiry["attributes"]
    # Persona has renamed this field across API versions; accept whichever the sandbox returns.
    hosted_url = attrs.get("session-token-url") or attrs.get("hosted-url") or attrs.get("url")
    return {
        "provider": "persona",
        "flow": "hosted",
        "inquiry_id": inquiry["id"],
        "status": attrs.get("status", "created"),
        "hosted_flow_url": hosted_url,
        "note": "Open hosted_flow_url to run the sandbox selfie/liveness capture; field name "
                "verified against docs.withpersona.com at build time — re-check if this comes back null.",
    }


def veriff_start_verification(first_name: str = "Test", last_name: str = "Sandbox") -> dict[str, Any]:
    """Create a Veriff test-integration session and return the hosted verification.url."""
    api_key = os.environ.get("VERIFF_API_KEY", "")
    shared = os.environ.get("VERIFF_SHARED_SECRET", "")
    if not api_key or not shared:
        raise RuntimeError("VERIFF_API_KEY / VERIFF_SHARED_SECRET are not set")
    base = os.environ.get("VERIFF_STATION_URL", "https://stationapi.veriff.com/v1")
    payload = {"verification": {"callback": os.environ.get("VERIFF_CALLBACK", ""),
                                 "person": {"firstName": first_name, "lastName": last_name},
                                 "vendorData": "kyc-sandbox-harness"}}
    body = json.dumps(payload)
    signature = hmac.new(shared.encode(), body.encode(), hashlib.sha256).hexdigest()
    with httpx.Client(timeout=TIMEOUT) as c:
        r = c.post(f"{base}/sessions", content=body,
                   headers={"Content-Type": "application/json", "X-AUTH-CLIENT": api_key,
                            "X-SIGNATURE": signature})
        r.raise_for_status()
        session = r.json()["verification"]
    return {
        "provider": "veriff",
        "flow": "hosted",
        "session_id": session["id"],
        "hosted_flow_url": session.get("url"),
        "note": "Open hosted_flow_url to run the sandbox selfie/liveness capture; the test "
                "integration gives no automatic decision — force it in the Veriff Customer Portal.",
    }


def _mock_start_verification(first_name: str = "Test", last_name: str = "Sandbox") -> dict[str, Any]:
    return {
        "provider": "mock",
        "flow": "hosted",
        "session_id": f"mock-{uuid.uuid4().hex[:12]}",
        "hosted_flow_url": None,
        "note": "Mock has no hosted flow — this simulates the step so the UI/flow can be tested end to end.",
    }


HOSTED_FLOW = {
    "mock": _mock_start_verification,
    "onfido": onfido_start_verification,
    "persona": persona_start_verification,
    "veriff": veriff_start_verification,
}

PROVIDERS = {"mock": _mock, "onfido": onfido, "persona": persona, "veriff": veriff}
