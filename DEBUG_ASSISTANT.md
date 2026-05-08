# Assistant Debug Commands

## 1. Test OpenAI key directly

```bash
curl -s https://api.openai.com/v1/models -H "Authorization: Bearer $(grep OPENAI_API_KEY .env | cut -d'=' -f2 | tr -d ' \r\n')" | head -c 200
```

## 2. Check full Django error for assistant

```bash
sudo journalctl -u gunicorn -n 200 --no-pager | grep -A 10 "assistant"
```

## 3. Stream live logs while testing

```bash
sudo journalctl -u gunicorn -f
```

## 4. Check nginx error log

```bash
grep -A5 "Bad Request.*assistant" /var/log/nginx/error.log | tail -20
```

## 5. Test assistant endpoint directly

```bash
curl -s -X POST https://admin.gogevgelija.com/api/assistant/query/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -d '{"message": "hello", "context_type": "general"}' | python3 -m json.tool
```

## 6. Test serializer validation directly

```bash
cd /srv/app/gogevgelija-api && python3 -c "
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()
from core.serializers import AssistantQuerySerializer
s = AssistantQuerySerializer(data={'message': 'hello'})
print(s.is_valid())
print(s.errors)
"
```

## 7. Get a real access token
```bash
python3 -c "
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()
from core.models import User
from rest_framework_simplejwt.tokens import AccessToken
u = User.objects.filter(is_staff=True).first()
print(AccessToken.for_user(u))
"
```

## 8. Test endpoint with real token (paste token from step 7)
```bash
curl -s -X POST https://admin.gogevgelija.com/api/assistant/query/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoiYWNjZXNzIiwiZXhwIjoxNzc4MjM4NjgzLCJpYXQiOjE3NzgyMzc3ODMsImp0aSI6IjExNzljMTgwODRlZTQzZjJiZGNjZjNkZDgyZTE3ZTcyIiwidXNlcl9pZCI6IjI1In0.M0vJbXrY7K9aCDWk5DBEpIPVkmxnMaYLuvMYH1GmAI4" \
  -d '{"message": "hello"}' | python3 -m json.tool
```
