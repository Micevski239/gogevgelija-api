# GoAI Debug Steps

## 1. SSH into the droplet

```bash
ssh root@167.71.37.168
```

## 2. Navigate to the API and activate venv

```bash
cd /var/www/gogevgelija-api   # or wherever it's deployed
source venv/bin/activate
```

## 3. Check env vars are set

```bash
grep -E "ASSISTANT|OPENAI" .env
```

Expected:
```
ASSISTANT_EXTERNAL_AI_PROVIDER=openai
OPENAI_API_KEY=sk-...
ASSISTANT_OPENAI_MODEL=gpt-5.4-mini
```

## 4. Test the AI provider in Django shell

```bash
python manage.py shell
```

```python
from core.assistant_ai import get_assistant_ai_provider

provider = get_assistant_ai_provider()
print("Provider:", provider)
print("Model:", provider.model if provider else "NO PROVIDER — check env vars")

# Test a simple display message
result = provider.generate_display_message(
    user_message="hey",
    language="en",
    tool="chat",
    results_summary="",
)
print("Result:", result)
```

## 5. Test the full endpoint with curl

```bash
curl -X POST http://localhost:8000/api/assistant/query/ \
  -H "Content-Type: application/json" \
  -d '{"message": "hey"}' \
  -v
```

## 6. Check Django logs for errors

```bash
journalctl -u gunicorn -n 50 --no-pager
# or
tail -n 50 /var/log/gunicorn/error.log
```
