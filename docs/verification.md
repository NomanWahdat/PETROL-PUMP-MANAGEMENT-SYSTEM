# Final application verification (implemented Prompts 1–3)

Audit verified on 12 October 2026; UI/branding and sample-data verification updated 13 October 2026. Environment: Python 3.12.6, Node 23.3.0, Django 5.2.18, DRF 3.17.2, PostgreSQL 14 and Vite 6.4.4. Use a supported Node LTS release for development/deployment.

| Check | Result |
| --- | --- |
| Django system checks | Passed, zero issues |
| All migrations on local SQLite | Passed |
| All migrations on isolated PostgreSQL 14 | Passed |
| Pending migration check | No changes detected |
| Django test suite on SQLite | 128 tests passed; 8 PostgreSQL-only concurrency/import tests skipped |
| Same test suite on PostgreSQL 14 | All 136 tests passed, including concurrent posting/reversal/closing and deployment import |
| Django `check --deploy` with production flags and a random secret | Passed, zero issues |
| TypeScript and Vite production build | Passed; 74 modules, approximately 124 KB gzipped JavaScript |
| Translation catalogs | `npm test` passes; 324 matching, non-empty, unique English/Dari/Pashto keys |
| Dependency audit | npm and Python locks report no known vulnerabilities after DRF security upgrade; Gunicorn 23.0.0 separately checked |
| Production cache/static files | Shared PostgreSQL cache read/write and `collectstatic` pass |
| Live frontend route serving | `/login` and `/account` served React entry point with browser HTML headers |
| Vite proxy → Django → PostgreSQL | Health/readiness, CSRF fetch, login, identity, station lookup and logout passed |
| Live isolation/security checks | Anonymous access rejected, login without CSRF rejected, forged tenant query ignored, logout invalidated session, login/logout audit events persisted |
| Chrome rendered platform flow | Login and station/initial-owner creation persisted through Vite/API/PostgreSQL |
| Chrome rendered owner flow | Product prices/history, tanks, pumps, nozzles, employee creation and station settings/branding persisted |
| Chrome localization | English/Dari/Pashto headings and LTR/RTL direction checked |
| Chrome mobile/tablet forms | Owner empty states/forms at 390, 768 and 1024 pixels in all languages; no horizontal overflow |
| Chrome worker flow | Three navigation links, management routes/API denied, mobile RTL width without horizontal overflow |
| Chrome accountant flow | Read-only product table, no create/edit buttons |
| Chrome fuel operation flow | Supplier/customer creation, delivery, cash funding, attendant shift, split cash/bank/credit sale and collection persisted |
| Chrome stock and closing flow | Final meters/cash handover, physical variance/explicit adjustment and daily closing persisted |
| Chrome receipts | Sale/payment receipts rendered; 58/80 mm columns fit printable margins in all three languages; PDF printing succeeds and navigation is hidden |
| PostgreSQL concurrency | Sale retries/intervals, shift starts, sale reversals and daily cash reconciliation cannot post twice |
| Query growth regressions | Customer and shift list query counts remain flat when adding rows/assignments |
| Development credentials | Five demo logins authenticate in a separate local station; command refuses production/collisions |
| Station branding/UI | Owner and platform upload forms persist sanitized logos; branded public login, watermark and five role guides checked at 390/768/1366 px in all languages |
| Sample data | Debug-only scoped/repeat-safe seeder creates balanced operations through existing services; original station/passwords preserved |
| Cloud demo preparation | Native Vercel proxy/SPA config checked; Render production checks and WhiteNoise admin CSS pass; Neon-compatible database PNG storage tested |
| Current-data migration rehearsal | 146 original snapshot records match field-for-field in isolated PostgreSQL except private platform-password rotation; all referenced PNG bytes match |
| Browser runtime | No uncaught exceptions in the verified flow |
| Git setup | New repository on `main`; local line-ending config and ignore rules in place |

The original 105 foundation/operation tests remain. Sixteen audit regressions add permission-revocation timing, strict setup numeric inputs, oversized requests, spoofed proxy IPs, custom domain permissions, filter validation, query growth, guarded development credentials, and concurrent reversal/day closing. Seven later tests cover public branding boundaries, scoped/Super Admin uploads, CSRF/image validation, inactive stations and balanced/repeat-safe demo data. Eight cloud tests cover database PNGs and private export/import boundaries, full numeric/ID/logo roundtrip, target protection and rollback. See [all 34 review areas](final-audit.md), [UI/branding changes](ui-branding.md) and [cloud deployment](cloud-demo-deployment.md). Cloud resources and live provider routing have not been provisioned/verified; VPS templates are retained.

HTTP and browser checks used random disposable accounts exclusively in an isolated loopback PostgreSQL cluster on port 55432. Existing PostgreSQL service/databases were not changed. The existing development station/account were preserved. Development logins and the subsequently requested sample data were explicitly created in the separate local SQLite demo station; no browser fixtures entered it. The UI checks used dedicated preview ports 5174/8002 with their test origin trusted for CSRF. Owned test services and the isolated cluster were stopped after verification; existing user servers were preserved. Browser screenshots remain in ignored `.postgres-test/screenshots/` for local review.

Chrome was controlled through its local debugging protocol with a separate disposable profile. Desktop owner, mobile Dari/Pashto worker, Pashto tablet form and thermal receipt screenshots were inspected. `scripts/verify_browser.mjs` checks foundation flows; `scripts/verify_fuel_browser.mjs` checks fuel workflow and persistence; `scripts/verify_final_audit.mjs` checks mobile/tablet forms, empty states and custom permissions; `scripts/verify_receipt_print.mjs` checks printable margins in all three languages and creates 58/80 mm PDFs. They share `scripts/browser_client.mjs`; `scripts/browser_fixture.py` refuses any database other than the isolated loopback test database. To repeat, migrate the isolated database, start Django with that `DATABASE_URL`, start Vite, and launch headless Chrome with `--remote-debugging-address=127.0.0.1 --remote-debugging-port=9333` and a separate `--user-data-dir` inside `.postgres-test/`. Then run:

```powershell
$env:DATABASE_URL='postgresql://petrol_test@127.0.0.1:55432/petrol_station_test_base'
node scripts/verify_browser.mjs
node scripts/verify_fuel_browser.mjs
node scripts/verify_final_audit.mjs
node scripts/verify_receipt_print.mjs
```

The later `scripts/verify_ui_branding.mjs` additionally verifies both logo-upload forms and all role dashboards. Create its PNG fixture first, then run it against the same isolated database/preview:

```powershell
.\.venv\Scripts\python.exe backend\manage.py shell -c "from pathlib import Path; from apps.tenants.management.commands.seed_demo_data import demo_logo; Path('.postgres-test/branding-test.png').write_bytes(demo_logo())"
node scripts/verify_ui_branding.mjs
```

When existing servers occupy the default ports, use dedicated ports and set `VERIFY_BASE_URL` for the browser helper and `VITE_DEV_API_TARGET` for Vite. Include that frontend origin in the test backend's `DJANGO_CSRF_TRUSTED_ORIGINS`.

Use only that disposable browser profile: the verifier clears its cookies before starting. Each run creates fresh test accounts and stations. Stop the test servers/browser/isolated cluster afterwards. Browser scripts verify representative setup and operational flows; backend tests provide broader role/isolation/error/reversal coverage. Native-speaker translation review, production hosting, durable offline recovery, accounting reports and hardware integrations remain for subsequent phases. A passing `check --deploy` does not establish that a hosting provider has TLS, backups or static-file serving configured.
