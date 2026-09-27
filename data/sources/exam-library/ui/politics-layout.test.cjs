/* node politics-layout.test.cjs */
const {JSDOM} = require(process.env.EXAM_JSDOM || 'jsdom');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const sources = path.resolve(__dirname, '../..');
const reader = fs.readFileSync(path.join(__dirname, 'reader.js'), 'utf8');

function render(year) {
  const file = path.join(sources, `politics-latex-2003-2023/papers/${year}-questions.htm`);
  const dom = new JSDOM(fs.readFileSync(file, 'utf8'), {
    url: `file://${file}?exam-embed=1`, runScripts: 'outside-only'
  });
  const main = dom.window.document.querySelector('main');
  dom.window.eval(reader);
  return {dom, main};
}

function question(main, number) {
  return [...main.querySelectorAll('p.question')]
    .find(node => new RegExp(`^\\s*${number}[.．]`).test(node.textContent));
}

{
  const {dom, main} = render(2023);
  assert(!/第\s*\d+\s*题\s*（续）/.test(main.textContent), 'page continuation labels are hidden');
  const q18 = question(main, 18);
  const choices = q18.nextElementSibling;
  assert(choices?.matches('.choices'), 'question 18 keeps its options next to its stem');
  assert.deepEqual([...choices.children].map(node => node.querySelector('b')?.textContent),
    ['A.', 'B.', 'C.', 'D.'], 'options split across pages form one set');
  assert(!main.textContent.includes('-3 •'), 'page-three folio is removed from option A');
  assert(!main.textContent.includes('-8 -'), 'page-eight folio is removed from material');
  assert.match(question(main, 35).textContent, /从二〇二〇年到二〇三五年/);
  assert(!question(main, 35).textContent.includes('从二。二O年'));
  for (const number of [35, 36, 37]) {
    const prompts = [...main.querySelectorAll('.reader-politics-subquestion')]
      .filter(node => node.dataset.question === String(number));
    assert.deepEqual(prompts.map(node => node.textContent.trim().slice(0, 3)),
      number === 35 ? ['(1)', '(2)'] : ['（1）', '（2）'],
      `question ${number} has separate numbered prompts`);
  }
  const q36 = question(main, 36);
  assert.match(q36.textContent, /摘自《邓小平文选》第二卷\s*$/);
  assert.match(q36.closest('section').nextElementSibling.firstElementChild.textContent,
    /^材料3 2022年1月30日/);
  dom.window.close();
}

{
  const {dom, main} = render(2016);
  assert(question(main, 35), 'another year remains readable');
  assert(main.textContent.includes('2015 年'), 'ordinary dates remain untouched');
  dom.window.close();
}

console.log('Politics layout checks passed for 2023 and 2016');
