"""Writing outline lines and signature directions remain inside the printed task."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from bs4 import BeautifulSoup

from scripts import build_structured_exams as builder


class KaoyanWritingRequirementsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.documents = {row["id"]: row for row in
                         json.loads((builder.ROOT / "documents.json").read_text())}

    def build_paper(self, stem):
        with tempfile.TemporaryDirectory() as directory, patch.object(builder, "OUT", Path(directory)):
            entry = builder.build_one(self.documents[f"kaoyan:{stem}"])
            paper = json.loads((Path(directory) / entry["json"]).read_text())
            reader = BeautifulSoup((Path(directory) / entry["reader"]).read_text(), "html.parser")
            return paper, reader

    def test_2002_to_2004_outlines_belong_to_q46(self):
        for year, page, first_index in ((2002, 12, 5), (2003, 12, 5), (2004, 12, 4)):
            with self.subTest(year=year):
                paper, reader = self.build_paper(f"{year}-01")
                writing = [q for q in paper["questions"] if q["recordType"] == "question"
                           and q["sectionTitle"] == "Section III Writing"]
                self.assertEqual([q["number"] for q in writing], ["46"])
                question = writing[0]
                expected = [f"b-{page}-{first_index}", f"b-{page}-{first_index + 1}"]
                self.assertTrue(set(expected) <= set(question["sourceBlocks"]))
                self.assertIn("1. ", question["stem"])
                self.assertIn("2. ", question["stem"])
                self.assertTrue(all(reader.find(id=bid) for bid in expected))

    def test_split_only_at_printed_do_not_sentence_boundary(self):
        for stem, block_id, count in (("2023-01", "b-14-6", 2),
                                      ("2017-01", "b-14-5", 3),
                                      ("2025-02", "b-14-7", 2)):
            with self.subTest(stem=stem):
                paper, reader = self.build_paper(stem)
                block = next(b for b in paper["blocks"] if b["id"] == block_id)
                presentation = block["presentation"]
                self.assertEqual(presentation["layoutKind"], "writing_instructions")
                self.assertEqual(len(presentation["instructions"]), count)
                self.assertEqual(" ".join(part["text"] for part in presentation["instructions"]),
                                 block["text"])
                self.assertTrue(any(part["strongPrefix"] == "Do not"
                                    for part in presentation["instructions"]))
                self.assertTrue(reader.find(id=block_id).select("strong"))

    def test_2024_email_signoff_remains_right_aligned(self):
        paper, _ = self.build_paper("2024-01")
        block = next(b for b in paper["blocks"] if b["id"] == "b-14-7")
        self.assertEqual(block["presentation"]["layoutKind"], "email")
        self.assertEqual(block["presentation"]["signoffAlignment"], "right")
        self.assertEqual([part["strongPrefix"] for part in block["presentation"]["instructions"]],
                         [None, "Do not"])


if __name__ == "__main__":
    unittest.main()
