import { spawnSync } from 'node:child_process';
import { resolve } from 'node:path';

export async function createBrowserClient({ operations = false } = {}) {
// Run from the repository root with the isolated test database and a separate headless Chrome profile.
const python = process.platform === 'win32' ? '.venv/Scripts/python.exe' : '.venv/bin/python';
const setup = spawnSync(resolve(python), ['scripts/browser_fixture.py'], { encoding: 'utf8', env: { ...process.env, BROWSER_FUEL_OPERATIONS: operations ? 'true' : 'false' } });
if (setup.status !== 0) throw new Error(setup.stderr || 'Unable to create disposable test fixtures');
const fixture = JSON.parse(setup.stdout);
const base = process.env.VERIFY_BASE_URL || 'http://127.0.0.1:5173';
const debugging = process.env.VERIFY_CHROME_URL || 'http://127.0.0.1:9333';
const target = await (await fetch(`${debugging}/json/new?${encodeURIComponent(base)}`, { method: 'PUT' })).json();
const socket = new WebSocket(target.webSocketDebuggerUrl);
let sequence = 0;
const pending = new Map();
const exceptions = [];
socket.onmessage = event => {
  const message = JSON.parse(event.data);
  if (message.id) {
    const job = pending.get(message.id);
    if (job) { pending.delete(message.id); message.error ? job.reject(new Error(message.error.message)) : job.resolve(message.result); }
  } else if (message.method === 'Runtime.exceptionThrown') exceptions.push(message.params.exceptionDetails.text);
};
await new Promise((resolve, reject) => { socket.onopen = resolve; socket.onerror = reject; });
function call(method, params = {}) {
  return new Promise((resolve, reject) => {
    const id = ++sequence;
    const timeout = setTimeout(() => { pending.delete(id); reject(new Error(`Timed out: ${method}`)); }, 20000);
    pending.set(id, { resolve: value => { clearTimeout(timeout); resolve(value); }, reject: error => { clearTimeout(timeout); reject(error); } });
    socket.send(JSON.stringify({ id, method, params }));
  });
}
async function evaluate(expression) {
  const result = await call('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true });
  if (result.exceptionDetails) throw new Error(result.exceptionDetails.exception?.description || result.exceptionDetails.text);
  return result.result.value;
}
async function waitFor(expression) {
  const deadline = Date.now() + 20000;
  while (Date.now() < deadline) {
    try { if (await evaluate(expression)) return; } catch { /* Navigation may replace the execution context. */ }
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  throw new Error(`Page condition failed: ${expression}`);
}
async function navigate(path) {
  await call('Page.navigate', { url: base + path });
  const destination = new URL(path, base);
  await waitFor(`document.readyState === "complete" && location.pathname === ${JSON.stringify(destination.pathname)} && location.search === ${JSON.stringify(destination.search)} && Boolean(document.querySelector('h1, .sidebar main [role=alert], main [role=alert]'))`);
}
async function fill(id, value) {
  await waitFor(`Boolean(document.getElementById(${JSON.stringify(id)}))`);
  await waitFor(`document.getElementById(${JSON.stringify(id)}).tagName !== 'SELECT' || Array.from(document.getElementById(${JSON.stringify(id)}).options).some(option => option.value === ${JSON.stringify(String(value))})`);
  await evaluate(`(() => {
    const input = document.getElementById(${JSON.stringify(id)});
    const prototype = input.tagName === 'SELECT' ? HTMLSelectElement.prototype : input.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(prototype, 'value').set.call(input, ${JSON.stringify(String(value))});
    input.dispatchEvent(new Event(input.tagName === 'SELECT' ? 'change' : 'input', { bubbles: true }));
  })()`);
}
async function click(selector) { await waitFor(`Boolean(document.querySelector(${JSON.stringify(selector)}))`); await evaluate(`document.querySelector(${JSON.stringify(selector)}).click()`); }
async function login(role) {
  await navigate('/login');
  await fill('username', fixture.users[role].username); await fill('password', fixture.users[role].password);
  await click('.login-panel button[type=submit]');
  await waitFor('Boolean(document.querySelector(".sidebar"))');
}
async function logout() { await click('.sidebar-account button'); await waitFor('Boolean(document.getElementById("username"))'); }
async function chooseLanguage(language) {
  await evaluate(`(() => { const select = document.querySelector('.language-select select'); Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value').set.call(select, ${JSON.stringify(language)}); select.dispatchEvent(new Event('change', { bubbles: true })); })()`);
  await waitFor(`document.documentElement.lang.startsWith(${JSON.stringify(language)})`);
}
async function api(path, options = {}) {
  return evaluate(`(async () => { const response = await fetch('/api/v1' + ${JSON.stringify(path)}, { credentials: 'include', ...${JSON.stringify(options)} }); return { status: response.status, data: await response.json() }; })()`);
}
async function addRecord(path, values, expected) {
  await navigate(path); await click('.page-heading-actions button');
  for (const [key, value] of Object.entries(values)) await fill('field-' + key, value);
  await click('.record-form button[type=submit]');
  await waitFor(`!document.querySelector('.record-form') && document.querySelector('table')?.innerText.includes(${JSON.stringify(expected)})`);
}
await call('Runtime.enable'); await call('Page.enable');
await call('Network.clearBrowserCookies');
await call('Emulation.setDeviceMetricsOverride', { width: 1366, height: 900, deviceScaleFactor: 1, mobile: false });
return { fixture, call, evaluate, waitFor, navigate, fill, click, login, logout, chooseLanguage, api, addRecord, exceptions,
close: async () => { await fetch(`${debugging}/json/close/${target.id}`).catch(() => {}); socket.close(); } };
}

