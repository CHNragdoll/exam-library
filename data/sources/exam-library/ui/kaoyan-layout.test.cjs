const {JSDOM} = require(process.env.EXAM_JSDOM || 'jsdom');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');

const sources = path.resolve(__dirname, '../..');
const script = fs.readFileSync(path.join(__dirname, 'reader.js'), 'utf8');
const css = fs.readFileSync(path.join(__dirname, 'reader.css'), 'utf8');

function originalLayout(year) {
  const file = path.join(sources, `english-exams-web-2026-09-26/kaoyan/papers/${year}-01.htm`);
  const dom = new JSDOM(fs.readFileSync(file, 'utf8'));
  const lines = [];
  for (const page of dom.window.document.querySelectorAll('main .page-wrap')) {
    const groups = new Map();
    for (const node of page.querySelectorAll('svg.text-overlay text[x][y]')) {
      const y = Number(node.getAttribute('y')).toFixed(1);
      if (!groups.has(y)) groups.set(y, []);
      groups.get(y).push([Number(node.getAttribute('x')), node.textContent]);
    }
    for (const parts of groups.values()) {
      parts.sort((a, b) => a[0] - b[0]);
      lines.push([parts[0][0], parts.map(part => part[1]).join('')]);
    }
  }
  const markers = lines.flatMap(([, text]) => {
    const match = /^\s*([A-H])\.\s*(\w.{30,})/.exec(text);
    return match ? [{letter: match[1], marker: '.',
      preview: match[2].replace(/\s+/g, '').toLowerCase().slice(0, 24)}] : [];
  });
  const right = lines.some(([x, text]) => x > 200 && /^\s*Yours,\s*$/.test(text));
  dom.window.close();
  return {letteredParagraphMarkers: markers, emailSignoffRight: right};
}

for (const year of [2024, 2025, 2026]) {
  const file = path.join(sources, `english-exams-reflow-latex/kaoyan/papers/${year}-01.htm`);
  const dom = new JSDOM(fs.readFileSync(file, 'utf8'), {
    url: `file://${file}`, runScripts: 'outside-only', pretendToBeVisual: true
  });
  const {window: w} = dom, d = w.document, main = d.querySelector('main');
  const before = main.textContent;
  Object.defineProperty(w, 'localStorage', {value: {getItem() { return null; }, setItem() {}}});
  w.scrollTo = () => {};
  const config = d.getElementById('exam-reader-config');
  config.textContent = JSON.stringify({...JSON.parse(config.textContent), ...originalLayout(year)});
  w.eval(script);

  const box = main.querySelector('.reader-email-box');
  assert(box, `${year}: source email has an outer box`);
  assert.equal(box.children.length, 4, `${year}: greeting, body, Yours, and Paul have separate lines`);
  assert.match(box.children[0].textContent.trim(), /^(?:Hi|Dear) Li Ming,$/);
  assert(box.children[1].textContent.trim().length > 40);
  assert.equal(box.children[2].textContent.trim(), 'Yours,');
  assert.equal(box.children[3].textContent.trim(), 'Paul');
  assert.match(box.nextElementSibling.textContent.trim(), /^(?:You should|Write your answer).*ANSWER SHEET\.$/);
  assert.match(box.nextElementSibling.nextElementSibling.textContent.trim(), /^Do not use your own name/);
  assert.equal(box.classList.contains('reader-email-right-signoff'), year === 2024,
    `${year}: signature alignment matches source`);
  if (year >= 2025) {
    const labels = [...main.querySelectorAll('.reader-lettered-label')].map(node => node.textContent.trim());
    assert.deepEqual(labels.slice(-8), ['A.', 'B.', 'C.', 'D.', 'E.', 'F.', 'G.', 'H.'],
      `${year}: long passage labels match original punctuation`);
    for (const paragraph of main.querySelectorAll('.reader-lettered-paragraph')) {
      assert(paragraph.querySelector('.reader-lettered-body')?.textContent.trim().length > 30);
    }
  }
  const normalized = text => text.replace(/\b([A-H])[).](?=\s+\w)/g, '$1.');
  assert.equal(normalized(main.textContent), normalized(before), `${year}: wording retained`);
  dom.window.close();
}

assert.match(css, /\.reader-email-box\{border:1px solid/);
assert.match(css, /\.reader-email-right-signoff \.reader-email-signoff/);
console.log('Kaoyan source-layout checks passed for 2024–2026');
