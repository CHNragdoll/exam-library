"""The archived 2018 CET-6 PDFs print option labels as A). / B)."""

from collections import Counter
import copy
import json
import unittest

import fitz

import build


PDFS = {
    '2018-06-02': ('deaa6e2ed08156b34f11c3e2ff71a4426790912adc20d5b2fe9c2b3945080c20', 115),
    '2018-06-03': ('976c64492aa905cbd21a241414dc6fb406d88b5b97838da68e7689746c39db14', 15),
}


class PdfVerifiedDottedOptionLabelsTest(unittest.TestCase):
    def test_printed_labels_are_preserved_without_leaking_period_into_text(self):
        manifest = json.loads((build.ROOT.parent / 'english-exams-web-2026-09-26' /
                               'manifest.json').read_text())
        for stem, (digest, expected) in PDFS.items():
            with self.subTest(stem=stem):
                entry = next(item for item in manifest['papers']
                             if item['file'] == f'cet6/papers/{stem}.htm')
                self.assertEqual(entry['source_pdf_sha256'], digest)
                self.assertEqual(build.sha(build.source_pdf(entry)), digest)
                repaired = []
                with fitz.open(build.source_pdf(entry)) as pdf:
                    for page_number, page in enumerate(pdf, 1):
                        data = build.extract(page, unknown_glyphs=build.source_chars(page),
                                             broad_source_blocks=('cet6', stem, page_number)
                                             in build.RECOVERY_CASES)
                        blocks = build.prepare(data['blocks'], page)
                        before = copy.deepcopy(blocks)
                        count = build.repair_pdf_verified_dotted_option_labels(
                            'cet6', stem, digest, page_number, blocks, page.get_text())
                        changed = [(old, new) for old_block, new_block in zip(before, blocks)
                                   for old, new in zip(old_block.get('items', []),
                                                       new_block.get('items', [])) if old != new]
                        self.assertEqual(len(changed), count)
                        for old, new in changed:
                            self.assertEqual(old['runs'][0]['text'],
                                             '. ' + new['runs'][0]['text'])
                            self.assertEqual(new['source_label'], new['label'] + ').')
                            self.assertFalse(new['runs'][0]['text'].startswith('.'))
                            self.assertIn('data-source-label="' + new['source_label'] + '"',
                                          build.html_option(new, 'b-1-1', 0))
                        repaired.extend(new for _, new in changed)
                self.assertEqual(len(repaired), expected)
                self.assertEqual(Counter(item['source_label'][0] for item in repaired),
                                 Counter(item['label'] for item in repaired))

    def test_wrong_pdf_hash_is_rejected_and_other_papers_are_untouched(self):
        blocks = [{'type': 'options', 'items': [{'label': 'B',
                   'runs': [{'text': '. They may turn', 'flags': [False, False, False]}]}]}]
        original = copy.deepcopy(blocks)
        with self.assertRaises(AssertionError):
            build.repair_pdf_verified_dotted_option_labels(
                'cet6', '2018-06-02', '0' * 64, 2, blocks, 'B). They may turn')
        self.assertEqual(blocks, original)
        self.assertEqual(build.repair_pdf_verified_dotted_option_labels(
            'cet6', '2014-06-01', '0' * 64, 2, blocks, 'B). They may turn'), 0)
        self.assertEqual(blocks, original)


if __name__ == '__main__':
    unittest.main()
