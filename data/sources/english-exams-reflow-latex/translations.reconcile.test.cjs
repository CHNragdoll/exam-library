/* Reconcile every source-backed translation with the generated reflow HTML. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {webcrypto} = require('node:crypto');
const {TextEncoder} = require('node:util');
const test = require('node:test');
const {JSDOM} = require('jsdom');

const reflow = __dirname;
const sidecars = process.env.TRANSLATION_SIDECAR_ROOT ||
  path.resolve(reflow, '../exam-library/structured/translations');
const script = fs.readFileSync(path.join(reflow, 'translations.js'), 'utf8');

test('every eligible sidecar paragraph and answer option attaches to its reflow source', async () => {
  const manifest = JSON.parse(fs.readFileSync(path.join(reflow, 'manifest.json'), 'utf8'));
  const mismatches = [];
  let papers = 0;
  let eligibleParagraphs = 0;
  let attachedParagraphs = 0;
  let eligibleOptions = 0;
  let attachedOptions = 0;
  let eligiblePdfOptions = 0;
  let attachedPdfOptions = 0;

  for (const category of fs.readdirSync(sidecars)) {
    for (const file of fs.readdirSync(path.join(sidecars, category)).filter(name => name.endsWith('.json'))) {
      const stem = path.basename(file, '.json');
      const directory = path.join(reflow, category, 'papers');
      const sidecar = JSON.parse(fs.readFileSync(path.join(sidecars, category, file), 'utf8'));
      const source = JSON.parse(fs.readFileSync(path.join(directory, file), 'utf8'));
      const html = fs.readFileSync(path.join(directory, `${stem}.htm`), 'utf8');
      const paragraphCount = sidecar.paragraphs.filter(record => record.translationEligible).length;
      const optionCount = (sidecar.options || []).filter(record => record.translationEligible).length;
      const pdfOptionCount = (sidecar.options || []).filter(record =>
        record.translationEligible && record.pdfVerifiedSource && record.reflowBlockId == null).length;
      // The exercise is structural: make every eligible record visible in this
      // isolated DOM without modifying the sidecar on disk.
      sidecar.paragraphs = sidecar.paragraphs.map(record => ({
        ...record, translationZh: record.translationEligible ? '核对译文' : null
      }));
      sidecar.options = (sidecar.options || []).map(record => ({
        ...record, translationZh: record.translationEligible ? '核对译文' : null
      }));

      const dom = new JSDOM(html, {
        url: `http://localhost/exam-library/data/sources/english-exams-reflow-latex/${category}/papers/${stem}.htm`,
        runScripts: 'outside-only'
      });
      const {window} = dom;
      window.TextEncoder = TextEncoder;
      Object.defineProperty(window.crypto, 'subtle', {value: webcrypto.subtle});
      const requests = [];
      window.fetch = async url => {
        requests.push(String(url));
        return {ok: true, json: async () =>
          String(url).includes('/structured/translations/') ? sidecar : source};
      };
      window.eval(script);
      window.dispatchEvent(new window.Event('load'));
      assert.equal(requests.length, 0, `${category}/${stem}: fetched before reveal`);
      const button = window.document.querySelector('.paragraph-translation-toggle');
      assert(button, `${category}/${stem}: missing translation control`);
      button.click();
      const paper = window.document.querySelector('main.paper');
      for (let attempt = 0; attempt < 200 && !paper.dataset.translationAttached; attempt++) {
        await new Promise(resolve => setTimeout(resolve, 5));
      }
      const attachedParagraphCount = Number(paper.dataset.translationParagraphsAttached || 0);
      const attachedOptionCount = Number(paper.dataset.translationOptionsAttached || 0);
      const attachedPdfOptionCount = Number(paper.dataset.translationPdfOptionsAttached || 0);
      const skipped = Number(paper.dataset.translationSkipped || 0);
      if (attachedParagraphCount !== paragraphCount || attachedOptionCount !== optionCount ||
          attachedPdfOptionCount !== pdfOptionCount || skipped) {
        mismatches.push({paper: `${category}/${stem}`, paragraphCount, attachedParagraphCount,
          optionCount, attachedOptionCount, pdfOptionCount, attachedPdfOptionCount, skipped});
      }
      papers++;
      eligibleParagraphs += paragraphCount;
      attachedParagraphs += attachedParagraphCount;
      eligibleOptions += optionCount;
      attachedOptions += attachedOptionCount;
      eligiblePdfOptions += pdfOptionCount;
      attachedPdfOptions += attachedPdfOptionCount;
      window.close();
    }
  }
  assert.equal(papers, manifest.documents);
  assert.deepEqual(mismatches.slice(0, 20), [], `${mismatches.length} papers have unmatched translations`);
  assert.equal(attachedParagraphs, eligibleParagraphs);
  assert.equal(attachedOptions, eligibleOptions);
  assert.equal(attachedPdfOptions, eligiblePdfOptions);
  console.log(`reconciled ${papers} papers: paragraphs ${attachedParagraphs}/${eligibleParagraphs}, ` +
    `options ${attachedOptions}/${eligibleOptions}, PDF-only ${attachedPdfOptions}/${eligiblePdfOptions}`);
});
