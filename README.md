# Synodus AI Context Engine

Small, stateless HTTP service for summarizing authorized chat context and returning validated candidate action items.

## Run locally

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m uvicorn app.main:app --reload --port 8085
```

Run tests with:

```powershell
\.\.venv\Scripts\python -m pytest
```

The service does not access Synodus storage, persist context, or create tasks. The Core API must authorize and fetch the context before calling `POST /v1/process`; accepted candidates must go through the normal task API.

Set `AI_SERVICE_TOKEN` in both services to require the Core API's `X-Synodus-AI-Token` header on processing requests. Health and documentation endpoints remain available without that header.

## Production image

Pushing to `main` publishes `ghcr.io/corta-11/ai-service:latest` and redeploys
`ai-service` and `api`. Configure `SERVER_HOST`, `SERVER_USER`, and
`SERVER_SSH_KEY` for this repository, as with the other service repositories,
and deploy the matching infra Compose changes before the first image release.
