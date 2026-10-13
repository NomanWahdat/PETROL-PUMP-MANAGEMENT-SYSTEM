# Station branding and UI enhancement

Updated 13 October 2026. The existing Django/React architecture and operational calculations are retained. No new business module or UI dependency was added.

The interface uses light green/blue surfaces, clearer headings, simple stock/cash summaries, readable forms/tables, an original SVG fuel-station illustration and compact pump marks. Each station dashboard displays its logo in the sidebar/header and as a faint non-interactive watermark. Every role has a translated usage guide; the worker guide starts collapsed so the shift workflow remains prominent. The application remains responsive and supports English, Dari RTL and Pashto RTL.

## Uploading logos

- **Owner:** Station settings → logo. The existing station permission applies, and upload selection cannot choose another tenant.
- **Super Admin:** Stations → find/edit a station → logo. No station membership is needed to manage its branding; uploads create platform audit events. Operational access still requires membership.
- PNG, JPEG and WebP files are decoded and re-encoded as PNG, up to 2 MB and 2048 pixels per side. Each logo uses its own generated tenant storage path. Replacing a logo removes the previous file after commit.
- For the free Render/Neon demo, `DJANGO_LOGO_STORAGE=database` stores the sanitized PNG in PostgreSQL rather than ephemeral local files. The decoded PNG must also fit within 2 MB. File storage remains the local/VPS default; both use the same authorized logo API.
- Stations without an uploaded logo show a fuel-pump mark. The sample demo logo can be replaced with the actual station logo.

## Branded login

Share the link shown in station settings or the platform station editor, for example:

```text
http://127.0.0.1:5173/login?station=development-demo
http://127.0.0.1:5173/login?station=ahmad
```

An unsigned visitor needs a station code/link to select branding; there is no public station directory. The login page's optional station-code form can change the displayed brand. Returning browsers remember only the last station code, not credentials. A branded link does not change tenant authorization or restrict an account to a guessed station; login/membership selection remains the source of access rights.

| API | Behavior |
| --- | --- |
| `GET /api/v1/branding/<slug>/` | Public name, slug, primary color and logo URL for an active station only |
| `GET /api/v1/branding/<slug>/logo/` | Public sanitized branding image; missing/inactive stations return 404 |
| `GET/POST /api/v1/station/logo/` | Existing authenticated tenant-scoped read/upload |
| `GET/POST /api/v1/platform/tenants/<uuid>/logo/` | Super Admin branding read/upload; POST requires CSRF |

Station names/logos are intentionally public to support pre-login branding. Addresses, contacts, users, membership details, settings and financial/stock records remain authenticated. Keep direct `/media/` access blocked in production.

## Development sample data

Run `create_demo_users`, then `seed_demo_data`, with debug enabled. Both have already run in this workspace's development database. The seeder is restricted to the original `development-demo` station and accounts, refuses pre-existing equipment, preserves uploaded logos and does nothing after successful seeding. It does not create accounts or change passwords. Financial postings use the existing validated Decimal services, authorization locks, idempotency records, ledgers and audit events within one atomic transaction.

Initial samples: two products, tanks, pumps and nozzles; two fictional suppliers and customers; one 1,500-liter diesel delivery; two sales totaling 6,150 AFN; one 100 AFN customer payment; one completed owner shift and one active `demo-worker` shift. Initial petrol/diesel book stock is 6,450/6,465 liters; station cash is 14,550 AFN; the transport customer's balance is 2,100 AFN. Subsequent user actions change those values normally. Receipts and notes identify demonstration transactions. The original Ahmad station and all account passwords were preserved.

## Verification

The backend suite includes seven new checks for public branding boundaries, scoped uploads, Super Admin audit events, CSRF/image validation, inactive stations and guarded/repeat-safe balanced demo data. The full suite passes on PostgreSQL; SQLite skips only the five real-concurrency cases. `npm test` checks all 324 translation keys and the production build passes.

`scripts/verify_ui_branding.mjs` uses the isolated PostgreSQL fixture and disposable Chrome profile to exercise both upload interfaces, branded login, watermark and all five role guides at mobile/tablet/desktop widths in English/Dari/Pashto. Generate its PNG fixture with `demo_logo()` from the sample-data command into `.postgres-test/branding-test.png` before running. `VERIFY_BASE_URL` can select a dedicated preview port; that origin must be in the test backend's CSRF trusted origins. Screenshots remain in ignored `.postgres-test/screenshots/`. These checks do not replace native-speaker review or production-host validation.
