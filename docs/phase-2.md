# Prompt 2: users, tenants and station configuration

This document records the Prompt 2 foundation. [Prompt 3](phase-3.md) subsequently adds operational posting on these models and permissions.

The existing Django/DRF and React architecture is extended with configuration modules. Transactional sales, purchases, shifts, accounting and stock movements are not implemented.

## Roles and access

| Role | Default access |
| --- | --- |
| Super Admin | Platform tenant creation/activation, global users, station assignments, platform counts and platform audit history |
| Tenant Owner/Admin | Station profile/settings/logo/compliance, employees, role policies and all fuel configuration/history |
| Manager | Station overview, worker employee management, fuel configuration and price history |
| Worker/Attendant | Station overview, own account/password and station selection; no setup tables or management forms |
| Accountant | Station overview, own account and read-only products/tanks/pumps/nozzles |

Station role policies can replace defaults; individual membership overrides can explicitly allow or deny known permissions. Policies and overrides are checked on every request. Only owners can configure role policies; owner access management cannot be removed. Managers with operational employee permission can manage workers and cannot alter permission overrides. Future shift/accounting/report permission identifiers reserve access vocabulary without enabling future modules.

Super Admin is the global Django `is_superuser` flag, not a tenant role. System administrators do not automatically read station data. To enter a station they need an active membership, select it, and receive that membership's permissions. Platform changes are recorded separately from tenant events.

## Setup workflow

1. Run migrations and create a superuser, or provision an initial station owner using the README commands.
2. A system administrator signs in to create a station and its initial owner atomically. The station has its own name, language, colors, profile and settings.
3. Owners create employee accounts, choose roles, and optionally configure role policies or overrides. System administrators assign existing global identities to additional stations through the system-user edit page.
4. Owners configure station details, supported settings and a logo. The same application serves every tenant with its active station's branding.
5. Owners/managers configure fuel products, tanks, pumps and nozzles. Price changes automatically append a history snapshot.

Global usernames are unique. Station employee names, contact details and activation remain local to a membership. Station owners may reset a password only for an ordinary identity belonging to that one station; shared identities and system administrators change their own passwords. A password change requires the current password, retains the current session and invalidates other sessions. Username/password changes cannot be made through generic platform user edits. There is no public signup or email password-recovery flow.

## APIs

All paths below are relative to `/api/v1/`. Unsafe requests require a session and valid CSRF token; login also requires CSRF. List endpoints are paginated unless noted. Resource APIs support GET, POST and PATCH; destructive DELETE and replacement PUT are disabled.

| Path | Methods and purpose |
| --- | --- |
| `auth/csrf/`, `auth/login/`, `auth/logout/`, `auth/me/` | Existing CSRF/session endpoints |
| `auth/memberships/` | GET authorized station choices, `{results}` |
| `auth/select-tenant/` | POST `{tenant_id}`; verified membership, rotated session/CSRF |
| `auth/platform/` | POST return a system administrator to platform context |
| `auth/password/` | POST `{current_password, new_password}` |
| `platform/status/` | GET tenant/active-tenant/global-user counts |
| `platform/tenants/` | List/create stations and initial owner; detail GET/PATCH |
| `platform/users/` | List/create global users; detail GET/PATCH identity/activation/admin flag |
| `platform/users/{id}/memberships/` | GET assignments; POST `{tenant_id, role, is_active}` |
| `platform/audit/` | GET paginated platform access/administration events |
| `roles/` | Owner GET policy defaults/effective policies; POST `{role, permissions}` |
| `employees/` | Scoped employee list/create; detail GET/PATCH |
| `station/` | GET permission-safe profile; PATCH authorized profile/settings/branding |
| `station/logo/` | Authenticated GET; station-manager POST multipart `logo` |
| `branding/<slug>/`, `branding/<slug>/logo/` | Public read-only station branding for login; active stations only, no operational fields |
| `platform/tenants/<uuid>/logo/` | Super Admin GET/POST sanitized logo; POST requires CSRF |
| `station/compliance/` | Scoped configurable compliance list/create/detail/PATCH |
| `fuel/products/` | Scoped products list/create/detail/PATCH, optional `price_reason` |
| `fuel/price-history/` | GET-only list/detail; filter by `product` UUID |
| `tanks/`, `pumps/`, `nozzles/` | Scoped equipment list/create/detail/PATCH |

Paginated responses use `{count, next, previous, results}`; `page` and `page_size` are supported (25 default, 200 maximum). Configuration lists support `search` and `is_active` where applicable; employee status filters its membership. The platform audit endpoint supports action/username search. Errors use the existing `{error: {code, message, details}}` shape.

## Configuration and validation

Prices use `Decimal(18,4)`; quantities/meters use `Decimal(18,3)` and are represented as JSON strings. Nonnegative values, positive tank capacity and opening/minimum quantities no greater than capacity are validated in APIs and database checks. Codes, tank names, pump numbers and nozzle numbers have appropriate tenant-scoped uniqueness constraints. Price history captures initial prices and each actual price change and cannot be edited through the API.

Scoped relationship choices and database constraints reject foreign-tenant memberships/products/tanks/pumps. A nozzle's tank must use its fuel product. Active equipment cannot point to inactive parents; linked active equipment prevents parent deactivation. Fuel unit changes after equipment creation, linked tank fuel changes, and nozzle opening-meter edits are rejected. Opening quantities are setup values, not a calculated inventory balance. Meter resets, stock adjustments and operational histories belong to Prompt 3.

Profile settings include station/contact/owner details, currency, language, IANA timezone, supported Gregorian date formats, receipt text and branding colors. Validated configurable `settings` keys are:

- `payment_methods`, `expense_categories`: up to 50 non-empty labels per list.
- `tax_enabled`, `tax_rate`: boolean and exact decimal rate from 0 to 100.
- `cash_difference_threshold`, `stock_variance_threshold`: nonnegative decimals.
- `opening_time`, `closing_time`: `HH:mm`.
- `receipt_width`: `58` or `80` mm.

These settings store configuration; they do not post taxes, generate receipts or compute cash/stock discrepancies yet. Compliance remains descriptive configurable records with source references/dates/status, without hard-coded legal decisions.

Logos are decoded PNG/JPEG/WebP files, limited to 2 MB and 2048 pixels in either dimension, then reencoded as fresh PNG to strip metadata and trailing content. Storage paths are generated per tenant. Only authenticated requests in that station context can read the logo. Do not expose `media/` through a public static route when deploying.

## UI and localization

Shared responsive tables/forms provide search, activation filters, pagination, add/edit actions, field-level validation indicators, retry feedback and submission locking. Worker navigation contains Overview, My account and Change station. Accountants receive read-only configuration tables. Owner and platform forms expose only authorized actions.

All 183 translation keys are present in English, Dari and Pashto. Dari/Pashto set RTL direction and localized labels; dates use the station timezone with a Gregorian calendar. The station language applies unless the user explicitly selects a language. Brand colors calculate a contrasting foreground. Failed form values remain in component memory; no passwords or operational drafts are persisted to browser storage. Native-speaker terminology review and expanded poor-network/offline behavior remain for Prompt 5.

## Migrations and verification

Migrations add role policies, employees, platform audit events and fuel configuration. Existing station memberships are backfilled with employee profiles. PostgreSQL composite foreign keys and SQLite triggers enforce same-tenant references, including nozzle/tank fuel agreement. Existing custom users, profiles, scoped managers, API errors and session architecture are reused.

The 63-test regression suite covers tenant list/detail/update isolation, spoofed tenant inputs, foreign relations, direct database violations, role policies, employee creation/deactivation, administrator lockout protection, session/CSRF rotation, password session invalidation, station settings, logo sanitization and decimal price history. See [verification results](verification.md) for database and browser checks and their limits.
