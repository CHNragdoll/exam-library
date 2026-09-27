const {JSDOM} = require(process.env.EXAM_JSDOM || 'jsdom');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');

const script = fs.readFileSync(path.join(__dirname, 'technical-subquestions.js'), 'utf8');
function apply(html) {
  const dom = new JSDOM(html, {runScripts: 'outside-only'});
  dom.window.eval(script);
  dom.window.ExamTechnicalSubquestions?.apply(dom.window.document);
  return dom;
}

const config = `<script id="exam-reader-config" type="application/json">{"category":"cs408","mode":"reflow","kind":"questions"}</script>`;
const sample = `${config}<main><section data-source-page="1">
  <p class="paragraph question">47．题干说明。</p>
  <p class="paragraph" id="prompt">请回答下列问题。（1）求 <em>x</em>？（2）写出理由。（3）计算结果。</p>
  <p class="paragraph" id="separate">（1）第一问。（2）第二问。</p>
  <p class="paragraph question">1．普通选择题（1）甲（2）乙</p>
  <p class="paragraph" id="other">（1）甲。（2）乙。</p>
</section></main>`;
const dom = apply(sample);
const {document} = dom.window;
const prompt = document.getElementById('prompt');
const source = '请回答下列问题。（1）求 x？（2）写出理由。（3）计算结果。';
assert.equal(prompt.textContent, source, 'prompt text and inline markup remain unchanged');
assert.equal(prompt.querySelectorAll('br.technical-subquestion-break').length, 3,
  'intro and all numbered parts have their own visual lines');
assert.equal(document.getElementById('separate').querySelectorAll('br').length, 1,
  'a paragraph that begins with (1) does not gain a blank first line');
assert.equal(document.getElementById('other').querySelectorAll('br').length, 0,
  'ordinary multiple-choice questions are outside the extended-question scope');
dom.window.ExamTechnicalSubquestions.apply(document);
assert.equal(prompt.querySelectorAll('br').length, 3, 'repeat enhancement is idempotent');
dom.window.close();

const paper = path.resolve(__dirname, '../../cs408-latex-2009-2017/papers/2025-questions.htm');
const real = new JSDOM(fs.readFileSync(paper, 'utf8'), {runScripts: 'outside-only'});
const paragraphs = [...real.window.document.querySelectorAll('main p.paragraph')];
const target = paragraphs.find(p => p.textContent.startsWith('请回答下列问题。') && p.textContent.includes('卫星链路'));
assert(target, '2025 408 extended question 47 exists');
const exact = target.textContent;
real.window.eval(script);
real.window.ExamTechnicalSubquestions.apply(real.window.document);
assert.equal(target.textContent, exact, 'actual 2025 question wording remains exactly copyable');
assert.equal(target.querySelectorAll('br.technical-subquestion-break').length, 3,
  '2025 question 47 has separate lines for (1), (2), and (3)');
const otherPrompts = paragraphs.filter(p => p.textContent.includes('请回答下列问题') && p !== target &&
  /[（(]1[）)]/.test(p.textContent) && /[（(]2[）)]/.test(p.textContent));
assert(otherPrompts.length >= 3 && otherPrompts.every(p => p.querySelector('br.technical-subquestion-break')),
  'other 2025 extended 408 prompts use the same rule');
real.window.close();
console.log('technical-subquestions: 2025 408 q47 and similar prompts passed');
