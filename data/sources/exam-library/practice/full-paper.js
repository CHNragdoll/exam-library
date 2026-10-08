(() => {
  'use strict';
  const {element, valueText, contextText, localImageUrl, renderStem, renderOptions, renderContent,
    renderAnswer, renderMath} = window.ExamPracticeRender;
  const byId = id => document.getElementById(id);
  const ui = {
    status: byId('page-status'), panel: byId('paper-panel'),
    category: byId('paper-category'), title: byId('paper-title'),
    count: byId('paper-count'), toc: byId('paper-toc-select'),
    immersiveTitle: byId('immersive-paper-title'), immersiveToggle: byId('immersive-toggle'),
    translationToggle: byId('paragraph-translation-toggle'),
    questionContext: byId('immersive-question-context'), groupCheck: byId('immersive-group-check'),
    groupBar: byId('immersive-question-context').parentElement,
    questionTabs: byId('immersive-question-tabs'),
    workspace: byId('immersive-workspace'), directory: byId('immersive-directory'),
    reading: byId('immersive-reading'),
    readingPage: byId('immersive-reading-page'),
    translationOverlay: byId('immersive-translation-overlay'),
    translationText: byId('immersive-translation-text'),
    immersiveQuestions: byId('immersive-questions'), questions: byId('question-list')
  };
  const answerCache = new Map();
  const translationCategories = new Set(['kaoyan', 'cet4', 'cet6', 'tem4', 'tem8']);
  let loadedQuestions = [];
  let immersiveState = null;
  let translationPaper = null;
  let translationsLoaded = false;
  let activeImmersiveTranslation = null;
  let activeImmersiveOption = null;
  let optionOverlay = null;

  function updateTranslationToggleLabel() {
    const visible = ui.translationToggle.getAttribute('aria-pressed') === 'true';
    ui.translationToggle.textContent = visible ?
      (immersiveState ? '关闭译文 · 点击原文或选项查看' : '隐藏中文译文') : '显示中文译文';
  }

  function resetImmersiveOptionReview() {
    activeImmersiveOption = null;
    if (!optionOverlay) return;
    optionOverlay.hidden = true;
    optionOverlay.querySelector('.immersive-option-translation-text').textContent = '';
    optionOverlay.style.removeProperty('top');
  }

  function selectImmersiveOptionTranslation(option, focusOverlay = true) {
    if (!immersiveState || !document.body.classList.contains('full-paper-translation-review') ||
        option.querySelector('.paper-option-translation.is-cloze-option')) return;
    const matching = immersiveState.activeGroup?.kind === 'matching';
    const sibling = option.nextElementSibling;
    const sourceTranslation = [...ui.readingPage.querySelectorAll('.paper-paragraph-translation')]
      .find(node => node.dataset.translationKey === option.dataset.translationKey && !node.hidden);
    // Matching passage choices are translated beside the passage itself. A
    // second right-pane overlay would cover their compact answer buttons.
    if (matching && sourceTranslation) return;
    const translation = sibling?.matches('.paper-option-translation, .paper-paragraph-translation') ?
      sibling : sourceTranslation;
    if (!translation || translation.hidden || !ui.immersiveQuestions.contains(option)) return;
    resetImmersiveTranslationReview();
    if (activeImmersiveOption === option) return;
    activeImmersiveOption = option;
    if (!optionOverlay) {
      optionOverlay = element('div', 'immersive-option-translation-overlay');
      optionOverlay.hidden = true;
      optionOverlay.tabIndex = 0;
      optionOverlay.setAttribute('role', 'button');
      optionOverlay.setAttribute('aria-label', '点击返回英文选项');
      optionOverlay.append(element('p', 'immersive-option-translation-hint',
        '本选项译文 · 点击返回选项'),
      element('p', 'immersive-option-translation-text'));
    }
    const overlayPane = matching ? ui.readingPage : ui.immersiveQuestions;
    overlayPane.append(optionOverlay);
    const letter = option.querySelector('.option-label')?.textContent.trim();
    optionOverlay.querySelector('.immersive-option-translation-hint').textContent =
      (letter ? letter + ' ' : '') + '选项译文 · 点击返回选项';
    const text = optionOverlay.querySelector('.immersive-option-translation-text');
    text.textContent = translation.textContent;
    optionOverlay.hidden = false;
    let fontSize = 16;
    text.style.fontSize = `${fontSize}px`;
    while (optionOverlay.scrollHeight > overlayPane.clientHeight - 16 && fontSize > 11) {
      fontSize--;
      text.style.fontSize = `${fontSize}px`;
    }
    const pane = overlayPane.getBoundingClientRect();
    const availableTop = pane.height - optionOverlay.scrollHeight - 8;
    const card = option.closest('.question-card');
    const lastChoice = [...(card?.querySelectorAll('.options-list .option') || [])].at(-1);
    const lastControl = card?.querySelector('.answer-actions') || lastChoice;
    const belowChoices = lastControl?.getBoundingClientRect().bottom - pane.top + 8;
    const desiredTop = matching ? option.getBoundingClientRect().top - pane.top :
      belowChoices <= availableTop ? belowChoices :
        option.getBoundingClientRect().bottom - pane.top + 4;
    optionOverlay.style.top = Math.max(8, Math.min(desiredTop, availableTop)) + 'px';
    if (focusOverlay && !matching) optionOverlay.focus({preventScroll: true});
  }

  function resetImmersiveTranslationReview() {
    activeImmersiveTranslation = null;
    ui.translationOverlay.hidden = true;
    ui.translationText.replaceChildren();
    ui.translationText.classList.remove('is-word-bank');
    ui.translationOverlay.style.removeProperty('top');
    ui.translationText.style.removeProperty('font-size');
    const active = Boolean(immersiveState) &&
      document.body.classList.contains('full-paper-translation-review');
    for (const node of ui.panel.querySelectorAll('.paper-translatable-source')) {
      if (active && ui.readingPage.contains(node)) node.tabIndex = 0;
      else node.removeAttribute('tabindex');
    }
  }

  function selectImmersiveTranslation(source) {
    if (!immersiveState || !document.body.classList.contains('full-paper-translation-review')) return;
    const key = source.dataset.translationKey;
    const translation = [...ui.readingPage.querySelectorAll(
      '.paper-paragraph-translation, .paper-word-bank-translations')]
      .find(node => node.dataset.translationKey === key && !node.hidden &&
        !node.closest('.paper-section[hidden], .immersive-source-hidden'));
    if (!translation) return;
    resetImmersiveOptionReview();
    const same = activeImmersiveTranslation === key;
    resetImmersiveTranslationReview();
    if (same) return;
    activeImmersiveTranslation = key;
    if (translation.classList.contains('paper-word-bank-translations')) {
      ui.translationText.classList.add('is-word-bank');
      ui.translationText.replaceChildren(
        ...[...translation.querySelectorAll('.paper-word-bank-entry')]
          .map(entry => element('span', 'paper-word-bank-entry', entry.textContent)));
    } else ui.translationText.textContent = translation.textContent;
    ui.translationOverlay.hidden = false;
    let fontSize = 18;
    ui.translationText.style.fontSize = `${fontSize}px`;
    while (ui.translationOverlay.scrollHeight > ui.readingPage.clientHeight - 16 && fontSize > 12) {
      fontSize--;
      ui.translationText.style.fontSize = `${fontSize}px`;
    }
    const page = ui.readingPage.getBoundingClientRect();
    const desiredTop = source.getBoundingClientRect().top - page.top;
    const availableTop = page.height - ui.translationOverlay.scrollHeight - 8;
    ui.translationOverlay.style.top = `${Math.max(8, Math.min(desiredTop, availableTop))}px`;
    ui.translationOverlay.focus({preventScroll: true});
  }

  function setTranslationsVisible(visible) {
    for (const translation of ui.panel.querySelectorAll(
      '.paper-paragraph-translation, .paper-option-translation, .paper-word-bank-translations')) {
      translation.hidden = !visible;
    }
    document.body.classList.toggle('full-paper-translation-review', visible);
    resetImmersiveTranslationReview();
    resetImmersiveOptionReview();
    ui.translationToggle.setAttribute('aria-pressed', String(visible));
    updateTranslationToggleLabel();
    if (immersiveState) {
      fitReadingPage();
      for (const card of immersiveState.cards) {
        if (!card.hidden) fitImmersiveQuestion(card);
      }
    }
  }

  function sourceParagraph(unit, index) {
    const paragraphs = unit.querySelectorAll('p.paragraph, p.content-text');
    if (paragraphs.length) return paragraphs[index] || null;
    return index === 0 ? unit : null;
  }

  function refreshImmersiveSources() {
    if (!immersiveState) return;
    for (const {sourceHolder, sourceBlocks} of immersiveState.placements) {
      if (!sourceHolder) continue;
      sourceHolder.replaceChildren(...sourceBlocks.map(block => {
        const copy = block.cloneNode(true);
        copy.classList.remove('immersive-source-hidden');
        copy.querySelectorAll('[id]').forEach(item => item.removeAttribute('id'));
        return copy;
      }));
    }
  }

  function addParagraphTranslations(sidecar, paper) {
    if (!Array.isArray(sidecar?.paragraphs)) return 0;
    if (sidecar.paperId !== paper.id) {
      console.warn('段落译文试卷 ID 与当前试卷不符', paper.id, sidecar.paperId);
      return 0;
    }
    const units = new Map();
    for (const selector of ['.paper-unit[data-source-block-id]',
      '.question-card .content-block[data-source-block-id]',
      '.question-card .paper-instruction[data-source-block-id]',
      '.question-card .question-stem[data-source-block-id]',
      '.question-card .practice-email-box > p[data-source-block-id]']) {
      for (const unit of ui.panel.querySelectorAll(selector)) {
        if (!units.has(unit.dataset.sourceBlockId)) units.set(unit.dataset.sourceBlockId, unit);
      }
    }
    const seen = new Set();
    const unmatched = [];
    const normalize = text => text.replace(/\s+/g, '');
    const passageOptions = sidecar.paragraphs.filter(record => record.kind === 'passage_option' &&
      record.translationEligible === true && typeof record.translationZh === 'string' &&
      record.translationZh.trim() && Array.isArray(record.sourceBlockIds) &&
      Number.isInteger(record.paragraphIndex) && record.paragraphIndex >= 0 &&
      record.sourceBlockIds.every(id => units.has(id)) &&
      normalize(record.sourceBlockIds.map(id =>
        sourceParagraph(units.get(id), record.paragraphIndex)?.textContent || '').join('')) ===
        normalize(record.sourceText || ''));
    for (const record of Array.isArray(sidecar.options) ? sidecar.options : []) {
      if (record?.kind === 'word_bank_option') continue;
      const alias = record?.coverageStatus === 'covered_by_paragraph' &&
        typeof record.translationRef === 'string';
      const optionAlias = record?.coverageStatus === 'covered_by_option' &&
        typeof record.translationRef === 'string';
      const owner = optionAlias && sidecar.options.find(candidate =>
        candidate.id === record.translationRef);
      const translated = record?.translationEligible === true &&
        typeof record.translationZh === 'string' && record.translationZh.trim();
      if (!alias && !translated && !optionAlias) continue;
      if (optionAlias && !owner) {
        unmatched.push(record.id || record.optionId || 'unknown-option-alias');
        continue;
      }
      if (optionAlias && !owner.translationZh) continue;
      if (optionAlias && (owner.kind !== 'answer_option' ||
          owner.translationEligible !== true ||
          owner.sourceText !== record.sourceText ||
          owner.sourceHash !== record.sourceHash ||
          JSON.stringify(owner.sourceBlockIds || []) !==
            JSON.stringify(record.sourceBlockIds || []) ||
          typeof owner.translationZh !== 'string' ||
          (record.translationZh && record.translationZh !== owner.translationZh))) {
        unmatched.push(record.id || record.optionId || 'unknown-option-alias');
        continue;
      }
      if (alias && !passageOptions.some(passage => passage.id === record.translationRef)) {
        // A valid but still untranslated paragraph cannot provide a review
        // overlay yet. A missing reference is reported below after the exact
        // source and option identity checks.
        const reference = sidecar.paragraphs.find(passage => passage.id === record.translationRef);
        if (reference && !reference.translationZh) continue;
      }
      const question = loadedQuestions.find(item => item.id === record.questionId);
      const optionIndex = question?.options?.findIndex(item => item.id === record.optionId) ?? -1;
      const option = optionIndex >= 0 && [...ui.panel.querySelectorAll('.question-card')]
        .find(card => card.dataset.questionId === question.id)
        ?.querySelectorAll('.option')[optionIndex];
      if (record.kind !== 'answer_option' || !option ||
          typeof record.sourceText !== 'string' ||
          normalize(valueText(question.options[optionIndex].text)) !== normalize(record.sourceText) ||
          normalize(option.querySelector('.option-text')?.textContent || '') !==
            normalize(record.sourceText)) {
        unmatched.push(record.id || record.optionId || 'unknown-option');
        continue;
      }
      const key = `option:${record.optionId}`;
      if (seen.has(key)) {
        unmatched.push(record.id || key);
        continue;
      }
      const sharedPassage = passageOptions.find(passage =>
        (!alias || passage.id === record.translationRef) &&
        normalize(passage.sourceText.replace(/^\s*[A-H][).]\s*/, '')) ===
          normalize(record.sourceText) &&
        (!Array.isArray(record.sourceBlockIds) || !record.sourceBlockIds.length ||
          record.sourceBlockIds.some(id => passage.sourceBlockIds.includes(id))));
      if (alias && !sharedPassage) {
        unmatched.push(record.id || key);
        continue;
      }
      seen.add(key);
      if (sharedPassage) {
        option.dataset.translationKey =
          `${sharedPassage.sourceBlockIds.join('|')}:${sharedPassage.paragraphIndex}`;
        continue;
      }
      option.dataset.translationKey = key;
      const clozeOption = question.labels?.some(label => label.kind === 'cloze');
      const translation = element(clozeOption ? 'span' : 'p', 'paper-option-translation',
        optionAlias ? owner.translationZh.trim() : record.translationZh.trim());
      translation.dataset.translationKey = key;
      translation.lang = 'zh-CN';
      translation.hidden = true;
      if (clozeOption) {
        translation.classList.add('is-cloze-option');
        option.append(translation);
      } else option.after(translation);
    }
    function sourceChoice(record) {
      if (record.sourceBlockIds.length !== 1 || record.paragraphIndex !== 0 ||
          typeof record.sourceText !== 'string') return null;
      const match = record.sourceText.match(/^\s*(\d+)[、.)]\s*([A-D])[).]\s*([\s\S]+)$/);
      if (!match) return null;
      const question = loadedQuestions.find(item => String(item.number) === match[1] &&
        item.sourceBlocks?.some(id =>
          (id.startsWith(`${paper.id}:`) ? id : `${paper.id}:${id}`) === record.sourceBlockIds[0]));
      const optionIndex = question?.options?.findIndex(option =>
        (option.sourceLabel || option.label || '').startsWith(match[2]) &&
        normalize(valueText(option.text)) === normalize(match[3]));
      if (optionIndex == null || optionIndex < 0) return null;
      const card = [...ui.panel.querySelectorAll('.question-card')]
        .find(item => item.dataset.questionId === question.id);
      return card?.querySelectorAll('.option')[optionIndex] || null;
    }
    for (const record of sidecar.paragraphs) {
      if (!record || record.translationEligible !== true ||
          typeof record.translationZh !== 'string' || !record.translationZh.trim()) continue;
      if (!Array.isArray(record.sourceBlockIds) || !record.sourceBlockIds.length ||
          !Number.isInteger(record.paragraphIndex) || record.paragraphIndex < 0) {
        unmatched.push(record.id || 'unknown');
        continue;
      }
      let sourceNodes = record.sourceBlockIds.flatMap(id => {
        const unit = units.get(id);
        if (!unit) return [null];
        if (unit.matches('.practice-email-box > p')) {
          if (record.paragraphIndex !== 0) return [null];
          const group = [unit];
          while (group.at(-1).nextElementSibling?.dataset.sourceBlockId === id) {
            group.push(group.at(-1).nextElementSibling);
          }
          return group;
        }
        return [sourceParagraph(unit, record.paragraphIndex)];
      });
      const exactSource = typeof record.sourceText === 'string' &&
        sourceNodes.every(Boolean) &&
        normalize(sourceNodes.map(node => node.textContent).join('')) ===
          normalize(record.sourceText);
      const choice = exactSource ? null : sourceChoice(record);
      if (!exactSource && !choice) {
        unmatched.push(record.id || record.sourceBlockIds[0]);
        continue;
      }
      if (choice) sourceNodes = [choice];
      const last = sourceNodes.at(-1);
      const key = `${record.sourceBlockIds.join('|')}:${record.paragraphIndex}`;
      if (seen.has(key)) {
        unmatched.push(record.id || record.sourceBlockIds[0]);
        continue;
      }
      seen.add(key);
      if (choice?.nextElementSibling?.classList.contains('paper-option-translation')) continue;
      for (const node of sourceNodes) {
        const wrapper = node.closest('[data-source-block-id]');
        const fullWrapper = wrapper && wrapper !== node &&
          wrapper.querySelectorAll('p.paragraph, p.content-text').length === 1 &&
          wrapper.textContent.trim() === node.textContent.trim();
        const source = fullWrapper ? wrapper : node;
        source.classList.add('paper-translatable-source');
        source.dataset.translationKey = key;
      }
      const translation = element('p', 'paper-paragraph-translation', record.translationZh.trim());
      translation.dataset.translationKey = key;
      translation.lang = 'zh-CN';
      translation.hidden = true;
      // A one-paragraph source unit stays untouched. For a multi-paragraph unit,
      // place the translation beside the exact paragraph within its wrapper.
      if (choice) choice.after(translation);
      else if (last === units.get(record.sourceBlockIds.at(-1)) ||
          last.parentElement?.querySelectorAll('p.paragraph, p.content-text').length === 1) {
        units.get(record.sourceBlockIds.at(-1)).after(translation);
      } else last.after(translation);
    }
    const wordBankChoices = new Map();
    for (const question of loadedQuestions) {
      for (const choice of question.context?.wordBank || []) {
        if (!wordBankChoices.has(choice.id)) {
          wordBankChoices.set(choice.id, {choice, questionId: question.id,
            contextId: question.context.id});
        }
      }
    }
    const bankPanels = new Map();
    for (const record of Array.isArray(sidecar.options) ? sidecar.options : []) {
      if (record?.kind !== 'word_bank_option' || record.translationEligible !== true ||
          typeof record.translationZh !== 'string' || !record.translationZh.trim()) continue;
      const bank = wordBankChoices.get(record.optionId);
      const sourceId = Array.isArray(record.sourceBlockIds) &&
        record.sourceBlockIds.length === 1 ? record.sourceBlockIds[0] : null;
      const unit = sourceId && units.get(sourceId);
      const sourceLabel = bank?.choice.sourceText;
      const sourceBlockId = bank?.choice.sourceBlockId;
      const exact = bank && (record.questionId === bank.questionId ||
        record.questionId === bank.contextId) &&
        sourceId === (sourceBlockId?.startsWith(paper.id + ':') ?
          sourceBlockId : paper.id + ':' + sourceBlockId) &&
        normalize(record.sourceText || '') === normalize(bank.choice.text || '') &&
        typeof sourceLabel === 'string' && sourceLabel.trim() &&
        unit && normalize(unit.textContent).includes(normalize(sourceLabel));
      const key = 'word-bank:' + record.optionId;
      if (!exact || seen.has(key)) {
        unmatched.push(record.id || record.optionId || 'unknown-word-bank');
        continue;
      }
      seen.add(key);
      let panel = bankPanels.get(sourceId);
      if (!panel) {
        panel = element('div', 'paper-word-bank-translations');
        panel.lang = 'zh-CN';
        panel.hidden = true;
        panel.dataset.translationKey = 'word-bank:' + sourceId;
        unit.classList.add('paper-translatable-source');
        unit.dataset.translationKey = panel.dataset.translationKey;
        let last = unit;
        while (last.nextElementSibling?.classList.contains('paper-paragraph-translation')) {
          last = last.nextElementSibling;
        }
        last.after(panel);
        bankPanels.set(sourceId, panel);
      }
      panel.append(element('span', 'paper-word-bank-entry',
        bank.choice.label + ' ' + record.translationZh.trim()));
    }
    ui.translationToggle.dataset.attached = String(seen.size);
    ui.translationToggle.dataset.unmatched = String(unmatched.length);
    ui.translationToggle.title = unmatched.length ?
      `已对齐 ${seen.size} 段译文，另有 ${unmatched.length} 段与当前原文不符，暂不显示` :
      `已对齐 ${seen.size} 段译文`;
    if (unmatched.length) console.warn('段落译文未能对齐原文', paper.id,
      `${seen.size} attached, ${unmatched.length} unmatched`, unmatched.slice(0, 12));
    refreshImmersiveSources();
    setTranslationsVisible(false);
    return seen.size;
  }

  async function loadParagraphTranslations(paper) {
    const stem = paper.id?.split(':')[1];
    if (!translationCategories.has(paper.category) ||
        !/^[a-z0-9-]+$/.test(stem || '')) return 0;
    try {
      const sidecar = await getJson(`/exam-library/structured/translations/${paper.category}/${stem}.json`);
      return addParagraphTranslations(sidecar, paper);
    } catch (_) {
      // Translation files are optional; a missing file leaves the paper unchanged.
      return 0;
    }
  }

  async function getJson(path) {
    const response = await fetch(path, {headers: {Accept: 'application/json'}});
    if (!response.ok) throw new Error(`请求失败（HTTP ${response.status}）`);
    return response.json();
  }

  function setStatus(message, error = false) {
    ui.status.textContent = message;
    ui.status.classList.toggle('is-error', error);
    ui.status.hidden = false;
  }

  function resetAnswer(card) {
    const panel = card.querySelector('.answer-panel');
    panel.replaceChildren();
    panel.hidden = true;
    card.querySelectorAll('.option').forEach(option => {
      option.classList.remove('is-correct', 'is-wrong');
      option.querySelector('.option-tag')?.remove();
      const input = option.querySelector('input');
      input.checked = false;
      input.disabled = false;
    });
    const written = card.querySelector('textarea');
    if (written) { written.value = ''; written.disabled = false; }
    for (const button of card.querySelectorAll('.paper-word-bank-option')) {
      button.disabled = false;
      button.classList.remove('is-selected');
      button.setAttribute('aria-pressed', 'false');
    }
    const reveal = card.querySelector('[data-action="reveal"]');
    reveal.hidden = false;
    reveal.disabled = false;
    reveal.textContent = '查看答案';
    card.querySelector('[data-action="redo"]').hidden = true;
  }

  function renderCard(question, index, seenBlocks, showContext, paper) {
    const card = element('article', 'question-card');
    card.id = 'question-' + (index + 1);
    card.dataset.questionId = question.id;
    const heading = element('div', 'question-heading');
    const numberValue = String(question.number || index + 1);
    const specialMatch = /^(Writing|Translation)(?:\s+(\d+))?$/.exec(numberValue);
    const specialNumber = specialMatch &&
      `${specialMatch[1] === 'Writing' ? '写作' : '翻译'}${specialMatch[2] ? ` ${specialMatch[2]}` : ''}`;
    const number = element('span', 'question-number', specialNumber || `第 ${numberValue} 题`);
    number.dataset.shortNumber = specialNumber || numberValue;
    heading.append(number);
    const options = Array.isArray(question.options) ? question.options : [];
    const labels = Array.isArray(question.labels) ? question.labels : [];
    const isKaoyanEnglish = paper?.category === 'kaoyan';
    if (labels.some(label => label.kind === 'cloze') && options.length === 4) {
      card.classList.add('is-cloze-choice');
    }
    const cetSectionTask = ['cet4', 'cet6'].includes(paper?.category) &&
      Boolean(specialMatch) &&
      ['writing_task', 'translation_passage'].includes(question.context?.kind);
    const hideEmptyClozeStem = isKaoyanEnglish &&
      labels.some(label => label.kind === 'cloze') && !valueText(question.stem).trim();
    if (!isKaoyanEnglish) {
      const multiple = /multi|multiple/i.test(question.questionType || '');
      const kind = multiple ? '多选' : options.length ? '单选' : '非选择题';
      heading.append(element('span', 'question-kind',
        question.status === 'complete' ? kind : kind + ' · 题文待核'));
    }
    card.append(heading);
    if (showContext && !cetSectionTask) {
      const context = contextText(question.context);
      if (context.trim()) card.append(element('div', 'question-context', context));
    }
    const stem = element('div', 'question-stem');
    const directionsMatch = /^\s*\d+[.)]?[ \t]*Directions:[ \t]*(?:\r?\n([\s\S]*))?$/i
      .exec(valueText(question.stem));
    const writingDirections = labels.some(label => label.kind === 'writing') &&
      Boolean(directionsMatch);
    const firstContentBlock = question.contentBlocks?.[0];
    const translationInstructionBlock = directionsMatch &&
      labels.some(label => label.kind === 'translation') &&
      /^Translate the following text(?: from English)? into Chinese\./i
        .test(valueText(firstContentBlock?.text).trim()) ? firstContentBlock : null;
    const inlineWritingItems = [];
    const inlineWritingTail = [];
    if (writingDirections || translationInstructionBlock) {
      stem.classList.add('paper-directions');
      stem.append(element('strong', 'paper-directions-label', 'Directions:'));
      for (const line of (directionsMatch[1] || '').split(/\r?\n/).filter(line => line.trim())) {
        if (writingDirections && /^\s*\d+[.)]\s+/.test(line)) {
          inlineWritingItems.push(element('p', 'paper-writing-item', line));
        } else if (inlineWritingItems.length) {
          inlineWritingTail.push(element('p', 'paper-writing-instruction', line));
        } else stem.append(element('p', 'paper-instruction', line));
      }
      if (translationInstructionBlock) {
        const instruction = element('p', 'paper-instruction',
          translationInstructionBlock.text.trim());
        const instructionId = translationInstructionBlock.id;
        if (instructionId) instruction.dataset.sourceBlockId =
          instructionId.startsWith(`${paper.id}:`) ? instructionId : `${paper.id}:${instructionId}`;
        stem.append(instruction);
      }
    } else if (!hideEmptyClozeStem && !cetSectionTask) renderStem(stem, question);
    const stemSourceId = question.sourceBlocks?.[0];
    if (stemSourceId && !hideEmptyClozeStem && !cetSectionTask) {
      stem.dataset.sourceBlockId = stemSourceId.startsWith(`${paper.id}:`) ?
        stemSourceId : `${paper.id}:${stemSourceId}`;
    }
    const content = element('div', 'question-content');
    const cetContentBlocks = cetSectionTask && question.context?.kind === 'writing_task' ?
      question.contentBlocks?.map(block => {
        const instructionIds = question.context.instructionSourceBlocks || [];
        const blockId = block.id?.startsWith(`${paper.id}:`) ?
          block.id.slice(paper.id.length + 1) : block.id;
        const instruction = valueText(question.context.instructionText).trim();
        const raw = valueText(block.text).trim();
        if (!instructionIds.includes(blockId) || !instruction || raw === instruction ||
            !/\bPart.{0,12}Listening Comprehension\b/i.test(raw) ||
            !raw.startsWith(instruction)) return block;
        // The source block also contains the next section in a few OCR
        // papers. Display the source-backed writing prefix without bringing
        // Part II into this task; the original structured block is untouched.
        return {...block, text: instruction, presentation: null,
          styledParagraphs: null, paragraphs: null};
      }) : question.contentBlocks;
    const contentQuestion = cetSectionTask ? {...question, stem: '',
      contentBlocks: cetContentBlocks} :
      translationInstructionBlock ? {...question,
        contentBlocks: question.contentBlocks.slice(1)} : question;
    renderContent(content, contentQuestion, {seenBlockIds: seenBlocks, imageLoading: 'lazy',
      emailLayout: true, questionRoleContent: true});
    if (cetSectionTask) {
      for (const block of content.querySelectorAll(':scope > .content-block')) {
        if (/\bDirections?\s*[:：,，]|\bFor this part\b/i.test(block.textContent)) {
          block.classList.add('paper-directions');
        }
      }
    }
    // The shared card renderer leaves source IDs off its content nodes. Attach
    // them here so whole-text translation passages can use the same sidecar.
    const renderedBlocks = [...content.querySelectorAll(':scope > .content-block')];
    const emailLines = [...content.querySelectorAll('.practice-email-box > p')];
    for (const block of contentQuestion.contentBlocks || []) {
      const source = valueText(block.text).replace(/\s+/g, '');
      if (!block.id || !source) continue;
      const rendered = renderedBlocks.find(node => !node.dataset.sourceBlockId &&
        node.textContent.replace(/\s+/g, '') === source);
      if (rendered) {
        rendered.dataset.sourceBlockId = block.id;
        continue;
      }
      // The email renderer can split one source block into greeting, body, and
      // sign-off paragraphs. Keep that layout, but retain each paragraph's
      // source identity for an exact translation match.
      for (let first = 0; first < emailLines.length; first++) {
        if (emailLines[first].dataset.sourceBlockId) continue;
        let joined = '';
        for (let last = first; last < emailLines.length &&
            !emailLines[last].dataset.sourceBlockId; last++) {
          joined += emailLines[last].textContent.replace(/\s+/g, '');
          if (joined === source) {
            for (let i = first; i <= last; i++) emailLines[i].dataset.sourceBlockId = block.id;
            first = emailLines.length;
            break;
          }
          if (joined.length >= source.length) break;
        }
      }
    }
    if (writingDirections) {
      content.querySelectorAll('.content-block').forEach(block => {
        if (block.classList.contains('content-question')) {
          block.classList.add('paper-writing-item');
        } else if (!block.querySelector('.practice-email-box, .content-figure')) {
          block.classList.add('paper-writing-instruction');
        }
      });
      content.prepend(...inlineWritingItems);
      content.append(...inlineWritingTail);
      // Keep the heading and opening prose in one Directions area. Numbered
      // writing requirements and source examples are ordinary paper content.
      while (content.firstElementChild?.classList.contains('paper-writing-instruction')) {
        stem.append(content.firstElementChild);
      }
      let tail = null;
      for (const child of [...content.children]) {
        if (child.classList.contains('paper-writing-instruction')) {
          if (!tail) {
            tail = element('div', 'paper-directions paper-directions-tail');
            child.before(tail);
          }
          tail.append(child);
        } else tail = null;
      }
    }
    if (!hideEmptyClozeStem && !cetSectionTask) card.append(stem);
    card.append(content);
    const form = element('form');
    form.addEventListener('submit', event => event.preventDefault());
    const optionList = element('div', 'options-list');
    let written = null;
    if (options.length) {
      const fieldset = element('fieldset', 'options-fieldset');
      fieldset.append(element('legend', 'sr-only', '选择答案'));
      renderOptions(optionList, question, 'choice-' + (index + 1));
      optionList.querySelectorAll('.option').forEach(option => {
        option.title = option.textContent.trim();
        option.querySelector('input')?.setAttribute('aria-label', option.title);
      });
      fieldset.append(optionList);
      form.append(fieldset);
    } else {
      const label = element('label', 'written-answer', '我的作答');
      written = element('textarea');
      const wordBank = question.context?.kind === 'word_bank_cloze' &&
        Array.isArray(question.context.wordBank) ? question.context.wordBank : [];
      written.rows = wordBank.length ? 1 : 4;
      written.placeholder = wordBank.length ? '输入 A–O，或点选下方词库' :
        '在这里记录思路或答案';
      label.append(written);
      form.append(label);
      if (wordBank.length) {
        const picker = element('div', 'paper-word-bank-picker');
        picker.setAttribute('role', 'group');
        picker.setAttribute('aria-label', '词库选项');
        picker.append(element('span', 'paper-word-bank-picker-title',
          '选词填空 · 选择字母或自行输入'));
        const choices = element('div', 'paper-word-bank-picker-choices');
        const buttons = [];
        for (const choice of wordBank) {
          const letter = /^([A-O])\s*[.)]?$/i.exec(valueText(choice.label).trim())?.[1]
            ?.toUpperCase();
          if (!letter || !valueText(choice.text).trim()) continue;
          const button = element('button', 'paper-word-bank-option');
          button.type = 'button';
          button.dataset.wordBankOptionId = choice.id;
          button.dataset.letter = letter;
          button.dataset.word = valueText(choice.text).trim();
          button.setAttribute('aria-pressed', 'false');
          button.append(element('strong', 'paper-word-bank-letter', letter + '.'),
            element('span', 'paper-word-bank-word', valueText(choice.text).trim()));
          button.addEventListener('click', () => {
            if (written.disabled) return;
            written.value = letter;
            written.dispatchEvent(new Event('input', {bubbles: true}));
            written.focus({preventScroll: true});
          });
          choices.append(button);
          buttons.push(button);
        }
        written.addEventListener('input', () => {
          const draft = written.value.trim().toLowerCase();
          for (const button of buttons) {
            const selected = draft === button.dataset.letter.toLowerCase() ||
              draft === button.dataset.word.toLowerCase();
            button.classList.toggle('is-selected', selected);
            button.setAttribute('aria-pressed', String(selected));
          }
        });
        picker.append(choices);
        form.append(picker);
        card.classList.add('paper-word-bank-question');
      }
    }
    card.append(form);
    const actions = element('div', 'answer-actions');
    const reveal = element('button', 'primary-button', '查看答案');
    reveal.type = 'button';
    reveal.dataset.action = 'reveal';
    const redo = element('button', '', '重做本题');
    redo.type = 'button';
    redo.dataset.action = 'redo';
    redo.hidden = true;
    const error = element('span', 'answer-error');
    error.hidden = true;
    actions.append(reveal, redo, error);
    if (card.classList.contains('is-cloze-choice')) heading.append(actions);
    else card.append(actions);
    const panel = element('section', 'answer-panel');
    panel.setAttribute('aria-label', '参考答案');
    panel.hidden = true;
    card.append(panel);
    async function revealAnswer({forGroup = false} = {}) {
      if (reveal.disabled) {
        if (!forGroup || card.groupAnswerAvailable) return {status: 'checked'};
        if (!card.answerStatus) return {status: 'error'};
        const selected = new Set([...optionList.querySelectorAll('input:checked')]
          .map(input => input.value));
        const draft = written?.value;
        resetAnswer(card);
        optionList.querySelectorAll('input').forEach(input => {
          input.checked = selected.has(input.value);
        });
        if (written) written.value = draft;
        return {status: 'unavailable'};
      }
      reveal.disabled = true;
      reveal.textContent = '正在读取答案…';
      error.hidden = true;
      try {
        const answer = answerCache.get(question.id) ||
          await getJson('/api/v1/questions/' + encodeURIComponent(question.id) + '/answer');
        answerCache.set(question.id, answer);
        card.answerStatus = answer.status;
        card.groupAnswerAvailable = answer.status === 'explicit' &&
          Boolean(answer.correctOptionIds?.length) &&
          answer.correctOptionIds.every(id => question.options.some(option => option.id === id));
        if (forGroup && !card.groupAnswerAvailable) {
          reveal.disabled = false;
          reveal.textContent = '查看答案';
          return {status: 'unavailable'};
        }
        const selected = new Set([...optionList.querySelectorAll('input:checked')]
          .map(input => input.value));
        renderAnswer({panel, question, answer, options: optionList, written, reveal, redo, selected});
        card.querySelectorAll('.paper-word-bank-option').forEach(button => {
          button.disabled = true;
        });
        return {status: 'checked'};
      } catch (failure) {
        reveal.disabled = false;
        reveal.textContent = '重试查看答案';
        error.textContent = '答案读取失败：' + failure.message;
        error.hidden = false;
        return {status: 'error'};
      }
    }
    card.revealAnswer = revealAnswer;
    reveal.addEventListener('click', revealAnswer);
    redo.addEventListener('click', () => { error.hidden = true; resetAnswer(card); });
    return card;
  }

  const semanticTags = new Set(['p', 'span', 'strong', 'b', 'em', 'i', 'u', 'br',
    'figure', 'figcaption', 'img']);
  const semanticClasses = new Set(['paragraph', 'blank', 'flowchart']);

  function safeSemanticNode(node, imageBase) {
    if (node.nodeType === Node.TEXT_NODE) return document.createTextNode(node.textContent);
    if (node.nodeType !== Node.ELEMENT_NODE ||
        node.matches('script,style,iframe,object,embed,template,form')) return null;
    if (!semanticTags.has(node.localName)) {
      const fragment = document.createDocumentFragment();
      for (const child of node.childNodes) {
        const safe = safeSemanticNode(child, imageBase);
        if (safe) fragment.append(safe);
      }
      return fragment;
    }
    const copy = element(node.localName);
    const classes = (node.getAttribute('class') || '').split(/\s+/)
      .filter(name => semanticClasses.has(name));
    if (classes.length) copy.className = classes.join(' ');
    if (node.localName === 'img') {
      const src = localImageUrl(node.getAttribute('src'), imageBase);
      if (!src) return null;
      copy.src = src;
      copy.alt = node.getAttribute('alt') || '';
      copy.loading = 'lazy';
      copy.decoding = 'async';
    }
    for (const child of node.childNodes) {
      const safe = safeSemanticNode(child, imageBase);
      if (safe) copy.append(safe);
    }
    return copy;
  }

  function joinAdjacentUnderlines(parent) {
    for (const child of [...parent.childNodes]) {
      if (child.nodeType === Node.ELEMENT_NODE) joinAdjacentUnderlines(child);
    }
    for (let current = parent.firstChild; current;) {
      if (current.nodeType === Node.ELEMENT_NODE && current.localName === 'u') {
        const spacer = current.nextSibling;
        const following = spacer?.nodeType === Node.TEXT_NODE && !spacer.textContent.trim() ?
          spacer.nextSibling : spacer;
        if (following?.nodeType === Node.ELEMENT_NODE && following.localName === 'u') {
          if (spacer !== following) current.append(spacer);
          while (following.firstChild) current.append(following.firstChild);
          following.remove();
          continue;
        }
      }
      current = current.nextSibling;
    }
  }

  function renderSemanticUnit(unit, seenBlocks, title, structuredContexts, imageBase,
    preferSource = false, joinTranslationUnderlines = false, wordBankSource = false) {
    const body = valueText(unit.text).trim();
    const markup = typeof unit.contentHtml === 'string' ? unit.contentHtml : '';
    if ((!body && !markup.trim()) ||
        (title && body && body.replace(/\s+/g, '') === title.replace(/\s+/g, ''))) return null;
    const compact = body.replace(/\s+/g, '');
    if (!preferSource && unit.provenance?.sourceBlockId && compact.length >= 30 &&
        structuredContexts.some(context => context.includes(compact))) return null;
    const sourceId = unit.provenance?.sourceBlockId;
    const sourceKey = sourceId && `${sourceId}\u0000${body || markup}`;
    if (sourceKey && seenBlocks.has(sourceKey)) return null;
    if (sourceKey) seenBlocks.add(sourceKey);
    const item = element('div', 'paper-unit paper-unit-' +
      (['paragraph', 'instruction', 'figure', 'code', 'formula'].includes(unit.type) ? unit.type : 'other'), body);
    if (markup.trim()) {
      const parsed = new DOMParser().parseFromString(markup, 'text/html');
      const safe = document.createDocumentFragment();
      const bankItems = wordBankSource ? parsed.body.querySelectorAll('ul.options > li') : [];
      if (bankItems.length >= 2) {
        item.classList.add('paper-word-bank-source');
        for (const bankItem of bankItems) {
          const choice = element('span', 'paper-word-bank-source-item');
          for (const child of bankItem.childNodes) {
            const copy = safeSemanticNode(child, imageBase);
            if (copy) choice.append(copy);
          }
          safe.append(choice);
        }
      } else {
        for (const child of parsed.body.childNodes) {
          const copy = safeSemanticNode(child, imageBase);
          if (copy) safe.append(copy);
        }
      }
      if (joinTranslationUnderlines) joinAdjacentUnderlines(safe);
      if (safe.childNodes.length) item.replaceChildren(safe);
    }
    if (!item.textContent.trim() && !item.querySelector('img')) return null;
    if (unit.type === 'figure' && sourceId) seenBlocks.add(`${sourceId}\u0000figure`);
    if (sourceId) item.dataset.sourceBlockId = sourceId;
    return item;
  }

  function renderPaperTree(root, questions, paper) {
    const safePath = value => typeof value === 'string' && /^[a-z0-9-]+$/.test(value);
    const slug = paper.id?.split(':')[1];
    const imageBase = safePath(paper.category) && safePath(slug) ?
      `/exam-library/structured/papers/${paper.category}/${slug}.htm` : document.baseURI;
    const sourceBlockId = id => typeof id === 'string' && id.startsWith(paper.id + ':') ?
      id : `${paper.id}:${id}`;
    const passageOwners = new Map();
    const instructionIds = new Set();
    const wordBankSourceIds = new Set();
    for (const question of questions) {
      const label = Array.isArray(question.labels) ? question.labels[0] : null;
      const context = question.context;
      if (!context || typeof context !== 'object') continue;
      const passageBlocks = context.passageSourceBlocks || [];
      const owner = label?.id ? label : passageBlocks.length ?
        {id: `${paper.id}:passage:${sourceBlockId(passageBlocks[0])}`} : null;
      for (const id of passageBlocks) {
        if (owner && !passageOwners.has(sourceBlockId(id))) {
          passageOwners.set(sourceBlockId(id), owner);
        }
      }
      for (const id of context.instructionSourceBlocks || []) instructionIds.add(sourceBlockId(id));
      if (context.instructionSourceBlock) instructionIds.add(sourceBlockId(context.instructionSourceBlock));
      for (const id of context.wordBankSourceBlocks || []) wordBankSourceIds.add(sourceBlockId(id));
      for (const choice of context.wordBank || []) {
        if (choice.sourceBlockId) wordBankSourceIds.add(sourceBlockId(choice.sourceBlockId));
      }
    }
    const byQuestionId = new Map(questions.map((question, index) => [question.id, {question, index}]));
    const byNodeId = new Map();
    const parentNodes = new Map();
    const structuredContexts = [];
    const mathSourceUnits = [];
    const isMathVariant = unit => paper.category === 'math3' &&
      /^[（(]?试卷\s*(?:[IVX]+|[Ⅰ-Ⅻ]+)[）)]?$/u.test(valueText(unit.text).trim());
    (function index(node, parent = null) {
      byNodeId.set(node.id, node);
      if (parent) parentNodes.set(node, parent);
      if (paper.category === 'math3') {
        for (const unit of node.units || []) {
          if (node.title === 'Unassigned source material' || isMathVariant(unit)) {
            mathSourceUnits.push(unit);
          }
        }
      }
      if (['material', 'passage'].includes(node.type)) {
        for (const unit of node.units || []) {
          if (unit.provenance?.jsonPath?.includes('.context.text')) {
            structuredContexts.push(valueText(unit.text).replace(/\s+/g, ''));
          }
        }
      }
      for (const child of node.children || []) index(child, node);
    })(root);
    const renderedMaterials = new Set();
    const renderedPassageGroups = new Set();
    const renderedUnitNodes = new Set();
    const renderedSourceTexts = new Set();
    let renderedSourceText = '';
    const seenBlocks = new Set();
    const seenContexts = new Set();
    const fragment = document.createDocumentFragment();
    // A compiler fallback can own cover notes despite occurring after several
    // real sections in the tree. Place those units by their original block
    // positions; variant titles can also belong to the previous question.
    const sourcePosition = id => {
      const match = /:b-(\d+)-(\d+)$/.exec(sourceBlockId(id));
      return match ? [Number(match[1]), Number(match[2])] : null;
    };
    const positionAfter = (left, right) => left && right &&
      (left[0] > right[0] || (left[0] === right[0] && left[1] > right[1]));
    const mathSourceEvents = new Map();
    const seenMathText = new Set();
    for (const unit of mathSourceUnits.sort((a, b) => {
      const x = sourcePosition(a.provenance?.sourceBlockId) || [Infinity, 0];
      const y = sourcePosition(b.provenance?.sourceBlockId) || [Infinity, 0];
      return x[0] - y[0] || x[1] - y[1];
    })) {
      const id = unit.provenance?.sourceBlockId;
      const position = id && sourcePosition(id);
      const body = valueText(unit.text).trim();
      if (!position || !body) continue;
      seenBlocks.add(`${id}\u0000${body}`);
      const textKey = body.replace(/\s+/g, '');
      if (seenMathText.has(textKey)) continue;
      seenMathText.add(textKey);
      const index = questions.findIndex(question =>
        positionAfter(sourcePosition(question.sourceBlocks?.[0]), position));
      const anchor = index < 0 ? questions.length : index;
      if (!mathSourceEvents.has(anchor)) mathSourceEvents.set(anchor, []);
      mathSourceEvents.get(anchor).push(unit);
    }

    function appendTitle(node, target) {
      if (node.title && !(paper.category === 'math3' &&
          node.title === 'Unassigned source material') &&
          !(['material', 'passage'].includes(node.type) &&
          /^[a-z][a-z0-9_]*$/.test(node.title))) {
        target.append(element(node.type === 'section' ? 'h3' : 'h4',
          'paper-section-title', node.title));
      }
    }

    function appendUnits(node, target) {
      if (renderedUnitNodes.has(node)) return false;
      renderedUnitNodes.add(node);
      let added = false;
      let activePassage = null;
      let direction = null;
      let expectsInstruction = false;
      const underReading = (() => {
        for (let parent = node; parent; parent = parentNodes.get(parent)) {
          if (parent.type === 'section' && /^Section II Reading Comprehension$/i.test(parent.title || '')) return true;
        }
        return false;
      })();
      const sectionPassage = paper.category === 'kaoyan' && underReading &&
        node.type === 'section' && (/^Text\s+\d+$/i.test(node.title || '') ||
          /^Part [BC]$/i.test(node.title || ''));
      for (const unit of node.units || []) {
        const sourceId = unit.provenance?.sourceBlockId;
        const owner = passageOwners.get(sourceId) ||
          (sectionPassage && ['paragraph', 'figure', 'code', 'formula'].includes(unit.type) &&
            !expectsInstruction ? {id: node.id} : null);
        const item = renderSemanticUnit(unit, seenBlocks, node.title, structuredContexts,
          imageBase, Boolean(owner) || expectsInstruction || instructionIds.has(sourceId),
          sectionPassage && /^Part C$/i.test(node.title || ''),
          wordBankSourceIds.has(sourceId));
        if (!item) continue;
        if (sourceId && valueText(unit.text).trim()) {
          const sourceText = valueText(unit.text).replace(/\s+/g, '');
          renderedSourceTexts.add(sourceText);
          renderedSourceText += sourceText;
        }
        if (unit.text?.trim() === 'Directions:') {
          direction = element('div', 'paper-directions');
          direction.append(element('strong', 'paper-directions-label', 'Directions:'));
          target.append(direction);
          expectsInstruction = true;
          activePassage = null;
          added = true;
          continue;
        }
        if (expectsInstruction || instructionIds.has(unit.provenance?.sourceBlockId)) {
          if (!direction) {
            direction = element('div', 'paper-directions');
            direction.append(element('strong', 'paper-directions-label', 'Directions:'));
            target.append(direction);
          }
          item.classList.add('paper-instruction');
          direction.append(item);
          expectsInstruction = false;
          activePassage = null;
          added = true;
          continue;
        }
        if (owner) {
          if (!activePassage || activePassage.dataset.groupId !== owner.id) {
            activePassage = element('div', 'paper-shared-material paper-passage');
            activePassage.dataset.groupId = owner.id;
            if (owner.text && owner.kind !== 'cloze' && !renderedPassageGroups.has(owner.id)) {
              activePassage.append(element('h4', 'paper-section-title paper-passage-title', owner.text));
            }
            target.append(activePassage);
          }
          activePassage.append(item);
          renderedPassageGroups.add(owner.id);
        } else {
          activePassage = null;
          target.append(item);
        }
        added = true;
      }
      return added;
    }

    function renderSourceNode(node, target) {
      if (!node || node.suppressionReason === 'answer_document_requires_explicit_route' ||
          node.type === 'answer' || node.type === 'option' || node.type === 'question') return;
      if (node.type === 'section' && node.title === 'Unassigned source material') {
        // A few partial source papers keep the writing prompt outside the
        // numbered question tree. The cover title and Chinese notes are not
        // practice material, but the Directions and their figure still are.
        const prompt = (node.units || []).findIndex(unit =>
          /Directions:/i.test(valueText(unit.text)) &&
          (valueText(unit.text).match(/[A-Za-z]+/g) || []).length >= 4);
        if (prompt < 0) return;
        const wrapper = element('section', 'paper-shared-material paper-unassigned-prompt');
        for (const unit of node.units.slice(prompt)) {
          if (unit.type !== 'figure' && unit !== node.units[prompt]) break;
          const item = renderSemanticUnit(unit, seenBlocks, '', structuredContexts,
            imageBase, true);
          if (item) wrapper.append(item);
        }
        if (wrapper.childNodes.length) target.append(wrapper);
        return;
      }
      const heading = target.querySelector(':scope > .paper-section-title')?.textContent.trim();
      if (heading && !(node.children || []).length && (node.units || []).length === 1 &&
          valueText(node.units[0].text).trim() === heading) return;
      if (['material', 'passage'].includes(node.type)) {
        if (renderedMaterials.has(node.id)) return;
        renderedMaterials.add(node.id);
      }
      const wrapper = element('section', node.type === 'section' ? 'paper-section' : 'paper-shared-material');
      appendTitle(node, wrapper);
      appendUnits(node, wrapper);
      for (const child of node.children || []) renderSourceNode(child, wrapper);
      const titleOnly = wrapper.children.length === 1 &&
        wrapper.firstElementChild.classList.contains('paper-section-title');
      if (wrapper.childNodes.length && !titleOnly) target.append(wrapper);
    }

    function renderQuestionNode(node, entry, target, hasSharedUnits) {
      const linked = (node?.links || []).map(link => ({link, target: byNodeId.get(link.toNodeId)}))
        .filter(item => item.target && ['material', 'passage'].includes(item.target.type));
      const sharedContext = linked.filter(item => item.link.type === 'shared_context');
      const label = Array.isArray(entry.question.labels) ? entry.question.labels[0] : null;
      const firstPassageBlock = entry.question.context?.passageSourceBlocks?.[0];
      const passageOwner = firstPassageBlock && passageOwners.get(sourceBlockId(firstPassageBlock));
      const sourcePassageShown = (label?.id && renderedPassageGroups.has(label.id)) ||
        (passageOwner && renderedPassageGroups.has(passageOwner.id));
      for (const item of sharedContext) {
        const significantUnits = (item.target.units || []).map(unit =>
          valueText(unit.text).replace(/\s+/g, '')).filter(text => text.length >= 20);
        const sourceContextShown = significantUnits.length > 0 &&
          significantUnits.every(text => renderedSourceTexts.has(text) ||
            renderedSourceText.includes(text));
        if (sourcePassageShown || sourceContextShown) renderedMaterials.add(item.target.id);
        else renderSourceNode(item.target, target);
      }
      const context = entry.question.context;
      const contextId = context && typeof context === 'object' ? context.id : null;
      const showContext = !hasSharedUnits && !sharedContext.length && !sourcePassageShown &&
        (!contextId || !seenContexts.has(contextId));
      if (showContext && contextId) seenContexts.add(contextId);
      const card = renderCard(entry.question, entry.index, seenBlocks, showContext, paper);
      const rawStem = valueText(entry.question.stem).trim();
      const stem = rawStem.replace(/^\s*\(?\d+\)?[.)]?\s*/, '')
        .replace(/\s+/g, '');
      const repeatedMatchingMaterial = label?.kind === 'matching' && stem.length >= 100 &&
        renderedSourceText.includes(stem);
      const bareGroupNumber = Boolean(context && label?.kind === 'matching' &&
        /^\d+[.)]?$/.test(rawStem));
      if (repeatedMatchingMaterial || bareGroupNumber) {
        card.querySelector('.question-stem')?.remove();
      }
      target.append(card);
      const cardContent = card.querySelector('.question-content');
      const contentAnchor = cardContent?.firstChild || null;
      let directionsGroup = null;
      // Section transitions and instructions can be attached to the preceding
      // question in the semantic tree even though they follow it on the page.
      // Only render these recognizable trailing source units; other question
      // units mostly restate stems and answer choices.
      for (const unit of node?.units || []) {
        const text = valueText(unit.text).trim();
        const continuationId = unit.provenance?.sourceBlockId;
        const contextSegments = valueText(context?.text).split(/\n\s*\n/)
          .map(segment => segment.replace(/\s+/g, '')).filter(Boolean);
        const isContextContinuation = ['cet4', 'cet6'].includes(paper.category) &&
          entry.question.questionType === 'free_response' && continuationId &&
          (context?.sourceBlocks || []).some(id => sourceBlockId(id) === continuationId) &&
          !(entry.question.contentBlocks || []).some(block => block.id === continuationId) &&
          contextSegments.includes(text.replace(/\s+/g, ''));
        const isTransition = (text.match(/[A-Za-z]+/g) || []).length >= 4 &&
          /^(?:Directions:|Part\s*[\]\[]|Now, listen to Part\s+)/i.test(text);
        if (unit.type !== 'other' || (!isTransition && !isContextContinuation)) continue;
        const item = renderSemanticUnit(unit, seenBlocks, '', structuredContexts,
          imageBase, true);
        if (!item) continue;
        item.classList.add(/^Part\s/i.test(text) ?
          'paper-transition-heading' : 'paper-transition-instruction');
        const contextOrder = (context?.sourceBlocks || [])
          .map(id => sourceBlockId(id));
        const firstContentIndex = contextOrder.indexOf(
          entry.question.contentBlocks?.[0]?.id);
        const isDirectionsPrefix = isContextContinuation &&
          context?.kind === 'translation_passage' && cardContent &&
          (firstContentIndex < 0 ||
            contextOrder.indexOf(continuationId) < firstContentIndex);
        if (isDirectionsPrefix) {
          if (!directionsGroup) {
            const instructionId = context?.instructionSourceBlocks?.[0];
            const qualifiedId = instructionId && sourceBlockId(instructionId);
            directionsGroup = qualifiedId &&
              [...target.querySelectorAll('.paper-directions')].find(group =>
                [...group.querySelectorAll('[data-source-block-id]')]
                  .some(source => source.dataset.sourceBlockId === qualifiedId));
            if (!directionsGroup) {
              directionsGroup = element('div', 'paper-directions');
              cardContent.insertBefore(directionsGroup, contentAnchor);
            }
          }
          directionsGroup.append(item);
        } else target.append(item);
      }
      for (const item of linked.filter(item => item.link.type === 'continuation')) {
        renderSourceNode(item.target, target);
      }
    }

    const questionNodes = new Map();
    const paths = new Map();
    const events = [];
    const containsQuestion = new Map();
    function hasQuestion(node) {
      const childResults = (node.children || []).map(hasQuestion);
      const found = (node.type === 'question' && byQuestionId.has(node.questionId)) ||
        childResults.some(Boolean);
      containsQuestion.set(node, found);
      return found;
    }
    hasQuestion(root);
    function collect(node, path) {
      if (node.type === 'question') {
        if (byQuestionId.has(node.questionId)) {
          questionNodes.set(node.questionId, node);
          paths.set(node.questionId, path);
          events.push({type: 'question', node});
        }
        return;
      }
      if (node !== root && !containsQuestion.get(node) &&
          ['section', 'material', 'passage'].includes(node.type)) {
        events.push({type: 'source', node, path});
        return;
      }
      const nextPath = ['section', 'material', 'passage'].includes(node.type) ? [...path, node] : path;
      for (const child of node.children || []) collect(child, nextPath);
    }
    collect(root, []);
    const sourceEvents = new Map();
    for (const [eventIndex, event] of events.entries()) {
      if (event.type !== 'source') continue;
      const next = events.slice(eventIndex + 1).find(item => item.type === 'question');
      const anchor = event.node.title === 'Unassigned source material' ? 0 :
        next ? byQuestionId.get(next.node.questionId).index : questions.length;
      if (!sourceEvents.has(anchor)) sourceEvents.set(anchor, []);
      sourceEvents.get(anchor).push(event);
    }

    appendUnits(root, fragment);
    let currentPath = [];
    let containers = [fragment];
    function ensurePath(path) {
      let common = 0;
      while (common < currentPath.length && common < path.length &&
          currentPath[common] === path[common]) common++;
      currentPath = currentPath.slice(0, common);
      containers = containers.slice(0, common + 1);
      for (const node of path.slice(common)) {
        const wrapper = element('section', node.type === 'section' ? 'paper-section' : 'paper-shared-material');
        appendTitle(node, wrapper);
        appendUnits(node, wrapper);
        containers.at(-1).append(wrapper);
        containers.push(wrapper);
        currentPath.push(node);
      }
      return {target: containers.at(-1),
        hasSharedUnits: path.some(node => (node.units || []).length > 0)};
    }
    for (let index = 0; index <= questions.length; index++) {
      for (const unit of mathSourceEvents.get(index) || []) {
        ensurePath([]);
        const item = isMathVariant(unit) ?
          element('h3', 'paper-section-title', valueText(unit.text).trim()) :
          renderSemanticUnit(unit, new Set(), '', structuredContexts, imageBase, true);
        if (item) {
          item.dataset.sourceBlockId = unit.provenance.sourceBlockId;
          fragment.append(item);
        }
      }
      for (const event of sourceEvents.get(index) || []) {
        const {target} = ensurePath(event.path);
        renderSourceNode(event.node, target);
      }
      if (index === questions.length) break;
      const question = questions[index];
      const {target, hasSharedUnits} = ensurePath(paths.get(question.id) || []);
      renderQuestionNode(questionNodes.get(question.id), {question, index}, target, hasSharedUnits);
    }
    return fragment;
  }

  function renderTableOfContents() {
    const placeholder = new Option('选择章节或题目', '');
    ui.toc.replaceChildren(placeholder);
    let sectionIndex = 0;
    for (const node of ui.questions.querySelectorAll('.paper-section-title, .question-card')) {
      if (node.classList.contains('paper-section-title')) {
        if (node.classList.contains('paper-passage-title')) continue;
        node.id = `paper-section-${++sectionIndex}`;
        let depth = -1;
        for (let parent = node.parentElement; parent; parent = parent.parentElement) {
          if (parent.classList.contains('paper-section')) depth++;
        }
        ui.toc.append(new Option(`${'　'.repeat(Math.max(0, depth))}${node.textContent.trim()}`, node.id));
      } else {
        const title = node.querySelector('.question-number')?.textContent.trim();
        if (title) ui.toc.append(new Option(`　${title}`, node.id));
      }
    }
    const current = location.hash.slice(1);
    if ([...ui.toc.options].some(option => option.value === current)) ui.toc.value = current;
  }

  function scrollToElement(node) {
    if (node && typeof node.scrollIntoView === 'function') {
      node.scrollIntoView({block: 'start', behavior: 'instant'});
    }
  }

  function renderImmersiveDirectory() {
    ui.toc.replaceChildren(new Option('选择大题', ''));
    ui.directory.replaceChildren();
    let sectionName = '';
    for (const group of immersiveState.groups) {
      const first = group.cards[0].querySelector('.question-number')?.textContent.trim() || '';
      const last = group.cards.at(-1).querySelector('.question-number')?.textContent.trim() || '';
      const range = first === last ? first : `${first}–${last}`;
      const firstNumber = group.cards[0].querySelector('.question-number')?.dataset.shortNumber || '';
      const lastNumber = group.cards.at(-1).querySelector('.question-number')?.dataset.shortNumber || '';
      const shortRange = firstNumber === lastNumber ? firstNumber : `${firstNumber}–${lastNumber}`;
      const rangeLabel = /^\d+(?:–\d+)?$/.test(shortRange) ? `第 ${shortRange} 题` : shortRange;
      ui.toc.append(new Option(`${group.label} · ${range}`, group.id));
      const path = group.label.split(' / ');
      if (path[0] !== sectionName) {
        sectionName = path[0];
        ui.directory.append(element('h3', 'immersive-directory-section', sectionName));
      }
      const button = element('button', 'immersive-directory-item');
      button.type = 'button';
      button.dataset.groupId = group.id;
      button.append(element('span', 'immersive-directory-name',
        path.length > 1 ? path.slice(1).join(' · ') : rangeLabel));
      if (path.length > 1) button.append(element('span', 'immersive-directory-range', rangeLabel));
      button.addEventListener('click', () => {
        history.pushState(null, '', `#${group.id}`);
        navigateImmersive(group.id);
      });
      ui.directory.append(button);
    }
  }

  function fitReadingPage() {
    if (!immersiveState) return;
    const content = ui.questions;
    const viewport = ui.readingPage;
    viewport.classList.remove('is-overflowing');
    content.style.zoom = '1';
    content.style.removeProperty('--immersive-cloze-font-size');
    content.classList.remove('immersive-two-column');
    if (immersiveState.activeGroup?.isCloze) {
      const available = viewport.getBoundingClientRect().height - 1;
      const target = available * .94;
      let low = 14;
      let high = 26;
      const measure = size => {
        content.style.setProperty('--immersive-cloze-font-size', `${size}px`);
        return content.getBoundingClientRect().height;
      };
      if (measure(low) <= target) {
        for (let count = 0; count < 12; count++) {
          const middle = (low + high) / 2;
          if (measure(middle) <= target) low = middle;
          else high = middle;
        }
      }
      measure(low);
      if (content.getBoundingClientRect().height > available) {
        content.style.zoom = String(Math.max(.1,
          available / content.getBoundingClientRect().height * .99));
      }
      viewport.classList.toggle('is-overflowing', content.getBoundingClientRect().height > available);
      return;
    }
    const fits = () => content.getBoundingClientRect().height <=
      viewport.getBoundingClientRect().height - 1;
    if (fits()) return;
    content.classList.add('immersive-two-column');
    if (fits()) return;
    let low = .55;
    let high = 1;
    content.style.zoom = String(low);
    while (!fits() && low > .12) {
      low *= .85;
      content.style.zoom = String(low);
    }
    for (let count = 0; count < 12; count++) {
      const middle = (low + high) / 2;
      content.style.zoom = String(middle);
      if (fits()) low = middle;
      else high = middle;
    }
    content.style.zoom = String(low);
    viewport.classList.toggle('is-overflowing', !fits());
  }

  function navigateImmersive(id) {
    if (!immersiveState) return;
    const {groups} = immersiveState;
    const group = groups.find(item => item.id === id || item.cards.some(card => card.id === id)) ||
      groups.find(item => item.section?.contains(byId(id))) || groups[0];
    if (!group) return;
    const card = group.cards.find(item => item.id === id) || group.cards[0];
    resetImmersiveOptionReview();
    const changed = immersiveState.activeGroup !== group;
    immersiveState.activeGroup = group;
    focusReadingSection(group.section || group.source, true);
    const firstNumber = group.cards[0].querySelector('.question-number')?.dataset.shortNumber;
    const lastNumber = group.cards.at(-1).querySelector('.question-number')?.dataset.shortNumber;
    const range = firstNumber === lastNumber ? firstNumber : `${firstNumber}–${lastNumber}`;
    ui.questionContext.textContent = group.isCloze ? `共 ${group.cards.length} 空` :
      `${group.shortLabel}${range ? ` · ${/^\d+(?:–\d+)?$/.test(range) ? `${range} 题` : range}` : ''}`;
    ui.immersiveQuestions.classList.toggle('is-cloze', group.isCloze);
    ui.immersiveQuestions.classList.toggle('is-matching', group.isMatching);
    ui.workspace.classList.toggle('is-cloze', group.isCloze);
    ui.workspace.classList.toggle('is-matching', group.isMatching);
    ui.workspace.classList.toggle('is-translation', group.kind === 'translation');
    ui.reading.classList.toggle('is-passage', ['cloze', 'reading'].includes(group.kind));
    ui.reading.classList.toggle('is-cloze', group.isCloze);
    ui.groupCheck.hidden = !(group.isCloze || group.isMatching);
    ui.groupCheck.disabled = false;
    ui.groupCheck.textContent = group.checked ? '重新作答' : (group.checkLabel || '核对本组');
    ui.questionTabs.replaceChildren();
    if (!group.isCloze && !group.isMatching && group.cards.length > 1) {
      for (const item of group.cards) {
        const button = element('button', '', item.querySelector('.question-number')?.dataset.shortNumber || '题目');
        button.type = 'button';
        button.setAttribute('aria-label', item.querySelector('.question-number')?.textContent.trim() || '题目');
        button.classList.toggle('is-active', item === card);
        button.setAttribute('aria-current', item === card ? 'true' : 'false');
        button.addEventListener('click', () => {
          history.pushState(null, '', `#${item.id}`);
          navigateImmersive(item.id);
        });
        ui.questionTabs.append(button);
      }
    }
    ui.questionTabs.hidden = group.isCloze || group.isMatching || group.cards.length <= 1;
    for (const item of immersiveState.cards) {
      item.hidden = group.isCloze || group.isMatching ? !group.cards.includes(item) : item !== card;
    }
    if (!group.isCloze && !group.isMatching) fitImmersiveQuestion(card);
    if (changed) {
      resetImmersiveTranslationReview();
      fitReadingPage();
    }
    ui.toc.value = group.id;
    for (const button of ui.directory.querySelectorAll('.immersive-directory-item')) {
      const active = button.dataset.groupId === group.id;
      button.classList.toggle('is-active', active);
      if (active) button.setAttribute('aria-current', 'true');
      else button.removeAttribute('aria-current');
    }
  }

  function focusReadingSection(source, includeDescendants = false) {
    const group = source?.closest('.paper-section');
    for (const section of ui.questions.querySelectorAll('.paper-section')) {
      section.hidden = Boolean(group && section !== group && !section.contains(group) &&
        !(includeDescendants && group.contains(section)));
    }
  }

  function fitImmersiveQuestion(card) {
    card.classList.remove('immersive-dense');
    if (card.scrollHeight > card.clientHeight + 2) card.classList.add('immersive-dense');
  }

  function sourceBlocksForCard(card, question) {
    const sources = [];
    const context = card.querySelector('.question-context');
    if (context) sources.push(context);
    const kind = question?.labels?.[0]?.kind ||
      (question?.context?.kind === 'writing_task' ? 'writing' :
        question?.context?.kind === 'translation_passage' ? 'translation' : null);
    if (kind === 'writing') {
      const stem = card.querySelector('.question-stem');
      const writingContent = card.querySelector('.question-content');
      if (stem) sources.push(stem);
      if (writingContent?.textContent.trim() || writingContent?.querySelector('img')) {
        sources.push(writingContent);
      }
      return sources;
    }
    const content = card.querySelector('.question-content');
    if (!content) return sources;
    if (kind === 'translation' &&
        (question?.context?.kind === 'translation_passage' ||
          content.textContent.trim().length >= 120 || content.querySelector('img'))) {
      sources.push(content);
    }
    return sources;
  }

  function enterImmersive() {
    const cards = [...ui.questions.querySelectorAll('.question-card')];
    if (!cards.length) return;
    const questionById = new Map(loadedQuestions.map(question => [question.id, question]));
    const sources = new Map();
    let source = null;
    for (const node of ui.questions.querySelectorAll('.paper-section-title, .paper-shared-material, .question-card')) {
      if (node.classList.contains('paper-section-title') && !node.classList.contains('paper-passage-title')) {
        source = node;
      } else if (node.classList.contains('paper-shared-material') && node.textContent.trim()) {
        source = node;
      } else if (node.classList.contains('question-card')) {
        sources.set(node.id, source);
      }
    }
    const placements = [];
    const paths = new Map();
    const groups = [];
    const groupBySection = new Map();
    for (const card of cards) {
      const path = [];
      for (let parent = card.parentElement; parent && parent !== ui.questions; parent = parent.parentElement) {
        const title = parent.querySelector(':scope > .paper-section-title')?.textContent.trim();
        if (title) path.unshift(title);
      }
      const pathLabel = path.join(' / ');
      paths.set(card.id, pathLabel);
      const section = card.parentElement.closest('.paper-section');
      let group = section && groupBySection.get(section);
      if (!group) {
        const heading = section?.querySelector(':scope > .paper-section-title');
        group = {id: heading?.id || card.id, section, source: sources.get(card.id),
          label: pathLabel || '题目', shortLabel: heading?.textContent.trim() || path.at(-1) || '题目',
          cards: [], isCloze: false, kind: ''};
        groups.push(group);
        if (section) groupBySection.set(section, group);
      }
      group.cards.push(card);
      const placeholder = document.createComment(`original position of ${card.id}`);
      card.before(placeholder);
      const sourceBlocks = sourceBlocksForCard(card, questionById.get(card.dataset.questionId));
      let sourceHolder = null;
      if (sourceBlocks.length) {
        sourceHolder = element('div', 'immersive-card-source');
        for (const block of sourceBlocks) {
          const copy = block.cloneNode(true);
          copy.querySelectorAll('[id]').forEach(item => item.removeAttribute('id'));
          sourceHolder.append(copy);
          block.classList.add('immersive-source-hidden');
        }
        placeholder.before(sourceHolder);
        sources.set(card.id, sourceHolder);
      }
      placements.push({card, placeholder, sourceHolder, sourceBlocks});
      card.hidden = true;
      ui.immersiveQuestions.append(card);
    }
    for (const group of groups) {
      const firstQuestion = questionById.get(group.cards[0].dataset.questionId);
      group.kind = firstQuestion?.labels?.[0]?.kind ||
        (firstQuestion?.context?.kind === 'writing_task' ? 'writing' :
          firstQuestion?.context?.kind === 'translation_passage' ? 'translation' : '');
      group.isCloze = group.cards.length > 1 && group.cards.every(card =>
        questionById.get(card.dataset.questionId)?.labels?.some(label => label.kind === 'cloze'));
      const sourceText = group.section?.textContent.replace(/\s+/g, '') || '';
      const optionTexts = [...group.cards[0].querySelectorAll('.option-text')]
        .map(option => option.textContent.replace(/\s+/g, ''));
      group.isMatching = group.kind === 'matching' && group.cards.length > 1 &&
        optionTexts.length >= 4 && optionTexts.every(text =>
          text.length >= 40 && sourceText.includes(text.slice(0, 40)));
    }
    immersiveState = {placements, cards, paths, sources, groups, activeGroup: null,
      pageScroll: document.scrollingElement?.scrollTop || 0};
    ui.readingPage.append(ui.questions);
    ui.workspace.hidden = false;
    ui.immersiveTitle.hidden = false;
    ui.immersiveToggle.textContent = '退出沉浸';
    ui.immersiveToggle.setAttribute('aria-pressed', 'true');
    document.body.classList.add('full-paper-immersive');
    updateTranslationToggleLabel();
    if (document.scrollingElement) document.scrollingElement.scrollTop = 0;
    renderImmersiveDirectory();
    const current = location.hash.slice(1);
    navigateImmersive(byId(current) ? current : cards[0].id);
  }

  function exitImmersive() {
    if (!immersiveState) return;
    for (const {card, placeholder, sourceHolder, sourceBlocks} of immersiveState.placements) {
      card.hidden = false;
      card.classList.remove('immersive-dense');
      placeholder.replaceWith(card);
      sourceHolder?.remove();
      sourceBlocks.forEach(block => block.classList.remove('immersive-source-hidden'));
    }
    ui.questions.querySelectorAll('.paper-section[hidden]').forEach(section => { section.hidden = false; });
    ui.workspace.before(ui.questions);
    ui.questions.style.zoom = '';
    ui.questions.classList.remove('immersive-two-column');
    resetImmersiveTranslationReview();
    resetImmersiveOptionReview();
    ui.immersiveQuestions.replaceChildren(ui.groupBar, ui.questionTabs);
    optionOverlay = null;
    ui.immersiveQuestions.classList.remove('is-cloze');
    ui.immersiveQuestions.classList.remove('is-matching');
    ui.workspace.classList.remove('is-cloze');
    ui.workspace.classList.remove('is-matching');
    ui.workspace.classList.remove('is-translation');
    ui.reading.classList.remove('is-passage');
    ui.workspace.hidden = true;
    ui.immersiveTitle.hidden = true;
    ui.immersiveToggle.textContent = '沉浸模式';
    ui.immersiveToggle.setAttribute('aria-pressed', 'false');
    document.body.classList.remove('full-paper-immersive');
    const previousScroll = immersiveState.pageScroll;
    immersiveState = null;
    updateTranslationToggleLabel();
    renderTableOfContents();
    const target = byId(location.hash.slice(1));
    if (target) scrollToElement(target);
    else if (document.scrollingElement) document.scrollingElement.scrollTop = previousScroll;
  }

  ui.immersiveToggle.addEventListener('click', () => {
    try {
      if (immersiveState) exitImmersive();
      else enterImmersive();
    } catch (error) {
      console.error('沉浸模式切换失败', error);
      setStatus('沉浸模式切换失败：' + error.message, true);
    }
  });
  ui.readingPage.addEventListener('click', event => {
    if (event.target.closest('.immersive-option-translation-overlay')) {
      resetImmersiveOptionReview();
      return;
    }
    if (event.target.closest('#immersive-translation-overlay')) {
      resetImmersiveTranslationReview();
      return;
    }
    const node = event.target.closest('.paper-translatable-source');
    if (node && ui.readingPage.contains(node) && node.dataset.translationKey) {
      selectImmersiveTranslation(node);
    }
  });
  ui.readingPage.addEventListener('keydown', event => {
    if (event.key === 'Escape' && optionOverlay && !optionOverlay.hidden) {
      resetImmersiveOptionReview();
      return;
    }
    if ((event.key === 'Enter' || event.key === ' ') &&
        event.target.closest('.immersive-option-translation-overlay')) {
      event.preventDefault();
      resetImmersiveOptionReview();
      return;
    }
    if (event.key === 'Escape' && !ui.translationOverlay.hidden) {
      resetImmersiveTranslationReview();
      return;
    }
    if (event.key !== 'Enter' && event.key !== ' ') return;
    if (event.target.closest('#immersive-translation-overlay')) {
      event.preventDefault();
      resetImmersiveTranslationReview();
      return;
    }
    const node = event.target.closest('.paper-translatable-source');
    if (node && ui.readingPage.contains(node) && node.dataset.translationKey) {
      event.preventDefault();
      selectImmersiveTranslation(node);
    }
  });
  ui.immersiveQuestions.addEventListener('click', event => {
    if (event.target.closest('.immersive-option-translation-overlay')) {
      resetImmersiveOptionReview();
      return;
    }
    const option = event.target.closest('.option');
    if (option && ui.immersiveQuestions.contains(option)) {
      selectImmersiveOptionTranslation(option);
    } else resetImmersiveOptionReview();
  });
  ui.immersiveQuestions.addEventListener('mouseover', event => {
    const option = event.target.closest('.option');
    if (option && ui.immersiveQuestions.contains(option)) {
      selectImmersiveOptionTranslation(option, false);
    }
  });
  ui.immersiveQuestions.addEventListener('focusin', event => {
    const option = event.target.closest('.option');
    if (option && ui.immersiveQuestions.contains(option)) {
      selectImmersiveOptionTranslation(option, false);
    }
  });
  ui.immersiveQuestions.addEventListener('keydown', event => {
    if (event.key === 'Escape' && optionOverlay && !optionOverlay.hidden) {
      resetImmersiveOptionReview();
      return;
    }
    if ((event.key === 'Enter' || event.key === ' ') &&
        event.target.closest('.immersive-option-translation-overlay')) {
      event.preventDefault();
      resetImmersiveOptionReview();
    }
  });
  ui.translationToggle.addEventListener('click', async () => {
    if (!translationPaper || ui.translationToggle.disabled) return;
    if (translationsLoaded) {
      setTranslationsVisible(ui.translationToggle.getAttribute('aria-pressed') !== 'true');
      return;
    }
    ui.translationToggle.disabled = true;
    ui.translationToggle.textContent = '正在加载译文…';
    const count = await loadParagraphTranslations(translationPaper);
    ui.translationToggle.disabled = false;
    if (count) {
      translationsLoaded = true;
      setTranslationsVisible(true);
    } else {
      ui.translationToggle.textContent = '重试加载译文';
      ui.translationToggle.title = '当前没有可显示的段落译文，可稍后重试';
    }
  });
  ui.groupCheck.addEventListener('click', async () => {
    const group = immersiveState?.activeGroup;
    if (!(group?.isCloze || group?.isMatching)) return;
    if (group.checked) {
      group.cards.forEach(card => resetAnswer(card));
      group.checked = false;
      group.checkLabel = null;
      ui.groupCheck.textContent = '核对本组';
      return;
    }
    ui.groupCheck.disabled = true;
    ui.groupCheck.textContent = '正在核对…';
    const results = await Promise.all(group.cards.map(card => card.revealAnswer({forGroup: true})));
    const checked = results.filter(result => result.status === 'checked').length;
    const errors = results.filter(result => result.status === 'error').length;
    group.checked = checked === group.cards.length;
    group.checkLabel = group.checked ? null : checked ? `${checked}/${group.cards.length} 已核对 · 重试` :
      errors ? '读取失败 · 重试' : '暂无参考答案 · 重试';
    ui.groupCheck.textContent = group.checked ? '重新作答' : group.checkLabel;
    ui.groupCheck.disabled = false;
  });
  window.addEventListener('resize', () => {
    if (!immersiveState) return;
    resetImmersiveTranslationReview();
    resetImmersiveOptionReview();
    fitReadingPage();
  });
  ui.readingPage.addEventListener('load', () => {
    if (!immersiveState) return;
    resetImmersiveTranslationReview();
    fitReadingPage();
  }, true);
  ui.toc.addEventListener('change', () => {
    if (!ui.toc.value) return;
    if (immersiveState) {
      if (location.hash !== `#${ui.toc.value}`) history.pushState(null, '', `#${ui.toc.value}`);
      navigateImmersive(ui.toc.value);
    } else location.hash = ui.toc.value;
  });
  window.addEventListener('hashchange', () => {
    const current = location.hash.slice(1);
    if (immersiveState) navigateImmersive(current);
    else if ([...ui.toc.options].some(option => option.value === current)) ui.toc.value = current;
  });
  window.addEventListener('popstate', () => {
    if (immersiveState) navigateImmersive(location.hash.slice(1));
  });

  async function loadPaper() {
    const paperId = new URLSearchParams(location.search).get('paper');
    if (!paperId) { setStatus('请从资料库选择一份题目卷后打开整卷练习。', true); return; }
    try {
      const [data, semantic] = await Promise.all([
        getJson('/api/v1/papers/' + encodeURIComponent(paperId) + '/questions?order=default'),
        getJson('/api/v2/papers/' + encodeURIComponent(paperId) + '/semantic')
      ]);
      if (!data.paper || data.paper.kind === 'answers' || !semantic.root ||
          !Array.isArray(data.questions) || !data.questions.length) {
        setStatus('这份试卷不是可练习的题目卷。', true);
        return;
      }
      ui.category.textContent = data.paper.categoryLabel || data.paper.category || '';
      ui.title.textContent = data.paper.title || paperId;
      document.title = ui.title.textContent + ' · 整卷练习';
      ui.count.textContent = '共 ' + data.questions.length + ' 题 · 原卷顺序';
      ui.immersiveTitle.textContent = ui.title.textContent;
      loadedQuestions = data.questions;
      ui.questions.replaceChildren(renderPaperTree(semantic.root, data.questions, data.paper));
      renderTableOfContents();
      ui.status.hidden = true;
      ui.panel.hidden = false;
      renderMath(ui.questions);
      translationPaper = data.paper;
      ui.translationToggle.hidden = !translationCategories.has(data.paper.category);
      updateTranslationToggleLabel();
    } catch (error) {
      setStatus('试卷加载失败：' + error.message + '。请确认本地题库服务已启动。', true);
    }
  }

  loadPaper();
})();
