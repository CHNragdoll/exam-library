(() => {
  'use strict';

  const byId = id => document.getElementById(id);
  const ui = {
    category: byId('category-select'), paper: byId('paper-select'),
    order: byId('order-select'), seed: byId('seed-input'),
    seedWrap: byId('seed-wrap'), reshuffle: byId('reshuffle-button'),
    status: byId('page-status'), panel: byId('practice-panel'),
    paperCategory: byId('paper-category'), paperTitle: byId('paper-title'),
    jump: byId('question-jump'), progress: byId('question-progress'),
    orderNote: byId('order-note'), number: byId('question-number'),
    kind: byId('question-kind'), context: byId('question-context'),
    stem: byId('question-stem'), content: byId('question-content'),
    optionsFieldset: byId('options-fieldset'),
    options: byId('options-list'), writtenWrap: byId('written-answer-wrap'),
    written: byId('written-answer'), reveal: byId('reveal-button'),
    redo: byId('redo-button'), answer: byId('answer-panel'),
    previous: byId('previous-button'), next: byId('next-button')
  };
  const state = {
    papers: [], questions: [], paper: null, index: 0, request: 0,
    selected: new Map(), written: new Map(), answers: new Map(), revealed: new Set()
  };
  let mathQueue = Promise.resolve();

  function element(tag, className, value) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (value !== undefined && value !== null) node.textContent = String(value);
    return node;
  }

  function valueText(value) {
    if (value === null || value === undefined) return '';
    if (typeof value === 'string') return value;
    if (Array.isArray(value)) return value.map(valueText).filter(Boolean).join('\n');
    if (typeof value === 'object') return JSON.stringify(value, null, 2);
    return String(value);
  }

  function contextText(context) {
    if (context && typeof context === 'object' && !Array.isArray(context) &&
        typeof context.text === 'string') return context.text;
    return valueText(context);
  }

  function localImageUrl(src) {
    if (typeof src !== 'string' || !src.trim()) return null;
    try {
      const url = new URL(src, document.baseURI);
      if (url.origin !== location.origin || !/^https?:$/.test(url.protocol) ||
          url.pathname.startsWith('/api/')) return null;
      return url.pathname + url.search;
    } catch (_) {
      return null;
    }
  }

  function setStatus(message, error = false) {
    ui.status.textContent = message;
    ui.status.classList.toggle('is-error', error);
    ui.status.hidden = false;
  }

  async function getJson(path) {
    const response = await fetch(path, {headers: {Accept: 'application/json'}});
    if (!response.ok) throw new Error(`请求失败（HTTP ${response.status}）`);
    return response.json();
  }

  function renderMath(node) {
    if (!/\\(?:\(|\[)/.test(node.textContent)) return;
    mathQueue = mathQueue.catch(() => {}).then(async () => {
      const math = window.MathJax;
      if (!math) return;
      await math.startup?.promise;
      if (math.typesetPromise && node.isConnected) await math.typesetPromise([node]);
    }).catch(() => { /* The safely inserted TeX text remains readable. */ });
  }

  function optionText(paper) {
    const count = Number(paper.questionCount) || 0;
    return `${paper.title || paper.id} · ${count} 题`;
  }

  function fillSelect(select, items, labelFor, valueFor) {
    select.replaceChildren(...items.map(item => {
      const option = element('option', '', labelFor(item));
      option.value = valueFor(item);
      return option;
    }));
  }

  function renderCategories(preferred) {
    const categories = new Map();
    for (const paper of state.papers) {
      if (paper.kind === 'answers') continue;
      if (!categories.has(paper.category)) categories.set(paper.category, paper.categoryLabel || paper.category);
    }
    fillSelect(ui.category, [...categories], pair => pair[1], pair => pair[0]);
    if (categories.has(preferred)) ui.category.value = preferred;
  }

  function renderPapers(preferred) {
    const papers = state.papers.filter(paper =>
      paper.category === ui.category.value && paper.kind !== 'answers');
    fillSelect(ui.paper, papers, optionText, paper => paper.id);
    if (papers.some(paper => paper.id === preferred)) ui.paper.value = preferred;
    if (papers.length) loadQuestions();
    else {
      state.questions = [];
      ui.panel.hidden = true;
      setStatus('这个科目暂无可练习的试卷。');
    }
  }

  function updateOrderControls() {
    const shuffled = ui.order.value === 'shuffle';
    ui.seedWrap.hidden = !shuffled;
    ui.reshuffle.hidden = !shuffled;
  }

  function currentQuestion() { return state.questions[state.index]; }

  async function loadQuestions() {
    const paperId = ui.paper.value;
    if (!paperId) return;
    const previousId = currentQuestion()?.id;
    const changedPaper = state.paper?.id !== paperId;
    if (changedPaper) {
      state.selected.clear(); state.written.clear();
      state.answers.clear(); state.revealed.clear();
    }
    const request = ++state.request;
    ui.panel.hidden = true;
    setStatus('正在加载题目…');
    const params = new URLSearchParams({order: ui.order.value});
    if (ui.order.value === 'shuffle') params.set('seed', ui.seed.value || '1');
    try {
      const data = await getJson(`/api/v1/papers/${encodeURIComponent(paperId)}/questions?${params}`);
      if (request !== state.request) return;
      state.paper = data.paper || state.papers.find(paper => paper.id === paperId);
      state.questions = Array.isArray(data.questions) ? data.questions : [];
      const oldIndex = changedPaper ? -1 : state.questions.findIndex(question => question.id === previousId);
      state.index = oldIndex >= 0 ? oldIndex : 0;
      fillSelect(ui.jump, state.questions, question => `第 ${question.number || '?'} 题`, question => question.id);
      ui.paperTitle.textContent = state.paper?.title || paperId;
      ui.paperCategory.textContent = state.paper?.categoryLabel || ui.category.selectedOptions[0]?.textContent || '';
      if (!state.questions.length) {
        setStatus('这份试卷暂无可练习的题目。');
        return;
      }
      ui.status.hidden = true;
      ui.panel.hidden = false;
      renderQuestion();
    } catch (error) {
      if (request !== state.request) return;
      setStatus(`题目加载失败：${error.message}。请确认本地题库服务已启动，然后重选试卷。`, true);
    }
  }

  function optionLabel(option, index) {
    return option.displayLabel || option.label || option.sourceLabel || `${String.fromCharCode(65 + index)}.`;
  }

  function renderOptions(question) {
    const options = Array.isArray(question.options) ? question.options : [];
    ui.options.replaceChildren();
    ui.optionsFieldset.hidden = options.length === 0;
    ui.writtenWrap.hidden = options.length > 0;
    ui.written.value = state.written.get(question.id) || '';
    const multiple = /multi|multiple/i.test(question.questionType || '');
    const selected = state.selected.get(question.id) || new Set();
    for (const [index, option] of options.entries()) {
      const label = element('label', 'option');
      label.dataset.optionId = String(option.id);
      const input = element('input');
      input.type = multiple ? 'checkbox' : 'radio';
      input.name = 'choice';
      input.value = String(option.id);
      input.checked = selected.has(String(option.id));
      label.append(input, element('span', 'option-label', optionLabel(option, index)),
        element('span', 'option-text', valueText(option.text)));
      ui.options.append(label);
    }
  }

  function numberedSubquestions(text) {
    const markers = [...text.matchAll(/[（(]([1-9１-９])[)）]/g)].map(match => ({
      index: match.index,
      length: match[0].length,
      number: Number(match[1].replace(/[１-９]/g, digit => String(digit.charCodeAt(0) - 0xff10)))
    }));
    const startsItem = marker => {
      const before = text.slice(0, marker.index).trimEnd();
      return !before || /[。！？；：.!?;:)）]$/.test(before);
    };
    const firstIndex = markers.findIndex(marker => marker.number === 1 && startsItem(marker));
    const first = markers[firstIndex];
    const second = markers[firstIndex + 1];
    if (!first || !second || second.number !== 2 || !startsItem(second) ||
        text.slice(first.index + first.length, second.index).trim().length < 2) return null;
    const sequence = [first, second];
    for (const marker of markers.slice(firstIndex + 2)) {
      if (marker.number !== sequence.length + 1 || !startsItem(marker)) break;
      sequence.push(marker);
    }
    return {prefix: text.slice(0, first.index), items: sequence.map((marker, index) =>
      text.slice(marker.index, sequence[index + 1]?.index ?? text.length))};
  }

  function contentText(text) {
    const paragraph = element('div', 'content-text');
    const parts = numberedSubquestions(text);
    if (!parts) {
      paragraph.textContent = text;
      return paragraph;
    }
    if (parts.prefix) paragraph.append(document.createTextNode(parts.prefix));
    for (const item of parts.items) paragraph.append(element('span', 'content-subquestion', item));
    return paragraph;
  }

  function renderContentBlocks(question) {
    ui.content.replaceChildren();
    const blocks = Array.isArray(question.contentBlocks) ? question.contentBlocks : [];
    for (const block of blocks) {
      if (!block || (block.role !== 'content' && block.role !== 'figure')) continue;
      const section = element('section', `content-block content-${block.role}`);
      const body = valueText(block.text);
      const codeText = valueText(block.code);
      const repeatedCode = codeText.trim() &&
        body.replace(/\s+/g, '') === codeText.replace(/\s+/g, '');
      if (body.trim() && !repeatedCode && block.role !== 'figure') {
        section.append(contentText(body));
      }
      if (codeText.trim()) {
        const pre = element('pre', 'content-code code');
        pre.append(element('code', '', codeText));
        section.append(pre);
      }
      const images = Array.isArray(block.images) ? block.images : [];
      const figure = element('figure', 'content-figure');
      for (const item of images) {
        const src = localImageUrl(item?.src);
        if (!src) continue;
        const image = element('img');
        image.alt = valueText(item.alt) || body || '题目附图';
        image.loading = 'lazy';
        image.decoding = 'async';
        const failure = element('p', 'image-error', '附图暂时无法加载，请查看原卷。');
        failure.hidden = true;
        image.addEventListener('error', () => { image.hidden = true; failure.hidden = false; });
        image.src = src;
        figure.append(image, failure);
      }
      if (figure.querySelector('img')) {
        if (body.trim() && block.role === 'figure') figure.append(element('figcaption', '', body));
        section.append(figure);
      } else if (body.trim() && block.role === 'figure') {
        section.append(element('p', 'content-text', body));
      }
      if (section.childNodes.length) ui.content.append(section);
    }
    ui.content.hidden = !ui.content.childNodes.length;
    window.ExamCodeHighlight?.apply(ui.content);
  }

  function appendAnswerField(label, value) {
    const text = valueText(value);
    if (!text.trim()) return;
    const row = element('p');
    row.append(element('strong', '', `${label}：`), document.createTextNode(text));
    ui.answer.append(row);
  }

  function renderAnswer(question) {
    ui.answer.replaceChildren();
    const answer = state.answers.get(question.id);
    const status = answer?.status || question.answerStatus || 'missing';
    const ids = Array.isArray(answer?.correctOptionIds) ? answer.correctOptionIds.map(String) : [];
    const optionIds = new Set((question.options || []).map(option => String(option.id)));
    const mapped = status === 'explicit' && ids.length > 0 && ids.every(id => optionIds.has(id));
    const selected = state.selected.get(question.id) || new Set();

    ui.answer.append(element('h3', '', '参考答案'));
    const statusNode = element('p', 'answer-status');
    if (status === 'missing' || status === 'unknown') statusNode.textContent = '暂无可用答案；本题不判对错。';
    else if (status === 'ambiguous') statusNode.textContent = '答案存在歧义，待核对；本题不判对错。';
    else if (status !== 'explicit') statusNode.textContent = '答案状态待核对；本题不判对错。';
    else if (mapped && selected.size) {
      const correct = selected.size === ids.length && ids.every(id => selected.has(id));
      statusNode.textContent = correct ? '回答正确。' : '回答与参考答案不同。';
      statusNode.classList.add(correct ? 'is-known' : 'is-uncertain');
    } else if (mapped) statusNode.textContent = '尚未作答；已标出正确选项。';
    else if ((question.options || []).length) statusNode.textContent = '已收录参考答案，但无法可靠对应选项；本题不判对错。';
    else statusNode.textContent = '已收录参考答案；请自行对照作答。';
    if (status !== 'explicit') statusNode.classList.add('is-uncertain');
    ui.answer.append(statusNode);

    appendAnswerField(status === 'explicit' && ui.order.value !== 'shuffle' ? '答案' : '原卷答案记录', answer?.value);
    appendAnswerField('解答', answer?.solution);
    appendAnswerField('解析', answer?.explanation);
    appendAnswerField('评注', answer?.commentary);
    appendAnswerField('知识点', answer?.knowledge);
    for (const label of ui.options.querySelectorAll('.option')) {
      const id = label.dataset.optionId;
      if (mapped && ids.includes(id)) {
        label.classList.add('is-correct');
        const original = (question.options || []).find(option => String(option.id) === id);
        const source = original?.sourceLabel || original?.label;
        const tag = ui.order.value === 'shuffle' && source ? `正确答案 · 原卷 ${source}` : '正确答案';
        label.append(element('span', 'option-tag', tag));
      } else if (mapped && selected.has(id)) {
        label.classList.add('is-wrong');
        label.append(element('span', 'option-tag', '我的选择'));
      }
    }
    ui.options.querySelectorAll('input').forEach(input => { input.disabled = true; });
    ui.written.disabled = true;
    ui.answer.hidden = false;
    ui.reveal.hidden = true;
    ui.redo.hidden = false;
    renderMath(ui.answer);
  }

  function renderQuestion() {
    const question = currentQuestion();
    if (!question) return;
    window.MathJax?.typesetClear?.([byId('question-card')]);
    const number = question.number || state.index + 1;
    ui.jump.value = question.id;
    ui.progress.textContent = `第 ${state.index + 1} / ${state.questions.length} 题`;
    ui.orderNote.textContent = ui.order.value === 'shuffle' ? `乱序练习 · 种子 ${ui.seed.value || '1'}` : '原卷选项顺序';
    ui.number.textContent = `第 ${number} 题`;
    const type = /multi|multiple/i.test(question.questionType || '') ? '多选' :
      (question.options || []).length ? '单选' : '非选择题';
    ui.kind.textContent = question.status === 'complete' ? type : `${type} · 题文待核`;
    const context = contextText(question.context);
    ui.context.textContent = context;
    ui.context.hidden = !context.trim();
    ui.stem.textContent = valueText(question.stem) || '题干暂缺，请以原卷核对。';
    renderContentBlocks(question);
    renderOptions(question);
    ui.answer.hidden = true;
    ui.answer.replaceChildren();
    ui.reveal.hidden = false;
    ui.reveal.disabled = false;
    ui.reveal.textContent = '查看答案';
    ui.redo.hidden = true;
    ui.written.disabled = false;
    ui.previous.disabled = state.index === 0;
    ui.next.disabled = state.index === state.questions.length - 1;
    if (state.revealed.has(question.id) && state.answers.has(question.id)) renderAnswer(question);
    renderMath(byId('question-card'));
  }

  async function revealAnswer() {
    const question = currentQuestion();
    if (!question) return;
    const id = question.id;
    ui.reveal.disabled = true;
    ui.reveal.textContent = '正在读取答案…';
    try {
      const answer = state.answers.get(id) ||
        await getJson(`/api/v1/questions/${encodeURIComponent(id)}/answer`);
      state.answers.set(id, answer);
      state.revealed.add(id);
      if (currentQuestion()?.id === id) renderAnswer(currentQuestion());
    } catch (error) {
      if (currentQuestion()?.id === id) {
        ui.reveal.disabled = false;
        ui.reveal.textContent = '重试查看答案';
        setStatus(`答案读取失败：${error.message}`, true);
      }
    }
  }

  ui.category.addEventListener('change', () => renderPapers());
  ui.paper.addEventListener('change', loadQuestions);
  ui.order.addEventListener('change', () => { updateOrderControls(); loadQuestions(); });
  ui.seed.addEventListener('change', () => { if (ui.order.value === 'shuffle') loadQuestions(); });
  ui.reshuffle.addEventListener('click', () => {
    ui.seed.value = String(Math.floor(Math.random() * 0x7fffffff) + 1);
    loadQuestions();
  });
  ui.jump.addEventListener('change', () => {
    const index = state.questions.findIndex(question => question.id === ui.jump.value);
    if (index >= 0) { state.index = index; renderQuestion(); }
  });
  ui.previous.addEventListener('click', () => { if (state.index > 0) { state.index--; renderQuestion(); } });
  ui.next.addEventListener('click', () => {
    if (state.index < state.questions.length - 1) { state.index++; renderQuestion(); }
  });
  ui.options.addEventListener('change', () => {
    const question = currentQuestion();
    if (!question) return;
    state.selected.set(question.id, new Set([...ui.options.querySelectorAll('input:checked')].map(input => input.value)));
  });
  ui.written.addEventListener('input', () => {
    const question = currentQuestion();
    if (question) state.written.set(question.id, ui.written.value);
  });
  ui.reveal.addEventListener('click', revealAnswer);
  ui.redo.addEventListener('click', () => {
    const question = currentQuestion();
    if (!question) return;
    state.revealed.delete(question.id);
    state.selected.delete(question.id);
    state.written.delete(question.id);
    renderQuestion();
  });

  (async () => {
    try {
      const data = await getJson('/api/v1/papers');
      state.papers = Array.isArray(data.papers) ? data.papers : [];
      const preferred = new URLSearchParams(location.search).get('paper');
      const selectedPaper = state.papers.find(paper => paper.id === preferred);
      renderCategories(selectedPaper?.category);
      renderPapers(preferred);
    } catch (error) {
      setStatus(`试卷目录加载失败：${error.message}。请确认本地题库服务已启动后刷新。`, true);
    }
  })();
})();
