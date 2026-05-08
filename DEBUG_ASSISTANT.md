# Setup Commands

## Cron job — keep all API caches warm

Runs every 2 minutes (shortest cache TTL is 3 min for events). Warms both language variants for all main endpoints so no real user ever hits a cold cache.

```bash
crontab -e
```

Add this line:

```
*/12 * * * * BASE=https://admin.gogevgelija.com/api; for EP in home/sections categories listings events promotions blogs billboard; do curl -s "$BASE/$EP/" > /dev/null; curl -s "$BASE/$EP/?lang=mk" > /dev/null; done
```

Manually trigger cache warm-up (to test or after deploy):

```bash
BASE=https://admin.gogevgelija.com/api; for EP in home/sections categories listings events promotions blogs billboard; do curl -s "$BASE/$EP/" > /dev/null; curl -s "$BASE/$EP/?lang=mk" > /dev/null; echo "$EP warmed"; done
```

---

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
cd /srv/app/gogevgelija-api && git pull && sudo systemctl restart gunicorn && sleep 3 && curl -s https://admin.gogevgelija.com/api/home/sections/ > /dev/null && curl -s "https://admin.gogevgelija.com/api/home/sections/?lang=mk" > /dev/null
```

The `sleep 3` waits for workers to start, then warms the home sections cache for both languages so the first real user doesn't pay the cold-cache cost.

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

## 12. Fix user first_name/last_name split (when full name is in first_name field)

```bash
cd /srv/app/gogevgelija-api && python3 -c "
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()
from core.models import User
u = User.objects.get(email='ilijaatanasov04@gmail.com')
u.first_name = 'Ilija'
u.last_name = 'Atanasov'
u.save()
print('done')
"
```

---

## 11. Check user account data

```bash
cd /srv/app/gogevgelija-api && python3 -c "
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()
from core.models import User
u = User.objects.get(email='ilijaatanasov04@gmail.com')
print('username:', u.username)
print('first_name:', u.first_name)
print('last_name:', u.last_name)
print('is_active:', u.is_active)
"
```

---

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

---

# Nginx — Block Unknown Host Scanners

Active config: `/etc/nginx/sites-enabled/gogevgelija`

Add these two blocks at the **very top** of the file, before any existing `server {}` blocks.
They drop connections with unknown `Host` headers at nginx (return 444 = no response), so gunicorn never sees them.

```nginx
server {
    listen 80 default_server;
    server_name _;
    return 444;
}

server {
    listen 443 ssl default_server;
    server_name _;
    ssl_certificate /etc/letsencrypt/live/admin.gogevgelija.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/admin.gogevgelija.com/privkey.pem;
    return 444;
}
```

After editing:

```bash
nginx -t && systemctl reload nginx
```

Test it works (should get no response / connection reset):

```bash
curl -v -H "Host: lightsonbycsv.com" http://165.22.76.15/
```

Test real domain still works:

```bash
curl -v https://admin.gogevgelija.com/api/health/
```

---

# Fail2ban — Auto-ban Malicious IPs

## Install

```bash
apt install fail2ban
```

## Configure — create jail.local

```bash
nano /etc/fail2ban/jail.local
```

```ini
[DEFAULT]
bantime = 1h
findtime = 10m
maxretry = 50

[sshd]
enabled = true
port = ssh
logpath = /var/log/auth.log

[nginx-bad-host]
enabled = true
port = http,https
logpath = /var/log/nginx/error.log
filter = nginx-bad-host
maxretry = 10
bantime = 24h

[nginx-limit-req]
enabled = true
port = http,https
logpath = /var/log/nginx/error.log
filter = nginx-limit-req
maxretry = 10
bantime = 1h
```

## Create custom filter

```bash
nano /etc/fail2ban/filter.d/nginx-bad-host.conf
```

```ini
[Definition]
failregex = .*\[error\].*client: <HOST>,.*invalid host.*
            .*\[error\].*client: <HOST>,.*disallowed host.*
ignoreregex =
```

## Start

```bash
systemctl enable fail2ban && systemctl restart fail2ban && fail2ban-client status
```

## Check banned IPs

```bash
fail2ban-client status nginx-bad-host
fail2ban-client status sshd
```

## Unban an IP

```bash
fail2ban-client set nginx-bad-host unbanip <IP>
```

---

# Nginx — Rate Limiting

Prevents flood attacks by limiting requests per IP.

## 1. Add rate limit zone to `/etc/nginx/nginx.conf` inside `http {}`

```bash
nano /etc/nginx/nginx.conf
```

Add this line inside `http {}` before the closing `}`:

```nginx
limit_req_zone $binary_remote_addr zone=api:10m rate=20r/s;
```

## 2. Apply rate limit in `/etc/nginx/sites-enabled/gogevgelija`

```bash
nano /etc/nginx/sites-enabled/gogevgelija
```

Add inside `location / {}` in **both** server blocks (port 80 and 443):

```nginx
limit_req zone=api burst=40 nodelay;
```

## 3. Test and reload

```bash
nginx -t && systemctl reload nginx
```

20 requests/sec per IP, burst to 40, then nginx returns 429. Fail2ban will auto-ban IPs that trigger too many 429s via the `nginx-limit-req` jail.
