/* node math-layout.test.cjs; checks the actual 2009–2019 math3 question pages. */
const {JSDOM} = require(process.env.EXAM_JSDOM || 'jsdom');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');

const root = path.resolve(__dirname, '../..');
const script = fs.readFileSync(path.join(__dirname, 'reader.js'), 'utf8');
const css = fs.readFileSync(path.join(__dirname, 'reader.css'), 'utf8');
const marker = /（[ⅠⅡⅢⅣⅤⅥ]）/g;
let subquestions = 0;

for (let year = 2009; year <= 2019; year++) {
  const file = path.join(root, `math3-latex-2009-2019/papers/${year}-questions.htm`);
  const dom = new JSDOM(fs.readFileSync(file, 'utf8'), {
    url: `file://${file}?exam-embed=1`, runScripts: 'outside-only'
  });
  const {window} = dom;
  const main = window.document.querySelector('main');
  const paragraphBefore = [...main.querySelectorAll('.paragraph')]
    .map(node => node.textContent.replace(/[。.]/g, '')).join('');
  const optionBefore = [...main.querySelectorAll('.math-option')]
    .map(node => node.querySelector('.math-option-content').textContent.replace(/[。.]/g, ''));
  const labelsBefore = [...main.querySelectorAll('.math-option-label')].map(node => node.textContent.trim());
  const texBefore = [...main.querySelectorAll('.tex-source')].map(node => node.textContent);
  const formulaCount = main.querySelectorAll('.formula').length;
  const markerCount = [...main.querySelectorAll('.paragraph')]
    .reduce((sum, paragraph) => sum + [...paragraph.textContent.matchAll(marker)].length, 0);
  window.eval(script);
  const pieces = [...main.querySelectorAll('.reader-math-subquestion')];
  assert.equal(pieces.length, markerCount, `${year}: every Roman-numbered prompt starts a block`);
  assert(pieces.every(piece => /^（[ⅠⅡⅢⅣⅤⅥ]）/.test(piece.textContent.trimStart())),
    `${year}: subquestion labels are at the beginning of their blocks`);
  assert.equal([...main.querySelectorAll('.paragraph')]
    .map(node => node.textContent.replace(/[。.]/g, '')).join(''), paragraphBefore,
    `${year}: question wording is preserved`);
  assert.deepEqual([...main.querySelectorAll('.math-option')]
    .map(node => node.querySelector('.math-option-content').textContent.replace(/[。.]/g, '')),
  optionBefore, `${year}: option wording is preserved`);
  assert.deepEqual([...main.querySelectorAll('.math-option-label')]
    .map(node => node.dataset.sourceLabel), labelsBefore,
  `${year}: each original option label stays available`);
  assert.deepEqual([...main.querySelectorAll('.tex-source')].map(node => node.textContent), texBefore,
    `${year}: original LaTeX remains untouched`);
  assert.equal(main.querySelectorAll('.formula').length, formulaCount,
    `${year}: no formula is lost while splitting subquestions`);
  assert([...main.querySelectorAll('.paragraph, .math-option-content')]
    .every(node => !node.textContent.includes('。')), `${year}: displayed question prose uses full stops`);
  assert([...main.querySelectorAll('.math-option-content')]
    .every(node => !/[。. ]\s*$/.test(node.textContent.trim())),
  `${year}: option content has no terminal full stop`);
  assert([...main.querySelectorAll('.math-option-label')]
    .every(node => /^[A-D]\.$/.test(node.textContent.trim())),
  `${year}: option labels display as A. through D.`);
  assert([...main.querySelectorAll('.math-options')]
    .every(node => node.querySelectorAll(':scope > .math-option').length === 4),
  `${year}: PDF page breaks do not split a question's four choices`);
  if (year === 2019) {
    const firstOptions = main.querySelector('.math-options');
    assert(firstOptions.classList.contains('reader-math-four-column'),
      '2019: four short choices share one row');
    assert.deepEqual([...firstOptions.querySelectorAll('.math-option-label')]
      .map(node => node.textContent.trim()), ['A.', 'B.', 'C.', 'D.']);
    for (const group of [...main.querySelectorAll('.math-options')].slice(0, 4)) {
      assert.equal(group.style.getPropertyValue('--reader-math-question-indent'), '2.6em',
        '2019: option label starts after the one-digit question number');
    }
    for (const [number, expected] of [[21, 2], [22, 3]]) {
      const question = [...main.querySelectorAll('.paragraph.question')]
        .find(node => node.textContent.trimStart().startsWith(`（${number}）`));
      assert(question, `2019: question ${number} exists`);
      const found = [];
      for (let node = question.nextElementSibling;
           node && !node.matches('.paragraph.question'); node = node.nextElementSibling) {
        if (node.matches('.reader-math-subquestion')) found.push(node);
      }
      assert.equal(found.length, expected, `2019: question ${number} has separate subquestion lines`);
    }
  }
  subquestions += pieces.length;
  window.close();
}

assert.match(css, /\.paragraph\.reader-math-subquestion\{display:block/);
assert.match(css, /margin-inline-start:var\(--reader-math-question-indent,0\)/);
console.log(`math3 layout: 11 papers, ${subquestions} subquestions verified`);
