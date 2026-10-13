# Installation and production deployment

The application implements configuration and fuel operations (Prompts 1–3). It has not been deployed to a public server. The templates in `deploy/` describe one conventional Linux deployment with PostgreSQL, Gunicorn, nginx and HTTPS; they are examples to adapt, not a hosting requirement. Existing working development instructions are in [README](../README.md).

The separate [Vercel/Render/Neon demo guide](cloud-demo-deployment.md) retains this VPS setup and explains how to transfer the current data privately. Small demo logos can use `DJANGO_LOGO_STORAGE=database`; file storage remains the default for this guide, optionally placed under `DJANGO_MEDIA_ROOT`. WhiteNoise also serves collected Django static files when nginx does not handle them. PostgreSQL defaults to disabled server-side cursors for transaction-pooler compatibility; `DJANGO_DISABLE_SERVER_SIDE_CURSORS` controls that setting.

## Local installation

Use Python 3.12, a supported Node LTS release (22.12 or newer), npm and PostgreSQL. From a fresh Windows checkout:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements-lock.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(64))"
```

Copy the generated secret into `.env`. Do not overwrite an existing environment or database. The template defaults to PostgreSQL. In `psql` as a database administrator:

```sql
CREATE ROLE petrol LOGIN;
\password petrol
CREATE DATABASE petrol_station OWNER petrol;
```

Set `DATABASE_URL=postgresql://petrol:URL_ENCODED_PASSWORD@127.0.0.1:5432/petrol_station`. The production role does not need `CREATEDB`. For a disposable development database only, clear `DATABASE_URL`, set `USE_SQLITE=true` and keep `DJANGO_DEBUG=true`; SQLite cannot provide exact PostgreSQL numeric storage or row-lock concurrency.

```powershell
.\.venv\Scripts\python.exe backend\manage.py migrate
.\.venv\Scripts\python.exe backend\manage.py create_demo_users
.\.venv\Scripts\python.exe backend\manage.py runserver 127.0.0.1:8000
```

In a second terminal:

```powershell
Set-Location frontend
npm.cmd ci
npm.cmd run dev
```

Open `http://127.0.0.1:5173`. Linux equivalents use `.venv/bin/python` and `npm`. Use the same browser hostname consistently for session/CSRF cookies. To create a real initial owner instead of demo accounts, use the existing `provision_station` command, which prompts securely for the password. `createsuperuser` creates a platform administrator separately.

## Development credentials

`create_demo_users` explicitly creates a separate **Development Demo Station** and these initial logins:

| Username | Role |
| --- | --- |
| `demo-owner` | Tenant owner |
| `demo-manager` | Manager |
| `demo-worker` | Worker/attendant |
| `demo-accountant` | Accountant |
| `demo-superadmin` | Platform Super Admin; no automatic station membership |

The initial development-only password for all five is **`PetrolDemo2026!`**. The account command refuses to run with debug disabled, refuses existing usernames/station slugs, and never resets existing accounts. It adds no fuel configuration or transactions. The separate `seed_demo_data` command populates only that demo station with sample equipment, transactions and a logo; it refuses production, protects existing equipment and prevents repeated seeding. Both commands have already run in this workspace's local SQLite database. See [sample contents and branding](ui-branding.md). These public credentials must never be provisioned into a production database. A fresh production database should be provisioned with private owner/admin credentials.

## Environment reference

| Variable | Development / production behavior |
| --- | --- |
| `DJANGO_SECRET_KEY` | Required; random and private, at least 50 characters outside debug |
| `DJANGO_DEBUG` | `true` locally; `false` in production |
| `DATABASE_URL` | PostgreSQL URL; takes precedence over the SQLite flag. URL-encode credentials; use the database provider's TLS/certificate options when remote |
| `USE_SQLITE` | Explicit debug-only fallback when the URL is empty |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated hosts, without schemes or paths |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Comma-separated exact trusted origins with scheme; no wildcard recommendation |
| `DJANGO_TIME_ZONE` | Global default `Asia/Kabul`; station-specific timezone governs operating days |
| `DJANGO_SECURE_SSL_REDIRECT` | Defaults on in production; keep enabled for this template |
| `DJANGO_TRUST_PROXY_SSL` | `false` by default; set `true` only when the trusted proxy overwrites forwarded protocol |
| `DJANGO_NUM_PROXIES` | Default `0`: ignore forwarded IPs for login throttling. Set `1` only for the documented single proxy which overwrites `X-Forwarded-For` |
| `DJANGO_CACHE_BACKEND` | `locmem` defaults in debug; `database` defaults in production. Production rejects `locmem` |
| `DJANGO_CACHE_LOCATION` | Local cache namespace or database table name (`petrol_cache` in production). Run `createcachetable` for database caching |
| `VITE_API_BASE_URL` | Public build-time frontend value; `/api/v1` for same-origin deployment |
| `VITE_DEV_API_TARGET` | Development proxy target, default `http://127.0.0.1:8000`; unused by production nginx |

Only `VITE_` values go into the frontend. The backend loads root `.env` without overriding already-provided environment variables. For deployment, use a restricted environment file such as `/etc/petrol.env` based on `deploy/production.env.example`; do not copy a debug `.env` into production. The Django upload limit is 3 MB and logos are limited to 2 MB/2048 pixels; nginx applies a matching overall body limit.

## Linux production setup

1. Install Python/venv support, Node/npm, PostgreSQL (or use a managed database), nginx and a valid TLS certificate for the actual domain. Use an unprivileged service user, for example `petrol`, and place the checkout at `/srv/petrol`. Configure a default nginx host that rejects unrecognized hostnames, adapting any existing host configuration.
2. Create the production database/role as above. Limit database access to the app/server network. Store real secrets in `/etc/petrol.env`, restrict its permissions, and replace every placeholder in the production environment and proxy/service templates. Set `DJANGO_DEBUG=false`, PostgreSQL URL, hosts/origins and the shared database cache. The service can read the file through systemd; use equivalent environment injection for one-off management commands.
3. Install dependencies and prepare the application under the same production environment:

```bash
cd /srv/petrol
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements-lock.txt
.venv/bin/python -m pip install 'gunicorn>=23,<24'
# In a trusted operator shell, load the administrator-created environment file.
set -a
. /etc/petrol.env
set +a
.venv/bin/python backend/manage.py migrate --noinput
.venv/bin/python backend/manage.py createcachetable
.venv/bin/python backend/manage.py collectstatic --noinput
.venv/bin/python backend/manage.py check --deploy
.venv/bin/python backend/manage.py provision_station --name "Your Station" --slug your-station --username your-owner --language fa
.venv/bin/python backend/manage.py createsuperuser
cd frontend
npm ci
npm run build
```

The lock file was generated on Windows and excludes Gunicorn, so its separate installation is intentional. Set `VITE_API_BASE_URL=/api/v1` in the frontend build environment. Do not place backend secrets in frontend files. Configure credentials in the environment file rather than passing passwords in shell arguments. The prompted provisioning commands are first-install operations; do not repeat them during ordinary releases.

4. Adapt `deploy/petrol.service.example` to the actual checkout/user, install it as `/etc/systemd/system/petrol.service`, and enable/start it with `systemctl daemon-reload` and `systemctl enable --now petrol`. Gunicorn binds to loopback only. Keep `backend/media/` persistent and readable/writable by the service user; logos use generated paths and are served only through validated API routes, including the intentional public branding route. Static files and frontend `dist/` must be readable by nginx. Do not use Django's development server or Vite's preview server for production.
5. Adapt `deploy/nginx.conf.example`, enable it, run `nginx -t`, then reload nginx. The reverse proxy serves the React route fallback, routes API/admin requests to Django, serves collected admin static files and blocks public `/media/`. It overwrites forwarded protocol/IP headers; the backend must not be directly reachable from the internet. The exact certificate paths depend on your TLS installation.
6. Check `/api/v1/health/` and `/api/v1/ready/` through HTTPS. Test login, CSRF-protected posting, logout, a worker's denied management access, scoped logo uploads, public login branding, station switching, RTL and receipt printing with disposable validation data. Confirm secure session/CSRF cookie flags at the public URL.

The database cache shares DRF login-throttle history across workers. DRF throttling is approximate and does not provide a hard concurrent rate limit; the proxy additionally limits login requests. Behind additional proxies, change the trust configuration only after confirming who sanitizes forwarded headers. See [DRF throttling](https://www.django-rest-framework.org/api-guide/throttling/) and [Django database caching](https://docs.djangoproject.com/en/5.2/topics/cache/#database-caching).

## Releases, backups and maintenance

Back up PostgreSQL and stored logos together and test restoration to a separate database. Before a release, run the PostgreSQL suite against a disposable test role/database, build the frontend, inspect migrations and back up production. Apply migrations once, rebuild/copy frontend assets, collect static files and restart the service. Do not run tests against the production role: the test runner needs a separate `CREATEDB` role.

Preserve the production secret, media files and database across releases. Keep the previous release and its assets until a new release is verified; a code rollback may not reverse a database migration safely. Review service/proxy logs without collecting passwords or entire request bodies, monitor database readiness, and periodically run `manage.py clearsessions`. Database-cache expiry is handled by Django's cache backend. Keep pinned dependencies under vulnerability review.

Use [Django's deployment checklist](https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/) to verify the actual host. Local production settings/cache/static checks passed, but the nginx/systemd templates require validation on the chosen Linux host. TLS, backup restoration and real thermal-printer output have not been verified on a production system.

## Limitations and future work

Current reports are transaction lists, stock views and saved daily-closing summaries. Expenses, supplier payments/statements, double-entry accounting, costing/profit, accounting exports and a tenant audit-log browser remain for Prompt 4. Transactions are API-immutable and audited, but privileged database administrators can still modify database records; this application does not implement database row-level security or tamper-evident audit storage.

Poor-network forms retain values and submission keys while mounted; durable recovery after refresh, offline sync and cross-tab station-context coordination remain future work. One station's writes serialize on its tenant row for correctness; heavy deployments require measured throughput testing before changing that design. Reference selectors load station choices and may need search-based loading for very large station inventories.

Dari/Pashto catalogs are complete and browser RTL layouts passed; native-speaker terminology review remains. Gregorian dates are used. Browser receipts support 58/80 mm layouts; select the matching paper and disable browser headers/footers in the print dialog. Direct ESC/POS/dispenser integration, general meter resets/rollovers, price changes within an active assignment, arbitrary historical backdating and currency conversion are not implemented. Self-service email password recovery, MFA and additional ingress monitoring are sensible later security work.
