"""Guard answer-key alignment across paper, question, and printed choices."""

from copy import deepcopy
import json
import unittest

from scripts import build_structured_exams as builder
from scripts import build_question_database as database_builder


class PublicEnglishAnswerKeysTests(unittest.TestCase):
    def test_real_papers_and_alignment_guards(self):
        papers = {}
        for paper_id in ("kaoyan:2026-01", "cet4:2025-12-01", "cet6:2025-12-01"):
            category, stem = paper_id.split(":")
            path = builder.OUT / "papers" / category / f"{stem}.json"
            papers[paper_id] = json.loads(path.read_text(encoding="utf-8"))
        original = deepcopy(papers)
        # Wrong printed option letters must not receive an answer, even when
        # the year/variant and question number happen to match.
        cet4 = papers["cet4:2025-12-01"]
        q2 = next(q for q in cet4["questions"] if q["number"] == "2")
        q2["options"] = [option for option in q2["options"] if option["label"] != "A."]
        counts = builder.attach_public_english_answer_keys(papers)
        self.assertEqual(counts["optionMismatch"], 1)

        kaoyan = {q["number"]: q for q in papers["kaoyan:2026-01"]["questions"]}
        self.assertEqual("".join(kaoyan[str(n)]["answer"]["value"] for n in range(1, 21)),
                         "ADBCBCADADDDCABCCBBA")
        self.assertEqual(kaoyan["46"]["answer"]["status"], "missing")
        self.assertTrue(kaoyan["1"]["answer"]["externalSource"]["url"].endswith("/kaoyan/2026/01"))
        first = kaoyan["1"]
        self.assertEqual(database_builder._choice_letters(
            first, [option["label"].rstrip(".") for option in first["options"]]), {"A"})
        unrelated_partial = deepcopy(first)
        unrelated_partial["context"] = None
        self.assertIsNone(database_builder._choice_letters(
            unrelated_partial, [option["label"].rstrip(".") for option in unrelated_partial["options"]]))

        for paper_id in ("cet4:2025-12-01", "cet6:2025-12-01"):
            questions = {q["number"]: q for q in papers[paper_id]["questions"]}
            self.assertEqual(questions["1"]["answer"]["status"], "explicit")
            self.assertEqual(questions["26"]["answer"]["status"], "explicit")
            self.assertEqual(questions["36"]["answer"]["status"], "explicit")
        self.assertEqual(q2["answer"], next(q["answer"] for q in original["cet4:2025-12-01"]["questions"]
                                              if q["number"] == "2"))

    def test_shared_matching_bank_rejects_unprinted_letters(self):
        papers = {}
        for paper_id in ("cet6:2025-12-03", "cet6:2016-12-02", "cet4:2023-12-02"):
            category, stem = paper_id.split(":")
            paper = json.loads((builder.OUT / "papers" / category / f"{stem}.json").read_text(encoding="utf-8"))
            papers[paper_id] = paper
            for question in paper["questions"]:
                if question["number"] in {"36", "38", "40", "44"}:
                    question["answer"] = {"value": None, "status": "missing"}
        counts = builder.attach_public_english_answer_keys(papers)
        invalid = {q["number"]: q for q in papers["cet6:2025-12-03"]["questions"]}
        self.assertEqual(invalid["36"]["answer"]["status"], "missing")
        self.assertEqual(invalid["40"]["answer"]["status"], "missing")
        self.assertGreaterEqual(counts["sharedBankMismatch"], 2)
        extended = {q["number"]: q for q in papers["cet6:2016-12-02"]["questions"]}
        self.assertEqual(extended["44"]["answer"]["value"], "Q")
        extended_cet4 = {q["number"]: q for q in papers["cet4:2023-12-02"]["questions"]}
        self.assertEqual(extended_cet4["38"]["answer"]["value"], "P")


if __name__ == "__main__":
    unittest.main()
