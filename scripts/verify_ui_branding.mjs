import assert from 'node:assert/strict';
import { mkdirSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { createBrowserClient } from './browser_client.mjs';

const { fixture, call, evaluate, waitFor, navigate, click, login, logout, chooseLanguage, api, exceptions, close } = await createBrowserClient({ operations: true });
mkdirSync('.postgres-test/screenshots', { recursive: true });
async function uploadLogo() {
  await waitFor('Boolean(document.querySelector(".branding-editor input[type=file]"))');
  const root = await call('DOM.getDocument');
  const node = await call('DOM.querySelector', { nodeId: root.root.nodeId, selector: '.branding-editor input[type=file]' });
  await call('DOM.setFileInputFiles', { nodeId: node.nodeId, files: [resolve('.postgres-test/branding-test.png')] });
  await waitFor('!document.querySelector(".branding-editor button").disabled');
  await click('.branding-editor button');
  await waitFor('Boolean(document.querySelector(".branding-editor .success-message"))');
}
async function screenshot(name) { writeFileSync('.postgres-test/screenshots/'+name+'.png', Buffer.from((await call('Page.captureScreenshot', { format: 'png' })).data, 'base64')); }
async function fits() { assert.equal(await evaluate('document.documentElement.scrollWidth <= innerWidth+1'), true, 'Page exceeds viewport'); }
try {
  await login('platform'); await chooseLanguage('en');
  await navigate('/platform/tenants');
  await evaluate(`(() => { const input=document.querySelector('.table-tools input'); Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(input,'browser-qa-${fixture.suffix}'); input.dispatchEvent(new Event('input',{bubbles:true})); })()`);
  await click('.table-tools button');
  await waitFor('document.querySelectorAll("tbody tr").length===1');
  await click('tbody button');
  await waitFor('Boolean(document.querySelector(".branding-editor"))');
  await uploadLogo();
  const publicBrand = (await api('/branding/browser-qa-'+fixture.suffix+'/')).data;
  assert.ok(publicBrand.logo_url);
  await navigate('/');
  assert.equal(await evaluate('document.querySelector(".dashboard-guide").innerText.includes("Manage stations")'), true);
  const csrf = (await api('/auth/csrf/')).data.csrf_token;
  const createdManager = await api('/platform/users/', { method: 'POST', headers: {'Content-Type':'application/json','X-CSRFToken':csrf}, body: JSON.stringify({username:'qa-manager-'+fixture.suffix,password:fixture.password,first_name:'QA Manager',tenant_id:fixture.tenant_id,role:'manager',preferred_language:'en'}) });
  assert.equal(createdManager.status, 201, JSON.stringify(createdManager.data));
  fixture.users.manager = {username:'qa-manager-'+fixture.suffix,password:fixture.password};
  await logout();
  await navigate('/login?station=browser-qa-'+fixture.suffix);
  await waitFor('Boolean(document.querySelector(".login-story img")?.complete && document.querySelector(".login-story img")?.naturalWidth)');
  for (const language of ['en','fa','ps']) {
    await chooseLanguage(language);
    for (const width of [390,768,1366]) {
      await call('Emulation.setDeviceMetricsOverride',{width,height:950,deviceScaleFactor:1,mobile:false});
      await fits();
      if (language==='en' && width===1366) await screenshot('ui-login-desktop');
      if (language==='ps' && width===390) await screenshot('ui-login-pashto-mobile');
    }
  }
  await call('Emulation.setDeviceMetricsOverride',{width:1366,height:950,deviceScaleFactor:1,mobile:false});
  await login('owner'); await chooseLanguage('en');
  await navigate('/station-settings'); await uploadLogo();
  await waitFor('document.querySelector(".station-login-link a")?.href.includes("browser-qa-")');
  await navigate('/');
  await waitFor('Boolean(document.querySelector(".dashboard-watermark")?.complete && document.querySelector(".dashboard-watermark")?.naturalWidth)');
  assert.equal(await evaluate('getComputedStyle(document.querySelector(".dashboard-watermark")).pointerEvents'), 'none');
  assert.equal(await evaluate('document.querySelector(".dashboard-guide").innerText.includes("Set up your station")'), true);
  await screenshot('ui-owner-dashboard');
  for (const role of ['manager','accountant','worker']) {
    await logout(); await login(role); await chooseLanguage('en'); await navigate('/');
    await waitFor('Boolean(document.querySelector(".dashboard-guide"))');
    await waitFor('Boolean(document.querySelector(".dashboard-watermark")?.complete && document.querySelector(".dashboard-watermark")?.naturalWidth)');
    const heading = {manager:'Run daily operations',accountant:'Follow customer payments',worker:'Start shift'}[role];
    await evaluate('document.querySelector(".dashboard-guide").open=true');
    assert.equal(await evaluate(`document.querySelector('.dashboard-guide').innerText.includes(${JSON.stringify(heading)})`), true);
    if (role==='worker') assert.equal(await evaluate('document.querySelectorAll(".sidebar nav a").length'),3);
    for (const language of ['en','fa','ps']) {
      await chooseLanguage(language);
      for (const width of [390,768,1366]) { await call('Emulation.setDeviceMetricsOverride',{width,height:950,deviceScaleFactor:1,mobile:false}); await fits(); }
    }
    if (role==='worker') { await call('Emulation.setDeviceMetricsOverride',{width:390,height:1100,deviceScaleFactor:1,mobile:false}); await screenshot('ui-worker-pashto-mobile'); }
  }
  assert.deepEqual(exceptions, []);
  console.log('PASS: Owner/platform logo uploads, public branded login, dashboard watermark, five role guides, mobile/tablet/desktop and English/Dari/Pashto');
} catch (error) {
  console.error(await evaluate('JSON.stringify({url:location.href,errors:Array.from(document.querySelectorAll("[role=alert]")).map(node=>node.textContent)})'));
  throw error;
} finally { await close(); }
