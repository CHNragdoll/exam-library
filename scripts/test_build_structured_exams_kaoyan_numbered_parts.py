"""Printed English I Part B slots and underlined translations remain answerable."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import build_structured_exams as builder


class KaoyanNumberedPartsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.documents = {row["id"]: row for row in
                         json.loads((builder.ROOT / "documents.json").read_text())}

    def build_paper(self, stem):
        with tempfile.TemporaryDirectory() as directory, patch.object(builder, "OUT", Path(directory)):
            row = builder.build_one(self.documents[f"kaoyan:{stem}"])
            path = Path(directory) / row["json"]
            paper = json.loads(path.read_text())
            for question in paper["questions"]:
                evidence = (question.get("context") or {}).get("pdfEvidence")
                if evidence:
                    self.assertTrue((path.parent / evidence["path"]).is_file())
            return paper

    def test_2026_ordering_and_translation_are_ten_source_linked_tasks(self):
        paper = self.build_paper("2026-01")
        by_number = {q["number"]: q for q in paper["questions"]
                     if q["recordType"] == "question"}
        self.assertEqual(set(map(str, range(1, 53))), set(by_number))
        blocks = {b["id"]: b for b in paper["blocks"]}
        for number in range(41, 46):
            with self.subTest(number=number):
                question = by_number[str(number)]
                self.assertEqual(question["questionType"], "single_choice")
                self.assertEqual([o["label"] for o in question["options"]],
                                 [f"{letter}." for letter in "ABDEG"])
                self.assertEqual(question["context"]["fixedLetters"], ["F", "H", "C"])
                self.assertEqual(question["context"]["diagramSequence"],
                                 ["F", "41", "42", "H", "43", "C", "44", "45"])
                self.assertIn("b-12-5", question["sourceBlocks"])
                self.assertEqual(question["answer"]["status"], "missing")
        for number in range(46, 51):
            with self.subTest(number=number):
                question = by_number[str(number)]
                self.assertEqual(question["questionType"], "free_response")
                self.assertEqual(question["options"], [])
                self.assertEqual(question["context"]["kind"], "translation_passage")
                self.assertEqual(question["answer"]["status"], "missing")
                self.assertTrue(question["translationFragments"])
                self.assertTrue(question["stem"])
                for fragment in question["translationFragments"]:
                    self.assertIn(fragment["sourceBlockId"], question["sourceBlocks"])
                    self.assertIn(fragment["sourceBlockId"], blocks)

    def test_printed_variants_and_older_numbering(self):
        for year in range(2001, 2027):
            stem = f"{year}-01"
            with self.subTest(stem=stem):
                paper = self.build_paper(stem)
                questions = {q["number"]: q for q in paper["questions"]
                             if q["recordType"] == "question"}
                self.assertTrue(set(map(str, range(41, 46))) <= questions.keys())
                if year >= 2005:
                    self.assertTrue(set(map(str, range(46, 51))) <= questions.keys())
                else:
                    self.assertEqual(questions["41"]["questionType"], "free_response")
                    self.assertEqual(questions["41"]["context"]["kind"], "translation_passage")
                    self.assertEqual(questions["41"]["labels"][0]["kind"], "translation")
        gap = self.build_paper("2022-01")
        gap_question = next(q for q in gap["questions"] if q["number"] == "41")
        self.assertEqual(gap_question["context"]["kind"], "numbered_gap_passage")
        self.assertEqual(gap_question["context"]["taskForm"], "heading_match")
        self.assertEqual([option["label"] for option in gap_question["options"]],
                         [f"{letter}." for letter in "ABCDEFG"])
        decimal = self.build_paper("2006-01")
        self.assertNotIn("69", {q["number"] for q in decimal["questions"]})
        old = self.build_paper("2000-01")
        old_numbers = {q["number"] for q in old["questions"]
                       if q["recordType"] == "question"}
        self.assertFalse(set(map(str, range(41, 51))) & old_numbers)


if __name__ == "__main__":
    unittest.main()
