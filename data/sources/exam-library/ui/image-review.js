(() => {
  'use strict';
  const data = JSON.parse(document.getElementById('review-data').textContent);
  const key = 'exam-library:image-review:v1';
  const allowed = new Set(['pending', 'pass', 'revise']);
  let saved = {};
  const storageStatus = document.getElementById('storage-status');
  try { const value = JSON.parse(localStorage.getItem(key) || '{}'); if (value && typeof value === 'object' && !Array.isArray(value)) saved = value; }
  catch (_) { storageStatus.textContent = '浏览器未允许本地保存；本次仍可审计，请导出结果后再关闭页面。'; }
  const cards = Array.from(document.querySelectorAll('.review-item'));
  const category = document.getElementById('category'), state = document.getElementById('state'), search = document.getElementById('search');
  const current = () => Object.fromEntries(cards.map(card => [card.dataset.id, {decision:card.querySelector('.decision').value, note:card.querySelector('.note').value}]));
  function filter() {
    let visible = 0, pass = 0, revise = 0;
    const query = search.value.trim().toLowerCase();
    for (const card of cards) {
      const decision = card.querySelector('.decision').value;
      if (decision === 'pass') pass++; if (decision === 'revise') revise++;
      card.dataset.decision = decision;
      card.hidden = (category.value !== 'all' && category.value !== card.dataset.category) || (state.value !== 'all' && state.value !== decision) || (query && !card.textContent.toLowerCase().includes(query));
      if (!card.hidden) visible++;
    }
    document.getElementById('summary').textContent = `显示 ${visible}/${cards.length} · 待检查 ${cards.length-pass-revise} · 通过 ${pass} · 需修改 ${revise}`;
    document.getElementById('empty').hidden = visible !== 0;
  }
  function save() {
    try { localStorage.setItem(key, JSON.stringify(current())); }
    catch (_) { storageStatus.textContent = '无法保存到浏览器；请导出审计 JSON，以免关闭后丢失备注。'; }
  }
  for (const card of cards) {
    const decision = card.querySelector('.decision'), note = card.querySelector('.note'), value = saved[card.dataset.id];
    if (value && allowed.has(value.decision)) decision.value = value.decision;
    if (value && typeof value.note === 'string') note.value = value.note;
    decision.addEventListener('change', () => { save(); filter(); });
    note.addEventListener('input', save);
  }
  category.addEventListener('change', filter); state.addEventListener('change', filter); search.addEventListener('input', filter); filter();
  document.getElementById('export').addEventListener('click', () => {
    const decisions = current();
    const payload = {version:1, pathBase:'data/sources/exam-library/', exportedAt:new Date().toISOString(), images:data.map(item => ({id:item.id,title:item.title,original:item.original,replacement:item.replacement,...decisions[item.id]}))};
    const url = URL.createObjectURL(new Blob([JSON.stringify(payload,null,2)], {type:'application/json;charset=utf-8'}));
    const a = document.createElement('a'); a.href=url; a.download='exam-image-review.json'; document.body.append(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url),1000);
  });
  const dialog = document.getElementById('zoom-dialog'), zoomImage = document.getElementById('zoom-image'), scale = document.getElementById('zoom-scale');
  for (const button of document.querySelectorAll('.zoom')) button.addEventListener('click', () => {
    const image = button.closest('figure').querySelector('img');
    zoomImage.src=image.src; zoomImage.alt=image.alt; document.getElementById('zoom-title').textContent=image.alt;
    scale.value='1'; zoomImage.style.width='100%'; dialog.showModal();
  });
  scale.addEventListener('change', () => { zoomImage.style.width=`${Number(scale.value)*100}%`; });
  document.getElementById('close-zoom').addEventListener('click', () => dialog.close());
})();
