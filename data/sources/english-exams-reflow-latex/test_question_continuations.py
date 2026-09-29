"""Printed line wraps inside numbered questions stay in the same stem."""
import json
import unittest

import fitz
import build


MANIFEST = json.loads((build.ROOT.parent / 'english-exams-web-2026-09-26' / 'manifest.json').read_text())


def paper_page(category, stem, number):
    entry = next(item for item in MANIFEST['papers']
                 if item['file'] == f'{category}/papers/{stem}.htm')
    with fitz.open(build.source_pdf(entry)) as doc:
        page = doc[number - 1]
        return build.extract(page, unknown_glyphs=build.source_chars(page))['blocks']


def text(block):
    return ''.join(run['text'] for run in block.get('runs', []))


class QuestionContinuationsTest(unittest.TestCase):
    def test_cet6_matching_stems_follow_printed_lines(self):
        blocks = paper_page('cet6', '2021-06-03', 4)
        questions = {int(text(block).split('.', 1)[0]): text(block)
                     for block in blocks if block['type'] == 'question'
                     and text(block).split('.', 1)[0].isdigit()}
        for number, ending in {
            36: 'should be recreated.',
            37: 'in new settings.',
            38: 'real actor especially in facial expressions.',
            43: 'from the real actor.',
            44: 'for the benefit of their families.',
        }.items():
            self.assertIn(ending, questions[number])
        leftovers = {'recreated.', 'new settings.', 'especially in facial expressions.',
                     'actor.', 'benefit of their families.'}
        self.assertFalse(leftovers & {text(block) for block in blocks
                                      if block['type'] == 'paragraph'})
        self.assertEqual(sum(text(block).startswith('40.') for block in blocks
                             if block['type'] == 'question'), 1)

    def test_left_indented_continuation_and_finished_neighbor(self):
        blocks = paper_page('cet4', '2016-12-01', 6)
        questions = {text(block).split('.', 1)[0]: text(block)
                     for block in blocks if block['type'] == 'question'}
        self.assertTrue(questions['38'].endswith('both inside and outside the house.'))
        self.assertTrue(questions['36'].endswith('necessary equipment and skill.'))
        self.assertTrue(questions['40'].endswith('technical means.'))


if __name__ == '__main__':
    unittest.main()
