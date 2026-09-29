"""Source-backed regression checks for CET Reading Section A word-bank cloze."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_structured_exams as builder


DOCUMENTS = {doc["id"]: doc for doc in json.loads(
    (builder.ROOT / "documents.json").read_text(encoding="utf-8"))}
ORIGINAL_PDFS = builder.ROOT.parent / "english-exams-web-2026-09-26/.firecrawl"


class CETClozeTests(unittest.TestCase):
    def build(self, document_id: str) -> dict:
        doc = DOCUMENTS[document_id]
        with TemporaryDirectory() as directory, patch.object(builder, "OUT", Path(directory)):
            builder.build_one(doc)
            output = Path(directory) / "papers" / doc["category"] / (Path(doc["reflow"]).stem + ".json")
            return json.loads(output.read_text(encoding="utf-8"))

    @staticmethod
    def cloze_questions(paper: dict) -> list[dict]:
        return [question for question in paper["questions"]
                if question["context"] and question["context"].get("kind") == "word_bank_cloze"]

    def pdf_page_text(self, document_id: str, first_page: int, last_page: int) -> str:
        category, stem = document_id.split(":", 1)
        pdf = ORIGINAL_PDFS / category / f"{stem}.pdf"
        self.assertTrue(pdf.is_file(), f"Original source PDF missing: {pdf}")
        return subprocess.run(
            ["pdftotext", "-f", str(first_page), "-l", str(last_page), "-layout", str(pdf), "-"],
            check=True, capture_output=True, text=True,
        ).stdout

    def test_2022_cet4_preserves_shared_passage_and_verified_o_word(self) -> None:
        source = self.pdf_page_text("cet4:2022-06-01", 4, 5)
        self.assertIn("Questions 26 to 35", source)
        self.assertIn("0 ) underneath", source)  # Selectable PDF OCR; visible page prints O).
        paper = self.build("cet4:2022-06-01")
        questions = self.cloze_questions(paper)
        self.assertEqual([question["number"] for question in questions], [str(n) for n in range(26, 36)])
        self.assertTrue(all(question["questionType"] == "fill_blank" and not question["options"]
                            and question["answer"]["status"] == "missing" for question in questions))
        context = questions[0]["context"]
        self.assertTrue(all(question["context"] == context for question in questions))
        self.assertIn("just 26 under any condition", context["text"])
        self.assertEqual([word["label"] for word in context["wordBank"]],
                         [f"{letter}." for letter in builder.CET_CLOZE_LETTERS])
        self.assertEqual([word["sourceOrder"] for word in context["wordBank"]], list(range(1, 16)))
        o_word = context["wordBank"][-1]
        self.assertEqual((o_word["id"], o_word["text"], o_word["sourceLabel"]),
                         ("cet4:2022-06-01:word-bank:O", "underneath", "0)"))
        self.assertEqual(o_word["transcriptionCorrection"]["displayLabel"], "O.")
        self.assertIn("G. dental 0) underneath", context["wordBankSourceText"])
        bank_block = next(block for block in paper["blocks"] if block["id"] == o_word["sourceBlockId"])
        self.assertIn("G. dental 0) underneath", bank_block["text"])

    def test_2022_cet6_line_leading_33_stays_in_passage(self) -> None:
        source = self.pdf_page_text("cet6:2022-06-01", 4, 4)
        self.assertIn("33 . Regardless", source)
        self.assertIn("O) versatile", source)
        paper = self.build("cet6:2022-06-01")
        questions = self.cloze_questions(paper)
        self.assertEqual([question["number"] for question in questions], [str(n) for n in range(26, 36)])
        self.assertEqual(len(questions[0]["context"]["wordBank"]), 15)
        self.assertTrue(all(not question["options"] for question in questions))
        self.assertEqual(questions[7]["sourceBlocks"], ["b-4-9"])
        self.assertIn("33 . Regardless", questions[7]["context"]["text"])
        self.assertFalse(any(question["number"] == "33" and question["options"]
                             for question in paper["questions"]))

    def test_older_reading_cloze_uses_printed_36_to_45_range(self) -> None:
        source = self.pdf_page_text("cet4:2014-06-01", 3, 4)
        self.assertIn("Questions 36 to 45", source)
        paper = self.build("cet4:2014-06-01")
        questions = self.cloze_questions(paper)
        self.assertEqual([question["number"] for question in questions], [str(n) for n in range(36, 46)])
        self.assertEqual(questions[0]["context"]["printedBlankNumbers"], list(range(36, 46)))
        self.assertEqual(questions[0]["context"]["wordBankStatus"], "complete")

    def test_pdf_verified_missing_html_marker_is_partial_without_a_guessed_answer(self) -> None:
        source = self.pdf_page_text("cet4:2021-06-02", 3, 4)
        self.assertRegex(source, r"(?<!\d)31(?!\d)")
        paper = self.build("cet4:2021-06-02")
        questions = self.cloze_questions(paper)
        self.assertEqual(len(questions), 10)
        missing = [question for question in questions if question.get("sourceNumberUnverified")]
        self.assertEqual([question["number"] for question in missing], ["31"])
        self.assertEqual(missing[0]["status"], "partial")
        self.assertIsNone(missing[0]["answer"]["value"])
        self.assertEqual(missing[0]["context"]["numberEvidence"]["kind"], "verified_original_pdf_text")
        self.assertEqual(missing[0]["context"]["wordBankStatus"], "partial")
        self.assertTrue(any(fragment["sourceLabel"] == "0)" for fragment in
                            missing[0]["context"]["unresolvedWordBankFragments"]))
        self.assertNotIn("O.", [word["label"] for word in missing[0]["context"]["wordBank"]])

    def test_2015_cet4_embedded_key_links_all_ten_word_bank_answers(self) -> None:
        pdf = self.pdf_page_text("cet4:2015-06-01", 15, 16)
        expected = "A K G L D H J O E C".split()
        for word in ("announcing", "entitled", "critically", "potential",
                     "commitment", "develop", "enhance", "retain", "component", "challenges"):
            self.assertIn(word, pdf)
        doc = DOCUMENTS["cet4:2015-06-01"]
        with TemporaryDirectory() as directory, patch.object(builder, "OUT", Path(directory)):
            row = builder.build_one(doc)
            builder.attach_answers([row])
            paper = json.loads((Path(directory) / row["json"]).read_text(encoding="utf-8"))
        blocks = {block["id"]: block for block in paper["blocks"]}
        questions = {question["number"]: question for question in self.cloze_questions(paper)}
        self.assertEqual(len(questions), 10)
        for number, letter in zip(range(36, 46), expected):
            answer = questions[str(number)]["answer"]
            self.assertEqual((answer["status"], answer["value"]), ("explicit", letter))
            self.assertEqual(answer["sourceDocumentId"], paper["id"])
            self.assertEqual(len(answer["sourceBlocks"]), 1)
            evidence = blocks[answer["sourceBlocks"][0]]
            self.assertIn(evidence["page"], {"15", "16"})
            self.assertEqual(evidence["sourceSection"], "answers")
            self.assertIn("辨析题", evidence["text"][:100])

    def test_2018_cet6_printed_dot_after_label_is_not_part_of_word(self) -> None:
        for document_id, page, first_word in (
            ("cet6:2018-06-02", 4, "campaign"),
            ("cet6:2018-06-03", 1, "amassed"),
        ):
            with self.subTest(document=document_id):
                pdf = self.pdf_page_text(document_id, page, page)
                self.assertIn(f"A). {first_word}", pdf)
                paper = self.build(document_id)
                questions = self.cloze_questions(paper)
                self.assertEqual([question["number"] for question in questions],
                                 [str(number) for number in range(26, 36)])
                words = questions[0]["context"]["wordBank"]
                self.assertEqual(len(words), 15)
                self.assertEqual([word["sourceOrder"] for word in words], list(range(1, 16)))
                self.assertEqual(words[0]["text"], first_word)
                self.assertEqual(words[0]["sourceLabel"], "A).")
                self.assertEqual(words[0]["sourceText"], f"A. {first_word}")
                self.assertTrue(all(not word["text"].startswith(". ") for word in words))
                self.assertEqual([word["sourceLabel"] for word in words],
                                 [letter + ")." for letter in "ABCDEFGHIJKLMNO"])
                source_blocks = {block["id"]: block for block in paper["blocks"]}
                self.assertTrue(all(word["sourceText"] in
                                    source_blocks[word["sourceBlockId"]]["text"] for word in words))

    def test_2018_word_bank_rejects_stale_or_unproven_label_state(self) -> None:
        for printed, text in ((None, "campaign"), ("A).", ". campaign"),
                              ("A)", "campaign")):
            with self.subTest(printed=printed, text=text):
                attr = f' data-source-label="{printed}"' if printed else ""
                element = BeautifulSoup(
                    f'<ul class="options"><li><span class="option-label"{attr}>'
                    f'A.</span><span>{text}</span></li></ul>', "html.parser").ul
                with self.assertRaisesRegex(ValueError, "word-bank punctuation changed"):
                    builder.cet_word_bank_from(
                        element, "b-4-4", "cet6:2018-06-02")


if __name__ == "__main__":
    unittest.main()
