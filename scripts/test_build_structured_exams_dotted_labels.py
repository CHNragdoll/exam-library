"""Keep printed A). labels complete only on the two verified CET-6 papers."""

import unittest

from bs4 import BeautifulSoup

from scripts import build_structured_exams as builder
from scripts import verify_structured_exams as verifier


class DottedSourceLabelTest(unittest.TestCase):
    def test_source_label_is_preserved_in_structured_option(self):
        html = ('<ul class="options"><li><span class="option-label" '
                'data-source-label="B).">B.</span><span>They may turn to benefit '
                'the local environment</span></li></ul>')
        options = builder.options_from(BeautifulSoup(html, 'html.parser').ul)
        self.assertEqual(options, [{'label': 'B.', 'sourceLabel': 'B).',
                                    'text': 'They may turn to benefit the local environment'}])

    def test_double_punctuation_is_accepted_only_for_the_verified_papers(self):
        option = {'label': 'B.', 'sourceLabel': 'B).'}
        for paper in ('cet6:2018-06-02', 'cet6:2018-06-03'):
            with self.subTest(paper=paper):
                self.assertTrue(builder.valid_cet_source_label(paper, option))
                self.assertTrue(verifier.valid_printed_option_label(
                    paper, option['label'], option['sourceLabel']))
        for paper in ('cet6:2018-06-01', 'cet4:2018-06-02', 'cet6:2014-06-01'):
            with self.subTest(paper=paper):
                self.assertFalse(builder.valid_cet_source_label(paper, option))
                self.assertFalse(verifier.valid_printed_option_label(
                    paper, option['label'], option['sourceLabel']))
        self.assertFalse(builder.valid_cet_source_label(
            'cet6:2018-06-02', {'label': 'A.', 'sourceLabel': 'B).'}))
        self.assertFalse(verifier.valid_printed_option_label(
            'cet6:2018-06-02', 'A.', 'B).'))
        self.assertTrue(builder.valid_cet_source_label(
            'cet6:2018-06-01', {'label': 'B.', 'sourceLabel': 'B.'}))


if __name__ == '__main__':
    unittest.main()
