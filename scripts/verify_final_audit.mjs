import assert from 'node:assert/strict';
import { writeFileSync, mkdirSync } from 'node:fs';
import { createBrowserClient } from './browser_client.mjs';

const { call, evaluate, waitFor, navigate, click, login, logout, chooseLanguage, api, exceptions, close } = await createBrowserClient();
try {
  await login('owner'); await chooseLanguage('en');
  if (!process.argv.includes('--permissions-only')) {
  await navigate('/');
  await waitFor('document.querySelector("main")?.innerText.includes("No records yet")');
  await navigate('/stock');
  await waitFor('Boolean(document.querySelector(".empty-state"))');
  for (const width of [390, 768, 1024]) {
    await call('Emulation.setDeviceMetricsOverride', { width, height: 1024, deviceScaleFactor: 1, mobile: width === 390 });
    for (const language of ['en', 'fa', 'ps']) {
      await chooseLanguage(language); await navigate('/products');
      await click('.page-heading-actions button');
      await waitFor('Boolean(document.querySelector(".record-form"))');
      const dimensions = await evaluate('({width:innerWidth, scroll:document.documentElement.scrollWidth, contentTop:document.querySelector("main").getBoundingClientRect().top, height:innerHeight, direction:document.documentElement.dir})');
      assert.equal(dimensions.scroll <= dimensions.width, true, `${language} product form overflows at ${width}px`);
      assert.equal(dimensions.contentTop < dimensions.height, true, `Owner navigation pushes content beyond the first screen at ${width}px`);
      assert.equal(dimensions.direction, language === 'en' ? 'ltr' : 'rtl');
    }
  }
  mkdirSync('.postgres-test/screenshots', { recursive: true });
  writeFileSync('.postgres-test/screenshots/audit-owner-pashto-tablet.png', Buffer.from((await call('Page.captureScreenshot', { format: 'png' })).data, 'base64'));
  console.log('PASS: owner empty states and forms at mobile/tablet widths in English, Dari and Pashto');
  await call('Emulation.setDeviceMetricsOverride', { width: 390, height: 844, deviceScaleFactor: 1, mobile: true });
  await logout(); await login('worker'); await chooseLanguage('ps');
  await waitFor('Boolean(document.querySelector(".nozzle-choices"))');
  await click('.record-form button[type=submit]');
  await waitFor('Boolean(document.querySelector(".record-form [role=alert]"))');
  assert.equal((await api('/shifts/')).data.count, 0);
  assert.equal(await evaluate('document.documentElement.scrollWidth <= innerWidth'), true);
  assert.equal(await evaluate('document.querySelectorAll(".sidebar nav a").length'), 3);
  writeFileSync('.postgres-test/screenshots/audit-worker-pashto-mobile.png', Buffer.from((await call('Page.captureScreenshot', { format: 'png' })).data, 'base64'));
  await logout(); await login('owner');
  }
  const csrf = (await api('/auth/csrf/')).data.csrf_token;
  const policy = await api('/roles/', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf }, body: JSON.stringify({ role: 'worker', permissions: ['station.view', 'purchases.manage'] }) });
  assert.equal(policy.status, 200);
  await logout(); await login('worker'); await chooseLanguage('en');
  await waitFor(`Boolean(document.querySelector("a[href='/operations/purchases']"))`);
  await navigate('/operations/purchases'); await click('.page-heading-actions button');
  await waitFor('Boolean(document.getElementById("field-supplier_id"))');
  assert.equal((await api('/purchases/')).status, 200);
  assert.equal((await api('/sales/')).status, 403);
  assert.deepEqual(exceptions, []);
  console.log('PASS: worker Pashto RTL, empty nozzle validation and custom domain permissions through UI/API');
} finally { await close(); }
