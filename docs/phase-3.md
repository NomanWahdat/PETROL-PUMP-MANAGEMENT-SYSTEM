# Prompt 3: fuel operations

The existing Django/DRF and React application now supports operational fuel posting. The reserved `shifts`, `sales`, `suppliers`, `purchases`, `inventory`, `customers` and `cash` packages are active Django apps. `operations` coordinates their services and APIs; it does not replace the tenant, employee or equipment architecture.

## Delivered modules

| Module | Behavior and interface |
| --- | --- |
| Meter readings / fuel sales | Closing minus current meter determines volume; backend quote and posting; incremental meter history |
| Shifts / assignments | Active employee and ready-nozzle assignment, captured prices/tax, cash handover, authorized reopening |
| Fuel purchases / suppliers | Supplier profiles, delivery quantities/costs, paid/unpaid amount, invoice uniqueness, stock posting and reversal |
| Inventory movements / tank stock | Read-only signed movement ledger; opening quantity plus movements gives book stock |
| Physical stock / variance | Measured versus expected snapshot; an explicit approved adjustment posts the difference |
| Cash management | Sales receipts, customer payments, delivery payments, deposits, withdrawals, reversals and closing-count reconciliation |
| Credit customers / payments | Credit limits, opening debts, outstanding balances, cash/bank payments and payment reversals |
| Daily closing | Closed shifts and fresh physical measurements required; cash count and preserved daily/tank totals |
| Receipts | Branded sale and customer-payment receipts, captured names/currency/text, 58/80 mm layouts and browser printing |

The worker home page is the shift workflow. Its three navigation links remain My shift, My account and Change station. Owners/managers use detailed setup and transaction tables; accountants read operational records and manage authorized customer/cash/day tasks.

## Initial setup and normal use

1. Run migrations using the existing README commands. Configure products, tanks, pumps and tank-connected nozzles through Prompt 2 pages. Enter each tank's genuine initial quantity and each nozzle's initial cumulative meter.
2. Add suppliers and credit customers. A customer credit limit of zero prohibits new credit; opening debt is an initial setup value and is immutable after creation.
3. Record a cash deposit/opening station fund in the cash book before cash-paid deliveries. Bank-paid deliveries do not affect the cash book. Deliveries may also leave an unpaid supplier amount.
4. The attendant selects available ready nozzles and enters the drawer's opening cash. A manager can start a shift for an authorized employee. An attendant and a nozzle can each have only one active shift assignment.
5. For each sale interval, enter the closing meter. Calculate the total, choose any bank/credit allocation and confirm. The remaining cash is calculated by the server. Record individual credit customers as separate meter intervals; one interval has at most one credit customer.
6. Receive credit payments when appropriate. A worker's payment belongs to the worker's open shift. Managers/accountants can optionally allocate cash/payment entries to an open shift, or post station-level entries.
7. At shift end, confirm every final meter and count the drawer. Any additional liters must be posted as a sale before closing. A discrepancy above the station threshold requires a manager and a reason.
8. Close every shift, measure physical stock for all active tanks, then count station cash and close the station day. Review the saved daily snapshot, including stock variance, sales, purchases, credit and payments.

Opening drawer cash describes an allocation of existing station cash; starting a shift does not create money in the station cash book. Shift closure represents handover of the counted drawer. A manual withdrawal reduces station cash, for example cash deposited in an external bank; it is not an internal drawer-to-safe transfer. No fabricated operational records or demo transactions were inserted into the existing development station.

## Calculation and historical rules

Application arithmetic uses Python `Decimal`. Quantities/meters have three decimal places; prices have four; payable money has two. `ROUND_HALF_UP` rounds the sale subtotal and configured tax separately. For example, `10.000 × 73.4567 = 734.57`; configured 10% tax is `73.46`, giving `808.03`. Prices are exclusive of configured tax when tax is enabled. This is a configurable calculation, not a hard-coded legal tax rule.

Selling price and configured tax rate are captured when a shift starts. Subsequent configuration changes apply to new shifts. To apply a price change to a nozzle immediately, close its existing shift and start a new one; historical intervals keep their captured price. Receipt station/customer/product names, currency, header/footer and paper width are captured at posting. The current private tenant logo is used when printing. Currency and timezone cannot change after a station begins operational posting.

The meter interval starts at the latest recorded closing meter, or the configured opening meter before the first sale. A closing meter must be greater than that value. Sale posting records the reading, subtracts the volume from the tank, and allocates the calculated charge between cash, bank and credit in one transaction. Confirming final meters at shift close does not post another sale or decrement stock again.

Book stock is the initial tank quantity plus signed purchase/sale/reversal/adjustment movements. A delivery cannot exceed capacity; a sale cannot exceed book stock. Physical readings preserve expected quantity, measured quantity and their difference. Recording a measurement alone leaves book stock unchanged. Applying its variance requires an explicit adjustment choice and a reason. Measurements are blocked while that tank has active nozzle assignments. Later stock movement makes a measurement stale for daily closing.

Customer debt is opening debt plus posted credit sales minus posted customer payments. Payments cannot exceed debt, and new credit cannot exceed the configured limit. Bank payments reduce debt without increasing drawer cash. Supplier debt in this phase is posted purchase totals minus the amounts paid on those purchases; later supplier-payment/statement workflows belong to Prompt 4.

The station's operating day starts automatically on the first operational post, using its configured timezone. One day remains open until explicitly closed, including across midnight. New records belong to that open day; the next day starts on the next post after closure. A closed local date cannot silently start another day. This avoids splitting an unfinished shift at midnight.

Daily closing preserves calculated totals and a per-tank physical/book snapshot. Expected station cash is the cash movement balance; bank transactions are excluded. Any counted difference requires a reason and appends a reconciliation movement, so the next opening cash balance carries the actual count. Shift discrepancies remain handover records and are not posted twice into station cash.

Use PostgreSQL for real financial operations: its `NUMERIC` storage and equality constraints are exact. SQLite remains the existing debug-only development fallback; its numeric storage is approximate, so development checks compare at the declared scale and aggregates are requantized. Production settings prohibit the SQLite fallback.

## Reversals, reopening and posting safety

- Transaction APIs provide no PATCH/PUT/DELETE. Original records and signed ledgers remain available. Sales, purchases and customer payments have authorized reversal actions requiring a reason.
- Only the latest erroneous sale reading on a nozzle can be reversed. Its shift and day must be open. Reversal appends an explicit meter correction restoring the preceding meter, opposite stock/cash entries, and the actor/reason/time. Verify the actual meter before using this action. It is not a refund flow for fuel genuinely dispensed.
- A delivery cannot be reversed if its stock has already been consumed below the delivery quantity. Related collected customer payments must be reversed before reversing a credit sale that would otherwise make the customer's balance negative.
- A closed shift can be reopened by a manager only when its attendant retains shift access, has no other open shift, its equipment is ready/active, and no subsequent nozzle assignment exists. Sales also recheck equipment readiness. A closed day can be reopened only if it is the latest day. Reopen events preserve the preceding closure details in tenant audit history.
- Tank opening quantity/product and nozzle relationships become immutable after operational use. Stock corrections use the movement ledger. Active shifts prevent nozzle deactivation.
- Every posting/action requires an `Idempotency-Key` UUID. Under a tenant row lock, the server rechecks access, compares the operation, actor and request fingerprint, and stores one response. The same key and payload replay that response; a changed payload or actor receives HTTP 409. Failed transactions roll back the key and all ledger records together.
- Each invoice number can be recorded only once for its supplier within the tenant. Empty invoice numbers are allowed for deliveries without an invoice; use the same submission key when retrying.
- The UI disables concurrent submission and retains the submission key while its form is open, including after a failed request. After refreshing following an uncertain network result, inspect transaction history before submitting another intent. Durable offline drafts/synchronization remain for Prompt 5.

## APIs and frontend routes

Paths below are relative to `/api/v1/`. All require authenticated active tenant membership, permission checks and CSRF for unsafe methods. Operational posting/reverse/reopen/close actions additionally require `Idempotency-Key`; read-only sale quotes and supplier/customer configuration use the existing API conventions without that header.

| API | Methods / actions | UI |
| --- | --- | --- |
| `operations/options/` | GET role-safe available nozzles/parties/stock/cash/day/open-shift choices | Shared form reference data and overview |
| `shifts/` | GET list/detail, POST start; detail POST `close/`, `reopen/` | `/work`, `/operations/shifts` |
| `sales/` | GET list/detail, POST sale; POST `quote/`; detail POST `reverse/`, GET `receipt/` | `/work`, `/operations/sales`, `/receipts/{id}` |
| `meter-readings/` | GET list/detail | `/operations/meter-readings` |
| `suppliers/` | Scoped GET/POST/PATCH | `/suppliers` |
| `purchases/` | GET list/detail, POST delivery; detail POST `reverse/` | `/operations/purchases` |
| `inventory-movements/` | GET list/detail | `/stock`, `/operations/inventory-movements` |
| `physical-stock/` | GET list/detail, POST measurement/optional adjustment | `/operations/physical-stock` |
| `cash-movements/` | GET list/detail, POST deposit/withdrawal | `/operations/cash-movements` |
| `customers/` | Scoped GET/POST/PATCH; worker reads return only safe choice fields | `/customers` |
| `customer-payments/` | GET list/detail, POST payment; detail POST `reverse/`, GET `receipt/` | `/work`, `/operations/customer-payments`, `/payment-receipts/{id}` |
| `daily-closings/` | GET list/detail; detail POST `close/`, `reopen/` | `/operations/daily-closings` |

Resource lists retain `{count, next, previous, results}` pagination, searches where applicable, status filters for shifts/postings, and a validated `day` UUID filter for day-owned ledgers. Prices/quantities/money are decimal strings in JSON; floating-point input values are rejected. Client-supplied totals, liters, tenant and actor fields never determine posting results.

Typical start payload: `{nozzle_ids: [uuid], attendant_id: optional_uuid, opening_cash: "100.00"}`. Sale payload: `{assignment_id: uuid, closing_meter: "110.000", bank_amount: "100.00", credit_amount: "200.00", customer_id: uuid}`; omitted cash is calculated as total minus bank/credit. Closing a shift requires `{closing_meters: {assignment_uuid: "110.000"}, counted_cash: "600.00", reason: optional_text}`.

Purchase input uses `tank_id`, `supplier_id`, `quantity`, `unit_cost`, `paid_amount`, `method`, optional invoice/notes. Payments use `customer_id`, `amount`, `method` and optional `shift_id`. Physical readings use `tank_id`, `measured_quantity`, `apply_adjustment` and `reason`. Cash entries use `kind` (`deposit`/`withdrawal`), positive `amount`, `reason` and optional `shift_id`. Reverse/reopen actions use `{reason}`; daily close uses `{counted_cash, reason}`.

## Permissions and isolation

New configurable permissions are `purchases.manage`, `inventory.manage`, `customers.manage`, `cash.manage` and `closing.manage`. Existing `shifts.own`, `shifts.manage` and `reports.operational` drive operational access. Owners receive all permissions by default; managers receive operational setup/posting/corrections; workers receive only their own shifts/sales/readings/payments; accountants receive reads and customer/cash/day permissions. Existing custom role policies retain their explicit permission lists; an owner must enable new permissions there when appropriate.

Every operational queryset and relation lookup uses the verified session tenant. Worker lists/details/receipts additionally filter by assigned membership. The options API withholds station stock/cash and full customer balances from ordinary workers. Platform administrators still require explicit station membership and role permission.

Thirty-three additional PostgreSQL composite foreign keys/SQLite relationship triggers reject cross-tenant operational relations, including assignment tank/product agreement. Uniqueness constraints protect active attendant/nozzle assignments, operating days, references, invoices and submission keys. Tenant row locking serializes configuration and operational edits; audit, meter, inventory, cash and debt-affecting records are committed atomically.

## Verification and remaining phases

The final audit extends the original operational suite to 121 tests: 116 pass on SQLite with 5 PostgreSQL concurrency tests skipped; all 121 pass on PostgreSQL. Concurrency checks cover equal-key sales, different-key sales of the same interval, shift starts, reversals and daily cash reconciliation. Browser verification posts rendered forms through Vite/Django/PostgreSQL and checks receipts/printing, mobile/tablet Dari/Pashto RTL, balances and closing. See [verification details](verification.md) and [final audit](final-audit.md).

Prompt 4 still adds supplier payments/statements, expense workflows, accounting reports/exports, costing/profit calculations and broader audit browsing. Prompt 5 covers durable poor-network/offline recovery, native-speaker translation review, additional security/deployment hardening and hardware/printer integration if required. Browser printing is implemented; direct ESC/POS printing, automated dispenser integration, general meter resets/rollovers, arbitrary historical backdating and multi-currency exchange are not implemented. No deployment was performed.
