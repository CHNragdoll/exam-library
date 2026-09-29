"""Printed answer appendices and inline keys stay behind the reveal boundary."""

from __future__ import annotations

from contextlib import closing
import unittest

from scripts.question_database_api import (
    DEFAULT_DATABASE, answer, connect, paper_questions, semantic_paper,
    semantic_paper_answers,
)


def descendants(node: dict):
    yield node
    for child in node["children"]:
        yield from descendants(child)


@unittest.skipUnless(DEFAULT_DATABASE.is_file(), "generated database unavailable")
class AnswerExposureBoundaryTests(unittest.TestCase):
    def test_politics_2022_inline_keys_hidden_until_reveal(self) -> None:
        with closing(connect()) as database:
            questions = paper_questions(database, "politics:2022-questions")["questions"]
            for question in questions:
                if question["number"].isdigit() and 1 <= int(question["number"]) <= 33:
                    with self.subTest(number=question["number"]):
                        self.assertFalse(any(block["text"].startswith("答案：")
                                             for block in question["contentBlocks"]))
                if question["number"] in {"34", "35", "36", "37", "38"}:
                    self.assertFalse(any("答题思路" in " ".join(
                        [block["text"], *block["paragraphs"],
                         *(part["text"] for part in block["styledParagraphs"])]
                    ) for block in question["contentBlocks"]),
                                     f"Q{question['number']} answer hint leaked")
            first = questions[0]
            self.assertEqual(answer(database, first["id"])["value"], "C")
            visible = semantic_paper(database, "politics:2022-questions")["root"]
            text = "\n".join(unit["text"] or "" for node in descendants(visible)
                             for unit in node["units"])
            self.assertFalse("答案：C" in text, "inline key leaked into semantic question view")
            self.assertFalse("答题思路:" in text, "printed answer hint leaked into semantic question view")
            self.assertIn("湖北", text)  # Q34 material remains available.
            mixed = next(unit for node in descendants(visible) for unit in node["units"]
                         if unit["provenance"]["sourceBlockId"] ==
                         "politics:2022-questions:b-10-1")
            self.assertIn("material-label", mixed["contentHtml"] or "")
            self.assertIn("material-source", mixed["contentHtml"] or "")
            self.assertNotIn("答题思路", mixed["contentHtml"] or "")
            original = semantic_paper_answers(database, "politics:2022-questions")["root"]
            original_text = "\n".join(unit["text"] or "" for node in descendants(original)
                                      for unit in node["units"])
            self.assertIn("答案：C", original_text)

    def test_cet6_embedded_answer_appendix_hidden_in_question_view(self) -> None:
        with closing(connect()) as database:
            for paper_id in ("cet6:2012-12-01", "cet6:2012-12-02", "cet6:2012-12-03",
                             "cet6:2012-06-01", "cet4:2015-06-01"):
                with self.subTest(paper=paper_id):
                    marker = "答案与详解" if paper_id.startswith("cet4:") else "参考答案"
                    visible = semantic_paper(database, paper_id)["root"]
                    visible_text = "\n".join(unit["text"] or ""
                                             for node in descendants(visible)
                                             for unit in node["units"])
                    self.assertFalse(marker in visible_text,
                                     "embedded answer appendix leaked into question view")
                    original = semantic_paper_answers(database, paper_id)["root"]
                    original_text = "\n".join(unit["text"] or ""
                                              for node in descendants(original)
                                              for unit in node["units"])
                    self.assertIn(marker, original_text)


if __name__ == "__main__":
    unittest.main()
