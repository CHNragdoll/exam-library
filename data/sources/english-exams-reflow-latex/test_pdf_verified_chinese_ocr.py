"""Regression checks for source-PDF-verified Chinese OCR corrections."""

import hashlib
import importlib.util
import json
from pathlib import Path
import re
import unittest

import fitz


ROOT = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location('english_reflow_build', ROOT / 'build.py')
BUILD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUILD)


class PdfVerifiedChineseOcrTests(unittest.TestCase):
    def test_cet6_2015_question_46_keeps_notice_separate(self):
        manifest = json.loads((ROOT.parent / 'english-exams-web-2026-09-26' /
                               'manifest.json').read_text())
        entry = next(item for item in manifest['papers']
                     if item['category'] == 'cet6' and Path(item['file']).stem == '2015-06-01')
        source = BUILD.source_pdf(entry)
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(),
                         '157b59f1bbbe90629b1e176b130dadf8a7bce98b9082226792875867c29693d6')
        with fitz.open(source) as document:
            page = document[5]
            extracted = BUILD.extract(page, unknown_glyphs=BUILD.source_chars(page),
                                      broad_source_blocks=False)
            blocks = BUILD.prepare(extracted['blocks'], page)
        BUILD.repair_cet6_2015_06_01_question_46('cet6', '2015-06-01', 6, blocks)
        notice = next(block for block in blocks
                      if BUILD.plain_text(block) == '注意：此部分试题请在答题卡2 上作答。')
        question = next(block for block in blocks
                        if BUILD.plain_text(block).startswith('46. According to Duncan Watts'))
        self.assertEqual(notice['type'], 'paragraph')
        self.assertEqual(question['type'], 'question')
        self.assertIn('“Mona Lisa”', BUILD.plain_text(question))
        self.assertTrue(BUILD.plain_text(question).endswith('cumulative advantage.'))

    def test_all_audited_pages_match_current_source_pdfs(self):
        manifest = json.loads((ROOT.parent / 'english-exams-web-2026-09-26' /
                               'manifest.json').read_text())
        entries = {(entry['category'], Path(entry['file']).stem): entry
                   for entry in manifest['papers']}
        cases = set(BUILD.TRANSLATION_OCR) | set(BUILD.GLOSS_OCR)
        self.assertEqual(len(BUILD.TRANSLATION_OCR), 9)
        self.assertGreaterEqual(len(BUILD.PDF_VERIFIED_CHINESE_OCR['glosses']), 40)

        for category, stem, page_number in sorted(cases):
            with self.subTest(category=category, paper=stem, page=page_number):
                entry = entries[category, stem]
                source = BUILD.source_pdf(entry)
                self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(),
                                 entry['source_pdf_sha256'])
                with fitz.open(source) as document:
                    page = document[page_number - 1]
                    extracted = BUILD.extract(
                        page, unknown_glyphs=BUILD.source_chars(page),
                        broad_source_blocks=(category, stem, page_number)
                        in BUILD.RECOVERY_CASES)
                    blocks = BUILD.prepare(extracted['blocks'], page)

                BUILD.repair_pdf_verified_chinese_ocr(
                    category, stem, page_number, blocks)
                text = '\n'.join(BUILD.plain_text(block) for block in blocks)
                for old, new in BUILD.GLOSS_OCR.get(
                        (category, stem, page_number), []):
                    self.assertNotIn(old, text)
                    self.assertEqual(text.count(new), 1)
                translation = BUILD.TRANSLATION_OCR.get(
                    (category, stem, page_number))
                if translation:
                    heading = next(index for index, block in enumerate(blocks)
                                   if BUILD.plain_text(block).startswith(
                                       'Part IV Translation'))
                    start = heading + translation['after_heading']
                    self.assertEqual(
                        [BUILD.plain_text(block) for block in
                         blocks[start:start + len(translation['paragraphs'])]],
                        translation['paragraphs'])
                    self.assertTrue(all(block['type'] == 'paragraph' for block in
                                        blocks[start:start + len(translation['paragraphs'])]))

    def test_replacement_preserves_surrounding_style(self):
        runs = [
            {'text': 'word ', 'flags': [False, False, True]},
            {'text': '( ~ ', 'flags': [False, False, False]},
            {'text': '1.. 69 )', 'flags': [True, False, False]},
            {'text': ' tail', 'flags': [False, False, True]},
        ]
        BUILD.replace_across_runs(runs, '( ~ 1.. 69 )', '(寄生的)')
        self.assertEqual(''.join(run['text'] for run in runs), 'word (寄生的) tail')
        self.assertEqual(runs[0]['flags'], [False, False, True])
        self.assertEqual(runs[-1]['flags'], [False, False, True])

    def test_english_corpus_has_no_unreviewed_mapped_gloss_candidates(self):
        """Flag future short symbol-heavy glosses before publishing a rebuild."""
        known = {(category, stem, page, old)
                 for (category, stem, page), items in BUILD.GLOSS_OCR.items()
                 for old, _ in items}
        # Printed arithmetic/abbreviations and a source-PDF defect on an
        # answer page are not Chinese glosses.
        reviewed_non_glosses = {
            ('cet4', '2021-06-02', 5, '("four"+ "10")'),
            ('cet4', '2015-06-01', 21, "(®l'i)"),
            ('cet4', '2019-06-02', 3, '(32.1%)'),
            ('cet6', '2017-12-03', 2, '(F.B.I)'),
        }
        unexpected = []
        for category in ('cet4', 'cet6'):
            for path in (ROOT / category / 'papers').glob('*.json'):
                paper = json.loads(path.read_text())
                for page in paper['pages']:
                    for block in page['blocks']:
                        if block['type'] == 'source_line':
                            continue
                        groups = ([block['runs']] if 'runs' in block else
                                  [item['runs'] for item in block.get('items', [])])
                        for runs in groups:
                            text = ''.join(run['text'] for run in runs)
                            for match in re.finditer(r'\([^()]{2,40}\)', text):
                                gloss = match.group()
                                inside = gloss[1:-1]
                                if re.search(r'[\u3400-\u9fff]', inside):
                                    continue
                                if sum(ch.isalpha() for ch in inside) > 6:
                                    continue
                                if sum(not ch.isalnum() and not ch.isspace()
                                       for ch in inside) < 2:
                                    continue
                                key = (category, path.stem, page['source_page'], gloss)
                                if key not in known and key not in reviewed_non_glosses:
                                    unexpected.append(key)
        self.assertEqual(unexpected, [])


if __name__ == '__main__':
    unittest.main()
