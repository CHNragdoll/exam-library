"""Small damaged glosses must not turn a selectable reading passage into a scan."""
import json
import unittest

import fitz
import build


MANIFEST = json.loads((build.ROOT.parent / 'english-exams-web-2026-09-26' / 'manifest.json').read_text())


class LocalGlyphFallbackTest(unittest.TestCase):
    def test_chinese_glosses_keep_english_passage_as_text(self):
        entry = next(item for item in MANIFEST['papers']
                     if item['file'] == 'cet6/papers/2021-06-03.htm')
        with fitz.open(build.source_pdf(entry)) as doc:
            for page_number in (2, 3):
                page = doc[page_number - 1]
                data = build.extract(page, unknown_glyphs=build.source_chars(page),
                                     broad_source_blocks=False)
                paragraphs = [''.join(run['text'] for run in block.get('runs', []))
                              for block in data['blocks'] if block['type'] == 'paragraph']
                self.assertTrue(any('Digital humans are coming' in line
                                    for line in paragraphs) if page_number == 2
                                else any('Now, a person can be animated' in line
                                         for line in paragraphs))
                self.assertLess(sum(block['type'] == 'source_line'
                                    for block in data['blocks']), 5)
                self.assertFalse(any(block['type'] == 'source_line'
                                     and fitz.Rect(block['bbox']).height > page.rect.height * .12
                                     for block in data['blocks']))


if __name__ == '__main__':
    unittest.main()
