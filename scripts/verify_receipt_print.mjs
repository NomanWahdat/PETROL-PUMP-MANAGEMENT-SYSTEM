import assert from 'node:assert/strict';
import { mkdirSync, writeFileSync } from 'node:fs';
import { createBrowserClient } from './browser_client.mjs';

const { call, evaluate, waitFor, navigate, login, chooseLanguage, api, exceptions, close } = await createBrowserClient({ operations: true });
try {
  await login('owner');
  const csrf = (await api('/auth/csrf/')).data.csrf_token;
  const post = async (path, body, method = 'POST') => {
    const response = await api(path, { method, headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf, 'Idempotency-Key': crypto.randomUUID() }, body: JSON.stringify(body) });
    assert.equal(response.status, 200, JSON.stringify(response.data));
    return response.data;
  };
  const choices = (await api('/operations/options/')).data;
  const shift = await post('/shifts/', { nozzle_ids: [choices.nozzles[0].id] });
  mkdirSync('.postgres-test/screenshots', { recursive: true });
  let meter = 100;
  for (const width of [58, 80]) {
    await post('/station/', { settings: { receipt_width: String(width) } }, 'PATCH');
    meter += 10;
    const sale = await post('/sales/', { assignment_id: shift.assignments[0].id, closing_meter: String(meter) });
    await navigate('/receipts/'+sale.id);
    await waitFor('Boolean(document.querySelector(".receipt-paper"))');
    // Screen captures do not apply @page margins; emulate them around the paper.
    const printablePixels = Math.floor((width-10)*96/25.4);
    const paperPixels = Math.ceil(width*96/25.4);
    await call('Emulation.setDeviceMetricsOverride', { width: paperPixels, height: 1100, deviceScaleFactor: 1, mobile: false });
    await call('Emulation.setEmulatedMedia', { media: 'print' });
    await evaluate(`(() => { const style=document.createElement('style'); style.id='verification-paper'; style.textContent='@media print { body { width:${width}mm; padding:5mm; } }'; document.head.append(style); })()`);
    for (const language of ['en', 'fa', 'ps']) {
      await chooseLanguage(language);
      const bounds = await evaluate(`(() => {
        const paper = document.querySelector('.receipt-paper').getBoundingClientRect();
        return { paper: {left:paper.left,right:paper.right,width:paper.width,viewport:innerWidth}, items:Array.from(document.querySelectorAll('.receipt-paper dt, .receipt-paper dd')).map(node => { const rect=node.getBoundingClientRect(); const range=document.createRange(); range.selectNodeContents(node); return {text:node.textContent,left:rect.left-paper.left,right:rect.right-paper.right, textBounds:Array.from(range.getClientRects()).map(textRect => ({left:textRect.left-paper.left,right:textRect.right-paper.right}))}; }) };
      })()`);
      assert.equal(bounds.paper.left >= -1 && bounds.paper.right <= paperPixels+1 && bounds.paper.width <= printablePixels+1, true, `${width}mm ${language} receipt paper exceeds printable viewport: ${JSON.stringify(bounds)}`);
      assert.equal(bounds.items.every(rect => rect.left >= -1 && rect.right <= 1 && rect.textBounds.every(textRect => textRect.left >= -1 && textRect.right <= 1)), true, `${width}mm ${language} receipt text exceeds printable width: ${JSON.stringify(bounds)}`);
      assert.equal(await evaluate('getComputedStyle(document.querySelector(".sidebar")).display'), 'none');
      writeFileSync(`.postgres-test/screenshots/receipt-${width}-${language}.png`, Buffer.from((await call('Page.captureScreenshot', { format: 'png' })).data, 'base64'));
    }
    await evaluate('document.getElementById("verification-paper").remove()');
    const pdf = await call('Page.printToPDF', { paperWidth: width/25.4, paperHeight: 180/25.4, printBackground: true });
    writeFileSync(`.postgres-test/screenshots/receipt-${width}.pdf`, Buffer.from(pdf.data, 'base64'));
    await call('Emulation.setEmulatedMedia', { media: '' });
    await call('Emulation.setDeviceMetricsOverride', { width: 1366, height: 900, deviceScaleFactor: 1, mobile: false });
  }
  assert.deepEqual(exceptions, []);
  console.log('PASS: 58/80 mm receipt columns fit printable margins in English/Dari/Pashto; PDF printing succeeds');
} finally { await close(); }
