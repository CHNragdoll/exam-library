const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {pathToFileURL, fileURLToPath} = require('node:url');
const {JSDOM} = require('jsdom');

const page = path.resolve(__dirname, '../crop-review.htm');
const markup = fs.readFileSync(page, 'utf8');
const script = fs.readFileSync(path.join(__dirname, 'crop-review.js'), 'utf8');
const initial = new JSDOM(markup, {url: pathToFileURL(page).href});
const entries = JSON.parse(initial.window.document.querySelector('#crop-review-data').textContent);
const cards = [...initial.window.document.querySelectorAll('.review-item')];
assert.equal(cards.length, entries.length);
assert.equal(cards.length, 35);
for (const card of cards) {
  assert.match(card.dataset.revision, /^[a-f0-9]{64}$/);
  assert.equal(card.querySelectorAll('.crop-box').length, 2);
}
for (const element of initial.window.document.querySelectorAll('img[src],a[href],link[href],script[src]')) {
  const ref = element.getAttribute('src') || element.getAttribute('href');
  assert(fs.existsSync(fileURLToPath(new URL(ref, pathToFileURL(page)))), ref);
}
assert(!cards.some(card => card.dataset.id.includes('cet4-2015-06-02')), 'unchanged clear figure excluded');
initial.window.close();

const key = 'exam-library:crop-review:v1';
const storage = new Map([[key, JSON.stringify({
  [entries[0].id]: {revision: entries[0].revision, decision: 'pass', note: 'checked'},
  [entries[1].id]: {revision: 'old', decision: 'pass', note: 'recheck'}
})]]);
const dom = new JSDOM(markup, {url: pathToFileURL(page).href, runScripts: 'outside-only'});
const w = dom.window, d = w.document;
let blob, download;
Object.defineProperty(w, 'localStorage', {value: {
  getItem(name) { return storage.get(name) || null; },
  setItem(name, value) { storage.set(name, value); }
}});
w.Blob = class { constructor(parts) { this.text = parts.join(''); } };
w.URL.createObjectURL = value => { blob = value; return 'blob:test'; };
w.URL.revokeObjectURL = () => {};
w.HTMLAnchorElement.prototype.click = function () { download = this.download; };
w.HTMLDialogElement.prototype.showModal = function () { this.open = true; };
w.HTMLDialogElement.prototype.close = function () { this.open = false; };
w.eval(script);
const active = [...d.querySelectorAll('.review-item')];
assert.equal(active[0].querySelector('.decision').value, 'pass');
assert.equal(active[1].querySelector('.decision').value, 'pending');
assert.equal(active[1].querySelector('.note').value, 'recheck');
assert.equal(active[1].querySelector('.revision-warning').hidden, false);
active[1].querySelector('.note').dispatchEvent(new w.Event('input'));
assert.equal(active[1].querySelector('.revision-warning').hidden, false, 'note edit does not approve changed crop');
const category = d.querySelector('#category');
category.value = 'english'; category.dispatchEvent(new w.Event('change'));
assert(active.some(card => card.hidden));
assert(active.filter(card => !card.hidden).every(card => card.dataset.category === 'english'));
category.value = 'all'; category.dispatchEvent(new w.Event('change'));
const state = d.querySelector('#state');
state.value = 'pass'; state.dispatchEvent(new w.Event('change'));
assert.deepEqual(active.filter(card => !card.hidden).map(card => card.dataset.id), [entries[0].id]);
state.value = 'all'; state.dispatchEvent(new w.Event('change'));
active[0].querySelector('.zoom').click();
assert(d.querySelector('#zoom-dialog').open);
assert(d.querySelector('#zoom-body .page-stage .old-box'));
d.querySelector('#close-zoom').click();
assert(!d.querySelector('#zoom-dialog').open);
d.querySelector('#export').click();
assert.equal(download, 'crop-review-audit.json');
const exported = JSON.parse(blob.text);
assert.equal(exported.entries.length, entries.length);
assert.equal(exported.entries[0].decision, 'pass');
dom.window.close();
console.log('PASS crop review assets, decisions, filters, zoom and export');
