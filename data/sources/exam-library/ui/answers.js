/* Answers are embedded in the reader config so local files work offline too. */
(() => {
  'use strict';
  const main = document.querySelector('main');
  const configNode = document.getElementById('exam-reader-config');
  if (!main || !configNode || main.dataset.examAnswersInitialized) return;
  let config;
  try { config = JSON.parse(configNode.textContent); } catch (_) { return; }
  if (config.mode !== 'reflow' || !Array.isArray(config.structuredAnswers)) return;
  main.dataset.examAnswersInitialized = 'true';

  // Capture positions before reader.js rearranges choices and paragraphs.
  const pages = [...main.querySelectorAll('section[data-source-page]')];
  const blocks = pages.map(page => [...page.children]);
  const labels = [
    ['value', '标准答案'], ['solution', '解答过程'], ['explanation', '解析'],
    ['commentary', '点评'], ['knowledge', '考点知识']
  ];
  const sourceCache = new Map();
  const htmlTags = new Set(['p', 'div', 'span', 'strong', 'b', 'em', 'i', 'sup', 'sub',
    'br', 'pre', 'code', 'ul', 'ol', 'li', 'table', 'tbody', 'thead', 'tr', 'td', 'th',
    'h2', 'h3', 'figure', 'figcaption', 'img', 'mjx-container']);
  const svgTags = new Set(['svg', 'g', 'path', 'defs', 'clipPath', 'rect', 'line',
    'polygon', 'polyline', 'circle', 'ellipse', 'text', 'tspan']);
  const svgAttributes = new Set(['d', 'transform', 'fill', 'stroke', 'stroke-width',
    'viewBox', 'width', 'height', 'focusable', 'role', 'xmlns', 'data-c',
    'data-mml-node', 'x', 'y', 'cx', 'cy', 'r', 'rx', 'ry', 'points']);
  // MathJax uses SVG <text> for glyphs absent from its path font (notably
  // Chinese). Dropping its font-size makes those glyphs effectively invisible.
  const svgTextAttributes = new Set(['font-size', 'font-family', 'data-variant']);
  const sourceUrl = (href, base = location.href) => {
    if (typeof href !== 'string' || !href.trim()) return null;
    try {
      const url = new URL(href, base);
      return ['http:', 'https:', 'file:'].includes(url.protocol) &&
        url.protocol === location.protocol && url.origin === location.origin ? url : null;
    } catch (_) { return null; }
  };
  // Answer pages already contain rendered MathJax SVG and verbatim code. Build
  // fresh nodes from an allowlist; fetched markup is never assigned as HTML.
  const safeCopy = (node, base) => {
    if (node.nodeType === Node.TEXT_NODE) return document.createTextNode(node.textContent);
    if (node.nodeType !== Node.ELEMENT_NODE) return null;
    const svg = node.namespaceURI === 'http://www.w3.org/2000/svg';
    const tag = node.localName;
    if (node.matches?.('pre.tex-source, script, style, iframe, object, embed, foreignObject')) return null;
    if (!(svg ? svgTags : htmlTags).has(tag)) {
      const fragment = document.createDocumentFragment();
      for (const child of node.childNodes) {
        const safe = safeCopy(child, base);
        if (safe) fragment.append(safe);
      }
      return fragment;
    }
    const copy = svg ? document.createElementNS('http://www.w3.org/2000/svg', tag)
      : document.createElement(tag);
    if (svg) {
      for (const name of svgAttributes) {
        if (node.hasAttribute(name)) copy.setAttribute(name, node.getAttribute(name));
      }
      if (tag === 'text') {
        for (const name of svgTextAttributes) {
          const value = node.getAttribute(name);
          if (name === 'font-size' && /^\d+(?:\.\d+)?px$/.test(value || '')) {
            copy.setAttribute(name, value);
          } else if (name === 'font-family' && value === 'serif') {
            copy.setAttribute(name, value);
          } else if (name === 'data-variant' && /^[a-z-]+$/.test(value || '')) {
            copy.setAttribute(name, value);
          }
        }
      }
      const alignment = node.getAttribute('style');
      if (tag === 'svg' && /^vertical-align:\s*-?[\d.]+ex;?$/.test(alignment || '')) {
        copy.style.verticalAlign = alignment.match(/-?[\d.]+ex/)[0];
      }
    } else {
      const classes = (node.getAttribute('class') || '').split(/\s+/)
        .filter(name => ['paragraph', 'question', 'formula', 'formula-source',
          'MathJax', 'code', 'table-scroll'].includes(name));
      if (classes.length) copy.className = classes.join(' ');
      if (tag === 'mjx-container' && node.getAttribute('jax') === 'SVG') {
        copy.setAttribute('jax', 'SVG');
        if (node.getAttribute('display') === 'true') copy.setAttribute('display', 'true');
      }
      if (tag === 'span' && node.classList.contains('formula') && node.hasAttribute('data-tex')) {
        copy.setAttribute('data-tex', node.getAttribute('data-tex'));
      }
      if (tag === 'img') {
        const image = sourceUrl(node.getAttribute('src'), base);
        if (!image) return null;
        copy.setAttribute('src', image.href);
        copy.setAttribute('alt', node.getAttribute('alt') || '');
      }
    }
    for (const child of node.childNodes) {
      const safe = safeCopy(child, base);
      if (safe) copy.append(safe);
    }
    return copy;
  };
  const richAnswer = async (answer, selectedBlocks) => {
    if (!selectedBlocks.length) return null;
    const url = sourceUrl(answer.sourceHref);
    if (!url) return null;
    if (!sourceCache.has(url.href)) {
      sourceCache.set(url.href, fetch(url.href).then(response => {
        if (!response.ok) throw new Error('answer source unavailable');
        return response.text();
      }).then(markup => new DOMParser().parseFromString(markup, 'text/html'))
        .catch(error => { sourceCache.delete(url.href); throw error; }));
    }
    const source = await sourceCache.get(url.href);
    const pages = [...source.querySelectorAll('main section[data-source-page]')];
    const content = document.createElement('div');
    content.className = 'exam-answer-original';
    for (const id of selectedBlocks) {
      const match = /^b-(\d+)-(\d+)$/.exec(id);
      const block = match && pages[Number(match[1]) - 1]?.children[Number(match[2]) - 1];
      if (!block) return null;
      const copy = safeCopy(block, url.href);
      if (copy) content.append(copy);
    }
    return content.children.length ? content : null;
  };
  const resolveBlock = id => {
    const match = /^b-(\d+)-(\d+)$/.exec(id);
    return match ? blocks[Number(match[1]) - 1]?.[Number(match[2]) - 1] : null;
  };
  const candidates = config.structuredAnswers.map(item =>
    Array.isArray(item.sourceBlocks) ? item.sourceBlocks.map(resolveBlock).filter(Boolean) : []);
  const sourceOwners = new Map();
  const questionOwners = new Map();
  for (const [index, item] of config.structuredAnswers.entries()) {
    for (const id of new Set(item.answer?.sourceBlocks || [])) {
      const key = `${item.answer.sourceHref}\n${id}`;
      if (!sourceOwners.has(key)) sourceOwners.set(key, new Set());
      sourceOwners.get(key).add(index);
    }
    for (const id of new Set(item.answer?.sourceQuestionIds || [])) {
      const key = `${item.answer.sourceHref}\n${id}`;
      if (!questionOwners.has(key)) questionOwners.set(key, new Set());
      questionOwners.get(key).add(index);
    }
  }
  const exclusiveBlocks = (answer, index) => {
    // A shared answer heading or key can cover a whole section. Require both a
    // question-specific answer ID and blocks unused by every other question.
    if (!(answer.sourceQuestionIds || []).some(id =>
      questionOwners.get(`${answer.sourceHref}\n${id}`)?.size === 1)) return [];
    return (answer.sourceBlocks || []).filter(id =>
      sourceOwners.get(`${answer.sourceHref}\n${id}`)?.size === 1 &&
      sourceOwners.get(`${answer.sourceHref}\n${id}`)?.has(index));
  };

  const appendFields = (target, answer, keys = labels) => {
    let count = 0;
    for (const [key, label] of keys) {
      if (!answer[key]) continue;
      const field = document.createElement('div');
      field.className = 'exam-answer-field';
      const heading = document.createElement('strong');
      heading.textContent = label;
      const value = document.createElement('p');
      value.textContent = answer[key];
      field.append(heading, value);
      target.append(field);
      count++;
    }
    return count;
  };

  const visible = node => node.isConnected && !node.closest('[hidden]') &&
    !node.matches('.tex-source') && getComputedStyle(node).display !== 'none';
  const render = () => {
    const insertedAfter = new Map();
    config.structuredAnswers.forEach((item, index) => {
      const anchor = candidates[index].filter(visible).at(-1);
      if (!anchor || !item.answer) return;
      const position = anchor.closest('.reader-listening-question') || anchor;
      const details = document.createElement('details');
      details.className = 'exam-answer-panel';
      if (item.questionId) details.dataset.questionId = item.questionId;
      const summary = document.createElement('summary');
      const prefix = item.number ? `第 ${item.number} 题 · ` : '';
      const updateSummary = () => {
        summary.textContent = prefix + (details.open ? '收起答案' : '点击查看答案');
      };
      updateSummary();
      details.append(summary);
      const answer = item.answer;
      if (answer.status === 'explicit') {
        const selectedBlocks = answer.sourceQuestionIds?.length && sourceUrl(answer.sourceHref)
          ? exclusiveBlocks(answer, index) : [];
        if (selectedBlocks.length) {
          appendFields(details, answer, labels.slice(0, 1));
          const loading = document.createElement('p');
          loading.className = 'exam-answer-status';
          loading.textContent = '正在读取本题原卷答案…';
          details.append(loading);
          let requested = false;
          details.addEventListener('toggle', async () => {
            if (!details.open || requested) return;
            requested = true;
            try {
              const content = await richAnswer(answer, selectedBlocks);
              if (content) {
                loading.replaceWith(content);
                window.ExamCodeHighlight?.apply(content);
                return;
              }
            } catch (_) { /* Fall back to embedded fields below. */ }
            const fallback = document.createElement('div');
            fallback.className = 'exam-answer-fallback';
            if (!appendFields(fallback, answer, labels.slice(1)) && !answer.value) {
              fallback.textContent = '此题暂无可展示的答案内容。';
            }
            loading.replaceWith(fallback);
          });
        } else if (!appendFields(details, answer)) {
          const message = document.createElement('p');
          message.textContent = '此题暂无可展示的答案内容。';
          details.append(message);
        }
      } else {
        const message = document.createElement('p');
        message.className = 'exam-answer-status';
        message.textContent = answer.status === 'ambiguous'
          ? (answer.ambiguityReason || '题号对应不明确，暂不显示答案。')
          : '此题暂无可用答案。';
        details.append(message);
      }
      summary.addEventListener('click', () => {
        // The native details element changes state after the click event.
        summary.textContent = prefix + (details.open ? '点击查看答案' : '收起答案');
      });
      details.addEventListener('toggle', updateSummary);
      // Several Part B questions share one source anchor. Repeated after()
      // insertions at that anchor would reverse their question/answer order.
      (insertedAfter.get(position) || position).after(details);
      insertedAfter.set(position, details);
    });
  };
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', render, {once: true});
  } else {
    render();
  }
})();
