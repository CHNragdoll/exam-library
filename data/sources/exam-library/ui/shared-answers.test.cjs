const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {JSDOM} = require(process.env.EXAM_JSDOM || 'jsdom');

// Part B has five question identities sharing the same passage blocks. The
// answer for 41 must remain first, including after reader.js wraps the passage.
const answers = ['B', 'E', 'A', 'G', 'D'].map((value, index) => ({
  questionId: `q-11-${index + 1}`, number: String(41 + index),
  sourceBlocks: ['b-1-1'], answer: {status: 'explicit', value}
}));
const page = new JSDOM(`<main><section data-source-page="1"><p id="passage">共用材料</p></section></main>
<script id="exam-reader-config" type="application/json">${JSON.stringify({mode: 'reflow', structuredAnswers: answers})}</script>`,
{runScripts: 'outside-only', url: 'http://localhost/paper.htm'});
const w = page.window;
w.eval(fs.readFileSync(path.join(__dirname, 'answers.js'), 'utf8'));
w.document.dispatchEvent(new w.Event('DOMContentLoaded'));
const panels = [...w.document.querySelectorAll('.exam-answer-panel')];
assert.deepEqual(panels.map(panel => panel.querySelector('.exam-answer-field p').textContent),
  ['B', 'E', 'A', 'G', 'D'], 'shared answers retain question order');
assert.deepEqual(panels.map(panel => panel.querySelector('summary').textContent),
  ['第 41 题 · 点击查看答案', '第 42 题 · 点击查看答案', '第 43 题 · 点击查看答案',
    '第 44 题 · 点击查看答案', '第 45 题 · 点击查看答案']);
panels[0].querySelector('summary').click();
assert.equal(panels[0].querySelector('summary').textContent, '第 41 题 · 收起答案');
panels[0].dispatchEvent(new w.Event('toggle'));
assert.equal(panels[0].querySelector('summary').textContent, '第 41 题 · 收起答案');
assert.equal(w.document.getElementById('passage').textContent, '共用材料');
assert.deepEqual(panels.map(panel => panel.dataset.questionId), answers.map(item => item.questionId));
page.window.close();
console.log('Shared Part B answers preserve question order and identity');
