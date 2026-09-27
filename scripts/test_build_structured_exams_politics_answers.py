"""Source-backed answer-key checks for scanned political answer papers."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import build_structured_exams as builder


class PoliticsAnswerTests(unittest.TestCase):
    def test_standard_answer_label_keeps_all_choice_letters(self):
        for source, expected in (
            ("18.【标准答案】ABD", "ABD"),
            ("24.【标准答案】 A、B、C、D", "ABCD"),
        ):
            match = builder.ANSWER_RE.search(source)
            self.assertIsNotNone(match, source)
            self.assertEqual(builder.normalize_choice_answer(match.group(1)), expected)

    def test_scanned_answer_papers_have_all_33_explicit_choice_keys(self):
        documents = json.loads((builder.ROOT / "documents.json").read_text(encoding="utf-8"))
        by_id = {doc["id"]: doc for doc in documents}
        source_root = builder.ROOT.parent / "politics-answers-latex-2009-2023"
        with tempfile.TemporaryDirectory() as directory, patch.object(builder, "OUT", Path(directory)):
            for year in range(2010, 2019):
                with self.subTest(year=year):
                    source = json.loads((source_root / "source" / f"{year}.json").read_text(encoding="utf-8"))
                    self.assertEqual(source["extraction"]["original_pages"],
                                     len(source["pages"]))
                    self.assertIn("OCR", source["extraction"]["method"])

                    row = builder.build_one(by_id[f"politics:{year}-answers"])
                    paper = json.loads((Path(directory) / row["json"]).read_text(encoding="utf-8"))
                    entries = builder.answer_entries(paper)
                    self.assertTrue(set(map(str, range(1, 34))) <= set(entries))
                    for number in range(1, 34):
                        entry = entries[str(number)]
                        value = entry["value"]
                        self.assertIsNotNone(value, (year, number))
                        self.assertTrue(set(value) <= set("ABCD"), (year, number, value))
                        self.assertEqual(len(value), len(set(value)), (year, number, value))
                        if number <= 16:
                            self.assertEqual(len(value), 1, (year, number, value))
                        else:
                            self.assertGreaterEqual(len(value), 2, (year, number, value))
                        self.assertTrue(entry["sourceQuestionIds"], (year, number))
                        self.assertTrue(entry["sourceBlocks"], (year, number))

                    question_row = builder.build_one(by_id[f"politics:{year}-questions"])
                    builder.attach_answers([question_row, row])
                    linked = json.loads((Path(directory) / question_row["json"]).read_text(encoding="utf-8"))
                    choices = [question for question in linked["questions"]
                               if question["recordType"] == "question"
                               and question["questionType"] in {"single_choice", "multiple_choice"}]
                    self.assertTrue(choices, year)
                    for question in choices:
                        answer = question["answer"]
                        self.assertEqual(answer["value"], entries[question["number"]]["value"])
                        self.assertEqual(answer["status"], "explicit")
                        self.assertEqual(answer["sourceDocumentId"], f"politics:{year}-answers")
                        self.assertTrue(answer["sourceBlocks"])


if __name__ == "__main__":
    unittest.main()
