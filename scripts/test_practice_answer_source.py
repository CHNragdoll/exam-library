"""Source ownership and layout regressions for the practice answer API."""

from __future__ import annotations

from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest

from bs4 import BeautifulSoup

from scripts.build_question_database import build_database
from scripts.question_database_api import DEFAULT_DATABASE, answer, connect, paper_questions
from scripts.test_question_database import _make_fixture


class PracticeAnswerSourceTests(unittest.TestCase):
    @unittest.skipUnless(DEFAULT_DATABASE.is_file(), "generated corpus database unavailable")
    def test_politics_material_segments_keep_labels_sources_and_subquestions(self) -> None:
        with closing(connect()) as database:
            questions = paper_questions(database, "politics:2023-questions")["questions"]
            question = next(row for row in questions if row["number"] == "36")
            corrected = next(row for row in questions if row["number"] == "35")
        stem = question["stemParagraphs"]
        continuation = question["contentBlocks"][0]["styledParagraphs"]
        self.assertEqual([part["text"] for part in stem if part["kind"] == "material_label"],
                         ["材料1", "材料2"])
        self.assertEqual([part["text"] for part in continuation if part["kind"] == "material_label"],
                         ["材料3"])
        self.assertEqual(sum(part["kind"] == "material_source" for part in stem), 2)
        self.assertEqual(sum(part["kind"] == "material_source" for part in continuation), 1)
        self.assertEqual(sum("（1）结合当时的形势" in part["text"] for part in continuation), 1)
        self.assertEqual(sum("（2）团结奋斗" in part["text"] for part in continuation), 1)
        self.assertEqual([part["text"] for part in corrected["stemParagraphs"]
                          if part["kind"] == "material_label"], ["材料1", "材料2"])
        self.assertEqual(sum(part["kind"] == "material_source"
                             for part in corrected["stemParagraphs"]), 2)
        self.assertIn("二〇二〇", " ".join(part["text"]
                                      for part in corrected["stemParagraphs"]))

    def test_resolved_reference_only_source_keeps_resolved_solution(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            structured, database = _make_fixture(Path(folder))
            build_database(structured, database)
            with closing(sqlite3.connect(database)) as writer:
                writer.execute(
                    """UPDATE source_blocks SET role = 'question', status = NULL,
                       text = '一、【同试卷 IV 第一题】',
                       content_html = '<div class="paragraph">一、【同试卷 IV 第一题】</div>'
                       WHERE id = 'test:2025:b-1-2'"""
                )
                writer.execute(
                    """UPDATE answers SET source_document_id = 'test:2025',
                       source_question_ids_json = '["q-1-1"]',
                       source_blocks_json = '["b-1-2"]',
                       solution = '解析得到 \\(\\displaystyle x=2\\) 。'
                       WHERE question_id = 'test:2025:q-1-1'"""
                )
                writer.execute(
                    """INSERT INTO answer_references
                       (id,question_id,source_field,ordinal,literal_text,target_year,
                        target_form,target_section,target_number,target_question_id,
                        status,ambiguity_reason,source_json_path)
                       VALUES ('test:2025:ref','test:2025:q-1-1','solution',1,
                               '【同试卷 IV 第一题】',2025,'IV','一','1',
                               'test:2025:q-2-1','resolved',NULL,'$.questions[0].answer')"""
                )
                writer.commit()
                with closing(connect(database)) as reader:
                    result = answer(reader, "test:2025:q-1-1")
                writer.execute(
                    "UPDATE answer_references SET status='unresolved',target_question_id=NULL WHERE id='test:2025:ref'"
                )
                writer.commit()
                with closing(connect(database)) as reader:
                    unresolved = answer(reader, "test:2025:q-1-1")
            self.assertEqual(len(result["sourceContentBlocks"]), 1)
            self.assertTrue(result["resolvedReferenceOnly"])
            self.assertIn("x=2", result["solution"])
            self.assertFalse(unresolved["resolvedReferenceOnly"])

    def test_duplicate_source_block_keeps_only_canonical_copy(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            structured, database = _make_fixture(Path(folder))
            build_database(structured, database)
            with closing(sqlite3.connect(database)) as writer:
                writer.execute(
                    """UPDATE source_blocks SET status = NULL,
                       raw_json = '{"duplicateOf":"b-1-1"}'
                       WHERE id = 'test:2025:b-1-2'"""
                )
                writer.execute(
                    """UPDATE answers SET source_document_id = 'test:2025',
                       source_question_ids_json = '["q-1-1"]',
                       source_blocks_json = '["b-1-1","b-1-2"]'
                       WHERE question_id = 'test:2025:q-1-1'"""
                )
                writer.commit()
                with closing(connect(database)) as reader:
                    result = answer(reader, "test:2025:q-1-1")
                writer.execute(
                    """UPDATE answers SET source_blocks_json = '["b-1-2"]'
                       WHERE question_id = 'test:2025:q-1-1'"""
                )
                writer.commit()
                with closing(connect(database)) as reader:
                    orphan = answer(reader, "test:2025:q-1-1")
            self.assertEqual([block["id"] for block in result["sourceContentBlocks"]],
                             ["test:2025:b-1-1"])
            self.assertEqual(orphan["sourceContentBlocks"], [])
            self.assertEqual(orphan["value"], "B")

    def test_foreign_answer_tail_is_removed_without_cutting_prose(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            structured, database = _make_fixture(Path(folder))
            build_database(structured, database)
            with closing(sqlite3.connect(database)) as writer:
                writer.execute(
                    """UPDATE source_blocks SET role = 'content', status = NULL,
                       text = '15号通知不影响本题。A正确。*2.【答案】C',
                       content_html = '<p class="paragraph">15号通知不影响本题。A正确。*2.【答案】C</p>'
                       WHERE id = 'test:2025:b-1-2'"""
                )
                writer.execute(
                    """UPDATE answers SET source_document_id = 'test:2025',
                       source_question_ids_json = '["q-1-1"]',
                       source_blocks_json = '["b-1-2"]'
                       WHERE question_id = 'test:2025:q-1-1'"""
                )
                writer.commit()
                with closing(connect(database)) as reader:
                    result = answer(reader, "test:2025:q-1-1")
                self.assertEqual(result["sourceContentBlocks"][0]["text"],
                                 '15号通知不影响本题。A正确。')
                self.assertEqual(result["sourceContentBlocks"][0]["contentHtml"],
                                 '<p class="paragraph">15号通知不影响本题。A正确。</p>')

                writer.execute(
                    """UPDATE source_blocks SET
                       text = 'A正确。*2.【答案】C 后面仍有文字',
                       content_html = '<p>A正确。*2.【答案】C 后面仍有文字</p>'
                       WHERE id = 'test:2025:b-1-2'"""
                )
                writer.commit()
                with closing(connect(database)) as reader:
                    ambiguous = answer(reader, "test:2025:q-1-1")
                writer.execute(
                    """UPDATE source_blocks SET
                       text = 'A正确。2.【答案】C',
                       content_html = '<p>A正确。2.【答案】C</p>'
                       WHERE id = 'test:2025:b-1-2'"""
                )
                writer.commit()
                with closing(connect(database)) as reader:
                    unstarred = answer(reader, "test:2025:q-1-1")
            self.assertEqual(ambiguous["sourceContentBlocks"], [],
                             "an embedded boundary must fall back instead of dropping later prose")
            self.assertEqual(ambiguous["value"], "B")
            self.assertEqual(unstarred["sourceContentBlocks"], [],
                             "an unmarked boundary is not safe to trim")

    def test_empty_block_answer_record_does_not_claim_another_answers_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            structured, database = _make_fixture(Path(folder))
            build_database(structured, database)
            with closing(sqlite3.connect(database)) as writer:
                writer.execute(
                    """UPDATE source_blocks SET role = 'heading', status = NULL,
                       content_html = '<h2>【答案】B</h2>'
                       WHERE id = 'test:2025:b-1-2'"""
                )
                writer.execute(
                    """UPDATE answers SET source_document_id = 'test:2025',
                       source_question_ids_json = '["q-1-1"]',
                       source_blocks_json = '["b-1-2"]'
                       WHERE question_id = 'test:2025:q-1-1'"""
                )
                writer.execute(
                    """UPDATE answers SET source_document_id = 'test:2025',
                       source_question_ids_json = '["q-1-1"]',
                       source_blocks_json = '[]'
                       WHERE question_id = 'test:2025:q-2-1'"""
                )
                writer.commit()
            with closing(connect(database)) as reader:
                result = answer(reader, "test:2025:q-1-1")
            self.assertEqual([block["id"] for block in result["sourceContentBlocks"]],
                             ["test:2025:b-1-2"])

    def test_question_and_choices_mixed_with_solution_fall_back(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            structured, database = _make_fixture(Path(folder))
            build_database(structured, database)
            with closing(sqlite3.connect(database)) as writer:
                writer.execute(
                    """UPDATE source_blocks SET role = 'choices', status = NULL,
                       content_html = '<div class="source-choice-block">'
                       || '<p>题干续句</p><div class="choices">'
                       || '<div class="choice">A. 错误</div></div>'
                       || '<p>解答：B。解析正文。</p></div>'
                       WHERE id = 'test:2025:b-1-2'"""
                )
                writer.execute(
                    """UPDATE answers SET source_document_id = 'test:2025',
                       source_question_ids_json = '["q-1-1"]',
                       source_blocks_json = '["b-1-2"]'
                       WHERE question_id = 'test:2025:q-1-1'"""
                )
                writer.commit()
            with closing(connect(database)) as reader:
                result = answer(reader, "test:2025:q-1-1")
            self.assertEqual(result["sourceContentBlocks"], [])
            self.assertIsNone(result["sourceBaseUrl"])
            self.assertEqual(result["value"], "B")

    def test_shared_answer_blocks_are_excluded_from_one_question(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            structured, database = _make_fixture(Path(folder))
            build_database(structured, database)
            with closing(sqlite3.connect(database)) as writer:
                writer.execute(
                    """UPDATE source_blocks SET role = 'heading', status = NULL,
                       text = '【答案】', content_html = '<h2>【答案】</h2>'
                       WHERE id = 'test:2025:b-1-2'"""
                )
                writer.execute(
                    """UPDATE answers SET source_document_id = 'test:2025',
                       source_question_ids_json = '["q-1-1"]',
                       source_blocks_json = '["b-1-1","b-1-2"]'
                       WHERE question_id = 'test:2025:q-1-1'"""
                )
                writer.execute(
                    """UPDATE answers SET source_document_id = 'test:2025',
                       source_question_ids_json = '["q-2-1"]',
                       source_blocks_json = '["b-1-1"]'
                       WHERE question_id = 'test:2025:q-2-1'"""
                )
                writer.commit()
            with closing(connect(database)) as reader:
                first = answer(reader, "test:2025:q-1-1")
                second = answer(reader, "test:2025:q-2-1")
            self.assertEqual([block["id"] for block in first["sourceContentBlocks"]],
                             ["test:2025:b-1-2"])
            self.assertEqual(first["sourceBaseUrl"], "/exam-library/structured/papers/test/2025.htm")
            self.assertEqual(second["sourceContentBlocks"], [])
            self.assertIsNone(second["sourceBaseUrl"])
            self.assertEqual(second["value"], "AC", "structured fallback remains intact")

    @unittest.skipUnless(DEFAULT_DATABASE.is_file(), "generated corpus database unavailable")
    def test_generated_politics_cs408_and_math_answers_keep_source_layout(self) -> None:
        with closing(connect()) as database:
            politics = answer(database, "politics:2023-questions:q-37-1")
            politics_2021 = answer(database, "politics:2021-questions:q-1-1")
            politics_tails = {number: answer(database, f"politics:2023-questions:q-{number}-1")
                              for number in (14, 15, 31)}
            cs408 = answer(database, "cs408:2017-questions:q-46-1")
            cs408_2023 = answer(database, "cs408:2023-questions:q-1-1")
            cs408_2024 = {number: answer(database, f"cs408:2024-questions:q-{number}-1")
                           for number in (41, 42, 43)}
            cs408_image = answer(database, "cs408:2009-complete:q-41-1")
            mixed_cs408 = answer(database, "cs408:2011-complete:q-31-1")
            math = answer(database, "math3:2019-questions:q-20-1")
            math_references = [answer(database, question_id) for question_id in (
                "math3:1993-questions:q-3-6", "math3:1994-questions:q-10-2",
                "math3:1995-questions:q-6-2", "math3:1996-questions:q-6-2")]
            shared_math = answer(database, "math3:2019-questions:q-1-1")

        self.assertEqual([block["role"] for block in politics["sourceContentBlocks"]],
                         ["question", "content", "content", "heading", "content",
                          "heading", "content", "heading", "content"])
        self.assertIn("【答案】", politics["sourceContentBlocks"][0]["contentHtml"])
        self.assertIn("【考点点拨】", politics["sourceContentBlocks"][3]["contentHtml"])
        self.assertIn("【试题简析】", politics["sourceContentBlocks"][5]["contentHtml"])
        self.assertIn("【名师点拨】", politics["sourceContentBlocks"][7]["contentHtml"])
        self.assertEqual(len(politics_2021["sourceContentBlocks"]), 5)
        self.assertIn("【答案】", politics_2021["sourceContentBlocks"][0]["contentHtml"])
        self.assertIn("【考点点拨】", politics_2021["sourceContentBlocks"][1]["contentHtml"])
        self.assertIn("【试题解析】", politics_2021["sourceContentBlocks"][3]["contentHtml"])
        for number, expected_count, last_sentence, foreign in (
            (14, 7, "A正确。", "*15.【答案】B"),
            (15, 6, "A、C、D错误。", "*16.【答案】D"),
            (31, 7, "A、C正确，B错误。", "*32.【答案】ABCD"),
        ):
            blocks = politics_tails[number]["sourceContentBlocks"]
            self.assertEqual(len(blocks), expected_count)
            self.assertTrue(blocks[-1]["text"].endswith(last_sentence))
            self.assertNotIn(foreign, "".join(block["contentHtml"] for block in blocks))
            self.assertNotIn(foreign, "".join(block["text"] for block in blocks))
        self.assertIn("<pre class=\"code\">", cs408["sourceContentBlocks"][2]["contentHtml"])
        self.assertIn("<table>", cs408["sourceContentBlocks"][4]["contentHtml"])
        self.assertEqual([block["id"] for block in cs408_2023["sourceContentBlocks"]],
                         ["cs408:2023-answers:b-1-4"],
                         "the shared 1–40 answer table must not appear under question 1")
        self.assertIn("【参考答案】D", cs408_2023["sourceContentBlocks"][0]["contentHtml"])
        self.assertEqual([block["id"].split(":")[-1] for block in
                          cs408_2024[41]["sourceContentBlocks"]],
                         ["b-1-5", "b-2-1", "b-3-1"])
        q41_html = BeautifulSoup("".join(block["contentHtml"] for block in
                                       cs408_2024[41]["sourceContentBlocks"]), "html.parser")
        self.assertEqual(len(q41_html.select("pre.code")), 2,
                         "the two distinct code continuations appear once each")
        self.assertEqual([block["id"].split(":")[-1] for block in
                          cs408_2024[42]["sourceContentBlocks"]],
                         ["b-3-2", "b-3-3", "b-3-4"])
        q42_html = BeautifulSoup("".join(block["contentHtml"] for block in
                                       cs408_2024[42]["sourceContentBlocks"]), "html.parser")
        self.assertEqual(len(q42_html.select("table")), 1)
        self.assertEqual(sum(r"\alpha=7/11" in node.get("data-tex", "") for node in
                             q42_html.select(".formula[data-tex]")), 1)
        self.assertEqual([block["id"].split(":")[-1] for block in
                          cs408_2024[43]["sourceContentBlocks"]],
                         ["b-3-5", "b-5-1"])
        q43_html = BeautifulSoup("".join(block["contentHtml"] for block in
                                       cs408_2024[43]["sourceContentBlocks"]), "html.parser")
        self.assertEqual(sum("2^5=32" in node.get("data-tex", "") for node in
                             q43_html.select(".formula[data-tex]")), 1)
        self.assertEqual(cs408_image["sourceBaseUrl"],
                         "/exam-library/structured/papers/cs408/2009-complete.htm")
        self.assertIn("../../../../cs408-latex-2009-2017/assets/figures/2009-complete-p007-b009.svg",
                      cs408_image["sourceContentBlocks"][1]["contentHtml"])
        self.assertEqual(mixed_cs408["sourceContentBlocks"], [],
                         "a mixed question/choice/solution block is not an answer-only excerpt")
        self.assertEqual(mixed_cs408["value"], "B")
        self.assertIn("\\(", math["sourceContentBlocks"][0]["contentHtml"])
        self.assertFalse(math["resolvedReferenceOnly"])
        for reference in math_references:
            self.assertTrue(reference["resolvedReferenceOnly"])
            self.assertEqual(len(reference["sourceContentBlocks"]), 1)
            self.assertIn("同试卷", reference["sourceContentBlocks"][0]["text"])
            self.assertTrue(reference["solution"])
        self.assertEqual(shared_math["sourceContentBlocks"], [],
                         "Math III Q1 must not expose the eight-question answer key")
        self.assertEqual(shared_math["value"], "C")


if __name__ == "__main__":
    unittest.main()
