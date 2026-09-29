"""Exercise the printed cross-form answers against temporary Math III papers."""

import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch
from copy import deepcopy

from scripts import build_structured_exams as builder


REFERENCE = re.compile(r"【同试卷\s*IV\s*第[^】]+题】")
ANSWER_FIELDS = ("value", "solution", "explanation", "commentary", "knowledge")


class MathCrossFormAnswerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        docs = json.loads((builder.ROOT / "documents.json").read_text(encoding="utf-8"))
        selected = [doc for doc in docs if doc["category"] == "math3"
                    and 1987 <= doc["year"] <= 1996]
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        cls.out = Path(cls.temp.name)
        with patch.object(builder, "OUT", cls.out):
            rows = [builder.build_one(doc) for doc in selected]
            builder.attach_answers(rows)
        cls.papers = {
            row["id"]: json.loads((cls.out / row["json"]).read_text(encoding="utf-8"))
            for row in rows
        }

    def test_all_printed_references_resolve_with_separate_provenance(self):
        references = []
        for year in range(1987, 1997):
            paper = self.papers[f"math3:{year}-questions"]
            answer_paper = self.papers[f"math3:{year}-answers"]
            answer_blocks = {block["id"] for block in answer_paper["blocks"]}
            for question in paper["questions"]:
                if question["recordType"] != "question":
                    continue
                answer = question["answer"]
                for reference in answer.get("references", []):
                    references.append((paper, question, reference))
                    self.assertEqual(answer["status"], "explicit")
                    self.assertNotIn("【同试卷", "\n".join(answer[key] or "" for key in ANSWER_FIELDS))
                    self.assertEqual(reference["resolutionStatus"], "resolved")
                    self.assertEqual(reference["targetPaperId"], paper["id"])
                    self.assertEqual(reference["targetForm"], "IV")
                    self.assertTrue(REFERENCE.fullmatch(reference["printedText"]))
                    self.assertEqual(reference["sourceDocumentId"], answer_paper["id"])
                    self.assertTrue(set(reference["sourceBlocks"]).issubset(answer_blocks))
                    self.assertEqual(reference["sourceBlocks"], answer["sourceBlocks"])
                    target = next(q for q in paper["questions"]
                                  if q["id"] == reference["targetQuestionId"])
                    self.assertEqual(reference["targetAnswerSourceDocumentId"],
                                     target["answer"]["sourceDocumentId"])
                    self.assertEqual(reference["targetAnswerSourceBlocks"],
                                     target["answer"]["sourceBlocks"])
                    self.assertFalse(any(REFERENCE.search(target["answer"].get(key) or "")
                                         for key in ANSWER_FIELDS))
        self.assertEqual(len(references), 91)
        self.assertEqual(sum(ref["targetSection"] == "main" for _, _, ref in references), 39)
        self.assertEqual(sum(ref["targetSection"] != "main" for _, _, ref in references), 52)

    def test_same_number_in_different_sections_does_not_capture_main_answer(self):
        paper = self.papers["math3:1990-questions"]
        question = next(q for q in paper["questions"] if q["id"] == "q-4-8")
        reference = question["answer"]["references"][0]
        self.assertEqual((reference["targetSection"], reference["targetNumber"],
                          reference["targetQuestionId"]), ("main", "4", "q-4-4"))
        self.assertIn("0.75", question["answer"]["solution"])
        self.assertNotIn("e^{-\\sin x}", question["answer"]["solution"])

    def test_1991_partial_reference_keeps_the_locally_printed_second_part(self):
        paper = self.papers["math3:1991-questions"]
        question = next(q for q in paper["questions"] if q["id"] == "q-13-2")
        answer = question["answer"]
        reference = answer["references"][0]
        self.assertEqual(reference["scope"], "part:1")
        self.assertEqual(reference["targetQuestionId"], "q-12-1")
        self.assertIn("P\\{X=0\\}", answer["solution"])
        self.assertIn("67", answer["solution"])
        self.assertIn("96", answer["solution"])
        self.assertIn("（2）", answer["solution"])
        self.assertIn("【同试卷IV 第十二题】", reference["originalAnswerText"])
        self.assertEqual(answer["sourceBlocks"], ["b-2-25"])

    def test_1996_sixth_question_uses_the_original_pdfs_seventh_reference(self):
        paper = self.papers["math3:1996-questions"]
        question = next(q for q in paper["questions"] if q["id"] == "q-6-2")
        answer = question["answer"]
        reference = answer["references"][0]
        self.assertEqual(reference["originalAnswerText"], "【同试卷 IV 第六题】")
        self.assertEqual(reference["printedText"], "【同试卷 IV 第七题】")
        self.assertEqual(reference["targetQuestionId"], "q-7-1")
        self.assertEqual(reference["pdfVerifiedCorrection"]["questionPage"], "58")
        self.assertEqual(reference["pdfVerifiedCorrection"]["answerPage"], "79")
        self.assertIn("销售额", answer["solution"])

    def test_unverified_target_cannot_be_scored(self):
        paper = deepcopy(self.papers["math3:1995-questions"])
        source = next(q for q in paper["questions"] if q["id"] == "q-2-3")
        target = next(q for q in paper["questions"] if q["id"] == "q-2-1")
        printed = source["answer"]["references"][0]["originalAnswerText"]
        source["answer"]["value"] = printed
        source["answer"].pop("references")
        target["answer"]["status"] = "missing"
        target["answer"]["value"] = None

        builder.resolve_math_cross_form_references({paper["id"]: paper})

        answer = source["answer"]
        self.assertEqual(answer["status"], "ambiguous")
        self.assertEqual(answer["references"][0]["resolutionStatus"], "unresolved")
        self.assertEqual(answer["references"][0]["originalAnswerText"], printed)
        self.assertFalse(any(answer[key] for key in ANSWER_FIELDS))
        self.assertIn("不可判分", answer["ambiguityReason"])


if __name__ == "__main__":
    unittest.main()
