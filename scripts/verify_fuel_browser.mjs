import assert from 'node:assert/strict';
import { mkdirSync, writeFileSync } from 'node:fs';
import { createBrowserClient } from './browser_client.mjs';
const { fixture, call, evaluate, waitFor, navigate, fill, click, login, logout, chooseLanguage, api, addRecord, exceptions, close } = await createBrowserClient({ operations: true });
async function clickText(text) {
  await waitFor(`Array.from(document.querySelectorAll('button')).some(button => button.textContent.trim() === ${JSON.stringify(text)})`);
  await evaluate(`Array.from(document.querySelectorAll('button')).find(button => button.textContent.trim() === ${JSON.stringify(text)}).click()`);
}
async function operation(path, values, expected) {
  await addRecord(path, values, expected);
}
try {
  await login('owner'); await chooseLanguage('en');
  await addRecord('/suppliers', { name: 'Browser Supplier', code: 'browser-supplier' }, 'Browser Supplier');
  await addRecord('/customers', { name: 'Browser Customer', code: 'browser-customer', credit_limit: '2000.00' }, 'Browser Customer');
  const supplier = (await api('/suppliers/')).data.results[0];
  const customer = (await api('/customers/')).data.results[0];
  const tank = (await api('/tanks/')).data.results[0];
  await operation('/operations/purchases', { supplier_id: supplier.id, tank_id: tank.id, quantity: '100.000', unit_cost: '60.0000', paid_amount: '0.00', invoice_number: 'BROWSER-'+fixture.suffix }, 'PURCHASE-000001');
  await operation('/operations/cash-movements', { kind: 'deposit', amount: '100.00', reason: 'Initial station cash fund' }, 'Cash deposit');
  assert.equal((await api('/operations/options/')).data.tanks[0].book_stock, '600.000');
  const ownerCsrf = (await api('/auth/csrf/')).data.csrf_token;
  assert.equal((await api('/station/', { method: 'PATCH', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': ownerCsrf }, body: JSON.stringify({ settings: { receipt_width: '58' } }) })).status, 200);
  console.log('PASS: rendered supplier/customer setup, delivery and opening cash persist');
  await logout(); await login('worker'); await chooseLanguage('en');
  await click('.nozzle-choices input[type=checkbox]');
  await fill('field-opening_cash', '100.00'); await click('.record-form button[type=submit]');
  await waitFor('Boolean(document.querySelector(".shift-summary"))');
  await click('.nozzle-action');
  await fill('sale-closing-meter', '110.000');
  await click('.sale-entry summary');
  await fill('sale-customer', customer.id); await fill('sale-credit', '200.00'); await fill('sale-bank', '100.00');
  await clickText('Calculate total');
  await waitFor('document.querySelector(".sale-quote")?.innerText.includes("700.00")');
  assert.equal(await evaluate('document.querySelector(".sale-quote").innerText.includes("400.00")'), true);
  await click('.sale-entry button[type=submit]');
  await waitFor('Boolean(document.querySelector(".sale-entry .success-message a"))');
  const sale = (await api('/sales/')).data.results[0];
  assert.equal(sale.liters, '10.000'); assert.equal(sale.total, '700.00'); assert.equal(sale.cash_amount, '400.00');
  const salePayload = { assignment_id: (await api('/shifts/?status=open')).data.results[0].assignments[0].id, closing_meter: '110.000' };
  const csrf = (await api('/auth/csrf/')).data.csrf_token;
  assert.equal((await api('/sales/', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf, 'Idempotency-Key': crypto.randomUUID() }, body: JSON.stringify(salePayload) })).status, 400);
  console.log('PASS: worker meter entry, backend quote and split cash/bank/credit sale; duplicate meter interval rejected');
  await navigate('/receipts/'+sale.id);
  await waitFor('document.querySelector(".receipt-paper")?.innerText.includes("SALE-000001")');
  assert.equal(await evaluate('document.querySelector(".receipt-paper").innerText.includes("700.00")'), true);
  for (const language of ['en', 'fa', 'ps']) {
    await chooseLanguage(language);
    assert.equal(await evaluate('document.documentElement.dir'), language === 'en' ? 'ltr' : 'rtl');
    assert.equal(await evaluate('document.querySelector(".receipt-paper").getBoundingClientRect().width <= 220'), true);
  }
  await call('Emulation.setEmulatedMedia', { media: 'print' });
  assert.equal(await evaluate('getComputedStyle(document.querySelector(".sidebar")).display'), 'none');
  mkdirSync('.postgres-test/screenshots', { recursive: true });
  writeFileSync('.postgres-test/screenshots/fuel-receipt.png', Buffer.from((await call('Page.captureScreenshot', { format: 'png' })).data, 'base64'));
  await call('Emulation.setEmulatedMedia', { media: '' });
  await chooseLanguage('en');
  await navigate('/'); await clickText('Receive customer payment');
  await fill('field-customer_id', customer.id); await fill('field-amount', '100.00'); await click('.record-form button[type=submit]');
  await waitFor(`Boolean(document.querySelector('.success-message a[href^="/payment-receipts/"]'))`);
  const payment = (await api('/customer-payments/')).data.results[0];
  await navigate('/payment-receipts/'+payment.id);
  await waitFor('document.querySelector(".receipt-paper")?.innerText.includes("PAYMENT-000001")');
  assert.equal(await evaluate('document.querySelector(".receipt-paper").innerText.includes("100.00")'), true);
  await navigate('/'); await chooseLanguage('fa');
  await call('Emulation.setDeviceMetricsOverride', { width: 390, height: 844, deviceScaleFactor: 1, mobile: true });
  await waitFor('Boolean(document.querySelector(".shift-summary"))');
  assert.equal(await evaluate('document.documentElement.dir'), 'rtl');
  assert.equal(await evaluate('document.documentElement.scrollWidth <= innerWidth'), true);
  writeFileSync('.postgres-test/screenshots/fuel-worker-mobile.png', Buffer.from((await call('Page.captureScreenshot', { format: 'png' })).data, 'base64'));
  assert.deepEqual(await evaluate('Array.from(document.querySelectorAll(".sidebar nav a"), a=>a.getAttribute("href"))'), ['/', '/account', '/select-station']);
  await chooseLanguage('en'); await clickText('Close shift');
  await fill('field-counted_cash', '600.00'); await click('.record-form button[type=submit]');
  await waitFor('!document.querySelector(".shift-summary") && Boolean(document.querySelector(".nozzle-choices"))');
  console.log('PASS: sale/payment receipts and print layout; simple mobile RTL worker flow and reconciled handover');
  await logout(); await login('owner'); await chooseLanguage('en');
  await call('Emulation.setDeviceMetricsOverride', { width: 1366, height: 900, deviceScaleFactor: 1, mobile: false });
  assert.equal((await api('/customers/'+customer.id+'/')).data.balance, '100.00');
  await navigate('/operations/physical-stock'); await click('.page-heading-actions button');
  await fill('field-tank_id', tank.id); await fill('field-measured_quantity', '589.500');
  await click('#field-apply_adjustment'); await fill('field-reason', 'Approved physical dip variance');
  await click('.record-form button[type=submit]');
  await waitFor('!document.querySelector(".record-form") && document.querySelector("table")?.innerText.includes("-0.500")');
  assert.equal((await api('/operations/options/')).data.tanks[0].book_stock, '589.500');
  await navigate('/operations/daily-closings'); await waitFor('Boolean(document.querySelector("table tbody tr"))');
  await clickText('Close station day'); await fill('field-counted_cash', '600.00'); await click('.record-form button[type=submit]');
  await waitFor('!document.querySelector(".record-form") && document.querySelector("table")?.innerText.includes("Closed")');
  const day = (await api('/daily-closings/')).data.results[0];
  assert.equal(day.snapshot.sales_total, '700.00'); assert.equal(day.snapshot.customer_payments, '100.00');
  assert.equal(day.expected_cash, '600.00'); assert.equal(day.cash_difference, '0.00');
  writeFileSync('.postgres-test/screenshots/fuel-daily-closing.png', Buffer.from((await call('Page.captureScreenshot', { format: 'png' })).data, 'base64'));
  assert.deepEqual(exceptions, []);
  console.log('PASS: owner physical variance adjustment and daily closing persist exact stock/cash snapshots; no uncaught browser exceptions');
} finally { await close(); }

