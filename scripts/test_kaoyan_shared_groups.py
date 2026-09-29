"""Printed English group labels and cloze instruction boundaries."""

from __future__ import annotations

from contextlib import closing
import json
from pathlib import Path
import unittest

from scripts.build_structured_exams import assign_kaoyan_group_labels, kaoyan_cloze_context
from scripts.question_database_api import DEFAULT_DATABASE, connect, paper_questions, semantic_paper


PAPERS = Path(__file__).resolve().parents[1] / "data/sources/exam-library/structured/papers/kaoyan"


def paper(name: str) -> dict:
    return json.loads((PAPERS / f"{name}.json").read_text(encoding="utf-8"))


class KaoyanSharedGroupsTests(unittest.TestCase):
    def test_cloze_boundary_and_labels_derive_from_printed_sections(self) -> None:
        for name in ("2000-01", "2019-01", "2026-01", "2026-02"):
            with self.subTest(paper=name):
                document = paper(name)
                first = next(question for question in document["questions"]
                             if question.get("context") and
                             question["context"].get("kind") == "passage")
                blocks = {block["id"]: block for block in document["blocks"]}
                source = [blocks[block_id] for block_id in first["context"]["sourceBlocks"]]
                split = kaoyan_cloze_context(source, first["number"])
                self.assertEqual(split["instructionSourceBlocks"], [source[0]["id"]])
                self.assertEqual(split["passageSourceBlocks"],
                                 [block["id"] for block in source[1:]])
                self.assertTrue(split["instructionText"].startswith((
                    "Read the following text", "For each numbered blank")))
                self.assertEqual(split["text"].split("\n\n", 1)[0], source[1]["text"])
                assign_kaoyan_group_labels(document["id"], document["questions"], document["toc"])
                self.assertEqual(first["labels"][0]["kind"], "cloze")
                if name == "2026-02":
                    translated = next(question for question in document["questions"]
                                      if question["number"] == "46")
                    self.assertEqual(translated["labels"][0]["kind"], "translation")

    @unittest.skipUnless(DEFAULT_DATABASE.is_file(), "generated database unavailable")
    def test_rebuilt_api_and_sql_group_queries(self) -> None:
        with closing(connect()) as database:
            questions = paper_questions(database, "kaoyan:2026-01")["questions"]
            by_number = {question["number"]: question for question in questions}
            cloze = [by_number[str(number)] for number in range(1, 21)]
            self.assertEqual({question["labels"][0]["id"] for question in cloze},
                             {"kaoyan:2026-01:group:b-1-2"})
            context = cloze[0]["context"]
            self.assertIn("Read the following text", context["instructionText"])
            self.assertNotIn("Read the following text", context["text"])
            self.assertTrue(context["text"].startswith("Advances in artificial intelligence"))
            self.assertEqual(context["instructionSourceBlocks"], ["b-1-4"])
            self.assertEqual(context["passageSourceBlocks"][0], "b-1-5")
            self.assertEqual(by_number["21"]["labels"], by_number["25"]["labels"])
            self.assertNotEqual(by_number["21"]["labels"], by_number["26"]["labels"])
            self.assertEqual(by_number["21"]["labels"][0]["kind"], "reading")
            english_two = paper_questions(database, "kaoyan:2026-02")["questions"]
            self.assertEqual(next(question for question in english_two
                                  if question["number"] == "46")["labels"][0]["kind"],
                             "translation")
            self.assertEqual(database.execute(
                """SELECT COUNT(*) FROM question_labels ql JOIN labels l ON l.id=ql.label_id
                    WHERE l.id='kaoyan:2026-01:group:b-1-2'"""
            ).fetchone()[0], 20)
            tree = semantic_paper(database, "kaoyan:2026-01")["root"]
            def descendants(node):
                yield node
                for child in node["children"]:
                    yield from descendants(child)
            passage = next(node for node in descendants(tree) if node["type"] == "passage")
            units = passage["units"]
            self.assertEqual(units[0]["type"], "instruction")
            self.assertEqual(units[0]["provenance"]["sourceBlockId"], "kaoyan:2026-01:b-1-4")
            self.assertEqual(units[1]["type"], "paragraph")
            self.assertEqual(units[1]["provenance"]["sourceBlockId"], "kaoyan:2026-01:b-1-5")
            first_node = next(node for node in descendants(tree)
                              if node["questionId"] == cloze[0]["id"])
            self.assertEqual(first_node["labels"], cloze[0]["labels"])


if __name__ == "__main__":
    unittest.main()
