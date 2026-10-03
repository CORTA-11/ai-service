# Synodus AI service

Stateless FastAPI service that summarizes authorized chat context and returns
candidate action items. Core-api authorizes and supplies context; this service
does not access application storage or create tasks. The
[infra installer](https://github.com/CORTA-11/infra#local-setup) starts it automatically.

## Source development

Requires Python 3.12+. On Windows, activate with `.venv\Scripts\Activate.ps1`.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m uvicorn app.main:app --reload --port 8085
# In another activated terminal:
python -m pytest
curl -fsS http://localhost:8085/health/ready
```

Direct core-api startup uses port 8085; Docker uses port 8080. API docs are at
`/docs`. `POST /v1/process` receives context and provider endpoint, model, and token.
Set matching `AI_SERVICE_TOKEN` values in both services to authenticate processing
via `X-Synodus-AI-Token`; health and docs remain accessible without it. Optional
controls: `AI_PROVIDER_TIMEOUT_SECONDS`, `AI_MAX_CONCURRENT_PROVIDER_CALLS`.
