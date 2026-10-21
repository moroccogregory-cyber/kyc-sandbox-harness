# KYC sandbox harness

Two steps: upload a test document (mock / Onfido / Persona / Veriff), then start the vendor's
**hosted flow** for selfie/liveness capture — that step always happens on the vendor's own hosted
page/SDK, never as a plain upload. Built for integration testing only — sandbox modes never verify
real documents or identities.

## Run locally

    .venv/bin/python -m uvicorn kyc_harness.app:app --host 127.0.0.1 --port 8899
    # or from inside kyc_harness/:
    uvicorn app:app --host 127.0.0.1 --port 8899
    open http://127.0.0.1:8899

Without keys only **mock** works; the other providers report exactly which env var is missing
(as clean JSON, no crash).

## Step 1 — Document upload

`POST /api/verify` — `provider`, `file` (front), optional `file_back`, optional `first_name` /
`last_name` / `date_of_birth`. Passed through to the vendor where it supports it (Onfido/Veriff
applicant name; Persona inquiry fields).

## Step 2 — Hosted flow (selfie/liveness)

`POST /api/start_verification` — `provider`, optional `first_name` / `last_name` /
`date_of_birth`. Returns the vendor's hosted-flow entry point:

- **Onfido**: creates an applicant, then an SDK token (`ONFIDO_REFERRER` must match where the
  Web SDK is mounted). The UI shows the `sdk_token` to feed Onfido's Web SDK — that is what runs
  the sandbox selfie/liveness capture.
- **Persona**: creates a sandbox Inquiry from `PERSONA_TEMPLATE_ID` and returns its hosted-flow
  URL (Persona has renamed this response field across API versions — the harness tries
  `session-token-url`, `hosted-url`, then `url`; re-check docs.withpersona.com if it comes back
  null).
- **Veriff**: creates a test-integration session (HMAC-SHA256 signed) and returns
  `verification.url`, the hosted flow, plus the session id. Test integrations never auto-decide —
  force the result in the Veriff Customer Portal.
- **mock**: simulates the step (returns a fake session id, no real hosted flow) so the full two-step
  flow can be exercised end to end without any vendor keys.

Every call — document upload, hosted-flow start, and incoming webhooks at `/webhook/{provider}` —
is appended to an in-memory event log; `GET /api/events` returns the last 50, and the page lists
them live under "Latest events".

## Deploy on Dokploy (your server)

1. Push this folder (or the repo) to a private GitHub repo under moroccogregory-cyber.
2. Dokploy → Create Application → Git → pick the repo, build path = repo root (Dockerfile at
   repo root must be `kyc_harness/Dockerfile`, so either set Dockerfile path to
   `kyc_harness/Dockerfile` or push `kyc_harness/` as its own repo).
3. Environment: paste the variables from `.env.example` (sandbox keys only!). Set
   `HARNESS_USER`/`HARNESS_PASS` so the harness isn't open to the internet. Set
   `ONFIDO_REFERRER` to the public domain (wildcard allowed), `PERSONA_TEMPLATE_ID` to a sandbox
   inquiry template, `VERIFF_CALLBACK` to `https://<public-domain>/webhook/veriff`.
4. Domain: point e.g. `kyc.bestelappje.com` at it, enable HTTPS (Let's Encrypt in Dokploy).
5. Deploy. Health check path: `/health`.

## Security notes

- Sandbox credentials only; never put live keys here. `ONFIDO_API_TOKEN` is rejected unless it
  starts with `api_sandbox`; Persona/Veriff keys must be the vendor's sandbox/test-integration
  credentials — this harness refuses to proceed on a missing/malformed key rather than silently
  calling a production endpoint.
- Add basic auth before exposing it publicly.
- The only persistent state is the last 50 events in memory (resets on restart); no database.
