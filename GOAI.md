# GoAI Assistant — Reference

## Architecture

- `core/assistant_ai.py` — AI provider (OpenAI calls, prompts, `generate_display_message`, `plan_query`)
- `core/assistant_parser.py` — Heuristic parser (greetings, wiki, category, FAQ, feed rules — no LLM needed)
- `core/views.py` — `AssistantQueryView` (orchestrates the full pipeline)

## Request Flow (views.py)

```
POST /api/assistant/query/
  │
  ├─ Step 1: Always run heuristic parser (free, fast)
  │
  ├─ Step 2: Greeting/identity? → return answer='' directly, NO AI call
  │
  ├─ Step 3: High/medium confidence → parser-first (DB query + optional display_message)
  │
  ├─ Step 4: Low confidence / unknown → full LLM pipeline (plan_query → execute → display_message)
  │
  └─ Step 5: AI unavailable/failed → pure parser fallback (heuristic search)
```

## Required Env Vars (production .env)

```
ASSISTANT_EXTERNAL_AI_PROVIDER=openai
OPENAI_API_KEY=<set in production secret manager>
ASSISTANT_OPENAI_MODEL=gpt-5.4-mini
ASSISTANT_OPENAI_TIMEOUT_SECONDS=20
```

## Known Bugs Fixed (May 2026 session)

### 1. Wrong model name (`gpt-5-mini` → `gpt-5.4-mini`)
- `gpt-5-mini` doesn't exist as a valid OpenAI model
- Correct model from OpenAI pricing page: `gpt-5.4-mini`
- Fixed in: production `.env` on droplet

### 2. `max_tokens` not supported by gpt-5.x (`assistant_ai.py`)
- gpt-5.x models require `max_completion_tokens` instead of `max_tokens`
- Error: `"Unsupported parameter: 'max_tokens' is not supported with this model"`
- Fixed in: `core/assistant_ai.py` line ~76
  ```python
  # Before
  body["max_tokens"] = max_tokens
  # After
  body["max_completion_tokens"] = max_tokens
  ```

### 3. `requests` exceptions not caught (`assistant_ai.py`)
- `requests.post` could throw `Timeout` / `ConnectionError` which bypassed `AssistantAIError`
- Caused 500 errors on network failures
- Fixed in: `core/assistant_ai.py` — wrapped `requests.post` in try/except `requests.RequestException`

### 4. Model default fallback removed
- Previous session removed the hardcoded default (`gpt-4o-mini`)
- If `ASSISTANT_OPENAI_MODEL` env var is missing, model becomes empty string → API error
- Fixed: restored default to `gpt-5.4-mini` in code

## Deployment (DigitalOcean droplet)

```bash
# On local machine
git add core/assistant_ai.py
git commit -m "Fix: use max_completion_tokens for gpt-5.x compatibility"
git push

# On droplet
cd /srv/app/gogevgelija-api
git pull
sudo systemctl restart gunicorn
```

## Debugging on Droplet

```bash
ssh <production-user>@<production-host>
cd /srv/app/gogevgelija-api
source venv/bin/activate

# Check env vars
grep -E "ASSISTANT|OPENAI" .env

# Test AI provider in Django shell
python manage.py shell
```

```python
from core.assistant_ai import get_assistant_ai_provider
provider = get_assistant_ai_provider()
print("Provider:", provider)
print("Model:", provider.model if provider else "NO PROVIDER")

result = provider.generate_display_message(
    user_message="hey",
    language="en",
    tool="chat",
    results_summary="",
)
print("Result:", result)
```

```bash
# Test endpoint directly
curl -X POST http://localhost:8000/api/assistant/query/ \
  -H "Content-Type: application/json" \
  -d '{"message": "hey"}' -v

# Check logs
journalctl -u gunicorn -n 50 --no-pager
```

## Pending

- [ ] Deploy `max_completion_tokens` fix to production (`git push` + `git pull` on droplet + restart gunicorn)
- [ ] Verify `generate_greeting` in `assistant_ai.py` is dead code (defined but never called from views)
