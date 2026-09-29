"""Original-PDF-backed boundaries for English prose and word-bank cloze."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from bs4 import BeautifulSoup

from scripts import build_structured_exams as builder


DOCUMENTS = {doc["id"]: doc for doc in json.loads(
    (builder.ROOT / "documents.json").read_text(encoding="utf-8"))}
ORIGINAL_PDFS = builder.ROOT.parent / "english-exams-web-2026-09-26/.firecrawl"


class EnglishStructureTests(unittest.TestCase):
    def build(self, document_id: str) -> dict:
        doc = DOCUMENTS[document_id]
        with tempfile.TemporaryDirectory() as directory, patch.object(builder, "OUT", Path(directory)):
            row = builder.build_one(doc)
            return json.loads((Path(directory) / row["json"]).read_text(encoding="utf-8"))

    def pdf_text(self, document_id: str, first_page: int, last_page: int) -> str:
        category, stem = document_id.split(":", 1)
        pdf = ((builder.ROOT.parent / "kaoyan-web-2026-09-26/.firecrawl" / f"{stem}.pdf")
               if category == "kaoyan" else ORIGINAL_PDFS / category / f"{stem}.pdf")
        self.assertTrue(pdf.is_file(), f"Original PDF missing: {pdf}")
        return subprocess.run(
            ["pdftotext", "-f", str(first_page), "-l", str(last_page),
             "-layout", str(pdf), "-"],
            check=True, capture_output=True, text=True,
        ).stdout

    def test_line_leading_numbers_in_passage_remain_prose(self) -> None:
        cases = (
            ("tem8:2023", 2, "5.5% drop", "b-2-14", "5"),
            ("cet4:2020-12-01", 4, "5. 5 percent", "b-4-13", "5"),
            ("cet6:2019-06-01", 4, '15.2 percent "surge"', "b-4-4", "15"),
            ("cet6:2017-12-02", 8, "25.5 米", "b-8-17", "25"),
            ("cet4:2023-06-02", 5, "14. About 100", "b-5-6", "14"),
            ("cet4:2019-06-01", 5, "50.", "b-5-22", "50"),
        )
        for document_id, page, source, block_id, number in cases:
            with self.subTest(document=document_id):
                self.assertIn(source, self.pdf_text(document_id, page, page))
                paper = self.build(document_id)
                block = next(item for item in paper["blocks"] if item["id"] == block_id)
                self.assertEqual(block["role"], "content")
                if document_id == "cet6:2017-12-02":
                    # This prose is owned by the recovered unnumbered
                    # translation task, not by a spurious Q25.
                    self.assertEqual(block.get("questionId"), "q-translation-1")
                    translation = next(q for q in paper["questions"]
                                       if q["id"] == "q-translation-1")
                    self.assertIn(block_id, translation["sourceBlocks"])
                    self.assertEqual(translation["context"]["kind"], "translation_passage")
                else:
                    self.assertNotIn("questionId", block)
                questions = [q for q in paper["questions"]
                             if q["recordType"] == "question" and q["number"] == number]
                self.assertEqual(len(questions), 1)
                self.assertNotIn(block_id, questions[0]["sourceBlocks"])

    def test_printed_numbered_list_in_reading_passage_is_not_three_questions(self) -> None:
        source = self.pdf_text("cet6:2015-12-01", 8, 8)
        self.assertIn("1. Per-capita", source)
        self.assertIn("2.   Prevalence", source)
        paper = self.build("cet6:2015-12-01")
        blocks = {block["id"]: block for block in paper["blocks"]}
        for block_id in ("b-8-7", "b-8-8", "b-8-9"):
            self.assertEqual(blocks[block_id]["role"], "content")
            self.assertNotIn("questionId", blocks[block_id])
        for number in ("1", "2", "3"):
            questions = [q for q in paper["questions"]
                         if q["recordType"] == "question" and q["number"] == number]
            self.assertEqual(len(questions), 1)
            self.assertEqual(questions[0]["sourcePages"], ["1"])

    def test_tem4_part_iv_has_ten_source_linked_blanks_per_printed_form(self) -> None:
        for document_id, expected_forms in (("tem4:2022", 2), ("tem4:2023", 2),
                                            ("tem4:2024", 1), ("tem4:2025", 2)):
            with self.subTest(document=document_id):
                self.assertIn("PART IV", self.pdf_text(document_id, 3, 4))
                paper = self.build(document_id)
                cloze = [q for q in paper["questions"]
                         if q["recordType"] == "question" and
                         (q.get("context") or {}).get("kind") == "word_bank_cloze"]
                groups: dict[str, list[dict]] = {}
                for question in cloze:
                    groups.setdefault(question["context"]["id"], []).append(question)
                self.assertEqual(len(groups), expected_forms)
                self.assertEqual(len(cloze), 10 * expected_forms)
                self.assertEqual(len({word["id"] for questions in groups.values()
                                      for word in questions[0]["context"]["wordBank"]}),
                                 15 * expected_forms)
                for questions in groups.values():
                    self.assertEqual([q["number"] for q in questions],
                                     [str(n) for n in range(31, 41)])
                    context = questions[0]["context"]
                    self.assertIn("Decide which of the words", context["instructionText"])
                    self.assertNotIn("Decide which of the words", context["text"])
                    self.assertEqual(context["wordBankStatus"], "complete")
                    self.assertEqual(len(context["wordBank"]), 15)
                    self.assertTrue(all(q["questionType"] == "fill_blank"
                                        and not q["options"] and
                                        q["answer"]["status"] == "missing"
                                        for q in questions))
                    self.assertEqual(set(context["printedBlankNumbers"]), set(range(31, 41)))

    def test_2012_english_ii_gi_joe_blank_stays_in_cloze_passage(self) -> None:
        source = self.pdf_text("kaoyan:2012-02", 1, 1)
        self.assertIn("G.I. Joe had a", source)
        self.assertIn("11", source)
        paper = self.build("kaoyan:2012-02")
        blocks = {block["id"]: block for block in paper["blocks"]}
        question = next(q for q in paper["questions"] if q["recordType"] == "question"
                        and q["number"] == "11")
        context = question["context"]
        self.assertIn("b-1-7", context["passageSourceBlocks"])
        self.assertEqual(blocks["b-1-7"]["role"], "content")
        self.assertIn("G.I. Joe had a 11 career", context["text"])
        markers = [span.get_text(" ", strip=True)
                   for block_id in context["passageSourceBlocks"]
                   for span in BeautifulSoup(blocks[block_id]["contentHtml"], "html.parser")
                   .select(".blank")]
        self.assertEqual(set(markers), {str(number) for number in range(1, 21)})


if __name__ == "__main__":
    unittest.main()
