# Final application audit

Reviewed and verified on 12 October 2026. This audit covers the implemented identity/configuration and fuel-operation application (Prompts 1–3). It does not add the accounting/offline modules reserved for later prompts or claim that an unconfigured public deployment is ready.

## Issues corrected

- Configuration writes now revalidate active tenant, membership, global account and current permission after acquiring the station lock. Permission revocation during a lock wait cannot authorize a stale write.
- Domain management permissions now permit the corresponding read screens, APIs, receipts and necessary reference choices without granting unrelated sales/cash/customer visibility. Worker ownership filters remain active unless the relevant management/report permission allows broader records.
- Setup prices, quantities and financial settings now use the same strict Decimal input field as operational transactions. Float-valued JSON is rejected. Shift closing already rejected float input; an additional regression verifies it.
- Daily-closing status filtering now works, and invalid operational status/day filters return validation errors. Page size remains capped at 200.
- Shift history uses related-object loading, assignment prefetching, latest-meter subqueries and grouped drawer totals. Customer/supplier balances use aggregate subqueries. Query-count tests verify that adding 25 customers or 12 assignment-bearing shifts does not introduce per-row queries. Ten indexes support station/day/customer/supplier/tank/assignment lookups.
- Late responses cannot replace newer filtered configuration/transaction lists. Stock/overview empty states are explicit, and failed transaction-list loads no longer show a permanent loading message.
- Nozzle selection uses a labeled fieldset with a required-selection check. Form controls fit narrow grids. Owner operations navigation starts collapsed on mobile; desktop navigation remains expanded. No gradients, animations, chart libraries or decorative dashboards were introduced.
- Django REST Framework was upgraded from 3.16.1 to 3.17.2 after the dependency audit found two published advisories. Oversized JSON returns a safe localized HTTP 413 response. See the upstream [request-size advisory](https://github.com/encode/django-rest-framework/security/advisories/GHSA-2m8g-3cmr-wg3w) and [AdminRenderer advisory](https://github.com/encode/django-rest-framework/security/advisories/GHSA-g47c-3xmw-q6m2); this app already uses JSON-only API rendering.
- Production requires shared database-cache login throttling and an explicit proxy-IP trust configuration. The provided nginx example overwrites forwarded headers, limits login requests, blocks public logos and serves the React routing fallback.
- An explicit debug-only `create_demo_users` command provides development credentials in a separate station, refusing collisions and preserving existing passwords/data. It creates no fuel transactions.
- Four unused phase-placeholder translations were removed. A repeatable translation test checks all 283 keys for language parity, duplicates, empty values and broken text.

## Requested review areas

| # | Area | Result / evidence and practical limit |
| --- | --- | --- |
| 1 | Tenant isolation/security | Scoped queries/relations, immutable session-selected tenant, worker ownership and database composite links tested against two tenants; no PostgreSQL RLS |
| 2 | Authentication | Password hashing, session rotation, CSRF, revoked/inactive access, logout and password/session invalidation tested |
| 3 | Role permissions | Default five roles plus configurable station policy/overrides; management/read alignment fixed and browser/API checked |
| 4 | API security | Session/CSRF required, JSON renderer, UUID inputs, bounded payloads, no transaction DELETE/PATCH and safe errors; dependency advisories addressed |
| 5 | Database integrity | All migrations pass on SQLite/PostgreSQL; same-tenant FK/trigger, assignment/day/reference/invoice/key uniqueness and numeric checks tested |
| 6 | Financial Decimal calculations | Decimal/NUMERIC with documented scales and rounding; exact allocations/tax/credit/payment/reversals tested; production requires PostgreSQL |
| 7 | Fuel stock | Opening stock plus signed movements, capacity/availability, reversal and explicit physical adjustment tests |
| 8 | Meter readings | Closing minus current opening, continuity, positive sale intervals, latest erroneous-reading correction and duplicate intervals tested |
| 9 | Shift closing | All assigned meters confirmed, backend expected drawer cash, counted difference, manager reason/threshold and safe reopen tested |
| 10 | Duplicate prevention | UUID replay and fingerprint/actor conflicts; five PostgreSQL concurrency cases cover sales, assignments, reversals and daily reconciliation |
| 11 | Validation | Scoped relationships, active equipment, capacity, credit limits, positive amounts, exact numeric strings, sizes and final readings tested |
| 12 | Error handling | Stable safe API envelopes, 400/403/404/409/413 behavior, frontend retry/error states; upstream proxy errors are handled as failed requests |
| 13 | Audit logging | Configuration/access/posting/correction/closing events preserve actors, times and safe changes; platform history available, tenant history UI remains future work |
| 14 | Responsive UI | Plain CSS, tables/forms and collapsed mobile operations navigation; no decorative effects added |
| 15 | Mobile/tablet | Owner forms at 390/768/1024 px, simple 390 px worker flow and no horizontal page overflow checked |
| 16 | Dari RTL | Document direction, translated owner/worker forms and receipts checked |
| 17 | Pashto RTL | Owner tablet forms, worker mobile validation and receipts checked |
| 18 | English | LTR setup, operational workflow, receipts and daily closing checked |
| 19 | Translation completeness | `npm test` checks 283 matching non-empty unique keys; TypeScript checks referenced keys; native-speaker review remains |
| 20 | Worker workflow | Default three navigation links; start/select nozzle/record meter/receive payment/close; management access denied |
| 21 | Owner dashboard | Persisted station profile, operating day, station cash and tank-stock table; empty state verified, no fabricated metrics |
| 22 | Performance | Related/aggregate list queries, 200-row page cap, targeted indexes, approximately 117 KB gzipped frontend; no production load benchmark |
| 23 | Loading states | Authentication/station/list/form loading and busy states reviewed; stale-list responses and error/loading conflict corrected |
| 24 | Empty states | Configuration/ledger and stock/overview empty states checked; empty nozzle choices give validation feedback |
| 25 | Form validation | Labeled fields, decimal steps, required choices, backend errors and disabled submissions; invalid nested nozzle labels corrected |
| 26 | Printing | Browser PDF printing succeeds at 58/80 mm and print CSS hides navigation; matching printer paper must be selected manually |
| 27 | Receipt layout | Captured station/customer/product/currency text, meter/tax/payment values, 58/80 mm printable margins and all three languages checked; no direct ESC/POS integration |
| 28 | Reports | Existing transaction histories, tank stock and daily-closing snapshots reviewed; full accounting/expense/profit/export reports are unimplemented |
| 29 | Database indexes | Existing FK/unique/audit indexes reviewed; ten operational composite indexes added via six migrations |
| 30 | Pagination/filtering | Standard `{count,next,previous,results}`, 25 default/200 maximum; search/status/day filters validated and scoped |
| 31 | Environment | Secret/database/debug/hosts/origins/proxy/cache/frontend variables documented; real secret remains ignored |
| 32 | Production | PostgreSQL-only, secure cookies/HTTPS, shared cache, proxy trust, deployment checks/static collection; Linux templates await host validation |
| 33 | Documentation | README, architecture, business/API notes, deployment guide, credentials, limits and audit results updated |
| 34 | Automated tests | All 121 PostgreSQL tests pass; 116 SQLite tests pass with five PostgreSQL-only concurrency skips; frontend build and browser checks pass |

## Verification

The complete suite retains the original 105 tests and adds 16 audit regressions. PostgreSQL passes all 121; SQLite passes 116 and skips the five real-concurrency cases. Django checks, production `check --deploy`, migration consistency, migrations on both databases, production database-cache read/write, `collectstatic`, TypeScript/Vite and translation checks pass.

`npm audit` and `pip-audit` report no known vulnerabilities in the reviewed dependency versions after the DRF upgrade. The Linux Gunicorn 23.0.0 version was also checked. Advisory checks are a snapshot, and the Windows lock excludes Gunicorn's platform-specific installation.

Chrome checks use a disposable profile and an isolated PostgreSQL cluster on port 55432. `verify_browser.mjs` covers setup/roles/localization; `verify_fuel_browser.mjs` covers delivery, drawer funding, split sale, payment, receipt, shift handover, variance and daily closing; `verify_final_audit.mjs` covers empty states, mobile/tablet forms and custom permissions. The latter supports `--permissions-only` for a focused permission recheck. `verify_receipt_print.mjs` verifies printable margins in English/Dari/Pashto and creates 58/80 mm PDFs. Screenshots and PDFs are kept in ignored `.postgres-test/screenshots/`. No browser fixtures entered the development database.

The existing account/station were preserved. Only the requested separate development test logins were added to local SQLite, and no operational transactions were created there. Temporary preview/browser/database services were stopped after verification. These checks are application tests and a code review, not an independent penetration test, a production hosting validation or real dispenser/printer certification.

## Handover

See [README](../README.md) for structure and development commands, [deployment guide](deployment.md) for installation, environment/database setup, production steps and development credentials, and [operational specification](phase-3.md) for calculation/reversal rules. The [deployment guide's limitations](deployment.md#limitations-and-future-work) distinguishes existing reports from future accounting, durable offline recovery, hardware integration and native-language review. No additional business modules were introduced by this audit.

## Subsequent UI update — 13 October 2026

The requested [UI/branding enhancement](ui-branding.md) adds light station interfaces, an illustrated login, owner/Super Admin logo uploads, intentionally public station login branding, dashboard watermarks, role-specific instructions and isolated development sample data. Seven additional backend regressions bring the current suite to 128 tests (123 pass and five skip on SQLite); the catalogs now contain 324 keys. The original audit results above remain a dated record; [verification](verification.md) documents the current application.

The subsequent [cloud demo preparation](cloud-demo-deployment.md) retains VPS support and adds Vercel/Render configuration, optional PostgreSQL-backed logos, static-file serving and private current-data export/import. Eight more regressions bring the suite to 136 PostgreSQL tests (128 pass and eight skip on SQLite). The actual 146-record snapshot and referenced logos passed an isolated PostgreSQL transfer rehearsal. No private data archive or environment secret belongs in the source repository.
