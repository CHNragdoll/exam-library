"""PDF-backed 2024 English I matching and translation tasks survive the export."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import build_structured_exams as builder


class Kaoyan2024SegmentsTests(unittest.TestCase):
    def test_matching_and_underlined_translation_have_ten_source_linked_records(self):
        documents = {row["id"]: row for row in
                     json.loads((builder.ROOT / "documents.json").read_text())}
        with tempfile.TemporaryDirectory() as directory, patch.object(builder, "OUT", Path(directory)):
            row = builder.build_one(documents["kaoyan:2024-01"])
            paper_path = Path(directory) / row["json"]
            paper = json.loads(paper_path.read_text())
            for number in range(41, 51):
                question = next(q for q in paper["questions"] if q["number"] == str(number))
                evidence = question["context"]["pdfEvidence"]
                self.assertTrue((paper_path.parent / evidence["path"]).is_file())

        questions = [q for q in paper["questions"] if q["recordType"] == "question"]
        by_number = {q["number"]: q for q in questions}
        self.assertEqual(len([q for q in questions if 41 <= int(q["number"]) <= 50]), 10)
        self.assertIn("40", by_number)
        self.assertIn("51", by_number)
        blocks = {block["id"]: block for block in paper["blocks"]}

        names = ("Hannah", "Buck", "Sara", "Victor", "Julia")
        for number, name in zip(range(41, 46), names):
            with self.subTest(number=number):
                q = by_number[str(number)]
                self.assertEqual(q["questionType"], "single_choice")
                self.assertIn(name, q["stem"])
                self.assertGreater(len(q["stem"]), len(name) + 50)
                if number < 45:
                    self.assertNotIn(names[number - 40], q["stem"])
                self.assertEqual([option["label"] for option in q["options"]],
                                 [f"{letter}." for letter in "ABCDEFG"])
                self.assertEqual(len({option["sourceOptionId"] for option in q["options"]}), 7)
                self.assertEqual(q["context"]["id"], "kaoyan:2024-01:part-b")
                self.assertEqual(q["context"]["choiceBankSourceBlock"], "b-12-3")
                self.assertIn("b-12-3", q["sourceBlocks"])
                self.assertEqual(q["answer"]["status"], "missing")
                self.assertTrue(all(blocks[bid]["page"] in {"11", "12"}
                                    for bid in q["sourceBlocks"]))

        starts = ("They sometimes travel", "The researchers are convinced",
                  "One possibility", "The volatile chemicals", "The experiment")
        for number, beginning in zip(range(46, 51), starts):
            with self.subTest(number=number):
                q = by_number[str(number)]
                self.assertEqual(q["questionType"], "free_response")
                self.assertTrue(q["stem"].startswith(beginning), q["stem"])
                self.assertEqual(q["sourcePages"], ["13"])
                self.assertEqual(q["options"], [])
                self.assertEqual(q["context"]["id"], "kaoyan:2024-01:part-c")
                self.assertEqual(q["context"]["kind"], "translation_passage")
                self.assertTrue(q["translationFragments"])
                self.assertEqual(q["answer"]["status"], "missing")
                for fragment in q["translationFragments"]:
                    self.assertIn(fragment["sourceBlockId"], q["sourceBlocks"])
                    self.assertGreater(fragment["underlineIndex"], 0)

        q46, q47 = by_number["46"], by_number["47"]
        self.assertEqual(q46["sourceBlocks"], ["b-13-2"])
        self.assertEqual(q47["sourceBlocks"], ["b-13-2"])
        self.assertFalse({f["underlineIndex"] for f in q46["translationFragments"]}
                         & {f["underlineIndex"] for f in q47["translationFragments"]})


if __name__ == "__main__":
    unittest.main()
