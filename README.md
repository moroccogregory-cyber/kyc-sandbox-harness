# KYC sandbox harness

One page: upload a test image, pick a sandbox provider (mock / Onfido / Persona / Veriff), see
the sandbox response. Built for integration testing only — sandbox modes never verify documents.

## Run locally

    .venv/bin/python -m uvicorn kyc_harness.app:app --host 127.0.0.1 --port 8899
    open http://127.0.0.1:8899

Without keys only **mock** works; the other providers report exactly which env var is missing.

## Deploy on Dokploy (your server)

1. Push this folder (or the repo) to a private GitHub repo under moroccogregory-cyber.
2. Dokploy → Create Application → Git → pick the repo, build path = repo root (Dockerfile at
   repo root must be `kyc_harness/Dockerfile`, so either set Dockerfile path to
   `kyc_harness/Dockerfile` or push `kyc_harness/` as its own repo).
3. Environment: paste the variables from `.env.example` (sandbox keys only!). Set
   `HARNESS_USER`/`HARNESS_PASS` so the harness isn't open to the internet.
4. Domain: point e.g. `kyc.bestelappje.com` at it, enable HTTPS (Let's Encrypt in Dokploy).
5. Deploy. Health check path: `/health`.

## Security notes

- Sandbox credentials only; never put live keys here.
- Add basic auth before exposing it publicly.
- The only persistent state is the last 50 responses in memory (resets on restart).
