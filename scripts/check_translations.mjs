import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

let baseline;
for (const language of ['en', 'fa', 'ps']) {
  const text = readFileSync(new URL(`../frontend/src/i18n/${language}.json`, import.meta.url), 'utf8');
  const entries = [...text.matchAll(/^\s*"([^"]+)":/gm)].map(match => match[1]);
  assert.equal(new Set(entries).size, entries.length, `${language}: duplicate translation keys`);
  const catalog = JSON.parse(text);
  const keys = Object.keys(catalog).sort();
  if (!baseline) baseline = keys;
  assert.deepEqual(keys, baseline, `${language}: missing/extra translation keys`);
  for (const [key, value] of Object.entries(catalog)) {
    assert.equal(typeof value === 'string' && value.trim().length > 0 && !value.includes('\ufffd') && !value.includes('???'), true, `${language}: invalid translation ${key}`);
  }
}
console.log(`PASS: ${baseline.length} matching, non-empty, unique translation keys in English/Dari/Pashto`);
