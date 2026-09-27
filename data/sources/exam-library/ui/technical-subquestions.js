/* Restore line breaks before numbered subquestions in 408 extended prompts. */
(() => {
  'use strict';

  const configNode = document.getElementById('exam-reader-config');
  let config;
  try { config = JSON.parse(configNode?.textContent || 'null'); } catch (_) { return; }
  if (config?.category !== 'cs408' || config.mode !== 'reflow' || config.kind === 'answers') return;

  const isAnswer = text => /(?:答案要点|参考答案|解答|解析)/.test(text.slice(0, 32));

  function splitSubquestions(paragraph) {
    if (paragraph.dataset.technicalSubquestions === 'true') return;
    const markers = [];
    const walker = document.createTreeWalker(paragraph, NodeFilter.SHOW_TEXT);
    for (let node = walker.nextNode(); node; node = walker.nextNode()) {
      if (node.parentElement?.closest('svg, mjx-container, .formula-source, code')) continue;
      for (const match of node.textContent.matchAll(/[（(]\s*([1-9])\s*[）)]/g)) {
        markers.push({node, offset: match.index, number: Number(match[1])});
      }
    }
    const sequence = [];
    for (const marker of markers) {
      if (marker.number === sequence.length + 1) sequence.push(marker);
    }
    if (sequence.length < 2) return;
    const beforeFirst = document.createRange();
    beforeFirst.setStart(paragraph, 0);
    beforeFirst.setEnd(sequence[0].node, sequence[0].offset);
    const hasIntro = Boolean(beforeFirst.toString().trim());
    // Reverse order keeps text offsets valid when several markers share a node.
    for (let index = sequence.length - 1; index >= 0; index--) {
      if (index === 0 && !hasIntro) continue;
      const {node, offset} = sequence[index];
      const rest = node.splitText(offset);
      const breakNode = document.createElement('br');
      breakNode.className = 'technical-subquestion-break';
      rest.before(breakNode);
    }
    paragraph.dataset.technicalSubquestions = 'true';
  }

  function apply(root = document) {
    let inExtendedQuestion = false;
    for (const block of root.querySelectorAll('main > section[data-source-page] > *')) {
      if (block.matches('h1, h2, h3')) {
        inExtendedQuestion = false;
        continue;
      }
      if (block.matches('p.question')) {
        const label = /^\s*(4[1-7])\s*[.．、]/.exec(block.textContent);
        inExtendedQuestion = Boolean(label) && !isAnswer(block.textContent);
      }
      if (inExtendedQuestion && block.matches('p.paragraph')) splitSubquestions(block);
    }
  }

  window.ExamTechnicalSubquestions = {apply};
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => apply(), {once: true});
  } else {
    apply();
  }
})();
