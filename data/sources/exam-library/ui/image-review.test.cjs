const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {pathToFileURL, fileURLToPath} = require('node:url');
const {JSDOM} = require('jsdom');

const page = path.resolve(__dirname, '../image-review.htm');
const markup = fs.readFileSync(page, 'utf8');
const script = fs.readFileSync(path.join(__dirname, 'image-review.js'), 'utf8');
const storageKey = 'exam-library:image-review:v1';

function fixture({denied = false, saved = new Map()} = {}) {
  const dom = new JSDOM(markup, {url:pathToFileURL(page).href, runScripts:'outside-only'});
  const w = dom.window, d = w.document;
  let blob, downloaded = false;
  Object.defineProperty(w, 'localStorage', {value:{
    getItem(key) { if (denied) throw Error('denied'); return saved.get(key) || null; },
    setItem(key, value) { if (denied) throw Error('denied'); saved.set(key, value); }
  }});
  w.Blob = class { constructor(parts) { this.text = parts.join(''); } };
  w.URL.createObjectURL = value => { blob = value; return 'blob:review-test'; };
  w.URL.revokeObjectURL = () => {};
  w.HTMLAnchorElement.prototype.click = function () { downloaded = this.download === 'exam-image-review.json'; };
  w.HTMLDialogElement.prototype.showModal = function () { this.open = true; };
  w.HTMLDialogElement.prototype.close = function () { this.open = false; };
  w.eval(script);
  return {dom, w, d, saved, exportResult() {
    d.querySelector('#export').click();
    assert(downloaded);
    return JSON.parse(blob.text);
  }};
}

const initial = new JSDOM(markup, {url:pathToFileURL(page).href});
const pageData = JSON.parse(initial.window.document.querySelector('#review-data').textContent);
const initialCards = [...initial.window.document.querySelectorAll('.review-item')];
assert.equal(initialCards.length, pageData.length);
assert(pageData.length >= 3);
for (const [index, item] of pageData.entries()) {
  assert.match(item.revision, /^[a-f0-9]{64}$/, `revision missing for ${item.id}`);
  const card = initialCards[index];
  assert.equal(card.dataset.revision, item.revision);
  assert.equal(card.dataset.revised, String(Boolean(item.reviewNote)));
  assert.equal(Boolean(card.querySelector('.review-note')), Boolean(item.reviewNote));
  for (const key of ['original', 'replacement', 'document', 'svgDocument']) {
    assert(fs.existsSync(fileURLToPath(new URL(item[key], pathToFileURL(page)))), [item.id, key]);
  }
}
for (const el of initial.window.document.querySelectorAll('img[src],a[href],link[href],script[src]')) {
  const ref = el.getAttribute('src') || el.getAttribute('href');
  assert(fs.existsSync(fileURLToPath(new URL(ref, pathToFileURL(page)))), ref);
}
assert(initial.window.document.querySelector('.page-header').textContent.includes('同类线条须统一用色并与图例一致'));
initial.window.close();

const records = new Map([[storageKey, JSON.stringify({
  [pageData[0].id]:{decision:'pass', note:'已核对', revision:pageData[0].revision},
  [pageData[1].id]:{decision:'pass', note:'旧图备注', revision:'old-revision'},
  [pageData[2].id]:{decision:'revise', note:'旧版无 revision'}
})]]);
const normal = fixture({saved:records});
const {d, w} = normal;
const cards = [...d.querySelectorAll('.review-item')];
assert.equal(cards[0].querySelector('.decision').value, 'pass', 'same revision retains review');
assert.equal(cards[0].querySelector('.note').value, '已核对');
assert(cards[0].querySelector('.revision-warning').hidden);
for (const [card, note] of [[cards[1], '旧图备注'], [cards[2], '旧版无 revision']]) {
  assert.equal(card.querySelector('.decision').value, 'pending', 'changed or missing revision resets review');
  assert.equal(card.querySelector('.note').value, note, 'review note survives image update');
  assert.equal(card.querySelector('.revision-warning').hidden, false);
  assert(card.querySelector('.revision-warning').textContent.includes('图片已更新，请重新核对'));
}
const staleNote = cards[1].querySelector('.note');
staleNote.value = '补充旧图备注'; staleNote.dispatchEvent(new w.Event('input'));
let persisted = JSON.parse(records.get(storageKey));
assert.equal(persisted[pageData[1].id].decision, 'pending');
assert.equal(persisted[pageData[1].id].note, '补充旧图备注');
assert.equal(persisted[pageData[1].id].revision, pageData[1].revision);
assert.equal(persisted[pageData[1].id].needsRecheck, true, 'editing a note does not approve changed art');
const reopened = fixture({saved:records});
assert.equal(reopened.d.querySelectorAll('.review-item')[1].querySelector('.revision-warning').hidden, false,
  'recheck warning survives reload until a decision is made');
reopened.dom.window.close();
const decision = cards[1].querySelector('.decision');
decision.value = 'pass'; decision.dispatchEvent(new w.Event('change'));
assert(cards[1].querySelector('.revision-warning').hidden);
persisted = JSON.parse(records.get(storageKey));
assert.equal(persisted[pageData[1].id].decision, 'pass');
assert.equal(persisted[pageData[1].id].revision, pageData[1].revision);
assert.equal(persisted[pageData[1].id].needsRecheck, undefined);
const reviewedAgain = fixture({saved:records});
assert.equal(reviewedAgain.d.querySelectorAll('.review-item')[1].querySelector('.decision').value, 'pass');
reviewedAgain.dom.window.close();

const revisedButton = d.querySelector('#revised-only');
revisedButton.click();
assert.equal(revisedButton.getAttribute('aria-pressed'), 'true');
assert.deepEqual(cards.filter(card => !card.hidden).map(card => card.dataset.id),
  cards.filter(card => card.dataset.revised === 'true').map(card => card.dataset.id));
revisedButton.click();
const state = d.querySelector('#state');
state.value = 'pass'; state.dispatchEvent(new w.Event('change'));
assert(cards.filter(card => !card.hidden).every(card => card.querySelector('.decision').value === 'pass'));
state.value = 'all'; state.dispatchEvent(new w.Event('change'));
const category = d.querySelector('#category');
category.value = cards[0].dataset.category; category.dispatchEvent(new w.Event('change'));
assert(cards.filter(card => !card.hidden).every(card => card.dataset.category === category.value));
category.value = 'all'; category.dispatchEvent(new w.Event('change'));
const search = d.querySelector('#search');
search.value = '图片已更新，请重新核对'; search.dispatchEvent(new w.Event('input'));
assert(cards.every(card => card.hidden), 'hidden warning is not searchable content');
search.value = 'unmatchable-review-test'; search.dispatchEvent(new w.Event('input'));
assert(cards.every(card => card.hidden)); assert.equal(d.querySelector('#empty').hidden, false);
const output = normal.exportResult();
assert.equal(output.pathBase, 'data/sources/exam-library/');
assert.equal(output.images.length, cards.length, 'export includes hidden cards');
assert.equal(output.images[0].revision, pageData[0].revision);
assert.equal(output.images[1].revision, pageData[1].revision);
assert.equal(output.images[1].note, '补充旧图备注');
cards[0].querySelector('.zoom').click();
assert(d.querySelector('#zoom-dialog').open);
assert.equal(d.querySelector('#zoom-image').src, cards[0].querySelector('img').src);
const scale = d.querySelector('#zoom-scale');
scale.value = '2'; scale.dispatchEvent(new w.Event('change'));
assert.equal(d.querySelector('#zoom-image').style.width, '200%');
d.querySelector('#close-zoom').click(); assert.equal(d.querySelector('#zoom-dialog').open, false);
normal.dom.window.close();
console.log(`PASS image review ${pageData.length} pairs / revision migration, filters, export, zoom (DOM only)`);

const blocked = fixture({denied:true});
const blockedCard = blocked.d.querySelector('.review-item');
assert(blocked.d.querySelector('#storage-status').textContent.includes('未允许'));
blockedCard.querySelector('.decision').value = 'revise';
blockedCard.querySelector('.decision').dispatchEvent(new blocked.w.Event('change'));
blockedCard.querySelector('.note').value = '仍可导出';
blockedCard.querySelector('.note').dispatchEvent(new blocked.w.Event('input'));
assert(blocked.d.querySelector('#storage-status').textContent.includes('导出'));
const blockedExport = blocked.exportResult();
assert.equal(blockedExport.images[0].decision, 'revise');
assert.equal(blockedExport.images[0].note, '仍可导出');
assert.equal(blockedExport.images[0].revision, pageData[0].revision);
blocked.dom.window.close();
console.log(`PASS image review ${pageData.length} pairs / storage denied (DOM only)`);
