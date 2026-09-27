import unittest

from audit_source_integrity import check_numbering, check_paper, paragraph_coverage


def question(number, *, qid=None, options=None):
    return {
        "id": qid or f"q-{number}", "number": str(number),
        "recordType": "question", "sectionKind": "single_choice",
        "questionType": "single_choice", "sourcePages": ["2"],
        "sourceBlocks": [f"b-{number}"], "options": options or [],
        "answer": {"status": "missing", "sourceDocumentId": None},
    }


class SourceIntegrityTests(unittest.TestCase):
    def test_category_aware_number_gap_and_duplicate(self):
        rows = [question(n) for n in (1, 2, 4, 5, 5, 6)]
        rows[4]["id"] = "q-5-copy"
        politics = {"category": "politics", "questions": rows}
        codes = [item["code"] for item in check_numbering(politics)]
        self.assertIn("duplicate_question_number", codes)
        self.assertIn("missing_question_number", codes)
        english = {"category": "cet4", "questions": rows}
        self.assertNotIn("missing_question_number", [item["code"] for item in check_numbering(english)])

    def test_incomplete_choice_and_unassigned_numbered_source_block(self):
        paper = {
            "category": "cs408", "kind": "questions", "questions": [question(1)],
            "blocks": [{"id": "b-2", "page": "2", "role": "content",
                        "status": "source_only", "text": "2. Which option is correct?"}],
        }
        findings = check_paper(paper, {"cs408:sample"})
        self.assertEqual({item["code"] for item in findings},
                         {"incomplete_choices", "unassigned_numbered_block"})
        self.assertEqual(findings[-1]["blockIds"], ["b-2"])

    def test_paragraph_coverage_normalizes_punctuation(self):
        source = "A source paragraph with enough material to be checked. " * 3
        self.assertGreater(paragraph_coverage(source, source.upper()), 0.9)
        self.assertLess(paragraph_coverage(source, "unrelated text"), 0.1)

    def test_kaoyan_matching_candidates_exclude_printed_example_letters(self):
        row = question(41, options=[{"label": f"{letter}."} for letter in "BDEFG"])
        row["context"] = {"kind": "ordering_diagram", "fixedLetters": ["A", "C", "H"]}
        paper = {"category": "kaoyan", "kind": "questions", "questions": [row], "blocks": []}
        self.assertNotIn("incomplete_choices", {item["code"] for item in check_paper(paper, set())})
        row["options"] = row["options"][:-1]
        self.assertIn("incomplete_choices", {item["code"] for item in check_paper(paper, set())})

    def test_missing_subquestions_and_typo_are_review_candidates(self):
        row = question(41)
        row["questionType"] = "free_response"
        row["stem"] = "原理，，请说明"
        paper = {
            "category": "politics", "kind": "questions", "questions": [row],
            "blocks": [{"id": "b-41", "page": "2", "role": "content",
                        "text": "（1）说明原理。\n（2）结合材料。"}],
        }
        codes = {item["code"] for item in check_paper(paper, {"politics:sample"})}
        self.assertIn("possible_missing_subquestions", codes)
        self.assertIn("suspect_typo", codes)


if __name__ == "__main__":
    unittest.main()
