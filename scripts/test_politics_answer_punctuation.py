"""Keep checked answer punctuation aligned with the printed PDF pages."""

import json
from pathlib import Path
import unittest

import fitz


ROOT = Path(__file__).resolve().parents[1] / "data/sources/politics-answers-latex-2009-2023"
CORRECTIONS = (
    (1, "就马克思主义本身来说，，根本原因", "就马克思主义本身来说，根本原因"),
    (4, "就可以多“泡馍”，，“汤”少", "就可以多“泡馍”，“汤”少"),
    (9, "创立习近平新时代中国特色社会主义思想，，领导人民", "创立习近平新时代中国特色社会主义思想，领导人民"),
)


class PoliticsAnswerPunctuationTests(unittest.TestCase):
    def test_2022_three_scanned_paragraphs_use_visible_single_comma(self):
        source = json.loads((ROOT / "source/2022.json").read_text(encoding="utf-8"))
        html = (ROOT / "papers/2022-answers.htm").read_text(encoding="utf-8")
        tex = (ROOT / "tex/2022-answers.tex").read_text(encoding="utf-8")
        for page_number, ocr_error, printed in CORRECTIONS:
            with self.subTest(page=page_number):
                page = next(page for page in source["pages"] if page["source_page"] == page_number)
                paragraphs = [block["text"] for block in page["blocks"] if block["type"] == "paragraph"]
                self.assertTrue(any(printed in paragraph for paragraph in paragraphs))
                self.assertFalse(any(ocr_error in paragraph for paragraph in paragraphs))
                self.assertIn(printed, html)
                self.assertIn(printed, tex)

    def test_2021_extra_comma_is_in_original_pdf(self):
        spec = next(spec for spec in json.loads((ROOT / "sources.json").read_text(encoding="utf-8"))
                    if spec["year"] == 2021)
        with fitz.open(spec["path"]) as pdf:
            self.assertIn("错误。，", pdf[3].get_text(sort=True))
        source = json.loads((ROOT / "source/2021.json").read_text(encoding="utf-8"))
        self.assertTrue(any("错误。，" in block.get("text", "")
                            for block in source["pages"][3]["blocks"]))

    def test_2022_page_9_marxism_china_phrase_matches_print(self):
        phrase = "实现了马克思主义中国化新的飞跃。"
        ocr_error = "马克思主义甲国化"
        source = json.loads((ROOT / "source/2022.json").read_text(encoding="utf-8"))
        page = next(page for page in source["pages"] if page["source_page"] == 9)
        self.assertTrue(any(phrase in block.get("text", "") for block in page["blocks"]))
        for path in (ROOT / "papers/2022-answers.htm", ROOT / "tex/2022-answers.tex"):
            rendered = path.read_text(encoding="utf-8")
            self.assertIn(phrase, rendered)
            self.assertNotIn(ocr_error, rendered)


if __name__ == "__main__":
    unittest.main()
