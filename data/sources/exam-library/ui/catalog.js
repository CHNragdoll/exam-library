/* Local, dependency-free catalog. Content and links are generated in build.py. */
(function () {
  'use strict';
  const form = document.getElementById('catalog-filters');
  if (!form) return;
  const main = document.getElementById('catalog-main');
  const cards = Array.from(document.querySelectorAll('article.paper'));
  const groups = Array.from(document.querySelectorAll('.year'));
  const search = document.getElementById('catalog-search');
  const year = document.getElementById('filter-year');
  const kind = document.getElementById('filter-kind');
  const category = document.getElementById('filter-category');
  const count = document.getElementById('result-count');
  const more = document.getElementById('load-more');
  let limit = 30;
  function normalize(value) { return String(value || '').normalize('NFKC').toLocaleLowerCase().replace(/\s+/g, ' ').trim(); }
  const indexed = cards.map(function (node) { return {node: node, text: normalize(node.dataset.search)}; });
  function matches(item, terms) {
    const data = item.node.dataset;
    return (!year.value || data.year === year.value) && (!kind.value || data.kind === kind.value) && (!category || !category.value || data.category === category.value) && terms.every(function (term) { return item.text.includes(term); });
  }
  function filter() {
    const terms = normalize(search.value).split(' ').filter(Boolean);
    let total = 0;
    indexed.forEach(function (item) { const match = matches(item, terms); if (match) total++; item.node.hidden = !match || total > limit; item.node.dataset.match = match ? '1' : '0'; });
    groups.forEach(function (group) {
      const items = Array.from(group.querySelectorAll('article.paper'));
      const shown = items.filter(function (node) { return !node.hidden; }).length;
      const matching = items.filter(function (node) { return node.dataset.match === '1'; }).length;
      group.hidden = shown === 0;
      group.querySelector('.year-count').textContent = matching + ' 份资料';
    });
    count.textContent = '共 ' + total + ' 份资料' + (total > limit ? ' · 已显示 ' + limit + ' 份' : '');
    document.getElementById('no-results').hidden = total !== 0;
    more.hidden = total <= limit;
    more.textContent = '再显示 ' + Math.min(30, Math.max(0, total - limit)) + ' 份资料';
  }
  function reset() { form.reset(); limit = 30; filter(); search.focus(); }
  form.addEventListener('submit', function (event) { event.preventDefault(); limit = 30; filter(); });
  form.addEventListener('input', function () { limit = 30; filter(); });
  form.addEventListener('change', function () { limit = 30; filter(); });
  form.addEventListener('reset', function () { setTimeout(function () { limit = 30; filter(); }, 0); });
  document.getElementById('empty-reset').addEventListener('click', reset);
  more.addEventListener('click', function () {
    const previouslyVisible = new Set(cards.filter(function (card) { return !card.hidden; }));
    limit += 30; filter();
    const firstNew = cards.find(function (card) { return !card.hidden && !previouslyVisible.has(card); });
    if (firstNew) firstNew.querySelector('h3 a').focus();
  });
  /* The reader owns this schema. Only accept URLs present in our generated catalog. */
  const allowed = new Set(Array.from(document.querySelectorAll('.versions a')).map(function (anchor) { const u = new URL(anchor.href); u.hash = ''; return u.href; }));
  const recentList = document.getElementById('recent-list');
  const recentEmpty = document.getElementById('recent-empty');
  const clearRecent = document.getElementById('clear-recent');
  const storageKey = 'exam-library:recent:v1';
  function readRecent() {
    recentList.replaceChildren(); clearRecent.hidden = true;
    let records;
    try { records = JSON.parse(localStorage.getItem(storageKey) || '[]'); }
    catch (_) { recentEmpty.hidden = false; recentEmpty.textContent = '此窗口暂时无法保存阅读记录，仍可正常打开试卷。'; return; }
    if (!Array.isArray(records)) records = [];
    const seen = new Set();
    records = records.filter(function (item) {
      if (!item || typeof item.url !== 'string' || typeof item.title !== 'string') return false;
      if (main.dataset.activeCategory && item.category !== main.dataset.activeCategory) return false;
      try {
        const u = new URL(item.url, location.href); u.hash = '';
        if (!allowed.has(u.href) || seen.has(u.href)) return false;
        seen.add(u.href); return true;
      } catch (_) { return false; }
    }).sort(function (a,b) { return (Number(b.updatedAt)||0) - (Number(a.updatedAt)||0); }).slice(0,3);
    recentEmpty.hidden = records.length > 0;
    recentEmpty.textContent = '读过的试卷会显示在这里，方便接着读。';
    clearRecent.hidden = records.length === 0;
    records.forEach(function (item) {
      const anchor = document.createElement('a'); anchor.className = 'recent-card';
      const url = new URL(item.url, location.href); url.hash = 'resume'; anchor.href = url.href;
      const title = document.createElement('strong'); title.textContent = item.title;
      const detail = document.createElement('p');
      const progress = Math.min(1, Math.max(0, Number(item.progress) || 0));
      detail.textContent = (item.mode === 'reflow' ? 'LaTeX 重排' : 'SVG 原版') + ' · 已读 ' + Math.round(progress * 100) + '% · 继续阅读 →';
      const bar = document.createElement('div'); bar.className = 'recent-progress'; bar.setAttribute('aria-hidden','true');
      const fill = document.createElement('span'); fill.style.width = (progress * 100) + '%'; bar.append(fill);
      anchor.append(title, detail, bar); recentList.append(anchor);
    });
  }
  clearRecent.addEventListener('click', function () {
    try { localStorage.removeItem(storageKey); readRecent(); }
    catch (_) { recentEmpty.hidden = false; recentEmpty.textContent = '此窗口暂时无法清除阅读记录。'; }
  });
  window.addEventListener('pageshow', readRecent);
  window.addEventListener('storage', function (event) { if (event.key === storageKey) readRecent(); });
  filter(); readRecent();
}());
