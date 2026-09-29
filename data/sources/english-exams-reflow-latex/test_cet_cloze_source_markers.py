"""PDF-backed checks for exceptional CET cloze text-layer markers."""

import json
from pathlib import Path
import subprocess
import unittest

import fitz
from lxml import html

import build


class CETClozeSourceMarkerTests(unittest.TestCase):
    def source_page(self, category, stem, page_number):
        source = Path(__file__).parent / category / 'papers' / f'{stem}.json'
        return json.loads(source.read_text(encoding='utf-8'))['pages'][page_number - 1]['blocks']

    def prepared_pdf_page(self, category, stem, page_number):
        manifest = json.loads((Path(__file__).parents[1] /
                               'english-exams-web-2026-09-26/manifest.json').read_text())
        entry = next(item for item in manifest['papers']
                     if item['category'] == category and Path(item['file']).stem == stem)
        with fitz.open(build.source_pdf(entry)) as pdf:
            page = pdf[page_number - 1]
            data = build.extract(page, unknown_glyphs=build.source_chars(page))
            return build.prepare(data['blocks'], page)

    def pdf_page(self, category, stem, page_number):
        pdf = (Path(__file__).parents[1] / 'english-exams-web-2026-09-26' /
               '.firecrawl' / category / f'{stem}.pdf')
        self.assertTrue(pdf.is_file(), str(pdf))
        return subprocess.run(['pdftotext', '-f', str(page_number), '-l', str(page_number),
                               '-layout', str(pdf), '-'], check=True, capture_output=True,
                              text=True).stdout

    def test_false_underlines_are_plain_prose_and_numeric_blanks_remain(self):
        cases = (
            ('cet4', '2015-06-01', 4, 4, 5, 'great educators in these schools.', '36'),
            ('cet6', '2016-12-01', 4, 0, 1, 'research and development,', '32'),
            ('cet6', '2017-12-01', 3, 21, 3, '” in the country', '32'),
        )
        for category, stem, page, block_index, run_index, printed, numbered in cases:
            with self.subTest(document=f'{category}:{stem}'):
                blocks = self.prepared_pdf_page(category, stem, page)
                runs = blocks[block_index]['runs']
                original = ''.join(run['text'] for run in runs)
                self.assertIn(printed, ' '.join(self.pdf_page(category, stem, page).split()))
                self.assertTrue(runs[run_index]['flags'][1])
                build.repair_cet_cloze_false_underlines(category, stem, page, blocks)
                self.assertFalse(runs[run_index]['flags'][1])
                self.assertEqual(''.join(run['text'] for run in runs), original)
                self.assertTrue(any(run['text'].strip() == numbered and run['flags'][1]
                                    for block in blocks for run in block.get('runs', [])))
                generated_blocks = self.source_page(category, stem, page)
                generated_runs = generated_blocks[block_index]['runs']
                self.assertFalse(generated_runs[run_index]['flags'][1])
                self.assertEqual(''.join(run['text'] for run in generated_runs), original)
                self.assertTrue(any(run['text'].strip() == numbered and run['flags'][1]
                                    for block in generated_blocks for run in block.get('runs', [])))

    def test_fullwidth_parenthesis_blank_is_marked_without_rewriting_source(self):
        blocks = self.prepared_pdf_page('cet4', '2017-06-02', 5)
        runs = blocks[6]['runs']
        original = ''.join(run['text'] for run in runs)
        self.assertIn('（28)_______', self.pdf_page('cet4', '2017-06-02', 5))
        self.assertEqual(original.count('（28)_______'), 1)
        rendered = build.cet4_2017_06_02_cloze_28_html(runs)
        self.assertIn('（<span class="blank">28</span>)_______', rendered)
        self.assertEqual(html.fromstring(f'<div>{rendered}</div>').text_content(), original)
        self.assertEqual(''.join(run['text'] for run in runs), original)


if __name__ == '__main__':
    unittest.main()
