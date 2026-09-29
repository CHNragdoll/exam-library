"""Regression checks for 2022 politics page seams and essay/answer boundaries."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import build_structured_exams as builder


class PoliticsSplitStemsTests(unittest.TestCase):
    def test_2022_essay_stems_include_all_printed_page_continuations(self):
        documents = json.loads((builder.ROOT / "documents.json").read_text(encoding="utf-8"))
        document = next(doc for doc in documents if doc["id"] == "politics:2022-questions")
        cases = {
            "27": (["7", "8"], ["b-7-11", "b-8-1"], "生死攸关的转折点"),
            "34": (["9", "10"], ["b-9-11", "b-10-1"], "底线思维"),
            "35": (["10", "11", "12"], ["b-10-2", "b-11-1", "b-12-1"], "迈进的重大"),
            "36": (["12", "13"], ["b-12-2", "b-13-1"], "就是一个主题"),
            "37": (["13", "14", "15"], ["b-13-2", "b-14-1", "b-15-1"], "条件更为"),
            "38": (["15", "16"], ["b-15-2", "b-16-1"], "和谐世界"),
        }
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            with patch.object(builder, "OUT", output):
                row = builder.build_one(document)
            paper = json.loads((output / row["json"]).read_text(encoding="utf-8"))
        blocks = {block["id"]: block for block in paper["blocks"]}
        for number, (pages, block_ids, seam) in cases.items():
            with self.subTest(number=number):
                question = next(q for q in paper["questions"] if q["number"] == number)
                self.assertEqual(question["sourcePages"], pages)
                self.assertTrue(set(block_ids).issubset(question["sourceBlocks"]))
                self.assertIn(seam, question["stem"])
                if number == "27":
                    self.assertEqual(question["stem"], "".join(blocks[bid]["text"] for bid in block_ids))
                    continue

                # Source blocks retain the printed answer hint, but the stem
                # shown before reveal must end after both actual prompts.
                source_text = "".join(blocks[bid]["text"] for bid in block_ids)
                display_text = "".join(
                    blocks[bid].get("presentation", {}).get("displayText", blocks[bid]["text"])
                    for bid in block_ids
                )
                self.assertEqual(question["stem"], display_text)
                self.assertIn("答题思路", source_text)
                self.assertNotIn("答题思路", question["stem"])
                self.assertEqual([subquestion["number"] for subquestion in question["subquestions"]],
                                 ["1", "2"])
                for subquestion in question["subquestions"]:
                    self.assertIn(subquestion["text"], question["stem"])

                note = question["embeddedAnswerNote"]
                self.assertEqual(note["kind"], "printed_answer_hint")
                self.assertEqual(note["sourceDocumentId"], document["id"])
                self.assertTrue(set(note["sourceBlocks"]).issubset(question["sourceBlocks"]))
                self.assertEqual(note["text"], question["answer"]["solution"])
                self.assertEqual(note["sourceBlocks"], question["answer"]["sourceBlocks"])
        for number in (4, 8, 20, 27):
            question = next(q for q in paper["questions"] if q["number"] == str(number))
            self.assertEqual(question["status"], "complete")
            self.assertEqual([option["label"] for option in question["options"]],
                             ["A.", "B.", "C.", "D."])
        self.assertEqual(next(q for q in paper["questions"] if q["number"] == "17")["sectionKind"],
                         "multiple_choice")


if __name__ == "__main__":
    unittest.main()
