import unittest
import json
from pathlib import Path
import tempfile

from triage_source_integrity import classify, classify_choice, text_match


def paper(document_id, question, blocks=()):
    return {
        "id": document_id,
        "category": document_id.split(":", 1)[0],
        "questions": [question],
        "blocks": list(blocks),
    }


def question(qid, number, source_blocks=()):
    return {
        "id": qid, "number": str(number), "sourceBlocks": list(source_blocks),
        "stem": "", "options": [],
    }


class TriageTests(unittest.TestCase):
    def test_answer_page_and_free_response_are_not_missing_choices(self):
        answer = paper("cs408:2013-complete", question("q-1-2", 1))
        self.assertEqual(classify_choice({"documentId": answer["id"], "questionIds": ["q-1-2"]}, answer)[0],
                         "confirmed_answer_page_misparsed")
        long_answer = paper("cs408:2013-complete", question("q-41-1", 41))
        self.assertEqual(classify_choice({"documentId": long_answer["id"], "questionIds": ["q-41-1"]}, long_answer)[0],
                         "confirmed_free_response_mistyped")

    def test_image_choice_and_original_duplicate_label_have_distinct_causes(self):
        diagram = paper("cs408:2017-questions", question("q-8-1", 8, ["b-1"]),
                        [{"id": "b-1", "role": "figure", "text": "四幅图"}])
        self.assertEqual(classify_choice({"documentId": diagram["id"], "questionIds": ["q-8-1"]}, diagram)[0],
                         "visual_options_present")
        printed = paper("cs408:2015-complete", question("q-1-1", 1))
        self.assertEqual(classify_choice({"documentId": printed["id"], "questionIds": ["q-1-1"]}, printed)[0],
                         "printed_original_duplicate_label")

    def test_unordered_comparison_handles_columns_and_chinese(self):
        self.assertEqual(text_match("A) apple I) ivory B) banana", "A. apple B. banana I. ivory", "cet6"), 1.0)
        self.assertEqual(text_match("建设中国特色社会主义法治体系", "本题建设中国特色社会主义法治体系是重点", "politics"), 1.0)

    def test_reviewed_fallback_is_reconciled_by_pdf_block_not_guesswork(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "docs").mkdir()
            (root / "paper.json").write_text(json.dumps({
                "category": "cet6", "questions": [],
                "blocks": [{"id": "b-1", "page": "1", "contentHtml": "<img src='crop.png'>"}],
            }))
            (root / "docs/fallback-visual-review-2026-09-28.json").write_text(json.dumps({"rows": [{
                "documentId": "cet6:test", "pages": [1], "pdfBlockIndex": 4,
                "visualConclusion": "preserved_in_fallback_image", "reviewId": 7,
            }]}))
            audit = {"catalogSha256": "sha", "documents": 1, "sourcePdfCount": 1,
                     "papers": [{"documentId": "cet6:test", "structured": "paper.json",
                                 "sourcePdf": "source.pdf", "sourcePdfPages": 1}],
                     "findings": [{"code": "possible_missing_paragraph", "documentId": "cet6:test",
                                   "pages": [1], "questionIds": [], "blockIds": [],
                                   "evidence": "PDF text block 4, shingle coverage 0%"}]}
            result = classify(audit, root=root)
            self.assertEqual(result["counts"], {"image_fallback_visually_present": 1})
            self.assertEqual(result["rows"][0]["visualReviewId"], 7)

    def test_pdf_reviewed_choice_gaps_are_classified_by_source_role(self):
        reference = paper("math3:1996-questions", question("q-3-5", 3, ["b-1"]),
                          [{"id": "b-1", "text": "同试卷 IV 第二、（3）题"}])
        self.assertEqual(classify_choice({"documentId": reference["id"], "questionIds": ["q-3-5"]}, reference)[0],
                         "printed_cross_reference_to_other_paper")
        directions = paper("kaoyan:2000-01", question("q-36-1", 36))
        self.assertEqual(classify_choice({"documentId": directions["id"], "questionIds": ["q-36-1"]}, directions)[0],
                         "non_choice_directions")
        duplicate = paper("politics:2005-questions", question("q-3-1", 3))
        self.assertEqual(classify_choice({"documentId": duplicate["id"], "questionIds": ["q-3-1"]}, duplicate)[0],
                         "printed_original_option_anomaly")


if __name__ == "__main__":
    unittest.main()
