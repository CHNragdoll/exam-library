"""PDF line wrapping must not manufacture new semantic paragraphs."""
import json
import unittest

import fitz
import build


MANIFEST = json.loads((build.ROOT.parent / 'english-exams-web-2026-09-26' / 'manifest.json').read_text())


def source_blocks(category, stem, page_number):
    entry = next(item for item in MANIFEST['papers']
                 if item['file'] == f'{category}/papers/{stem}.htm')
    with fitz.open(build.source_pdf(entry)) as document:
        page = document[page_number - 1]
        blocks = build.extract(page, unknown_glyphs=build.source_chars(page))['blocks']
        build.repair_pdf_verified_soft_wraps(category, stem, page_number, blocks)
        return blocks


def paragraph_texts(blocks):
    return [''.join(run['text'] for run in block['runs'])
            for block in blocks if block['type'] == 'paragraph']


class SoftLineWrapsTest(unittest.TestCase):
    def test_english_word_and_phrase_are_not_separate_paragraphs(self):
        cases = [
            ('cet4', '2018-06-03', 1, 'no more than 180 words.', 'n180 words.'),
            ('cet4', '2014-12-02', 5, 'making sales calls for a car company.',
             'for a car company.'),
        ]
        for category, stem, page, joined, orphan in cases:
            with self.subTest(stem=stem):
                paragraphs = paragraph_texts(source_blocks(category, stem, page))
                self.assertTrue(any(joined in paragraph for paragraph in paragraphs), joined)
                self.assertNotIn(orphan, paragraphs)

    def test_chinese_translation_mid_word_is_one_paragraph(self):
        paragraphs = paragraph_texts(source_blocks('cet6', '2018-06-03', 7))
        self.assertTrue(any('随着城市交通拥堵' in paragraph for paragraph in paragraphs))
        self.assertFalse(any(paragraph.startswith('通拥堵') for paragraph in paragraphs))

    def test_genuine_paragraphs_still_stay_separate(self):
        paragraphs = paragraph_texts(source_blocks('cet4', '2014-06-01', 7))
        for opening in ('Part of the reason this happens', 'We’ve all met the type',
                        'Truth is, they’re nothing'):
            self.assertEqual(sum(paragraph.startswith(opening) for paragraph in paragraphs), 1)

    def test_source_verified_question_final_lines(self):
        for (category, stem, page, number), tail in build.PDF_VERIFIED_QUESTION_CONTINUATIONS.items():
            with self.subTest(stem=stem, number=number):
                blocks = source_blocks(category, stem, page)
                build.repair_pdf_verified_question_continuations(
                    category, stem, page, blocks)
                questions = [''.join(run['text'] for run in block['runs'])
                             for block in blocks if block['type'] == 'question']
                self.assertEqual(sum(question.startswith(f'{number}.')
                                     and question.endswith(' ' + tail)
                                     for question in questions), 1)
                self.assertNotIn(tail, paragraph_texts(blocks))


if __name__ == '__main__':
    unittest.main()
