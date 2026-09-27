/* node reader-continuations.test.cjs */
const {JSDOM} = require(process.env.EXAM_JSDOM || 'jsdom');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const sources = path.resolve(__dirname, '../..');
const reader = fs.readFileSync(path.join(__dirname, 'reader.js'), 'utf8');

function render(relative) {
  const file = path.join(sources, relative);
  const dom = new JSDOM(fs.readFileSync(file, 'utf8'), {
    url: `file://${file}?exam-embed=1`, runScripts: 'outside-only'
  });
  const {document} = dom.window;
  const main = document.querySelector('main');
  const config = document.getElementById('exam-reader-config');
  const payload = JSON.parse(config.textContent);
  payload.imageRedraws = [];
  config.textContent = JSON.stringify(payload);
  const before = main.textContent.replace(/\s+/g, '');
  dom.window.eval(reader);
  assert.equal(main.textContent.replace(/\s+/g, ''), before,
    'joining extracted blocks retains every source character in order');
  return {dom, main};
}

{
  const {dom, main} = render('english-exams-reflow-latex/cet6/papers/2015-12-02.htm');
  const sections = [...main.querySelectorAll('section[data-source-page]')];
  const i = [...main.querySelectorAll('.reader-lettered-paragraph')]
    .find(node => node.querySelector('.reader-lettered-label')?.textContent === 'I)');
  const j = [...main.querySelectorAll('.reader-lettered-paragraph')]
    .find(node => node.querySelector('.reader-lettered-label')?.textContent === 'J)');
  assert(i && j, 'the source I) and J) passages remain separate');
  assert.match(i.textContent, /new energy industry are specialists/);
  assert.match(i.textContent, /industry\), and education, like any other complicated endeavor/);
  assert.match(i.textContent, /before the builders and operators/);
  assert.match(i.textContent, /In some cases, colleges and universities/);
  assert.match(i.textContent, /adding another layer of difficulty\.$/);
  assert(!i.textContent.includes('By far the biggest type'), 'J) does not merge into I)');
  assert(![...sections[5].querySelectorAll('p.paragraph')]
    .some(node => /^industry are specialists|^and education|^to be trained|^builders and operators|^cases, colleges/.test(node.textContent)),
    'page-six line fragments no longer become separate paragraphs');

  const sectionB = [...main.querySelectorAll('h2.heading')]
    .find(node => node.textContent.trim() === 'Section B');
  const directions = sectionB.nextElementSibling;
  assert(directions.matches('p.paragraph'));
  assert.match(directions.textContent, /Both the passage and the questions will be spoken only once/);
  assert.match(directions.textContent, /four choices marked A/);
  assert(![...main.querySelectorAll('h2.heading')]
    .some(node => /^passage and the questions will be spoken only once/.test(node.textContent.trim())),
    'OCR continuation is no longer a false heading');
  dom.window.close();
}

{
  const {dom, main} = render('english-exams-reflow-latex/cet6/papers/2017-12-01.htm');
  const g = [...main.querySelectorAll('.reader-lettered-paragraph')]
    .find(node => node.querySelector('.reader-lettered-label')?.textContent === 'G)');
  assert(g && /agenda\. Take email, for example/.test(g.textContent),
    'the same page-break extraction error is repaired in another paper');
  dom.window.close();
}

console.log('reader continuation checks passed');
