"""Regression checks for source-backed reader metadata."""

from pathlib import Path
import unittest

from enhance_readers import translation_paragraph_starts


SOURCES = Path(__file__).resolve().parent.parent


class TranslationParagraphStartsTest(unittest.TestCase):
    def starts(self, paper):
        original = SOURCES / 'english-exams-web-2026-09-26/cet6/papers' / paper
        reflow = SOURCES / 'english-exams-reflow-latex/cet6/papers' / paper
        return translation_paragraph_starts(original, reflow)

    def test_chinese_passage_keeps_original_two_paragraph_starts(self):
        self.assertEqual(self.starts('2015-12-02.htm'), [
            '最近，中国政府决定将其工',
            '中国造产品越来越受欢迎。',
        ])

    def test_sentence_completion_does_not_use_answer_explanations(self):
        self.assertEqual(self.starts('2012-12-02.htm'), [])


if __name__ == '__main__':
    unittest.main()
