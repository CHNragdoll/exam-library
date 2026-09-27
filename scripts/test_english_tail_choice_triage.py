"""PDF-checked last English option candidates and section boundaries."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import fitz

from scripts import build_structured_exams as builder


ROOT = Path(__file__).resolve().parents[1]
REFLOW = ROOT / "data/sources/english-exams-reflow-latex"
ORIGINAL = ROOT / "data/sources/english-exams-web-2026-09-26/.firecrawl"


def paper(category, stem):
    return json.loads((REFLOW / category / "papers" / f"{stem}.json").read_text())


def run_text(block):
    return "".join(run["text"] for run in block.get("runs", []))


class EnglishTailChoiceTriageTests(unittest.TestCase):
    def test_original_pdf_evidence_for_all_seven_candidates(self):
        cases = (
            ("cet6", "2020-12-02", 1, ("4. A) Clearer road signs.",
                "B) More people driving safely.", "D_) More self-driving trucks on the road.")),
            ("cet6", "2018-06-02", 8, ("53. What does the author say about the value",
                "E) It is underestimated by profit-seeking employers.")),
            ("cet6", "2015-12-01", 7, ("56. Reflect on the responsibilities",
                "C)\nReadjust their practice")),
            ("cet6", "2014-12-01", 7, ("61. What was the University of Kent famous for?",
                "C) Its distinguished teaching staff.", "C) Its up-to-date course offerings.")),
            ("cet4", "2014-12-01", 7, ("61. Alex Pang’s new book",
                "AD) can hardly tear themselves away from the Internet")),
            ("cet4", "2018-06-01", 7, ("45. Digital access codes are criticized",
                "business.Section C", "D). You should decide on the best choice")),
        )
        for category, stem, page, fragments in cases:
            with self.subTest(category=category, stem=stem, page=page):
                with fitz.open(ORIGINAL / category / f"{stem}.pdf") as document:
                    text = document[page - 1].get_text()
                for fragment in fragments:
                    self.assertIn(fragment, text)
        with fitz.open(ROOT / "data/sources/kaoyan-web-2026-09-26/.firecrawl/2000-01.pdf") as document:
            text = document[12].get_text()
        self.assertIn("Section   III        Writing", text)
        self.assertIn("36. Directions:", text)
        self.assertIn("B.  Your  essay  must  be  written", text)

    def test_q4_and_printed_irregular_labels_are_preserved_in_reflow(self):
        blocks = paper("cet6", "2020-12-02")["pages"][0]["blocks"]
        index = next(i for i, block in enumerate(blocks)
                     if block["type"] == "question" and run_text(block) == "4.")
        self.assertEqual([item["label"] for block in blocks[index + 1:index + 4]
                          if block["type"] == "options" for item in block["items"]],
                         list("ABCD"))
        self.assertTrue(any(block["type"] == "source_line" for block in blocks[index + 1:index + 4]))

        blocks = paper("cet6", "2018-06-02")["pages"][7]["blocks"]
        second = next(i for i, block in enumerate(blocks) if block["type"] == "question" and
                      run_text(block).startswith("53. What does the author say about the value"))
        self.assertEqual([item["label"] for item in blocks[second + 1]["items"]],
                         ["B", "C", "D", "E"])

        blocks = paper("cet6", "2014-12-01")["pages"][6]["blocks"]
        index = next(i for i, block in enumerate(blocks) if block["type"] == "question" and
                     run_text(block).startswith("61. What was the University of Kent"))
        self.assertEqual([item["label"] for block in blocks[index + 1:index + 3]
                          for item in block["items"]], ["A", "C", "C", "D"])

        blocks = paper("cet6", "2015-12-01")["pages"][6]["blocks"]
        index = next(i for i, block in enumerate(blocks) if block["type"] == "question" and
                     run_text(block).startswith("56."))
        self.assertEqual([item["label"] for item in blocks[index + 1]["items"]], list("ABC"))

    def test_q61_and_q45_have_printed_line_boundaries_without_invented_options(self):
        blocks = paper("cet4", "2014-12-01")["pages"][6]["blocks"]
        index = next(i for i, block in enumerate(blocks) if block["type"] == "question" and
                     run_text(block).startswith("61."))
        self.assertEqual([item["label"] for item in blocks[index + 1]["items"]], list("ABC"))
        self.assertEqual(run_text(blocks[index + 1]["items"][2]),
                         "are fearful about using the cellphone or computer")
        self.assertEqual(blocks[index + 2]["type"], "paragraph")
        self.assertEqual(run_text(blocks[index + 2]),
                         "AD) can hardly tear themselves away from the Internet")

        blocks = paper("cet4", "2018-06-01")["pages"][6]["blocks"]
        index = next(i for i, block in enumerate(blocks) if block["type"] == "question" and
                     run_text(block).startswith("45."))
        self.assertEqual(run_text(blocks[index]),
                         "45. Digital access codes are criticized because they are profit-driven "
                         "just like the textbook business.")
        self.assertEqual(blocks[index + 1]["type"], "heading")
        self.assertEqual(run_text(blocks[index + 1]), "Section C")
        self.assertEqual(blocks[index + 2]["type"], "instruction")
        self.assertIn("D). You should decide", run_text(blocks[index + 2]))

    def test_structured_cards_do_not_turn_source_misprints_into_answers(self):
        documents = {document["id"]: document for document in
                     json.loads((builder.ROOT / "documents.json").read_text())}
        ids = ("cet6:2020-12-02", "cet6:2018-06-02", "cet6:2015-12-01",
               "cet6:2014-12-01", "cet4:2014-12-01", "cet4:2018-06-01",
               "kaoyan:2000-01")
        with tempfile.TemporaryDirectory() as directory, patch.object(builder, "OUT", Path(directory)):
            papers = {}
            for document_id in ids:
                row = builder.build_one(documents[document_id])
                papers[document_id] = json.loads((Path(directory) / row["json"]).read_text())

        def question(document_id, number, page, ordinal=0):
            matches = [q for q in papers[document_id]["questions"]
                       if q["recordType"] == "question" and q["number"] == str(number)
                       and str(page) in q["sourcePages"]]
            return matches[ordinal]

        self.assertEqual([o["label"] for o in question("cet6:2020-12-02", 4, 1)["options"]],
                         ["A.", "B.", "C.", "D."])
        self.assertEqual([o["label"] for o in question("cet6:2018-06-02", 53, 8, 1)["options"]],
                         ["B.", "C.", "D.", "E."])
        self.assertEqual([o["label"] for o in question("cet6:2015-12-01", 56, 7)["options"]],
                         ["A.", "B.", "C."])
        self.assertEqual([o["label"] for o in question("cet6:2014-12-01", 61, 7)["options"]],
                         ["A.", "C.", "C.", "D."])
        self.assertEqual([o["label"] for o in question("cet4:2014-12-01", 61, 7)["options"]],
                         ["A.", "B.", "C."])
        self.assertEqual(question("cet4:2018-06-01", 45, 7)["options"], [])
        writing = question("kaoyan:2000-01", 36, 13)
        self.assertEqual(writing["sectionKind"], "free_response")
        self.assertEqual(writing["questionType"], "free_response")
        self.assertEqual(writing["options"], [])
        self.assertIn("A. Study the following two pictures", writing["stem"])
        self.assertIn("3) Suggest counter-measures.", writing["stem"])


if __name__ == "__main__":
    unittest.main()
