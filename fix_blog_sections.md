Run this on the server:

```bash
python manage.py shell -c "from django.db import connection; c = connection.cursor(); c.execute('ALTER TABLE core_blog_sections RENAME TO core_blog_home_sections'); connection.connection.commit(); print('done')"
```

Then restart:

```bash
sudo systemctl restart gunicorn
```

git pull && python manage.py shell -c "from django.core.cache import cache; cache.clear(); print('done')" && sudo systemctl restart gunicorn

## Check what Groq returned for last query

```bash
tail -5 /srv/app/gogevgelija-api/logs/assistant_queries.log | python3 -c "import sys,json; [print(json.dumps(json.loads(l), indent=2, ensure_ascii=False)) for l in sys.stdin if l.strip()]"
```

Look for `"tool"` inside `"understanding"` — if it says `"search"` or `"feed"` instead of `"chat"`, Groq is ignoring the chat routing rule.

## List available Groq models

```bash
python manage.py shell -c "
import requests, os
r = requests.get('https://api.groq.com/openai/v1/models', headers={'Authorization': 'Bearer ' + os.getenv('GROQ_API_KEY','')})
for m in sorted(r.json().get('data',[]), key=lambda x: x['id']):
    print(m['id'])
"
```

## Test Groq API directly (single line)

```bash
and
```

## Debug: check if Groq provider is loading

```bash
python manage.py shell -c "from core.assistant_ai import get_assistant_ai_provider; p = get_assistant_ai_provider(); print(p)"
```

If prints `None`, Django can't see the env vars. Then check:

```bash
python manage.py shell -c "import os; print(repr(os.getenv('ASSISTANT_EXTERNAL_AI_PROVIDER'))); print(repr(os.getenv('GROQ_API_KEY', 'NOT SET')[:15]))"
```
