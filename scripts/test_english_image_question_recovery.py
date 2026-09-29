"""PDF-checked image questions retain a crop or verified searchable source text."""

import importlib.util
import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch

from scripts import build_structured_exams as builder


REFLOW = Path(__file__).resolve().parents[1] / "data/sources/english-exams-reflow-latex"
ORIGINAL = Path(__file__).resolve().parents[1] / "data/sources/english-exams-web-2026-09-26"
RECOVERY_MODULE = REFLOW / "tools/recover_image_questions.py"
SPEC = importlib.util.spec_from_file_location("english_image_recovery", RECOVERY_MODULE)
assert SPEC and SPEC.loader
recovery = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(recovery)

# Each number is visibly printed as a separate question on the physical PDF page.
# Retain a crop where text is unreadable; otherwise verify searchable text
# against the original reader's PDF-derived SVG layer.
EXPECTED = {
    ("cet4", "2020-09-01", 8): (51, 52, 53, 54, 55),
    ("cet4", "2020-12-01", 6): (40,),
    ("cet4", "2020-12-02", 2): (16, 17, 18),
    ("cet4", "2020-12-03", 6): (51,),
    ("cet4", "2021-06-02", 7): (46, 47, 48, 49, 50),
    ("cet6", "2019-12-01", 12): (53, 54, 55),
    ("cet6", "2019-12-02", 12): (51, 52, 53, 54, 55),
    ("cet6", "2019-12-03", 8): (51, 52, 53, 54, 55),
    ("cet6", "2020-07-01", 8): (37, 39, 40, 41, 43, 44, 45),
    ("cet6", "2020-09-01", 12): (53, 54, 55),
    ("cet6", "2020-09-02", 7): (51, 52, 53, 54, 55),
    ("cet6", "2020-12-01", 2): (9, 10, 11, 12, 13, 14),
    ("cet6", "2020-12-01", 6): (38, 39, 40, 41, 42, 43),
    ("cet6", "2020-12-02", 1): (5, 6),
    ("cet6", "2020-12-03", 6): (51, 52, 53, 54, 55),
    ("cet6", "2021-06-02", 6): (36, 37, 38, 39, 40, 41, 42, 43, 44, 45),
    ("cet6", "2021-06-02", 8): (51, 52, 53, 54, 55),
    ("cet6", "2021-06-03", 6): (51, 52, 53, 54, 55),
}

MATCHING_PAGES = {
    ("cet4", "2020-12-01", 6),
    ("cet6", "2020-07-01", 8),
    ("cet6", "2020-12-01", 6),
    ("cet6", "2021-06-02", 6),
}


def question_number(block):
    if block["type"] != "question":
        return None
    text = "".join(run.get("text", "") for run in block.get("runs", []))
    match = re.match(r"\s*(\d+)\s*[.．]", text)
    return int(match.group(1)) if match else None


class EnglishImageQuestionRecoveryTests(unittest.TestCase):
    def test_all_82_questions_have_individual_reflow_blocks_and_source_evidence(self):
        self.assertEqual(sum(map(len, EXPECTED.values())), 82)
        for (category, stem, page_number), numbers in EXPECTED.items():
            with self.subTest(category=category, stem=stem, page=page_number):
                paper = json.loads((REFLOW / category / "papers" / f"{stem}.json").read_text())
                blocks = paper["pages"][page_number - 1]["blocks"]
                actual = [question_number(block) for block in blocks]
                for number in numbers:
                    self.assertEqual(actual.count(number), 1, (category, stem, page_number, number))
                if not any(block["type"] == "source_line" for block in blocks):
                    # A repaired text layer no longer needs an image fallback.
                    # Require every stem and A–D choice to match the original
                    # SVG text layer before accepting that replacement.
                    case = (category, stem, page_number)
                    source = ORIGINAL / category / "papers" / f"{stem}.htm"
                    self.assertTrue(source.is_file())
                    rows = recovery._svg_rows(source, page_number)
                    extracted = recovery._existing_questions(blocks, set(numbers), case)
                    self.assertEqual(set(extracted), set(numbers))
                    for number in numbers:
                        index, options = extracted[number]
                        self.assertEqual([option["label"] for option in options], list("ABCD"))
                        recovery._verify_extracted_question(
                            number, blocks[index], options, rows, case)

    def test_all_82_questions_survive_targeted_structured_build(self):
        self.assertEqual(sum(len(numbers) for key, numbers in EXPECTED.items()
                             if key in MATCHING_PAGES), 24)
        documents = {document["id"]: document for document in
                     json.loads((builder.ROOT / "documents.json").read_text())}
        cases_by_paper = {}
        for (category, stem, page_number), numbers in EXPECTED.items():
            cases_by_paper.setdefault(f"{category}:{stem}", {})[page_number] = numbers
        with tempfile.TemporaryDirectory() as directory, patch.object(builder, "OUT", Path(directory)):
            for document_id, pages in cases_by_paper.items():
                with self.subTest(document=document_id):
                    category, stem = document_id.split(":", 1)
                    row = builder.build_one(documents[document_id])
                    paper = json.loads((Path(directory) / row["json"]).read_text())
                    questions = [question for question in paper["questions"]
                                 if question["recordType"] == "question"]
                    for page_number, numbers in pages.items():
                        for number in numbers:
                            matches = [question for question in questions
                                       if question["number"] == str(number)
                                       and str(page_number) in question["sourcePages"]]
                            self.assertEqual(len(matches), 1,
                                             (document_id, page_number, number, matches))
                            labels = [option["label"] for option in matches[0]["options"]]
                            if (category, stem, page_number) in MATCHING_PAGES:
                                self.assertEqual(labels, [],
                                                 (document_id, page_number, number, labels))
                            else:
                                self.assertEqual(labels, ["A.", "B.", "C.", "D."],
                                                 (document_id, page_number, number, labels))
                                self.assertTrue(all(len(option["text"].strip()) >= 4
                                                    and "�" not in option["text"]
                                                    for option in matches[0]["options"]),
                                                (document_id, page_number, number,
                                                 matches[0]["options"]))


if __name__ == "__main__":
    unittest.main()
