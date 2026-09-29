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
    })
    .catch(() => { /* Practicing remains available if the catalog is unavailable. */ });
})();
