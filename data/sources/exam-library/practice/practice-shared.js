(() => {
  'use strict';
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

  function localImageUrl(src, base = document.baseURI) {
    if (typeof src !== 'string' || !src.trim()) return null;
    try {
      const url = new URL(src, new URL(base, location.origin));
      if (url.origin !== location.origin || !/^https?:$/.test(url.protocol) ||
          url.pathname.startsWith('/api/')) return null;
      return url.pathname + url.search;
    } catch (_) { return null; }
  }

  function renderMath(node) {
    if (!/\\(?:\(|\[)/.test(node.textContent)) return;
    mathQueue = mathQueue.catch(() => {}).then(async () => {
      const math = window.MathJax;
      if (!math) return;
      await math.startup?.promise;
      if (math.typesetPromise && node.isConnected) await math.typesetPromise([node]);
    }).catch(() => { /* Keep source TeX readable when MathJax is unavailable. */ });
  }

  function styledParagraphs(parts) {
    if (!Array.isArray(parts) || !parts.length) return null;
    const group = element('div', 'styled-paragraphs');
    for (const part of parts) {
      if (!part || typeof part.text !== 'string' || !part.text.trim()) continue;
      const kind = part.kind === 'material_label' ? 'material-label' :
        part.kind === 'material_source' ? 'material-source' : 'paragraph';
      group.append(element('p', `styled-paragraph ${kind}`, part.text));
    }
    return group.childNodes.length ? group : null;
  }

  function renderStem(container, question) {
    container.replaceChildren();
    const styled = styledParagraphs(question.stemParagraphs);
    if (styled) container.append(styled);
    else container.textContent = valueText(question.stem) || '题干暂缺，请以原卷核对。';
  }

  function optionImage(option) {
    const image = option.image;
    const src = localImageUrl(image?.src);
    const crop = image?.crop;
    if (!src || !crop || !['x', 'y', 'width', 'height', 'sourceWidth', 'sourceHeight']
        .every(key => Number.isInteger(crop[key])) ||
        crop.x < 0 || crop.y < 0 || crop.width <= 0 || crop.height <= 0 ||
        crop.x + crop.width > crop.sourceWidth || crop.y + crop.height > crop.sourceHeight) return null;
    const frame = element('span', 'option-image-frame');
    frame.style.width = `min(100%, ${crop.width * 2}px)`;
    frame.style.aspectRatio = `${crop.width} / ${crop.height}`;
    const picture = element('img', 'option-image');
    picture.alt = valueText(image.alt) || `原卷选项 ${option.label || ''} 图`;
    picture.loading = 'lazy';
    picture.decoding = 'async';
    picture.style.width = `${crop.sourceWidth / crop.width * 100}%`;
    picture.style.height = `${crop.sourceHeight / crop.height * 100}%`;
    picture.style.left = `${-crop.x / crop.width * 100}%`;
    picture.style.top = `${-crop.y / crop.height * 100}%`;
    picture.src = src;
    const failure = element('span', 'image-error', '选项图无法加载，请查看原始选项图。');
    failure.hidden = true;
    picture.addEventListener('error', () => { picture.hidden = true; failure.hidden = false; });
    frame.append(picture, failure);
    return frame;
  }

  function renderOptions(container, question, name = 'choice', selected = new Set()) {
    container.replaceChildren();
    const multiple = /multi|multiple/i.test(question.questionType || '');
    for (const [index, option] of (question.options || []).entries()) {
      const label = element('label', 'option');
      label.dataset.optionId = String(option.id);
      const input = element('input');
      input.type = multiple ? 'checkbox' : 'radio';
      input.name = name;
      input.value = String(option.id);
      input.checked = selected.has(String(option.id));
      const body = element('span', 'option-body');
      if (valueText(option.text)) body.append(element('span', 'option-text', valueText(option.text)));
      const image = optionImage(option);
      if (image) body.append(image);
      label.append(input, element('span', 'option-label',
        option.displayLabel || option.label || option.sourceLabel || `${String.fromCharCode(65 + index)}.`), body);
      container.append(label);
    }
  }

  function numberedSubquestions(text) {
    const markers = [...text.matchAll(/[（(]([1-9１-９])[)）]/g)].map(match => ({
      index: match.index, length: match[0].length,
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
    if (!parts) { paragraph.textContent = text; return paragraph; }
    if (parts.prefix) paragraph.append(document.createTextNode(parts.prefix));
    for (const item of parts.items) paragraph.append(element('span', 'content-subquestion', item));
    return paragraph;
  }

  function presentationMatches(parts, text) {
    const compact = value => valueText(value).replace(/\s+/g, '');
    return compact(parts.map(part => part.text).join(' ')) === compact(text);
  }

  function sourceEmail(block) {
    const presentation = block.presentation;
    const lines = presentation?.lines;
    const roles = new Set(['greeting', 'body', 'closing', 'signature']);
    if (presentation?.version !== 1 || presentation.layoutKind !== 'email' ||
        !['single', 'start', 'middle', 'end'].includes(presentation.framePart) ||
        !Array.isArray(lines) || !lines.length || lines.some(line => !roles.has(line?.role) ||
          typeof line.text !== 'string' || !line.text.trim()) ||
        !presentationMatches(lines, block.text)) return null;
    const box = element('div', 'practice-email-box');
    box.dataset.framePart = presentation.framePart;
    for (const line of lines) box.append(element('p', `practice-email-${line.role}`, line.text));
    return box;
  }

  function sourceInstructions(block) {
    const presentation = block.presentation;
    const instructions = presentation?.instructions;
    const isInstructionLayout = presentation?.layoutKind === 'writing_instructions' ||
      (presentation?.layoutKind === 'email' && presentation.instructionsOutsideFrame);
    if (!isInstructionLayout || (presentation.version != null && presentation.version !== 1) ||
        !Array.isArray(instructions) || !instructions.length ||
        instructions.some(item => typeof item?.text !== 'string' || !item.text.trim()) ||
        !presentationMatches(instructions, block.text)) return null;
    const group = element('div', 'practice-source-instructions');
    for (const item of instructions) {
      const line = element('p', 'practice-source-instruction');
      const prefix = typeof item.strongPrefix === 'string' &&
        item.text.startsWith(item.strongPrefix) ? item.strongPrefix : '';
      if (prefix) {
        line.append(element('strong', '', prefix));
        line.append(document.createTextNode(item.text.slice(prefix.length)));
      } else line.textContent = item.text;
      group.append(line);
    }
    return group;
  }

  function renderContent(container, question, {seenBlockIds = null, imageLoading = 'eager',
    emailLayout = false, questionRoleContent = false} = {}) {
    container.replaceChildren();
    const optionFigureIds = new Set((question.options || [])
      .map(option => option.image?.sourceBlockId).filter(Boolean));
    for (const block of question.contentBlocks || []) {
      if (!block || !(['content', 'figure'].includes(block.role) ||
          (questionRoleContent && block.role === 'question'))) continue;
      if (block.role === 'question' && valueText(block.text).trim() ===
          valueText(question.stem).trim()) continue;
      if (block.role === 'figure' && seenBlockIds?.has(`${block.id}\u0000figure`)) continue;
      // A source block can carry several distinct paragraphs. Deduplicate only
      // identical content, not every item that shares its provenance ID.
      const plainText = !valueText(block.code).trim() && !(block.images || []).length;
      const blockKey = block.id && (plainText ?
        `${block.id}\u0000${valueText(block.text).trim()}` :
        `${block.id}\u0000${valueText(block.text)}\u0000${valueText(block.code)}\u0000${JSON.stringify(block.images || [])}`);
      if (seenBlockIds && blockKey && seenBlockIds.has(blockKey)) continue;
      if (seenBlockIds && blockKey) seenBlockIds.add(blockKey);
      const section = element('section', `content-block content-${block.role}`);
      const body = valueText(block.text);
      const codeText = valueText(block.code);
      const repeatedCode = codeText.trim() &&
        body.replace(/\s+/g, '') === codeText.replace(/\s+/g, '');
      if (body.trim() && !repeatedCode && block.role !== 'figure') {
        const styled = styledParagraphs(block.styledParagraphs);
        const email = emailLayout ? sourceEmail(block) : null;
        const instructions = emailLayout ? sourceInstructions(block) : null;
        const paragraphs = Array.isArray(block.paragraphs) ? block.paragraphs.filter(part =>
          typeof part === 'string' && part.trim()) : [];
        if (email) section.append(email);
        else if (instructions) section.append(instructions);
        else if (styled) section.append(styled);
        else if (paragraphs.length) {
          const group = element('div', 'content-paragraphs');
          for (const part of paragraphs) group.append(contentText(part));
          section.append(group);
        } else section.append(contentText(body));
      }
      if (codeText.trim()) {
        const pre = element('pre', 'content-code code');
        pre.append(element('code', '', codeText));
        section.append(pre);
      }
      const images = Array.isArray(block.images) ? block.images : [];
      if (block.role === 'figure' && optionFigureIds.has(block.id)) {
        const src = localImageUrl(images[0]?.src);
        if (src) {
          const link = element('a', 'source-figure-link', '查看原始四选项图 ↗');
          link.href = src; link.target = '_blank'; link.rel = 'noopener';
          section.append(link);
        }
        if (section.childNodes.length) container.append(section);
        continue;
      }
      const figure = element('figure', 'content-figure');
      for (const item of images) {
        const src = localImageUrl(item?.src);
        if (!src) continue;
        const image = element('img');
        image.alt = valueText(item.alt) || body || '题目附图';
        image.loading = imageLoading;
        image.decoding = 'async';
        const failure = element('p', 'image-error', '附图暂时无法加载，请查看原卷。');
        failure.hidden = true;
        image.addEventListener('error', () => { image.hidden = true; failure.hidden = false; });
        image.src = src;
        figure.append(image, failure);
        const redrawSrc = localImageUrl(item.redraw?.src);
        if (redrawSrc && redrawSrc !== src) {
          const redraw = element('img', 'content-redraw-image');
          redraw.alt = valueText(item.redraw.alt) || image.alt;
          redraw.loading = imageLoading;
          redraw.decoding = 'async';
          redraw.hidden = true;
          const control = element('div', 'content-redraw-control');
          const label = element('span', '', '重绘图加载中');
          const toggle = element('button', '', '查看原图');
          toggle.type = 'button';
          let ready = false;
          let showRedraw = true;
          const matchOriginalWidth = () => {
            if (image.naturalWidth > 0) redraw.style.width = `${image.naturalWidth}px`;
          };
          const update = () => {
            image.hidden = showRedraw && ready;
            redraw.hidden = !showRedraw || !ready;
            label.textContent = showRedraw ? (ready ? '重绘图' : '重绘图加载中') : '原图';
            toggle.textContent = showRedraw ? '查看原图' : '查看重绘图';
          };
          image.addEventListener('load', matchOriginalWidth);
          redraw.addEventListener('load', () => { ready = true; matchOriginalWidth(); update(); });
          redraw.addEventListener('error', () => {
            showRedraw = false; update();
            label.textContent = '重绘图加载失败，已显示原图';
            toggle.hidden = true;
          });
          toggle.addEventListener('click', () => { showRedraw = !showRedraw; update(); });
          control.append(label, toggle);
          figure.append(redraw, control);
          redraw.src = redrawSrc;
        }
      }
      if (figure.querySelector('img')) {
        if (body.trim() && block.role === 'figure') figure.append(element('figcaption', '', body));
        section.append(figure);
      } else if (body.trim() && block.role === 'figure') section.append(element('p', 'content-text', body));
      if (section.childNodes.length) container.append(section);
    }
    if (emailLayout) {
      // Some source emails span two or more adjacent blocks. Keep their
      // provenance-based line breaks, but present one printed frame.
      for (const section of [...container.children]) {
        const box = section.querySelector(':scope > .practice-email-box[data-frame-part="start"]');
        if (!box) continue;
        for (let next = section.nextElementSibling; next;) {
          const part = next.querySelector(':scope > .practice-email-box');
          if (!part || !['middle', 'end'].includes(part.dataset.framePart)) break;
          const last = part.dataset.framePart === 'end';
          box.append(...part.childNodes);
          next.remove();
          if (last) break;
          next = section.nextElementSibling;
        }
      }
    }
    container.hidden = !container.childNodes.length;
    window.ExamCodeHighlight?.apply(container);
  }

  const answerTags = new Set(['p', 'div', 'span', 'strong', 'b', 'em', 'i', 'sup', 'sub',
    'br', 'pre', 'code', 'h2', 'h3', 'ul', 'ol', 'li', 'table', 'thead', 'tbody', 'tfoot',
    'tr', 'th', 'td', 'figure', 'figcaption', 'img']);
  const answerClasses = new Set(['paragraph', 'paragraph-group', 'question', 'formula',
    'display', 'code', 'table-scroll', 'material-label', 'material-source']);

  function safeAnswerNode(node, base) {
    if (node.nodeType === Node.TEXT_NODE) return document.createTextNode(node.textContent);
    if (node.nodeType !== Node.ELEMENT_NODE) return null;
    if (node.matches('script, style, iframe, object, embed, template, form, pre.tex-source')) return null;
    const tag = node.localName;
    if (!answerTags.has(tag)) {
      const fragment = document.createDocumentFragment();
      for (const child of node.childNodes) {
        const safe = safeAnswerNode(child, base);
        if (safe) fragment.append(safe);
      }
      return fragment;
    }
    const copy = document.createElement(tag);
    const classes = (node.getAttribute('class') || '').split(/\s+/)
      .filter(name => answerClasses.has(name));
    if (classes.length) copy.className = classes.join(' ');
    if (tag === 'img') {
      const url = localImageUrl(node.getAttribute('src'), base);
      if (!url) return null;
      copy.src = url;
      copy.alt = node.getAttribute('alt') || '';
    }
    if (tag === 'th' || tag === 'td') {
      for (const name of ['rowspan', 'colspan']) {
        const value = node.getAttribute(name);
        if (/^[1-9]\d?$/.test(value || '')) copy.setAttribute(name, value);
      }
    }
    for (const child of node.childNodes) {
      const safe = safeAnswerNode(child, base);
      if (safe) copy.append(safe);
    }
    return copy;
  }

  function appendSourceAnswer(panel, answer) {
    if (answer?.status !== 'explicit' || !Array.isArray(answer.sourceContentBlocks) ||
        !answer.sourceContentBlocks.length) return false;
    const base = localImageUrl(answer.sourceBaseUrl);
    if (!base) return false;
    const content = element('div', 'answer-source');
    for (const block of answer.sourceContentBlocks) {
      if (typeof block.contentHtml !== 'string' || !block.contentHtml.trim()) continue;
      const parsed = new DOMParser().parseFromString(block.contentHtml, 'text/html');
      const wrapper = element('div', 'answer-source-block');
      for (const child of parsed.body.childNodes) {
        const safe = safeAnswerNode(child, base);
        if (safe) wrapper.append(safe);
      }
      if (wrapper.childNodes.length) content.append(wrapper);
    }
    if (!content.children.length) return false;
    panel.append(content);
    window.ExamCodeHighlight?.apply(content);
    return true;
  }

  function appendAnswerField(panel, label, value) {
    const text = valueText(value);
    if (!text.trim()) return;
    const row = element('p');
    row.append(element('strong', '', `${label}：`), document.createTextNode(text));
    panel.append(row);
  }

  function renderAnswer({panel, question, answer, options, written, reveal, redo,
    selected = new Set(), order = 'default'}) {
    panel.replaceChildren();
    const status = answer?.status || question.answerStatus || 'missing';
    const ids = Array.isArray(answer?.correctOptionIds) ? answer.correctOptionIds.map(String) : [];
    const optionIds = new Set((question.options || []).map(option => String(option.id)));
    const mapped = status === 'explicit' && ids.length > 0 && ids.every(id => optionIds.has(id));
    panel.append(element('h3', '', '参考答案'));
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
    panel.append(statusNode);
    const hasSource = appendSourceAnswer(panel, answer);
    if (hasSource && answer?.resolvedReferenceOnly) appendAnswerField(panel, '对应试卷解答', answer.solution);
    if (!hasSource) {
      appendAnswerField(panel, status === 'explicit' && order !== 'shuffle' ? '答案' : '原卷答案记录', answer?.value);
      appendAnswerField(panel, '解答', answer?.solution);
      appendAnswerField(panel, '解析', answer?.explanation);
      appendAnswerField(panel, '评注', answer?.commentary);
      appendAnswerField(panel, '知识点', answer?.knowledge);
    }
    for (const label of options.querySelectorAll('.option')) {
      const id = label.dataset.optionId;
      if (mapped && ids.includes(id)) {
        label.classList.add('is-correct');
        const original = (question.options || []).find(option => String(option.id) === id);
        const source = original?.sourceLabel || original?.label;
        const tag = order === 'shuffle' && source ? `正确答案 · 原卷 ${source}` : '正确答案';
        label.append(element('span', 'option-tag', tag));
      } else if (mapped && selected.has(id)) {
        label.classList.add('is-wrong');
        label.append(element('span', 'option-tag', '我的选择'));
      }
    }
    options.querySelectorAll('input').forEach(input => { input.disabled = true; });
    if (written) written.disabled = true;
    panel.hidden = false;
    reveal.hidden = true;
    redo.hidden = false;
    renderMath(panel);
  }

  window.ExamPracticeRender = Object.freeze({element, valueText, contextText, localImageUrl,
    renderMath, styledParagraphs, renderStem, renderOptions, renderContent, renderAnswer});
})();
