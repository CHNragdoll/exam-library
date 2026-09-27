"""The 2003–2004 politics PDFs print five choices in each multi-choice item."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import build_structured_exams as builder


class PoliticsFiveChoiceTests(unittest.TestCase):
    def test_early_politics_choices_preserve_printed_a_through_e(self) -> None:
        documents = {doc["id"]: doc for doc in json.loads(
            (builder.ROOT / "documents.json").read_text(encoding="utf-8"))}
        for year in (2003, 2004):
            document_id = f"politics:{year}-questions"
            with self.subTest(year=year), tempfile.TemporaryDirectory() as folder:
                with patch.object(builder, "OUT", Path(folder)):
                    row = builder.build_one(documents[document_id])
                paper = json.loads((Path(folder) / row["json"]).read_text(encoding="utf-8"))
                by_number = {int(q["number"]): q for q in paper["questions"]
                             if q["recordType"] == "question" and q["number"].isdigit()}
                for number in range(16, 31):
                    with self.subTest(year=year, number=number):
                        question = by_number[number]
                        self.assertEqual(question["questionType"], "multiple_choice")
                        self.assertEqual([o["label"] for o in question["options"]],
                                         ["A.", "B.", "C.", "D.", "E."])
                        self.assertEqual(question["status"], "complete")


if __name__ == "__main__":
    unittest.main()
