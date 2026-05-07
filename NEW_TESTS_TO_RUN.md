# New Tests — Run on Server

After deploying, run these new test classes:

```bash
cd /var/www/gogevgelija-api
source venv/bin/activate
python manage.py test \
  core.tests.SearchLimitCapTests \
  core.tests.SupportEndpointPermissionTests \
  core.tests.AuthEmailFlowTests \
  --verbosity=2
```

## What each class tests

| Class | What it verifies |
|-------|-----------------|
| `SearchLimitCapTests` | `?limit=99999`, `?limit=abc`, `?limit=0` all return non-500 |
| `SupportEndpointPermissionTests` | Anonymous POST to `/api/help-support/` and `/api/collaboration-contact/` returns 401/403 |
| `AuthEmailFlowTests` | `/api/auth/send-code/` rejects missing/invalid email (400); `/api/auth/verify-code/` rejects missing code (400) |

## Full test suite (run all at once)

```bash
python manage.py test core.tests --verbosity=2
```
