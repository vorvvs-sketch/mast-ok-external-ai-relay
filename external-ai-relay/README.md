# External AI Relay

Minimal relay service for deployment in a supported region.

What it does:

- accepts `POST /api/diagnose`
- accepts `POST /api/diagnose-form`
- calls OpenAI directly
- returns the response in the format already used by the main `mast-ok` backend

## Env

```text
AI_API_KEY=
AI_MODEL=gpt-4.1-mini
AI_API_URL=https://api.openai.com/v1/chat/completions
AI_TIMEOUT=30
MAX_UPLOAD_MB=8
CATALOG_PATH=/app/catalog.json
```

## Local run

```powershell
pip install -r external-ai-relay\requirements.txt
uvicorn external-ai-relay.app:app --host 0.0.0.0 --port 8020
```

## Docker run

```powershell
docker build -t mast-ok-external-ai .\external-ai-relay
docker run -p 8020:8020 `
  -e AI_API_KEY=YOUR_KEY `
  -e AI_MODEL=gpt-4.1-mini `
  mast-ok-external-ai
```

## Render deploy

The folder already contains:

- `Dockerfile`
- `render.yaml`

Fast path:

1. Push the repository to GitHub.
2. Create a new Render Blueprint from that repository.
3. Confirm deployment of `mast-ok-external-ai-relay`.
4. Set secret env var `AI_API_KEY`.
5. Wait for deploy and open:

```text
https://your-render-service.onrender.com/api/health
```

## Health

```text
GET /api/health
```

## After relay deploy

On the main `mast-ok` backend set:

```text
EXTERNAL_AI_BASE_URL=https://your-relay-domain.example.com
EXTERNAL_AI_MODE=mastok_api
EXTERNAL_AI_BEARER_TOKEN=
```

Then restart `mast-ok-backend`.
