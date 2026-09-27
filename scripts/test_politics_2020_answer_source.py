"""Keep the printed 2020 politics answer 13 explanation in every reader."""

import hashlib
import json
from pathlib import Path
import re
import unittest

from bs4 import BeautifulSoup
import fitz


ROOT = Path(__file__).resolve().parents[1] / "data/sources/politics-answers-latex-2009-2023"
START = "本题考查全面依法治国的总抓手。"
END = "ACD不符合题意。"


def compact(text: str) -> str:
    return re.sub(r"\s+", "", text)


class Politics2020AnswerSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = next(spec for spec in json.loads((ROOT / "sources.json").read_text(encoding="utf-8"))
                        if spec["year"] == 2020)
        cls.source = json.loads((ROOT / "source/2020.json").read_text(encoding="utf-8"))

    def test_question_13_explanation_matches_original_pdf_page_2(self):
        pdf_path = Path(self.spec["path"])
        self.assertEqual(hashlib.sha256(pdf_path.read_bytes()).hexdigest(), self.spec["sha256"])
        with fitz.open(pdf_path) as pdf:
            page_text = pdf[1].get_text(sort=True)
        beginning = page_text.index(START)
        ending = page_text.index(END, beginning) + len(END)
        printed = page_text[beginning:ending]

        page = next(page for page in self.source["pages"] if page["source_page"] == 2)
        blocks = page["blocks"]
        answer_13 = next(i for i, block in enumerate(blocks)
                         if block["type"] == "heading" and block["text"].startswith("13. 【答案】"))
        answer_14 = next(i for i, block in enumerate(blocks[answer_13 + 1:], answer_13 + 1)
                         if block["type"] == "heading" and block["text"].startswith("14. 【答案】"))
        explanation = [block["text"] for block in blocks[answer_13 + 1:answer_14]
                       if block["type"] == "paragraph"]
        self.assertEqual(len(explanation), 1)
        self.assertEqual(compact(explanation[0]), compact(printed))

    def test_question_13_explanation_reaches_reflow_and_tex(self):
        source_page = next(page for page in self.source["pages"] if page["source_page"] == 2)
        source_text = next(block["text"] for block in source_page["blocks"]
                           if block["type"] == "paragraph" and block["text"].startswith(START))
        page = BeautifulSoup((ROOT / "papers/2020-answers.htm").read_text(encoding="utf-8"), "html.parser")
        answer_13 = next(node for node in page.select("main h2") if node.get_text(strip=True).startswith("13. 【答案】"))
        explanation = answer_13.find_next_sibling("p")
        self.assertIsNotNone(explanation)
        self.assertEqual(compact(explanation.get_text()), compact(source_text))
        tex = (ROOT / "tex/2020-answers.tex").read_text(encoding="utf-8")
        self.assertIn(source_text, tex)


if __name__ == "__main__":
    unittest.main()
