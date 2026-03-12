# External AI Relay

Minimal relay service for deployment in a supported region.

What it does:

- accepts `POST /api/diagnose`
- accepts `POST /api/diagnose-form`
- calls OpenAI directly
- returns the response in the format already used by the main `mast-ok` backend
- uses local `catalog.json`

## Env

```text
AI_API_KEY=
AI_MODEL=gpt-4.1-mini
AI_API_URL=https://api.openai.com/v1/chat/completions
AI_TIMEOUT=30
MAX_UPLOAD_MB=20
CATALOG_PATH=./catalog.json
```

## Local run

```powershell
pip install -r requirements.txt
uvicorn app:app --host 0.0.0.0 --port 8020
```

## Render deploy

Put these files in the root of a separate GitHub repository:

- `app.py`
- `requirements.txt`
- `README.md`
- `render.yaml`
- `catalog.json`
- `test-cases.json`
- `evaluate.py`

Then in Render:

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

## Quality check

You can run a simple relay quality check against local or remote endpoint:

```powershell
$env:RELAY_ENDPOINT='https://your-relay-domain.example.com/api/diagnose'
python evaluate.py
```
