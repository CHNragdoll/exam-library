(() => {
  'use strict';
  const nav = document.getElementById('paper-versions');
  const paperId = new URLSearchParams(location.search).get('paper');
  if (!nav || !paperId) return;

  const catalogUrl = new URL('../index.htm', location.href);
  function readerUrl(relativePath) {
    if (typeof relativePath !== 'string' || !relativePath) return null;
    try {
      const url = new URL(relativePath, catalogUrl);
      return url.origin === location.origin && url.protocol === location.protocol ? url : null;
    } catch (_) { return null; }
  }
  function link(label, url) {
    const anchor = document.createElement('a');
    anchor.textContent = label;
    anchor.href = url.href;
    return anchor;
  }

  async function showSourceNotices(paper) {
    const holder = document.getElementById('paper-source-notices');
    if (!holder || !['kaoyan', 'math3', 'cs408', 'politics'].includes(paper.category)) return;
    try {
      const response = await fetch('../source-notices.json', {headers: {Accept: 'application/json'}});
      if (!response.ok) return;
      const data = await response.json();
      const notes = data.schema === 'exam-source-notices-v1' && data.papers?.[paper.id];
      if (!Array.isArray(notes) || !notes.length || notes.some(note => typeof note !== 'string')) return;
      const body = holder.querySelector('div');
      if (!body) return;
      body.replaceChildren(...notes.map(note => {
        const paragraph = document.createElement('p');
        paragraph.textContent = note;
        return paragraph;
      }));
      holder.hidden = false;
    } catch (_) { /* Optional warnings must not prevent practicing. */ }
  }

  fetch('../documents.json', {headers: {Accept: 'application/json'}})
    .then(response => { if (!response.ok) throw new Error('catalog'); return response.json(); })
    .then(documents => {
      const paper = Array.isArray(documents) && documents.find(item => item.id === paperId);
      if (!paper || paper.kind === 'answers') return;
      const svg = readerUrl(paper.svg);
      const reflow = readerUrl(paper.reflow);
      if (!svg || !reflow) return;
      const compare = new URL(reflow.href);
      compare.searchParams.set('exam-compare', '1');
      const current = document.createElement('span');
      current.textContent = '整卷刷题';
      current.setAttribute('aria-current', 'page');
      nav.replaceChildren(link('SVG 原版', svg), link('LaTeX 重排', reflow),
        current, link('并排对比', compare));
      nav.hidden = false;
      showSourceNotices(paper);
    })
    .catch(() => { /* Practicing remains available if the catalog is unavailable. */ });
})();
