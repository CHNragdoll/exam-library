"""University PDF answers attach only to ten matched CET reading questions."""

import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import build_structured_exams as builder
from scripts.verified_cet_external_answers import (
    ANSWER_PDF, ANSWER_SHA, FIXTURE, PAPER_ID, QUESTION_PDF, QUESTION_SHA,
    SOURCE_PDF, SOURCE_SHA, attach_verified_reading, verified_reading_plan,
)


@unittest.skipUnless(FIXTURE.is_file(), "private CET reading evidence is unavailable")
class VerifiedCetExternalAnswersTests(unittest.TestCase):
    @staticmethod
    def papers():
        paper = json.loads((builder.OUT / "papers/cet4/2016-12-03.json").read_text())
        for question in paper["questions"]:
            if question.get("number") not in {str(n) for n in range(46, 56)}:
                continue
            answer = question["answer"]
            if answer.get("status") == "explicit":
                if answer.get("externalSource", {}).get("kind") != "source_verified_cross_set_reading":
                    raise AssertionError("Target has an unrelated explicit answer")
                question["answer"] = {"value": None, "status": "missing"}
        return {PAPER_ID: paper}

    def test_all_three_pdf_hashes_match_fixed_sources(self):
        evidence = json.loads(FIXTURE.read_text())
        for path, digest, field in (
            (SOURCE_PDF, SOURCE_SHA, "sourcePdfSha256"),
            (QUESTION_PDF, QUESTION_SHA, "questionPdfSha256"),
            (ANSWER_PDF, ANSWER_SHA, "answerPdfSha256"),
        ):
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), digest)
            self.assertEqual(evidence[field], digest)

    def test_plan_attach_idempotence_and_other_answers_unchanged(self):
        papers = self.papers()
        before = copy.deepcopy(papers)
        self.assertEqual(len(verified_reading_plan(papers)), 10)
        self.assertEqual(papers, before)
        self.assertEqual(attach_verified_reading(papers), 10)
        self.assertEqual(attach_verified_reading(papers), 0)
        expected = dict(zip(map(str, range(46, 56)), "CADAB DDBAC".replace(" ", "")))
        for question in papers[PAPER_ID]["questions"]:
            if question.get("number") in expected and question.get("recordType") == "question":
                self.assertEqual(question["answer"]["value"], expected[question["number"]])
                self.assertEqual(question["answer"]["externalSource"]["answerPdfSha256"], ANSWER_SHA)
            else:
                original = next(q for q in before[PAPER_ID]["questions"] if q["id"] == question["id"])
                self.assertEqual(question["answer"], original["answer"])

    def test_changed_option_or_answer_conflict_rejects_entire_batch(self):
        for mutate in (
            lambda p: next(q for q in p[PAPER_ID]["questions"] if q.get("number") == "46")
                ["options"][2].update(text="different option"),
            lambda p: next(q for q in p[PAPER_ID]["questions"] if q.get("number") == "55")
                ["answer"].update(value="D", status="explicit"),
        ):
            papers = self.papers()
            mutate(papers)
            before = copy.deepcopy(papers)
            with self.assertRaises(ValueError):
                attach_verified_reading(papers)
            self.assertEqual(papers, before)

    def test_fixture_or_university_pdf_change_rejects_entire_batch(self):
        papers = self.papers()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fixture.json"
            evidence = json.loads(FIXTURE.read_text())
            evidence["questions"][0]["answerLetter"] = "D"
            path.write_text(json.dumps(evidence))
            with self.assertRaisesRegex(ValueError, "university answer differs"):
                attach_verified_reading(papers, fixture_path=path)
            fake_pdf = Path(directory) / "questions.pdf"
            fake_pdf.write_bytes(b"changed source")
            with self.assertRaisesRegex(ValueError, "PDF hash changed"):
                attach_verified_reading(papers, question_pdf=fake_pdf)
        self.assertEqual(len(verified_reading_plan(papers)), 10)

    def test_temp_build_changes_only_ten_reading_answers(self):
        document = next(doc for doc in json.loads((builder.ROOT / "documents.json").read_text())
                        if doc["id"] == PAPER_ID)
        with tempfile.TemporaryDirectory() as directory, patch.object(builder, "OUT", Path(directory)), \
                patch.object(builder, "attach_verified_reading", return_value=0):
            row = builder.build_one(document)
            builder.attach_answers([row])
            baseline = json.loads((Path(directory) / row["json"]).read_text())
        with tempfile.TemporaryDirectory() as directory, patch.object(builder, "OUT", Path(directory)):
            row = builder.build_one(document)
            builder.attach_answers([row])
            attached = json.loads((Path(directory) / row["json"]).read_text())
            audit = json.loads((Path(directory) / "public-english-answer-audit.json").read_text())
        self.assertEqual(audit["sourceVerifiedCetReadingAttached"], 10)
        changed = [before["number"] for before, after in zip(baseline["questions"], attached["questions"])
                   if before["answer"] != after["answer"]]
        self.assertEqual(changed, [str(n) for n in range(46, 56)])


if __name__ == "__main__":
    unittest.main()
