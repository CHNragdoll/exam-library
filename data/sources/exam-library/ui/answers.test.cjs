const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {JSDOM} = require(process.env.EXAM_JSDOM || 'jsdom');

const script = fs.readFileSync(path.join(__dirname, 'answers.js'), 'utf8');
const answers = [
  {sourceBlocks: ['b-1-1', 'b-1-2', 'b-1-3'], answer: {
    status: 'explicit', value: 'B', explanation: '因为 x < 2。', solution: '第一步\n第二步'
  }},
  {sourceBlocks: ['b-1-4'], answer: {status: 'missing'}},
  {sourceBlocks: ['b-1-5'], answer: {status: 'ambiguous', ambiguityReason: '题号重复，无法可靠对应'}}
];
const markup = `<!doctype html><html><body><main><section data-source-page="1">
  <p class="question" id="q1">1. <span class="formula" data-tex="x^2"><svg id="formula"></svg></span></p>
  <ul class="options" id="choices"><li>A</li><li>B</li></ul>
  <pre class="tex-source" hidden>source only</pre>
  <p class="question" id="q2">2. 第二题</p>
  <p class="question" id="q3">3. 第三题</p>
</section></main><script id="exam-reader-config" type="application/json">${JSON.stringify({mode: 'reflow', structuredAnswers: answers})}</script></body></html>`;
const dom = new JSDOM(markup, {runScripts: 'outside-only', url: 'file:///exam.htm'});
const {window: w} = dom;
const d = w.document;
const main = d.querySelector('main');
const originalIds = [...main.querySelectorAll('[id]')].map(node => node.id);
const originalNodes = originalIds.map(id => d.getElementById(id));
const originalTexts = originalNodes.map(node => node.textContent);
const formula = d.getElementById('formula');
w.eval(script);
// Reader code can wrap choices after answers.js records the original positions.
const row = d.createElement('div');
row.className = 'reader-listening-question';
d.getElementById('q1').before(row);
row.append(d.getElementById('q1'), d.getElementById('choices'));
d.dispatchEvent(new w.Event('DOMContentLoaded'));

const panels = [...main.querySelectorAll('.exam-answer-panel')];
assert.equal(panels.length, 3);
assert(panels.every(panel => !panel.open && panel.querySelector('summary').textContent === '点击查看答案'));
assert.equal(row.nextElementSibling, panels[0], 'answer follows the full question and choices');
assert.equal(d.getElementById('q2').nextElementSibling, panels[1]);
assert.equal(d.getElementById('q3').nextElementSibling, panels[2]);
assert.deepEqual([...panels[0].querySelectorAll('strong')].map(node => node.textContent),
  ['标准答案', '解答过程', '解析']);
assert.match(panels[0].textContent, /第一步\n第二步/);
assert.match(panels[1].textContent, /暂无可用答案/);
assert.match(panels[2].textContent, /题号重复/);
assert.deepEqual([...main.querySelectorAll('[id]')].map(node => node.id), originalIds);
assert.deepEqual(originalNodes.map(node => node.textContent), originalTexts);
assert(originalNodes.every((node, index) => d.getElementById(originalIds[index]) === node));
assert.equal(d.getElementById('formula'), formula);
w.eval(script);
d.dispatchEvent(new w.Event('DOMContentLoaded'));
assert.equal(main.querySelectorAll('.exam-answer-panel').length, 3, 'idempotent');
panels[0].querySelector('summary').click();
assert.equal(panels[0].querySelector('summary').textContent, '收起答案');
dom.window.close();
async function checkReal408Answer() {
  const sources = path.resolve(__dirname, '../..');
  const questionFile = path.join(sources, 'cs408-latex-2009-2017/papers/2025-questions.htm');
  const answerFile = path.join(sources, 'cs408-answers-latex-2016-2025/papers/2025-answers.htm');
  const paper = JSON.parse(fs.readFileSync(path.join(__dirname, '../structured/papers/cs408/2025-questions.json'), 'utf8'));
  const questions = paper.questions.filter(item => item.recordType === 'question');
  const questionIndex = questions.findIndex(item => item.number === '41');
  const question = questions[questionIndex];
  assert(question);
  const page = new JSDOM(fs.readFileSync(questionFile, 'utf8'), {
    runScripts: 'outside-only', url: 'http://localhost:8765/cs408-latex-2009-2017/papers/2025-questions.htm'
  });
  const {window: browser} = page;
  const document = browser.document;
  const originalQuestion = [...document.querySelectorAll('main p.question')]
    .find(node => /^41[.．、]/.test(node.textContent.trim()));
  const originalFormula = originalQuestion.querySelector('svg');
  const source = fs.readFileSync(answerFile, 'utf8').replace('41．【答案要点】',
    '41．【答案要点】<span onclick="window.__unsafe=1">安全测试</span><img src="javascript:alert(1)" onerror="window.__unsafe=1"><script>window.__unsafe=1</script>');
  let fetches = 0;
  browser.fetch = async url => {
    assert.match(url, /cs408-answers-latex-2016-2025\/papers\/2025-answers\.htm$/);
    fetches++;
    return {ok: true, text: async () => source};
  };
  const generatedConfig = JSON.parse(document.getElementById('exam-reader-config').textContent);
  assert.equal(generatedConfig.structuredAnswers.length, questions.length, 'generated config covers every question');
  const configuredAnswer = generatedConfig.structuredAnswers[questionIndex].answer;
  assert.deepEqual(generatedConfig.structuredAnswers[questionIndex].sourceBlocks, question.sourceBlocks);
  assert.match(configuredAnswer.sourceHref, /cs408-answers-latex-2016-2025\/papers\/2025-answers\.htm$/,
    'production config links the actual answer page');
  assert.deepEqual(configuredAnswer.sourceBlocks, question.answer.sourceBlocks);
  browser.eval(fs.readFileSync(path.join(__dirname, 'code-highlight.js'), 'utf8'));
  browser.eval(script);
  document.dispatchEvent(new browser.Event('DOMContentLoaded'));
  const panel = [...document.querySelectorAll('main .exam-answer-panel')][questionIndex];
  assert(panel && !panel.open);
  panel.open = true;
  panel.dispatchEvent(new browser.Event('toggle'));
  await new Promise(resolve => setTimeout(resolve, 0));
  const rich = panel.querySelector(':scope > .exam-answer-original');
  assert(rich, 'question-owned original answer is the primary answer');
  assert.equal(panel.querySelector('.exam-answer-original-disclosure'), null);
  assert(rich.querySelectorAll('.formula svg path').length > 0, 'pre-rendered formula SVG is visible');
  const code = rich.querySelector('pre.code > code');
  assert(code, 'source code is in a real code block');
  assert.match(code.textContent, /void calMulMax\(int A\[\], int res\[\], int n\)\n\{/);
  assert.match(code.textContent, /\n    int i, Max, Min;/);
  assert(code.querySelector('.code-token'), 'existing highlighter runs on restored code');
  assert.equal(rich.querySelector('script, img[src^="javascript:"]'), null);
  assert.equal(rich.querySelector('[onclick], [onerror]'), null);
  assert.equal(browser.__unsafe, undefined);
  assert.match(rich.textContent, /第一步|算法的基本设计思想/);
  assert.equal(fetches, 1);
  assert(originalQuestion.isConnected);
  assert.equal(originalQuestion.querySelector('svg'), originalFormula);
  page.window.close();
}

async function checkReal2019MathAnswer() {
  const sources = path.resolve(__dirname, '../..');
  const questionsFile = path.join(sources, 'math3-latex-2009-2019/papers/2019-questions.htm');
  const answersFile = path.join(sources, 'math3-latex-2009-2019/papers/2019-answers.htm');
  const page = new JSDOM(fs.readFileSync(questionsFile, 'utf8'), {
    runScripts: 'outside-only', url: 'http://localhost:8765/math3-latex-2009-2019/papers/2019-questions.htm'
  });
  const {window: browser} = page;
  const document = browser.document;
  const config = JSON.parse(document.getElementById('exam-reader-config').textContent);
  assert.equal(config.structuredAnswers[0].answer.value, 'C');
  assert.equal(config.structuredAnswers[1].answer.value, 'D');
  let fetches = 0;
  browser.fetch = async url => {
    assert.match(url, /math3-latex-2009-2019\/papers\/2019-answers\.htm$/);
    fetches++;
    return {ok: true, text: async () => fs.readFileSync(answersFile, 'utf8')};
  };
  browser.eval(script);
  document.dispatchEvent(new browser.Event('DOMContentLoaded'));
  const panels = [...document.querySelectorAll('main .exam-answer-panel')];
  assert(panels.length >= 2);
  const first = panels[0];
  first.open = true;
  first.dispatchEvent(new browser.Event('toggle'));
  assert.equal(fetches, 0, 'opening question 1 never fetches the full-section answer');
  assert.equal(first.querySelector('.exam-answer-original'), null);
  assert.match(first.querySelector(':scope > .exam-answer-field').textContent, /标准答案\s*C/);
  assert.doesNotMatch(first.querySelector(':scope > .exam-answer-field').textContent, /（8）A/);
  assert.match(panels[1].querySelector(':scope > .exam-answer-field').textContent, /标准答案\s*D/);
  assert.equal(first.querySelector('.exam-answer-original'), null);
  assert.equal(first.querySelector('.exam-answer-original-disclosure'), null);
  assert.equal(fetches, 0, 'a shared full-section answer is never fetched for one question');
  assert.match(first.querySelector(':scope > .exam-answer-field').textContent, /标准答案\s*C/);
  page.window.close();
}

async function checkReal2017Cs408Answers() {
  const sources = path.resolve(__dirname, '../..');
  const questionFile = path.join(sources, 'cs408-latex-2009-2017/papers/2017-questions.htm');
  const answerFile = path.join(sources, 'cs408-answers-latex-2016-2025/papers/2017-answers.htm');
  const page = new JSDOM(fs.readFileSync(questionFile, 'utf8'), {
    runScripts: 'outside-only', url: 'http://localhost:8765/cs408-latex-2009-2017/papers/2017-questions.htm'
  });
  const {window: browser} = page;
  const document = browser.document;
  const config = JSON.parse(document.getElementById('exam-reader-config').textContent);
  const questions = JSON.parse(fs.readFileSync(path.join(__dirname,
    '../structured/papers/cs408/2017-questions.json'), 'utf8')).questions
    .filter(item => item.recordType === 'question');
  const index = number => questions.findIndex(item => item.number === number);
  const source = fs.readFileSync(answerFile, 'utf8');
  let fetches = 0;
  browser.fetch = async url => {
    assert.match(url, /cs408-answers-latex-2016-2025\/papers\/2017-answers\.htm$/);
    fetches++;
    return {ok: true, text: async () => source};
  };
  browser.eval(fs.readFileSync(path.join(__dirname, 'code-highlight.js'), 'utf8'));
  browser.eval(script);
  document.dispatchEvent(new browser.Event('DOMContentLoaded'));
  const panels = [...document.querySelectorAll('main .exam-answer-panel')];
  assert.equal(panels.length, questions.length);
  const q46 = panels[index('46')];
  const solution = config.structuredAnswers[index('46')].answer.solution;
  assert(solution.includes('semaphore mutex_y1=1;'));
  assert.equal(q46.querySelector('.exam-answer-field pre.code'), null);
  q46.open = true;
  q46.dispatchEvent(new browser.Event('toggle'));
  await new Promise(resolve => setTimeout(resolve, 0));
  const rich46 = q46.querySelector(':scope > .exam-answer-original');
  const code = rich46?.querySelector('pre.code > code');
  assert(code, 'q46 uses the source-backed code block in the primary answer');
  assert.match(code.textContent, /semaphore mutex_y1=1;[^\n]*\nsemaphore mutex_y2=1;/);
  assert.match(code.textContent, /thread1 \{\n    cnum w;\n    wait\(mutex_y1\);/);
  assert.equal((rich46.textContent.match(/semaphore mutex_y1=1;/g) || []).length, 1);
  assert.equal(q46.querySelector('.exam-answer-original-disclosure'), null);
  const table = rich46.querySelector('.table-scroll table');
  assert(table, 'q46 grading rubric remains a table');
  assert.equal(table.querySelectorAll('tr').length, 4);
  assert.match(table.textContent, /thread1 和 thread2/);
  assert.match(rich46.textContent, /若考生仅使用一个互斥信号量/);
  assert(code.querySelector('.code-token'), 'existing code highlighting applies to restored source');

  const q47 = panels[index('47')];
  assert.match(config.structuredAnswers[index('47')].answer.solution, /\\text\{发送数据的时间\}/);
  q47.open = true;
  q47.dispatchEvent(new browser.Event('toggle'));
  await new Promise(resolve => setTimeout(resolve, 0));
  const rich47 = q47.querySelector(':scope > .exam-answer-original');
  assert(rich47, 'q47 uses its original answer directly');
  const chinese = [...rich47.querySelectorAll('svg text')]
    .find(node => node.textContent === '发');
  assert(chinese, 'source-backed q47 formula retains Chinese SVG text');
  assert.match(chinese.getAttribute('font-size'), /^\d+(?:\.\d+)?px$/);
  assert.equal(chinese.getAttribute('font-family'), 'serif');
  assert.equal(fetches, 1, 'the answer page is fetched once for code and verification');
  page.window.close();
}

async function checkReal2009Cs408Ownership() {
  const sources = path.resolve(__dirname, '../..');
  const file = path.join(sources, 'cs408-latex-2009-2017/papers/2009-complete.htm');
  const markup = fs.readFileSync(file, 'utf8');
  const page = new JSDOM(markup, {
    runScripts: 'outside-only', url: 'http://localhost:8765/cs408-latex-2009-2017/papers/2009-complete.htm'
  });
  const {window: browser} = page;
  const document = browser.document;
  browser.fetch = async () => ({ok: true, text: async () => markup});
  browser.eval(script);
  document.dispatchEvent(new browser.Event('DOMContentLoaded'));
  const panels = [...document.querySelectorAll('main .exam-answer-panel')];
  for (const number of [12, 13, 14, 15, 16]) {
    const panel = panels[number - 1];
    panel.open = true;
    panel.dispatchEvent(new browser.Event('toggle'));
    await new Promise(resolve => setTimeout(resolve, 0));
    const rich = panel.querySelector(':scope > .exam-answer-original');
    assert(rich, `q${number} has a question-owned original explanation`);
    assert.match(rich.textContent.trim(), new RegExp(`^${number}[．.]`));
    assert.doesNotMatch(rich.textContent, /9\. A 10\. B 11\. C 12\. D/,
      'the shared answer key is excluded from one question');
    assert.match(panel.querySelector(':scope > .exam-answer-field').textContent,
      /标准答案/, 'the explicit letter remains available');
  }
  page.window.close();
}

Promise.all([checkReal408Answer(), checkReal2019MathAnswer(), checkReal2017Cs408Answers(),
  checkReal2009Cs408Ownership()]).then(() => {
  console.log('answers.js: owned original answers, shared-key fallback, and CS408 2017 formatting passed');
}).catch(error => { console.error(error); process.exitCode = 1; });
