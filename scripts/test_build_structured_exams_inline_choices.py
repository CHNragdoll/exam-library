"""Compressed PDF text can join the next choice label to Chinese text."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import build_structured_exams as builder


class InlineChoiceTests(unittest.TestCase):
    def test_cs408_2010_q26_preserves_all_printed_choices(self) -> None:
        documents = json.loads((builder.ROOT / "documents.json").read_text(encoding="utf-8"))
        document = next(doc for doc in documents if doc["id"] == "cs408:2010-complete")
        with tempfile.TemporaryDirectory() as folder, patch.object(builder, "OUT", Path(folder)):
            row = builder.build_one(document)
            paper = json.loads((Path(folder) / row["json"]).read_text(encoding="utf-8"))
        for number in ("26", "27"):
            with self.subTest(number=number):
                question = next(q for q in paper["questions"]
                                if q["number"] == number and q["recordType"] == "question")
                self.assertEqual(question["status"], "complete")
                self.assertEqual([option["label"] for option in question["options"]],
                                 ["A.", "B.", "C.", "D."])
                if number == "26":
                    self.assertEqual(question["options"][0]["text"], "进程的时间片用完")
                    self.assertEqual(question["options"][1]["text"], "进程刚完成I/O，进入就绪列队")


if __name__ == "__main__":
    unittest.main()
