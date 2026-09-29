"""Original-SVG recovery of the 82 PDF-verified image-only English questions."""

from collections import Counter
from pathlib import Path
import re
import sys
import unittest

import fitz


SOURCES = Path(__file__).resolve().parents[1] / "data" / "sources"
REFLOW = SOURCES / "english-exams-reflow-latex"
sys.path.insert(0, str(REFLOW / "tools"))

from encoding import get_unknown_glyphs  # noqa: E402
from extract import extract  # noqa: E402
from layout import prepare  # noqa: E402
from recover_image_questions import MATCHING_CASES, RECOVERY_CASES, recover_image_questions  # noqa: E402


def block_text(block: dict) -> str:
    return "".join(run["text"] for run in block.get("runs", []))


class ImageQuestionRecoveryTests(unittest.TestCase):
    def test_selectable_question_requires_source_faithful_options(self):
        category, stem, page_number = "cet4", "2020-09-01", 8
        pdf = SOURCES / "english-exams-web-2026-09-26" / ".firecrawl" / category / f"{stem}.pdf"
        original = SOURCES / "english-exams-web-2026-09-26" / category / "papers" / f"{stem}.htm"
        with fitz.open(pdf) as document:
            page = document[page_number - 1]
            blocks = prepare(extract(page, unknown_glyphs=get_unknown_glyphs(page))["blocks"], page)
        first_options = next(block for block in blocks if block["type"] == "options")
        first_options["items"][0]["runs"][0]["text"] = "An unsupported answer."
        with self.assertRaisesRegex(ValueError, "extracted option differs from original SVG"):
            recover_image_questions(category, stem, page_number, blocks, original)

    def test_all_confirmed_questions_keep_crops_and_printed_option_groups(self):
        self.assertEqual(len(RECOVERY_CASES), 18)
        self.assertEqual(sum(map(len, RECOVERY_CASES.values())), 82)
        self.assertEqual(sum(len(numbers) for case, numbers in RECOVERY_CASES.items()
                             if case in MATCHING_CASES), 24)
        checked = Counter()
        for (category, stem, page_number), targets in RECOVERY_CASES.items():
            with self.subTest(category=category, paper=stem, page=page_number):
                pdf = SOURCES / "english-exams-web-2026-09-26" / ".firecrawl" / category / f"{stem}.pdf"
                original = SOURCES / "english-exams-web-2026-09-26" / category / "papers" / f"{stem}.htm"
                with fitz.open(pdf) as document:
                    page = document[page_number - 1]
                    blocks = prepare(extract(page, unknown_glyphs=get_unknown_glyphs(page))["blocks"], page)
                crops = [block for block in blocks if block["type"] == "source_line"]
                self.assertTrue(crops)
                recover_image_questions(category, stem, page_number, blocks, original)
                self.assertEqual([block for block in blocks if block["type"] == "source_line"], crops)
                for number in targets:
                    matches = [(index, block) for index, block in enumerate(blocks)
                               if block["type"] == "question" and
                               re.match(rf"^{number}[.．](?:\s|$)", block_text(block))]
                    self.assertEqual(len(matches), 1, (category, stem, page_number, number))
                    index, question = matches[0]
                    self.assertEqual(len(question["runs"]), 1)
                    self.assertFalse(re.search(r"[\x80-\x9f\ufffd]", block_text(question)))
                    if (category, stem, page_number) in MATCHING_CASES:
                        self.assertGreater(len(block_text(question)), len(f"{number}. "))
                        checked["matching"] += 1
                    else:
                        labels = []
                        for following in blocks[index + 1:]:
                            if following["type"] != "options":
                                break
                            labels.extend(item["label"] for item in following["items"])
                        self.assertEqual(labels, list("ABCD"),
                                         (category, stem, page_number, number, labels))
                        checked["choice"] += 1
        self.assertEqual(checked, {"choice": 58, "matching": 24})

    def test_pdf_confirmed_text_and_page_boundaries(self):
        samples = (
            ("cet4", "2020-12-01", 6, 40, "today still have the chance", None),
            ("cet6", "2020-07-01", 8, 37, "colleagues’ study shows two-year-olds", None),
            ("cet6", "2020-12-01", 6, 40, "Even the farmers know the data", None),
            ("cet6", "2020-12-01", 6, 41, "in turn, arouses doubts", None),
            ("cet6", "2021-06-02", 6, 45, "media attention throughout the world.", None),
            ("cet6", "2021-06-03", 6, 54, None,
             "It helps to protect one's intellectual property rights."),
        )
        for category, stem, page_number, number, stem_fragment, option_fragment in samples:
            with self.subTest(category=category, paper=stem, page=page_number, number=number):
                pdf = SOURCES / "english-exams-web-2026-09-26" / ".firecrawl" / category / f"{stem}.pdf"
                original = SOURCES / "english-exams-web-2026-09-26" / category / "papers" / f"{stem}.htm"
                with fitz.open(pdf) as document:
                    page = document[page_number - 1]
                    blocks = prepare(extract(page, unknown_glyphs=get_unknown_glyphs(page))["blocks"], page)
                recover_image_questions(category, stem, page_number, blocks, original)
                index = next(index for index, block in enumerate(blocks)
                             if block["type"] == "question" and
                             re.match(rf"^{number}[.．](?:\s|$)", block_text(block)))
                if stem_fragment:
                    self.assertIn(stem_fragment, block_text(blocks[index]))
                    self.assertNotIn("Section C", block_text(blocks[index]))
                if option_fragment:
                    self.assertIn(option_fragment, " ".join(
                        block_text(item) for item in blocks[index + 1]["items"]))


if __name__ == "__main__":
    unittest.main()
