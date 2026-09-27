(() => {
  'use strict';
  const dataNode = document.getElementById('crop-review-data');
  if (!dataNode) return;
  let entries;
  try { entries = JSON.parse(dataNode.textContent); } catch (_) { return; }
  const KEY = 'exam-library:crop-review:v1';
  const cards = Array.from(document.querySelectorAll('.review-item'));
  const category = document.getElementById('category');
  const state = document.getElementById('state');
  const search = document.getElementById('search');
  const summary = document.getElementById('summary');
  const empty = document.getElementById('empty');
  const storageStatus = document.getElementById('storage-status');
  const revisions = new Map(entries.map(item => [item.id, item.revision]));
  let saved = {};
  try { saved = JSON.parse(localStorage.getItem(KEY)) || {}; } catch (_) { storageStatus.textContent = '浏览器未提供本地保存；请导出审查 JSON。'; }
  const persist = () => {
    try { localStorage.setItem(KEY, JSON.stringify(saved)); }
    catch (_) { storageStatus.textContent = '本地保存不可用；请导出审查 JSON。'; }
  };
  const refresh = () => {
    const query = search.value.trim().toLocaleLowerCase();
    let visible = 0;
    for (const card of cards) {
      const decision = card.querySelector('.decision').value;
      const matches = (category.value === 'all' || card.dataset.category === category.value)
        && (state.value === 'all' || decision === state.value)
        && (!query || card.textContent.toLocaleLowerCase().includes(query));
      card.hidden = !matches;
      if (matches) visible += 1;
    }
    const counts = {pending: 0, pass: 0, revise: 0};
    cards.forEach(card => { counts[card.querySelector('.decision').value] += 1; });
    summary.textContent = `显示 ${visible}/${cards.length} · 待检查 ${counts.pending} · 通过 ${counts.pass} · 需修改 ${counts.revise}`;
    empty.hidden = visible > 0;
  };
  for (const card of cards) {
    const id = card.dataset.id;
    const record = saved[id];
    const decision = card.querySelector('.decision');
    const note = card.querySelector('.note');
    if (record && typeof record === 'object') {
      note.value = typeof record.note === 'string' ? record.note : '';
      if (record.revision === revisions.get(id) && !record.needsRecheck && ['pending', 'pass', 'revise'].includes(record.decision)) {
        decision.value = record.decision;
      } else if (record.needsRecheck || (record.decision && record.decision !== 'pending')) {
        card.querySelector('.revision-warning').hidden = false;
      }
    }
    const save = (event) => {
      const needsRecheck = !card.querySelector('.revision-warning').hidden && event.type !== 'change';
      saved[id] = {revision: revisions.get(id), decision: decision.value, note: note.value};
      if (needsRecheck) saved[id].needsRecheck = true;
      else card.querySelector('.revision-warning').hidden = true;
      persist();
      refresh();
    };
    decision.addEventListener('change', save);
    note.addEventListener('input', save);
  }
  [category, state, search].forEach(control => control.addEventListener(control === search ? 'input' : 'change', refresh));
  refresh();
  document.getElementById('export').addEventListener('click', () => {
    const result = {version: 1, exportedAt: new Date().toISOString(), entries: cards.map(card => {
      const id = card.dataset.id;
      return {id, revision: revisions.get(id), decision: card.querySelector('.decision').value, note: card.querySelector('.note').value};
    })};
    const blob = new Blob([JSON.stringify(result, null, 2)], {type: 'application/json'});
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = 'crop-review-audit.json';
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  });
  const dialog = document.getElementById('zoom-dialog');
  const zoomBody = document.getElementById('zoom-body');
  document.querySelectorAll('.zoom').forEach(button => button.addEventListener('click', () => {
    const card = button.closest('.review-item');
    const panel = button.dataset.panel;
    const source = panel === 'page' ? card.querySelector('.page-stage')
      : card.querySelector(panel === 'before' ? '.review-grid figure:nth-child(2) img' : '.review-grid figure:nth-child(3) img');
    if (!source) return;
    zoomBody.replaceChildren(source.cloneNode(true));
    zoomBody.querySelectorAll('img').forEach(img => { img.loading = 'eager'; });
    document.getElementById('zoom-title').textContent = `${card.querySelector('h2').textContent} · ${panel === 'page' ? '原页位置' : panel === 'before' ? '修复前' : '修复后'}`;
    dialog.showModal();
  }));
  document.getElementById('close-zoom').addEventListener('click', () => dialog.close());
  dialog.addEventListener('click', event => { if (event.target === dialog) dialog.close(); });
})();
