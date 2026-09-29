"""Decimal measurements in printed passages do not create exam questions."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import build_structured_exams as builder


class KaoyanDecimalContinuationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.documents = {row["id"]: row for row in
                         json.loads((builder.ROOT / "documents.json").read_text())}

    def build_paper(self, stem):
        with tempfile.TemporaryDirectory() as directory, patch.object(builder, "OUT", Path(directory)):
            result = builder.build_one(self.documents[f"kaoyan:{stem}"])
            return json.loads((Path(directory) / result["json"]).read_text())

    def test_2012_english_two_percentage_continues_translation_q46(self):
        paper = self.build_paper("2012-02")
        questions = [q for q in paper["questions"] if q["recordType"] == "question"]
        self.assertEqual(len(questions), 48)
        self.assertEqual([q["number"] for q in questions].count("3"), 1)
        q46 = next(q for q in questions if q["number"] == "46")
        self.assertEqual(q46["sourceBlocks"],
                         [f"b-13-{index}" for index in range(2, 7)])
        continuation = next(b for b in paper["blocks"] if b["id"] == "b-13-6")
        self.assertEqual(continuation["role"], "content")
        self.assertEqual(continuation["questionId"], q46["id"])
        self.assertTrue(continuation["text"].startswith("3.3% of all Indians"))
        self.assertEqual([q["number"] for q in questions[-3:]], ["46", "47", "48"])

    def test_other_printed_decimals_do_not_create_questions(self):
        for stem, number, expected in (("2005-01", "26", 1), ("2006-01", "69", 0),
                                       ("2019-01", "1", 1)):
            with self.subTest(stem=stem):
                paper = self.build_paper(stem)
                questions = [q for q in paper["questions"] if q["recordType"] == "question"]
                self.assertEqual([q["number"] for q in questions].count(number), expected)


if __name__ == "__main__":
    unittest.main()
