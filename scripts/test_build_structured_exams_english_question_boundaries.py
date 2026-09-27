"""PDF-verified English question numbers must survive into structured records."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import build_structured_exams as builder


CASES = {
    "cet4:2020-07-01": (7, {47: "How are business transactions done in big modern stores?"}),
    "cet6:2019-12-01": (10, {47: "Why does the Harvard neuroscientist say that lying takes work?"}),
    "cet6:2021-06-01": (7, {47: "What does the author think of the recent research?"}),
    "cet6:2020-09-02": (4, {
        37: "Many employers are eager to provide telemedicine service as a benefit to their employees because",
        41: "Some supporters of telemedicine hope states will accept each other's medical practice licenses as valid.",
    }),
}


class EnglishQuestionBoundaryTests(unittest.TestCase):
    def test_five_spaced_numbers_are_distinct_question_records(self):
        documents = {doc["id"]: doc for doc in json.loads((builder.ROOT / "documents.json").read_text())}
        with tempfile.TemporaryDirectory() as directory, patch.object(builder, "OUT", Path(directory)):
            for document_id, (source_page, expected) in CASES.items():
                with self.subTest(document=document_id):
                    row = builder.build_one(documents[document_id])
                    paper = json.loads((Path(directory) / row["json"]).read_text())
                    questions = [q for q in paper["questions"] if q["recordType"] == "question"]
                    for number, stem in expected.items():
                        matches = [q for q in questions if q["number"] == str(number)]
                        self.assertEqual(len(matches), 1)
                        self.assertEqual(matches[0]["sourcePages"], [str(source_page)])
                        self.assertEqual(matches[0]["stem"], f"{number}. {stem}")
                    if document_id == "cet6:2020-09-02":
                        q40 = next(q for q in questions if q["number"] == "40")
                        q41 = next(q for q in questions if q["number"] == "41")
                        blocks = {block["id"]: block for block in paper["blocks"]}
                        self.assertIn("telemedicine services.",
                                      [blocks[bid]["text"] for bid in q40["sourceBlocks"]])
                        self.assertNotIn(q41["sourceBlocks"][0], q40["sourceBlocks"])


if __name__ == "__main__":
    unittest.main()
