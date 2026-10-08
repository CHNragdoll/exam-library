const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {JSDOM} = require(process.env.EXAM_JSDOM || 'jsdom');

const markup = fs.readFileSync(path.join(__dirname, 'full-paper.htm'), 'utf8');
const script = fs.readFileSync(path.join(__dirname, 'full-paper.js'), 'utf8');
const shared = fs.readFileSync(path.join(__dirname, 'practice-shared.js'), 'utf8');
const highlighter = fs.readFileSync(path.join(__dirname, '../ui/code-highlight.js'), 'utf8');

async function waitFor(check, label) {
  for (let count = 0; count < 60; count++) {
    if (check()) return;
    await new Promise(resolve => setTimeout(resolve, 5));
  }
  assert.fail(`Timed out: ${label}`);
}

function browser(paper, questions, answers, semanticRoot, translations = null) {
  const dom = new JSDOM(markup, {
    url: `http://127.0.0.1:8765/exam-library/practice/full-paper.htm?paper=${encodeURIComponent(paper.id)}`,
    runScripts: 'outside-only'
  });
  const calls = [];
  const warnings = [];
  const w = dom.window;
  w.console.warn = (...parts) => warnings.push(parts);
  w.MathJax = {startup: {promise: Promise.resolve()}, typesetPromise: async () => {}};
  w.fetch = async url => {
    calls.push(String(url));
    const questionPrefix = `/api/v1/papers/${encodeURIComponent(paper.id)}/questions`;
    let payload;
    if (String(url).startsWith(questionPrefix)) payload = {paper, questions};
    else if (String(url).includes('/api/v2/papers/')) payload = {paper, root: semanticRoot || {type: 'paper', children: questions.map((question, index) => ({type: 'question', questionId: question.id, ordinal: index, children: []}))}};
    else if (String(url).startsWith('/exam-library/structured/translations/')) {
      return translations ? {ok: true, json: async () => translations} : {ok: false, status: 404};
    }
    else {
      const id = decodeURIComponent(String(url).split('/questions/')[1]?.replace(/\/answer$/, '') || '');
      assert(answers.has(id), `Unexpected answer request: ${url}`);
      payload = answers.get(id);
    }
    return {ok: true, json: async () => payload};
  };
  w.eval(highlighter);
  w.eval(shared);
  w.eval(script);
  return {dom, w, d: w.document, calls, warnings};
}

async function requestTranslations(view, count, label) {
  await waitFor(() => !view.d.querySelector('#paper-panel').hidden,
    `${label} paper ready`);
  assert.equal(view.calls.filter(url => url.includes('/structured/translations/')).length, 0,
    'ordinary practice never fetches answer-bearing translation data');
  assert.equal(view.d.querySelectorAll('.paper-paragraph-translation').length, 0);
  const toggle = view.d.querySelector('#paragraph-translation-toggle');
  assert.equal(toggle.hidden, false);
  toggle.click();
  await waitFor(() => view.d.querySelectorAll('.paper-paragraph-translation').length === count,
    label);
  assert.equal(view.calls.filter(url => url.includes('/structured/translations/')).length, 1,
    'translation sidecar loads only after the explicit toggle');
  assert.equal(toggle.getAttribute('aria-pressed'), 'true');
  return toggle;
}

async function main() {
  const paper = {id: 'cs408:2017-questions', title: '2017 年计算机统考 408 · 真题',
    category: 'cs408', categoryLabel: '408 计算机统考', kind: 'questions', questionCount: 2};
  const firstId = `${paper.id}:q-1-1`;
  const writtenId = `${paper.id}:q-46-1`;
  const options = 'ABCD'.split('').map(letter => ({id: `${firstId}:${letter}`,
    label: `${letter}.`, sourceLabel: `${letter}.`, text: `${letter} 项`}));
  const questions = [
    {id: firstId, number: '1', questionType: 'single_choice', status: 'complete',
      stem: '第一题 \(x^2\)', context: null, options, contentBlocks: []},
    {id: writtenId, number: '46', questionType: 'free_response', status: 'complete',
      stem: '第 46 题：线程同步', context: null, options: [], contentBlocks: [
        {id: `${paper.id}:b-10-2`, role: 'content', text: 'int main() { return 0; }',
          code: 'int main() { return 0; }', images: []}
      ]}
  ];
  const sourceBaseUrl = '/exam-library/structured/papers/cs408/2017-answers.htm';
  const answers = new Map([
    [firstId, {status: 'explicit', value: 'B', correctOptionIds: [options[1].id],
      sourceContentBlocks: []}],
    [writtenId, {status: 'explicit', solution: '压平的代码不应代替原卷', correctOptionIds: [],
      sourceBaseUrl, sourceContentBlocks: [
        {id: 'source-1', role: 'question', contentHtml: '<p class="paragraph question">46. 解答：</p>'},
        {id: 'source-2', role: 'content', contentHtml: '<pre class="code"><code>int solve() { return 1; }</code></pre>'},
        {id: 'source-3', role: 'content', contentHtml: '<div class="table-scroll"><table><tr><th>变量</th><td>thread1</td></tr></table></div>'},
        {id: 'source-4', role: 'content', contentHtml: '<div class="display"><span class="formula">\\(x^2\\)</span></div>'},
        {id: 'source-5', role: 'figure', contentHtml: '<figure><img src="../../../../cs408-answers-latex-2016-2025/assets/figures/sample.svg" alt="原卷图"></figure><script>alert(1)</script><img src="https://evil.example/x.svg">'}
      ]}]
  ]);
  const {dom, d, calls} = browser(paper, questions, answers);
  await waitFor(() => d.querySelectorAll('#question-list > .question-card').length === 2, 'whole paper loaded');
  const cards = [...d.querySelectorAll('#question-list > .question-card')];
  assert.deepEqual(cards.map(card => card.querySelector('.question-number').textContent), ['第 1 题', '第 46 题']);
  assert.equal(d.querySelector('.question-nav, #previous-button, #next-button'), null,
    'the whole paper has no previous/next question controls');
  assert.deepEqual([...d.querySelector('#paper-toc-select').options].map(option => option.value),
    ['', 'question-1', 'question-2'], 'papers without section headings still have a question directory');
  assert.equal(cards[0].querySelectorAll('.option').length, 4);
  assert(cards[1].querySelector('textarea') && cards[1].querySelector('pre.code > code'));
  assert.equal(cards[1].querySelector('pre.code > code').dataset.examHighlighted, 'true');
  assert.equal(d.querySelector('.answer-source'), null, 'answers are not loaded before reveal');
  assert.equal(calls.filter(url => url.endsWith('/answer')).length, 0);

  cards[1].querySelector('textarea').value = '我的草稿';
  cards[1].querySelector('[data-action="reveal"]').click();
  await waitFor(() => !cards[1].querySelector('.answer-panel').hidden, 'written answer loaded');
  assert.equal(cards[0].querySelector('.answer-panel').hidden, true, 'reveal stays local to one question');
  assert.equal(cards[1].querySelector('.answer-source pre.code > code').textContent,
    'int solve() { return 1; }');
  assert.equal(cards[1].querySelector('.answer-source pre.code > code').dataset.examHighlighted, 'true');
  assert.equal(cards[1].querySelector('.answer-source table td').textContent, 'thread1');
  assert.equal(cards[1].querySelector('.answer-source .formula').textContent, '\\(x^2\\)');
  assert.equal(cards[1].querySelector('.answer-source img').getAttribute('src'),
    '/cs408-answers-latex-2016-2025/assets/figures/sample.svg');
  assert.equal(cards[1].querySelectorAll('.answer-source img').length, 1, 'external image is rejected');
  assert.equal(cards[1].querySelector('.answer-source script'), null, 'source HTML is sanitized');
  assert(!cards[1].querySelector('.answer-panel').textContent.includes('压平的代码'));

  cards[0].querySelector('.option input').click();
  cards[0].querySelector('[data-action="reveal"]').click();
  await waitFor(() => !cards[0].querySelector('.answer-panel').hidden, 'choice answer loaded');
  assert(cards[0].querySelectorAll('.option')[1].classList.contains('is-correct'));
  assert(cards[0].querySelectorAll('.option')[0].classList.contains('is-wrong'));
  cards[0].querySelector('[data-action="redo"]').click();
  assert.equal(cards[0].querySelector('.answer-panel').hidden, true);
  assert.equal(cards[0].querySelector('.option input').checked, false);
  assert.equal(cards[1].querySelector('.answer-panel').hidden, false);
  assert(calls.some(url => url.includes(`${encodeURIComponent(paper.id)}/questions?order=default`)));
  assert(calls.some(url => url.includes(`/api/v2/papers/${encodeURIComponent(paper.id)}/semantic`)));
  dom.window.close();

  const cet = {id: 'cet4:2021-12-03', title: '2021 年 12 月英语四级',
    category: 'cet4', categoryLabel: '英语四级', kind: 'questions', questionCount: 2};
  const cetQuestions = [46, 47].map(number => ({
    id: `${cet.id}:q-${number}-1`, number: String(number), questionType: 'single_choice',
    status: 'complete', stem: `${number}. Which claim is true?`,
    context: {id: 'reading-passage-one', text: 'Shared article body'},
    options: 'ABCD'.split('').map(letter => ({id: `q-${number}:${letter}`, label: letter,
      text: `${letter} option`})),
    contentBlocks: [{id: 'shared-block', role: 'content', text: 'Shared source paragraph'},
      {id: `own-${number}`, role: 'content', text: `Question ${number} note`},
      ...(number === 47 ? [{id: 'shared-block', role: 'content',
        text: 'Distinct paragraph from shared source block'}] : [])]
  }));
  const articleBody = 'Shared article body spans a complete paragraph in the source paper.';
  const passage = {id: 'shared-reading', type: 'material', title: 'Passage One', units: [
    {type: 'paragraph', text: articleBody,
      provenance: {jsonPath: '$.questions[0].context.text'}},
    {type: 'paragraph', text: articleBody, provenance: {sourceBlockId: 'passage-block'}}
  ], children: []};
  const cetRoot = {type: 'paper', children: [{type: 'section', title: 'Part III Reading',
    units: [{type: 'paragraph', text: articleBody,
      provenance: {sourceBlockId: 'raw-passage-block'}}],
    children: [...cetQuestions.map(question => ({type: 'question', questionId: question.id,
      links: [{type: 'shared_context', toNodeId: 'shared-reading'}]})), passage]}]};
  const cetView = browser(cet, cetQuestions, new Map(), cetRoot);
  await waitFor(() => cetView.d.querySelectorAll('.question-card').length === 2, 'CET reading paper');
  assert.deepEqual([...cetView.d.querySelectorAll('.paper-section-title')].map(node => node.textContent),
    ['Part III Reading', 'Passage One']);
  assert.equal([...cetView.d.querySelectorAll('.paper-unit')]
    .filter(node => node.textContent === articleBody).length, 1,
  'structured article and matching raw source block appear only once');
  assert(cetView.d.querySelector('.paper-unit')
    .compareDocumentPosition(cetView.d.querySelector('.question-card')) &
    cetView.w.Node.DOCUMENT_POSITION_FOLLOWING, 'linked article precedes its first question');
  assert.equal(cetView.d.querySelectorAll('.question-context').length, 0,
    'semantic article is not repeated on either question');
  assert.equal(cetView.d.querySelectorAll('.content-block').length, 4,
    'identical shared text appears once while distinct text from the same block remains');
  assert.equal(cetView.d.querySelectorAll('.question-card .option').length, 8,
    'choices remain attached to their individual questions');
  cetView.dom.window.close();

  const cetOptionPaper = {...cet, id: 'cet4:2021-12-01', questionCount: 1};
  const cetOptionSource = JSON.parse(fs.readFileSync(path.join(__dirname,
    '../structured/papers/cet4/2021-12-01.json'), 'utf8'));
  const optionParagraph = cetOptionSource.blocks.find(block => block.id === 'b-5-4');
  const listeningInstruction = cetOptionSource.blocks.find(block => block.id === 'b-1-5');
  assert(optionParagraph?.text.startsWith('A) '));
  assert(listeningInstruction?.text.startsWith('Directions: In this section'));
  const cetOptionQuestion = {...cetQuestions[0], id: `${cetOptionPaper.id}:q-36-1`,
    number: '36', context: null, contentBlocks: []};
  const cetOptionRoot = {type: 'paper', children: [{type: 'section',
    title: 'Part III Reading Comprehension', children: [{type: 'section',
      title: 'Section B', units: [listeningInstruction, optionParagraph].map(block =>
        ({type: 'paragraph', text: block.text, contentHtml: block.contentHtml,
          provenance: {sourceBlockId: `${cetOptionPaper.id}:${block.id}`}})),
      children: [{type: 'question', questionId: cetOptionQuestion.id}]}]}]};
  const cetOptionView = browser(cetOptionPaper, [cetOptionQuestion], new Map(),
    cetOptionRoot, {paperId: cetOptionPaper.id, paragraphs: [
      {id: 'listening-directions', kind: 'instruction',
        sourceBlockIds: [`${cetOptionPaper.id}:b-1-5`], paragraphIndex: 0,
        sourceText: listeningInstruction.text, translationEligible: true,
        translationZh: '听力说明译文。'},
      {id: 'section-b-A', kind: 'passage_option',
        sourceBlockIds: [`${cetOptionPaper.id}:b-5-4`], paragraphIndex: 0,
        sourceText: optionParagraph.text, translationEligible: true,
        translationZh: '匹配题 A 段译文。'}]});
  await requestTranslations(cetOptionView, 2,
    'CET listening instruction and Section B option paragraph aligned');
  const originalOption = cetOptionView.d.querySelector('[data-source-block-id="cet4:2021-12-01:b-5-4"]');
  assert.equal(originalOption.nextElementSibling.textContent, '匹配题 A 段译文。');
  assert.equal(originalOption.textContent.trim(), optionParagraph.text);
  assert.equal(cetOptionView.d.querySelector('[data-source-block-id="cet4:2021-12-01:b-1-5"]')
    .nextElementSibling.textContent, '听力说明译文。');
  assert.equal(cetOptionView.d.querySelectorAll('.question-card .option').length, 4,
    'short A–D answer choices remain unchanged');
  cetOptionView.dom.window.close();

  const splitOptionPaper = {...cet, id: 'cet4:2016-12-03', questionCount: 1};
  const splitOptionSource = JSON.parse(fs.readFileSync(path.join(__dirname,
    '../structured/papers/cet4/2016-12-03.json'), 'utf8'));
  const splitOptionBlocks = ['b-1-15', 'b-1-16'].map(id =>
    splitOptionSource.blocks.find(block => block.id === id));
  assert(splitOptionBlocks.every(Boolean), 'split Section B source blocks exist');
  const splitOptionQuestion = {...cetQuestions[0], id: `${splitOptionPaper.id}:q-36-1`,
    number: '36', context: null, contentBlocks: []};
  const splitOptionRoot = {type: 'paper', children: [{type: 'section',
    title: 'Section B', units: splitOptionBlocks.map(block =>
      ({type: block.role === 'choices' ? 'options' : 'paragraph', text: block.text,
        contentHtml: block.contentHtml,
        provenance: {sourceBlockId: `${splitOptionPaper.id}:${block.id}`}})),
    children: [{type: 'question', questionId: splitOptionQuestion.id}]}]};
  const splitOptionView = browser(splitOptionPaper, [splitOptionQuestion], new Map(), splitOptionRoot,
    {paperId: splitOptionPaper.id, paragraphs: [{id: 'split-section-b-A',
      kind: 'passage_option', sourceBlockIds: splitOptionBlocks.map(block =>
        `${splitOptionPaper.id}:${block.id}`), paragraphIndex: 0,
      sourceText: splitOptionBlocks.map(block => block.text).join(' '),
      translationEligible: true, translationZh: '跨两个源块的 A 段译文。'}]});
  await requestTranslations(splitOptionView, 1,
    'split option prose aligns across the source option and continuation');
  const splitOptionEnd = splitOptionView.d.querySelector(
    '[data-source-block-id="cet4:2016-12-03:b-1-16"]');
  assert.equal(splitOptionEnd.nextElementSibling?.textContent, '跨两个源块的 A 段译文。');
  assert.equal(splitOptionView.d.querySelector('#paragraph-translation-toggle').dataset.unmatched, '0');
  assert.equal(splitOptionView.d.querySelector(
    '[data-source-block-id="cet4:2016-12-03:b-1-15"]').textContent.replace(/\s+/g, ''),
    splitOptionBlocks[0].text.replace(/\s+/g, ''), 'the long A option stays in English');
  splitOptionView.dom.window.close();

  const reorderedPaper = {...cet, id: 'cet4:2015-06-01', title: '2015 年 6 月英语四级'};
  const ordered = [45, 46, 56].map(number => ({...cetQuestions[0],
    id: `${reorderedPaper.id}:q-${number}-1`, number: String(number),
    stem: `${number}. Source question`, context: null, contentBlocks: []}));
  const reorderedTree = {id: 'paper', type: 'paper', children: [
    {id: 'section-a', type: 'section', title: 'Part A', children: [
      {type: 'question', questionId: ordered[0].id},
      {id: 'nested', type: 'section', title: 'Passage Two', children: [
        {type: 'question', questionId: ordered[2].id}]},
      {type: 'question', questionId: ordered[1].id}
    ]}
  ]};
  const reorderedView = browser(reorderedPaper, ordered, new Map(), reorderedTree);
  await waitFor(() => reorderedView.d.querySelectorAll('.question-card').length === 3,
    'v1 order through a nonordinal semantic tree');
  assert.deepEqual([...reorderedView.d.querySelectorAll('.question-card')]
    .map(card => card.dataset.questionId), ordered.map(question => question.id),
  'the v1 paper order is authoritative when semantic DFS differs');
  reorderedView.dom.window.close();

  const source2026 = JSON.parse(fs.readFileSync(path.join(__dirname,
    '../structured/papers/kaoyan/2026-01.json'), 'utf8'));
  const realBlock = id => {
    const block = source2026.blocks.find(item => item.id === id);
    assert(block, `Missing real 2026 source block ${id}`);
    return {type: id === 'b-12-5' ? 'figure' : 'paragraph', text: block.text,
      contentHtml: block.contentHtml,
      provenance: {sourceBlockId: `kaoyan:2026-01:${id}`}};
  };
  const kaoyan = {id: 'kaoyan:2026-01', title: '2026年考研英语一', category: 'kaoyan',
    categoryLabel: '考研英语', kind: 'questions', questionCount: 3};
  const clozeLabel = {id: 'kaoyan:2026-01:group:b-1-2', kind: 'cloze', text: '完形填空',
    sourceTitle: 'Section I Use of English', sourceBlockId: 'kaoyan:2026-01:b-1-2'};
  const clozeQuestions = [1, 2].map(number => ({id: `kaoyan:2026-01:q-${number}-1`,
    number: String(number), questionType: 'single_choice', status: 'complete',
    stem: `${number}. Choose the best word`, labels: [clozeLabel],
    context: {kind: 'passage', text: source2026.blocks.find(b => b.id === 'b-1-5').text,
      instructionText: source2026.blocks.find(b => b.id === 'b-1-4').text,
      instructionSourceBlocks: ['b-1-3', 'b-1-4'], passageSourceBlocks: ['b-1-5']},
    options: 'ABCD'.split('').map(letter => ({id: `2026-${number}-${letter}`,
      label: letter, text: `${letter} word`})), contentBlocks: []}));
  clozeQuestions[0].stem = '';
  const readingQuestion = {...clozeQuestions[0], id: 'kaoyan:2026-01:q-21-1',
    number: '21', stem: '21. What happened?', context: null,
    labels: [{id: 'kaoyan:2026-01:group:b-3-1', kind: 'reading',
      text: '阅读理解 · Text 1', sourceTitle: 'Text 1', sourceBlockId: 'kaoyan:2026-01:b-3-1'}]};
  const clozePassage = {id: 'cloze-context', type: 'passage', title: 'passage',
    units: [{type: 'paragraph', text: clozeQuestions[0].context.text,
      provenance: {jsonPath: '$.questions[0].context.text'}}], children: []};
  const kaoyanRoot = {type: 'paper', children: [
    {type: 'section', title: 'Section I Use of English',
      units: [realBlock('b-1-3'), realBlock('b-1-4'), realBlock('b-1-5')],
      children: [...clozeQuestions.map(question => ({type: 'question', questionId: question.id,
        links: [{type: 'shared_context', toNodeId: 'cloze-context'}]})), clozePassage]},
    {type: 'section', title: 'Section II Reading Comprehension', units: [], children: [
      {id: 'part-a', type: 'section', title: 'Part A', units: [realBlock('b-2-23'), realBlock('b-2-24')], children: [
        {id: 'text-1', type: 'section', title: 'Text 1', units: [realBlock('b-3-1'), realBlock('b-3-2'),
          realBlock('b-3-3')], children: [{type: 'question', questionId: readingQuestion.id}]}
      ]},
      {id: 'part-b', type: 'section', title: 'Part B', units: [realBlock('b-12-5')], children: []}
    ]}
  ]};
  const clozeAnswers = new Map(clozeQuestions.map(question => [question.id, {
    status: 'explicit', value: 'B', correctOptionIds: [question.options[1].id],
    sourceContentBlocks: []
  }]));
  const kaoyanView = browser(kaoyan, [...clozeQuestions, readingQuestion], clozeAnswers, kaoyanRoot);
  await waitFor(() => kaoyanView.d.querySelectorAll('.question-card').length === 3,
    'real 2026 cloze source rendered');
  assert.equal(kaoyanView.d.querySelector('#question-1 .question-stem'), null,
    'cloze blank uses the shared passage without a missing-stem placeholder');
  assert.equal(kaoyanView.d.querySelectorAll('.question-card .question-kind').length, 0,
    'Kaoyan English question cards do not show generic type or pending badges');
  const tocOptions = [...kaoyanView.d.querySelector('#paper-toc-select').options];
  assert.deepEqual(tocOptions.map(option => option.textContent.trim()), [
    '选择章节或题目', 'Section I Use of English', '第 1 题', '第 2 题',
    'Section II Reading Comprehension', 'Part A', 'Text 1', '第 21 题', 'Part B'
  ], 'directory follows the rendered Section, Part, Text, and question order');
  assert.equal(kaoyanView.d.querySelector('#paper-section-1').textContent,
    'Section I Use of English');
  kaoyanView.d.querySelector('#paper-toc-select').value = 'question-3';
  kaoyanView.d.querySelector('#paper-toc-select').dispatchEvent(new kaoyanView.w.Event('change'));
  assert.equal(kaoyanView.w.location.hash, '#question-3', 'directory selection jumps to the question');
  assert(kaoyanView.d.querySelector('#question-1 .options-list .option'),
    'hiding the cloze stem does not remove its choices');
  const clozeArticle = kaoyanView.d.querySelector('.paper-passage');
  assert(clozeArticle && clozeArticle.textContent.includes('Advances in artificial intelligence'));
  assert.equal(kaoyanView.d.querySelectorAll('[data-group-id="kaoyan:2026-01:group:b-1-2"]').length, 1,
    'one shared passage for both cloze questions');
  assert.equal(clozeArticle.querySelectorAll('.blank').length, 3,
    'only source-marked blanks 1–3 receive underlines');
  assert.deepEqual([...clozeArticle.querySelectorAll('.blank')].map(node => node.textContent.trim()),
    ['1', '2', '3']);
  assert(!clozeArticle.textContent.includes('Directions:'), 'directions stay outside the article');
  assert.equal(kaoyanView.d.querySelectorAll('.paper-passage').length, 3,
    'cloze, reading, and Part B material share the same presentation class');
  assert(kaoyanView.d.querySelector('.paper-section .paper-section .paper-section .paper-passage')
    .textContent.includes('For thousands of years, donkeys'));
  assert.equal(kaoyanView.d.querySelectorAll('.question-group-label, .paper-passage-title').length, 0,
    'group data does not repeat generic labels in the article or on each question');
  assert.equal(kaoyanView.d.querySelectorAll('.paper-directions').length, 2);
  assert([...kaoyanView.d.querySelectorAll('.paper-directions')].every(node =>
    node.querySelector('strong')?.textContent === 'Directions:' &&
    node.querySelector('.paper-instruction')?.textContent.trim()));
  const fullPaperCss = fs.readFileSync(path.join(__dirname, 'full-paper.css'), 'utf8');
  assert.match(fullPaperCss, /\.paper-passage\{[^}]*background:transparent/);
  assert.match(fullPaperCss, /\.paper-passage \.paper-unit \.paragraph\{text-align:justify/);
  assert.match(fullPaperCss, /\.paper-directions-label\{display:block/);
  assert.match(fullPaperCss,
    /\.paper-directions\{[^}]*padding:16px 20px;[^}]*background:#f8fafc;[^}]*border-left:3px solid #bfd1e0/,
    'all Directions use the same quote inset, pale background, and left rule');
  assert.match(fullPaperCss, /\.paper-directions\{[^}]*border-radius:0[;}]/,
    'Directions quote corners remain square');
  const flowchart = kaoyanView.d.querySelector('.paper-unit-figure figure.flowchart img');
  assert(flowchart, 'textless semantic figure still displays its source image');
  assert.equal(flowchart.getAttribute('src'),
    '/english-exams-reflow-latex/kaoyan/papers/2026-01.assets/figure-012-004.svg');
  assert.equal(flowchart.parentElement.getAttribute('style'), null,
    'source inline style is not copied into the practice page');
  kaoyanView.w.location.hash = '#question-1';
  kaoyanView.d.querySelector('#immersive-toggle').click();
  assert(kaoyanView.d.body.classList.contains('full-paper-immersive'));
  assert.equal(kaoyanView.d.querySelectorAll('#immersive-reading .question-card').length, 0);
  assert.equal(kaoyanView.d.querySelectorAll('#immersive-questions .question-card').length, 3);
  assert.deepEqual([...kaoyanView.d.querySelector('#paper-toc-select').options]
    .map(option => option.textContent.trim()), [
      '选择大题', 'Section I Use of English · 第 1 题–第 2 题',
      'Section II Reading Comprehension / Part A / Text 1 · 第 21 题'
    ], 'immersion directory switches source groups, not individual blanks');
  assert.equal(kaoyanView.d.querySelectorAll('#immersive-questions .question-card:not([hidden])').length,
    2, 'every cloze blank is on the same answer sheet');
  assert.equal(kaoyanView.d.querySelector('#immersive-question-tabs').hidden, true,
    'cloze answers do not require question-by-question navigation');
  assert.equal(kaoyanView.d.querySelector('#immersive-group-check').hidden, false);
  assert.equal(kaoyanView.d.querySelectorAll('#immersive-directory button').length, 2,
    'the immersive directory is a persistent left rail of whole source groups');
  assert.equal(kaoyanView.d.querySelector('#immersive-directory button.is-active')?.dataset.groupId,
    'paper-section-1');
  kaoyanView.d.querySelector('#question-1 .option input').click();
  kaoyanView.d.querySelector('#immersive-group-check').click();
  await waitFor(() => kaoyanView.d.querySelector('#immersive-group-check').textContent === '重新作答',
    'cloze group answer reveal');
  assert.equal(kaoyanView.d.querySelectorAll('#immersive-questions .question-card:not([hidden]) .answer-panel:not([hidden])').length,
    2, 'group check evaluates all cloze blanks together');
  assert(kaoyanView.d.querySelector('#question-1 .option.is-wrong'));
  kaoyanView.d.querySelector('#immersive-group-check').click();
  assert.equal(kaoyanView.d.querySelector('#question-1 .option input').disabled, false,
    'a checked group can be attempted again');
  assert.equal(kaoyanView.d.querySelector('#question-1 .option input').checked, false);
  assert(kaoyanView.d.querySelector('#immersive-reading .paper-passage')
    .textContent.includes('Advances in artificial intelligence'));
  assert.equal(kaoyanView.d.querySelectorAll('#immersive-questions .paper-passage').length, 0);
  assert(kaoyanView.d.querySelector('#immersive-questions #question-1 .option'));
  kaoyanView.d.querySelector('#immersive-directory button[data-group-id="paper-section-4"]').click();
  assert.equal(kaoyanView.w.location.hash, '#paper-section-4');
  assert.equal(kaoyanView.d.querySelector('#immersive-directory button.is-active')?.dataset.groupId,
    'paper-section-4');
  assert.deepEqual([...kaoyanView.d.querySelectorAll('#immersive-questions .question-card:not([hidden])')]
    .map(card => card.querySelector('.question-number').textContent), ['第 21 题'],
  'directory replaces the whole source group and its answer area');
  kaoyanView.d.querySelector('#immersive-toggle').click();
  assert.equal(kaoyanView.d.querySelectorAll('#question-list .question-card').length, 3,
    'leaving immersion restores the same question cards to source order');
  assert.equal(kaoyanView.d.querySelector('#immersive-workspace').hidden, true);
  kaoyanView.dom.window.close();

  const translatedBlock = source2026.blocks.find(block => block.id === 'b-1-5');
  const readingBlock = source2026.blocks.find(block => block.id === 'b-3-2');
  const translations = {paperId: kaoyan.id, paragraphs: [
    {id: 'cloze-1', sourceBlockIds: [`${kaoyan.id}:b-1-5`], paragraphIndex: 0,
      sourceText: translatedBlock.text, translationEligible: true,
      translationZh: '测试译文：人工智能正在发展。'},
    {id: 'reading-1', sourceBlockIds: [`${kaoyan.id}:b-3-2`], paragraphIndex: 0,
      sourceText: readingBlock.text, translationEligible: true,
      translationZh: '测试译文：阅读段落。'},
    {id: 'stale', sourceBlockIds: [`${kaoyan.id}:b-3-3`], paragraphIndex: 0,
      sourceText: 'A stale source paragraph.', translationEligible: true,
      translationZh: '过期译文不应显示。'},
    {id: 'unfinished', sourceBlockIds: [`${kaoyan.id}:b-3-3`], paragraphIndex: 0,
      sourceText: source2026.blocks.find(block => block.id === 'b-3-3').text,
      translationEligible: false, translationZh: '未完成译文不应显示。'}
  ]};
  const translationView = browser(kaoyan, [...clozeQuestions, readingQuestion],
    clozeAnswers, kaoyanRoot, translations);
  const translationToggle = await requestTranslations(translationView, 2,
    'two source-aligned translations loaded');
  translationToggle.click();
  const sourceUnit = translationView.d.querySelector('[data-source-block-id="kaoyan:2026-01:b-1-5"]');
  const originalEnglish = sourceUnit.textContent;
  assert.equal(translationToggle.hidden, false);
  assert.equal(translationToggle.getAttribute('aria-pressed'), 'false');
  assert.equal(translationToggle.dataset.attached, '2');
  assert.equal(translationToggle.dataset.unmatched, '1',
    'stale sidecar records are reported separately from attached translations');
  assert(translationView.warnings.some(parts => parts.at(-1).includes('stale')),
    'unmatched source IDs are available for diagnosis');
  assert([...translationView.d.querySelectorAll('.paper-paragraph-translation')]
    .every(node => node.hidden), 'answer-revealing cloze translation starts hidden');
  assert.equal(sourceUnit.nextElementSibling?.className, 'paper-paragraph-translation',
    'translation follows the source paragraph as its own node');
  assert.equal(sourceUnit.textContent, originalEnglish,
    'adding a translation does not change the English source node');
  translationToggle.click();
  assert.equal(translationToggle.getAttribute('aria-pressed'), 'true');
  assert([...translationView.d.querySelectorAll('.paper-paragraph-translation')]
    .every(node => !node.hidden));
  translationView.d.querySelector('#immersive-toggle').click();
  assert(translationView.d.body.classList.contains('full-paper-translation-review'),
    'immersive translation review is active only after the learner requests it');
  assert(translationView.d.querySelector('#immersive-reading .paper-translatable-source'),
    'immersive reading marks the English source for replacement without changing its text');
  const interactiveEnglish = translationView.d.querySelector(
    '#immersive-reading .paper-translatable-source');
  interactiveEnglish.click();
  assert.equal(translationView.d.querySelector('#immersive-translation-overlay').hidden, false);
  assert.equal(translationView.d.querySelector('#immersive-translation-text').textContent,
    '测试译文：人工智能正在发展。');
  translationView.d.querySelector('#immersive-translation-overlay').click();
  assert.equal(translationView.d.querySelector('#immersive-translation-overlay').hidden, true,
  'clicking the Chinese overlay restores the English original');
  interactiveEnglish.click();
  translationView.d.querySelector('#immersive-directory button[data-group-id="paper-section-4"]').click();
  assert.equal(translationView.d.querySelector('#immersive-translation-overlay').hidden, true,
    'switching source groups closes the single-paragraph overlay');
  assert.equal(translationView.d.querySelectorAll('#immersive-reading .paper-paragraph-translation').length,
    2, 'immersive source pane keeps the paragraph translations');
  assert.equal(translationView.d.querySelectorAll('#immersive-questions .paper-paragraph-translation').length,
    0, 'translations do not enter the answer pane');
  translationToggle.click();
  assert(!translationView.d.body.classList.contains('full-paper-translation-review'));
  assert([...translationView.d.querySelectorAll('.paper-paragraph-translation')]
    .every(node => node.hidden));
  translationView.d.querySelector('#immersive-toggle').click();
  assert.equal(sourceUnit.textContent, originalEnglish);
  assert.equal(translationView.calls.filter(url => url.endsWith('/answer')).length, 0,
    'translations never request answer data');
  translationView.dom.window.close();

  const completeCloze = {paperId: kaoyan.id, paragraphs: [5, 6, 7, 8, 9].map(number => {
    const block = source2026.blocks.find(item => item.id === `b-1-${number}`);
    return {id: `cloze-${number}`, sourceBlockIds: [`${kaoyan.id}:${block.id}`],
      paragraphIndex: 0, sourceText: block.text, translationEligible: true,
      translationZh: '完整段落的中文译文用于检验固定高度的沉浸模式。'.repeat(10)};
  })};
  const completeClozeRoot = structuredClone(kaoyanRoot);
  completeClozeRoot.children[0].units.push(...[6, 7, 8, 9]
    .map(number => realBlock(`b-1-${number}`)));
  const completeClozeQuestions = clozeQuestions.map(question => ({...question,
    context: {...question.context, passageSourceBlocks: [5, 6, 7, 8, 9]
      .map(number => `b-1-${number}`)}}));
  const completeClozeView = browser(kaoyan, completeClozeQuestions, new Map(),
    completeClozeRoot, completeCloze);
  await requestTranslations(completeClozeView, 5, 'all five cloze paragraphs aligned');
  completeClozeView.d.querySelector('#immersive-toggle').click();
  assert.equal(completeClozeView.d.querySelectorAll(
    '#immersive-reading .paper-translatable-source').length, 5);
  assert.equal(completeClozeView.d.querySelectorAll(
    '#immersive-reading .paper-paragraph-translation:not([hidden])').length, 5);
  assert.equal(completeClozeView.d.querySelectorAll(
    '#immersive-reading .paper-paragraph-translation.immersive-translation-selected').length, 0,
  'five translations stay concealed in the fixed immersive reading pane');
  assert.equal(completeClozeView.d.querySelector('#immersive-translation-overlay').hidden, true);
  const clozeSources = [...completeClozeView.d.querySelectorAll(
    '#immersive-reading .paper-translatable-source')];
  clozeSources[0].click();
  assert.equal(completeClozeView.d.querySelector('#immersive-translation-overlay').hidden, false);
  assert(completeClozeView.d.querySelector('#immersive-translation-text').textContent.length > 100);
  completeClozeView.d.querySelector('#immersive-translation-overlay').dispatchEvent(
    new completeClozeView.w.KeyboardEvent('keydown', {key: 'Escape', bubbles: true}));
  assert.equal(completeClozeView.d.querySelector('#immersive-translation-overlay').hidden, true,
    'Escape dismisses the selected paragraph without paging or scrolling');
  clozeSources[1].click();
  assert.equal(completeClozeView.d.querySelector('#immersive-translation-overlay').hidden, false);
  assert.equal(completeClozeView.d.querySelectorAll(
    '#immersive-questions .paper-paragraph-translation:not([hidden])').length, 0);
  assert.match(fullPaperCss, /full-paper-translation-review #immersive-reading \.paper-paragraph-translation,\s*body\.full-paper-immersive\.full-paper-translation-review #immersive-reading \.paper-word-bank-translations\{display:none!important/);
  completeClozeView.d.querySelector('#paragraph-translation-toggle').click();
  assert(!completeClozeView.d.body.classList.contains('full-paper-translation-review'));
  assert.equal(completeClozeView.d.querySelectorAll(
    '#immersive-reading .paper-paragraph-translation:not([hidden])').length, 0);
  completeClozeView.dom.window.close();

  const originalQuestion21 = source2026.questions.find(question => question.number === '21');
  const questionPrompt = {...originalQuestion21, id: `${kaoyan.id}:${originalQuestion21.id}`,
    contentBlocks: []};
  const questionPromptView = browser(kaoyan, [questionPrompt], new Map(), null,
    {paperId: kaoyan.id, paragraphs: [{id: 'reading-question-21', kind: 'question_prompt',
      sourceBlockIds: [`${kaoyan.id}:${questionPrompt.sourceBlocks[0]}`],
      paragraphIndex: 0, sourceText: questionPrompt.stem,
      translationEligible: true, translationZh: '第 21 题题干译文。'}]});
  await requestTranslations(questionPromptView, 1,
    'English reading question prompt aligned');
  const questionStem = questionPromptView.d.querySelector('#question-1 .question-stem');
  assert.equal(questionStem.nextElementSibling.textContent, '第 21 题题干译文。');
  assert.equal(questionStem.textContent, questionPrompt.stem);
  assert.equal(questionPromptView.d.querySelectorAll('#question-1 .option').length, 4,
    'question translation leaves A–D choices intact');
  questionPromptView.dom.window.close();

  const missingAnswers = new Map(clozeQuestions.map(question => [question.id, {
    status: 'missing', correctOptionIds: [], sourceContentBlocks: []
  }]));
  const missingView = browser(kaoyan, [...clozeQuestions, readingQuestion], missingAnswers, kaoyanRoot);
  await waitFor(() => missingView.d.querySelectorAll('.question-card').length === 3,
    'missing-answer cloze loaded');
  const preservedInput = missingView.d.querySelector('#question-1 .option input');
  preservedInput.click();
  missingView.d.querySelector('#question-1 [data-action="reveal"]').click();
  await waitFor(() => !missingView.d.querySelector('#question-1 .answer-panel').hidden,
    'ordinary mode missing answer shown');
  assert.equal(preservedInput.disabled, true);
  missingView.d.querySelector('#immersive-toggle').click();
  missingView.d.querySelector('#immersive-group-check').click();
  await waitFor(() => missingView.d.querySelector('#immersive-group-check').textContent.includes('暂无参考答案'),
    'missing group answers reported');
  assert.equal(preservedInput.checked, true, 'a missing answer must preserve the learner selection');
  assert.equal(preservedInput.disabled, false, 'a missing answer must not lock the question');
  assert.equal(missingView.d.querySelector('#question-1 .answer-panel').hidden, true);
  assert.equal(missingView.d.querySelector('#immersive-group-check').disabled, false,
    'the group may retry after answers become available');
  missingView.dom.window.close();

  const sourceQuestion = number => {
    const record = source2026.questions.find(question => String(question.number) === String(number));
    assert(record, `Missing source question ${number}`);
    return {...record, id: `${kaoyan.id}:${record.id}`, contentBlocks: record.contentBlocks || []};
  };
  const partBQuestion = {...sourceQuestion(41), labels: [{kind: 'matching', text: '阅读匹配 · Part B'}]};
  const partCQuestion = sourceQuestion(46);
  const contextMaterial = (id, context) => ({id, type: 'material', title: context.kind,
    units: context.text.split(/\n\n+/).map(text => ({type: 'paragraph', text,
      provenance: {jsonPath: '$.questions[0].context.text'}})), children: []});
  const partBContextId = 'part-b-context';
  const partCContextId = 'part-c-context';
  const sourceContextRoot = {id: 'paper', type: 'paper', children: [
    {id: 'reading', type: 'section', title: 'Section II Reading Comprehension', children: [
      {id: 'part-b', type: 'section', title: 'Part B',
        units: ['b-11-2', 'b-11-3', 'b-11-4', 'b-12-4', 'b-12-5'].map(realBlock),
        children: [{type: 'question', questionId: partBQuestion.id,
          links: [{type: 'shared_context', toNodeId: partBContextId}]}]},
      {id: 'part-c', type: 'section', title: 'Part C',
        units: ['b-12-7', 'b-12-8', 'b-13-1', 'b-13-2', 'b-13-3', 'b-13-4', 'b-13-5']
          .map(realBlock),
        children: [{type: 'question', questionId: partCQuestion.id,
          links: [{type: 'shared_context', toNodeId: partCContextId}]}]}
    ]},
    contextMaterial(partBContextId, partBQuestion.context),
    contextMaterial(partCContextId, partCQuestion.context)
  ]};
  const partBOptionBlock = source2026.blocks.find(block => block.id === 'b-11-4');
  const contextView = browser(kaoyan, [partBQuestion, partCQuestion], new Map(),
    sourceContextRoot, {paperId: kaoyan.id, paragraphs: [{id: 'part-b-A',
      kind: 'passage_option', sourceBlockIds: [`${kaoyan.id}:b-11-4`],
      paragraphIndex: 0, sourceText: partBOptionBlock.text,
      translationEligible: true, translationZh: '排序题 A 段译文。'}]});
  await waitFor(() => contextView.d.querySelectorAll('.question-card').length === 2,
    '2026 Part B and C source material loaded');
  await requestTranslations(contextView, 1,
    'Kaoyan Part B option paragraph aligned');
  assert.equal(contextView.d.querySelector('[data-source-block-id="kaoyan:2026-01:b-11-4"]')
    .nextElementSibling.textContent, '排序题 A 段译文。');
  const partBSection = contextView.d.querySelector('#question-1').closest('.paper-section');
  const partCSection = contextView.d.querySelector('#question-2').closest('.paper-section');
  assert.equal(partBSection.querySelectorAll('.paper-directions').length, 1,
    'Part B source Directions appear once before the choice bank');
  assert.equal(partCSection.querySelectorAll('.paper-directions').length, 1,
    'Part C source Directions appear once before its passage');
  assert.equal(partBSection.querySelectorAll('.paper-unit').length, 4,
    'Part B linked context is not repeated below the flowchart');
  assert.equal(partCSection.querySelectorAll('.paper-unit').length, 6,
    'Part C linked context is not repeated below its source passage');
  assert.equal(contextView.d.querySelectorAll('.question-card .question-context').length, 0,
    'both questions use the source context above the cards');
  assert.equal(partBSection.querySelector('#question-1 .question-stem'), null,
    'a bare matching question number is not repeated below its group');
  const translationUnderlines = [...partCSection.querySelectorAll('.paper-passage u')];
  assert.equal(translationUnderlines.length, 5,
    'source line fragments combine into five continuous translation underlines');
  assert(translationUnderlines[0].textContent.includes('literacy has shifted over time'),
    'underlined source joins adjacent spans without dropping the separating space');
  for (const id of ['b-13-2', 'b-13-3', 'b-13-4', 'b-13-5']) {
    const expected = source2026.blocks.find(block => block.id === id).text.replace(/\s+/g, '');
    const rendered = partCSection.querySelector(`[data-source-block-id="kaoyan:2026-01:${id}"]`)
      .textContent.replace(/\s+/g, '');
    assert.equal(rendered, expected, `translation source text ${id} is preserved exactly`);
  }
  const translationStem = partCSection.querySelector('#question-2 .question-stem');
  assert(translationStem, 'the translation card retains its one-sentence excerpt');
  assert(translationStem.textContent.includes('Tracing the history of the term'),
    'the translation excerpt is shown below question 46');
  assert.equal(partCSection.querySelector('#question-2 .question-content').textContent.trim(), '',
    'the full source paragraph is not repeated below the translation excerpt');
  assert(partCSection.querySelector('#question-2 textarea'),
    'translation answer input remains available');
  assert.equal(contextView.d.querySelectorAll('.paper-shared-material:not(.paper-passage)').length, 0,
    'linked context does not become a second framed block');
  assert.match(fullPaperCss, /\.paper-shared-material\{padding:0;border:0;background:transparent/);
  contextView.dom.window.close();

  const source2024 = JSON.parse(fs.readFileSync(path.join(__dirname,
    '../structured/papers/kaoyan/2024-01.json'), 'utf8'));
  const record2024 = source2024.questions.find(question => String(question.number) === '41');
  assert(record2024?.context?.kind === 'matching_comments');
  const paper2024 = {...kaoyan, id: 'kaoyan:2024-01', title: source2024.title};
  const question2024 = {...record2024, id: `${paper2024.id}:${record2024.id}`,
    labels: [{kind: 'matching', text: '阅读匹配 · Part B'}]};
  const sourceBlock2024 = id => {
    const block = source2024.blocks.find(item => item.id === id);
    assert(block, `Missing 2024 source block ${id}`);
    return {type: 'paragraph', text: block.text, contentHtml: block.contentHtml,
      provenance: {sourceBlockId: `${paper2024.id}:${id}`}};
  };
  const root2024 = {id: 'paper', type: 'paper', children: [
    {id: 'reading', type: 'section', title: 'Section II Reading Comprehension', children: [
      {id: 'part-b', type: 'section', title: 'Part B',
        units: ['b-11-2', ...record2024.context.sourceBlocks].map(sourceBlock2024),
        children: [{type: 'question', questionId: question2024.id,
          links: [{type: 'shared_context', toNodeId: 'combined-comments'}]}]}
    ]}, contextMaterial('combined-comments', record2024.context)
  ]};
  const view2024 = browser(paper2024, [question2024], new Map(), root2024);
  await waitFor(() => view2024.d.querySelector('.question-card'), '2024 matching comments loaded');
  const section2024 = view2024.d.querySelector('#question-1').closest('.paper-section');
  assert.equal(section2024.querySelectorAll('.paper-directions').length, 1);
  assert.equal(section2024.querySelectorAll('.paper-shared-material:not(.paper-passage)').length, 0,
    '2024 comments merged across source blocks are not repeated after the source material');
  assert.equal(section2024.querySelector('#question-1 .question-stem'), null,
    '2024 Hannah comment is shown only in its original source position');
  view2024.dom.window.close();

  const emailBlock = source2026.blocks.find(block => block.id === 'b-14-5');
  assert(emailBlock?.text.startsWith('Hi Li Ming,'));
  const writingQuestion = {id: 'kaoyan:2026-01:q-51-1', number: '51',
    questionType: 'free_response', status: 'complete', stem: '51. Directions:',
    labels: [{kind: 'writing', text: '写作 · Part A'}],
    context: null, options: [], contentBlocks: [
      ...['b-14-4', 'b-14-5', 'b-14-6'].map(id => {
        const block = source2026.blocks.find(item => item.id === id);
        return {id: `kaoyan:2026-01:${id}`, role: 'content', text: block.text,
          presentation: block.presentation, images: []};
      })
    ]};
  const writingView = browser(kaoyan, [writingQuestion], new Map());
  await waitFor(() => writingView.d.querySelector('.practice-email-box'), 'real 2026 email prompt');
  assert.deepEqual([...writingView.d.querySelectorAll('.practice-email-box p')]
    .map(node => node.textContent), [
      'Hi Li Ming,',
      'I was really moved by the Chinese families’ handwritten letters you posted yesterday. They are priceless! Could you please tell me a bit more about them? And are they currently on public display somewhere? I’m very keen to see them in person. Thanks.',
      'Yours,', 'Paul'
    ]);
  assert.equal(writingView.d.querySelectorAll('.practice-email-box').length, 1);
  assert.equal(writingView.d.querySelector('.question-stem.paper-directions strong')
    .textContent, 'Directions:');
  assert.deepEqual([...writingView.d.querySelectorAll('.practice-source-instruction')]
    .map(node => node.textContent), [
      'You should write about 100 words on the ANSWER SHEET.',
      'Do not use your own name in the email; use “Li Ming” instead. (10 points)']);
  assert.equal(writingView.d.querySelector('.practice-source-instruction strong').textContent,
    'Do not');
  assert.equal(writingView.d.querySelectorAll('.paper-writing-instruction').length, 2,
    'email frame stays distinct from Directions prose');
  assert(writingView.d.querySelector('.question-stem.paper-directions')
    .textContent.includes('Read the following email from your friend Paul'),
  'opening writing instruction shares the Directions container');
  assert.equal(writingView.d.querySelectorAll('.paper-directions-tail .practice-source-instruction').length, 2,
    'closing writing requirements share a separate Directions container');
  assert.equal(writingView.d.querySelector('.practice-email-box').closest('.paper-directions'), null,
    'email example remains on the white paper');
  writingView.d.querySelector('#immersive-toggle').click();
  assert.equal(writingView.d.querySelectorAll('#immersive-reading .practice-email-box').length, 1,
    'writing source email is available beside the answer area');
  assert(writingView.d.querySelector('#immersive-reading .question-stem.paper-directions'));
  assert(writingView.d.querySelector('#immersive-questions textarea'));
  assert(writingView.d.querySelector('#immersive-questions .practice-email-box')
    .closest('.immersive-source-hidden'), 'the email is not shown twice');
  writingView.d.querySelector('#immersive-toggle').click();
  assert.equal(writingView.d.querySelectorAll('#question-list .practice-email-box').length, 1);
  assert(!writingView.d.querySelector('.practice-email-box').classList.contains('immersive-source-hidden'));
  writingView.dom.window.close();

  const essayQuestion = {...writingQuestion, id: 'kaoyan:2026-01:q-52-1', number: '52',
    stem: '52. Directions:', labels: [{kind: 'writing', text: '写作 · Part B'}],
    contentBlocks: ['b-14-9', 'b-14-10', 'b-14-11', 'b-14-12', 'b-14-13']
      .map(id => {
        const block = source2026.blocks.find(item => item.id === id);
        return {id: `kaoyan:2026-01:${id}`, role: /^b-14-1[012]$/.test(id) ?
          'question' : 'content', text: block.text, images: []};
      })};
  const essayView = browser(kaoyan, [essayQuestion], new Map());
  await waitFor(() => essayView.d.querySelectorAll('.paper-writing-instruction').length === 2,
    'writing Directions keep all source lines');
  assert.deepEqual([...essayView.d.querySelectorAll('.paper-writing-instruction, .paper-writing-item')]
    .map(node => node.textContent.trim()), [
      'Write an essay based on the charts below. In your essay, you should',
      '1) describe the charts briefly,',
      '2) interpret the charts, and',
      '3) give your comments,',
      'Write your answer in 160-200 words on the ANSWER SHEET. (20 points)']);
  assert.deepEqual([...essayView.d.querySelectorAll('.paper-writing-item')]
    .map(node => node.textContent.trim()), [
      '1) describe the charts briefly,',
      '2) interpret the charts, and',
      '3) give your comments,']);
  assert(essayView.d.querySelector('.question-stem.paper-directions')
    .textContent.includes('Write an essay based on the charts below'));
  assert(essayView.d.querySelector('.paper-directions-tail')
    .textContent.includes('Write your answer in 160-200 words'));
  assert([...essayView.d.querySelectorAll('.paper-writing-item')]
    .every(node => !node.closest('.paper-directions')),
  'numbered essay requirements remain ordinary body text');
  essayView.dom.window.close();

  for (const year of ['2024', '2025']) {
    const emailSource = JSON.parse(fs.readFileSync(path.join(__dirname,
      `../structured/papers/kaoyan/${year}-01.json`), 'utf8'));
    const original = emailSource.questions.find(item => item.number === '51');
    assert(original, `${year} writing question exists`);
    const emailQuestion = {...original, id: `${emailSource.id}:${original.id}`,
      contentBlocks: original.sourceBlocks.slice(1).map(id => {
        const block = emailSource.blocks.find(item => item.id === id);
        return {id: `${emailSource.id}:${id}`, role: block.role, text: block.text,
          presentation: block.presentation, images: []};
      })};
    const emailPaper = {id: emailSource.id, title: `${year}年考研英语一`,
      category: 'kaoyan', categoryLabel: '考研英语', kind: 'questions', questionCount: 1};
    const emailTranslations = {paperId: emailPaper.id, paragraphs: ['b-14-5', 'b-14-6']
      .map((id, index) => ({id, kind: 'writing_prompt', paragraphIndex: 0,
        sourceBlockIds: [`${emailPaper.id}:${id}`],
        sourceText: emailSource.blocks.find(block => block.id === id).text,
        translationEligible: true, translationZh: `邮件译文 ${index + 1}`}))};
    const emailView = browser(emailPaper, [emailQuestion], new Map(), null,
      emailTranslations);
    await requestTranslations(emailView, 2,
      `${year} email paragraphs align with source blocks`);
    emailView.d.querySelector('#paragraph-translation-toggle').click();
    const emailBox = emailView.d.querySelector('.practice-email-box');
    assert(emailBox, `${year} email layout preserved`);
    assert.equal(emailView.d.querySelector('#paragraph-translation-toggle').dataset.unmatched, '0');
    assert.equal(emailBox.querySelectorAll('.paper-paragraph-translation').length, 2,
      'email translations follow their English source lines within the email box');
    assert([...emailBox.querySelectorAll('.paper-paragraph-translation')]
      .every(node => node.hidden), 'email translation is hidden by default');
    emailView.dom.window.close();
  }

  const source2026EnglishTwo = JSON.parse(fs.readFileSync(path.join(__dirname,
    '../structured/papers/kaoyan/2026-02.json'), 'utf8'));
  const englishTwoQuestions = ['46', '47', '48'].map(number => {
    const sourceQuestion = source2026EnglishTwo.questions.find(item => item.number === number);
    assert(sourceQuestion, `Missing 2026 English II question ${number}`);
    return {...sourceQuestion, id: `${source2026EnglishTwo.id}:${sourceQuestion.id}`,
      contentBlocks: sourceQuestion.sourceBlocks.slice(1).map(id => {
        const block = source2026EnglishTwo.blocks.find(item => item.id === id);
        return {id: `${source2026EnglishTwo.id}:${id}`, role: block.role,
          text: block.text, presentation: block.presentation, images: []};
      })};
  });
  const englishTwoPaper = {id: source2026EnglishTwo.id,
    title: '2026年考研英语二', category: 'kaoyan', categoryLabel: '考研英语',
    kind: 'questions', questionCount: 3};
  const englishTwoTranslations = {paperId: englishTwoPaper.id, paragraphs:
    ['b-13-3', 'b-13-4', 'b-13-5', 'b-14-4', 'b-14-5', 'b-14-7',
      'b-14-10', 'b-14-11', 'b-14-13'].map((id, index) => ({id, paragraphIndex: 0,
      sourceBlockIds: [`${englishTwoPaper.id}:${id}`],
      sourceText: source2026EnglishTwo.blocks.find(block => block.id === id).text,
      translationEligible: true, translationZh: `英语二正文译文 ${index + 1}`}))};
  const englishTwoView = browser(englishTwoPaper, englishTwoQuestions, new Map(),
    null, englishTwoTranslations);
  await waitFor(() => englishTwoView.d.querySelectorAll('.question-card').length === 3,
    '2026 English II writing and translation');
  await requestTranslations(englishTwoView, 9,
    'English II translation passage and writing instructions aligned');
  englishTwoView.d.querySelector('#paragraph-translation-toggle').click();
  const [translation2026, letter2026, essay2026] =
    [...englishTwoView.d.querySelectorAll('.question-card')];
  assert(translation2026.querySelector('.question-stem.paper-directions')
    .textContent.includes('Translate the following text into Chinese.'));
  assert(!translation2026.querySelector('.question-content').closest('.paper-directions'));
  const firstBodyBlock = translation2026.querySelector(
    '[data-source-block-id="kaoyan:2026-02:b-13-4"]');
  assert(firstBodyBlock, 'whole-text translation keeps source identity on the card body');
  assert.equal(firstBodyBlock.nextElementSibling?.textContent, '英语二正文译文 2',
    'translation is a sibling after its English source paragraph');
  assert.equal(firstBodyBlock.textContent.trim(),
    source2026EnglishTwo.blocks.find(block => block.id === 'b-13-4').text,
    'source paragraph stays unchanged');
  assert(englishTwoView.d.querySelector('#paragraph-translation-toggle').hidden === false);
  assert.equal(englishTwoView.d.querySelector('#paragraph-translation-toggle').dataset.unmatched, '0');
  assert.equal(translation2026.querySelector('[data-source-block-id="kaoyan:2026-02:b-13-3"]')
    .nextElementSibling?.textContent, '英语二正文译文 1');
  assert.equal(letter2026.querySelector('[data-source-block-id="kaoyan:2026-02:b-14-4"]')
    .nextElementSibling?.textContent, '英语二正文译文 4');
  assert.equal(essay2026.querySelector('[data-source-block-id="kaoyan:2026-02:b-14-10"]')
    .nextElementSibling?.textContent, '英语二正文译文 7');
  assert([...englishTwoView.d.querySelectorAll('.paper-paragraph-translation')]
    .every(node => node.hidden));
  for (const card of [letter2026, essay2026]) {
    assert(card.querySelector('.question-stem.paper-directions .paper-writing-instruction'),
      'opening instruction joins Directions heading');
    assert(card.querySelector('.paper-directions-tail .paper-writing-instruction'),
      'closing word-count requirement has a Directions background');
    assert([...card.querySelectorAll('.paper-writing-item')]
      .every(node => !node.closest('.paper-directions')),
    'numbered instructions remain normal paper text');
  }
  assert.equal(letter2026.querySelectorAll('.paper-writing-item').length, 2);
  assert.equal(essay2026.querySelectorAll('.paper-writing-item').length, 2);
  englishTwoView.d.querySelector('#immersive-toggle').click();
  assert(englishTwoView.d.querySelector('#immersive-reading .immersive-card-source')
    .textContent.includes('The influence of wearables'),
  'whole-text translation places its complete article beside the response field');
  assert.equal(englishTwoView.d.querySelectorAll(
    '#immersive-reading .immersive-card-source .paper-paragraph-translation').length, 8,
    'passage and writing source instructions move to the reading pane');
  englishTwoView.d.querySelector('#paragraph-translation-toggle').click();
  assert([...englishTwoView.d.querySelectorAll(
    '#immersive-reading .paper-paragraph-translation')].every(node => !node.hidden));
  assert.equal([...englishTwoView.d.querySelectorAll(
    '#immersive-questions .paper-paragraph-translation:not([hidden])')]
    .filter(node => !node.closest('.immersive-source-hidden')).length, 1,
    'translation instruction remains beside its original Directions in the answer pane');
  assert(translation2026.querySelector('.question-content')
    .classList.contains('immersive-source-hidden'));
  assert(englishTwoView.d.querySelector('#immersive-questions #question-1 textarea'));
  englishTwoView.d.querySelector('#immersive-toggle').click();
  assert(!translation2026.querySelector('.question-content')
    .classList.contains('immersive-source-hidden'));
  englishTwoView.dom.window.close();

  let resolveLateTranslations;
  const lateTranslations = new Promise(resolve => { resolveLateTranslations = resolve; });
  const lateView = browser(englishTwoPaper, englishTwoQuestions, new Map(), null,
    lateTranslations);
  await waitFor(() => lateView.d.querySelectorAll('.question-card').length === 3,
    'English II paper ready before translation sidecar');
  lateView.d.querySelector('#immersive-toggle').click();
  lateView.d.querySelector('#paragraph-translation-toggle').click();
  resolveLateTranslations({paperId: englishTwoPaper.id, paragraphs: [
    englishTwoTranslations.paragraphs.find(record => record.id === 'b-13-4')]});
  await waitFor(() => lateView.d.querySelector(
    '#immersive-reading .paper-paragraph-translation'),
  'late sidecar refreshes the immersive source copy');
  assert.equal(lateView.d.querySelector('#immersive-reading .paper-paragraph-translation').hidden,
    false, 'explicitly requested translation appears when the sidecar arrives');
  lateView.d.querySelector('#paragraph-translation-toggle').click();
  assert.equal(lateView.d.querySelector('#immersive-reading .paper-paragraph-translation').hidden,
    true);
  lateView.d.querySelector('#paragraph-translation-toggle').click();
  lateView.d.querySelector('#immersive-toggle').click();
  assert.equal(lateView.d.querySelector('#question-list .paper-paragraph-translation').hidden,
    false, 'leaving immersion preserves the chosen translation visibility');
  lateView.dom.window.close();

  const legacyWriting = {...writingQuestion, id: 'kaoyan:2000-01:q-36-1',
    stem: '36. Directions:\n1) Describe the pictures.\n2) Give your comments.',
    contentBlocks: []};
  const legacyView = browser({...kaoyan, id: 'kaoyan:2000-01'}, [legacyWriting], new Map());
  await waitFor(() => legacyView.d.querySelector('.question-stem.paper-directions'),
    'older writing directions');
  assert.deepEqual([...legacyView.d.querySelectorAll('.question-content .paper-writing-item')]
    .map(node => node.textContent), ['1) Describe the pictures.', '2) Give your comments.']);
  assert.equal(legacyView.d.querySelector('.question-stem .paper-writing-item'), null);
  legacyView.dom.window.close();

  for (let year = 2010; year <= 2026; year++) {
    const source = JSON.parse(fs.readFileSync(path.join(__dirname,
      `../structured/papers/kaoyan/${year}-02.json`), 'utf8'));
    const sourceQuestion = source.questions.find(item => item.number === '46');
    const translationQuestion = {...sourceQuestion, id: `${source.id}:${sourceQuestion.id}`,
      contentBlocks: sourceQuestion.sourceBlocks.slice(1).map(id => {
        const block = source.blocks.find(item => item.id === id);
        return {id: `${source.id}:${id}`, role: block.role, text: block.text,
          contentHtml: block.contentHtml, images: []};
      })};
    const firstBody = translationQuestion.contentBlocks[1];
    const sidecar = {paperId: source.id, paragraphs: [{id: `${year}-body`,
      sourceBlockIds: [firstBody.id], paragraphIndex: 0, sourceText: firstBody.text,
      translationEligible: true, translationZh: `测试译文 ${year}`}]};
    const translationView = browser({id: source.id, title: `${year}年考研英语二`,
      category: 'kaoyan', categoryLabel: '考研英语', kind: 'questions', questionCount: 1},
    [translationQuestion], new Map(), null, sidecar);
    await waitFor(() => translationView.d.querySelector('.question-card textarea'),
      `${year} English II translation question`);
    const translationCard = translationView.d.querySelector('.question-card');
    const directions = translationCard.querySelector('.question-stem.paper-directions');
    assert(directions, `${year} translation has a dedicated Directions block`);
    assert.equal(directions.querySelector('.paper-directions-label').textContent, 'Directions:');
    assert.equal(directions.querySelectorAll('.paper-instruction').length, 1);
    assert.match(directions.querySelector('.paper-instruction').textContent,
      /^Translate the following text (?:from English )?into Chinese\./);
    assert.equal(translationCard.querySelectorAll('.question-content .content-block').length,
      translationQuestion.contentBlocks.length - 1,
      `${year} translation body retains every source paragraph without repeating instructions`);
    assert.equal(translationCard.querySelector('.question-content .content-block').textContent.trim(),
      translationQuestion.contentBlocks[1].text);
    await requestTranslations(translationView, 1,
      `${year} English II translation sidecar mapped`);
    assert.equal(translationCard.querySelector('.paper-paragraph-translation').hidden, false);
    translationView.dom.window.close();
  }

  const source2025 = JSON.parse(fs.readFileSync(path.join(__dirname,
    '../structured/papers/kaoyan/2025-01.json'), 'utf8'));
  const email2025 = {...writingQuestion, id: 'kaoyan:2025-01:q-51-1',
    contentBlocks: ['b-14-4', 'b-14-5', 'b-14-6', 'b-14-7'].map(id => {
      const block = source2025.blocks.find(item => item.id === id);
      return {id: `kaoyan:2025-01:${id}`, role: 'content', text: block.text,
        presentation: id === 'b-14-7' ? {version: 1, layoutKind: 'writing_instructions',
          instructions: block.presentation.instructions} : block.presentation, images: []};
    })};
  const email2025View = browser({...kaoyan, id: 'kaoyan:2025-01'}, [email2025], new Map());
  await waitFor(() => email2025View.d.querySelector('.practice-email-box'),
    '2025 source email spanning two blocks');
  assert.equal(email2025View.d.querySelectorAll('.practice-email-box').length, 1,
    'adjacent start/end source blocks form a single email frame');
  assert.deepEqual([...email2025View.d.querySelectorAll('.practice-email-box p')]
    .map(node => node.textContent), [
      'Dear Li Ming,',
      'I was really excited to hear that you’d invite some young craftsmen to demonstrate their innovative craft-making on campus. May I know more about what they’ll Show? Also, I’d like to help with your preparation work. Please let me know what I can do.',
      'Yours,', 'Paul'
    ]);
  assert.equal(email2025View.d.querySelectorAll('.practice-source-instruction').length, 2);
  email2025View.dom.window.close();
  const flow2025 = source2025.blocks.find(block => block.id === 'b-12-5');
  assert(flow2025 && !flow2025.text.trim() && flow2025.contentHtml.includes('flowchart'));
  const paper2025 = {...kaoyan, id: 'kaoyan:2025-01', title: '2025年考研英语一'};
  const question2025 = {...clozeQuestions[0], id: 'kaoyan:2025-01:q-41-1', number: '41',
    labels: [], context: null, contentBlocks: [{id: 'kaoyan:2025-01:b-12-5',
      role: 'figure', text: '', images: [{src:
        '/english-exams-reflow-latex/kaoyan/papers/2025-01.assets/figure-012-004.svg'}]}]};
  const root2025 = {type: 'paper', children: [{type: 'section', title: 'Part B', units: [
    {type: 'figure', text: '', contentHtml: flow2025.contentHtml,
      provenance: {sourceBlockId: 'kaoyan:2025-01:b-12-5'}},
    {type: 'figure', text: '', contentHtml:
      '<figure><img src="https://example.invalid/evil.svg" onerror="alert(1)"></figure><script>alert(1)</script>',
    provenance: {sourceBlockId: 'kaoyan:2025-01:b-malicious'}}
  ], children: [{type: 'question', questionId: question2025.id,
    links: [{type: 'shared_context', toNodeId: 'part-b-reference'}]},
    {id: 'part-b-reference', type: 'material', units: [{type: 'paragraph', text: 'Part B'}],
      children: []}]}]};
  const view2025 = browser(paper2025, [question2025], new Map(), root2025);
  await waitFor(() => view2025.d.querySelector('.paper-unit-figure img'), 'real 2025 flowchart');
  assert.equal(view2025.d.querySelectorAll('.paper-unit-figure img').length, 1,
    'the real local figure is preserved and external markup is rejected');
  assert.equal(view2025.d.querySelectorAll('.content-figure img').length, 0,
    'a shared semantic flowchart is not repeated inside the linked question');
  assert.equal([...view2025.d.querySelectorAll('.paper-shared-material:not(.paper-passage)')]
    .filter(node => node.textContent.trim() === 'Part B').length, 0,
  'a linked source heading does not repeat its section heading in a shaded box');
  assert.equal(view2025.d.querySelector('.paper-unit-figure script'), null);
  assert.equal(view2025.d.querySelector('.paper-unit-figure img').getAttribute('src'),
    '/english-exams-reflow-latex/kaoyan/papers/2025-01.assets/figure-012-004.svg');
  view2025.dom.window.close();

  const politics = {id: 'politics:2023-questions', title: '2023 年考研政治真题',
    category: 'politics', categoryLabel: '考研政治', kind: 'questions', questionCount: 1};
  const politicalQuestion = {id: `${politics.id}:q-37-1`, number: '37',
    questionType: 'free_response', status: 'complete', options: [], context: null,
    stem: '37. 结合材料回答问题：\n\n材料1\n\n科技工作者矢志报国。\n\n摘编自《光明日报》',
    stemParagraphs: [{text: '37. 结合材料回答问题：', kind: 'paragraph'},
      {text: '材料1', kind: 'material_label'},
      {text: '科技工作者矢志报国。', kind: 'paragraph'},
      {text: '摘编自《光明日报》', kind: 'material_source'}],
    contentBlocks: [{role: 'content', text: '材料2 科学实践\n摘编自《人民日报》',
      styledParagraphs: [{text: '材料2', kind: 'material_label'},
        {text: '科学实践', kind: 'paragraph'},
        {text: '摘编自《人民日报》', kind: 'material_source'}], images: []}]};
  const political = browser(politics, [politicalQuestion], new Map());
  await waitFor(() => political.d.querySelector('.question-card'), 'politics paper loaded');
  assert.deepEqual([...political.d.querySelectorAll('.material-label')].map(node => node.textContent),
    ['材料1', '材料2']);
  assert.deepEqual([...political.d.querySelectorAll('.material-source')].map(node => node.textContent),
    ['摘编自《光明日报》', '摘编自《人民日报》']);
  const css = fs.readFileSync(path.join(__dirname, '../ui/material.css'), 'utf8');
  assert.match(css, /\.material-label[^}]*font-weight:700/);
  assert.match(css, /\.material-source[^}]*text-align:right/);
  political.dom.window.close();

  const sourceOnlyFixtures = [
    ['cet4:2015-12-03', 'b-1-2'], ['cet6:2014-12-03', 'b-1-2']
  ];
  for (const [paperId, blockId] of sourceOnlyFixtures) {
    const [category, stem] = paperId.split(':');
    const structured = JSON.parse(fs.readFileSync(path.join(__dirname,
      `../structured/papers/${category}/${stem}.json`), 'utf8'));
    const block = structured.blocks.find(item => item.id === blockId);
    const paperMeta = {id: paperId, category, title: structured.title,
      categoryLabel: category, kind: 'questions', questionCount: 1};
    const question = {id: `${paperId}:q-test`, number: '1', questionType: 'free_response',
      stem: '1.', options: [], contentBlocks: []};
    const root = {id: 'root', type: 'paper', children: [
      {id: 'unassigned', type: 'section', title: 'Unassigned source material',
        units: [{type: 'paragraph', text: structured.blocks[0].text,
          provenance: {sourceBlockId: `${paperId}:${structured.blocks[0].id}`}},
        {type: 'paragraph', text: block.text, contentHtml: block.contentHtml,
          provenance: {sourceBlockId: `${paperId}:${blockId}`}}], children: []},
      {id: 'questions', type: 'section', title: 'Questions',
        children: [{id: 'q', type: 'question', questionId: question.id, children: []}]}
    ]};
    const view = browser(paperMeta, [question], new Map(), root,
      {paperId, paragraphs: [{id: `${paperId}:source-prompt`, kind: 'writing_prompt',
        sourceBlockIds: [`${paperId}:${blockId}`], paragraphIndex: 0,
        sourceText: block.text, translationEligible: true, translationZh: '作文说明译文。'}]});
    await requestTranslations(view, 1, `${paperId} unassigned writing prompt`);
    const source = view.d.querySelector(`[data-source-block-id="${paperId}:${blockId}"]`);
    assert(source && source.compareDocumentPosition(view.d.querySelector('.question-card')) &
      view.w.Node.DOCUMENT_POSITION_FOLLOWING,
    'unassigned writing source is presented before question cards');
    assert.equal(source.nextElementSibling.textContent, '作文说明译文。');
    view.dom.window.close();
  }

  for (const [paperId, blockId] of [
    ['cet4:2020-12-02', 'b-3-16'], ['cet4:2021-06-02', 'b-8-19'],
    ['cet6:2020-12-02', 'b-3-15'], ['tem8:2025', 'b-1-22']
  ]) {
    const [category, stem] = paperId.split(':');
    const structured = JSON.parse(fs.readFileSync(path.join(__dirname,
      `../structured/papers/${category}/${stem}.json`), 'utf8'));
    const block = structured.blocks.find(item => item.id === blockId);
    const paperMeta = {id: paperId, category, title: structured.title,
      categoryLabel: category, kind: 'questions', questionCount: 1};
    const question = {id: `${paperId}:q-test`, number: '25', questionType: 'free_response',
      stem: '25.', options: [], contentBlocks: []};
    const root = {id: 'root', type: 'paper', children: [
      {id: 'section', type: 'section', title: 'Section C', children: [
        {id: 'q', type: 'question', questionId: question.id,
          units: [{type: 'other', text: block.text, contentHtml: block.contentHtml,
            provenance: {sourceBlockId: `${paperId}:${blockId}`}}], children: []}
      ]}
    ]};
    const view = browser(paperMeta, [question], new Map(), root,
      {paperId, paragraphs: [{id: `${paperId}:trailing`, kind: 'instruction',
        sourceBlockIds: [`${paperId}:${blockId}`], paragraphIndex: 0,
        sourceText: block.text, translationEligible: true, translationZh: '后续说明译文。'}]});
    await requestTranslations(view, 1, `${paperId} trailing instruction`);
    const source = view.d.querySelector(`[data-source-block-id="${paperId}:${blockId}"]`);
    assert(source && view.d.querySelector('.question-card').compareDocumentPosition(source) &
      view.w.Node.DOCUMENT_POSITION_FOLLOWING,
    'trailing section material follows its preceding question');
    assert.equal(source.nextElementSibling.textContent, '后续说明译文。');
    view.dom.window.close();
  }

  const choicePaperId = 'cet6:2014-12-01';
  const choiceStructured = JSON.parse(fs.readFileSync(path.join(__dirname,
    '../structured/papers/cet6/2014-12-01.json'), 'utf8'));
  const choiceBlock = choiceStructured.blocks.find(item => item.id === 'b-2-33');
  const choiceQuestion = choiceStructured.questions.find(item => String(item.number) === '22');
  const choiceView = browser({id: choicePaperId, category: 'cet6',
    title: choiceStructured.title, categoryLabel: '英语六级', kind: 'questions', questionCount: 1},
  [{...choiceQuestion, id: `${choicePaperId}:${choiceQuestion.id}`,
    options: choiceQuestion.options.map((option, index) => ({...option,
      id: `${choicePaperId}:q-22-1:${index}`})), contentBlocks: []}],
  new Map(), null, {paperId: choicePaperId, paragraphs: [{id: 'long-answer-choice',
    kind: 'writing_prompt', sourceBlockIds: [`${choicePaperId}:b-2-33`],
    paragraphIndex: 0, sourceText: choiceBlock.text, translationEligible: true,
    translationZh: 'A 选项译文。'}]});
  await requestTranslations(choiceView, 1, 'source-backed answer choice line');
  const choiceCard = choiceView.d.querySelector('.question-card');
  const choiceA = choiceCard.querySelector('.option');
  assert.equal(choiceA.querySelector('.option-text').textContent,
    choiceQuestion.options[0].text, 'A choice English stays unchanged');
  assert.equal(choiceA.nextElementSibling.textContent, 'A 选项译文。');
  assert.equal(choiceCard.querySelectorAll('.option').length, 4);
  assert.equal(choiceView.d.querySelector('#paragraph-translation-toggle').dataset.unmatched, '0');
  choiceView.dom.window.close();

  const optionPaper = {id: 'kaoyan:2026-01', category: 'kaoyan', title: '英语一',
    categoryLabel: '考研英语', kind: 'questions', questionCount: 1};
  const optionQuestion = {id: `${optionPaper.id}:q-21-1`, number: '21',
    questionType: 'single_choice', status: 'complete', stem: 'Which statement is true?',
    options: ['A', 'B', 'C', 'D'].map((letter, index) => ({
      id: `${optionPaper.id}:q-21-1:${letter}`, label: `${letter}.`,
      text: `English option ${index + 1}`})), contentBlocks: []};
  const optionRecords = optionQuestion.options.map((option, index) => ({
    id: `option-${index + 1}`, kind: 'answer_option', questionId: optionQuestion.id,
    optionId: option.id, sourceText: option.text, translationEligible: true,
    translationZh: `第 ${index + 1} 个选项译文。`
  }));
  optionRecords[3].sourceText = 'A different English option';
  const optionView = browser(optionPaper, [optionQuestion], new Map(), null,
    {paperId: optionPaper.id, paragraphs: [], options: optionRecords});
  const optionStyle = optionView.d.createElement('style');
  optionStyle.textContent = fs.readFileSync(path.join(__dirname, 'full-paper.css'), 'utf8');
  optionView.d.head.append(optionStyle);
  await waitFor(() => optionView.d.querySelector('.question-card'), 'option translation paper');
  assert.equal(optionView.calls.filter(url => url.includes('/structured/translations/')).length, 0,
    'answer option translations are not fetched before the explicit toggle');
  optionView.d.querySelector('#paragraph-translation-toggle').click();
  await waitFor(() => optionView.d.querySelectorAll('.paper-option-translation').length === 3,
    'three exact answer option translations attached');
  const optionLabels = [...optionView.d.querySelectorAll('.question-card .option')];
  assert.equal(optionLabels.length, 4, 'the original four options remain intact');
  assert.deepEqual(optionLabels.map(label => label.querySelector('.option-label').textContent),
    ['A.', 'B.', 'C.', 'D.']);
  assert.deepEqual(optionLabels.map(label => label.querySelector('.option-text').textContent),
    optionQuestion.options.map(option => option.text));
  assert.equal(optionLabels[0].nextElementSibling.textContent, '第 1 个选项译文。');
  assert.equal(optionView.d.querySelector('#paragraph-translation-toggle').dataset.attached, '3');
  assert.equal(optionView.d.querySelector('#paragraph-translation-toggle').dataset.unmatched, '1',
    'an option with the wrong English source text is reported, not misattached');
  assert.equal(optionView.calls.filter(url => url.endsWith('/answer')).length, 0,
    'showing option translations never loads correct answers');
  optionView.d.querySelector('#immersive-toggle').click();
  assert.equal(optionView.w.getComputedStyle(optionLabels[0].nextElementSibling).display, 'none',
    'non-cloze immersive option text stays in the on-demand overlay');
  optionLabels[0].dispatchEvent(new optionView.w.MouseEvent('mouseover', {bubbles: true}));
  const optionOverlay = optionView.d.querySelector('.immersive-option-translation-overlay');
  assert.equal(optionOverlay.hidden, false);
  assert.equal(optionOverlay.querySelector('.immersive-option-translation-text').textContent,
    '第 1 个选项译文。');
  assert.equal(optionLabels[0].querySelector('input').checked, false,
    'hover can reveal a translation without answering');
  optionLabels[0].click();
  assert.equal(optionLabels[0].querySelector('input').checked, true,
    'translation review does not prevent answer selection');
  optionLabels[1].click();
  assert.equal(optionOverlay.querySelector('.immersive-option-translation-text').textContent,
    '第 2 个选项译文。');
  optionOverlay.dispatchEvent(new optionView.w.KeyboardEvent('keydown',
    {key: 'Escape', bubbles: true}));
  assert.equal(optionOverlay.hidden, true, 'Escape closes the option translation');
  optionView.d.querySelector('#immersive-toggle').click();
  assert.equal(optionView.d.querySelectorAll('.paper-option-translation:not([hidden])').length, 3,
    'normal mode retains its inline option translations');
  optionView.dom.window.close();

  const clozeQuestion = {...optionQuestion, id: `${optionPaper.id}:q-1-1`, number: '1',
    stem: '', labels: [{kind: 'cloze'}], options: 'ABCD'.split('').map(letter => ({
      id: `${optionPaper.id}:q-1-1:${letter}`, label: `${letter}.`, text: `word-${letter}`}))};
  const clozeView = browser(optionPaper, [clozeQuestion], new Map(), null,
    {paperId: optionPaper.id, paragraphs: [], options: clozeQuestion.options.map(option => ({
      id: option.id, kind: 'answer_option', questionId: clozeQuestion.id,
      optionId: option.id, sourceText: option.text, translationEligible: true,
      translationZh: `中文${option.label[0]}`}))});
  const clozeStyle = clozeView.d.createElement('style');
  clozeStyle.textContent = fs.readFileSync(path.join(__dirname, 'full-paper.css'), 'utf8');
  clozeView.d.head.append(clozeStyle);
  await waitFor(() => !clozeView.d.querySelector('#paper-panel').hidden, 'cloze choices ready');
  assert.equal(clozeView.calls.filter(url => url.includes('/structured/translations/')).length, 0);
  clozeView.d.querySelector('#paragraph-translation-toggle').click();
  await waitFor(() => clozeView.d.querySelectorAll('.is-cloze-option').length === 4,
    'cloze option translations attach inside the original rows');
  const clozeChoices = [...clozeView.d.querySelectorAll('.question-card .option')];
  assert(clozeChoices.every(choice => choice.querySelector(':scope > .paper-option-translation')));
  assert(clozeChoices.every(choice => !choice.nextElementSibling?.classList
    .contains('paper-option-translation')));
  assert.deepEqual(clozeChoices.map(choice => choice.querySelector('.option-text').textContent),
    clozeQuestion.options.map(option => option.text), 'English cloze words stay unchanged');
  clozeView.d.querySelector('#immersive-toggle').click();
  assert.equal(clozeView.w.getComputedStyle(clozeChoices[0].querySelector('.is-cloze-option')).display,
    'block', 'immersive cloze translation must override the general option hide rule');
  clozeChoices[0].click();
  assert.equal(clozeChoices[0].querySelector('input').checked, true);
  assert.equal(clozeView.d.querySelector('.immersive-option-translation-overlay'), null,
    'cloze translations need no separate immersive gray overlay');
  assert.equal(clozeView.calls.filter(url => url.endsWith('/answer')).length, 0);
  clozeView.d.querySelector('#paragraph-translation-toggle').click();
  assert.equal(clozeView.w.getComputedStyle(clozeChoices[0].querySelector('.is-cloze-option')).display,
    'none', 'closing translation review must hide immersive cloze translations again');
  clozeView.dom.window.close();

  const duplicatePaper = {...optionPaper, id: 'kaoyan:2022-01', questionCount: 2};
  const duplicateText = 'Zoos which care for animals deserve fair criticism.';
  const duplicateQuestions = ['41', '42'].map(number => {
    const id = duplicatePaper.id + ':q-' + number + '-1';
    return {id, number, questionType: 'single_choice', status: 'complete',
      stem: number + '. Choose the best answer.', context: null, contentBlocks: [],
      options: [{id: id + ':A', label: 'A.', text: duplicateText}]};
  });
  const ownerOptionId = duplicateQuestions[0].options[0].id;
  const aliasOptionId = duplicateQuestions[1].options[0].id;
  const duplicateView = browser(duplicatePaper, duplicateQuestions, new Map(), null,
    {paperId: duplicatePaper.id, paragraphs: [], options: [
      {id: ownerOptionId, kind: 'answer_option', questionId: duplicateQuestions[0].id,
        optionId: ownerOptionId, sourceText: duplicateText, sourceHash: 'matching-source-hash',
        sourceBlockIds: [duplicatePaper.id + ':b-12-6'],
        translationEligible: true, translationZh: '重复选项译文。'},
      {id: aliasOptionId, kind: 'answer_option', questionId: duplicateQuestions[1].id,
        optionId: aliasOptionId, sourceText: duplicateText, sourceHash: 'matching-source-hash',
        sourceBlockIds: [duplicatePaper.id + ':b-12-6'],
        translationEligible: false, coverageStatus: 'covered_by_option',
        translationRef: ownerOptionId, translationZh: null}
    ]});
  await waitFor(() => !duplicateView.d.querySelector('#paper-panel').hidden,
    'duplicate answer choices ready');
  duplicateView.d.querySelector('#paragraph-translation-toggle').click();
  await waitFor(() => duplicateView.d.querySelectorAll('.paper-option-translation').length === 2,
    'repeated source-backed choices share one translated value');
  assert.equal(duplicateView.d.querySelector('#paragraph-translation-toggle').dataset.unmatched, '0');
  assert.deepEqual([...duplicateView.d.querySelectorAll('.paper-option-translation')]
    .map(node => node.textContent), ['重复选项译文。', '重复选项译文。']);
  duplicateView.dom.window.close();

  const sharedOptionSource = JSON.parse(fs.readFileSync(path.join(__dirname,
    '../structured/papers/kaoyan/2026-01.json'), 'utf8'));
  const sharedOptionQuestion = sharedOptionSource.questions.find(item => String(item.number) === '41');
  const sharedOptionParagraph = JSON.parse(fs.readFileSync(path.join(__dirname,
    '../structured/translations/kaoyan/2026-01.json'), 'utf8')).paragraphs.find(item =>
    item.kind === 'passage_option' && item.sourceText.startsWith('A)'));
  const sharedOptionId = sharedOptionParagraph.sourceBlockIds[0];
  const sharedRoot = {type: 'paper', children: [{type: 'section', title: 'Part B',
    units: [{type: 'paragraph', text: sharedOptionParagraph.sourceText,
      provenance: {sourceBlockId: sharedOptionId}}],
    children: [{type: 'question', questionId: `${optionPaper.id}:${sharedOptionQuestion.id}`}]}]};
  const sharedQuestion = {...sharedOptionQuestion,
    id: `${optionPaper.id}:${sharedOptionQuestion.id}`,
    options: sharedOptionQuestion.options.map(option => ({...option,
      id: `${optionPaper.id}:${sharedOptionQuestion.id}:${option.label.replace(/\W/g, '')}`})),
    contentBlocks: []};
  const sharedView = browser(optionPaper, [sharedQuestion], new Map(), sharedRoot,
    {paperId: optionPaper.id, paragraphs: [{...sharedOptionParagraph,
      translationEligible: true, translationZh: 'A 篇材料译文。'}],
    options: [{id: 'shared-A', kind: 'answer_option', questionId: sharedQuestion.id,
      optionId: sharedQuestion.options[0].id, sourceBlockIds: [sharedOptionId],
      sourceText: sharedQuestion.options[0].text, translationEligible: false,
      coverageStatus: 'covered_by_paragraph', translationRef: sharedOptionParagraph.id,
      translationZh: null}]});
  await requestTranslations(sharedView, 1, 'passage option and answer option reuse one translation');
  assert.equal(sharedView.d.querySelectorAll('.paper-option-translation').length, 0,
    'a full passage option already translated in the source pane is not duplicated by its choice');
  assert.equal(sharedView.d.querySelector('#paragraph-translation-toggle').dataset.attached, '2');
  assert.equal(sharedView.d.querySelector('#paragraph-translation-toggle').dataset.unmatched, '0');
  sharedView.d.querySelector('#immersive-toggle').click();
  sharedView.d.querySelector('.immersive-reading .paper-translatable-source').click();
  assert.equal(sharedView.d.querySelector('#immersive-translation-text').textContent,
    'A 篇材料译文。', 'a matching option reuses its source passage translation on the left');
  sharedView.dom.window.close();

  const matchingSecondId = optionPaper.id + ':q-42-1';
  const matchingFirst = {...sharedQuestion, labels: [{kind: 'matching'}]};
  const matchingSecond = {...matchingFirst, id: matchingSecondId, number: '42',
    options: matchingFirst.options.map(option => ({...option,
      id: `${matchingSecondId}:${option.label.replace(/\W/g, '')}`}))};
  const matchingUnits = [{type: 'paragraph', text: sharedOptionParagraph.sourceText,
    provenance: {sourceBlockId: sharedOptionId}},
  ...matchingFirst.options.slice(1).map((option, index) => ({type: 'paragraph',
    text: option.text, provenance: {sourceBlockId: `${optionPaper.id}:b-test-${index}`}}))];
  const matchingRoot = {type: 'paper', children: [{type: 'section', title: 'Part B',
    units: matchingUnits, children: [matchingFirst, matchingSecond].map(question =>
      ({type: 'question', questionId: question.id}))}]};
  const matchingView = browser(optionPaper, [matchingFirst, matchingSecond], new Map(),
    matchingRoot, {paperId: optionPaper.id,
      paragraphs: [{...sharedOptionParagraph, translationEligible: true,
        translationZh: 'A 篇材料译文。'}],
      options: [{id: 'matching-A', kind: 'answer_option', questionId: matchingFirst.id,
        optionId: matchingFirst.options[0].id, sourceBlockIds: [sharedOptionId],
        sourceText: matchingFirst.options[0].text, translationEligible: false,
        coverageStatus: 'covered_by_paragraph', translationRef: sharedOptionParagraph.id}]});
  await requestTranslations(matchingView, 1, 'matching source choice translation');
  matchingView.d.querySelector('#immersive-toggle').click();
  assert(matchingView.d.querySelector('.immersive-questions.is-matching'));
  const matchingChoice = matchingView.d.querySelector('.immersive-questions .question-card .option');
  matchingChoice.dispatchEvent(new matchingView.w.MouseEvent('mouseover', {bubbles: true}));
  assert.equal(matchingView.d.querySelector('.immersive-option-translation-overlay'), null,
    'long passage translation cannot cover matching answer controls on hover');
  matchingChoice.click();
  assert.equal(matchingChoice.querySelector('input').checked, true,
    'matching choice remains selectable while translation review is enabled');
  matchingView.d.querySelector('.immersive-reading .paper-translatable-source').click();
  assert.equal(matchingView.d.querySelector('#immersive-translation-overlay').hidden, false,
    'matching passage translation stays available on demand in the left pane');
  matchingView.dom.window.close();

  const figureView = browser(optionPaper, [matchingFirst], new Map(),
    {type: 'paper', children: [{type: 'section', title: 'Part B',
      units: matchingUnits, children: [{type: 'question', questionId: matchingFirst.id}]}]},
    {paperId: optionPaper.id, paragraphs: [], options: [{id: 'figure-A',
      kind: 'answer_option', questionId: matchingFirst.id,
      optionId: matchingFirst.options[0].id, sourceText: matchingFirst.options[0].text,
      translationEligible: true, translationZh: '图表选项 A 的译文。'}]});
  await waitFor(() => !figureView.d.querySelector('#paper-panel').hidden,
    'single-card matching figure ready');
  figureView.d.querySelector('#paragraph-translation-toggle').click();
  await waitFor(() => figureView.d.querySelector('.paper-option-translation'),
    'figure choice translation attached');
  figureView.d.querySelector('#immersive-toggle').click();
  assert.equal(figureView.d.querySelector('.immersive-questions.is-matching'), null,
    'figure-style matching presents one card at a time');
  const figureChoice = figureView.d.querySelector('.immersive-questions .option');
  figureChoice.dispatchEvent(new figureView.w.MouseEvent('mouseover', {bubbles: true}));
  const figureOverlay = figureView.d.querySelector('.immersive-option-translation-overlay');
  assert.equal(figureOverlay.parentElement.id, 'immersive-reading-page',
    'figure-bank translation must not cover the right answer controls');
  figureChoice.click();
  assert.equal(figureChoice.querySelector('input').checked, true);
  figureOverlay.click();
  assert.equal(figureOverlay.hidden, true, 'click closes the left option translation');
  figureChoice.dispatchEvent(new figureView.w.MouseEvent('mouseover', {bubbles: true}));
  figureOverlay.dispatchEvent(new figureView.w.KeyboardEvent('keydown',
    {key: 'Enter', bubbles: true}));
  assert.equal(figureOverlay.hidden, true, 'keyboard activation closes the left option translation');
  figureView.dom.window.close();

  const bankPaper = {id: 'cet4:2020-12-01', category: 'cet4', title: '英语四级',
    categoryLabel: '英语四级', kind: 'questions', questionCount: 1};
  const bankQuestionId = bankPaper.id + ':q-26-1';
  const bankSourceId = bankPaper.id + ':b-4-5';
  const bankQuestion = {id: bankQuestionId, number: '26', questionType: 'fill_blank',
    status: 'partial', stem: '26.', options: [], contentBlocks: [],
    context: {kind: 'word_bank_cloze', wordBank: [
      {id: bankPaper.id + ':word-bank:A', label: 'A.', text: 'constantly',
        sourceBlockId: 'b-4-5', sourceText: 'A. constantly'},
      {id: bankPaper.id + ':word-bank:B', label: 'B.', text: 'credible',
        sourceBlockId: 'b-4-5', sourceText: 'B. credible'},
      {id: bankPaper.id + ':word-bank:J', label: 'J.', text: 'records',
        sourceBlockId: 'b-4-5', sourceText: 'J. records 0) watching'}]}};
  const nextBankQuestion = {...bankQuestion, id: bankPaper.id + ':q-27-1', number: '27',
    stem: '27.'};
  const bankRoot = {type: 'paper', children: [{type: 'section', title: 'Section A',
    units: [{type: 'other', text: 'A. constantly B. credible J. records 0) watching',
      contentHtml: '<ul class="options"><li><span>A.</span><span>constantly</span></li>' +
        '<li><span>B.</span><span>credible</span></li>' +
        '<li><span>J.</span><span>records 0) watching</span></li></ul>',
      provenance: {sourceBlockId: bankSourceId}}],
    children: [{type: 'question', questionId: bankQuestionId, children: []},
      {type: 'question', questionId: nextBankQuestion.id, children: []}]}]};
  const bankView = browser(bankPaper, [bankQuestion, nextBankQuestion],
    new Map([[bankQuestionId, {status: 'unknown'}]]), bankRoot,
    {paperId: bankPaper.id, paragraphs: [], options: [
      {id: 'bank-A', kind: 'word_bank_option', questionId: bankQuestionId,
        optionId: bankPaper.id + ':word-bank:A', sourceBlockIds: [bankSourceId],
        sourceText: 'constantly', translationEligible: true, translationZh: '经常'},
      {id: 'bank-B', kind: 'word_bank_option', questionId: bankQuestionId,
        optionId: bankPaper.id + ':word-bank:B', sourceBlockIds: [bankSourceId],
        sourceText: 'credible', translationEligible: true, translationZh: '可信的'},
      {id: 'bank-J', kind: 'word_bank_option', questionId: bankQuestionId,
        optionId: bankPaper.id + ':word-bank:J', sourceBlockIds: [bankSourceId],
        sourceText: 'watching', translationEligible: true, translationZh: '看'},
    ]});
  await waitFor(() => !bankView.d.querySelector('#paper-panel').hidden, 'word bank source ready');
  assert.equal(bankView.calls.filter(url => url.includes('/structured/translations/')).length, 0);
  bankView.d.querySelector('#paragraph-translation-toggle').click();
  await waitFor(() => bankView.d.querySelectorAll('.paper-word-bank-entry').length === 2,
    'exact word-bank options translated');
  assert.equal(bankView.d.querySelector('#paragraph-translation-toggle').dataset.attached, '2');
  assert.equal(bankView.d.querySelector('#paragraph-translation-toggle').dataset.unmatched, '1',
    'mismatched word-bank English is rejected');
  assert.equal(bankView.d.querySelector('[data-source-block-id="' + bankSourceId + '"]')
    .textContent, 'A.constantlyB.credibleJ.records 0) watching',
    'source bank English and letters remain unchanged');
  assert.equal(bankView.d.querySelectorAll('.paper-word-bank-source-item').length, 3,
    'word bank source preserves each original English item as a separate grid cell');
  const bankCards = [...bankView.d.querySelectorAll('.question-card')];
  assert.equal(bankCards[0].querySelectorAll('.paper-word-bank-option').length, 3);
  assert.equal(bankCards[1].querySelectorAll('.paper-word-bank-option').length, 3);
  bankCards[0].querySelector('.paper-word-bank-option').click();
  assert.equal(bankCards[0].querySelector('textarea').value, 'A');
  bankCards[1].querySelectorAll('.paper-word-bank-option')[1].click();
  assert.equal(bankCards[1].querySelector('textarea').value, 'B');
  assert.equal(bankCards[0].querySelector('textarea').value, 'A',
    'choosing for the next blank does not overwrite a previous draft');
  bankCards[0].querySelector('[data-action="reveal"]').click();
  await waitFor(() => !bankCards[0].querySelector('.answer-panel').hidden,
    'bank answer state ready');
  assert.equal(bankCards[0].querySelector('.paper-word-bank-option').disabled, true);
  bankCards[0].querySelector('[data-action="redo"]').click();
  assert.equal(bankCards[0].querySelector('textarea').value, '');
  assert.equal(bankCards[0].querySelector('.paper-word-bank-option').disabled, false);
  assert.equal(bankCards[1].querySelector('textarea').value, 'B',
    'resetting one blank keeps the next answer intact');
  bankView.d.querySelector('#immersive-toggle').click();
  const bankTabs = bankView.d.querySelectorAll('#immersive-question-tabs button');
  if (bankTabs.length > 1) {
    bankTabs[1].click();
    assert.equal(bankCards[1].querySelector('textarea').value, 'B',
      'switching immersive questions preserves the draft');
    bankTabs[0].click();
  }
  assert.equal(bankView.d.querySelectorAll('#immersive-reading-page .paper-word-bank-translations')
    .length, 1);
  bankView.d.querySelector('#immersive-reading-page .paper-translatable-source').click();
  assert(bankView.d.querySelector('#immersive-translation-text').classList.contains('is-word-bank'));
  assert.equal(bankView.d.querySelectorAll('#immersive-translation-text .paper-word-bank-entry')
    .length, 2);
  assert(bankView.d.querySelector('#immersive-translation-text').textContent.includes('A. 经常'));
  assert(bankView.d.querySelector('#immersive-translation-text').textContent.includes('B. 可信的'));
  bankView.w.dispatchEvent(new bankView.w.Event('resize'));
  assert.equal(bankView.d.querySelector('#immersive-translation-overlay').hidden, true,
    'resizing dismisses a positioned translation instead of clipping it');
  assert.equal(bankView.calls.filter(url => url.endsWith('/answer')).length, 1,
    'only the explicit reveal fetched an answer; translation and bank selection did not');
  bankView.dom.window.close();

  for (const [number, expected] of [['Writing', '写作'], ['Translation', '翻译'],
    ['Writing 2', '写作 2'], ['Translation 2', '翻译 2']]) {
    const task = {id: `cet4:2022-06-03:q-${number.toLowerCase()}-1`, number,
      questionType: 'free_response', status: 'partial', stem: 'Directions: Write your answer.',
      context: null, options: [], contentBlocks: []};
    const view = browser({id: 'cet4:2022-06-03', category: 'cet4', title: '测试卷',
      categoryLabel: '英语四级', kind: 'questions', questionCount: 1}, [task], new Map());
    await waitFor(() => view.d.querySelector('.question-card'), `${number} section card`);
    assert.equal(view.d.querySelector('.question-number').textContent, expected);
    view.d.querySelector('#immersive-toggle').click();
    assert(view.d.querySelector('#immersive-directory').textContent.includes(expected));
    view.dom.window.close();
  }

  const cetTaskPaper = {id: 'cet4:2022-06-03', category: 'cet4', title: '英语四级',
    categoryLabel: '英语四级', kind: 'questions', questionCount: 2};
  const writingDirections = 'Directions: Write a proposal to your school clinic.';
  const translationDirections = 'Directions: Translate the following passage into English.';
  const chinesePassage = '从前，有个农夫正在地里耕作。';
  const cetTasks = [
    {id: `${cetTaskPaper.id}:q-writing-1`, number: 'Writing', questionType: 'free_response',
      status: 'complete', stem: writingDirections, context: {kind: 'writing_task',
        text: writingDirections}, sourceBlocks: ['b-1-4'], options: [],
      contentBlocks: [{id: `${cetTaskPaper.id}:b-1-4`, role: 'content',
        text: writingDirections, images: []}]},
    {id: `${cetTaskPaper.id}:q-translation-1`, number: 'Translation',
      questionType: 'free_response', status: 'complete', stem: chinesePassage,
      context: {kind: 'translation_passage', text: `${translationDirections}\n\n${chinesePassage}`},
      sourceBlocks: ['b-1-6', 'b-1-7'], options: [], contentBlocks: [
        {id: `${cetTaskPaper.id}:b-1-6`, role: 'content', text: translationDirections, images: []},
        {id: `${cetTaskPaper.id}:b-1-7`, role: 'content', text: chinesePassage, images: []}
      ]}
  ];
  const cetTaskView = browser(cetTaskPaper, cetTasks, new Map(), null,
    {paperId: cetTaskPaper.id, paragraphs: [
      {id: 'writing-directions', kind: 'instruction',
        sourceBlockIds: [`${cetTaskPaper.id}:b-1-4`], paragraphIndex: 0,
        sourceText: writingDirections, translationEligible: true, translationZh: '写作说明译文。'},
      {id: 'translation-directions', kind: 'instruction',
        sourceBlockIds: [`${cetTaskPaper.id}:b-1-6`], paragraphIndex: 0,
        sourceText: translationDirections, translationEligible: true,
        translationZh: '翻译说明译文。'}
    ]});
  await requestTranslations(cetTaskView, 2, 'CET source-backed free-response tasks');
  assert.equal(cetTaskView.d.querySelectorAll('.question-card').length, 2);
  assert.equal(cetTaskView.d.querySelectorAll('.question-stem, .question-context').length, 0,
    'composed stem and context do not duplicate printed source content');
  assert.equal(cetTaskView.d.querySelectorAll('.content-block').length, 3);
  assert.equal(cetTaskView.d.querySelectorAll('.content-block.paper-directions').length, 2);
  assert.equal(cetTaskView.d.querySelector('#paragraph-translation-toggle').dataset.unmatched, '0');
  cetTaskView.d.querySelector('#immersive-toggle').click();
  assert(cetTaskView.d.querySelector('#immersive-reading-page').textContent.includes(
    writingDirections), 'writing source is available in the immersive left pane');
  cetTaskView.d.querySelectorAll('#immersive-directory .immersive-directory-item')[1].click();
  assert(cetTaskView.d.querySelector('#immersive-reading-page').textContent.includes(
    chinesePassage), 'translation passage is available in the immersive left pane');
  assert(cetTaskView.d.querySelector('#immersive-workspace').classList.contains('is-translation'),
    'source-backed CET translation uses the wider reading layout without printed labels');
  cetTaskView.dom.window.close();

  const fusedWriting = 'Directions: Write a short essay about education.';
  const fusedTask = {id: 'cet4:2019-06-01:q-writing-1', number: 'Writing',
    questionType: 'free_response', status: 'complete', stem: fusedWriting,
    context: {kind: 'writing_task', instructionText: fusedWriting,
      instructionSourceBlocks: ['b-1-3']}, sourceBlocks: ['b-1-3'], options: [],
    contentBlocks: [{id: 'cet4:2019-06-01:b-1-3', role: 'content',
      text: `${fusedWriting} Part II Listening Comprehension`, images: []}]};
  const fusedView = browser({...cetTaskPaper, id: 'cet4:2019-06-01', questionCount: 1},
    [fusedTask], new Map());
  await waitFor(() => fusedView.d.querySelector('.question-card'),
    'fused Writing and Part II source loaded');
  assert.equal(fusedView.d.querySelector('.question-card .content-block').textContent,
    fusedWriting, 'a fused OCR block does not pull Part II into the Writing card');
  fusedView.dom.window.close();

  const imageTaskPaper = {...cetTaskPaper, id: 'cet4:2020-09-01', questionCount: 1};
  const imageTask = {id: `${imageTaskPaper.id}:q-translation-1`, number: 'Translation',
    questionType: 'free_response', status: 'partial', stem: translationDirections,
    context: {kind: 'translation_passage', text: translationDirections,
      figureSourceBlocks: ['b-8-17']}, sourceBlocks: ['b-8-16', 'b-8-17'], options: [],
    contentBlocks: [
      {id: `${imageTaskPaper.id}:b-8-16`, role: 'content', text: translationDirections,
        images: []},
      {id: `${imageTaskPaper.id}:b-8-17`, role: 'figure', text: '',
        images: [{src: '/exam-library/assets/translation-source.png', alt: '翻译原文图'}]}
    ]};
  const imageTaskView = browser(imageTaskPaper, [imageTask], new Map());
  await waitFor(() => imageTaskView.d.querySelector('.question-card'),
    'image-only CET translation task loaded');
  assert.equal(imageTaskView.d.querySelectorAll('.question-card img').length, 1);
  imageTaskView.d.querySelector('#immersive-toggle').click();
  assert.equal(imageTaskView.d.querySelectorAll('#immersive-reading-page img').length, 1,
    'image-only translation source remains visible in immersive reading pane');
  imageTaskView.dom.window.close();

  const continuedDirections = 'should write your answer on Answer Sheet 2 .';
  const headingTaskPaper = {...cetTaskPaper, id: 'cet4:2020-12-01', questionCount: 1};
  const headingTaskId = `${headingTaskPaper.id}:q-translation-1`;
  const headingTask = {id: headingTaskId, number: 'Translation',
    questionType: 'free_response', status: 'partial', stem: translationDirections,
    context: {kind: 'translation_passage',
      text: `${translationDirections}\n\n${continuedDirections}`,
      sourceBlocks: ['b-8-16', 'b-8-17', 'b-8-18'],
      figureSourceBlocks: ['b-8-18']},
    sourceBlocks: ['b-8-16', 'b-8-17', 'b-8-18'], options: [],
    contentBlocks: [{id: `${headingTaskPaper.id}:b-8-18`, role: 'content',
      text: '', images: [{src: '/exam-library/assets/translation-source.png', alt: '原文图'}]}]};
  const headingUnits = [translationDirections, continuedDirections].map((text, index) => ({
    type: 'other', text, provenance: {sourceBlockId: `${headingTaskPaper.id}:b-8-${16 + index}`}}));
  const headingRoot = {type: 'paper', children: [{type: 'question',
    questionId: headingTaskId, units: headingUnits, children: []}]};
  const headingView = browser(headingTaskPaper, [headingTask], new Map(), headingRoot,
    {paperId: headingTaskPaper.id, paragraphs: [{id: 'continued-directions',
      kind: 'heading_prose', sourceBlockIds: [`${headingTaskPaper.id}:b-8-17`],
      paragraphIndex: 0, sourceText: continuedDirections,
      translationEligible: true, translationZh: '应将答案写在答题卡 2 上。'}]});
  await requestTranslations(headingView, 1, 'source-backed continuation of CET directions');
  assert.equal(headingView.d.querySelector('#paragraph-translation-toggle').dataset.unmatched, '0');
  assert(headingView.d.querySelector('#paper-panel').textContent.includes(continuedDirections));
  assert.deepEqual([...headingView.d.querySelectorAll('.question-card .question-content > .paper-directions > .paper-unit')]
    .map(node => node.dataset.sourceBlockId),
  [headingTaskPaper.id + ':b-8-16', headingTaskPaper.id + ':b-8-17'],
  'omitted source-backed Directions lines remain before the translation passage image');
  headingView.dom.window.close();

  const variantPaper = {id: 'math3:1987-questions', category: 'math3',
    title: '1987 年考研数学三 · 真题', kind: 'questions', questionCount: 3};
  const variantQuestion = {id: variantPaper.id + ':q-1-1', number: '1',
    stem: '（1）判断题', questionType: 'free_response', options: [], contentBlocks: [],
    sourceBlocks: ['b-1-6']};
  const variantLastQuestion = {...variantQuestion, id: variantPaper.id + ':q-4-1',
    number: '4', sourceBlocks: ['b-9-1'], contentBlocks: [
      {id: variantPaper.id + ':b-18-1', role: 'content', text: '（试卷V）', images: []}
    ]};
  const variantNextQuestion = {...variantQuestion, id: variantPaper.id + ':q-1-2',
    sourceBlocks: ['b-18-3']};
  const editorNote = '【编者注】数学试卷IV、V均为现在的数学三。';
  const variantRoot = {type: 'paper', children: [
    {type: 'section', title: '一、判断题', units: [], children: [
      {type: 'question', questionId: variantQuestion.id, units: [], children: []}
    ]},
    {type: 'section', title: 'Unassigned source material', units: [
      {type: 'paragraph', text: editorNote,
        provenance: {sourceBlockId: variantPaper.id + ':b-1-2'}},
      {type: 'code', text: editorNote,
        provenance: {sourceBlockId: variantPaper.id + ':b-1-3'}},
      {type: 'other', text: '（试卷IV）', contentHtml: '<h2>（试卷IV）</h2>',
        provenance: {sourceBlockId: variantPaper.id + ':b-1-4'}}
    ], children: [{type: 'question', questionId: variantLastQuestion.id, units: [
      {type: 'other', text: '（试卷V）', contentHtml: '<h2>（试卷V）</h2>',
        provenance: {sourceBlockId: variantPaper.id + ':b-18-1'}}
    ], children: []}]},
    {type: 'section', title: '一、判断题', units: [], children: [
      {type: 'question', questionId: variantNextQuestion.id, units: [], children: []}
    ]}
  ]};
  const variantView = browser(variantPaper,
    [variantQuestion, variantLastQuestion, variantNextQuestion], new Map(), variantRoot);
  await waitFor(() => variantView.d.querySelector('.question-card'), 'old mathematics paper loaded');
  const variantHeading = [...variantView.d.querySelectorAll('#question-list h3')]
    .find(node => node.textContent === '（试卷IV）');
  assert(variantHeading, 'source variant heading remains visible before the first problem');
  assert(variantHeading.compareDocumentPosition(variantView.d.querySelector('.question-card')) & 4);
  assert(!variantView.d.querySelector('#question-list').textContent.includes('Unassigned source material'),
    'a parser fallback is not displayed as an original paper heading');
  assert.equal(variantView.d.querySelector('#question-list').textContent.split(editorNote).length - 1, 1,
    'paragraph and compiler-source copies of one cover note do not duplicate it');
  const variantCards = [...variantView.d.querySelectorAll('.question-card')];
  assert.deepEqual(variantCards.map(card => card.dataset.questionId),
    [variantQuestion.id, variantLastQuestion.id, variantNextQuestion.id]);
  const nextVariantHeading = [...variantView.d.querySelectorAll('#question-list h3')]
    .find(node => node.textContent === '（试卷V）');
  assert(nextVariantHeading.compareDocumentPosition(variantCards[1]) & 2);
  assert(nextVariantHeading.compareDocumentPosition(variantCards[2]) & 4);
  assert.equal(variantView.d.querySelector('#question-list').textContent.split('（试卷V）').length - 1, 1);
  variantView.dom.window.close();

  const answersOnly = browser({...paper, id: 'cs408:2017-answers', kind: 'answers'}, questions, answers);
  await waitFor(() => answersOnly.d.getElementById('page-status').classList.contains('is-error'),
    'answer-only paper rejected');
  assert.equal(answersOnly.d.querySelectorAll('.question-card').length, 0);
  answersOnly.dom.window.close();
}

main().catch(error => {console.error(error); process.exitCode = 1;});
