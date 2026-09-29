const assert = require('node:assert/strict');
const {createHash, webcrypto} = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const {TextEncoder} = require('node:util');
const {JSDOM} = require('jsdom');

const script = fs.readFileSync(path.join(__dirname, 'translations.js'), 'utf8');
const hash = value => createHash('sha256').update(value).digest('hex');
const block = (type, text) => ({type, runs: [{text}]});
const record = (sourceText, ids, translationZh = '译文') => ({
  sourceBlockIds: ids.map(() => 'cet4:test:b-9-9'),
  reflowBlockIds: ids.map(id => `cet4:test:${id}`), paragraphIndex: 0,
  sourceText, sourceHash: hash(sourceText), translationEligible: true,
  unresolvedBlanks: [], translationZh
});

async function reader(markup, records, pages, options = [], paperId = 'cet4:test') {
  const dom = new JSDOM(`<!doctype html><body><div class="reader-controls"></div><main class="paper" data-paper-id="${paperId}" data-translation-sidecar="sidecar.json" data-source-json="test.json">${markup}</main></body>`,
    {url: 'http://localhost/paper.htm', runScripts: 'outside-only'});
  const {window} = dom;
  window.TextEncoder = TextEncoder;
  Object.defineProperty(window.crypto, 'subtle', {value: webcrypto.subtle});
  window.fetchCalls = [];
  window.fetch = async url => { window.fetchCalls.push(String(url)); return {ok: true, json: async () =>
    String(url).endsWith('sidecar.json') ? {paperId, sourcePdfSha256: hash('reviewed pdf'), paragraphs: records, options} : {pages}};
  };
  window.eval(script);
  window.dispatchEvent(new window.Event('load'));
  return dom;
}

async function reveal(dom) {
  dom.window.document.querySelector('.paragraph-translation-toggle').click();
  for (let attempt = 0; attempt < 100 && !dom.window.document.querySelector('main').dataset.translationAttached; attempt++) {
    await new Promise(resolve => setTimeout(resolve, 2));
  }
}

test('paragraph, instruction and passage choice translations stay hidden until toggled', async () => {
  const html = [
    '<p class="instruction">Read this<span class="source-block-marker" data-source-block-id="b-1-1"></span></p>',
    '<p class="paragraph">A) Long choice text<span class="source-block-marker" data-source-block-id="b-1-2"></span></p>'
  ].join('');
  const dom = await reader(html,
    [record('Read this', ['b-1-1'], '请阅读'), record('A) Long choice text', ['b-1-2'], 'A 段译文')],
    [{blocks: [block('instruction', 'Read this'), block('paragraph', 'A) Long choice text')]}]);
  const doc = dom.window.document;
  assert.equal(dom.window.fetchCalls.length, 0, 'sidecar is not fetched on page load');
  assert.equal(doc.querySelectorAll('.paragraph-translation').length, 0);
  await reveal(dom);
  const translations = [...doc.querySelectorAll('.paragraph-translation')];
  const toggle = doc.querySelector('.paragraph-translation-toggle');
  assert.equal(dom.window.fetchCalls.filter(url => url.endsWith('sidecar.json')).length, 1,
    'sidecar is fetched once on the first reveal');
  assert.equal(translations.length, 2);
  assert(translations.every(node => !node.hidden));
  assert.equal(doc.querySelector('p.instruction').textContent, 'Read this');
  assert.equal(toggle.getAttribute('aria-pressed'), 'true');
  toggle.click();
  assert(translations.every(node => node.hidden));
  toggle.click();
  assert(translations.every(node => !node.hidden));
  assert.equal(dom.window.fetchCalls.filter(url => url.endsWith('sidecar.json')).length, 1,
    'repeated toggles reuse the loaded sidecar');
  dom.window.close();
});

test('cross-page source blocks attach only to their combined paragraph', async () => {
  const html = '<p class="paragraph">First<span class="source-block-marker" data-source-block-id="b-1-1"></span> second<span class="source-block-marker" data-source-block-id="b-2-1"></span></p>';
  const dom = await reader(html, [record('First second', ['b-1-1', 'b-2-1'])],
    [{blocks: [block('paragraph', 'First')]}, {blocks: [block('paragraph', 'second')]}]);
  await reveal(dom);
  assert.equal(dom.window.document.querySelectorAll('.paragraph-translation').length, 1);
  dom.window.close();
});

test('Chinese text split across raw blocks follows the exact verified separator', async () => {
  const html = '<p class="question">84. She has (几乎没有' +
    '<span class="source-block-marker" data-source-block-id="b-1-1"></span></p>' +
    '<p class="paragraph">什么共同之处).<span class="source-block-marker" data-source-block-id="b-1-2"></span></p>';
  const pages = [{blocks: [block('question', '84. She has (几乎没有'),
    block('paragraph', '什么共同之处).')]}];
  for (const sourceText of ['84. She has (几乎没有什么共同之处).',
    '84. She has (几乎没有 什么共同之处).']) {
    const dom = await reader(html,
      [record(sourceText, ['b-1-1', 'b-1-2'], '她几乎没有共同之处。')], pages);
    await reveal(dom);
    assert.equal(dom.window.document.querySelector('main').dataset.translationParagraphsAttached, '1');
    dom.window.close();
  }
});

test('a verified CET running header can separate cross-page paragraph fragments', async () => {
  const html = '<section data-source-page="1"><p class="paragraph">First' +
    '<span class="source-block-marker" data-source-block-id="b-1-1"></span></p></section>' +
    '<section data-source-page="2"><p class="paragraph">全国英语六级历年真题' +
    '<span class="source-block-marker" data-source-block-id="b-2-1"></span></p>' +
    '<p class="paragraph">second<span class="source-block-marker" data-source-block-id="b-2-2"></span></p></section>';
  const pages = [
    {blocks: [block('paragraph', 'First')]},
    {blocks: [block('paragraph', '全国英语六级历年真题'), block('paragraph', 'second')]}
  ];
  const dom = await reader(html, [record('First second', ['b-1-1', 'b-2-2'])], pages);
  await reveal(dom);
  assert.equal(dom.window.document.querySelectorAll('.paragraph-translation').length, 1);
  dom.window.close();
});

test('other intervening text cannot bridge cross-page paragraph fragments', async () => {
  const html = '<section data-source-page="1"><p class="paragraph">First' +
    '<span class="source-block-marker" data-source-block-id="b-1-1"></span></p></section>' +
    '<section data-source-page="2"><p class="paragraph">An English heading' +
    '<span class="source-block-marker" data-source-block-id="b-2-1"></span></p>' +
    '<p class="paragraph">second<span class="source-block-marker" data-source-block-id="b-2-2"></span></p></section>';
  const pages = [
    {blocks: [block('paragraph', 'First')]},
    {blocks: [block('paragraph', 'An English heading'), block('paragraph', 'second')]}
  ];
  const dom = await reader(html, [record('First second', ['b-1-1', 'b-2-2'])], pages);
  await reveal(dom);
  assert.equal(dom.window.document.querySelectorAll('.paragraph-translation').length, 0);
  assert.equal(dom.window.document.querySelector('main').dataset.translationSkipped, '1');
  dom.window.close();
});

test('changed source and ambiguous merged blocks are skipped', async () => {
  const html = '<p class="paragraph">Combined<span class="source-block-marker" data-source-block-id="b-1-1"></span><span class="source-block-marker" data-source-block-id="b-1-2"></span></p>';
  const dom = await reader(html,
    [record('Old wording', ['b-1-1']), record('Second', ['b-1-2'])],
    [{blocks: [block('paragraph', 'New wording'), block('paragraph', 'Second')]}]);
  const doc = dom.window.document;
  await reveal(dom);
  assert.equal(doc.querySelector('main').dataset.translationAttached, '0');
  assert.equal(doc.querySelector('main').dataset.translationSkipped, '2');
  assert.equal(doc.querySelector('.paragraph-translation-toggle').disabled, true);
  dom.window.close();
});

test('single option starter and following prose share one translation after the prose', async () => {
  const html = '<section data-source-page="1"><ul class="options single"><li><span class="option-label">A.</span><span>First part</span></li></ul><p class="paragraph">second part<span class="source-block-marker" data-source-block-id="b-1-2"></span></p></section>';
  const option = {type: 'options', items: [{label: 'A', runs: [{text: 'First part'}]}]};
  const item = {...record('A. First part second part', ['b-1-1', 'b-1-2']), kind: 'passage_option'};
  const dom = await reader(html, [item], [{blocks: [option, block('paragraph', 'second part')]}]);
  await reveal(dom);
  const doc = dom.window.document;
  assert.equal(doc.querySelector('main').dataset.translationAttached, '1');
  assert.equal(doc.querySelector('p.paragraph').nextElementSibling.className, 'paragraph-translation');
  dom.window.close();
});

test('separate marked prose blocks attach after their final block', async () => {
  const html = '<section data-source-page="1"><p class="paragraph">First<span class="source-block-marker" data-source-block-id="b-1-1"></span></p><p class="paragraph">second<span class="source-block-marker" data-source-block-id="b-1-2"></span></p></section>';
  const dom = await reader(html, [record('First second', ['b-1-1', 'b-1-2'])],
    [{blocks: [block('paragraph', 'First'), block('paragraph', 'second')]}]);
  await reveal(dom);
  const doc = dom.window.document;
  assert.equal(doc.querySelector('main').dataset.translationAttached, '1');
  assert.equal(doc.querySelectorAll('p.paragraph')[1].nextElementSibling.className, 'paragraph-translation');
  dom.window.close();
});

test('one-item instruction option attaches from exact raw source text', async () => {
  const html = '<section data-source-page="1"><ul class="options single"><li><span class="option-label">D.</span><span>. You should decide.</span></li></ul></section>';
  const option = {type: 'options', items: [{label: 'D', runs: [{text: '. You should decide.'}]}]};
  const item = {...record('D. . You should decide.', ['b-1-1']), kind: 'instruction'};
  const dom = await reader(html, [item], [{blocks: [option]}]);
  await reveal(dom);
  const doc = dom.window.document;
  assert.equal(doc.querySelector('main').dataset.translationAttached, '1');
  assert.equal(doc.querySelector('ul.options').nextElementSibling.className, 'paragraph-translation');
  dom.window.close();
});

const optionRecord = (blockId, optionIndex, label, sourceText, translationZh) => ({
  kind: 'answer_option', questionId: 'cet4:test:q-1-1',
  optionId: `cet4:test:q-1-1:${label}`,
  reflowBlockId: `cet4:test:${blockId}`, reflowOptionIndex: optionIndex,
  sourceText, sourceHash: hash(sourceText), reflowSourceText: sourceText,
  translationEligible: true, translationZh
});

test('answer options in options and choice_row blocks attach only to their exact items', async () => {
  const html = '<section data-source-page="1">' +
    '<ul class="options" data-source-block-id="b-1-1">' +
    '<li data-source-block-id="b-1-1" data-source-option-index="0"><span class="option-label">A.</span><span>First answer.</span></li>' +
    '<li data-source-block-id="b-1-1" data-source-option-index="1"><span class="option-label">B.</span><span>Second answer.</span></li></ul>' +
    '<div class="choice-scroll" data-source-block-id="b-1-2"><div class="choice-row">' +
    '<span class="choice-number">2.</span>' +
    '<span class="choice-item" data-source-block-id="b-1-2" data-source-option-index="0"><strong>A.</strong> Row answer.</span>' +
    '</div></div></section>';
  const pages = [{blocks: [
    {type: 'options', items: [
      {label: 'A', runs: [{text: 'First answer.'}]},
      {label: 'B', runs: [{text: 'Second answer.'}]}
    ]},
    {type: 'choice_row', runs: [{text: '2.'}],
      items: [{label: 'A', runs: [{text: 'Row answer.'}]}]}
  ]}];
  const options = [
    optionRecord('b-1-1', 1, 'B', 'Second answer.', '第二项译文'),
    optionRecord('b-1-2', 0, 'A', 'Row answer.', '行内选项译文')
  ];
  const dom = await reader(html, [], pages, options);
  const doc = dom.window.document;
  assert.equal(dom.window.fetchCalls.length, 0);
  assert.equal(doc.querySelectorAll('.option-translation').length, 0);
  await reveal(dom);
  assert.equal(doc.querySelector('main').dataset.translationAttached, '2');
  assert.equal(doc.querySelectorAll('.option-translation').length, 2);
  assert.equal(doc.querySelector('ul.options li:first-child .option-translation'), null);
  assert.equal(doc.querySelector('ul.options li:nth-child(2) .option-translation').textContent, '第二项译文');
  assert.equal(doc.querySelector('ul.options li:nth-child(2) > span:nth-child(2)').classList.contains('cloze-inline-option'), false);
  assert.equal(doc.querySelector('.choice-item .option-translation').textContent, '行内选项译文');
  assert.equal(doc.querySelector('ul.options li:nth-child(2) .option-label').textContent, 'B.');
  assert.equal(doc.querySelector('ul.options li:nth-child(2) > span:nth-child(2)').firstChild.textContent, 'Second answer.');
  doc.querySelector('.paragraph-translation-toggle').click();
  assert([...doc.querySelectorAll('.option-translation')].every(node => node.hidden));
  dom.window.close();
});

test('word-bank choices use their stable bank ID and exact raw label', async () => {
  const html = '<section data-source-page="1"><ul class="options" data-source-block-id="b-1-1">' +
    '<li data-source-block-id="b-1-1" data-source-option-index="0">' +
    '<span class="option-label">A.</span><span>constantly</span></li></ul></section>';
  const pages = [{blocks: [{type: 'options', items: [
    {label: 'A', runs: [{text: 'constantly'}]}
  ]}]}];
  const option = {...optionRecord('b-1-1', 0, 'A', 'constantly', '不断地'),
    kind: 'word_bank_option', optionId: 'cet4:test:word-bank:A'};
  for (const optionId of [option.optionId, 'cet4:test:b-1-1:word-bank:A']) {
    const dom = await reader(html, [], pages, [{...option, optionId}]);
    await reveal(dom);
    assert.equal(dom.window.document.querySelector('main').dataset.translationOptionsAttached, '1');
    assert.equal(dom.window.document.querySelector('.option-translation').textContent, '不断地');
    assert(dom.window.document.querySelector('li > span:last-child').classList.contains('cloze-inline-option'));
    assert.equal(dom.window.document.querySelector('.cloze-option-original').textContent, 'constantly');
    dom.window.close();
  }
});

test('only Section I Kaoyan cloze rows use inline right-side translations', async () => {
  const html = '<section data-source-page="1"><div class="choice-row" data-source-block-id="b-1-1">' +
    '<span class="choice-number">1.</span>' +
    '<span class="choice-item" data-source-block-id="b-1-1" data-source-option-index="0"><strong>A.</strong> Still</span>' +
    '</div></section>';
  const pages = [{blocks: [{type: 'choice_row', runs: [{text: '1.'}],
    items: [{label: 'A', runs: [{text: 'Still'}]}]}]}];
  const option = {...optionRecord('b-1-1', 0, 'A', 'Still', '仍然'),
    questionId: 'kaoyan:test:q-1-1', optionId: 'kaoyan:test:q-1-1:A',
    reflowBlockId: 'kaoyan:test:b-1-1'};
  const dom = await reader(html, [], pages, [option], 'kaoyan:test');
  await reveal(dom);
  const choice = dom.window.document.querySelector('.choice-item');
  assert(choice.classList.contains('cloze-inline-option'));
  assert(choice.parentElement.classList.contains('cloze-inline-row'));
  assert.equal(choice.querySelector('.cloze-option-original').textContent, 'A. Still');
  assert.equal(choice.querySelector('.option-translation').textContent, '仍然');
  assert.equal(choice.querySelector('.option-translation').hidden, false);
  dom.window.close();
});

test('PDF-verified figure choices appear once beside their exact source figure', async () => {
  const html = '<section data-source-page="1"><p>Passage</p>' +
    '<figure><img src="test.assets/figure-001-001.svg" alt="原卷图表"></figure></section>';
  const pages = [{blocks: [block('paragraph', 'Passage'), {type: 'figure', bbox: [1, 2, 3, 4]}],
    figures: 1, figure_text: ['A. first phrase.', 'B. second phrase.']}];
  const pdf = (label, sourceText, translationZh) => ({
    id: `kaoyan:test:q-41-1:${label}`, kind: 'answer_option', paperId: 'kaoyan:test',
    questionId: 'kaoyan:test:q-41-1', optionId: `kaoyan:test:q-41-1:${label}`,
    sourceText, sourceHash: hash(sourceText), translationEligible: true, translationZh,
    reflowBlockIds: ['kaoyan:test:b-1-2'],
    pdfVerifiedSource: {sourcePdfSha256: hash('reviewed pdf'), pdfPage: 1,
      anchorKind: 'figure_bank', reflowBlockIds: ['kaoyan:test:b-1-2'],
      sourceOptionId: `kaoyan:test:part-b:${label}`}
  });
  const first = pdf('A', 'first phrase.', '第一句');
  const second = pdf('B', 'second phrase.', '第二句');
  const alias = {...first, id: 'kaoyan:test:q-42-1:A', optionId: 'kaoyan:test:q-42-1:A',
    questionId: 'kaoyan:test:q-42-1', translationEligible: false, translationZh: '重复译文'};
  const dom = await reader(html, [], pages, [first, second, alias], 'kaoyan:test');
  const doc = dom.window.document;
  assert.equal(doc.querySelectorAll('.pdf-option-translation-board').length, 0);
  assert.equal(dom.window.fetchCalls.length, 0);
  await reveal(dom);
  assert.equal(doc.querySelectorAll('figure').length, 1);
  assert.equal(doc.querySelectorAll('.pdf-option-translation-board').length, 1);
  assert.equal(doc.querySelector('figure').nextElementSibling.className, 'pdf-option-translation-board');
  assert.equal(doc.querySelectorAll('.pdf-option-translation-row').length, 2);
  assert.equal(doc.querySelector('.pdf-option-translation-row').textContent, 'A.first phrase.第一句');
  assert.equal(doc.querySelector('main').dataset.translationOptionsAttached, '2');
  assert.equal(doc.querySelector('main').dataset.translationOptionsSkipped, '0');
  assert.equal(doc.querySelector('.pdf-option-translation-board').hidden, false);
  dom.window.close();

  for (const invalid of [
    {...first, sourceHash: '0'.repeat(64)},
    {...first, pdfVerifiedSource: {...first.pdfVerifiedSource, sourcePdfSha256: '0'.repeat(64)}}
  ]) {
    const rejected = await reader(html, [], pages, [invalid], 'kaoyan:test');
    await reveal(rejected);
    assert.equal(rejected.window.document.querySelectorAll('.pdf-option-translation-board').length, 0);
    assert.equal(rejected.window.document.querySelector('main').dataset.translationOptionsSkipped, '1');
    rejected.window.close();
  }
});

test('PDF-only CET words sharing one OCR item have one source-verified board', async () => {
  const html = '<section data-source-page="1"><ul class="options" data-source-block-id="b-1-1">' +
    '<li data-source-block-id="b-1-1" data-source-option-index="0">' +
    '<span class="option-label">G.</span><span>dental 0) underneath</span></li></ul></section>';
  const pages = [{blocks: [{type: 'options', items: [
    {label: 'G', runs: [{text: 'dental 0) underneath'}]}]}]}];
  const pdf = (label, sourceText, translationZh) => ({
    id: `cet4:test:word-bank:${label}`, kind: 'word_bank_option', paperId: 'cet4:test',
    questionId: 'cet4:test:q-26-1', optionId: `cet4:test:word-bank:${label}`,
    sourceText, sourceHash: hash(sourceText), translationEligible: true, translationZh,
    reflowBlockIds: ['cet4:test:b-1-1'],
    pdfVerifiedSource: {sourcePdfSha256: hash('reviewed pdf'), pdfPage: 1,
      anchorKind: 'word_bank_option', reflowBlockIds: ['cet4:test:b-1-1'],
      reflowOptionIndex: 0, sourceOptionId: `cet4:test:word-bank:${label}`}
  });
  const dom = await reader(html, [], pages,
    [pdf('G', 'dental', '牙科的'), pdf('O', 'underneath', '在下面')]);
  await reveal(dom);
  const doc = dom.window.document;
  assert.equal(doc.querySelectorAll('.pdf-option-translation-board').length, 1);
  assert.equal(doc.querySelectorAll('.pdf-option-translation-row').length, 2);
  assert.equal(doc.querySelector('ul.options').textContent, 'G.dental 0) underneath');
  assert.equal(doc.querySelector('main').dataset.translationOptionsAttached, '2');
  dom.window.close();
});

test('PDF spacing before punctuation may differ between structured and raw option text', async () => {
  const html = '<section data-source-page="1"><ul class="options" data-source-block-id="b-1-1">' +
    '<li data-source-block-id="b-1-1" data-source-option-index="0">' +
    '<span class="option-label">A.</span><span>She told me herself.</span></li></ul></section>';
  const pages = [{blocks: [{type: 'options', items: [
    {label: 'A', runs: [{text: 'She told me herself.'}]}
  ]}]}];
  const sourceText = 'She told me herself .';
  const option = {...optionRecord('b-1-1', 0, 'A', sourceText, '她亲口告诉我的。'),
    reflowSourceText: 'She told me herself.'};
  const dom = await reader(html, [], pages, [option]);
  await reveal(dom);
  assert.equal(dom.window.document.querySelector('main').dataset.translationOptionsAttached, '1');
  assert.equal(dom.window.document.querySelector('li span:nth-child(2)').firstChild.textContent,
    'She told me herself.');
  dom.window.close();
});

test('answer option mismatches and duplicate raw anchors never attach', async () => {
  const html = '<section data-source-page="1"><ul class="options" data-source-block-id="b-1-1">' +
    '<li data-source-block-id="b-1-1" data-source-option-index="0"><span class="option-label">A.</span><span>Actual answer.</span></li>' +
    '<li data-source-block-id="b-1-1" data-source-option-index="1"><span class="option-label">B.</span><span>Other answer.</span></li>' +
    '</ul></section>';
  const pages = [{blocks: [{type: 'options', items: [
    {label: 'A', runs: [{text: 'Actual answer.'}]},
    {label: 'B', runs: [{text: 'Other answer.'}]}
  ]}]}];
  const options = [
    optionRecord('b-1-1', 0, 'A', 'Changed answer.', '不得挂接'),
    optionRecord('b-1-1', 1, 'B', 'Other answer.', '正确译文'),
    optionRecord('b-1-1', 1, 'B', 'Other answer.', '重复译文')
  ];
  const dom = await reader(html, [], pages, options);
  await reveal(dom);
  const doc = dom.window.document;
  assert.equal(doc.querySelector('main').dataset.translationAttached, '1');
  assert.equal(doc.querySelector('main').dataset.translationSkipped, '2');
  assert.equal(doc.querySelector('li:first-child .option-translation'), null);
  assert.equal(doc.querySelector('li:nth-child(2) .option-translation').textContent, '正确译文');
  dom.window.close();
});

test('raw item anchor survives reader regrouping of split option blocks', async () => {
  const html = '<section data-source-page="1"><ul class="options" data-source-block-id="b-1-1">' +
    '<li data-source-block-id="b-1-1" data-source-option-index="0"><span class="option-label">A.</span><span>First.</span></li>' +
    '<li data-source-block-id="b-1-2" data-source-option-index="0"><span class="option-label">B.</span><span>Second.</span></li>' +
    '<li data-source-block-id="b-1-2" data-source-option-index="1"><span class="option-label">C.</span><span>Third.</span></li>' +
    '<li data-source-block-id="b-1-2" data-source-option-index="2"><span class="option-label">D.</span><span>Fourth.</span></li>' +
    '</ul></section>';
  const pages = [{blocks: [
    {type: 'options', items: [{label: 'A', runs: [{text: 'First.'}]}]},
    {type: 'options', items: [
      {label: 'B', runs: [{text: 'Second.'}]}, {label: 'C', runs: [{text: 'Third.'}]},
      {label: 'D', runs: [{text: 'Fourth.'}]}
    ]}
  ]}];
  const dom = await reader(html, [], pages,
    [optionRecord('b-1-2', 2, 'D', 'Fourth.', '第四项')]);
  await reveal(dom);
  assert.equal(dom.window.document.querySelector('main').dataset.translationAttached, '1');
  assert.equal(dom.window.document.querySelector('li:last-child .option-translation').textContent, '第四项');
  dom.window.close();
});

test('one structured option ID cannot translate two different raw choices', async () => {
  const html = '<section data-source-page="1">' +
    '<ul class="options" data-source-block-id="b-1-1"><li data-source-block-id="b-1-1" data-source-option-index="0">' +
    '<span class="option-label">A.</span><span>One.</span></li></ul>' +
    '<ul class="options" data-source-block-id="b-1-2"><li data-source-block-id="b-1-2" data-source-option-index="0">' +
    '<span class="option-label">A.</span><span>Two.</span></li></ul></section>';
  const pages = [{blocks: [
    {type: 'options', items: [{label: 'A', runs: [{text: 'One.'}]}]},
    {type: 'options', items: [{label: 'A', runs: [{text: 'Two.'}]}]}
  ]}];
  const dom = await reader(html, [], pages, [
    optionRecord('b-1-1', 0, 'A', 'One.', '第一项'),
    optionRecord('b-1-2', 0, 'A', 'Two.', '不得重复')
  ]);
  await reveal(dom);
  const doc = dom.window.document;
  assert.equal(doc.querySelector('main').dataset.translationOptionsAttached, '1');
  assert.equal(doc.querySelector('main').dataset.translationOptionsSkipped, '1');
  assert.equal(doc.querySelectorAll('.option-translation').length, 1);
  dom.window.close();
});
