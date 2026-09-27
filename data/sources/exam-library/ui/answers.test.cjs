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
  const rich = panel.querySelector('.exam-answer-original');
  assert(rich, 'the answer source replaces the flattened text');
  assert(rich.querySelectorAll('.formula svg path').length > 0, 'pre-rendered formula SVG is visible');
  const code = rich.querySelector('pre.code > code');
  assert(code, 'source code is in a real code block');
  assert.match(code.textContent, /void calMulMax\(int A\[\], int res\[\], int n\)\n\{/);
  assert.match(code.textContent, /\n    int i, Max, Min;/);
  assert(code.querySelector('.code-token'), 'existing highlighter runs on restored code');
  assert.equal(rich.querySelector('script, img[src^="javascript:"]'), null);
  assert.equal(rich.querySelector('[onclick], [onerror]'), null);
  assert.equal(browser.__unsafe, undefined);
  assert.equal(panel.querySelector('.exam-answer-original-label').textContent, '原卷答案排版');
  const extracted = panel.querySelector('.exam-answer-extracted');
  assert(extracted && !extracted.open, 'field extracts remain available in a secondary disclosure');
  assert.deepEqual([...extracted.querySelectorAll('.exam-answer-field strong')].map(node => node.textContent),
    ['解答过程']);
  assert.match(extracted.textContent, /第一步|算法的基本设计思想/);
  assert.equal(fetches, 1);
  assert(originalQuestion.isConnected);
  assert.equal(originalQuestion.querySelector('svg'), originalFormula);
  page.window.close();
}

checkReal408Answer().then(() => {
  console.log('answers.js: states, placement, original nodes, and real 2025 408 q41 formula/code passed');
}).catch(error => { console.error(error); process.exitCode = 1; });
