"""Source-PDF regressions for localized unmapped glyph fallback."""

from pathlib import Path
import re
import sys
import unittest

import fitz

sys.path.insert(0, str(Path(__file__).parent / "tools"))
from encoding import get_unknown_glyphs
from extract import extract


SOURCE_PDF = (
    Path(__file__).parents[1]
    / "english-exams-web-2026-09-26/.firecrawl/cet6/2021-06-03.pdf"
)


class GlyphFallbackTest(unittest.TestCase):
    def test_chinese_glosses_do_not_turn_english_lines_into_images(self):
        with fitz.open(SOURCE_PDF) as doc:
            page = doc[1]
            unknown = get_unknown_glyphs(page)
            self.assertEqual(3, sum(
                cp == 0xFFFD
                for span in page.get_texttrace()
                for cp, _gid, _origin, _bbox in span["chars"]
            ))
            self.assertLess(len(unknown), 30)
            affected = {(round(g["origin"][0], 3), round(g["origin"][1], 3)) for g in unknown}

            for block in page.get_text("rawdict")["blocks"]:
                for line in block.get("lines", []):
                    chars = [c for span in line["spans"] for c in span["chars"]]
                    text = "".join(c["c"] for c in chars)
                    if "old footage" not in text and "a hologram" not in text:
                        continue
                    for index, char in enumerate(chars):
                        origin = (round(char["origin"][0], 3), round(char["origin"][1], 3))
                        if text.index("(") <= index <= text.index(")"):
                            # extract.py joins glyph boxes by the *rawdict*
                            # origin, so a near texttrace origin is not enough.
                            self.assertIn(origin, affected, text)
                        else:
                            self.assertNotIn(origin, affected, text)
            extracted = extract(page, unknown_glyphs=unknown)
            footage_gloss = re.search(
                r"old footage (.*?) and photographs", extracted["source_text"]
            )
            self.assertIsNotNone(footage_gloss)
            self.assertEqual({"\ufffd"}, set(footage_gloss.group(1)))

    def test_nonparenthetical_unknown_keeps_conservative_line_fallback(self):
        with fitz.open(SOURCE_PDF) as doc:
            page = doc[2]
            unknown = get_unknown_glyphs(page)
            self.assertLess(len(unknown), 150)
            affected = {(round(g["origin"][0], 3), round(g["origin"][1], 3)) for g in unknown}
            matching = [
                [c for span in line["spans"] for c in span["chars"]]
                for block in page.get_text("rawdict")["blocks"]
                for line in block.get("lines", [])
                if "famous faces" in "".join(c["c"] for span in line["spans"] for c in span["chars"])
            ]
            self.assertEqual(1, len(matching))
            for char in matching[0]:
                if char["c"].strip():
                    self.assertIn((round(char["origin"][0], 3), round(char["origin"][1], 3)), affected)


if __name__ == "__main__":
    unittest.main()
