# Setup Commands

## BetterStack — Log Monitoring (nginx + gunicorn)

Ships nginx and gunicorn logs to BetterStack in real time using Vector.

### Source details

- Source token: `LidNY314bEEzagKcGw8EbBL8`
- Ingesting host: `s2424994.eu-fsn-3.betterstackdata.com`

### Step 1 — test connectivity

```bash
curl -X POST \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer LidNY314bEEzagKcGw8EbBL8' \
  -d '{"dt":"'"$(date -u +'%Y-%m-%d %T UTC')"'","message":"Hello from Better Stack!"}' \
  --insecure \
  https://s2424994.eu-fsn-3.betterstackdata.com
```

Should return `{}` or empty — check BetterStack → Logs → Live tail for the message.

### Step 2 — install Vector

```bash
curl -L https://github.com/vectordotdev/vector/releases/download/v0.43.1/vector_0.43.1-1_amd64.deb -o vector.deb && sudo dpkg -i vector.deb && rm vector.deb
```

Verify:

```bash
vector --version
```

### Step 3 — configure Vector

```bash
nano /etc/vector/vector.yaml
```

Paste this config:

```yaml
sources:
  nginx_access:
    type: file
    include:
      - /var/log/nginx/access.log

  nginx_error:
    type: file
    include:
      - /var/log/nginx/error.log

  gunicorn:
    type: journald
    include_units:
      - gunicorn.service

sinks:
  betterstack:
    type: http
    inputs:
      - nginx_access
      - nginx_error
      - gunicorn
    uri: https://s2424994.eu-fsn-3.betterstackdata.com
    encoding:
      codec: json
    auth:
      strategy: bearer
      token: LidNY314bEEzagKcGw8EbBL8
    headers:
      Content-Type: application/json
```

### Step 4 — fix config and start Vector

```bash
sed -i 's/    units:/    include_units:/' /etc/vector/vector.yaml
```

```bash
vector validate /etc/vector/vector.yaml && sudo systemctl enable vector && sudo systemctl start vector && sudo systemctl status vector
```

### Step 5 — verify logs are flowing

```bash
sudo journalctl -u vector -f
```

Should show Vector reading files and sending to BetterStack. Check BetterStack → Logs → Live tail to see nginx and gunicorn logs streaming in.

---

## BetterStack — Error Tracking + Log Monitoring

BetterStack captures Django exceptions AND streams nginx/gunicorn logs. Uses the Sentry SDK protocol — no code changes needed, just swap the DSN. Sentry stays for the mobile frontend only.

### Setup (one time)

Create a Django application at **betterstack.com → Error Tracking → Connect Application → Django**. Copy the DSN it gives you.

### Swap DSN on server

```bash
sed -i 's|SENTRY_DSN=.*|SENTRY_DSN=https://TkoE8ioJn7Y5b5RUDDYYztb2@s2424979.eu-nbg-2.betterstackdata.com/2424981|' /srv/app/gogevgelija-api/.env
```

Current BetterStack DSN:

```
https://TkoE8ioJn7Y5b5RUDDYYztb2@s2424979.eu-nbg-2.betterstackdata.com/2424981
```

### Restart gunicorn

```bash
sudo systemctl restart gunicorn
```

### Test connection

```bash
cd /srv/app/gogevgelija-api && source venv/bin/activate && python3 -c "
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()
import sentry_sdk
sentry_sdk.capture_message('Hello Better Stack, this is a test message from Python!')
print('done')
"
```

Check BetterStack → Errors — the test message should appear. From now on every Django error lands there automatically.

---

## Sentry Backend — Error Monitoring (replaced by BetterStack)

~~Captures every Django exception, 500 error, and unhandled crash in real time. No frontend build needed.~~

### 1. Create Sentry project

Go to **Sentry → Projects → New Project → Python → Django**, name it `gogevgelija-api`, copy the DSN.

### 2. Add DSN to server .env

```bash
echo 'SENTRY_DSN=https://YOUR_DSN_HERE' >> /srv/app/gogevgelija-api/.env
```

### 3. Deploy

```bash
cd /srv/app/gogevgelija-api && git pull && pip install -r requirements.txt && sudo systemctl restart gunicorn
```

### 4. Test connection

```bash
cd /srv/app/gogevgelija-api && source venv/bin/activate && python3 -c "
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()
import sentry_sdk
sentry_sdk.capture_message('Sentry backend connected', level='info')
print('done')
"
```

If the message appears in Sentry Issues → connected. From now on every backend error lands there automatically.

---

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

## 0. Diagnose why assistant stopped working (run in order)

### Step 1 — test endpoint without token (fastest check)

```bash
curl -s -X POST https://admin.gogevgelija.com/api/assistant/query/ \
  -H "Content-Type: application/json" \
  -d '{"message": "hello"}' | python3 -m json.tool
```

Expected: JSON with `answer` field. If you get `429` → rate limit/fail2ban. If `500` → server error. If `{"detail": ...}` → auth issue.

### Step 2 — check gunicorn logs for errors

```bash
sudo journalctl -u gunicorn -n 100 --no-pager | grep -iE "assistant|Error|Exception|Traceback" | tail -50
```

### Step 3 — check if your IP is banned by fail2ban

```bash
fail2ban-client status nginx-limit-req
fail2ban-client status nginx-bad-host
```

If your IP is listed under "Banned IP list" — unban it:

```bash
fail2ban-client set nginx-limit-req unbanip <YOUR_IP>
```

### Step 4 — check nginx is returning 429 or 503 for assistant

```bash
curl -v -X POST https://admin.gogevgelija.com/api/assistant/query/ \
  -H "Content-Type: application/json" \
  -d '{"message": "hello"}' 2>&1 | grep -E "< HTTP|{|answer|detail"
```

### Step 5 — check what model/key is active on the server

```bash
cd /srv/app/gogevgelija-api && grep -E "OPENAI_API_KEY|ASSISTANT_OPENAI_MODEL" .env
```

### Step 6 — test OpenAI key directly

```bash
cd /srv/app/gogevgelija-api && curl -s https://api.openai.com/v1/models \
  -H "Authorization: Bearer $(grep OPENAI_API_KEY .env | cut -d'=' -f2 | tr -d ' \r\n')" | python3 -m json.tool | head -30
```

If you get `{"error": ...}` → key is invalid or quota exceeded.

### Step 7 — stream live logs while sending a test message

Open two terminals. Terminal 1:

```bash
sudo journalctl -u gunicorn -f
```

Terminal 2 (send request):

```bash
curl -s -X POST https://admin.gogevgelija.com/api/assistant/query/ \
  -H "Content-Type: application/json" \
  -d '{"message": "what hotels are in gevgelija"}' | python3 -m json.tool
```

Watch terminal 1 for tracebacks.

---

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
u = User.objects.get(email='dragana.petkova04@gmail.com')
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
u = User.objects.get(email='dragana.petkova04@gmail.com')
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

## Fix — Random Logouts (JWT Rotation Race Condition)

Production `.env` had rotation + blacklisting enabled with a 15-minute access token.
Every refresh invalidated the old refresh token — any in-flight request using the old token got a 401 → logged out.

### Step 1 — patch the env vars

```bash
sed -i 's/JWT_ROTATE_REFRESH_TOKENS=1/JWT_ROTATE_REFRESH_TOKENS=0/' /srv/app/gogevgelija-api/.env
sed -i 's/JWT_BLACKLIST_AFTER_ROTATION=1/JWT_BLACKLIST_AFTER_ROTATION=0/' /srv/app/gogevgelija-api/.env
sed -i 's/JWT_ACCESS_TOKEN_LIFETIME_MINUTES=15/JWT_ACCESS_TOKEN_LIFETIME_MINUTES=60/' /srv/app/gogevgelija-api/.env
```

### Step 2 — deploy and restart

```bash
cd /srv/app/gogevgelija-api && git pull && sudo systemctl restart gunicorn
```

### Step 3 — verify

```bash
cat /srv/app/gogevgelija-api/.env | grep JWT
```

Expected: `JWT_ROTATE_REFRESH_TOKENS=0`, `JWT_BLACKLIST_AFTER_ROTATION=0`, `JWT_ACCESS_TOKEN_LIFETIME_MINUTES=60`

sudo journalctl -u gunicorn --since "2026-05-08 22:00" --until "2026-05-09 09:00" --no-pager | grep -iE "401|token|blacklist|refresh" | tail -30

awk '/08\/May\/2026:22/,/09\/May\/2026:09/' /var/log/nginx/access.log | grep "token/refresh"

grep "193.36.90\|31.11.88\|31.11.82" /var/log/nginx/access.log | head -20

---

## Fix — Blacklisted Tokens Causing Overnight Logout

Even after disabling rotation, old blacklisted tokens from the previous system stay in the database.
When the phone switches networks overnight, the app refreshes from a new IP using a blacklisted token → 401 → logged out.

### Clear the blacklist (one time)

```bash
cd /srv/app/gogevgelija-api && source venv/bin/activate && python3 manage.py shell -c "
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken
count = BlacklistedToken.objects.count()
BlacklistedToken.objects.all().delete()
print(f'Cleared {count} blacklisted tokens')
"
```

After running this, log in fresh on the phone. With rotation disabled, the new token will never be blacklisted and stays valid for 30 days.

---

## Check all token statuses (read-only, changes nothing)

```bash
cd /srv/app/gogevgelija-api && source venv/bin/activate && python3 manage.py shell -c "
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from datetime import datetime, timezone

now = datetime.now(timezone.utc)
print(f'Total blacklisted: {BlacklistedToken.objects.count()}')
print()

for t in OutstandingToken.objects.all().order_by('user__email', '-created_at'):
    is_blacklisted = BlacklistedToken.objects.filter(token=t).exists()
    expired = t.expires_at < now
    status = 'BLACKLISTED' if is_blacklisted else ('EXPIRED' if expired else 'VALID')
    print(f'{status} | {t.user.email} | created: {t.created_at.strftime(\"%m-%d %H:%M\")} | expires: {t.expires_at.strftime(\"%m-%d %H:%M\")}')
"
```

Shows every token per user — VALID means safe, BLACKLISTED means next refresh will fail and log out, EXPIRED means token is past its lifetime.
