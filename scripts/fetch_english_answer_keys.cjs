#!/usr/bin/env node
// Capture the free answer-letter grids shown by the public paper reader.
// Keep the resulting key file independent of the site's code and PDF assets.
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { webcrypto, createHash } = require('node:crypto');

const ORIGIN = 'https://zhenti.burningvocabulary.cn';
const WORKER_PATH = '/javascripts/read_zhenti_web_worker.js?version=20260911crypto2';
// The worker is executed only to reproduce the public reader's free answer grid.
// Refuse changed remote code until its behavior has been reviewed again.
const WORKER_SHA256 = 'e6f00de05cb36730674615aa5e1d33532dd6ae58d7290732b269476208736195';
const CATEGORIES = ['kaoyan', 'cet4', 'cet6'];
const OUTPUT = path.resolve(__dirname, '../.local/answer-keys/burningvocabulary.json');

async function getText(url) {
  for (let attempt = 0; attempt < 3; attempt++) {
    try {
      const response = await fetch(url, { headers: { 'User-Agent': 'exam-library-answer-key-audit/1.0' } });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return await response.text();
    } catch (error) {
      if (attempt === 2) throw error;
      await new Promise(resolve => setTimeout(resolve, 500 * (attempt + 1)));
    }
  }
}

function paperId(urlPath) {
  const parts = urlPath.split('/').filter(Boolean);
  return parts[0] === 'kaoyan'
    ? `kaoyan:${parts[1]}-${parts[2]}`
    : `${parts[0]}:${parts[1]}-${parts[2]}`;
}

function decrypt(publicReaderWorker, payload) {
  let result;
  const context = {
    self: { postMessage: message => { result = message; } },
    crypto: globalThis.crypto || webcrypto,
    TextEncoder, TextDecoder, atob, btoa, URL, Uint8Array, ArrayBuffer,
    setTimeout, clearTimeout,
  };
  vm.createContext(context);
  vm.runInContext(publicReaderWorker, context, { timeout: 2000 });
  context.self.onmessage({ data: { type: 'decryp_msg_ans', resData: { data: payload } } });
  const values = result?.resData?.data;
  if (result?.type !== 'decryp_msg_ans_ed' || !Array.isArray(values)) {
    throw new Error('Public reader did not return an answer grid');
  }
  return Array.from(values, value => String(value));
}

async function main() {
  const paths = [];
  for (const category of CATEGORIES) {
    const index = await getText(`${ORIGIN}/${category}`);
    const pattern = new RegExp(`href="(\\/${category}\\/[0-9]{4}(?:-[0-9]{2})?\\/[0-9]{2})"`, 'g');
    for (const match of index.matchAll(pattern)) paths.push(match[1]);
  }
  const uniquePaths = [...new Set(paths)];
  const worker = await getText(`${ORIGIN}${WORKER_PATH}`);
  if (createHash('sha256').update(worker).digest('hex') !== WORKER_SHA256) {
    throw new Error('Public reader worker changed; review it before running');
  }
  const papers = [];
  for (let i = 0; i < uniquePaths.length; i++) {
    const urlPath = uniquePaths[i];
    const record = { paperId: paperId(urlPath), sourceUrl: `${ORIGIN}${urlPath}` };
    try {
      const html = await getText(record.sourceUrl);
      const match = html.match(/var globalConfig = (\{[^\n]+\})/);
      if (!match) throw new Error('Paper configuration missing');
      const config = JSON.parse(match[1]);
      record.title = config.title;
      if (config.newAnswer) {
        const values = decrypt(worker, config.newAnswer);
        record.answers = values.map(value => value.toUpperCase());
        record.status = values.length && values.every(value => /^\d{1,3}-[A-Za-z]$/.test(value))
          ? 'available' : 'partial';
      } else {
        record.status = 'unavailable';
        record.answers = [];
      }
    } catch (error) {
      record.status = 'error';
      record.error = String(error?.message || error);
      record.answers = [];
    }
    papers.push(record);
    if ((i + 1) % 25 === 0 || i + 1 === uniquePaths.length) {
      process.stderr.write(`Captured ${i + 1}/${uniquePaths.length} public papers\n`);
    }
    await new Promise(resolve => setTimeout(resolve, 150));
  }
  const capture = {
    source: ORIGIN,
    capturedAt: new Date().toISOString(),
    description: 'Public 查答案 choice letters only; no paid explanations or PDF content',
    papers,
  };
  fs.mkdirSync(path.dirname(OUTPUT), { recursive: true });
  fs.writeFileSync(OUTPUT, JSON.stringify(capture, null, 2) + '\n');
  const counts = Object.groupBy(papers, paper => paper.status);
  process.stdout.write(JSON.stringify(Object.fromEntries(Object.entries(counts).map(([key, value]) => [key, value.length]))) + '\n');
}

module.exports = { ORIGIN, WORKER_PATH, WORKER_SHA256, getText, decrypt };

if (require.main === module) {
  main().catch(error => { console.error(error); process.exitCode = 1; });
}
