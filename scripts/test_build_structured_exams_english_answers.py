"""PDF-backed regression checks for English books with appended answer pages."""

import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from bs4 import BeautifulSoup
import fitz

from scripts import build_structured_exams as builder


SOURCE = Path(__file__).resolve().parents[1] / "data/sources/english-exams-web-2026-09-26"
CASES = {
    "cet4:2015-06-01": ("cet4", "2015-06-01", 9, "答案与详解", "第1 套"),
    "cet6:2012-06-01": ("cet6", "2012-06-01", 20, "参考答案", "Interpersonal Communication"),
    "cet6:2012-12-01": ("cet6", "2012-12-01", 16, "参考答案", "Ranch Inn"),
    "cet6:2012-12-02": ("cet6", "2012-12-02", 16, "参考答案", "US Federal Reserve"),
    "cet6:2012-12-03": ("cet6", "2012-12-03", 15, "参考答案", "textbooks"),
}


class EmbeddedEnglishAnswersTests(unittest.TestCase):
    def test_original_pdf_page_boundaries_and_hashes(self):
        manifest = json.loads((SOURCE / "manifest.json").read_text())
        entries = {entry["file"]: entry for entry in manifest["papers"]}
        for document_id, (category, stem, start, marker, topic) in CASES.items():
            with self.subTest(document=document_id):
                source_entry = entries[f"{category}/papers/{stem}.htm"]
                pdf = SOURCE / ".firecrawl" / category / f"{stem}.pdf"
                self.assertEqual(hashlib.sha256(pdf.read_bytes()).hexdigest(),
                                 source_entry["source_pdf_sha256"])
                with fitz.open(pdf) as document:
                    self.assertNotIn(marker, document[start - 2].get_text())
                    self.assertIn(marker, document[start - 1].get_text())
                    self.assertIn(topic.casefold(), document[start - 1].get_text().casefold())
                original_html = BeautifulSoup((SOURCE / source_entry["file"]).read_text(), "html.parser")
                original_page = original_html.select_one(f'main > section[data-page="{start}"]')
                self.assertIsNotNone(original_page)
                selectable_text = "".join(node.get_text() for node in original_page.select("svg text"))
                self.assertGreater(len(selectable_text), 100)
                self.assertIn(marker, "".join(selectable_text.split()))
                self.assertIn(topic.casefold(), selectable_text.casefold())

    def test_answer_pages_stay_traceable_and_only_supported_keys_link(self):
        documents = {document["id"]: document for document in
                     json.loads((builder.ROOT / "documents.json").read_text())}
        with tempfile.TemporaryDirectory() as directory, patch.object(builder, "OUT", Path(directory)):
            rows = [builder.build_one(documents[document_id]) for document_id in CASES]
            builder.attach_answers(rows)
            papers = {row["id"]: json.loads((Path(directory) / row["json"]).read_text())
                      for row in rows}
            bank = builder.write_question_bank(rows)
            self.assertEqual(bank["questions"], 339)

            self.assertEqual(sum(q["recordType"] == "answer" for paper in papers.values()
                                 for q in paper["questions"]), 353)
            for document_id, (_, _, start, _, _) in CASES.items():
                with self.subTest(document=document_id):
                    paper = papers[document_id]
                    blocks = {block["id"]: block for block in paper["blocks"]}
                    self.assertEqual(paper["audit"]["embeddedAnswerStartPage"], start)
                    row = next(row for row in rows if row["id"] == document_id)
                    self.assertEqual(row["questions"], sum(q["recordType"] == "question"
                                                           for q in paper["questions"]))
                    self.assertEqual(paper["audit"]["embeddedAnswerRecords"],
                                     sum(q["recordType"] == "answer" for q in paper["questions"]))
                    self.assertTrue(all(block["sourceSection"] ==
                                        ("questions" if block["sourcePageIndex"] < start else "answers")
                                        for block in paper["blocks"]))
                    for question in paper["questions"]:
                        expected = "question" if int(question["sourcePages"][0]) < start else "answer"
                        self.assertEqual(question["recordType"], expected)
                        if expected == "answer":
                            self.assertEqual(question["options"], [])
                        if expected == "question" and question["answer"]["status"] == "explicit":
                            answer = question["answer"]
                            self.assertEqual(answer["sourceDocumentId"], document_id)
                            self.assertTrue(answer["sourceBlocks"])
                            self.assertTrue(all(blocks[bid]["sourceSection"] == "answers"
                                                for bid in answer["sourceBlocks"]))
                            if answer["value"] in {"A", "B", "C", "D"} and question["options"]:
                                self.assertIn(answer["value"] + ".",
                                              [option["label"] for option in question["options"]])

            def answer(document_id, number):
                return next(q["answer"] for q in papers[document_id]["questions"]
                            if q["recordType"] == "question" and q["number"] == str(number))

            self.assertEqual(answer("cet4:2015-06-01", 26)["value"], "prospering")
            self.assertEqual(answer("cet4:2015-06-01", 6)["status"], "missing")
            self.assertEqual(answer("cet6:2012-06-01", 26)["value"], "C")
            self.assertEqual(answer("cet6:2012-06-01", 82)["status"], "missing")
            self.assertEqual(answer("cet6:2012-12-01", 71)["value"], "A")
            self.assertEqual(answer("cet6:2012-12-02", 53)["value"], "A")
            self.assertEqual(answer("cet6:2012-12-02", 54)["value"], "B")
            self.assertEqual(answer("cet6:2012-12-02", 82)["value"],
                             "No matter how/However powerful China becomes")
            self.assertEqual(answer("cet6:2012-12-03", 1)["value"], "B")
            self.assertEqual(answer("cet6:2012-12-03", 60)["value"], "A")
            self.assertEqual(answer("cet6:2012-12-03", 86)["value"],
                             "it is inadvisable/unwise to attempt to conquer it")

            reader_row = next(row for row in rows if row["id"] == "cet6:2012-12-02")
            reader = BeautifulSoup((Path(directory) / reader_row["reader"]).read_text(), "html.parser")
            source_link = reader.select_one("#q-54-1 .answer-panel .answer-source")
            self.assertIsNotNone(source_link)
            self.assertTrue(source_link["href"].endswith("#b-26-11"))


if __name__ == "__main__":
    unittest.main()
