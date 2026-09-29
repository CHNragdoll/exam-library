const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {JSDOM} = require(process.env.EXAM_JSDOM || 'jsdom');

const root = path.resolve(__dirname, '..');
const markup = fs.readFileSync(path.join(__dirname, 'full-paper.htm'), 'utf8');
const script = fs.readFileSync(path.join(__dirname, 'practice-version-nav.js'), 'utf8');
const documents = JSON.parse(fs.readFileSync(path.join(root, 'documents.json'), 'utf8'));

async function setup(id) {
  const dom = new JSDOM(markup, {
    url: `http://127.0.0.1:8765/exam-library/practice/full-paper.htm?paper=${encodeURIComponent(id)}`,
    runScripts: 'outside-only'
  });
  dom.window.fetch = async () => ({ok: true, json: async () => documents});
  dom.window.eval(script);
  await new Promise(resolve => setTimeout(resolve, 0));
  return dom;
}

(async () => {
  const dom = await setup('kaoyan:2026-01');
  const nav = dom.window.document.getElementById('paper-versions');
  assert.equal(nav.hidden, false);
  assert.deepEqual([...nav.children].map(node => node.textContent),
    ['SVG 原版', 'LaTeX 重排', '整卷刷题', '并排对比']);
  assert.equal(nav.querySelector('[aria-current="page"]').tagName, 'SPAN');
  assert.match(nav.lastElementChild.href,
    /\/english-exams-reflow-latex\/kaoyan\/papers\/2026-01\.htm\?exam-compare=1$/);
  assert.match(nav.firstElementChild.href,
    /\/english-exams-web-2026-09-26\/kaoyan\/papers\/2026-01\.htm$/);
  dom.window.close();

  const answers = await setup('politics:2023-answers');
  assert.equal(answers.window.document.getElementById('paper-versions').hidden, true);
  answers.window.close();
  console.log('Practice whole-paper version navigation passed');
})().catch(error => { console.error(error); process.exitCode = 1; });
