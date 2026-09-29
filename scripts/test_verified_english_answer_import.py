"""Read-only adapter checks for privately verified CET answer evidence."""

import copy
import json
import unittest
from pathlib import Path

from scripts.build_english_paragraph_manifest import (
    listening_dictation_blocks,
    verified_dictation_words,
)
from scripts.verified_english_answer_import import (
    attach_verified_word_bank_answers,
    dictation_manifest_evidence,
    word_bank_attachment_plan,
)
from scripts.verify_english_answer_evidence import DEFAULT_EVIDENCE, ROOT


@unittest.skipUnless(DEFAULT_EVIDENCE.is_file(), "private evidence file is unavailable")
class VerifiedEnglishAnswerImportTests(unittest.TestCase):
    @staticmethod
    def word_bank_papers():
        papers = {}
        for slug in ("2014-06-01", "2014-06-02", "2014-06-03",
                     "2016-06-01", "2016-06-02", "2016-06-03",
                     "2016-12-01", "2016-12-02", "2016-12-03"):
            paper_id = f"cet4:{slug}"
            path = ROOT / f"data/sources/exam-library/structured/papers/cet4/{slug}.json"
            paper = json.loads(path.read_text())
            for question in paper["questions"]:
                if (question.get("recordType") == "question" and
                        (question.get("context") or {}).get("kind") == "word_bank_cloze" and
                        question.get("number") in {str(n) for n in range(26, 46)}):
                    question["answer"]["value"] = None
                    question["answer"]["status"] = "missing"
            papers[paper_id] = paper
        return papers

    def test_dictation_adapter_uses_exact_cited_source_location_and_builder_accepts_all_six(self):
        original = json.loads(DEFAULT_EVIDENCE.read_text())
        converted = dictation_manifest_evidence()
        self.assertEqual(converted["schema"], "verified-listening-dictation.v1")
        self.assertEqual(len(converted["papers"]), 6)
        for paper_id, entry in converted["papers"].items():
            with self.subTest(paper_id=paper_id):
                cited = original["listeningDictation"][paper_id]
                self.assertEqual(entry["sourcePage"], cited["sourceLocation"])
                self.assertEqual(entry["originalPdfSha256"], cited["originalPdfSha256"])
                category, slug = paper_id.split(":")
                source = ROOT / f"data/sources/english-exams-reflow-latex/{category}/papers/{slug}.json"
                blocks = listening_dictation_blocks(json.loads(source.read_text()))
                self.assertEqual(set(verified_dictation_words(blocks, entry) or ()),
                                 {str(number) for number in range(26, 36)})

    def test_word_bank_attaches_ninety_local_choice_letters_in_memory(self):
        papers = self.word_bank_papers()
        before = copy.deepcopy(papers)
        self.assertEqual(len(word_bank_attachment_plan(papers)), 90)
        self.assertEqual(papers, before, "planning must not mutate the papers")
        self.assertEqual(attach_verified_word_bank_answers(papers), 90)
        evidence = json.loads(DEFAULT_EVIDENCE.read_text())["wordBank"]
        for paper_id, entry in evidence.items():
            matched = [q for q in papers[paper_id]["questions"]
                       if q.get("recordType") == "question" and q.get("number") in entry["answers"]
                       and (q.get("context") or {}).get("kind") == "word_bank_cloze"]
            self.assertEqual(len(matched), 10)
            for question in matched:
                expected = entry["answers"][question["number"]]
                self.assertEqual(question["answer"]["value"], expected["letter"])
                self.assertEqual(question["answer"]["externalSource"]["word"], expected["word"])
        self.assertEqual(attach_verified_word_bank_answers(papers), 0, "repeat attach should be idempotent")

    def test_selected_paper_attach_keeps_full_corpus_requirement_explicit(self):
        paper_id = "cet4:2016-06-01"
        selected = {paper_id: self.word_bank_papers()[paper_id]}
        before = copy.deepcopy(selected)
        with self.assertRaisesRegex(ValueError, "target paper missing"):
            word_bank_attachment_plan(selected)
        self.assertEqual(selected, before)
        self.assertEqual(len(word_bank_attachment_plan(selected, require_all=False)), 10)
        self.assertEqual(attach_verified_word_bank_answers(selected, require_all=False), 10)
        linked = [q for q in selected[paper_id]["questions"]
                  if q.get("recordType") == "question" and q.get("number") in
                  {str(number) for number in range(26, 36)}]
        self.assertEqual(len(linked), 10)
        self.assertTrue(all(q["answer"]["status"] == "explicit" for q in linked))

    def test_conflict_fails_without_partial_attachment(self):
        papers = self.word_bank_papers()
        target = next(q for q in papers["cet4:2016-12-03"]["questions"]
                      if q.get("number") == "35" and (q.get("context") or {}).get("kind") == "word_bank_cloze")
        target["answer"]["value"] = "A"
        target["answer"]["status"] = "explicit"
        before = copy.deepcopy(papers)
        with self.assertRaisesRegex(ValueError, "existing answer conflicts"):
            attach_verified_word_bank_answers(papers)
        self.assertEqual(papers, before)


if __name__ == "__main__":
    unittest.main()
