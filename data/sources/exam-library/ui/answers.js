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
  const richAnswer = async answer => {
    if (!answer.sourceQuestionIds?.length || !answer.sourceBlocks?.length) return null;
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
    for (const id of answer.sourceBlocks) {
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

  const visible = node => node.isConnected && !node.closest('[hidden]') &&
    !node.matches('.tex-source') && getComputedStyle(node).display !== 'none';
  const render = () => {
    config.structuredAnswers.forEach((item, index) => {
      const anchor = candidates[index].filter(visible).at(-1);
      if (!anchor || !item.answer) return;
      const position = anchor.closest('.reader-listening-question') || anchor;
      const details = document.createElement('details');
      details.className = 'exam-answer-panel';
      const summary = document.createElement('summary');
      summary.textContent = '点击查看答案';
      details.append(summary);
      const answer = item.answer;
      if (answer.status === 'explicit') {
        let count = 0;
        for (const [key, label] of labels) {
          if (!answer[key]) continue;
          const field = document.createElement('div');
          field.className = 'exam-answer-field';
          const heading = document.createElement('strong');
          heading.textContent = label;
          const value = document.createElement('p');
          value.textContent = answer[key];
          field.append(heading, value);
          details.append(field);
          count++;
        }
        if (!count) {
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
        summary.textContent = details.open ? '点击查看答案' : '收起答案';
      });
      let upgraded = false;
      details.addEventListener('toggle', async () => {
        if (!details.open || upgraded || answer.status !== 'explicit') return;
        try {
          const content = await richAnswer(answer);
          if (!content) return;
          const originalLabel = document.createElement('p');
          originalLabel.className = 'exam-answer-original-label';
          originalLabel.textContent = '原卷答案排版';
          const fields = [...details.querySelectorAll(':scope > .exam-answer-field')];
          if (fields.length) {
            const extracted = document.createElement('details');
            extracted.className = 'exam-answer-extracted';
            const extractedSummary = document.createElement('summary');
            extractedSummary.textContent = '查看答案字段摘录';
            extracted.append(extractedSummary, ...fields);
            details.append(originalLabel, content, extracted);
          } else {
            details.append(originalLabel, content);
          }
          window.ExamCodeHighlight?.apply(content);
          upgraded = true;
        } catch (_) { /* Keep safe text when the local source cannot load. */ }
      });
      position.after(details);
    });
  };
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', render, {once: true});
  } else {
    render();
  }
})();
