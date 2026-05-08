# Setup Commands

## Check token status for all users

```bash
cd /srv/app/gogevgelija-api && python3 -c "
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()
from core.models import User
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken
from datetime import datetime, timezone

now = datetime.now(timezone.utc)
users = User.objects.filter(is_active=True).order_by('email')

for u in users:
    latest = OutstandingToken.objects.filter(user=u).order_by('-created_at').first()
    if latest:
        expired = latest.expires_at < now
        status = 'EXPIRED' if expired else 'VALID'
        print(f'{status} | {u.email} | expires: {latest.expires_at.strftime(\"%Y-%m-%d %H:%M\")}')
    else:
        print(f'NO TOKEN | {u.email}')
"
```

---

## Rebuild preview APK

```bash
eas build --profile preview --platform android
```

---

# Deploy Backend Changes

## Pull latest code and restart

```bash
cd /srv/app/gogevgelija-api && git pull && sudo systemctl restart gunicorn
```

---

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

## 8. Test endpoint WITHOUT token (AllowAny - should still work)

```bash
curl -s -X POST https://admin.gogevgelija.com/api/assistant/query/ \
  -H "Content-Type: application/json" \
  -d '{"message": "hello"}' | python3 -m json.tool
```

## 10. Check token expiry for a specific user

```bash
cd /srv/app/gogevgelija-api && python3 -c "
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()
from core.models import User
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken
from datetime import datetime, timezone

email = 'dragana.petkova04@gmail.com'
u = User.objects.get(email=email)
tokens = OutstandingToken.objects.filter(user=u).order_by('-created_at')[:5]
for t in tokens:
    expired = t.expires_at < datetime.now(timezone.utc)
    print(f'jti: {t.jti} | expires: {t.expires_at} | expired: {expired}')
"
```

## 9. Test endpoint with real token (paste token from step 7)

```bash
curl -s -X POST https://admin.gogevgelija.com/api/assistant/query/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoiYWNjZXNzIiwiZXhwIjoxNzc4MjQ3Njc3LCJpYXQiOjE3NzgyNDY3NzcsImp0aSI6IjU5M2QyODZiMDM3ZTRkM2U5ZWM0MDZhZWE5Mzk3ODhjIiwidXNlcl9pZCI6IjI1In0.FjDRTpuSIXxcQH9s9pTe8sD2LctZ-jn9bKD2od6Vc2A" \
  -d '{"message": "hello"}' | python3 -m json.tool
```
