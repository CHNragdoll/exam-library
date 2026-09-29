const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {JSDOM} = require(process.env.EXAM_JSDOM || 'jsdom');

const markup = fs.readFileSync(path.join(__dirname, 'index.htm'), 'utf8');
const script = fs.readFileSync(path.join(__dirname, 'practice.js'), 'utf8');
const shared = fs.readFileSync(path.join(__dirname, 'practice-shared.js'), 'utf8');
const highlighter = fs.readFileSync(path.join(__dirname, '../ui/code-highlight.js'), 'utf8');
const paperId = 'math3:2019-questions';
const questionId = `${paperId}:q-1-1`;
const unknownId = `${paperId}:q-2-1`;
const ambiguousId = `${paperId}:q-3-1`;
const options = [
  {id: 'o-a', label: 'A.', sourceLabel: 'A.', text: '<img src=x onerror=alert(1)>', defaultPosition: 0},
  {id: 'o-b', label: 'B.', sourceLabel: 'B.', text: 'B', defaultPosition: 1},
  {id: 'o-c', label: 'C.', sourceLabel: 'C.', text: '\\(x^2\\)', defaultPosition: 2},
  {id: 'o-d', label: 'D.', sourceLabel: 'D.', text: 'D', defaultPosition: 3}
];
const numberedFullwidth = '要求如下。（1）给出算法的基本设计思想。（4分）（2）描述算法，关键处注释。（7分）（3）说明复杂度。（2分）';
const numberedAscii = 'Tasks: (1) Explain the method. (2) Compare the result.';
const ordinaryReference = '补充：见式(1)和式(2)，并计算\\(a+b\\) <script>alert(1)</script>';
const questions = [
  {id: questionId, number: '1', questionType: 'single_choice', stem: '<script>alert(1)</script> 求值 \\(x^2\\)', context: {kind: 'passage', blankNumber: '1', text: '阅读材料正文'}, options, contentBlocks: [
    {role: 'figure', text: '题图', images: [
      {src: '/cs408-latex-2009-2017/assets/figures/sample.svg', alt: '<img onerror=alert(1)>'},
      {src: 'https://example.invalid/tracker.png', alt: '外站'},
      {src: 'javascript:alert(1)', alt: '脚本'}]},
    {role: 'content', text: 'int count=0, i, j; for(i=1; i*i<=n; i++) for(j=1; j<=i; j++) count ++;',
      code: 'int count=0, i, j;\nfor(i=1; i*i<=n; i++)\n  for(j=1; j<=i; j++)\n    count ++;', images: []},
    {role: 'content', text: ordinaryReference, code: null, images: []},
    {role: 'content', text: numberedFullwidth, code: null, images: []},
    {role: 'content', text: numberedAscii, code: null, images: []}
  ], status: 'complete', answerStatus: 'explicit'},
  {id: unknownId, number: '2', questionType: 'single_choice', stem: '答案未知', context: '', options, status: 'complete', answerStatus: 'missing'},
  {id: ambiguousId, number: '3', questionType: 'single_choice', stem: '答案待核', context: '', options, status: 'complete', answerStatus: 'ambiguous'}
];
const paper = {id: paperId, title: '2019 数学三', category: 'math3', categoryLabel: '考研数学三', year: 2019, kind: 'questions', questionCount: 3};
const otherPaper = {id: 'kaoyan:2026-01', title: '2026 考研英语一', category: 'kaoyan', categoryLabel: '考研英语', year: 2026, kind: 'questions', questionCount: 1};

async function waitFor(test, description) {
  for (let n = 0; n < 50; n++) {
    if (test()) return;
    await new Promise(resolve => setTimeout(resolve, 5));
  }
  assert.fail(`Timed out: ${description}`);
}

function item(doc, id) {
  return [...doc.querySelectorAll('.option')].find(node => node.dataset.optionId === id);
}

async function main() {
  const dom = new JSDOM(markup, {
    url: 'http://127.0.0.1:8765/exam-library/practice/index.htm', runScripts: 'outside-only'
  });
  const w = dom.window;
  const d = w.document;
  const urls = [];
  w.MathJax = {startup: {promise: Promise.resolve()}, typesetPromise: async () => {}};
  w.fetch = async url => {
    urls.push(String(url));
    let payload;
    if (url === '/api/v1/papers') payload = {papers: [paper, otherPaper]};
    else if (String(url).includes('/questions?')) {
      if (String(url).includes(encodeURIComponent(otherPaper.id))) {
        payload = {paper: otherPaper, questions: [{...questions[0], id: `${otherPaper.id}:q-1-1`}]};
      } else {
        const shuffled = String(url).includes('order=shuffle');
        payload = {paper, questions: questions.map(question => ({
          ...question,
          options: (shuffled ? [options[2], options[0], options[3], options[1]] : options)
            .map((option, index) => ({...option, displayLabel: `${'ABCD'[index]}.`}))
        }))};
      }
    } else if (String(url).endsWith(`${encodeURIComponent(questionId)}/answer`)) {
      payload = {status: 'explicit', value: '<img src=x onerror=alert(1)> C', solution: '\\(x^2\\)', correctOptionIds: ['o-c']};
    } else if (String(url).endsWith(`${encodeURIComponent(unknownId)}/answer`)) {
      payload = {status: 'missing', value: null, correctOptionIds: []};
    } else if (String(url).endsWith(`${encodeURIComponent(ambiguousId)}/answer`)) {
      payload = {status: 'ambiguous', value: 'A 或 B', correctOptionIds: []};
    } else assert.fail(`Unexpected API request: ${url}`);
    return {ok: true, json: async () => payload};
  };
  assert(markup.includes('../ui/code-highlight.css') && markup.includes('../ui/code-highlight.js'));
  w.eval(highlighter);
  w.eval(shared);
  w.eval(script);
  await waitFor(() => !d.getElementById('practice-panel').hidden, 'questions loaded');
  assert.deepEqual([...d.querySelectorAll('.option')].map(node => node.dataset.optionId), ['o-a', 'o-b', 'o-c', 'o-d'], 'default keeps source order');
  assert.deepEqual([...d.querySelectorAll('.option-label')].map(node => node.textContent), ['A.', 'B.', 'C.', 'D.']);
  assert.equal(d.querySelector('#question-stem script'), null, 'question text cannot inject HTML');
  assert.equal(d.querySelector('.option img'), null, 'option text cannot inject HTML');
  assert.equal(d.getElementById('question-context').textContent, '阅读材料正文', 'context renders source text, not JSON metadata');
  const content = d.getElementById('question-content');
  assert(!content.hidden);
  assert(d.getElementById('question-stem').compareDocumentPosition(content) & w.Node.DOCUMENT_POSITION_FOLLOWING);
  assert(content.compareDocumentPosition(d.getElementById('answer-form')) & w.Node.DOCUMENT_POSITION_FOLLOWING);
  assert.equal(content.querySelectorAll('img').length, 1, 'external and script image URLs are rejected');
  assert.equal(content.querySelector('img').getAttribute('src'), '/cs408-latex-2009-2017/assets/figures/sample.svg');
  assert.equal(content.querySelector('img').alt, '<img onerror=alert(1)>');
  const code = content.querySelector('pre.code > code');
  assert.match(code.textContent, /for\(j=1; j<=i; j\+\+\)/);
  assert.equal(code.textContent, questions[0].contentBlocks[1].code, 'syntax colors preserve copyable source');
  assert.equal(code.dataset.examHighlighted, 'true', 'dynamically rendered code is highlighted');
  assert(code.querySelector('.code-token-type') && code.querySelector('.code-token-keyword'));
  assert.equal(content.querySelectorAll('.content-text').length, 3, 'flattened code is not repeated as prose');
  const fullwidth = [...content.querySelectorAll('.content-text')].find(node => node.textContent === numberedFullwidth);
  const ascii = [...content.querySelectorAll('.content-text')].find(node => node.textContent === numberedAscii);
  const ordinary = [...content.querySelectorAll('.content-text')].find(node => node.textContent === ordinaryReference);
  assert.equal(fullwidth.querySelectorAll('.content-subquestion').length, 3, 'fullwidth numbered subquestions get separate lines');
  assert.equal(ascii.querySelectorAll('.content-subquestion').length, 2, 'ASCII numbered subquestions get separate lines');
  assert.equal(ordinary.querySelectorAll('.content-subquestion').length, 0, 'ordinary parenthesized references stay intact');
  assert.equal(content.querySelector('script'), null, 'supplemental text cannot inject HTML');
  content.querySelector('img').dispatchEvent(new w.Event('error'));
  assert.equal(content.querySelector('img').hidden, true, 'missing image shows a fallback');
  assert.equal(content.querySelector('.image-error').hidden, false);

  item(d, 'o-a').querySelector('input').click();
  d.getElementById('order-select').value = 'shuffle';
  d.getElementById('order-select').dispatchEvent(new w.Event('change'));
  await waitFor(() => [...d.querySelectorAll('.option')][0]?.dataset.optionId === 'o-c', 'shuffle loaded');
  assert.equal(d.querySelector('pre.code > code')?.dataset.examHighlighted, 'true', 'reloaded question is highlighted again');
  assert.deepEqual([...d.querySelectorAll('.option')].map(node => node.dataset.optionId), ['o-c', 'o-a', 'o-d', 'o-b']);
  assert.equal(item(d, 'o-a').querySelector('input').checked, true, 'selection follows stable option id');
  assert.equal(item(d, 'o-c').querySelector('.option-label').textContent, 'A.', 'shuffled display labels are used');
  d.getElementById('reveal-button').click();
  await waitFor(() => !d.getElementById('answer-panel').hidden, 'answer loaded');
  assert(item(d, 'o-c').classList.contains('is-correct'), 'correct answer follows id after shuffling');
  assert(item(d, 'o-a').classList.contains('is-wrong'), 'the selected wrong id is identified');
  assert.equal(d.querySelector('#answer-panel img'), null, 'answer cannot inject HTML');

  d.getElementById('question-jump').value = unknownId;
  d.getElementById('question-jump').dispatchEvent(new w.Event('change'));
  assert.equal(content.hidden, true, 'next question clears previous figure and code');
  assert.equal(content.querySelector('img'), null);
  item(d, 'o-b').querySelector('input').click();
  d.getElementById('reveal-button').click();
  await waitFor(() => !d.getElementById('answer-panel').hidden, 'missing answer shown');
  assert.match(d.getElementById('answer-panel').textContent, /暂无可用答案.*不判对错/);
  assert.equal(d.querySelectorAll('.option.is-correct, .option.is-wrong').length, 0);

  d.getElementById('question-jump').value = ambiguousId;
  d.getElementById('question-jump').dispatchEvent(new w.Event('change'));
  d.getElementById('reveal-button').click();
  await waitFor(() => !d.getElementById('answer-panel').hidden, 'ambiguous answer shown');
  assert.match(d.getElementById('answer-panel').textContent, /歧义.*不判对错/);
  assert.equal(d.querySelectorAll('.option.is-correct, .option.is-wrong').length, 0);

  d.getElementById('seed-input').value = 'test-seed';
  d.getElementById('seed-input').dispatchEvent(new w.Event('change'));
  await waitFor(() => urls.some(url => url.includes('seed=test-seed')), 'seed request');
  assert(urls.some(url => url.includes(`papers/${encodeURIComponent(paperId)}/questions?order=default`)));
  assert(urls.some(url => url.includes(`papers/${encodeURIComponent(paperId)}/questions?order=shuffle`)));
  d.getElementById('category-select').value = 'kaoyan';
  d.getElementById('category-select').dispatchEvent(new w.Event('change'));
  await waitFor(() => d.getElementById('paper-title').textContent === otherPaper.title, 'category filter');
  assert.deepEqual([...d.querySelectorAll('#paper-select option')].map(node => node.value), [otherPaper.id]);
  dom.window.close();

  const mathDom = new JSDOM(markup, {url: 'http://127.0.0.1:8765/exam-library/practice/index.htm', runScripts: 'outside-only'});
  const mathWindow = mathDom.window;
  const mathDoc = mathWindow.document;
  mathWindow.fetch = async url => ({ok: true, json: async () => {
    if (url === '/api/v1/papers') return {papers: [paper]};
    if (String(url).includes('/questions?')) return {paper, questions: [questions[0]]};
    return {status: 'explicit', value: 'C', solution: '\\(x^2+1\\)', correctOptionIds: ['o-c']};
  }});
  mathWindow.eval(mathDoc.querySelector('head script').textContent);
  mathWindow.eval(fs.readFileSync(path.join(__dirname, '../ui/vendor/mathjax-3.2.2-tex-svg-full.js'), 'utf8'));
  mathWindow.eval(shared);
  mathWindow.eval(script);
  await waitFor(() => mathDoc.querySelector('#question-stem mjx-container svg path') &&
    item(mathDoc, 'o-c')?.querySelector('mjx-container svg path') &&
    mathDoc.querySelector('.content-text mjx-container svg path'), 'local MathJax renders question, content and option');
  mathDoc.getElementById('reveal-button').click();
  await waitFor(() => mathDoc.querySelector('#answer-panel mjx-container svg path'), 'local MathJax renders answer');
  mathDom.window.close();

  const figureDom = new JSDOM(markup, {url: 'http://127.0.0.1:8765/exam-library/practice/index.htm', runScripts: 'outside-only'});
  const figureWindow = figureDom.window;
  const figureDoc = figureWindow.document;
  const figurePaper = {...paper, id: 'cs408:2009-complete', category: 'cs408', questionCount: 1};
  const figureId = `${figurePaper.id}:q-4-1`;
  const figureSrc = '/cs408-latex-2009-2017/assets/figures/2009-complete-p001-b007.svg';
  const regions = [[0, 0, 72, 86], [72, 0, 84, 86], [156, 0, 73, 86], [229, 0, 72, 86]];
  const figureOptions = regions.map(([x, y, width, height], index) => ({
    id: `${figureId}:${'ABCD'[index]}`, label: `${'ABCD'[index]}.`, text: '',
    image: {src: figureSrc, sourceBlockId: `${figurePaper.id}:b-1-8`, alt: `原卷选项 ${'ABCD'[index]} 图`,
      crop: {x, y, width, height, sourceWidth: 373, sourceHeight: 86}}
  }));
  const figureQuestion = {id: figureId, number: '4', questionType: 'single_choice', stem: '选择平衡二叉树',
    options: figureOptions, contentBlocks: [{id: `${figurePaper.id}:b-1-8`, role: 'figure',
      text: 'A、B、C、D 四棵候选树', images: [{src: figureSrc, alt: '原图'}]}]};
  figureWindow.fetch = async url => ({ok: true, json: async () => {
    if (url === '/api/v1/papers') return {papers: [figurePaper]};
    if (String(url).includes('/questions?')) return {paper: figurePaper, questions: [figureQuestion]};
    return {status: 'explicit', value: 'B', correctOptionIds: [figureOptions[1].id]};
  }});
  figureWindow.eval(shared);
  figureWindow.eval(script);
  await waitFor(() => figureDoc.querySelectorAll('.option-image').length === 4, 'four figure options render');
  assert.equal(figureDoc.querySelectorAll('.option-image-frame').length, 4);
  assert.equal(figureDoc.querySelectorAll('.content-figure img').length, 0, 'combined figure is not duplicated');
  assert.equal(figureDoc.querySelector('.source-figure-link').getAttribute('href'), figureSrc);
  assert.equal(figureDoc.querySelector('.source-figure-link').getAttribute('target'), '_blank');
  assert.equal(item(figureDoc, figureOptions[1].id).querySelector('.option-image').style.left,
    `${-72 / 84 * 100}%`, 'B choice uses its own source region');
  item(figureDoc, figureOptions[1].id).querySelector('input').click();
  assert(item(figureDoc, figureOptions[1].id).querySelector('input').checked);
  figureDom.window.close();

  const redrawDom = new JSDOM(markup, {url: 'http://127.0.0.1:8765/exam-library/practice/index.htm', runScripts: 'outside-only'});
  const redrawWindow = redrawDom.window;
  const redrawDoc = redrawWindow.document;
  const originalSrc = '/cs408-latex-2009-2017/assets/figures/2025-questions-p012-b001.svg';
  const redrawSrc = '/exam-library/assets/redrawn/cs408-2025-questions-p012-b001-v4-color.png';
  const redrawQuestion = {id: 'cs408:2025-questions:q-47-1', number: '47',
    questionType: 'free_response', stem: '卫星链路', options: [], contentBlocks: [
      {role: 'figure', text: '题47图', images: [{src: originalSrc, alt: '原图',
        redraw: {src: redrawSrc, alt: '彩色重绘图'}}]}
    ]};
  const redrawPaper = {...figurePaper, id: 'cs408:2025-questions'};
  redrawWindow.fetch = async url => ({ok: true, json: async () =>
    url === '/api/v1/papers' ? {papers: [redrawPaper]} :
      {paper: redrawPaper, questions: [redrawQuestion]}});
  redrawWindow.eval(shared);
  redrawWindow.eval(script);
  await waitFor(() => redrawDoc.querySelector('.content-redraw-control button'), 'redraw control renders');
  const original = redrawDoc.querySelector('.content-figure img:not(.content-redraw-image)');
  const redraw = redrawDoc.querySelector('.content-redraw-image');
  const toggle = redrawDoc.querySelector('.content-redraw-control button');
  assert.equal(original.getAttribute('src'), originalSrc);
  assert.equal(redraw.getAttribute('src'), redrawSrc);
  Object.defineProperty(original, 'naturalWidth', {value: 395});
  original.dispatchEvent(new redrawWindow.Event('load'));
  redraw.dispatchEvent(new redrawWindow.Event('load'));
  assert.equal(redraw.style.width, '395px', 'redraw uses original display width');
  assert.equal(redraw.hidden, false, 'loaded redraw is the default');
  assert.equal(original.hidden, true);
  assert.equal(toggle.textContent, '查看原图');
  toggle.click();
  assert.equal(original.hidden, false);
  assert.equal(redraw.hidden, true);
  assert.equal(toggle.textContent, '查看重绘图');
  toggle.click();
  assert.equal(redraw.hidden, false);
  redrawDom.window.close();

  const sourceDom = new JSDOM(markup, {
    url: 'http://127.0.0.1:8765/exam-library/practice/index.htm', runScripts: 'outside-only'
  });
  const sourceWindow = sourceDom.window;
  const sourceDoc = sourceWindow.document;
  const sourcePaper = {id: 'test:source-answers', title: '原卷答案排版', category: 'test',
    categoryLabel: '测试', year: 2023, kind: 'questions', questionCount: 5};
  const sourceQuestions = ['37', '46', '20', '41', '6'].map(number => ({
    id: `${sourcePaper.id}:q-${number}-1`, number, questionType: 'free_response',
    stem: `第 ${number} 题`, context: null, options: [], contentBlocks: [],
    status: 'complete', answerStatus: 'explicit'
  }));
  const sourceAnswers = new Map([
    [sourceQuestions[0].id, {status: 'explicit', explanation: '压平的解析不应重复',
      commentary: '压平的评注不应重复', sourceBaseUrl: '/politics-answers-latex-2009-2023/papers/2023-answers.htm',
      sourceContentBlocks: [
        {contentHtml: '<h2>37. 【答案】</h2>'},
        {contentHtml: '<p class="paragraph">（1）爱国主义正文。</p>'},
        {contentHtml: '<p class="paragraph">（2）创新创造正文。</p>'},
        {contentHtml: '<h2>【考点点拨】</h2>'},
        {contentHtml: '<p>爱国主义、科学家精神。</p>'},
        {contentHtml: '<h2>【试题简析】</h2>'},
        {contentHtml: '<p>逐题分析。</p>'},
        {contentHtml: '<h2>【名师点拨】</h2>'},
        {contentHtml: '<p>进一步提示。</p><script>window.__unsafe=1</script><img src="javascript:alert(1)">'}
      ]}],
    [sourceQuestions[1].id, {status: 'explicit', solution: '压平的代码不应重复',
      sourceBaseUrl: '/cs408-answers-latex-2016-2025/papers/2017-answers.htm',
      sourceContentBlocks: [
        {contentHtml: '<p>46.解答：</p>'},
        {contentHtml: '<pre class="code"><code>semaphore mutex_y1=1;\nthread1 {\n    wait(mutex_y1);\n}</code></pre>'},
        {contentHtml: '<div class="table-scroll"><table><thead><tr><th>变量</th><th>给分</th></tr></thead><tbody><tr><td>y</td><td>3 分</td></tr></tbody></table></div>'}
      ]}],
    [sourceQuestions[2].id, {status: 'explicit', value: '旧字段',
      solution: '已有原卷答案时不重复结构化解答', resolvedReferenceOnly: false,
      sourceBaseUrl: '/math3-latex-2009-2019/papers/2019-answers.htm',
      sourceContentBlocks: [
        {contentHtml: '<div class="paragraph question">（20）当 \\(\\displaystyle a\\neq-1\\) 时成立。</div>'},
        {contentHtml: '<pre class="tex-source">重复的 TeX 原文</pre>'}
      ]}],
    [sourceQuestions[3].id, {status: 'explicit',
      sourceBaseUrl: '/exam-library/structured/papers/cs408/2009-complete.htm',
      sourceContentBlocks: [
        {contentHtml: '<p>41．解答：见图。</p>'},
        {contentHtml: '<figure><img alt="第41题反例" src="../../../../cs408-latex-2009-2017/assets/figures/2009-complete-p007-b009.svg"></figure>'}
      ]}],
    [sourceQuestions[4].id, {status: 'explicit', resolvedReferenceOnly: true,
      solution: '（1）当 \\(\\displaystyle 0<p<1\\) 时销售额增加。',
      sourceBaseUrl: '/exam-library/structured/papers/math3/1996-answers.htm',
      sourceContentBlocks: [
        {contentHtml: '<div class="paragraph">六、【同试卷 IV 第六题】</div>'}
      ]}]
  ]);
  sourceWindow.fetch = async url => ({ok: true, json: async () => {
    if (url === '/api/v1/papers') return {papers: [sourcePaper]};
    if (String(url).includes('/questions?')) return {paper: sourcePaper, questions: sourceQuestions};
    return sourceAnswers.get(decodeURIComponent(String(url).split('/').at(-2)));
  }});
  sourceWindow.eval(sourceDoc.querySelector('head script').textContent);
  sourceWindow.eval(fs.readFileSync(path.join(__dirname, '../ui/vendor/mathjax-3.2.2-tex-svg-full.js'), 'utf8'));
  sourceWindow.eval(highlighter);
  sourceWindow.eval(shared);
  sourceWindow.eval(script);
  await waitFor(() => !sourceDoc.getElementById('practice-panel').hidden, 'source-answer paper loaded');
  sourceDoc.getElementById('reveal-button').click();
  await waitFor(() => sourceDoc.querySelectorAll('#answer-panel .answer-source-block').length === 9,
    'politics source answer loaded');
  assert.deepEqual([...sourceDoc.querySelectorAll('#answer-panel .answer-source h2')].map(node => node.textContent),
    ['37. 【答案】', '【考点点拨】', '【试题简析】', '【名师点拨】']);
  assert.match(sourceDoc.querySelector('#answer-panel .answer-source').textContent,
    /（1）爱国主义正文。[\s\S]*（2）创新创造正文。/);
  assert.doesNotMatch(sourceDoc.getElementById('answer-panel').textContent, /压平的解析|压平的评注/);
  assert.equal(sourceDoc.querySelector('#answer-panel script, #answer-panel img[src^="javascript:"]'), null);
  assert.equal(sourceWindow.__unsafe, undefined);

  sourceDoc.getElementById('question-jump').value = sourceQuestions[1].id;
  sourceDoc.getElementById('question-jump').dispatchEvent(new sourceWindow.Event('change'));
  sourceDoc.getElementById('reveal-button').click();
  await waitFor(() => sourceDoc.querySelector('#answer-panel .answer-source pre.code > code'),
    'CS408 source code loaded');
  assert.match(sourceDoc.querySelector('#answer-panel pre.code').textContent, /thread1 \{\n    wait/);
  assert.equal(sourceDoc.querySelector('#answer-panel table tr').children.length, 2);
  assert(sourceDoc.querySelector('#answer-panel .code-token'), 'restored answer code is highlighted');
  assert.doesNotMatch(sourceDoc.getElementById('answer-panel').textContent, /压平的代码/);

  sourceDoc.getElementById('question-jump').value = sourceQuestions[2].id;
  sourceDoc.getElementById('question-jump').dispatchEvent(new sourceWindow.Event('change'));
  sourceDoc.getElementById('reveal-button').click();
  await waitFor(() => sourceDoc.querySelector('#answer-panel .answer-source mjx-container svg path'),
    'Math III source formula rendered');
  assert.equal(sourceDoc.querySelector('#answer-panel pre.tex-source'), null);
  assert.doesNotMatch(sourceDoc.getElementById('answer-panel').textContent, /旧字段|重复的 TeX 原文/);
  assert.doesNotMatch(sourceDoc.getElementById('answer-panel').textContent,
    /已有原卷答案时不重复结构化解答/);

  sourceDoc.getElementById('question-jump').value = sourceQuestions[3].id;
  sourceDoc.getElementById('question-jump').dispatchEvent(new sourceWindow.Event('change'));
  sourceDoc.getElementById('reveal-button').click();
  await waitFor(() => sourceDoc.querySelector('#answer-panel .answer-source figure img'),
    'CS408 source answer figure loaded');
  assert.equal(sourceDoc.querySelector('#answer-panel .answer-source img').getAttribute('src'),
    '/cs408-latex-2009-2017/assets/figures/2009-complete-p007-b009.svg');
  assert.equal(sourceDoc.querySelector('#answer-panel .answer-source img').alt, '第41题反例');

  sourceDoc.getElementById('question-jump').value = sourceQuestions[4].id;
  sourceDoc.getElementById('question-jump').dispatchEvent(new sourceWindow.Event('change'));
  sourceDoc.getElementById('reveal-button').click();
  await waitFor(() => sourceDoc.querySelector('#answer-panel mjx-container svg path'),
    'resolved cross-form solution rendered');
  assert.match(sourceDoc.getElementById('answer-panel').textContent, /同试卷 IV 第六题/);
  assert.match(sourceDoc.getElementById('answer-panel').textContent, /对应试卷解答：/);
  assert.match(sourceDoc.getElementById('answer-panel').textContent, /销售额增加/);
  sourceDom.window.close();

  const materialDom = new JSDOM(markup, {
    url: 'http://127.0.0.1:8765/exam-library/practice/index.htm', runScripts: 'outside-only'
  });
  const materialWindow = materialDom.window;
  const materialDoc = materialWindow.document;
  const style = materialDoc.createElement('style');
  style.textContent = fs.readFileSync(path.join(__dirname, 'practice.css'), 'utf8') + fs.readFileSync(path.join(__dirname, '../ui/material.css'), 'utf8');
  materialDoc.head.append(style);
  const materialPaper = {id: 'politics:2023-questions', title: '2023 政治',
    category: 'politics', categoryLabel: '考研政治', year: 2023,
    kind: 'questions', questionCount: 1};
  const materialQuestion = {id: 'politics:2023-questions:q-36-1', number: '36',
    questionType: 'free_response', stem: '36. 结合材料回答问题：\n材料1\n正文1\n摘自材料1\n材料2\n正文2\n摘自材料2',
    stemParagraphs: [
      {text: '36. 结合材料回答问题：', kind: 'paragraph'},
      {text: '材料1', kind: 'material_label'}, {text: '正文1', kind: 'paragraph'},
      {text: '摘自材料1', kind: 'material_source'},
      {text: '材料2', kind: 'material_label'}, {text: '正文2', kind: 'paragraph'},
      {text: '摘自材料2', kind: 'material_source'}
    ], options: [], contentBlocks: [{role: 'content', text: '材料3 正文3 摘自材料3 （1）问题',
      paragraphs: ['材料3', '正文3', '摘自材料3', '（1）问题'], styledParagraphs: [
        {text: '材料3', kind: 'material_label'}, {text: '正文3', kind: 'paragraph'},
        {text: '摘自材料3', kind: 'material_source'}, {text: '（1）问题', kind: 'paragraph'}
      ]}], status: 'complete', answerStatus: 'explicit'};
  materialWindow.fetch = async url => ({ok: true, json: async () =>
    url === '/api/v1/papers' ? {papers: [materialPaper]} :
      {paper: materialPaper, questions: [materialQuestion]}});
  materialWindow.eval(shared);
  materialWindow.eval(script);
  await waitFor(() => !materialDoc.getElementById('practice-panel').hidden,
    'politics material question loaded');
  assert.deepEqual([...materialDoc.querySelectorAll('.material-label')].map(node => node.textContent),
    ['材料1', '材料2', '材料3']);
  assert.deepEqual([...materialDoc.querySelectorAll('.material-source')].map(node => node.textContent),
    ['摘自材料1', '摘自材料2', '摘自材料3']);
  assert.equal(materialWindow.getComputedStyle(materialDoc.querySelector('.material-label')).fontWeight, '700');
  assert.equal(materialWindow.getComputedStyle(materialDoc.querySelector('.material-source')).textAlign, 'right');
  assert.equal(materialDoc.querySelector('#question-content').textContent.match(/（1）问题/g).length, 1);
  materialDom.window.close();
  console.log('practice: filters, stable-id shuffle, answer status, safe content blocks, local MathJax, source-clipped image choices, redraw toggle passed');
}

main().catch(error => { console.error(error); process.exitCode = 1; });
