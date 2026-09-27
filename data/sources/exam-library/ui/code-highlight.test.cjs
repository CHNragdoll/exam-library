const {JSDOM} = require(process.env.EXAM_JSDOM || 'jsdom');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');

const script = fs.readFileSync(path.join(__dirname, 'code-highlight.js'), 'utf8');
const source = 'int count=0; // keep int 23 unchanged\nfor(i=1; i*i<=n; i++) count++;\nchar *message="func(2)";\nint func(int n) { return n*2; }\n';
const html = `<main><pre class="code"><code></code></pre><pre class="tex-source"><code>int untouched = 7;</code></pre></main>`;
const dom = new JSDOM(html, {runScripts: 'outside-only'});
const {window} = dom;
const {document} = window;
document.querySelector('pre.code code').textContent = source;
window.eval(script);
window.ExamCodeHighlight.apply(document);
const code = document.querySelector('pre.code code');
assert.equal(code.textContent, source, 'copying the block yields the exact original source');
assert.equal(code.dataset.examHighlighted, 'true');
for (const [kind, expected] of [
  ['type', 'int'], ['keyword', 'for'], ['number', '0'],
  ['function', 'func'], ['comment', '// keep int 23 unchanged'],
  ['string', '"func(2)"'], ['operator', '++']
]) {
  assert([...code.querySelectorAll(`.code-token-${kind}`)].some(node => node.textContent === expected),
    `${kind} syntax is distinguished`);
}
assert.equal(document.querySelector('pre.tex-source code').innerHTML, 'int untouched = 7;',
  'non-code blocks are unchanged');
const markup = code.innerHTML;
window.ExamCodeHighlight.apply(document);
assert.equal(code.innerHTML, markup, 'highlighting is idempotent');
dom.window.close();

const paper = path.resolve(__dirname, '../../cs408-latex-2009-2017/papers/2025-questions.htm');
const corpus = new JSDOM(fs.readFileSync(paper, 'utf8'), {runScripts: 'outside-only'});
const original = corpus.window.document.querySelector('main pre.code code');
assert(original, '2025 408 question 1 contains a source-code block');
const originalText = original.textContent;
corpus.window.eval(script);
corpus.window.ExamCodeHighlight.apply(corpus.window.document);
assert.equal(original.textContent, originalText, 'actual exam code remains byte-for-byte copyable');
assert(original.querySelector('.code-token-keyword'), 'actual exam loop keyword receives color');
assert(original.querySelector('.code-token-type'), 'actual exam type receives color');
corpus.window.close();
console.log('code-highlight: source preservation, syntax categories, idempotence, and 2025 408 fixture passed');
