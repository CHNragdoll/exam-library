"""Source-backed checks for politics analysis-question prompts."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from bs4 import BeautifulSoup

from scripts import build_structured_exams as builder


# These analysis-question pairs were checked against the original PDF text and
# the corresponding reflow blocks. Keeping the cases here avoids coupling the
# regression to a regenerated source-integrity audit report.
EXPECTED_PAIR_QUESTIONS = {
    2004: (34, 35, 37),
    2005: (34, 35, 36, 37),
    2006: (34, 35, 36, 37, 38),
    2007: (34, 35, 36, 37, 38),
    2008: (34, 35, 36, 37, 38),
    2009: (34, 35, 36, 37, 38),
    2010: (34, 35, 36, 37, 38),
    2011: (34, 35, 36, 37),
    2012: (34, 35, 36, 37, 38),
    2013: (34, 35, 36, 37, 38),
    2014: (35, 36, 38),
    2015: (34, 35, 36, 37, 38),
    2016: (34, 35, 36, 37, 38),
    2017: (34, 35, 36, 37),
    2018: (34, 36, 37, 38),
    2019: (34, 35, 36, 37, 38),
    2020: (34, 35, 36, 37, 38),
    2021: (34, 35, 36, 37, 38),
}


class PoliticsSubquestionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.documents = {doc["id"]: doc for doc in json.loads(
            (builder.ROOT / "documents.json").read_text(encoding="utf-8"))}

    def build_paper(self, year):
        with tempfile.TemporaryDirectory() as directory, patch.object(builder, "OUT", Path(directory)):
            row = builder.build_one(self.documents[f"politics:{year}-questions"])
            paper = json.loads((Path(directory) / row["json"]).read_text(encoding="utf-8"))
            preview = BeautifulSoup((Path(directory) / row["reader"]).read_text(encoding="utf-8"),
                                    "html.parser")
        return paper, preview

    def test_2022_prompts_end_before_numbered_answer_notes(self):
        paper, preview = self.build_paper(2022)
        blocks = {block["id"]: block for block in paper["blocks"]}
        for number in range(34, 39):
            question = next(q for q in paper["questions"] if q["number"] == str(number))
            self.assertEqual([part["number"] for part in question["subquestions"]], ["1", "2"])
            self.assertTrue(all("答题思路" not in part["text"] for part in question["subquestions"]))
            source_block = preview.find(id=question["subquestions"][0]["sourceBlockId"])
            paragraphs = [" ".join(p.get_text(" ", strip=True).split())
                          for p in source_block.select(".paragraph-group > p")]
            for part in question["subquestions"]:
                self.assertTrue(any(" ".join(part["text"].split()) in text
                                    for text in paragraphs),
                                f"2022 question {number} part {part['number']} shares a paragraph")
            # The original source retains the printed hint. The reader preview
            # and unrevealed question text must stop before that answer section.
            note = question["embeddedAnswerNote"]
            self.assertTrue(any("答题思路" in blocks[bid]["text"]
                                for bid in note["sourceBlocks"]))
            self.assertNotIn("答题思路", source_block.get_text())
            self.assertNotIn("答题思路", question["stem"])
            self.assertEqual(question["answer"]["solution"], note["text"])

    def test_numbered_explanations_are_not_prompts(self):
        cases = ((2007, "38", {"b-6-1", "b-6-2", "b-6-3"}, ["b-6-6", "b-6-7"]),
                 (2008, "34", {"b-4-5", "b-4-6"}, ["b-4-2", "b-4-3", "b-4-4"]))
        for year, number, explanation_blocks, prompt_blocks in cases:
            with self.subTest(year=year, number=number):
                paper, _ = self.build_paper(year)
                question = next(q for q in paper["questions"] if q["number"] == number)
                self.assertEqual([part["sourceBlockId"] for part in question["subquestions"]],
                                 prompt_blocks)
                self.assertFalse(explanation_blocks & {
                    part["sourceBlockId"] for part in question["subquestions"]})

    def test_circled_and_single_printed_prompts_are_kept(self):
        paper_2003, _ = self.build_paper(2003)
        question_34 = next(q for q in paper_2003["questions"] if q["number"] == "34")
        self.assertEqual([part["number"] for part in question_34["subquestions"]],
                         ["1", "2", "3"])
        self.assertTrue(question_34["subquestions"][0]["text"].startswith("①"))

        paper_2018, _ = self.build_paper(2018)
        question_35 = next(q for q in paper_2018["questions"] if q["number"] == "35")
        self.assertEqual([part["number"] for part in question_35["subquestions"]], ["1"])

    def test_2004_to_2021_pairs_have_source_linked_metadata(self):
        self.assertEqual(sum(map(len, EXPECTED_PAIR_QUESTIONS.values())), 82)
        for year, numbers in EXPECTED_PAIR_QUESTIONS.items():
            paper, _ = self.build_paper(year)
            blocks = {block["id"]: block for block in paper["blocks"]}
            for number in numbers:
                with self.subTest(year=year, number=number):
                    question = next(q for q in paper["questions"] if q["number"] == str(number))
                    parts = question["subquestions"]
                    self.assertEqual([part["number"] for part in parts[:2]], ["1", "2"])
                    self.assertTrue(all(part["sourceBlockId"] in question["sourceBlocks"]
                                        and part["text"] in blocks[part["sourceBlockId"]]["text"]
                                        for part in parts[:2]))


if __name__ == "__main__":
    unittest.main()
