"""PDF-confirmed boundaries in 408 and politics question papers."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import build_structured_exams as builder


class OriginalQuestionBoundariesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.documents = {doc["id"]: doc for doc in json.loads(
            (builder.ROOT / "documents.json").read_text(encoding="utf-8"))}

    def build(self, document_id):
        with tempfile.TemporaryDirectory() as directory, patch.object(builder, "OUT", Path(directory)):
            row = builder.build_one(self.documents[document_id])
            return json.loads((Path(directory) / row["json"]).read_text(encoding="utf-8"))

    def test_408_complete_papers_separate_questions_from_answers(self):
        for year in (2011, 2013):
            with self.subTest(year=year):
                paper = self.build(f"cs408:{year}-complete")
                questions = [q for q in paper["questions"] if q["recordType"] == "question"]
                self.assertEqual([q["number"] for q in questions], [str(n) for n in range(1, 48)])
                if year == 2011:
                    self.assertIn("已知有6个顶点", questions[40]["stem"])
                else:
                    self.assertEqual(len([q for q in paper["questions"] if q["recordType"] == "answer"]), 47)

    def test_only_pdf_present_unnumbered_politics_questions_are_recovered(self):
        for year, number, first_block, last_block in (
            (2004, "36", "b-4-10", "b-4-12"),
            (2011, "25", "b-3-12", "b-3-13"),
        ):
            with self.subTest(year=year):
                paper = self.build(f"politics:{year}-questions")
                question = next(q for q in paper["questions"] if q["number"] == number)
                self.assertTrue(question["sourceNumberAbsent"])
                self.assertEqual((question["sourceBlocks"][0], question["sourceBlocks"][-1]),
                                 (first_block, last_block))
                self.assertEqual([q["number"] for q in paper["questions"]],
                                 [str(n) for n in range(1, 39 if year == 2011 else 38)])
        # The 2010 source PDF jumps directly from 20 to 22, with no 21 text.
        paper = self.build("politics:2010-questions")
        self.assertNotIn("21", [q["number"] for q in paper["questions"]])

    def test_decimal_continuation_is_not_question_five(self):
        paper = self.build("politics:2013-questions")
        self.assertEqual([q["number"] for q in paper["questions"]],
                         [str(n) for n in range(1, 39)])
        q35 = next(q for q in paper["questions"] if q["number"] == "35")
        self.assertIn("b-5-6", q35["sourceBlocks"])
        self.assertIn("5.8 万元", next(b for b in paper["blocks"] if b["id"] == "b-5-7")["text"])

    def test_material_headings_and_separate_subquestions_stay_in_parent(self):
        paper = self.build("politics:2014-questions")
        for number, material in (("34", "秸秆种蘑菇"), ("37", "鹦哥岭来了大学生")):
            question = next(q for q in paper["questions"] if q["number"] == number)
            owned = [b["text"] for b in paper["blocks"] if b["id"] in question["sourceBlocks"]]
            self.assertTrue(any(material in text for text in owned), number)
            self.assertEqual([part["number"] for part in question["subquestions"]], ["1", "2"])
        older = self.build("politics:2004-questions")
        self.assertEqual([part["number"] for part in next(q for q in older["questions"]
                                                            if q["number"] == "35")["subquestions"]],
                         ["1", "2"])
        earliest = self.build("politics:2003-questions")
        self.assertEqual([part["number"] for part in next(q for q in earliest["questions"]
                                                            if q["number"] == "34")["subquestions"]],
                         ["1", "2", "3"])

    def test_split_complete_choices_are_not_marked_partial(self):
        for doc, number in (("cs408:2020-questions", "21"),
                            ("politics:2023-questions", "18")):
            with self.subTest(doc=doc):
                paper = self.build(doc)
                question = next(q for q in paper["questions"] if q["number"] == number)
                self.assertEqual([option["label"] for option in question["options"]],
                                 ["A.", "B.", "C.", "D."])
                self.assertEqual(question["status"], "complete")


if __name__ == "__main__":
    unittest.main()
