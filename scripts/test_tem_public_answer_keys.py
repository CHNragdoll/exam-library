"""TEM public keys must match the exact paper and printed local choices."""

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest

from scripts import tem_public_answer_keys as tem


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data/sources/english-exams-web-2026-09-26/manifest.json"
PAPERS = ROOT / "data/sources/exam-library/structured/papers"
PRIVATE_CAPTURE = ROOT / ".local/answer-keys/burningvocabulary-tem.json"


def fixture():
    original = json.loads(SOURCE.read_text(encoding="utf-8"))
    rows = [row for row in original["papers"] if row["category"] in {"tem4", "tem8"}]
    papers = {}
    sources = []
    for row in rows:
        category, year = row["category"], row["year"]
        paper_id = f"{category}:{year}"
        paper = deepcopy(json.loads((PAPERS / category / f"{year}.json").read_text(encoding="utf-8")))
        # The canonical paper may already contain this exact import. Restore
        # only answers carrying verified TEM capture provenance in our private
        # test copy; preserve all unrelated source answers and ambiguous items.
        for question in paper["questions"]:
            answer = question["answer"]
            provenance = answer.get("externalSource") or {}
            if provenance.get("workerSha256") != tem.WORKER_SHA256:
                continue
            if (provenance.get("url") != row["source_url"] or
                    provenance.get("sourceDocumentUrl") != row["document_url"] or
                    provenance.get("sourcePdfSha256") != row["source_pdf_sha256"] or
                    provenance.get("answerToken") != f'{question["number"]}-{answer["value"]}' or
                    answer["status"] != "explicit" or
                    any(answer.get(field) for field in
                        ("solution", "explanation", "commentary", "knowledge"))):
                raise AssertionError(f"Unexpected existing TEM answer provenance: {paper_id}:{question['id']}")
            answer["value"] = None
            answer["status"] = "missing"
            del answer["externalSource"]
        papers[paper_id] = paper
        end = 50 if category == "tem4" else 24
        answers = [f"{n}-{'ABCDEFGHIJ'[n - 31] if category == 'tem4' and 31 <= n <= 40 else 'A'}"
                   for n in range(1, end + 1)]
        sources.append({
            "paperId": paper_id, "sourceUrl": row["source_url"],
            "sourceDocumentUrl": row["document_url"],
            "sourcePdfSha256": row["source_pdf_sha256"],
            "answers": answers,
        })
    capture = {"source": tem.ORIGIN, "capturedAt": "2026-09-29T00:00:00Z",
               "workerSha256": tem.WORKER_SHA256, "papers": sources}
    return papers, capture, original


class TemPublicAnswerKeysTests(unittest.TestCase):
    @unittest.skipUnless(PRIVATE_CAPTURE.is_file(), "private TEM capture is not installed")
    def test_private_capture_matches_local_source_pdfs_and_attaches_only_verified_questions(self):
        papers, _, original = fixture()
        capture = json.loads(PRIVATE_CAPTURE.read_text(encoding="utf-8"))
        for source in capture["papers"]:
            category, year = source["paperId"].split(":")
            pdf = SOURCE.parent / ".firecrawl" / category / f"{year}.pdf"
            self.assertEqual(sha256(pdf.read_bytes()).hexdigest(), source["sourcePdfSha256"])
        counts = tem.attach_tem_public_answer_keys(papers, capture, original)
        self.assertEqual(counts, {"attached": 266, "duplicateOrMissingNumber": 30})
        imported = [question for paper in papers.values() for question in paper["questions"]
                    if question["answer"].get("externalSource", {}).get("workerSha256")]
        self.assertEqual(sum(q["questionType"] == "single_choice" for q in imported), 256)
        self.assertEqual(sum(q["questionType"] == "fill_blank" for q in imported), 10)

    def test_unique_printed_choices_and_single_word_bank_attach(self):
        papers, capture, original = fixture()
        counts = tem.attach_tem_public_answer_keys(papers, capture, original)
        self.assertEqual(counts["attached"], 266)
        self.assertEqual(counts["duplicateOrMissingNumber"], 30)
        q2024 = {q["number"]: q for q in papers["tem4:2024"]["questions"]}
        self.assertEqual(q2024["31"]["answer"]["value"], "A")
        self.assertEqual(q2024["31"]["answer"]["externalSource"]["sourcePdfSha256"],
                         next(s["sourcePdfSha256"] for s in capture["papers"]
                              if s["paperId"] == "tem4:2024"))
        self.assertEqual(sum(q["answer"]["status"] == "explicit"
                             for q in papers["tem8:2025"]["questions"]), 24)
        self.assertTrue(all(q["answer"]["status"] == "missing" for q in papers["tem4:2025"]["questions"]
                            if q["number"] == "31"))

    def test_focused_build_attaches_only_present_tem_paper(self):
        papers, capture, original = fixture()
        focused = {"tem8:2025": papers["tem8:2025"]}
        counts = tem.attach_tem_public_answer_keys(focused, capture, original)
        self.assertEqual(counts, {"unmatchedPapers": 7, "attached": 24})
        self.assertEqual(sum(q["answer"]["status"] == "explicit"
                             for q in focused["tem8:2025"]["questions"]), 24)

    def test_second_import_is_idempotent_and_preserves_first_provenance(self):
        papers, capture, original = fixture()
        self.assertEqual(tem.attach_tem_public_answer_keys(papers, capture, original)["attached"], 266)
        once = deepcopy(papers)
        counts = tem.attach_tem_public_answer_keys(papers, capture, original)
        self.assertEqual(counts, {"duplicateOrMissingNumber": 30, "alreadyKnown": 266})
        self.assertEqual(papers, once)

    def test_pdf_or_url_mismatch_fails_without_mutation(self):
        for field, bad in (("sourcePdfSha256", "0" * 64),
                           ("sourceUrl", "https://zhenti.burningvocabulary.cn/tem4/2023")):
            with self.subTest(field=field):
                papers, capture, original = fixture()
                capture["papers"][0][field] = bad
                before = deepcopy(papers)
                with self.assertRaises(ValueError):
                    tem.attach_tem_public_answer_keys(papers, capture, original)
                self.assertEqual(papers, before)

    def test_changed_archived_pdf_fails_before_any_answer_mutation(self):
        papers, capture, original = fixture()
        before = deepcopy(papers)
        with TemporaryDirectory() as directory:
            destination = Path(directory)
            manifest_path = destination / "manifest.json"
            capture_path = destination / "capture.json"
            manifest_path.write_text(json.dumps(original), encoding="utf-8")
            capture_path.write_text(json.dumps(capture), encoding="utf-8")
            tampered = False
            for row in original["papers"]:
                if row["category"] not in {"tem4", "tem8"}:
                    continue
                pdf = destination / ".firecrawl" / row["category"] / f'{row["year"]}.pdf'
                pdf.parent.mkdir(parents=True, exist_ok=True)
                if not tampered:
                    pdf.write_bytes(b"changed PDF")
                    tampered = True
                else:
                    pdf.symlink_to(SOURCE.parent / ".firecrawl" /
                                   row["category"] / f'{row["year"]}.pdf')
            with self.assertRaisesRegex(ValueError, "archived source PDF changed"):
                tem.attach_from_private_capture(papers, capture_path, manifest_path)
        self.assertEqual(papers, before)

    def test_rejects_unprinted_choice_and_preserves_explicit_conflict(self):
        papers, capture, original = fixture()
        q1, q2 = papers["tem8:2025"]["questions"][:2]
        q1["answer"].update({"status": "explicit", "value": "B"})
        q2["options"] = [option for option in q2["options"] if option["label"] != "A."]
        counts = tem.attach_tem_public_answer_keys(papers, capture, original)
        self.assertEqual(counts["attached"], 264)
        self.assertEqual(counts["existingAnswerConflict"], 1)
        self.assertEqual(counts["printedOptionOrBankMismatch"], 1)
        self.assertEqual(q1["answer"]["value"], "B")
        self.assertEqual(q2["answer"]["status"], "missing")

    def test_rejects_duplicate_word_bank_letter_and_changed_worker(self):
        papers, capture, original = fixture()
        source = next(x for x in capture["papers"] if x["paperId"] == "tem4:2024")
        source["answers"][31] = "32-A"
        with self.assertRaisesRegex(ValueError, "duplicate TEM4 word-bank"):
            tem.attach_tem_public_answer_keys(papers, capture, original)
        papers, capture, original = fixture()
        capture["workerSha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "worker hash"):
            tem.attach_tem_public_answer_keys(papers, capture, original)

    @unittest.skipUnless(PRIVATE_CAPTURE.is_file(), "private TEM capture is not installed")
    def test_duplicate_numbers_attach_only_pdf_main_paper_choices(self):
        papers, _, original = fixture()
        capture = json.loads(PRIVATE_CAPTURE.read_text(encoding="utf-8"))
        counts = tem.attach_tem_public_answer_keys(papers, capture, original)
        self.assertEqual(counts["attached"], 266)
        expected = {2022: 7, 2023: 11, 2025: 8}
        for year, count in expected.items():
            with self.subTest(year=year):
                paper = papers[f"tem4:{year}"]
                main = [q for q in paper["questions"] if
                        q["answer"].get("externalSource", {}).get("sourceSet") ==
                        "main_paper_before_pdf_supplement"]
                self.assertEqual(len(main), count)
                self.assertTrue(all(q["questionType"] == "single_choice" and
                                    q["sourcePages"] in (["2"], ["3"])
                                    for q in main))
                supplement = [q for q in paper["questions"] if
                              q.get("recordType") == "question" and q.get("sourcePages") == ["10"]
                              and q.get("number") in {x["number"] for x in main}]
                self.assertEqual(len(supplement), count)
                self.assertTrue(all(q["answer"]["status"] == "missing" for q in supplement))

    def test_supplement_heading_or_page_change_keeps_duplicate_unknown(self):
        for expected_attached, mutate in (
            (259, lambda p: next(b for b in p["blocks"] if b["id"] == "b-10-1").update(text="changed")),
            (265, lambda p: next(q for q in p["questions"] if q["id"] == "q-11-1").update(sourcePages=["10"])),
        ):
            papers, capture, original = fixture()
            paper = papers["tem4:2022"]
            mutate(paper)
            counts = tem.attach_tem_public_answer_keys(papers, capture, original)
            self.assertEqual(counts["attached"], expected_attached)
            self.assertEqual(next(q for q in paper["questions"] if q["id"] == "q-11-1")
                             ["answer"]["status"], "missing")

    def test_node_fetcher_is_importable_without_network_and_validates_tokens(self):
        script = """
          const tem = require('./scripts/fetch_tem_answer_keys.cjs');
          const valid = Array.from({length: 50}, (_, i) => `${i + 1}-${i >= 30 && i < 40 ? 'ABCDEFGHIJ'[i - 30] : 'A'}`);
          if (tem.validatedAnswers('tem4', valid).length !== 50) process.exit(1);
          valid[31] = '32-A';
          try { tem.validatedAnswers('tem4', valid); process.exit(2); }
          catch (e) { if (!String(e.message).includes('distinct')) process.exit(3); }
          const fs = require('fs');
          const paper = JSON.parse(fs.readFileSync('./data/sources/exam-library/structured/papers/tem4/2022.json'));
          const matches = paper.questions.filter(q => q.recordType === 'question' && q.number === '11');
          if (tem.mainChoiceBeforeSupplement(paper, '11', matches)?.id !== 'q-11-1') process.exit(4);
          paper.blocks.find(b => b.id === 'b-10-1').text = 'different heading';
          if (tem.mainChoiceBeforeSupplement(paper, '11', matches) !== null) process.exit(5);
        """
        result = subprocess.run(["node", "-e", script], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
