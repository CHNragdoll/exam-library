"""Source-backed reading paragraph regressions; run with the project Python."""

import importlib.util
import unittest
from pathlib import Path


HERE = Path(__file__).resolve().parent
SOURCES = HERE.parent
spec = importlib.util.spec_from_file_location('enhance_readers_under_test', HERE / 'enhance_readers.py')
enhance = importlib.util.module_from_spec(spec)
spec.loader.exec_module(enhance)


def starts(category, slug):
    original = SOURCES / 'english-exams-web-2026-09-26' / category / 'papers' / f'{slug}.htm'
    reflow = SOURCES / 'english-exams-reflow-latex' / category / 'papers' / f'{slug}.htm'
    return enhance.reading_paragraph_starts(original, reflow)


class ReadingParagraphsTest(unittest.TestCase):
    def test_five_source_paragraphs_on_cet6_2015_page_seven(self):
        rows = [row for row in starts('cet6', '2015-12-02') if row['sourcePageIndex'] == 7]
        self.assertEqual([row['sourceY'] for row in rows], [98.7, 158.7, 203.7, 263.7])
        self.assertTrue(all(row['reflowPageIndex'] == 7 and row['reflowBlockIndex'] == 1
                            for row in rows))

    def test_wrapped_names_options_and_answers_are_not_paragraphs(self):
        examples = [
            ('cet6', '2013-06-01', ('AppleiPhones', 'Freed-HardemanUniversity')),
            ('cet4', '2014-12-02', ('LaborDepartment', 'SocialSecurity')),
            ('cet4', '2014-12-03', ('EnglandandWales',)),
            ('cet4', '2015-06-02', ('Stanford', 'HewlettFoundation')),
            ('cet6', '2013-12-03', ('Americans',)),
            ('cet6', '2015-12-03', ('RichardThaler',)),
            ('cet6', '2019-12-03', ('NewYork',)),
            ('cet6', '2012-12-03', ('M:It’sabitdated', 'W:Yes,Iam')),
            ('cet4', '2014-06-02', ('A)Theycame',)),
            ('cet4', '2015-06-01', ('“形成”',)),
        ]
        for category, slug, fragments in examples:
            with self.subTest(paper=f'{category}/{slug}'):
                anchors = [row['anchor'] for row in starts(category, slug)]
                for fragment in fragments:
                    self.assertFalse(any(fragment in anchor for anchor in anchors), fragment)


if __name__ == '__main__':
    unittest.main()
