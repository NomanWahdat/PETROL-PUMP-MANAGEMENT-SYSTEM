# Demo deployment: Vercel + Render + Neon

This guide publishes the existing React frontend on Vercel, Django API on Render and PostgreSQL records **including station logos** on Neon. No Render disk, Cloudflare account or Supabase service is required. The separate [VPS deployment](deployment.md#linux-production-setup) and `deploy/nginx.conf.example` / `deploy/petrol.service.example` remain available for later use.

The source repository is `https://github.com/NomanWahdat/PETROL-PUMP-MANAGEMENT-SYSTEM`. Upload source code only. `.env`, SQLite, uploaded files and `.deployment-data/` are ignored. The transfer ZIP contains private station records and password hashes and must never be uploaded to GitHub, Vercel public files or a public download URL.

## Hosting plan limits

The Render Blueprint uses a **free** Python web service and Neon can supply the demo PostgreSQL database. Free Render services sleep after 15 minutes without inbound traffic and have ephemeral local files. Logos use database storage so uploads survive redeploys/restarts. Neon may suspend idle compute and has plan-specific storage/usage limits; small logos count toward that database storage. Slow startup can require the user to retry a request; retained submission keys prevent a duplicate transaction.

Vercel Hobby is restricted to personal, non-commercial use. A software-house sales demonstration is commercial usage, so check Vercel's terms and use an appropriate plan; this particular three-provider setup cannot be promised to be entirely free for your business. This does not change the supplied deployment configuration. See [Vercel fair use](https://vercel.com/docs/limits/fair-use-guidelines), [Render free limits](https://render.com/docs/free), [Neon plans](https://neon.com/docs/introduction/plans).

## 1. Create a fresh Neon demo database

1. Create a Neon account/project and choose a region near the Render service.
2. Use a new empty database dedicated to this demo. Do not select an existing client's database.
3. In **Connect**, select the database/role, turn connection pooling **off** for the one-time import, and copy the direct PostgreSQL URL. Keep its TLS parameters (such as `sslmode=require`). Never paste this URL into chat or source files.

The local importer deliberately accepts only a direct `.neon.tech` database URL with TLS and refuses any nonempty schema. Use the pooled URL for Render later if desired. Migrations/import/backup use direct connections. See [Neon connection pooling](https://neon.com/docs/connect/connection-pooling).

## 2. Move the current local data privately

A current snapshot has been prepared at `.deployment-data/current-demo-2026-10-13.zip`. It contains the users, stations, memberships, configuration, financial/stock/meter/shift records, audit/idempotency history and referenced logos. Browser sessions, caches and generated Django permissions/content types are not copied. No local passwords or records were changed by exporting.

If you made more local changes after that snapshot, pause editing and create a **new filename**:

```powershell
.\.venv\Scripts\python.exe backend\manage.py export_deployment_data .deployment-data\updated-demo.zip
```

From this Windows workspace, run:

```powershell
.\.venv\Scripts\python.exe scripts\import_to_neon.py .deployment-data\current-demo-2026-10-13.zip
```

The script prompts for the Neon direct connection string with input hidden. It verifies the bundle checksums and an empty database, then asks you to type `IMPORT`. It applies all migrations, creates the shared cache table and imports data/logos in one transaction. Schema setup precedes the data transaction; a failed data import may leave empty migrated tables but does not leave partial business data. Do not use the fresh-database launcher again in that case; correct the cause and use the management import command under the same target environment.

It prompts for a **new private password for every imported Super Admin**, including `demo-superadmin`. The published development administrator password is rejected. All other user password hashes, IDs, roles, timestamps and transaction values are preserved. Keep the new platform password private; share only station demo credentials with clients.

This process does not edit your local `.env` or SQLite database. The ZIP remains local and ignored. Keep a secure copy until import verification is complete. Subsequent online changes exist in Neon, independently of the local development database; Git pushes never overwrite the online data.

For an already-migrated but empty PostgreSQL target, the lower-level command is `python backend/manage.py import_deployment_data PRIVATE_BUNDLE.zip --confirm-empty-target`, with the target environment configured and `DJANGO_LOGO_STORAGE=database`. It also prompts for platform passwords, refuses any existing application data, verifies relationships and rolls back on errors. Never use `flush` against a deployed database.

## 3. Deploy the backend on Render

Connect Render to GitHub and choose this repository. Either create a **Blueprint** using root `render.yaml` or create a Python **Web Service** manually:

| Setting | Value |
| --- | --- |
| Branch | `main` |
| Root Directory | Leave empty (repository root) |
| Runtime | Python |
| Instance plan | Free |
| Build Command | `bash deploy/render-build.sh` |
| Start Command | `bash deploy/render-start.sh` |
| Health Check | `/api/v1/ready/` |

The root `.python-version` selects the latest available Python 3.12 patch. The build installs pinned backend dependencies/Gunicorn and collects admin static files. Startup migrates schema, creates the cache table, runs production checks and starts Gunicorn. It never seeds/imports data automatically. WhiteNoise serves collected static files; uploaded logos are served by their scoped/public-branding API, never WhiteNoise.

Set these Render environment variables (see `deploy/render.env.example`):

| Variable | Value |
| --- | --- |
| `DATABASE_URL` | The SAME Neon database imported in step 2; SSL required; pooled URL is suitable for runtime |
| `DJANGO_SECRET_KEY` | A new private random secret of at least 50 characters |
| `DJANGO_DEBUG` | `false` |
| `USE_SQLITE` | `false` |
| `DJANGO_LOGO_STORAGE` | `database` |
| `DJANGO_CACHE_BACKEND` | `database` |
| `DJANGO_CACHE_LOCATION` | `petrol_cache` |
| `DJANGO_TRUST_PROXY_SSL` | `true` for Render's HTTPS ingress |
| `DJANGO_NUM_PROXIES` | `0` (conservative default; do not guess proxy-chain lengths) |
| `DJANGO_DISABLE_SERVER_SIDE_CURSORS` | `true` |
| `DJANGO_TIME_ZONE` | `Asia/Kabul` |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Exact HTTPS Vercel production origin after step 4; initially leave empty if the frontend URL is not assigned |

Generate the secret locally with `.\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(64))"` and enter it directly in Render settings. Keep it stable across redeploys. Render's standard generated 256-bit environment secret can be shorter than this app's 50-character minimum; use the command above.

The start script defaults `DJANGO_ALLOWED_HOSTS` to Render's `RENDER_EXTERNAL_HOSTNAME`. Once both URLs are assigned, explicitly set it to `YOUR-SERVICE.onrender.com,YOUR-PROJECT.vercel.app`. Do not add schemes or wildcard domains. Render's free service does not provide the paid persistent-disk/shell features; the local-to-Neon importer avoids needing a Render shell or file upload.

Deploy and record the actual HTTPS `onrender.com` URL. Open `/api/v1/health/` and `/api/v1/ready/`; both should succeed. See [Render Django hosting](https://render.com/docs/deploy-django) and [Python selection](https://render.com/docs/python-version).

## 4. Deploy the frontend on Vercel

1. Import the same GitHub repository into Vercel.
2. Set **Root Directory = `frontend`**, framework **Vite**, build **`npm run build`**, output **`dist`** and install **`npm ci`**. Use supported Node 22 LTS or newer compatible LTS.
3. Set `VITE_API_BASE_URL=/api/v1`. The static `frontend/vercel.json` points to the deployed `https://petrol-pump-demo-api.onrender.com` backend. If that service URL changes, update the external route destination in that file and push the change before deploying. Select the production environment; preview deployments need their own intentionally configured backend/origin. The previously documented `RENDER_BACKEND_URL` variable is no longer used and can be removed.
4. Deploy. Record the actual stable production `vercel.app` URL.
5. Update Render's `DJANGO_CSRF_TRUSTED_ORIGINS=https://YOUR-ACTUAL-PROJECT.vercel.app` and allowed hosts as above; save/redeploy the backend.

`frontend/vercel.json` declares ordered native routes: `/api`, `/admin` and `/static` proxy to Render before filesystem serving and the SPA fallback. The regex captures the complete path, including Django's required trailing slash. The earlier `:path*` high-level rewrites routed slashless requests but allowed trailing-slash API requests to fall through to `index.html` on the deployed site. The browser accesses APIs/logos through the **Vercel origin**, preserving host-only session/CSRF cookies. `/media` is forwarded to the backend's 404 route, not exposed as public files. API/admin responses use `no-store`. No Supabase Auth, CORS package or cross-site cookie rewrite is introduced. Keep `VITE_API_BASE_URL=/api/v1`; setting it directly to Render would bypass this design.

The static config replaces the earlier dynamic `.mjs` file after Vercel's new-project importer rejected an unresolved rewrite destination. It includes literal destination URLs, requiring no configuration-time environment evaluation or additional package. See [static configuration](https://vercel.com/docs/project-configuration/vercel-json) and [external rewrites](https://vercel.com/docs/routing/rewrites). Secrets/database URLs belong only in Render or the private import prompt, never Vercel's `VITE_` variables.

## 5. Verify and share the demo

- Through Vercel, open `/api/v1/health/`, `/api/v1/ready/` and `/login?station=development-demo`.
- Sign in with existing station demo accounts. Verify current station/product/customer/transaction data and balances against the local snapshot.
- Sign in as `demo-superadmin` with the new private password; verify the original stations/users/memberships and upload a logo.
- Confirm logos survive a Render redeploy, worker management access is denied, station switching remains scoped, CSRF posting/logout work, and English/Dari/Pashto receipts render/print.
- Share station credentials and branded login links with clients. Do not share platform-admin access or the transfer ZIP.

Data lives in **Neon**, including PNG logos in `stations_stationlogo`; Vercel stores frontend build assets; Render runs Django and collects disposable static assets. This database-logo option is for a small demo, with a 2 MB decoded PNG limit. For larger deployments, keep the VPS file option or add object storage later.

## Later updates and VPS migration

Push reviewed code to `main`; connected providers can rebuild/redeploy. Render applies new migrations and preserves the Neon records. Do not rerun the one-time importer or demo seed commands during releases. Back up Neon and verify recovery before schema changes.

The existing VPS guide, systemd/nginx templates and production env example are retained. `DJANGO_LOGO_STORAGE=file` remains the local/VPS default; `DJANGO_MEDIA_ROOT` can point to persistent storage. The same transfer format can export online records/logos and import them into a new VPS PostgreSQL database with file storage. A standard PostgreSQL backup can also preserve database-backed logos.

No cloud service has been created or publicly deployed by preparing these files. Provider account setup, Neon credentials, actual service URLs and live HTTPS/cookie checks are still required. Local checks and PostgreSQL transfer tests do not establish that the provider deployment is configured correctly.
