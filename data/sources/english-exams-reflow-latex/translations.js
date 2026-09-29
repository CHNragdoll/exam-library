/* Source-verified optional Chinese translations for the offline reflow reader. */
(() => {
  'use strict';
  const readable = 'p.paragraph,p.instruction,p.question,h2.heading';
  const sourceTypes = new Set(['paragraph', 'instruction', 'question', 'heading']);
  const blockText = block => {
    if (block.type === 'options' && block.items?.length === 1) {
      const item = block.items[0];
      return `${item.label}. ` + item.runs.map(run => run.text || '').join('');
    }
    return block.runs.map(run => run.text || '').join('');
  };
  const sha256 = async text => {
    const bytes = new TextEncoder().encode(text);
    const digest = await crypto.subtle.digest('SHA-256', bytes);
    return [...new Uint8Array(digest)].map(byte => byte.toString(16).padStart(2, '0')).join('');
  };
  // Structured extraction sometimes retains a PDF space before punctuation
  // that the raw reflow item does not. Keep both literal sources verified.
  const optionComparisonText = text => text.replace(/[ \t]+(?=[.,!?;:’])/g, '');

  window.addEventListener('load', () => {
    const paper = document.querySelector('main.paper[data-paper-id][data-translation-sidecar][data-source-json]');
    if (!paper || document.body.classList.contains('reader-embed')) return;
    if (paper.dataset.translationInitialized) return;
    paper.dataset.translationInitialized = 'true';
    const loadTranslations = async () => {
    let sidecar, source;
    try {
      const sidecarResponse = await fetch(new URL(paper.dataset.translationSidecar, location.href));
      if (!sidecarResponse.ok) return;
      sidecar = await sidecarResponse.json();
      if (!Array.isArray(sidecar?.paragraphs) ||
          !Array.isArray(sidecar?.options || []) ||
          ![...sidecar.paragraphs, ...(sidecar.options || [])]
            .some(record => record?.translationEligible === true &&
              typeof record.translationZh === 'string' && record.translationZh.trim())) return [];
      const sourceResponse = await fetch(new URL(paper.dataset.sourceJson, location.href));
      if (!sourceResponse.ok) return;
      source = await sourceResponse.json();
    } catch (_) { return []; }
    if (!Array.isArray(source?.pages) || !globalThis.crypto?.subtle) return [];

    const blocks = new Map();
    source.pages.forEach((page, pageIndex) => {
      page.blocks?.forEach((block, blockIndex) => {
        blocks.set(`b-${pageIndex + 1}-${blockIndex + 1}`, block);
      });
    });
    const markers = new Map();
    for (const marker of paper.querySelectorAll('.source-block-marker[data-source-block-id]')) {
      const id = marker.dataset.sourceBlockId;
      if (!markers.has(id)) markers.set(id, []);
      markers.get(id).push(marker);
    }
    const markerNodes = [...paper.querySelectorAll('.source-block-marker[data-source-block-id]')];
    const markerOrder = new Map(markerNodes
      .map((marker, index) => [marker, index]));
    // Reader layout can merge split option lists and move their <li> nodes.
    // Anchor each source item itself, so the raw block identity survives that move.
    const optionAnchors = new Map();
    for (const node of paper.querySelectorAll('[data-source-block-id][data-source-option-index]')) {
      const key = `${node.dataset.sourceBlockId}:${node.dataset.sourceOptionIndex}`;
      if (!optionAnchors.has(key)) optionAnchors.set(key, []);
      optionAnchors.get(key).push(node);
    }
    const optionAnchor = (id, block, nextNode) => {
      const match = /^b-(\d+)-(\d+)$/.exec(id);
      if (!match || block.type !== 'options' || block.items?.length !== 1) return null;
      const section = [...paper.querySelectorAll(':scope > section[data-source-page]')]
        .find(node => node.dataset.sourcePage === match[1]);
      if (!section) return null;
      const item = block.items[0];
      const candidates = [...section.children].filter(node => {
        if (!node.matches('ul.options') || node.children.length !== 1) return false;
        const choice = node.firstElementChild;
        const spans = [...choice.children];
        return choice.matches('li') && spans.length === 2 &&
          spans[0].matches('.option-label') && spans[0].textContent === `${item.label}.` &&
          spans[1].textContent === item.runs.map(run => run.text || '').join('');
      });
      if (candidates.length !== 1) return null;
      const candidate = candidates[0];
      if (!nextNode) return candidate;
      if (candidate.parentElement === nextNode.parentElement) {
        return candidate.nextElementSibling === nextNode ? candidate : null;
      }
      const nextSection = nextNode.closest('section[data-source-page]');
      if (!nextSection || candidate !== section.lastElementChild ||
          [...nextSection.children].slice(0, [...nextSection.children].indexOf(nextNode))
            .some(node => !node.matches('.notice'))) return null;
      return candidate;
    };

    const used = new Set();
    const translations = [];
    let skipped = 0;
    for (const record of sidecar.paragraphs) {
      if (record?.translationEligible !== true ||
          typeof record.translationZh !== 'string' || !record.translationZh.trim()) continue;
      const fullIds = record.reflowBlockIds;
      const prefix = `${paper.dataset.paperId}:`;
      if (!record.translationEligible || record.paragraphIndex !== 0 ||
          !Array.isArray(fullIds) || !fullIds.length ||
          !fullIds.every(id => typeof id === 'string' && id.startsWith(prefix)) ||
          record.unresolvedBlanks?.length) { skipped++; continue; }
      const ids = fullIds.map(id => id.slice(prefix.length));
      if (new Set(ids).size !== ids.length || ids.some(id => used.has(id))) { skipped++; continue; }
      const originals = ids.map(id => blocks.get(id));
      if (originals.some((block, index) => !block ||
          !(sourceTypes.has(block.type) && Array.isArray(block.runs) ||
            index === 0 && ['passage_option', 'instruction'].includes(record.kind) &&
            block.type === 'options' && block.items?.length === 1))) {
        skipped++; continue;
      }
      const actualText = originals.map(blockText).reduce((text, part) => {
        if (!text) return part;
        const joinsWithinChineseWord = /[\u3400-\u9fff]$/.test(text.trimEnd()) &&
          /^[\u3400-\u9fff]/.test(part.trimStart());
        const omitSpace = text.trimEnd().endsWith('-') ||
          joinsWithinChineseWord && record.sourceText.startsWith(text + part);
        return text + (omitSpace ? '' : ' ') + part;
      }, '');
      if (record.sourceText !== actualText ||
          record.sourceHash !== await sha256(actualText)) {
        skipped++; continue;
      }
      const optionStart = originals[0].type === 'options';
      if (ids.some((id, index) => (!optionStart || index > 0) && markers.get(id)?.length !== 1)) {
        skipped++; continue;
      }
      const continuationNodes = ids.slice(optionStart ? 1 : 0)
        .map(id => markers.get(id)[0].closest(readable));
      if (continuationNodes.some(node => !node)) { skipped++; continue; }
      const optionNode = optionStart ? optionAnchor(ids[0], originals[0], continuationNodes[0]) : null;
      if (optionStart && !optionNode) { skipped++; continue; }
      const nodes = optionStart ? [optionNode, ...continuationNodes] : continuationNodes;
      const target = nodes.at(-1);
      const markedIds = [...new Set(continuationNodes)]
        .flatMap(node => [...node.querySelectorAll('.source-block-marker[data-source-block-id]')]
          .map(marker => marker.dataset.sourceBlockId));
      const expectedMarked = ids.slice(optionStart ? 1 : 0);
      if (markedIds.length !== expectedMarked.length ||
          markedIds.some((id, index) => id !== expectedMarked[index])) { skipped++; continue; }
      const markerPositions = expectedMarked.map(id => markerOrder.get(markers.get(id)[0]));
      // Older CET scans repeat this exact Chinese running header at the start
      // of each page. It may sit between two fragments of one English paragraph.
      // Permit only that source-verified page header between cross-page markers.
      const hasUnexpectedInterveningMarker = markerPositions.some((position, index) => {
        if (!index || position === markerPositions[index - 1] + 1) return false;
        const previousPage = Number(/^b-(\d+)-/.exec(expectedMarked[index - 1])?.[1]);
        const currentPage = Number(/^b-(\d+)-/.exec(expectedMarked[index])?.[1]);
        if (currentPage !== previousPage + 1) return true;
        const headerId = `b-${currentPage}-1`;
        const between = markerNodes.slice(markerPositions[index - 1] + 1, position);
        return between.length !== 1 || between[0].dataset.sourceBlockId !== headerId ||
          blocks.get(headerId)?.type !== 'paragraph' ||
          blockText(blocks.get(headerId)) !== '全国英语六级历年真题' ||
          between[0].closest(readable)?.textContent !== '全国英语六级历年真题';
      });
      if (hasUnexpectedInterveningMarker) {
        skipped++; continue;
      }

      const translation = document.createElement('aside');
      translation.className = 'paragraph-translation';
      translation.setAttribute('lang', 'zh-CN');
      translation.hidden = true;
      const label = document.createElement('span');
      label.className = 'paragraph-translation-label';
      label.textContent = '段落译文';
      const text = document.createElement('p');
      text.textContent = record.translationZh.trim();
      translation.append(label, text);
      target.after(translation);
      ids.forEach(id => used.add(id));
      translations.push(translation);
    }
    const paragraphAttached = translations.length;
    const optionUsed = new Set();
    const optionIdsUsed = new Set();
    const pdfSourceIdsUsed = new Set();
    const pdfGroups = new Map();
    let optionSkipped = 0;
    let pdfAttached = 0;
    const queuePdfOption = async record => {
      const meta = record.pdfVerifiedSource;
      const prefix = `${paper.dataset.paperId}:`;
      const fullIds = record.reflowBlockIds;
      if (!record.translationEligible || record.paperId !== paper.dataset.paperId ||
          record.id !== record.optionId || !record.optionId?.startsWith(prefix) ||
          !record.questionId?.startsWith(prefix) ||
          !Array.isArray(fullIds) || fullIds.length !== 1 ||
          !fullIds[0].startsWith(prefix) ||
          !Array.isArray(meta?.reflowBlockIds) ||
          meta.reflowBlockIds.length !== 1 || meta.reflowBlockIds[0] !== fullIds[0] ||
          !/^[a-f0-9]{64}$/.test(sidecar.sourcePdfSha256 || '') ||
          meta.sourcePdfSha256 !== sidecar.sourcePdfSha256 ||
          typeof record.sourceText !== 'string' || !record.sourceText.trim() ||
          record.sourceHash !== await sha256(record.sourceText) ||
          optionIdsUsed.has(record.optionId) ||
          pdfSourceIdsUsed.has(meta.sourceOptionId)) return false;
      const id = fullIds[0].slice(prefix.length);
      const match = /^b-(\d+)-(\d+)$/.exec(id);
      if (!match) return false;
      const pageNumber = Number(match[1]);
      const blockNumber = Number(match[2]);
      const page = source.pages[pageNumber - 1];
      const block = page?.blocks?.[blockNumber - 1];
      if (!block || meta.pdfPage !== pageNumber) return false;
      const label = record.optionId.split(':').at(-1);
      if (!/^[A-Z]$/.test(label)) return false;
      let target;
      let groupKey;
      if (meta.anchorKind === 'figure_bank' && record.kind === 'answer_option') {
        if (!paper.dataset.paperId.startsWith('kaoyan:') ||
            record.questionId !== `${paper.dataset.paperId}:q-41-1` ||
            meta.sourceOptionId !== `${paper.dataset.paperId}:part-b:${label}` ||
            block.type !== 'figure' || !Array.isArray(block.bbox) || block.bbox.length !== 4 ||
            !block.bbox.every(Number.isFinite)) return false;
        const figureText = (page.figure_text || []).join(' ').replace(/\s+/g, ' ').trim();
        if (!figureText.includes(`${label}. ${record.sourceText.replace(/\s+/g, ' ').trim()}`)) return false;
        const section = [...paper.querySelectorAll(':scope > section[data-source-page]')]
          .find(node => node.dataset.sourcePage === String(pageNumber));
        const rawFigures = page.blocks.filter(item => item.type === 'figure');
        const figures = section?.querySelectorAll(':scope > figure');
        const figureIndex = page.blocks.slice(0, blockNumber)
          .filter(item => item.type === 'figure').length - 1;
        const stem = paper.dataset.paperId.split(':').at(-1);
        const expectedImage = `${stem}.assets/figure-${String(pageNumber).padStart(3, '0')}-${String(blockNumber - 1).padStart(3, '0')}.svg`;
        if (page.figures !== rawFigures.length || figures?.length !== rawFigures.length ||
            figureIndex < 0 ||
            figures[figureIndex]?.querySelector('img')?.getAttribute('src') !== expectedImage) return false;
        target = figures[figureIndex];
        groupKey = `figure:${id}`;
      } else if (meta.anchorKind === 'word_bank_option' &&
                 record.kind === 'word_bank_option') {
        if (meta.sourceOptionId !== record.optionId ||
            record.optionId !== `${paper.dataset.paperId}:word-bank:${label}` ||
            block.type !== 'options' ||
            !Number.isInteger(meta.reflowOptionIndex) || meta.reflowOptionIndex < 0) return false;
        const item = block.items?.[meta.reflowOptionIndex];
        if (!item || !Array.isArray(item.runs)) return false;
        const rawText = item.runs.map(run => run.text || '').join('');
        const at = rawText.indexOf(record.sourceText);
        if (at < 0 || /[A-Za-z]/.test(rawText[at - 1] || '') ||
            /[A-Za-z]/.test(rawText[at + record.sourceText.length] || '')) return false;
        const anchors = optionAnchors.get(`${id}:${meta.reflowOptionIndex}`);
        const node = anchors?.length === 1 ? anchors[0] : null;
        if (!node?.matches('li') || !node.parentElement?.matches('ul.options') ||
            node.children.length !== 2 ||
            node.children[0].textContent !== `${item.label}.` ||
            node.children[1].textContent !== rawText) return false;
        target = node.parentElement;
        groupKey = `bank:${id}`;
      } else return false;
      const group = pdfGroups.get(groupKey);
      if (group && group.target !== target) return false;
      if (!group) pdfGroups.set(groupKey, {target, kind: meta.anchorKind, id, entries: []});
      pdfGroups.get(groupKey).entries.push({label, sourceText: record.sourceText,
        translationZh: record.translationZh.trim()});
      optionIdsUsed.add(record.optionId);
      pdfSourceIdsUsed.add(meta.sourceOptionId);
      return true;
    };
    for (const record of sidecar.options || []) {
      if (record?.translationEligible !== true ||
          typeof record.translationZh !== 'string' || !record.translationZh.trim()) continue;
      if (record.pdfVerifiedSource && record.reflowBlockId == null) {
        if (await queuePdfOption(record)) pdfAttached++;
        else optionSkipped++;
        continue;
      }
      const prefix = `${paper.dataset.paperId}:`;
      const fullId = record.reflowBlockId;
      const index = record.reflowOptionIndex;
      if (!['answer_option', 'word_bank_option'].includes(record.kind) ||
          record.translationEligible !== true ||
          typeof record.questionId !== 'string' || !record.questionId.startsWith(prefix) ||
          typeof record.optionId !== 'string' ||
          typeof fullId !== 'string' || !fullId.startsWith(prefix) ||
          !Number.isInteger(index) || index < 0 ||
          typeof record.sourceText !== 'string' ||
          typeof record.reflowSourceText !== 'string') { optionSkipped++; continue; }
      const id = fullId.slice(prefix.length);
      if (!/^b-\d+-\d+$/.test(id) || used.has(id)) { optionSkipped++; continue; }
      const key = `${id}:${index}`;
      if (optionUsed.has(key) || optionIdsUsed.has(record.optionId) ||
          optionAnchors.get(key)?.length !== 1) {
        optionSkipped++; continue;
      }
      const block = blocks.get(id);
      const item = ['options', 'choice_row'].includes(block?.type) && block.items?.[index];
      if (!item || typeof item.label !== 'string' || !Array.isArray(item.runs)) {
        optionSkipped++; continue;
      }
      const optionPrefix = `${record.questionId}:${item.label}`;
      const suffix = record.optionId.slice(optionPrefix.length);
      const bankId = record.optionId.startsWith(prefix) ? record.optionId.slice(prefix.length) : '';
      const structuredIdMatches = record.kind === 'word_bank_option'
        ? (bankId === `word-bank:${item.label}` ||
          /^b-\d+-\d+:word-bank:[A-Z]$/.test(bankId) &&
            bankId.endsWith(`:${item.label}`))
        : record.optionId === optionPrefix ||
          record.optionId.startsWith(optionPrefix) && /^:\d+$/.test(suffix);
      if (!structuredIdMatches ||
          optionComparisonText(record.sourceText) !==
            optionComparisonText(record.reflowSourceText) ||
          record.reflowSourceText !== item.runs.map(run => run.text || '').join('') ||
          record.sourceHash !== await sha256(record.sourceText)) {
        optionSkipped++; continue;
      }
      const node = optionAnchors.get(key)[0];
      let textNode;
      if (block.type === 'options' && node.matches('li') &&
          node.parentElement?.matches('ul.options') && node.children.length === 2 &&
          node.children[0].matches('span.option-label') &&
          node.children[0].textContent === `${item.label}.` &&
          node.children[1].matches('span') &&
          node.children[1].textContent === record.reflowSourceText) {
        textNode = node.children[1];
      } else if (block.type === 'choice_row' && node.matches('.choice-item') &&
          node.parentElement?.matches('.choice-row') &&
          node.firstElementChild?.matches('strong') &&
          node.firstElementChild.textContent === `${item.label}.` &&
          node.textContent.slice(node.firstElementChild.textContent.length).trimStart() ===
            record.reflowSourceText) {
        textNode = node;
      }
      if (!textNode) { optionSkipped++; continue; }
      // choice_row also renders CET/TEM listening; only Kaoyan Section I uses Q1–20 for cloze.
      const questionNumber = /^q-(\d+)-\d+$/.exec(record.questionId.slice(prefix.length));
      const kaoyanCloze = record.kind === 'answer_option' &&
        paper.dataset.paperId.startsWith('kaoyan:') && block.type === 'choice_row' &&
        questionNumber && Number(questionNumber[1]) >= 1 && Number(questionNumber[1]) <= 20 &&
        block.runs?.map(run => run.text || '').join('').trim() === `${questionNumber[1]}.`;
      const inlineCloze = record.kind === 'word_bank_option' || kaoyanCloze;
      const translation = document.createElement('span');
      translation.className = 'option-translation';
      translation.setAttribute('lang', 'zh-CN');
      translation.textContent = record.translationZh.trim();
      translation.hidden = true;
      if (inlineCloze) {
        const original = document.createElement('span');
        original.className = 'cloze-option-original';
        while (textNode.firstChild) original.append(textNode.firstChild);
        textNode.append(original);
        textNode.classList.add('cloze-inline-option');
        if (kaoyanCloze) node.parentElement?.classList.add('cloze-inline-row');
      }
      textNode.append(translation);
      optionUsed.add(key);
      optionIdsUsed.add(record.optionId);
      translations.push(translation);
    }
    const ordinaryOptionsAttached = translations.length - paragraphAttached;
    for (const group of pdfGroups.values()) {
      const board = document.createElement('aside');
      board.className = 'pdf-option-translation-board';
      board.dataset.sourceBlockId = group.id;
      board.setAttribute('lang', 'zh-CN');
      board.hidden = true;
      const heading = document.createElement('strong');
      heading.className = 'pdf-option-translation-heading';
      heading.textContent = group.kind === 'figure_bank' ? '原图选项译文' : '词库补充译文';
      board.append(heading);
      for (const entry of group.entries.sort((a, b) => a.label.localeCompare(b.label))) {
        const row = document.createElement('div');
        row.className = 'pdf-option-translation-row';
        for (const [name, value] of [['label', `${entry.label}.`],
          ['source', entry.sourceText], ['text', entry.translationZh]]) {
          const cell = document.createElement('span');
          cell.className = `pdf-option-translation-${name}`;
          cell.textContent = value;
          row.append(cell);
        }
        board.append(row);
      }
      group.target.after(board);
      translations.push(board);
    }
    paper.dataset.translationParagraphsAttached = String(paragraphAttached);
    paper.dataset.translationOptionsAttached = String(ordinaryOptionsAttached + pdfAttached);
    paper.dataset.translationPdfOptionsAttached = String(pdfAttached);
    paper.dataset.translationPdfBoardsAttached = String(pdfGroups.size);
    paper.dataset.translationOptionsSkipped = String(optionSkipped);
    paper.dataset.translationAttached = String(paragraphAttached + ordinaryOptionsAttached + pdfAttached);
    paper.dataset.translationSkipped = String(skipped + optionSkipped);
    return translations;
    };

    const toggle = document.createElement('button');
    toggle.type = 'button';
    toggle.className = document.querySelector('.reader-controls')
      ? 'reader-button paragraph-translation-toggle' : 'paragraph-translation-toggle';
    toggle.textContent = '显示译文';
    toggle.setAttribute('aria-pressed', 'false');
    let translations = null;
    toggle.addEventListener('click', async () => {
      if (translations === null) {
        toggle.disabled = true;
        toggle.textContent = '正在加载译文';
        translations = await loadTranslations();
        toggle.disabled = false;
        if (!translations?.length) {
          toggle.disabled = true;
          toggle.textContent = '暂无译文';
          return;
        }
      }
      const show = toggle.getAttribute('aria-pressed') !== 'true';
      toggle.setAttribute('aria-pressed', String(show));
      toggle.textContent = show ? '隐藏译文' : '显示译文';
      translations.forEach(translation => { translation.hidden = !show; });
    });
    const controls = document.querySelector('.reader-controls');
    if (controls) controls.append(toggle);
    else document.querySelector('body > header nav')?.append(toggle);
  });
})();
