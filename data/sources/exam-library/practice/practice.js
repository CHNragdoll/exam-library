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
  const {element, contextText, renderMath, renderStem,
    renderOptions: renderSharedOptions, renderContent, renderAnswer: renderSharedAnswer} =
    window.ExamPracticeRender;

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

  function renderOptions(question) {
    const options = Array.isArray(question.options) ? question.options : [];
    ui.optionsFieldset.hidden = options.length === 0;
    ui.writtenWrap.hidden = options.length > 0;
    ui.written.value = state.written.get(question.id) || '';
    renderSharedOptions(ui.options, question, 'choice', state.selected.get(question.id) || new Set());
  }

  function renderAnswer(question) {
    renderSharedAnswer({panel: ui.answer, question, answer: state.answers.get(question.id),
      options: ui.options, written: ui.written, reveal: ui.reveal, redo: ui.redo,
      selected: state.selected.get(question.id) || new Set(), order: ui.order.value});
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
    renderStem(ui.stem, question);
    renderContent(ui.content, question);
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
