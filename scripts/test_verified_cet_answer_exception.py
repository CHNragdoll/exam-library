"""The single CET grid exception must stay tied to its original PDF and Q50."""

import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import build_structured_exams as builder
from scripts.verified_cet_answer_exception import (
    EVIDENCE, PDF_SHA256, PAPER_ID, SOURCE_MANIFEST,
    attach_verified_q50, verified_q50_plan,
)


@unittest.skipUnless(EVIDENCE.is_file(), "private Q50 evidence is unavailable")
class VerifiedCetAnswerExceptionTests(unittest.TestCase):
    @staticmethod
    def papers():
        paper = json.loads((builder.OUT / "papers/cet6/2018-12-02.json").read_text())
        # Canonical data may later contain this very attachment. Test the
        # importer against a source-identical, unanswered in-memory copy.
        question = next(q for q in paper["questions"] if q.get("number") == "50"
                        and q.get("recordType") == "question")
        question["answer"] = {
            "value": None, "solution": None, "explanation": None,
            "commentary": None, "knowledge": None, "status": "missing",
        }
        return {PAPER_ID: paper}

    @staticmethod
    def question(papers):
        return next(q for q in papers[PAPER_ID]["questions"]
                    if q.get("number") == "50" and q.get("recordType") == "question")

    def test_private_evidence_matches_local_original_pdf_and_capture(self):
        evidence = json.loads(EVIDENCE.read_text())
        original = (builder.ROOT.parent / "english-exams-web-2026-09-26"
                    / ".firecrawl/cet6/2018-12-02.pdf")
        self.assertEqual(hashlib.sha256(original.read_bytes()).hexdigest(), PDF_SHA256)
        self.assertEqual(evidence["sourcePdfSha256"], PDF_SHA256)
        capture = json.loads((builder.ROOT.parents[2] / ".local/answer-keys/burningvocabulary.json")
                             .read_text())
        source = [entry for entry in capture["papers"] if entry["paperId"] == PAPER_ID]
        self.assertEqual(len(source), 1)
        self.assertEqual(source[0]["sourceUrl"], evidence["sourceUrl"])
        self.assertEqual(source[0]["answers"][49], "50-C-")
        self.assertEqual(evidence["gridAnswers46To50"], ["C", "A", "B", "A", "C"])

    def test_attaches_only_q50_then_is_idempotent(self):
        papers = self.papers()
        before = copy.deepcopy(papers)
        self.assertIsNotNone(verified_q50_plan(papers))
        self.assertEqual(papers, before, "planning must not mutate papers")
        self.assertEqual(attach_verified_q50(papers), 1)
        self.assertEqual(self.question(papers)["answer"]["value"], "C")
        self.assertEqual(self.question(papers)["answer"]["externalSource"]["sourcePdfSha256"],
                         PDF_SHA256)
        self.assertEqual(attach_verified_q50(papers), 0)
        before_q50 = self.question(before)
        self.assertEqual(
            [(q["id"], q["answer"]) for q in papers[PAPER_ID]["questions"] if q is not self.question(papers)],
            [(q["id"], q["answer"]) for q in before[PAPER_ID]["questions"] if q is not before_q50],
        )

    def test_wrong_paper_number_option_and_existing_answer_fail_closed(self):
        for name, mutate in (
            ("paper", lambda p: p[PAPER_ID].update(id="cet6:2018-12-01")),
            ("question id", lambda p: self.question(p).update(id="q-50-2")),
            ("duplicate number", lambda p: p[PAPER_ID]["questions"].append(copy.deepcopy(self.question(p)))),
            ("printed option", lambda p: self.question(p)["options"][2].update(text="Different choice")),
            ("answer conflict", lambda p: self.question(p)["answer"].update(value="D", status="explicit")),
        ):
            with self.subTest(name=name):
                papers = self.papers()
                mutate(papers)
                before = copy.deepcopy(papers)
                with self.assertRaises(ValueError):
                    attach_verified_q50(papers)
                self.assertEqual(papers, before)

    def test_changed_fixture_or_source_pdf_hash_fail_closed(self):
        papers = self.papers()
        evidence = json.loads(EVIDENCE.read_text())
        manifest = json.loads(SOURCE_MANIFEST.read_text())
        with tempfile.TemporaryDirectory() as directory:
            fixture_path = Path(directory) / "evidence.json"
            manifest_path = Path(directory) / "manifest.json"
            evidence["sourcePdfSha256"] = "0" * 64
            fixture_path.write_text(json.dumps(evidence))
            with self.assertRaisesRegex(ValueError, "sourcePdfSha256"):
                attach_verified_q50(papers, fixture_path, SOURCE_MANIFEST)
            evidence["sourcePdfSha256"] = PDF_SHA256
            fixture_path.write_text(json.dumps(evidence))
            source = next(row for row in manifest["papers"]
                          if row.get("source_url") == evidence["sourceUrl"])
            source["source_pdf_sha256"] = "0" * 64
            manifest_path.write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, "source PDF provenance"):
                attach_verified_q50(papers, fixture_path, manifest_path)
            bad_pdf = Path(directory) / "wrong.pdf"
            bad_pdf.write_bytes(b"not the reviewed PDF")
            with self.assertRaisesRegex(ValueError, "local original PDF hash"):
                attach_verified_q50(papers, fixture_path, SOURCE_MANIFEST, bad_pdf)
        self.assertEqual(self.question(papers)["answer"]["status"], "missing")

    def test_selected_paper_build_uses_exception_without_other_answer_changes(self):
        document = next(doc for doc in json.loads((builder.ROOT / "documents.json").read_text())
                        if doc["id"] == PAPER_ID)
        with tempfile.TemporaryDirectory() as directory, patch.object(builder, "OUT", Path(directory)), \
                patch.object(builder, "attach_verified_q50", return_value=0):
            baseline_row = builder.build_one(document)
            builder.attach_answers([baseline_row])
            baseline = json.loads((Path(directory) / baseline_row["json"]).read_text())
        with tempfile.TemporaryDirectory() as directory, patch.object(builder, "OUT", Path(directory)):
            row = builder.build_one(document)
            builder.attach_answers([row])
            attached = json.loads((Path(directory) / row["json"]).read_text())
            audit = json.loads((Path(directory) / "public-english-answer-audit.json").read_text())
        self.assertEqual(audit["sourceVerifiedCetGridExceptionAttached"], 1)
        changed = [(before["id"], after["answer"]["value"])
                   for before, after in zip(baseline["questions"], attached["questions"])
                   if before["answer"] != after["answer"]]
        self.assertEqual(changed, [("q-50-1", "C")])


if __name__ == "__main__":
    unittest.main()
