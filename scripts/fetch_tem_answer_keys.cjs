#!/usr/bin/env node
// Capture only the free public answer-letter grid for canonical TEM papers.
// Audit mode is read-only; --write creates a separate manifest and never edits
// the existing Kaoyan/CET capture.
const fs = require('node:fs');
const path = require('node:path');
const { createHash } = require('node:crypto');
const { ORIGIN, WORKER_PATH, WORKER_SHA256, getText, decrypt } = require('./fetch_english_answer_keys.cjs');

const SOURCE_MANIFEST = path.resolve(__dirname, '../data/sources/english-exams-web-2026-09-26/manifest.json');
const STRUCTURED = path.resolve(__dirname, '../data/sources/exam-library/structured/papers');
const OUTPUT = path.resolve(__dirname, '../.local/answer-keys/burningvocabulary-tem.json');
const CATEGORIES = new Set(['tem4', 'tem8']);
const SUPPLEMENTARY_HEADINGS = {
  'tem4:2022': '2023 年英语专业四级真题补充卷说明：本次考试全国出现了两套试题',
  'tem4:2023': '2023 年英语专业四级真题补充卷说明：本次考试全国出现了两套试题',
  'tem4:2025': '2025 年英语专业四级真题补充卷说明：本次考试全国出现了两套试题',
};

function sha256(bytes) {
  return createHash('sha256').update(bytes).digest('hex');
}

function canonicalRows(manifest) {
  const rows = manifest.papers.filter(row => CATEGORIES.has(row.category));
  if (rows.length !== 8 || new Set(rows.map(row => `${row.category}:${row.year}`)).size !== 8) {
    throw new Error('Expected eight unique canonical TEM papers from 2022–2025');
  }
  for (const row of rows) {
    const stem = String(row.year);
    if (!/^202[2-5]$/.test(stem) || row.file !== `${row.category}/papers/${stem}.htm` ||
        row.source_url !== `${ORIGIN}/${row.category}/${stem}` ||
        !row.document_url.startsWith('https://res-zhenti.burningvocabulary.cn/images/read/') ||
        !/^[a-f0-9]{64}$/.test(row.source_pdf_sha256)) {
      throw new Error(`Unexpected TEM source manifest row: ${row.category}:${stem}`);
    }
  }
  return rows.sort((a, b) => a.category.localeCompare(b.category) || a.year - b.year);
}

async function getBytes(url) {
  for (let attempt = 0; attempt < 3; attempt++) {
    try {
      const response = await fetch(url, { headers: { 'User-Agent': 'exam-library-answer-key-audit/1.0' } });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return Buffer.from(await response.arrayBuffer());
    } catch (error) {
      if (attempt === 2) throw error;
      await new Promise(resolve => setTimeout(resolve, 500 * (attempt + 1)));
    }
  }
}

function validatedAnswers(category, values) {
  const expected = category === 'tem4' ? 50 : 24;
  if (values.length !== expected) throw new Error(`${category}: expected ${expected} answer tokens, got ${values.length}`);
  const answers = values.map((raw, index) => {
    const token = raw.toUpperCase();
    const match = token.match(/^(\d{1,3})-([A-O])$/);
    if (!match || Number(match[1]) !== index + 1 ||
        (category === 'tem8' || index < 30 || index >= 40) && !/^[A-D]$/.test(match[2])) {
      throw new Error(`${category}: invalid or out-of-order answer token at ${index + 1}: ${raw}`);
    }
    return token;
  });
  if (category === 'tem4' && new Set(answers.slice(30, 40).map(token => token.split('-')[1])).size !== 10) {
    throw new Error('TEM4 word-bank answers must use ten distinct letters');
  }
  return answers;
}

async function captureTem() {
  const source = JSON.parse(fs.readFileSync(SOURCE_MANIFEST, 'utf8'));
  const rows = canonicalRows(source);
  const indexPaths = new Set();
  for (const category of CATEGORIES) {
    const index = await getText(`${ORIGIN}/${category}`);
    const pattern = new RegExp(`href="(\\/${category}\\/202[2-5])"`, 'g');
    for (const match of index.matchAll(pattern)) indexPaths.add(match[1]);
  }
  const worker = await getText(`${ORIGIN}${WORKER_PATH}`);
  if (sha256(worker) !== WORKER_SHA256) throw new Error('Public reader worker changed; review before capture');
  const papers = [];
  for (const row of rows) {
    const paperId = `${row.category}:${row.year}`;
    const urlPath = `/${row.category}/${row.year}`;
    if (!indexPaths.has(urlPath)) throw new Error(`${paperId}: missing from public index`);
    const html = await getText(row.source_url);
    const configMatch = html.match(/var globalConfig = (\{[^\n]+\})/);
    if (!configMatch) throw new Error(`${paperId}: paper configuration missing`);
    const config = JSON.parse(configMatch[1]);
    if (config.filePath !== `${row.category}/${row.year}` || !config.newAnswer) {
      throw new Error(`${paperId}: configuration/path/answer mismatch`);
    }
    const pdf = await getBytes(row.document_url);
    if (sha256(pdf) !== row.source_pdf_sha256) throw new Error(`${paperId}: source PDF SHA-256 changed`);
    const answers = validatedAnswers(row.category, decrypt(worker, config.newAnswer));
    papers.push({
      paperId, sourceUrl: row.source_url, sourceDocumentUrl: row.document_url,
      sourcePdfSha256: row.source_pdf_sha256, title: config.title, answers,
    });
    await new Promise(resolve => setTimeout(resolve, 150));
  }
  return {
    source: ORIGIN, capturedAt: new Date().toISOString(), workerSha256: WORKER_SHA256,
    description: 'Public 查答案 choice letters only; no paid explanations or PDF content', papers,
  };
}

function classifyCandidate(paper, question, value, numberCount) {
  if (numberCount !== 1) return 'duplicateLocalNumber';
  if (question.recordType !== 'question') return 'notQuestion';
  let labels;
  if (question.questionType === 'single_choice') {
    labels = question.options.map(option => String(option.label).replace(/\.$/, '').toUpperCase());
    if (labels.length !== 4 || [...labels].sort().join('') !== 'ABCD') return 'printedOptionsMismatch';
  } else if (paper.paperId.startsWith('tem4:') && question.questionType === 'fill_blank') {
    const context = question.context;
    if (context?.kind !== 'word_bank_cloze' || context.wordBankStatus !== 'complete' ||
        context.unresolvedWordBankFragments?.length || !context.text?.trim() ||
        !context.passageSourceBlocks?.length ||
        !context.printedBlankNumbers?.map(String).includes(String(question.number)) ||
        context.sourceNumberUnverifiedNumbers?.map(String).includes(String(question.number))) {
      return 'unverifiedWordBank';
    }
    labels = context.wordBank.map(option => String(option.label).replace(/\.$/, '').toUpperCase());
    if (labels.length !== 15 || [...labels].sort().join('') !== 'ABCDEFGHIJKLMNO') return 'printedWordBankMismatch';
  } else {
    return 'incompatibleQuestionType';
  }
  if (labels.filter(label => label === value).length !== 1) return 'letterNotPrinted';
  const answer = question.answer || {};
  if (answer.status === 'explicit') return answer.value === value ? 'alreadyKnown' : 'existingAnswerConflict';
  if (answer.status !== 'missing') return 'otherExistingAnswer';
  return null;
}

function mainChoiceBeforeSupplement(paper, number, matches) {
  const heading = SUPPLEMENTARY_HEADINGS[paper.id];
  if (!heading || !/^\d+$/.test(number) || Number(number) < 11 || Number(number) > 30 ||
      matches.length !== 2) return null;
  const blocks = new Map(paper.blocks.map(block => [block.id, block]));
  if (blocks.get('b-10-1')?.page !== '10' ||
      !blocks.get('b-10-1')?.text?.startsWith(heading)) return null;
  const main = matches.filter(question =>
    question.id === `q-${number}-1` && question.questionType === 'single_choice' &&
    ['2', '3'].includes(question.sourcePages?.join(',')) && question.sourceBlocks?.length &&
    question.sourceBlocks.every(id => ['2', '3'].includes(blocks.get(id)?.page)));
  const supplement = matches.filter(question =>
    question.id === `q-${number}-2` && question.sourcePages?.join(',') === '10' &&
    question.sourceBlocks?.length &&
    question.sourceBlocks.every(id => blocks.get(id)?.page === '10'));
  return main.length === 1 && supplement.length === 1 ? main[0] : null;
}

function auditTem(capture) {
  const candidates = [], rejected = [], counts = {};
  for (const source of capture.papers) {
    const [category, stem] = source.paperId.split(':');
    const paper = JSON.parse(fs.readFileSync(path.join(STRUCTURED, category, `${stem}.json`), 'utf8'));
    if (paper.id !== source.paperId || paper.category !== category || paper.kind === 'answers') {
      throw new Error(`${source.paperId}: local paper identity mismatch`);
    }
    const questionsByNumber = new Map();
    for (const question of paper.questions) {
      const number = String(question.number);
      questionsByNumber.set(number, [...(questionsByNumber.get(number) || []), question]);
    }
    for (const token of source.answers) {
      const [number, value] = token.split('-');
      const matches = questionsByNumber.get(number) || [];
      const question = matches.length === 1 ? matches[0] : mainChoiceBeforeSupplement(paper, number, matches);
      const reason = question ? classifyCandidate(source, question, value, 1) : 'duplicateLocalNumber';
      if (reason) {
        rejected.push({ paperId: source.paperId, answerToken: token, reason });
        counts[reason] = (counts[reason] || 0) + 1;
      } else {
        candidates.push({
          paperId: source.paperId, questionId: question.id, answerToken: token,
          sourceUrl: source.sourceUrl, sourcePdfSha256: source.sourcePdfSha256,
          contextId: question.context?.id || null,
          ...(matches.length > 1 ? { sourceSet: 'main_paper_before_pdf_supplement' } : {}),
        });
      }
    }
  }
  return { summary: { papers: capture.papers.length, tokens: capture.papers.reduce((n, p) => n + p.answers.length, 0),
    candidates: candidates.length, rejected: rejected.length, reasons: counts }, candidates, rejected };
}

function atomicWrite(file, value) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  const temporary = `${file}.${process.pid}.tmp`;
  try {
    fs.writeFileSync(temporary, JSON.stringify(value, null, 2) + '\n', { flag: 'wx' });
    fs.renameSync(temporary, file);
  } finally {
    if (fs.existsSync(temporary)) fs.unlinkSync(temporary);
  }
}

async function main() {
  const mode = process.argv[2] || '--audit';
  if (!['--audit', '--write'].includes(mode) || process.argv.length > 3) {
    throw new Error('Usage: node scripts/fetch_tem_answer_keys.cjs [--audit|--write]');
  }
  const capture = await captureTem();
  const audit = auditTem(capture);
  if (mode === '--write') atomicWrite(OUTPUT, capture);
  process.stdout.write(JSON.stringify(audit, null, 2) + '\n');
}

module.exports = { canonicalRows, validatedAnswers, classifyCandidate, mainChoiceBeforeSupplement, auditTem };
if (require.main === module) main().catch(error => { console.error(error); process.exitCode = 1; });
