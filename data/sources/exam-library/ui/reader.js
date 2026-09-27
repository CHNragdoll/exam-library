/* Shared offline reader. Enhances existing paper markup; never rewrites exam content. */
(() => {
  'use strict';
  const configNode = document.getElementById('exam-reader-config');
  const main = document.querySelector('main');
  if (!configNode || !main || document.querySelector('.reader-toolbar')) return;
  let config;
  try { config = JSON.parse(configNode.textContent); } catch (_) { return; }
  if (!config || !['svg', 'reflow'].includes(config.mode)) return;
  const SETTINGS_KEY = 'exam-library:reader:v1';
  const RECENT_KEY = 'exam-library:recent:v1';
  const isSvg = config.mode === 'svg';
  const clamp = (n, a, b) => Math.max(a, Math.min(b, n));
  const safeUrl = value => {
    try {
      const u = new URL(value, location.href);
      if (u.protocol !== location.protocol) return null;
      if (u.protocol !== 'file:' && u.origin !== location.origin) return null;
      if (!['file:', 'http:', 'https:'].includes(u.protocol)) return null;
      return u.href;
    } catch (_) { return null; }
  };
  const read = (key, fallback) => {
    try { return JSON.parse(localStorage.getItem(key)) ?? fallback; } catch (_) { return fallback; }
  };
  let storageFailed = false;
  const write = (key, value) => {
    try { localStorage.setItem(key, JSON.stringify(value)); return true; }
    catch (_) { storageFailed = true; return false; }
  };
  const currentUrl = new URL(location.href); currentUrl.hash = '';
  const embedded = currentUrl.searchParams.get('exam-embed') === '1';
  currentUrl.searchParams.delete('exam-embed');
  const storedRecent = read(RECENT_KEY, []);
  const recent = Array.isArray(storedRecent) ? storedRecent : [];
  const previous = recent.find(item => item && item.url === currentUrl.href);
  const rawSettings = read(SETTINGS_KEY, {});
  const settings = {
    fontSize: clamp(Number(rawSettings?.fontSize) || 19, 16, 26),
    width: [760, 920, 1120].includes(Number(rawSettings?.width)) ? Number(rawSettings.width) : 920,
    svgZoom: ['fit', '100', '125', '150'].includes(rawSettings?.svgZoom) ? rawSettings.svgZoom : 'fit'
  };
  const applyImageRedraws = () => {
    if (isSvg || !Array.isArray(config.imageRedraws)) return;
    const figures = Array.from(main.querySelectorAll('figure img[src]'));
    for (const item of config.imageRedraws) {
      if (!item || typeof item.id !== 'string' || typeof item.alt !== 'string' ||
          typeof item.originalHref !== 'string' || typeof item.replacementHref !== 'string') continue;
      const originalUrl = safeUrl(item.originalHref);
      const replacementUrl = safeUrl(item.replacementHref);
      if (!originalUrl || !replacementUrl || originalUrl === replacementUrl) continue;
      for (const image of figures) {
        // Compare full resolved URLs, including query and fragment, to avoid
        // replacing a similarly named image or a formula outside a figure.
        if (image.src !== originalUrl || image.dataset.readerRedrawApplied === '1' || image.closest('picture')) continue;
        image.dataset.readerRedrawApplied = '1';
        // Keep the original image node intact. A separate image lets loading
        // finish after a toggle without an old event changing the chosen view.
        const redraw = image.cloneNode(false);
        redraw.classList.add('reader-redraw-image');
        redraw.removeAttribute('id');
        redraw.removeAttribute('data-reader-redraw-applied');
        redraw.removeAttribute('src');
        redraw.removeAttribute('srcset');
        redraw.removeAttribute('sizes');
        redraw.loading = 'eager';
        redraw.alt = item.alt;
        redraw.hidden = true;
        const control = document.createElement('span');
        control.className = 'reader-redraw-control';
        control.dataset.redrawId = item.id;
        const label = document.createElement('span');
        label.className = 'reader-redraw-label';
        const toggle = document.createElement('button');
        toggle.className = 'reader-redraw-toggle';
        toggle.type = 'button';
        control.append(label, toggle);
        image.insertAdjacentElement('afterend', redraw);
        redraw.insertAdjacentElement('afterend', control);
        let wantRedraw = true, ready = false, failed = false;
        const showOriginal = () => {
          wantRedraw = false;
          image.hidden = false;
          redraw.hidden = true;
          label.textContent = '原图';
          toggle.textContent = '查看重绘图';
        };
        const showRedraw = () => {
          if (failed) return;
          wantRedraw = true;
          image.hidden = ready;
          redraw.hidden = !ready;
          label.textContent = ready ? '重绘图' : '重绘图加载中';
          toggle.textContent = '查看原图';
        };
        redraw.addEventListener('load', () => {
          if (failed) return;
          ready = true;
          if (wantRedraw) showRedraw();
        });
        redraw.addEventListener('error', () => {
          if (failed) return;
          failed = true;
          showOriginal();
          label.textContent = '重绘图加载失败，已显示原图';
          toggle.hidden = true;
        });
        toggle.addEventListener('click', () => wantRedraw ? showOriginal() : showRedraw());
        showRedraw();
        redraw.src = replacementUrl;
      }
    }
  };
  applyImageRedraws();
  // Embedded readers contain exam material only: no nested toolbar, history writes,
  // resume action, or comparison frames. No access to a child document is needed.
  if (embedded) {
    document.body.classList.add('exam-reader', 'reader-embed', isSvg ? 'reader-svg' : 'reader-reflow');
    document.body.style.setProperty('--reader-font-size', `${settings.fontSize}px`);
    document.body.style.setProperty('--reader-width', `${settings.width}px`);
    return;
  }
  let comparing = false, singleScroll = 0, comparison = null;
  const el = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  };
  const button = (text, action, className = '') => {
    const node = el('button', `reader-button ${className}`, text);
    node.type = 'button'; node.addEventListener('click', action); return node;
  };
  const link = (text, href, className = '') => {
    const url = typeof href === 'string' && href ? safeUrl(href) : null;
    if (!url) return null;
    const node = el('a', className, text); node.href = url; return node;
  };
  const append = (parent, ...nodes) => nodes.forEach(node => { if (node) parent.append(node); });
  const originalHeader = document.querySelector('body > header');
  const toolbar = el('div', 'reader-toolbar');
  toolbar.setAttribute('role', 'region'); toolbar.setAttribute('aria-label', '试卷阅读工具');
  const top = el('div', 'reader-top');
  const identity = el('div', 'reader-identity');
  const breadcrumbs = el('nav', 'reader-breadcrumbs'); breadcrumbs.setAttribute('aria-label', '当前位置');
  append(breadcrumbs, link('真题库', config.libraryHref), el('span', 'reader-divider', '/'), link(config.categoryLabel || '科目目录', config.categoryHref));
  const title = el('div', 'reader-title', config.title || document.title);
  title.title = title.textContent;
  append(identity, breadcrumbs, title);
  const versions = el('nav', 'reader-versions'); versions.setAttribute('aria-label', '阅读版本');
  const active = el('button', 'reader-version reader-version-current', isSvg ? 'SVG 原版' : 'LaTeX 重排'); active.type = 'button'; active.setAttribute('aria-current', 'page'); active.addEventListener('click', () => exitComparison());
  const alternative = link(config.alternateLabel || (isSvg ? 'LaTeX 重排' : 'SVG 原版'), config.alternateHref, 'reader-version');
  const compareButton = alternative ? el('button', 'reader-version', '并排对比') : null;
  if (compareButton) {
    compareButton.type = 'button'; compareButton.setAttribute('aria-pressed', 'false');
    compareButton.addEventListener('click', () => comparing ? exitComparison() : enterComparison());
  }
  append(versions, ...(isSvg ? [active, alternative] : [alternative, active]), compareButton);
  append(top, identity, versions);
  const controls = el('div', 'reader-controls');
  const tocLabel = el('label', 'reader-toc-label');
  tocLabel.append(el('span', 'reader-control-label', isSvg ? '页码' : '目录'));
  const toc = el('select', 'reader-toc'); toc.setAttribute('aria-label', isSvg ? '跳转到试卷页面' : '跳转到章节或题目');
  const targets = isSvg ? Array.from(main.querySelectorAll('.page-wrap')) : Array.from(main.querySelectorAll('h2, h3, .question'));
  const chosen = [];
  targets.forEach((node, index) => {
    // Avoid nested question/heading duplicates and invisible source-code copies.
    if (chosen.some(item => item.node.contains(node))) return;
    let text = isSvg ? `第 ${index + 1} 页` : node.textContent.replace(/\s+/g, ' ').trim();
    if (!text) return;
    if (!node.id) node.id = `reader-anchor-${index + 1}`;
    chosen.push({node, text});
    const option = el('option', '', text.length > 64 ? `${text.slice(0, 64)}…` : text);
    option.value = String(chosen.length - 1); toc.append(option);
  });
  if (!chosen.length) { tocLabel.hidden = true; }
  else {
    toc.addEventListener('change', () => jump(chosen[Number(toc.value)]?.node));
    tocLabel.append(toc);
  }
  const progressText = el('span', 'reader-progress-text', '0%'); progressText.setAttribute('aria-label', '阅读进度');
  const settingsDetails = el('details', 'reader-settings');
  const settingsSummary = el('summary', 'reader-button', '阅读设置');
  const panel = el('div', 'reader-settings-panel');
  const status = el('p', 'reader-storage-status', '字号与宽度会保存在本机。');
  status.setAttribute('role', 'status');
  const saveSettings = () => {
    write(SETTINGS_KEY, {...(rawSettings && typeof rawSettings === 'object' && !Array.isArray(rawSettings) ? rawSettings : {}), ...settings});
    if (storageFailed) status.textContent = '此窗口不允许保存设置；本次阅读仍可调整。';
  };
  const applySettings = () => {
    document.body.style.setProperty('--reader-font-size', `${settings.fontSize}px`);
    document.body.style.setProperty('--reader-width', `${settings.width}px`);
    document.body.style.setProperty('--reader-svg-width', `${1000 * (Number(settings.svgZoom) || 100) / 100}px`);
    document.body.classList.toggle('reader-zoomed', isSvg && settings.svgZoom !== 'fit');
  };
  if (isSvg) {
    const label = el('label', 'reader-setting'); label.append(el('span', '', '页面缩放'));
    const zoom = el('select'); zoom.setAttribute('aria-label', '原卷缩放');
    [['fit', '适合窗口'], ['100', '100%'], ['125', '125%'], ['150', '150%']].forEach(([value, text]) => {
      const o = el('option', '', text); o.value = value; zoom.append(o);
    });
    zoom.value = settings.svgZoom;
    zoom.addEventListener('change', () => { settings.svgZoom = zoom.value; applySettings(); saveSettings(); });
    label.append(zoom); panel.append(label);
    panel.append(el('p', 'reader-setting-hint', '放大后可在试卷区域左右滚动，原卷比例保持不变。'));
  } else {
    const fontRow = el('div', 'reader-setting'); fontRow.append(el('span', '', '正文字号'));
    const fontGroup = el('div', 'reader-stepper');
    const sizeOutput = el('output', '', `${settings.fontSize}px`); sizeOutput.setAttribute('aria-live', 'polite');
    let less, more;
    const changeSize = amount => {
      settings.fontSize = clamp(settings.fontSize + amount, 16, 26);
      sizeOutput.textContent = `${settings.fontSize}px`; less.disabled = settings.fontSize <= 16; more.disabled = settings.fontSize >= 26;
      applySettings(); saveSettings();
    };
    less = button('减小', () => changeSize(-1)); more = button('增大', () => changeSize(1));
    less.disabled = settings.fontSize <= 16; more.disabled = settings.fontSize >= 26;
    append(fontGroup, less, sizeOutput, more); fontRow.append(fontGroup); panel.append(fontRow);
    const widthLabel = el('label', 'reader-setting'); widthLabel.append(el('span', '', '阅读宽度'));
    const width = el('select'); width.setAttribute('aria-label', '阅读宽度');
    [[760, '紧凑'], [920, '标准'], [1120, '宽幅']].forEach(([value, text]) => { const o = el('option', '', text); o.value = String(value); width.append(o); });
    width.value = String(settings.width);
    width.addEventListener('change', () => { settings.width = Number(width.value); applySettings(); saveSettings(); });
    widthLabel.append(width); panel.append(widthLabel);
  }
  const focus = button('专注阅读', () => {
    const enabled = document.body.classList.toggle('reader-focus');
    focus.setAttribute('aria-pressed', String(enabled)); focus.textContent = enabled ? '退出专注' : '专注阅读';
  });
  focus.setAttribute('aria-pressed', 'false');
  append(panel, status); append(settingsDetails, settingsSummary, panel);
  append(controls, tocLabel, progressText, settingsDetails, focus, button('回到开头', () => { window.scrollTo({top: 0, behavior: 'auto'}); }));
  const progress = el('div', 'reader-progress'); progress.setAttribute('role', 'progressbar'); progress.setAttribute('aria-label', '阅读进度'); progress.setAttribute('aria-valuemin', '0'); progress.setAttribute('aria-valuemax', '100');
  const progressFill = el('div', 'reader-progress-fill'); progress.append(progressFill);
  append(toolbar, top, controls, progress);
  const skip = el('a', 'reader-skip', '跳到试卷正文');
  if (!main.id) main.id = 'reader-paper';
  skip.href = `#${main.id}`;
  main.setAttribute('tabindex', '-1');
  document.body.prepend(skip, toolbar);
  document.body.classList.add('exam-reader', isSvg ? 'reader-svg' : 'reader-reflow');
  if (originalHeader) {
    originalHeader.classList.add('reader-source-header');
    const heading = originalHeader.querySelector('h1'); if (heading) heading.classList.add('reader-original-title');
    const first = originalHeader.firstElementChild; if (first?.tagName === 'A') first.classList.add('reader-original-back');
  }
  applySettings();
  const announce = el('div', 'reader-announcement'); announce.setAttribute('role', 'status'); document.body.append(announce);
  let toastTimer;
  const announceText = message => { announce.textContent = message; announce.classList.add('reader-announcement-visible'); clearTimeout(toastTimer); toastTimer = setTimeout(() => announce.classList.remove('reader-announcement-visible'), 3500); };
  function jump(node) {
    if (!node) return;
    const top = window.scrollY + node.getBoundingClientRect().top - toolbar.getBoundingClientRect().height - 22;
    window.scrollTo({top: Math.max(0, top), behavior: 'auto'});
    node.setAttribute('tabindex', '-1'); node.focus({preventScroll: true});
  }
  const contentRange = () => {
    const top = window.scrollY + main.getBoundingClientRect().top;
    return {start: Math.max(0, top - toolbar.getBoundingClientRect().height), length: Math.max(1, main.getBoundingClientRect().height - window.innerHeight + toolbar.getBoundingClientRect().height)};
  };
  let lastProgress = 0, scrollTick = false, saveTimer;
  const saveRecent = () => {
    if (comparing) return;
    const data = read(RECENT_KEY, []);
    const records = Array.isArray(data) ? data.filter(item => item && typeof item.url === 'string' && safeUrl(item.url) && item.url !== currentUrl.href) : [];
    records.unshift({url: currentUrl.href, title: config.title || document.title, category: config.category, categoryLabel: config.categoryLabel, mode: config.mode, progress: lastProgress, scrollY: Math.round(window.scrollY), updatedAt: Date.now()});
    write(RECENT_KEY, records.slice(0, 20));
  };
  const updateProgress = () => {
    scrollTick = false;
    if (comparing) return;
    const range = contentRange();
    lastProgress = clamp((window.scrollY - range.start) / range.length, 0, 1);
    const percent = Math.round(lastProgress * 100);
    progressFill.style.width = `${percent}%`; progressText.textContent = `${percent}%`; progress.setAttribute('aria-valuenow', String(percent));
    let current = 0;
    const threshold = toolbar.getBoundingClientRect().height + 60;
    chosen.forEach((item, i) => { if (item.node.getBoundingClientRect().top <= threshold) current = i; });
    if (document.activeElement !== toc && chosen.length) toc.value = String(current);
    clearTimeout(saveTimer); saveTimer = setTimeout(saveRecent, 800);
  };
  window.addEventListener('scroll', () => { if (!scrollTick) { scrollTick = true; requestAnimationFrame(updateProgress); } }, {passive: true});
  window.addEventListener('resize', () => { updateProgress(); sizeComparison(); }, {passive: true});
  window.addEventListener('pagehide', saveRecent);
  document.addEventListener('visibilitychange', () => { if (document.hidden) saveRecent(); });
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && settingsDetails.open) { settingsDetails.open = false; settingsSummary.focus(); }
    else if (event.key === 'Escape' && comparing) exitComparison();
  });
  document.addEventListener('click', event => { if (settingsDetails.open && !settingsDetails.contains(event.target)) settingsDetails.open = false; });
  function sizeComparison() {
    if (comparing) document.body.style.setProperty('--reader-toolbar-height', `${Math.ceil(toolbar.getBoundingClientRect().height)}px`);
  }
  function createComparisonPane(label, url) {
    const pane = el('section', 'reader-compare-pane'); pane.setAttribute('aria-label', label);
    const bar = el('div', 'reader-compare-pane-bar');
    const heading = el('h2', '', label);
    const separate = link('单独打开', url, 'reader-compare-open');
    separate.target = '_blank'; separate.rel = 'noopener'; separate.setAttribute('aria-label', `在新窗口单独打开${label}`);
    append(bar, heading, separate);
    const frameUrl = new URL(url); frameUrl.hash = ''; frameUrl.searchParams.set('exam-embed', '1');
    const frame = el('iframe', 'reader-compare-frame');
    frame.title = `${config.title || document.title} · ${label}`;
    frame.src = frameUrl.href;
    const hint = el('p', 'reader-compare-hint', '独立滚动 · 若此处未显示，可单独打开此版本。');
    frame.addEventListener('error', () => { hint.textContent = '此窗口未能载入本地页面，请使用“单独打开”。'; });
    append(pane, bar, frame, hint); return pane;
  }
  function enterComparison() {
    if (comparing || !alternative) return;
    updateProgress(); saveRecent(); clearTimeout(saveTimer);
    singleScroll = window.scrollY; settingsDetails.open = false; comparing = true;
    if (!comparison) {
      comparison = el('section', 'reader-comparison'); comparison.setAttribute('aria-label', '原版与重排版并排对比');
      const overview = el('div', 'reader-compare-overview');
      append(overview, el('p', '', '宽屏左右对照，窄屏上下阅读；两版独立滚动。'), button('退出对比', () => exitComparison()));
      const panes = el('div', 'reader-compare-panes');
      const svgUrl = isSvg ? currentUrl.href : alternative.href;
      const reflowUrl = isSvg ? alternative.href : currentUrl.href;
      append(panes, createComparisonPane('SVG 原版', svgUrl), createComparisonPane('LaTeX 重排', reflowUrl));
      append(comparison, overview, panes); toolbar.after(comparison);
    }
    comparison.hidden = false;
    document.body.classList.add('reader-comparing');
    active.classList.remove('reader-version-current'); active.removeAttribute('aria-current');
    compareButton.classList.add('reader-version-current'); compareButton.setAttribute('aria-pressed', 'true');
    sizeComparison(); window.scrollTo({top: 0, behavior: 'auto'});
    comparison.querySelector('button').focus({preventScroll: true});
  }
  function exitComparison() {
    if (!comparing) return;
    comparing = false; comparison.hidden = true; document.body.classList.remove('reader-comparing');
    active.classList.add('reader-version-current'); active.setAttribute('aria-current', 'page');
    compareButton.classList.remove('reader-version-current'); compareButton.setAttribute('aria-pressed', 'false');
    window.scrollTo({top: singleScroll, behavior: 'auto'}); updateProgress();
    active.focus({preventScroll: true});
  }
  // A newly opened paper always starts normally. Resume is an explicit catalog action.
  const ready = () => {
    if (location.hash === '#resume' && previous) {
      const range = contentRange();
      const target = typeof previous.progress === 'number' && Number.isFinite(previous.progress) ? range.start + clamp(previous.progress, 0, 1) * range.length : Math.max(0, Number(previous.scrollY) || 0);
      window.scrollTo({top: target, behavior: 'auto'});
      announceText('已回到上次阅读位置');
      try { history.replaceState(null, '', currentUrl.href); } catch (_) { /* file URL history can be restricted */ }
    } else if (location.hash && location.hash !== '#resume') {
      try { const target = document.getElementById(decodeURIComponent(location.hash.slice(1))); if (target && main.contains(target)) jump(target); } catch (_) { /* malformed external fragment */ }
    }
    updateProgress();
  };
  if (document.readyState === 'complete') ready(); else window.addEventListener('load', ready, {once: true});
})();
