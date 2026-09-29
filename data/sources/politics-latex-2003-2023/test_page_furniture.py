"""Regression checks for the page-number variants in the printed politics PDF."""

import unittest
from pathlib import Path
import re

from page_furniture import is_page_footer_line, without_trailing_page_footer


class PageFurnitureTests(unittest.TestCase):
    def test_printed_2023_page_number_variants(self):
        for page, line in ((1, " •  1  • "), (2, "2"), (3, " -3  • "),
                           (8, " -8  - "), (10, " ・10  - ")):
            with self.subTest(page=page):
                self.assertTrue(is_page_footer_line(line, page))

    def test_requires_matching_isolated_page_number(self):
        for page, line in ((8, "-3 •"), (8, "摘自《邓小平文选》第二卷 -8 -"),
                           (8, "-0.8"), (8, "2022年8月"),
                           (8, "第36题（续）：材料3"), (8, "8. 题干")):
            with self.subTest(line=line):
                self.assertFalse(is_page_footer_line(line, page))

    def test_only_final_matching_line_is_removed(self):
        source = "材料3 2022年1月30日，增长率-0.8。\n第36题（续）：保留\n -8  -\n"
        self.assertEqual(without_trailing_page_footer(source, 8),
                         "材料3 2022年1月30日，增长率-0.8。\n第36题（续）：保留")
        self.assertEqual(without_trailing_page_footer(source, 9), source.rstrip("\n"))

    def test_all_2023_transcription_page_footers(self):
        raw = (Path(__file__).resolve().parent / "work/2023-questions.txt").read_text()
        pages = {int(number): content for number, content in re.findall(
            r"=== PAGE (\d+) ===\n(.*?)(?=\n=== PAGE |\Z)", raw, re.S)}
        self.assertEqual(set(pages), set(range(1, 12)))
        for number, content in pages.items():
            with self.subTest(page=number):
                before = content.splitlines()
                last = next(line for line in reversed(before) if line.strip())
                self.assertTrue(is_page_footer_line(last, number))
                after = without_trailing_page_footer(content, number)
                expected = before.copy()
                del expected[max(i for i, line in enumerate(expected) if line.strip())]
                self.assertEqual(after, "\n".join(expected))


if __name__ == "__main__":
    unittest.main()
