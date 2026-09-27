const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {JSDOM} = require(process.env.EXAM_JSDOM || 'jsdom');

const root = path.resolve(__dirname, '../..');
const mathScript = fs.readFileSync(path.join(__dirname, 'answer-math.js'), 'utf8');
const answerScript = fs.readFileSync(path.join(__dirname, 'answers.js'), 'utf8');
const vendor = fs.readFileSync(path.join(__dirname, 'vendor/mathjax-3.2.2-tex-svg-full.js'), 'utf8');
const documents = JSON.parse(fs.readFileSync(path.join(root, 'exam-library/documents.json'), 'utf8'));

function fixture(id) {
  const doc = documents.find(item => item.id === id);
  assert(doc, id);
  const reflow = path.join(root, 'exam-library', doc.reflow);
  const paper = JSON.parse(fs.readFileSync(path.join(root, 'exam-library/structured/papers',
    doc.category, path.basename(reflow, '.htm') + '.json'), 'utf8'));
  return {doc, reflow, paper};
}

function browser(markup, url) {
  const dom = new JSDOM(markup, {runScripts: 'outside-only', url});
  const {window: w} = dom;
  const d = w.document;
  let loads = 0;
  const append = d.head.append.bind(d.head);
  d.head.append = (...nodes) => {
    const result = append(...nodes);
    for (const node of nodes) {
      if (node.tagName === 'SCRIPT' && /mathjax-3\.2\.2-tex-svg-full\.js$/.test(node.src)) {
        loads++;
        setTimeout(() => { w.eval(vendor); node.dispatchEvent(new w.Event('load')); }, 0);
      }
    }
    return result;
  };
  return {dom, w, d, loads: () => loads};
}

async function rendered(panel) {
  for (let attempt = 0; attempt < 40; attempt++) {
    if (panel.dataset.examMathRendered === 'true') return;
    await new Promise(resolve => setTimeout(resolve, 50));
  }
  assert.fail('local MathJax did not finish rendering the answer');
}

function open(w, panel) {
  panel.open = true;
  panel.dispatchEvent(new w.Event('toggle'));
}

async function checkStructuredMath() {
  const page = path.join(root, 'exam-library/structured/papers/math3/2019-questions.htm');
  const {dom, w, d, loads} = browser(fs.readFileSync(page, 'utf8'),
    'http://localhost:8765/exam-library/structured/papers/math3/2019-questions.htm');
  assert(d.querySelector('script[src*="answer-math.js"]'), 'generated structured page loads answer math');
  const panel = d.querySelector('#q-9-1 details.answer-panel');
  assert(panel?.textContent.includes('\\('));
  w.eval(mathScript);
  open(w, panel);
  await rendered(panel);
  assert(panel.querySelector('.answer-field mjx-container svg path'), 'math3 structured answer has rendered SVG');
  const vectors = d.querySelector('#q-20-1 details.answer-panel');
  assert(vectors?.textContent.includes('\\boldsymbol'));
  open(w, vectors);
  await rendered(vectors);
  assert(vectors.querySelector('.answer-field mjx-container svg path'));
  assert.equal(vectors.querySelector('[fill="red"], [stroke="red"], [data-mml-node="merror"]'), null,
    'math3 q20 bold Greek vectors render without undefined commands');
  assert(!vectors.textContent.includes('\\boldsymbol'), 'raw boldsymbol command is absent');
  assert.equal(loads(), 1);
  dom.window.close();
}

async function checkReflow(id, questionNumber, {dropSource = false, failFetch = false, math = true, bold = false} = {}) {
  const {doc, reflow, paper} = fixture(id);
  const pageUrl = 'http://localhost:8765/' + path.relative(root, reflow).replaceAll(path.sep, '/');
  const {dom, w, d, loads} = browser(fs.readFileSync(reflow, 'utf8'), pageUrl);
  assert(d.querySelector('script[src*="answer-math.js"]'), id + ' generated reader loads answer math');
  const configNode = d.getElementById('exam-reader-config');
  const config = JSON.parse(configNode.textContent);
  const questions = paper.questions.filter(item => item.recordType === 'question');
  const index = questions.findIndex(item => item.number === questionNumber);
  assert(index >= 0);
  assert.equal(config.structuredAnswers.length, questions.length);
  if (dropSource) {
    delete config.structuredAnswers[index].answer.sourceHref;
    configNode.textContent = JSON.stringify(config);
  }
  if (failFetch) w.fetch = async () => { throw new Error('test source unavailable'); };
  w.eval(mathScript);
  w.eval(answerScript);
  d.dispatchEvent(new w.Event('DOMContentLoaded'));
  const panel = [...d.querySelectorAll('main .exam-answer-panel')][index];
  assert(panel && !panel.open);
  open(w, panel);
  if (math) {
    await rendered(panel);
    assert(panel.querySelector('.exam-answer-field mjx-container svg path'),
      `${id} #${questionNumber} renders formula even without the original answer page`);
    if (bold) {
      assert.equal(panel.querySelector('[fill="red"], [stroke="red"], [data-mml-node="merror"]'), null);
      assert(!panel.textContent.includes('\\boldsymbol'));
    }
    assert.equal(loads(), 1);
  } else {
    await new Promise(resolve => setTimeout(resolve, 30));
    assert.equal(loads(), 0, `${id} does not load math for plain or missing answers`);
  }
  dom.window.close();
}

async function checkUnsafeTeX() {
  const markup = '<!doctype html><html><head><script src="http://localhost:8765/exam-library/ui/answer-math.js"></script></head><body>' +
    '<details class="exam-answer-panel"><summary>答案</summary><p>\\(\\href{javascript:alert(1)}{x}\\) \\(\\htmlClass{bad}{y}\\)</p></details></body></html>';
  const {dom, w, d} = browser(markup, 'http://localhost:8765/test.htm');
  w.eval(mathScript);
  const panel = d.querySelector('details');
  open(w, panel);
  await rendered(panel);
  assert.equal(panel.querySelector('[href^="javascript:"], .bad'), null,
    'restricted TeX packages cannot create an unsafe link or class');
  dom.window.close();
}

(async () => {
  await checkStructuredMath();
  await checkReflow('math3:2019-questions', '9', {dropSource: true});
  await checkReflow('math3:2019-questions', '20', {dropSource: true, bold: true});
  await checkReflow('cs408:2025-questions', '41', {failFetch: true});
  await checkReflow('politics:2023-questions', '1', {math: false});
  await checkReflow('kaoyan:2026-01', '1', {math: false});
  await checkUnsafeTeX();
  console.log('answer-math: math3 q20 boldsymbol in structured/reflow, 408 fallback, politics, English, safe TeX passed');
})().catch(error => { console.error(error); process.exitCode = 1; });
