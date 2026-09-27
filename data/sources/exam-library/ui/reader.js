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
  const sourcePages = () => [...main.querySelectorAll(':scope > section[data-source-page]')];
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
  const joinExtractedProse = () => {
    if (isSvg || !['cet4', 'cet6'].includes(config.category)) return;
    const blocks = sourcePages()
      .flatMap(section => [...section.children]);
    const prose = node => node?.matches('p.paragraph');
    const startsLowercase = node => /^[a-z]/.test(node.textContent.trimStart());
    const append = (target, continuation) => {
      // The extraction omitted spaces at block boundaries; restoring one also
      // keeps copied text readable after the two blocks become one paragraph.
      target.append(document.createTextNode(' '));
      while (continuation.firstChild) target.append(continuation.firstChild);
      continuation.remove();
    };
    for (let index = 0; index < blocks.length; index++) {
      const block = blocks[index];
      if (!block.isConnected || !prose(block)) continue;
      const text = block.textContent.trim();
      if (/^Directions\s*[：:]/i.test(text) && !/[.!?。．]\s*$/.test(text)) {
        let nextIndex = index + 1;
        // Long lowercase "headings" in directions are OCR line fragments,
        // not section headings. Keep real headings such as Passage One apart.
        while (blocks[nextIndex]?.isConnected && blocks[nextIndex].matches('h2.heading') &&
               startsLowercase(blocks[nextIndex]) &&
               blocks[nextIndex].textContent.trim().length >= 40 &&
               !/^(?:passage|section|part|text)\s+(?:\d+|one|two|three|four)\b/i.test(blocks[nextIndex].textContent.trim())) {
          append(block, blocks[nextIndex++]);
        }
        if (nextIndex > index + 1 && prose(blocks[nextIndex]) &&
            startsLowercase(blocks[nextIndex]) && !/[.!?。．]\s*$/.test(block.textContent)) {
          append(block, blocks[nextIndex]);
        }
      }
      // Matching passages assign every true paragraph its own A)–O) marker.
      // PDF page/line breaks may create lowercase unmarked fragments, including
      // across two section elements; those fragments belong to this paragraph.
      if (!/^[A-O][)）]\s+\S.{30}/s.test(text)) continue;
      for (let nextIndex = index + 1; prose(blocks[nextIndex]) &&
           blocks[nextIndex].isConnected && startsLowercase(blocks[nextIndex]); nextIndex++) {
        append(block, blocks[nextIndex]);
      }
    }
  };
  const restoreSourceParagraphs = targets => {
    if (isSvg || !['cet4', 'cet6'].includes(config.category)) return;
    for (const [paragraph, anchors] of targets) {
      if (!paragraph.isConnected || !paragraph.matches('p.paragraph')) continue;
      const raw = paragraph.textContent;
      let compact = '';
      const offsets = [];
      for (let index = 0; index < raw.length; index++) {
        if (!/\s/.test(raw[index])) { compact += raw[index]; offsets.push(index); }
      }
      const cuts = [];
      for (const anchor of anchors) {
        if (typeof anchor !== 'string' || anchor.length < 20) continue;
        const first = compact.indexOf(anchor);
        if (first <= 0 || compact.indexOf(anchor, first + 1) !== -1) continue;
        cuts.push(offsets[first]);
      }
      if (!cuts.length) continue;
      paragraph.classList.add('reader-source-paragraph');
      for (const offset of [...new Set(cuts)].sort((a, b) => b - a)) {
        const walker = document.createTreeWalker(paragraph, NodeFilter.SHOW_TEXT);
        let remaining = offset, point = null;
        for (let node = walker.nextNode(); node; node = walker.nextNode()) {
          if (remaining <= node.textContent.length) { point = [node, remaining]; break; }
          remaining -= node.textContent.length;
        }
        if (!point) continue;
        const range = document.createRange();
        range.setStart(...point);
        range.setEnd(paragraph, paragraph.childNodes.length);
        const next = document.createElement('p');
        next.className = paragraph.className;
        next.append(range.extractContents());
        paragraph.after(next);
      }
    }
  };
  const normalizeEnglishLayout = () => {
    if (isSvg || !['cet4', 'cet6', 'tem4', 'tem8'].includes(config.category)) return;
    for (const paragraph of main.querySelectorAll('p.paragraph')) {
      const notePattern = /\s*注意[：:]\s*此部分试题请在答题卡\s*[12]\s*上作答(?:[^。]*。)?/;
      const match = paragraph.textContent.match(notePattern);
      if (!match || !paragraph.textContent.slice(0, match.index).trim()) continue;
      const textPoint = position => {
        const walker = document.createTreeWalker(paragraph, NodeFilter.SHOW_TEXT);
        for (let node = walker.nextNode(); node; node = walker.nextNode()) {
          if (position <= node.textContent.length) return [node, position];
          position -= node.textContent.length;
        }
        return null;
      };
      const remainder = document.createElement('p');
      remainder.className = paragraph.className;
      const end = textPoint(match.index + match[0].length);
      if (!end) continue;
      const trailing = document.createRange();
      trailing.setStart(...end);
      trailing.setEnd(paragraph, paragraph.childNodes.length);
      remainder.append(trailing.extractContents());
      const start = textPoint(match.index);
      const range = document.createRange();
      range.setStart(...start);
      range.setEnd(paragraph, paragraph.childNodes.length);
      const note = document.createElement('p');
      note.className = 'reader-answer-sheet-note';
      note.append(range.extractContents());
      paragraph.after(note);
      if (remainder.textContent.trim()) note.after(remainder);
    }
    const splitAt = (paragraph, offset, className) => {
      const walker = document.createTreeWalker(paragraph, NodeFilter.SHOW_TEXT);
      let remaining = offset, point = null;
      for (let node = walker.nextNode(); node; node = walker.nextNode()) {
        if (remaining <= node.textContent.length) { point = [node, remaining]; break; }
        remaining -= node.textContent.length;
      }
      if (!point) return null;
      const range = document.createRange();
      range.setStart(...point);
      range.setEnd(paragraph, paragraph.childNodes.length);
      const next = document.createElement('p');
      next.className = className;
      next.append(range.extractContents());
      paragraph.after(next);
      return next;
    };
    // Translation instructions and the Chinese passage can share one extracted
    // PDF block. Split the display at the answer-sheet sentence, then restore
    // paragraph starts traced from the positioned SVG text layer.
    for (const paragraph of [...main.querySelectorAll('p.paragraph')]) {
      const text = paragraph.textContent;
      if (!/^\s*Directions\s*[：:]/i.test(text) || !/translat/i.test(text)) continue;
      const end = /Answer Sheet\s*2\s*\./i.exec(text);
      if (!end || !/[\u3400-\u9fff]/.test(text.slice(end.index + end[0].length))) continue;
      const body = splitAt(paragraph, end.index + end[0].length, 'paragraph reader-translation-body');
      if (!body) continue;
      paragraph.classList.add('reader-translation-directions');
      let tail = body;
      for (const anchor of config.translationParagraphStarts || []) {
        if (typeof anchor !== 'string' || !anchor) continue;
        const raw = tail.textContent;
        let normalized = '', offsets = [];
        for (let index = 0; index < raw.length; index++) {
          if (!/\s/.test(raw[index])) { normalized += raw[index]; offsets.push(index); }
        }
        const found = normalized.indexOf(anchor);
        if (found < 0 || !raw.slice(0, offsets[found]).trim()) continue;
        const next = splitAt(tail, offsets[found], 'paragraph reader-translation-body');
        if (next) tail = next;
      }
    }
    // Matching passages in the source PDF place A)–O) in a narrow label
    // column, with the prose aligned to the right on every wrapped line.
    for (const paragraph of main.querySelectorAll('p.paragraph')) {
      const first = paragraph.firstChild;
      if (!first || first.nodeType !== Node.TEXT_NODE) continue;
      const match = /^(\s*)([A-O][)）])(\s+)/.exec(first.textContent);
      if (!match) continue;
      first.textContent = match[3] + first.textContent.slice(match[0].length);
      const label = document.createElement('span');
      label.className = 'reader-lettered-label';
      label.textContent = match[1] + match[2];
      const prose = document.createElement('span');
      prose.className = 'reader-lettered-body';
      while (paragraph.firstChild) prose.append(paragraph.firstChild);
      paragraph.append(label, prose);
      paragraph.classList.add('reader-lettered-paragraph');
    }
    if (config.documentId === 'cet6:2015-12-02') {
      const caption = main.querySelector(':scope > section[data-source-page="1"] > figure + p.paragraph');
      if (caption?.textContent.trim().startsWith('We just don’t have much useful information.')) {
        caption.classList.add('reader-cartoon-followup');
      }
    }
    // PDF extraction can split one four-choice question into separate lists,
    // including at a source-page boundary. Keep the choices with their number.
    const blocks = sourcePages()
      .flatMap(section => [...section.children]);
    for (let index = 0; index < blocks.length; index++) {
      const number = blocks[index];
      if (!number.matches('p.question') || !/^\s*\d+[.．]\s*$/.test(number.textContent)) continue;
      const groups = [];
      for (let next = index + 1; blocks[next]?.matches('ul.options'); next++) groups.push(blocks[next]);
      if (!groups.length) continue;
      if (groups.length > 1) {
        const choices = groups.flatMap(group => [...group.children]);
        const labels = choices.map(choice => choice.querySelector('.option-label')?.textContent.trim());
        if (choices.length === 4 && new Set(labels).size === 4 &&
            labels.every(label => /^[ABCD]\.$/.test(label))) {
          choices.sort((a, b) => a.querySelector('.option-label').textContent.localeCompare(b.querySelector('.option-label').textContent));
          groups[0].append(...choices);
          groups[0].classList.toggle('single', groups.some(group => group.classList.contains('single')));
          groups.slice(1).forEach(group => group.remove());
        }
      }
      if (groups[0].parentElement !== number.parentElement) number.after(groups[0]);
    }
    for (const number of main.querySelectorAll('p.question')) {
      const options = number.nextElementSibling;
      if (!/^\s*\d+[.．]\s*$/.test(number.textContent) || !options?.matches('ul.options')) continue;
      const row = document.createElement('div');
      row.className = 'reader-listening-question';
      number.before(row);
      row.append(number, options);
    }
  };
  const normalizeKaoyanLayout = () => {
    if (isSvg || config.category !== 'kaoyan') return;
    const splitAt = (paragraph, offset) => {
      const walker = document.createTreeWalker(paragraph, NodeFilter.SHOW_TEXT);
      let point = null;
      for (let node = walker.nextNode(); node; node = walker.nextNode()) {
        if (offset <= node.textContent.length) { point = [node, offset]; break; }
        offset -= node.textContent.length;
      }
      if (!point) return null;
      const range = document.createRange();
      range.setStart(...point);
      range.setEnd(paragraph, paragraph.childNodes.length);
      const next = document.createElement('p');
      next.className = paragraph.className;
      next.append(range.extractContents());
      paragraph.after(next);
      return next;
    };
    // The PDF uses a period for long reading passages even when extraction
    // emitted a closing parenthesis. Match the passage text before changing
    // its marker, so answer options and unrelated lettered text stay intact.
    for (const paragraph of main.querySelectorAll('p.paragraph')) {
      const first = paragraph.firstChild;
      if (!first || first.nodeType !== Node.TEXT_NODE) continue;
      const match = /^(\s*)([A-O])([)）.．])(\s+)/.exec(first.textContent);
      if (!match) continue;
      const preview = paragraph.textContent.slice(match[0].length).replace(/\s+/g, '').toLowerCase().slice(0, 24);
      const source = (config.letteredParagraphMarkers || []).find(item =>
        item.letter === match[2] && item.preview === preview);
      if (!source || !['.', ')'].includes(source.marker)) continue;
      first.textContent = match[4] + first.textContent.slice(match[0].length);
      const label = document.createElement('span');
      label.className = 'reader-lettered-label';
      label.textContent = match[1] + match[2] + source.marker;
      const prose = document.createElement('span');
      prose.className = 'reader-lettered-body';
      while (paragraph.firstChild) prose.append(paragraph.firstChild);
      paragraph.append(label, prose);
      paragraph.classList.add('reader-lettered-paragraph');
    }
    // Writing prompts can arrive as one extracted paragraph although the
    // source email has its own box and separate greeting/signature lines.
    for (const candidate of [...main.querySelectorAll('p.paragraph')]) {
      if (!/Yours,\s*Paul\b/.test(candidate.textContent) || candidate.closest('.reader-email-box')) continue;
      let greeting = /^\s*(?:Hi|Dear)\s+Li Ming,/i.test(candidate.textContent)
        ? candidate : candidate.previousElementSibling;
      const greetingMatch = greeting?.matches('p.paragraph') &&
        /^\s*(?:Hi|Dear)\s+Li Ming,/i.exec(greeting.textContent);
      if (!greetingMatch || greeting.parentElement !== candidate.parentElement) continue;
      let body = candidate === greeting ? greeting : candidate;
      let signoff = candidate;
      if (greeting.textContent.slice(greetingMatch[0].length).trim()) {
        body = splitAt(greeting, greetingMatch[0].length);
        if (!body) continue;
        if (candidate === greeting) signoff = body;
      }
      const signoffOffset = signoff.textContent.search(/Yours,\s*Paul\b/);
      if (signoffOffset > 0) {
        signoff = splitAt(signoff, signoffOffset);
        if (!signoff) continue;
      }
      const signature = /Yours,\s*/.exec(signoff.textContent);
      if (!signature || signature.index !== 0) continue;
      const paul = splitAt(signoff, signature[0].length);
      if (!paul) continue;
      const instructionOffset = paul.textContent.search(/(?:You should write|Write your answer)\b/i);
      if (instructionOffset > 0) splitAt(paul, instructionOffset);
      const emailParts = [];
      for (let node = greeting; node; node = node.nextElementSibling) {
        emailParts.push(node);
        if (node === paul) break;
      }
      if (emailParts.at(-1) !== paul || emailParts.some(node => !node.matches('p.paragraph'))) continue;
      const box = document.createElement('div');
      box.className = 'reader-email-box';
      greeting.before(box);
      box.append(...emailParts);
      greeting.classList.add('reader-email-greeting');
      body.classList.add('reader-email-body');
      signoff.classList.add('reader-email-signoff');
      paul.classList.add('reader-email-name');
      if (config.emailSignoffRight) box.classList.add('reader-email-right-signoff');
      const instruction = box.nextElementSibling;
      if (instruction?.matches('p.paragraph') && /^(?:You should|Write your answer)/i.test(instruction.textContent.trim())) {
        const doNot = instruction.textContent.search(/\bDo not\b/i);
        if (doNot > 0) splitAt(instruction, doNot);
        instruction.classList.add('reader-email-instruction');
        if (instruction.nextElementSibling?.matches('p.paragraph') && /^\s*Do not\b/i.test(instruction.nextElementSibling.textContent)) {
          instruction.nextElementSibling.classList.add('reader-email-instruction');
        }
      }
    }
  };
  const normalizePoliticsQuestions = () => {
    if (isSvg || config.category !== 'politics' || config.kind !== 'questions') return;
    const pages = sourcePages();

    // Only a folio at the very end of its matching source page is removed.
    // The source sometimes recognizes the closing dash as a bullet.
    for (const page of pages) {
      const last = page.lastElementChild;
      if (!last?.matches('p.paragraph, .choices')) continue;
      const walker = document.createTreeWalker(last, NodeFilter.SHOW_TEXT);
      let tail = null;
      for (let node = walker.nextNode(); node; node = walker.nextNode()) {
        if (node.textContent.trim()) tail = node;
      }
      if (!tail) continue;
      const folio = /\s+-\s*(\d{1,2})\s*[-•·]\s*$/.exec(tail.textContent);
      if (folio && Number(folio[1]) === Number(page.dataset.sourcePage)) {
        tail.textContent = tail.textContent.slice(0, folio.index);
      }
    }

    const blocks = pages.flatMap(page => [...page.children]);
    let currentQuestion = null;
    for (const block of blocks) {
      const number = block.matches('p.question') && /^\s*(\d+)[.．]/.exec(block.textContent);
      if (number) currentQuestion = Number(number[1]);
      if (!block.matches('p.paragraph') || currentQuestion == null) continue;
      const marker = /^\s*第\s*(\d+)\s*题\s*[（(]\s*续\s*[）)]\s*[：:]?\s*/.exec(block.textContent);
      if (!marker || Number(marker[1]) !== currentQuestion) continue;
      const first = block.firstChild;
      if (first?.nodeType !== Node.TEXT_NODE || !first.textContent.startsWith(marker[0])) continue;
      first.textContent = first.textContent.slice(marker[0].length);
      if (!block.textContent.trim()) block.remove();
    }

    // A source-page break can divide A from B/C/D. The complete A–D set
    // belongs to the preceding question, even when the latter page differs.
    const liveBlocks = pages.flatMap(page => [...page.children]);
    for (let index = 0; index < liveBlocks.length; index++) {
      const stem = liveBlocks[index];
      if (!stem.matches('p.question')) continue;
      const groups = [];
      for (let next = index + 1; next < liveBlocks.length; next++) {
        const block = liveBlocks[next];
        if (block.matches('p.question, h2, h3')) break;
        if (block.matches('.choices')) groups.push(block);
        else if (block.matches('p.paragraph') && block.textContent.trim()) break;
      }
      if (groups.length < 2) continue;
      const choices = groups.flatMap(group => [...group.children]);
      const labels = choices.map(choice => choice.querySelector('b')?.textContent.trim());
      if (labels.join('') !== 'A.B.C.D.') continue;
      groups[0].append(...choices.slice(groups[0].children.length));
      groups.slice(1).forEach(group => group.remove());
    }

    const splitAt = (paragraph, offset) => {
      const walker = document.createTreeWalker(paragraph, NodeFilter.SHOW_TEXT);
      let point = null;
      for (let node = walker.nextNode(); node; node = walker.nextNode()) {
        if (offset <= node.textContent.length) { point = [node, offset]; break; }
        offset -= node.textContent.length;
      }
      if (!point) return null;
      const range = document.createRange();
      range.setStart(...point);
      range.setEnd(paragraph, paragraph.childNodes.length);
      const prompt = document.createElement('p');
      prompt.className = 'paragraph reader-politics-subquestion';
      prompt.append(range.extractContents());
      paragraph.after(prompt);
      return prompt;
    };
    let analysisQuestion = null;
    for (const paragraph of pages.flatMap(page => [...page.querySelectorAll(':scope > p.paragraph')])) {
      const number = paragraph.matches('.question') && /^\s*(\d+)[.．]/.exec(paragraph.textContent);
      if (number) analysisQuestion = Number(number[1]);
      if (analysisQuestion == null || analysisQuestion < 34 || analysisQuestion > 38) continue;
      const text = paragraph.textContent;
      const sourceEnd = Math.max(text.lastIndexOf('摘自'), text.lastIndexOf('摘编自'));
      const markers = [...text.matchAll(/[（(]([1-4])[）)]/g)]
        .filter(match => match.index > sourceEnd);
      if (markers.length < 2 || markers[0][1] !== '1' || markers[1][1] !== '2') continue;
      for (const match of markers.reverse()) {
        const prompt = match.index === 0 ? paragraph : splitAt(paragraph, match.index);
        if (!prompt) continue;
        prompt.classList.add('reader-politics-subquestion');
        prompt.dataset.question = String(analysisQuestion);
      }
    }

    // The original 2023 PDF reads “从二〇二〇年到二〇三五年”. Keep this
    // verified correction narrower than a general OCR punctuation rule.
    if (config.documentId === 'politics:2023-questions') {
      const question35 = [...main.querySelectorAll('p.question')]
        .find(node => /^\s*35[.．]/.test(node.textContent));
      if (question35) {
        const walker = document.createTreeWalker(question35, NodeFilter.SHOW_TEXT);
        for (let node = walker.nextNode(); node; node = walker.nextNode()) {
          node.textContent = node.textContent
            .replace('从二。二O年到二O三五年', '从二〇二〇年到二〇三五年')
            .replace('从二O三五年到本世纪中叶', '从二〇三五年到本世纪中叶');
        }
      }
    }
  };
  const normalizeMathQuestions = () => {
    if (isSvg || config.category !== 'math3' || config.kind !== 'questions') return;
    const questionProse = main.querySelectorAll('.paragraph, .math-option-content');
    for (const block of questionProse) {
      // Keep the original LaTeX/source blocks and formula DOM untouched. Only
      // the displayed punctuation in question prose follows this paper style.
      const walker = document.createTreeWalker(block, NodeFilter.SHOW_TEXT);
      for (let node = walker.nextNode(); node; node = walker.nextNode()) {
        if (node.parentElement.closest('.formula, mjx-container, .tex-source')) continue;
        node.textContent = node.textContent.replace(/。/g, '.');
      }
    }
    // The converter leaves several (I)/(II)/(III) prompts inline with the
    // stem or with each other. Split at their actual text nodes so MathJax SVG
    // and source formulas remain attached to the right subquestion.
    const marker = /（[ⅠⅡⅢⅣⅤⅥ]）/g;
    for (const paragraph of [...main.querySelectorAll('.paragraph')]) {
      const starts = [];
      const walker = document.createTreeWalker(paragraph, NodeFilter.SHOW_TEXT);
      for (let node = walker.nextNode(); node; node = walker.nextNode()) {
        if (node.parentElement.closest('.formula, mjx-container, .tex-source')) continue;
        for (const match of node.textContent.matchAll(marker)) starts.push([node, match.index]);
      }
      if (!starts.length) continue;
      for (const [node, offset] of starts.reverse()) {
        if (offset === 0 && node === paragraph.firstChild) {
          paragraph.classList.add('reader-math-subquestion');
          continue;
        }
        const range = document.createRange();
        range.setStart(node, offset);
        range.setEnd(paragraph, paragraph.childNodes.length);
        const next = document.createElement('div');
        next.className = 'paragraph reader-math-subquestion';
        next.append(range.extractContents());
        paragraph.after(next);
      }
    }
    // The source archive has both (A) and （A）. Display one consistent label,
    // while keeping each original label available on the element and in TeX.
    for (const option of main.querySelectorAll('.math-option')) {
      const label = option.querySelector('.math-option-label');
      const content = option.querySelector('.math-option-content');
      if (!label || !content) continue;
      const sourceLabel = label.textContent.trim();
      const match = /^[（(]?\s*([A-D])\s*[）).．]?$/i.exec(sourceLabel);
      if (match) {
        if (!label.dataset.sourceLabel) label.dataset.sourceLabel = sourceLabel;
        label.textContent = `${match[1].toUpperCase()}.`;
      }
      const leaves = [];
      const collect = node => {
        if (node.nodeType === Node.TEXT_NODE) {
          if (node.textContent.trim()) leaves.push(node);
        } else if (node.nodeType === Node.ELEMENT_NODE) {
          if (node.matches('.formula, mjx-container')) { leaves.push(null); return; }
          for (const child of node.childNodes) collect(child);
        }
      };
      collect(content);
      const last = leaves.at(-1);
      if (last) last.textContent = last.textContent.replace(/[。.](?=\s*$)/, '');
    }
    // Page extraction sometimes emits A/B and C/D as separate grids. The
    // question number, rather than PDF page boundaries, defines one set.
    const sequence = [...main.querySelectorAll('.paragraph.question, .math-options')];
    for (let index = 0; index < sequence.length; index++) {
      if (!sequence[index].matches('.paragraph.question')) continue;
      const number = /^\s*（(\d+)）/.exec(sequence[index].textContent);
      const groups = [];
      const continuations = [];
      for (let next = index + 1; next < sequence.length; next++) {
        if (sequence[next].matches('.paragraph.question')) {
          const continued = number && new RegExp(`^\\s*（${number[1]}）（续）`).test(sequence[next].textContent);
          if (continued) { continuations.push(sequence[next]); continue; }
          break;
        }
        groups.push(sequence[next]);
      }
      if (!groups.length) continue;
      if (number) groups[0].style.setProperty('--reader-math-question-indent',
        `${2 + number[1].length * .6}em`);
      const choices = groups.flatMap(group => [...group.querySelectorAll(':scope > .math-option')]);
      const labels = choices.map(choice => choice.querySelector('.math-option-label')?.textContent.trim());
      if (choices.length !== 4 || labels.join('') !== 'A.B.C.D.') continue;
      groups[0].append(...choices);
      groups.slice(1).forEach(group => group.remove());
      continuations.forEach(node => node.classList.add('reader-math-continuation'));
    }
    const visibleWidth = option => {
      const content = option.querySelector('.math-option-content');
      if (!content) return Infinity;
      let ex = 3; // A. and its gap
      const walker = document.createTreeWalker(content, NodeFilter.SHOW_TEXT);
      for (let node = walker.nextNode(); node; node = walker.nextNode()) {
        if (node.parentElement.closest('.formula, mjx-container')) continue;
        for (const char of node.textContent.trim()) {
          ex += /[\u3400-\u9fff，；：？！]/.test(char) ? 2 : /\s/.test(char) ? .35 : 1;
        }
      }
      for (const svg of content.querySelectorAll('.formula svg[width]')) {
        ex += Number.parseFloat(svg.getAttribute('width')) || 0;
      }
      return ex;
    };
    for (const group of main.querySelectorAll('.math-options')) {
      const choices = [...group.querySelectorAll(':scope > .math-option')];
      group.classList.add('reader-math-two-column');
      if (choices.length === 4 && choices.every(choice => visibleWidth(choice) <= 19)) {
        group.classList.add('reader-math-four-column');
      }
    }
  };
  const layoutCompactChoices = () => {
    if (isSvg) return;
    for (const row of main.querySelectorAll('.choice-row')) {
      const cells = [...row.children];
      if (cells.length !== 5 || !cells[0].matches('.choice-number') ||
          !cells.slice(1).every(cell => cell.matches('.choice-item'))) continue;
      const choices = cells.slice(1).map(cell => cell.textContent.replace(/\s+/g, ' ').trim());
      // Four short alternatives can share a row. Longer prose keeps the
      // source's two-column layout so it remains readable without scrolling.
      if (choices.every((choice, index) =>
        choice.startsWith(`${'ABCD'[index]}.`) && choice.length <= 18)) {
        row.classList.add('reader-four-column');
      }
    }
  };
  const sizeFigures = () => {
    if (isSvg) return;
    for (const image of main.querySelectorAll('figure > img[src]')) {
      if (image.classList.contains('reader-figure-image') || image.classList.contains('inline-glyph') ||
          image.closest('.formula, mjx-container, .source-line')) continue;
      const figure = image.parentElement;
      image.classList.add('reader-figure-image');
      const setWidth = () => {
        const width = image.naturalWidth, height = image.naturalHeight;
        if (!width || !height) return;
        // Normalize standalone diagrams by readable on-page size, not just
        // their source pixel count. Tiny source figures can be vectors too.
        // Keep the original and its redraw at the same width when toggled.
        const isVector = /\.svg(?:[?#]|$)/i.test(image.src);
        const readableFloor = isVector ? 280 : width * height >= 20000 ? 360 : 240;
        const target = Math.round(Math.min(600, Math.max(readableFloor, width * 1.5), 560 * width / height));
        figure.style.setProperty('--reader-figure-width', `${target}px`);
        figure.classList.add('reader-sized-figure');
      };
      image.addEventListener('load', setWidth);
      if (image.complete) setWidth();
    }
  };
  const applyImageRedraws = () => {
    if (isSvg || !Array.isArray(config.imageRedraws)) return;
    const figures = Array.from(main.querySelectorAll('figure > img.reader-figure-image[src]'));
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
        // Lazy originals must still load so the shared width can be measured.
        image.loading = 'eager';
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
  // Capture source targets before layout cleanup inserts/moves DOM nodes.
  // Source block indexes describe the original reflow HTML, not the enhanced DOM.
  const structuredTargets = [];
  if (!isSvg && Array.isArray(config.structuredToc)) {
    const pages = sourcePages();
    for (const entry of config.structuredToc) {
      const node = pages[entry.pageIndex - 1]?.children[entry.blockIndex - 1];
      if (node) structuredTargets.push({node, label: entry.label, level: entry.level || 0});
    }
  }
  const sourceParagraphTargets = new Map();
  if (!isSvg && Array.isArray(config.readingParagraphStarts)) {
    const pages = sourcePages();
    for (const entry of config.readingParagraphStarts) {
      const node = pages[entry.reflowPageIndex - 1]?.children[entry.reflowBlockIndex - 1];
      if (!node?.matches('p.paragraph')) continue;
      if (!sourceParagraphTargets.has(node)) sourceParagraphTargets.set(node, []);
      sourceParagraphTargets.get(node).push(entry.anchor);
    }
  }
  joinExtractedProse();
  restoreSourceParagraphs(sourceParagraphTargets);
  normalizeEnglishLayout();
  normalizeKaoyanLayout();
  normalizePoliticsQuestions();
  normalizeMathQuestions();
  layoutCompactChoices();
  sizeFigures();
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
  const chosen = [];
  const addTocTarget = (node, text, level = 0) => {
    if (!node || !text || chosen.some(item => item.node === node)) return;
    if (!node.id) node.id = `reader-anchor-${chosen.length + 1}`;
    chosen.push({node, text});
    const visible = `${'　'.repeat(Math.min(3, level))}${text.length > 64 ? `${text.slice(0, 64)}…` : text}`;
    const option = el('option', '', visible);
    option.value = String(chosen.length - 1); toc.append(option);
  };
  for (const entry of structuredTargets) addTocTarget(entry.node, entry.label, entry.level);
  if (!chosen.length) {
    const targets = isSvg ? Array.from(main.querySelectorAll('.page-wrap')) : Array.from(main.querySelectorAll('h2, h3, .question'));
    targets.forEach((node, index) => {
      if (chosen.some(item => item.node.contains(node))) return;
      const text = isSvg ? `第 ${index + 1} 页` : node.textContent.replace(/\s+/g, ' ').trim();
      addTocTarget(node, text);
    });
  }
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
