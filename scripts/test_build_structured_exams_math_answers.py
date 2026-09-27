"""Audit real mathematics answer numbering and continuation fields."""

import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch

from scripts import build_structured_exams as builder


def balanced_tex_delimiters(value: str) -> bool:
    stack = []
    for match in re.finditer(r"(\\+)([()\[\]])", value):
        if len(match.group(1)) % 2 == 0:
            continue  # TeX row break \\ followed by a parenthesis.
        marker = match.group(2)
        if marker in "([":
            stack.append(")" if marker == "(" else "]")
        elif not stack or stack.pop() != marker:
            return False
    return not stack


class MathAnswerExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        docs = json.loads((builder.ROOT / "documents.json").read_text())
        cls.answer_docs = [doc for doc in docs if doc["category"] == "math3" and doc["kind"] == "answers"]

    def build_answer_paper(self, doc, directory):
        with patch.object(builder, "OUT", directory):
            row = builder.build_one(doc)
        return json.loads((directory / row["json"]).read_text())

    def test_formula_arguments_are_not_answer_numbers_and_followups_are_in_solution(self):
        selected = {doc["year"]: doc for doc in self.answer_docs if doc["year"] in {2004, 2005, 2011, 2019}}
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            papers = {year: self.build_answer_paper(doc, folder) for year, doc in selected.items()}
        for year, token in ((2004, "y(0)"), (2005, "g(1)")):
            paper = papers[year]
            q = next(q for q in paper["questions"] if q["number"] == "19")
            self.assertEqual([m.group(1) for m in builder.math_answer_numbers(q["stem"])], ["19"])
            entry = builder.answer_entries(paper)["19"]
            self.assertIsNone(entry["value"])
            self.assertIn(token, entry["solution"])
            self.assertEqual(entry["sourceBlocks"], q["sourceBlocks"])

        for year, ids in ((2011, ("b-1-28", "b-1-30", "b-1-32", "b-1-34")),
                          (2019, ("b-1-29",))):
            paper = papers[year]
            blocks = {block["id"]: block for block in paper["blocks"]}
            entry = builder.answer_entries(paper)["22"]
            self.assertIsNone(entry["value"])
            self.assertIn("（Ⅱ）", entry["solution"])
            self.assertIn("（Ⅲ）", entry["solution"])
            for block_id in ids:
                self.assertIn(blocks[block_id]["text"], entry["solution"])
                self.assertIn(block_id, entry["sourceBlocks"])

    def test_all_math_answer_fields_conserve_continuations_and_tex(self):
        self.assertEqual(len(self.answer_docs), 33)
        audited_continuations = 0
        audited_fields = 0
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            for doc in self.answer_docs:
                paper = self.build_answer_paper(doc, folder)
                entries = builder.answer_entries(paper)
                blocks = {block["id"]: block for block in paper["blocks"]}
                questions = {q["id"]: q for q in paper["questions"]}
                for number, entry in entries.items():
                    self.assertTrue(number.isdigit(), doc["id"])
                    self.assertTrue(set(entry["sourceBlocks"]).issubset(blocks), doc["id"])
                    values = [entry[key] for key in ("value", "solution", "explanation", "commentary", "knowledge")]
                    for value in values:
                        if value:
                            audited_fields += 1
                            self.assertTrue(balanced_tex_delimiters(value), (doc["id"], number))
                    joined = "\n".join(value or "" for value in values)
                    for question_id in entry["sourceQuestionIds"]:
                        question = questions[question_id]
                        if int(question["number"]) < 15 or number != question["number"]:
                            continue
                        for block_id in question["sourceBlocks"]:
                            block = blocks[block_id]
                            if block["role"] == "content" and block["text"]:
                                audited_continuations += 1
                                self.assertIn(block["text"], joined, (doc["id"], number, block_id))
        self.assertGreaterEqual(audited_continuations, 16)
        self.assertGreater(audited_fields, 300)


if __name__ == "__main__":
    unittest.main()
