"""Regression checks for source-verified CET-6 split translation prompts."""

from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from scripts.pdf_verified_cet_bilingual_joins import (
    FIXTURES,
    ROOT,
    verified_bilingual_completion_joins,
)


RAW_DIR = ROOT / "data/sources/english-exams-reflow-latex/cet6/papers"
EXPECTED_TEXT = {
    "cet6:2012-06-01": {
        "b-19-7": (
            "84. As far as hobbies are concerned, Jane and her sister "
            "______________________ (几乎没有什么共同之处)."
        ),
        "b-19-9": (
            "85. Only after many failures______________________ "
            "(我才认识到仅凭运气是不能成功的)."
        ),
        "b-19-11": (
            "86. But for the survival instinct which nearly all creatures have, "
            "______________________ (更多的物种就可能已经在地球上灭绝了)."
        ),
    },
    "cet6:2012-12-02": {
        "b-14-27": (
            "83.Success in life does not depend so much on one's school "
            "records______________（而是靠其勤奋和坚持）."
        ),
        "b-15-2": (
            "85. In recent years, with his business booming, he "
            "_______________ （给慈善事业捐了大笔的钱）."
        ),
    },
}


def load_raw(paper_id: str) -> dict:
    basename = paper_id.split(":", 1)[1]
    return json.loads((RAW_DIR / f"{basename}.json").read_text(encoding="utf-8"))


class VerifiedBilingualCompletionJoinsTests(unittest.TestCase):
    def test_five_pdf_verified_joins_preserve_raw_source_and_chinese_cue(self):
        for paper_id, expected_joins in EXPECTED_TEXT.items():
            with self.subTest(paper_id=paper_id):
                raw = load_raw(paper_id)
                original = copy.deepcopy(raw)
                pdf_sha256 = FIXTURES[paper_id][0]
                joins = verified_bilingual_completion_joins(paper_id, pdf_sha256, raw)
                self.assertEqual(set(joins), set(expected_joins))
                self.assertEqual(raw, original)
                for from_id, expected_text in expected_joins.items():
                    joined = joins[from_id]
                    self.assertEqual(joined.joined_text, expected_text)
                    self.assertEqual(joined.original_pdf_sha256, pdf_sha256)
                    self.assertEqual(joined.source_block_ids[0], from_id)
                    start, end = joined.chinese_cue_span
                    self.assertEqual(joined.joined_text[start:end], joined.chinese_cue)
                    self.assertRegex(joined.chinese_cue, r"[\u3400-\u9fff]")

    def test_other_paper_has_no_fixture(self):
        self.assertEqual(verified_bilingual_completion_joins("cet6:2013-06-01", "", {}), {})

    def test_pdf_hash_mismatch_fails_closed(self):
        paper_id = "cet6:2012-06-01"
        with self.assertRaisesRegex(ValueError, "original PDF hash differs"):
            verified_bilingual_completion_joins(paper_id, "0" * 64, load_raw(paper_id))

    def test_pdf_file_mismatch_fails_closed(self):
        paper_id = "cet6:2012-06-01"
        with self.assertRaisesRegex(ValueError, "original PDF hash differs"):
            verified_bilingual_completion_joins(
                paper_id, FIXTURES[paper_id][0], load_raw(paper_id),
                pdf_dir=Path(__file__).parent,
            )

    def test_tampered_continuation_fails_closed(self):
        paper_id = "cet6:2012-12-02"
        raw = load_raw(paper_id)
        raw["pages"][13]["blocks"][27]["runs"][0]["text"] += "!"
        with self.assertRaisesRegex(ValueError, "split prompt text changed"):
            verified_bilingual_completion_joins(paper_id, FIXTURES[paper_id][0], raw)

    def test_changed_continuation_type_fails_closed(self):
        paper_id = "cet6:2012-12-02"
        raw = load_raw(paper_id)
        raw["pages"][14]["blocks"][2]["type"] = "question"
        with self.assertRaisesRegex(ValueError, "split prompt block types changed"):
            verified_bilingual_completion_joins(paper_id, FIXTURES[paper_id][0], raw)


if __name__ == "__main__":
    unittest.main()
