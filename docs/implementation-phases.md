# Five implementation phases

## Prompt 1 — Setup, architecture and database foundation

Deliver the Django/React projects, environment/configuration, PostgreSQL support with explicit SQLite development fallback, custom user, tenant and membership foundation, station/compliance/audit foundations, migrations, session/CSRF endpoints, health/readiness endpoints, protected station view, base routes, plain styling, Dari/Pashto/English dictionaries, tests and development documentation.

Acceptance: backend checks and migrations succeed; health is public; station data requires verified membership; tenant spoofing and revoked access are denied; worker output excludes sensitive settings; frontend builds and supports both directions. Remaining production hardening is explicit.

## Prompt 2 — Authentication, tenants, roles, employees and station settings

Implemented: Super Admin tenant provisioning/activation and global user management, secure multi-tenant selection, configurable roles/permissions, employee profiles/accounts/assignments, password changes, profile/receipt settings, validated private logo uploads and tenant branding. Fuel products, exact decimal price history, tanks, pumps and nozzles are part of Prompt 2 configuration. Log access/settings changes. Platform administration does not automatically grant station access. Verified-email password recovery remains to be implemented.

Acceptance: role matrix tests, tenant-specific CRUD isolation, safe tenant switching, revoked access, upload validation and password/session lifecycle tests.

## Prompt 3 — Fuel operations

Implemented on Prompt 2 products/price history/tanks/pumps/nozzles: physical readings/variance/adjustments, meter history and sales, purchases/refills/suppliers, shifts and handovers, cash movements, credit customers/payments, daily closing, reversals/reopening and printable receipts. Decimal scales and rounding are explicit; shifts capture prices/tax and changes apply to new shifts. Posting is atomic and idempotent. General meter resets/rollovers, inventory costing/profit, supplier payments/statements and full accounting remain for subsequent work. See [operational rules](phase-3.md).

Acceptance: exact decimal calculations, concurrent meter/stock safety, no double-counting, reversals, historical pricing, closed-shift permissions, duplicate submission protection and tenant isolation.

## Prompt 4 — Accounting and reporting

Complete credit customers and supplier statements/payments, configurable expenses, cash management, daily closing, reports/exports, profit estimates, receipts, alerts and authorized read-only audit history. Keep accounting operational; do not introduce a full ERP.

Acceptance: balance reconciliation, opening/closing stock and cash, permissions, correct date/timezone filters, historical cost reporting, closed-day protections and exports matching report totals.

## Prompt 5 — Integration, localization, reliability and security

Review worker tasks for minimal clicks, polish responsive/RTL layouts and translations with native speakers, verify printer-friendly receipts, add safe operational drafts and failure recovery, complete integration/concurrency/isolation tests, configure distributed rate limiting, validate uploads, check deployments/backups and prepare future PWA support without an unnecessary sync engine.

Acceptance: complete browser → API → PostgreSQL flows, restored failed forms without duplicate posting, permission/tenant regression suite, production configuration checks and documented rollout/recovery procedures.
