"""PDF-backed links for two embedded English answer sections with broken OCR boundaries."""

import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch

import fitz

from scripts import build_structured_exams as builder


def _normalized(text: str) -> str:
    return re.sub(r"[\W_]+", "", text).casefold()


PDF_ROOT = builder.ROOT.parent / "english-exams-web-2026-09-26" / ".firecrawl"


class EmbeddedEnglishAnswerReconciliationTests(unittest.TestCase):
    def test_cet4_same_set_answer_key_and_matching_paragraphs(self):
        documents = {doc["id"]: doc for doc in json.loads((builder.ROOT / "documents.json").read_text())}
        with tempfile.TemporaryDirectory() as directory, patch.object(builder, "OUT", Path(directory)):
            row = builder.build_one(documents["cet4:2015-06-01"])
            builder.attach_answers([row])
            paper = json.loads((Path(directory) / row["json"]).read_text())

        blocks = {block["id"]: block for block in paper["blocks"]}
        questions = {q["number"]: q for q in paper["questions"] if q["recordType"] == "question"}
        expected = {4: ("A", "11"), 46: ("K", "18"), 47: ("A", "18"),
                    48: ("G", "18"), 49: ("I", "18"), 50: ("B", "19"),
                    51: ("D", "19"), 52: ("E", "19"), 53: ("H", "20"),
                    54: ("F", "20"), 55: ("J", "20"), 61: ("B", "22")}
        with fitz.open(PDF_ROOT / "cet4" / "2015-06-01.pdf") as pdf:
            for number, (value, page) in expected.items():
                with self.subTest(number=number):
                    answer = questions[str(number)]["answer"]
                    self.assertEqual(answer["status"], "explicit")
                    self.assertEqual(answer["value"], value)
                    self.assertIn(page, answer["sourcePages"])
                    self.assertTrue(answer["sourceBlocks"])
                    self.assertTrue(all(blocks[bid]["sourceSection"] == "answers"
                                        for bid in answer["sourceBlocks"]))
                    pdf_text = _normalized(pdf[int(page) - 1].get_text())
                    if number == 4:
                        self.assertIn(_normalized("故本题答案为A"), pdf_text)
                    elif number == 48:
                        # The conclusion glyph is damaged in the PDF extraction;
                        # the printed G) paragraph and locator remain legible.
                        self.assertIn(_normalized("G) Companies are also trying"), pdf_text)
                    elif number == 61:
                        self.assertIn(_normalized("61. B)"), pdf_text)
                    else:
                        self.assertIn(_normalized("故答案为" + value), pdf_text)
        # The PDF page 19 prints question 50's B beneath question 49's I;
        # reflow placed both under answer record 49. Never overwrite 49 with B.
        self.assertEqual(questions["49"]["answer"]["sourceQuestionIds"], ["q-49-2"])
        self.assertEqual(questions["50"]["answer"]["sourceQuestionIds"], ["q-49-2"])
        self.assertIn("故答案为I", "".join(blocks[bid]["text"]
                                          for bid in questions["49"]["answer"]["sourceBlocks"]))
        self.assertIn("故答案为B", "".join(blocks[bid]["text"]
                                          for bid in questions["50"]["answer"]["sourceBlocks"]))
        self.assertIn("rather disappointing", blocks[questions["4"]["answer"]["sourceBlocks"][0]]["text"])
        self.assertIn("rich countries", "".join(blocks[bid]["text"]
                                                for bid in questions["61"]["answer"]["sourceBlocks"]))

    def test_cet6_answer_words_match_original_options_despite_printed_label_conflicts(self):
        documents = {doc["id"]: doc for doc in json.loads((builder.ROOT / "documents.json").read_text())}
        with tempfile.TemporaryDirectory() as directory, patch.object(builder, "OUT", Path(directory)):
            row = builder.build_one(documents["cet6:2012-06-01"])
            builder.attach_answers([row])
            paper = json.loads((Path(directory) / row["json"]).read_text())

        blocks = {block["id"]: block for block in paper["blocks"]}
        questions = {q["number"]: q for q in paper["questions"] if q["recordType"] == "question"}
        expected = {11: ("C", "A", "23"), 12: ("C", "C", "24"),
                    13: ("B", "A", "24"), 14: ("B", "C", "24"),
                    15: ("C", "D", "25"), 16: ("D", "B", "25"),
                    17: ("A", "C", "25"), 18: ("A", "A", "26")}
        with fitz.open(PDF_ROOT / "cet6" / "2012-06-01.pdf") as pdf:
            for number, (value, printed_label, page) in expected.items():
                with self.subTest(number=number):
                    q = questions[str(number)]
                    answer = q["answer"]
                    self.assertEqual(answer["status"], "explicit")
                    self.assertEqual(answer["value"], value)
                    self.assertEqual(answer["sourceQuestionIds"], [f"q-{number}-2"])
                    self.assertIn(page, answer["sourcePages"])
                    evidence = " ".join(blocks[bid]["text"] for bid in answer["sourceBlocks"])
                    match = re.search(r"【答案】\s*([A-D])\s*[)）.．]\s*([^【]+)", evidence)
                    self.assertIsNotNone(match)
                    self.assertEqual(match.group(1), printed_label)
                    printed_words = re.sub(r"\s+\d+\s*/\s*\d+\s*$", "", match.group(2)).strip()
                    option = next(option for option in q["options"] if option["label"] == value + ".")
                    self.assertEqual(_normalized(printed_words), _normalized(option["text"]))
                    self.assertIn(_normalized(printed_words), _normalized(pdf[int(page) - 1].get_text()))
                    question_page = int(q["sourcePages"][0])
                    self.assertIn(_normalized(option["text"]),
                                  _normalized(pdf[question_page - 1].get_text()))

    def test_cet6_translation_fill_is_taken_from_the_printed_complete_sentence(self):
        documents = {doc["id"]: doc for doc in json.loads((builder.ROOT / "documents.json").read_text())}
        with tempfile.TemporaryDirectory() as directory, patch.object(builder, "OUT", Path(directory)):
            row = builder.build_one(documents["cet6:2012-06-01"])
            builder.attach_answers([row])
            paper = json.loads((Path(directory) / row["json"]).read_text())

        questions = {q["number"]: q for q in paper["questions"] if q["recordType"] == "question"}
        expected = {82: ("worth $80 without a discount", "38"),
                    83: ("Facing the fierce competition from other companies", "38"),
                    84: ("nearly have nothing in common / hardly have anything in common", "38"),
                    85: ("have I realized that I cannot succeed with luck merely", "38"),
                    86: ("more species would have been extinct from the earth", "39")}
        with fitz.open(PDF_ROOT / "cet6" / "2012-06-01.pdf") as pdf:
            for number, (value, page) in expected.items():
                with self.subTest(number=number):
                    answer = questions[str(number)]["answer"]
                    self.assertEqual(answer["status"], "explicit")
                    self.assertEqual(answer["value"], value)
                    self.assertEqual(answer["sourceQuestionIds"], [f"q-{number}-2"])
                    self.assertIn(page, answer["sourcePages"])
                    self.assertTrue(answer["sourceBlocks"])
                    self.assertIn(_normalized(value), _normalized(pdf[int(page) - 1].get_text()))


if __name__ == "__main__":
    unittest.main()
