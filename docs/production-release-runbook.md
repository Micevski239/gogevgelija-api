# Production Release Runbook

This checklist is the release gate for each production update. Complete it before shipping an API deploy, Expo/EAS mobile build, or store update.

## Required Evidence

- GitHub CI is green for the exact API commit being deployed.
- Android production build succeeded in EAS.
- iOS production build succeeded in EAS.
- Production API environment variables are configured outside git.
- OpenAI/API/storage/database keys have been rotated after any suspected exposure.
- DigitalOcean Managed Database automatic backups are enabled.
- A restore point or backup timestamp exists before the release.
- A rollback path is identified before deployment starts.
- Post-deploy smoke tests pass.

## Pre-Deploy Checks

1. Confirm API checks pass:

   ```bash
   python manage.py check --deploy
   python manage.py test core.tests
   ```

2. Confirm mobile checks pass:

   ```bash
   npm run typecheck
   npx jest --runInBand --no-watchman
   ```

3. Confirm secrets are not tracked:

   ```bash
   git grep -n "OPENAI_API_KEY\\|SECRET_KEY\\|DATABASE_URL\\|REDIS_URL\\|AWS_SECRET_ACCESS_KEY"
   git ls-files .env .env.* db.sqlite3 staticfiles media
   ```

4. Confirm production config:

   - `DJANGO_DEBUG=0`
   - `DJANGO_SECRET_KEY` set in DigitalOcean environment
   - `DATABASE_URL` set in DigitalOcean environment
   - `REDIS_URL` set in DigitalOcean environment
   - `ALLOWED_HOSTS` includes only production hosts
   - `CORS_ALLOWED_ORIGINS` includes only approved origins
   - Spaces credentials are set only in DigitalOcean secrets

## DigitalOcean Backup Check

Before deployment:

1. Open DigitalOcean Managed Database.
2. Confirm automated backups are enabled.
3. Record the latest backup timestamp.
4. Confirm the retention window is acceptable for the release.
5. If the release includes risky migrations, create a manual backup/snapshot first.

## Deployment

1. Deploy API through the GitHub/DigitalOcean workflow.
2. Watch deploy logs until the app is healthy.
3. Run migrations only once per release.
4. Do not deploy mobile binaries until the API is healthy.
5. Submit Android/iOS builds only after API smoke tests pass.

## Post-Deploy Smoke Tests

Run these against production:

- Health/admin login page loads over HTTPS.
- Login email code request works.
- Verification code login works.
- Guest login works.
- Home screen loads sections.
- Listings, events, promotions, blogs load read-only for anonymous users.
- Anonymous POST/PUT/PATCH/DELETE against public content endpoints returns `401`, `403`, or `405`.
- Wishlist requires authenticated non-guest user.
- Search returns capped results and rejects invalid limits.
- Assistant returns a safe response for a normal query.
- Assistant rejects overly large history payloads.
- File upload rejects unsupported MIME types and files over 10 MB.
- Macedonian and English language switch renders without raw translation keys.

## Rollback

API rollback options, in order:

1. Redeploy the previous healthy DigitalOcean deployment if available.
2. Revert the release commit and redeploy through GitHub.
3. If a migration caused data damage, restore from the recorded Managed Database backup.

Mobile rollback options:

1. If using Expo Updates, publish a fixed OTA update only for JS-safe changes.
2. If native/runtime config changed, submit a new store build.
3. If a store release is bad, pause staged rollout in Google Play/App Store Connect.

Rollback decision rule:

- Roll back immediately for auth failures, data loss, admin exposure, broken app startup, or production API 5xx spikes.
- Fix forward only for isolated UI copy issues or non-critical visual defects.

## Recovery Notes

- Keep the previous API commit SHA and build IDs in the release notes.
- Keep the backup timestamp in the release notes.
- Keep screenshots or links proving Android, iOS, and CI success.
- If monitoring is intentionally not implemented, manually check logs immediately after deploy and again after peak usage.
