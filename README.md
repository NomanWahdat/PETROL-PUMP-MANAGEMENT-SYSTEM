# Petrol Pump Management System

One application for multiple Afghan fuel stations. Django REST Framework + PostgreSQL backend; React + TypeScript + Vite frontend. Dari and Pashto have RTL layouts; English is also available.

**Implemented scope: Prompts 1, 2 and 3.** Tenant/user/equipment configuration now connects to meter-based sales, shifts and nozzle assignments, supplier deliveries, tank/physical stock, credit customers/payments, cash movements, daily closing and printable receipts. Posting uses backend Decimal calculations, atomic tenant-scoped services, idempotency keys and preserved reversal history. The English, Dari and Pashto interfaces support LTR/RTL layouts. See [operational rules and APIs](docs/phase-3.md) and [configuration foundation](docs/phase-2.md).

## Project structure

```text
backend/
  config/                  Settings, URLs, WSGI/ASGI
  apps/
    common/                UUID/timestamp/tenant bases, health, errors
    accounts/              Custom user, CSRF, sessions, selection/password APIs
    tenants/               Membership, policies, platform administration
    employees/             Station-specific employee profiles and access
    stations/              Profile and configurable compliance records
    audit/                 Tenant audit events and platform audit history
    fuel/                  Products, price history, tanks, pumps, nozzles
    sales/ shifts/ inventory/ customers/ suppliers/ purchases/ cash/
                             Active operational domain models
    operations/              Posting services, coordinated APIs, idempotency
    expenses/ reports/       Reserved for Prompt 4
frontend/
  src/
    components/ layouts/ pages/ features/auth/ features/station/
    features/configuration/  Shared resource forms and permission controls
    features/operations/     Posting forms, worker meter entry and receipts
    services/ hooks/ i18n/ types/
docs/
  architecture.md          Domain boundaries and security conventions
  implementation-phases.md  Five-phase roadmap
  phase-2.md               Implemented roles, APIs and setup rules
  phase-3.md               Fuel, stock, cash, credit and closing rules/APIs
  final-audit.md           Review results and fixes across all 34 areas
  deployment.md            Installation, environment, deployment and limitations
deploy/                    Linux nginx, systemd and production env examples
scripts/                   Isolated database/browser verification helpers
.env.example               Shared development environment template
```

## Requirements and dependencies

- Python 3.12 recommended; Node 22.12+ LTS recommended; npm.
- PostgreSQL 14+ for production and PostgreSQL integration testing. SQLite is an explicit development fallback.
- Backend: Django 5.2 LTS, DRF 3.17.2, psycopg 3, dj-database-url, python-dotenv and Pillow for validated image processing. Gunicorn is installed on non-Windows systems for deployment.
- Frontend: React 19, React Router 7, Vite 6, TypeScript 5.8 and the Vite React plugin. Plain CSS; no component framework or charting library.
- Exact frontend versions are in `frontend/package-lock.json`; the tested Python environment is in `backend/requirements-lock.txt`. Install that lock for reproducible development. On Linux deployments additionally install `gunicorn>=23,<24` (the Windows-generated lock excludes it).

## Quick start (PowerShell, repository root)

This workspace has an ignored `.env` with a random development secret and SQLite enabled. Existing station accounts remain usable. A debug-only demo-account command is available below; it never runs automatically. For a fresh checkout, follow these installation steps. If `.venv` and dependencies already exist, skip installation.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements-lock.txt
Copy-Item .env.example .env   # Only for a fresh checkout; do not overwrite an existing .env.
```

For local SQLite, edit `.env`: clear `DATABASE_URL`, set `USE_SQLITE=true`, keep `DJANGO_DEBUG=true`. For PostgreSQL, use the database setup below. Generate a random secret for a fresh checkout with:

```powershell
.\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(64))"
```

Put the result in `DJANGO_SECRET_KEY`. Then:

```powershell
.\.venv\Scripts\python.exe backend\manage.py migrate
.\.venv\Scripts\python.exe backend\manage.py provision_station --name "Ahmad Fuel Station" --slug ahmad --username ahmad --language fa
.\.venv\Scripts\python.exe backend\manage.py runserver 127.0.0.1:8000
```

Provisioning securely prompts for the owner's password twice and creates the tenant, station, user, owner membership and employee profile in one database transaction. Repeat with a different station slug and username for another client, or create tenants through the Super Admin interface. There is no public registration endpoint.

In a second terminal:

```powershell
Set-Location frontend
npm.cmd ci
npm.cmd run dev
```

Open `http://127.0.0.1:5173` and sign in with the owner created above. Use one consistent hostname for the frontend. Vite proxies `/api` to Django, including session and CSRF cookies. On PowerShell use `npm.cmd` when execution policy blocks `npm.ps1`; changing the machine execution policy is unnecessary.

For development test credentials in a separate station, run once with debug enabled:

```powershell
.\.venv\Scripts\python.exe backend\manage.py create_demo_users
```

The initial password is `PetrolDemo2026!` for `demo-owner`, `demo-manager`, `demo-worker`, `demo-accountant` and `demo-superadmin`. These logins are already created in this workspace's local development database. The platform account has no automatic station access. The account command refuses production mode/collisions and never changes existing passwords; it adds no sample transactions. See [development credentials](docs/deployment.md#development-credentials).

Sample equipment and transactions are also available through the separate debug-only command:

```powershell
.\.venv\Scripts\python.exe backend\manage.py seed_demo_data
```

Sample data is already loaded in this workspace's **Development Demo Station**, including a logo, two products/tanks/pumps/nozzles, two suppliers/customers, one delivery, two sales, one payment and two shifts (one open for `demo-worker`). Re-running the command adds nothing. The existing Ahmad station and all passwords were preserved. Sample data never loads automatically or in production.

The UI uses light station workspaces, a fuel-station login illustration, dashboard watermarks and translated instructions for each role. Owners upload logos in station settings; Super Admin uploads them while editing a station. Share `/login?station=STATION_SLUG` for that station's branded login. Returning browsers remember the last station's code. Only the station name/color/logo are public; authentication and tenant isolation still protect operational data. See [branding and dashboard guide](docs/ui-branding.md).

Optional system administrator (separate from station ownership):

```powershell
.\.venv\Scripts\python.exe backend\manage.py createsuperuser
```

Django admin is at `http://127.0.0.1:8000/admin/` and manages global user accounts only. Sign into the React application as a superuser for the tenant, system-user and platform-audit pages. Station access still requires an active membership; use the system-user assignment form to assign an existing user. A user belonging to several stations chooses a station after login. A superuser starts in the platform area and can select an explicitly assigned station.

## PostgreSQL database setup

Run `psql -U postgres -h localhost` (or the absolute path to `psql.exe` if it is not on PATH), then:

```sql
CREATE ROLE petrol LOGIN;
\password petrol
CREATE DATABASE petrol_station OWNER petrol;
```

Set `.env`:

```dotenv
DATABASE_URL=postgresql://petrol:YOUR_URL_ENCODED_PASSWORD@localhost:5432/petrol_station
USE_SQLITE=false
```

URL-encode special characters in the password. For hosted PostgreSQL append `?sslmode=require` or the provider's certificate-verification options. Then run `backend\manage.py migrate` with the virtual-environment Python as above. Production never falls back to SQLite.

The Django test runner creates a separate test database. Use a dedicated local test role with `CREATEDB`; do not give the production application role that privilege:

```sql
CREATE ROLE petrol_test LOGIN CREATEDB;
\password petrol_test
CREATE DATABASE petrol_station_test_base OWNER petrol_test;
```

In your test shell set `DATABASE_URL` to that test database, then run the tests below. Django creates/drops `test_petrol_station_test_base`; it does not use your production data.

## Environment variables

| Variable | Purpose |
| --- | --- |
| `DJANGO_SECRET_KEY` | Required; random secret, at least 50 characters in production |
| `DJANGO_DEBUG` | Local development only; production `false` |
| `DATABASE_URL` | PostgreSQL connection URL; takes precedence over SQLite |
| `USE_SQLITE` | Explicit local fallback, allowed only with debug enabled |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated backend hostnames |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Exact trusted frontend origins, including scheme |
| `DJANGO_TIME_ZONE` | Defaults to `Asia/Kabul` |
| `DJANGO_SECURE_SSL_REDIRECT` | Defaults to `true` outside debug |
| `DJANGO_TRUST_PROXY_SSL` | Enable only behind a trusted proxy that sanitizes forwarded headers |
| `DJANGO_NUM_PROXIES` | Default `0`; use `1` only behind the documented proxy which overwrites forwarded IPs |
| `DJANGO_CACHE_BACKEND` | Debug default `locmem`; production requires/defaults to shared `database` |
| `DJANGO_CACHE_LOCATION` | Namespace/table name; production example `petrol_cache`, created with `createcachetable` |
| `VITE_API_BASE_URL` | Defaults to `/api/v1`; public build-time value, never a secret |
| `VITE_DEV_API_TARGET` | Local Vite proxy target; defaults to `http://127.0.0.1:8000` |

Only `VITE_` values are exposed to the frontend. Secrets remain on the backend.

## Verification

```powershell
.\.venv\Scripts\python.exe backend\manage.py check
.\.venv\Scripts\python.exe backend\manage.py makemigrations --check --dry-run
Set-Location backend
..\.venv\Scripts\python.exe manage.py test --noinput
Set-Location ..
Set-Location frontend
npm.cmd test
npm.cmd run build
```

Tests cover CSRF, secure session handling, invalid/disabled logins, tenant switching, password changes, throttling, cross-tenant lists/details/writes/relations, role policies, employee access, private logo validation, decimal price history and database integrity. Run the same suite against PostgreSQL before deployment. The liveness and database readiness endpoints are `/api/v1/health/` and `/api/v1/ready/`.

The current suite passes all 136 tests on PostgreSQL 14; SQLite passes 128 and skips eight PostgreSQL-only concurrency/import tests. Frontend/translation checks, migrations, production cache/static checks and Chrome setup/fuel/mobile/tablet/receipt/closing flows pass. The translation catalogs contain 324 matching keys. The actual current-data snapshot also passed a field-by-field PostgreSQL transfer rehearsal, with all logo bytes preserved and only clone platform-admin passwords rotated. The patched dependencies report no known vulnerabilities in the audit snapshot. See [final review](docs/final-audit.md), [verification details and limits](docs/verification.md) and [cloud demo deployment](docs/cloud-demo-deployment.md).

## Deployment preparation

For the current demo, use [Vercel frontend + Render backend + Neon data/logos](docs/cloud-demo-deployment.md). Root `render.yaml` and `frontend/vercel.mjs` are prepared; no paid disk is needed because `DJANGO_LOGO_STORAGE=database` keeps small logos in PostgreSQL. The current local data is in a private ignored transfer bundle, with a guarded one-time import and mandatory private Super Admin passwords. Never commit that bundle or `.env`. The existing VPS instructions/templates remain below and in [deployment.md](docs/deployment.md).

Keep frontend deployment and backend hosting separate from business logic. Prefer a **same-origin HTTPS reverse proxy**: `/api/v1/*` routes to Django and all other application routes serve the React build. A Vercel frontend with a Railway/Render backend can use this pattern; configure session/CSRF forwarding and browser-route fallback at deployment time. Unrelated frontend/backend domains require a deliberate authentication/CORS/cookie design; simply changing the API URL is insufficient.

Set debug off, configure hosts/origins and the shared database cache, then run migrations, `createcachetable`, `collectstatic` and `check --deploy`. Serve Django through a production server. Production secrets, backups, PostgreSQL credentials, ingress limits, TLS and hosting rules must be configured for the chosen platform. [The deployment guide](docs/deployment.md) provides concrete Linux instructions and templates in `deploy/`. No site was deployed.

## Next phase

Prompt 4 adds supplier-payment/statement workflows, expenses, accounting reports/exports, costing/profit and broader audit history. Verified-email password recovery, production infrastructure, durable offline handling and hardware integration still require further work. Use PostgreSQL for real financial posting; SQLite is a debug-only development fallback. See [operational setup](docs/phase-3.md), [the five-phase plan](docs/implementation-phases.md) and [architecture](docs/architecture.md).
