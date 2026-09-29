"""Regression tests for the source-preserving SQLite question bank build."""

from __future__ import annotations

from collections import Counter
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from scripts.build_question_database import build_database
from scripts import question_database_api


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def _answer(value: str | None, status: str) -> dict:
    return {
        "value": value, "solution": None, "explanation": None,
        "commentary": None, "knowledge": None, "sourceDocumentId": None,
        "sourceQuestionIds": [], "sourceBlocks": [], "sourcePages": [],
        "status": status,
    }


def _question(number: int, kind: str, options: list[dict], value: str | None,
              status: str) -> dict:
    return {
        "id": f"q-{number}-1", "number": str(number), "sectionKind": "test",
        "sectionTitle": "Part I", "recordType": "question",
        "sourceBlocks": ["b-1-1"], "sourcePages": ["1"],
        "stem": f"Question {number}", "options": options,
        "answer": _answer(value, status), "status": "complete",
        "context": {"kind": "passage", "blankNumber": str(number),
                    "text": "Shared context", "sourceBlocks": ["b-1-2"],
                    "sourcePages": ["1"]},
        "questionType": kind,
    }


def _make_fixture(root: Path) -> tuple[Path, Path]:
    structured = root / "structured"
    output = root / "question-bank.sqlite3"
    options = [
        {"label": f"{letter}.", "sourceLabel": f"({letter})", "text": letter,
         "sourceOrder": 4 - index}
        for index, letter in enumerate("ABCD")
    ]
    questions = [
        _question(1, "single_choice", options, "B", "explicit"),
        _question(2, "multiple_choice", options, "AC", "explicit"),
        _question(3, "single_choice", options, None, "missing"),
        _question(4, "single_choice", options, "B", "ambiguous"),
        _question(5, "single_choice", options[:3], "B", "explicit"),
    ]
    # OCR can merge one option into its neighbor while still leaving a valid
    # answer letter. That incomplete question must never be scored.
    questions[-1]["status"] = "partial"
    questions.extend(_question(number, "fill_blank", [], str(number), "explicit")
                     for number in range(6, 11))
    questions.append(_question(11, "multiple_choice", [
        {"label": f"{letter}.", "sourceLabel": f"({letter})", "text": letter,
         "sourceOrder": index}
        for index, letter in enumerate("ABCDE", 1)
    ], "ACE", "explicit"))
    block = lambda local_id, status=None: {
        "id": local_id, "page": "1", "sourcePageIndex": 1,
        "sourceBlockIndex": int(local_id[-1]), "role": "content", "text": local_id,
        "contentHtml": f"<p>{local_id}</p>", "formulas": ["x^2"],
        "images": ["figure.png"], **({"status": status} if status else {}),
    }
    paper = {
        "schema": "exam-paper.v1", "id": "test:2025", "title": "Test paper",
        "category": "test", "categoryLabel": "Test", "kind": "questions",
        "year": 2025, "template": "test", "source": {
            "original": "original.htm", "reflow": "reflow.htm"},
        "pages": 1, "blocks": [block("b-1-1"), block("b-1-2", "source_only")],
        "questions": questions, "toc": [], "audit": {},
    }
    document = {
        "id": paper["id"], "category": paper["category"], "kind": paper["kind"],
        "title": paper["title"], "template": paper["template"],
        "json": "papers/test/2025.json", "reader": "papers/test/2025.htm",
        "questions": len(questions), "partialQuestions": 1,
        "sourceBlocks": 2, "sourceOnlyBlocks": 1,
    }
    audit = {
        "schema": "exam-paper.v1", "papers": 1, "categories": {"test": 1},
        "questionRecords": len(questions), "bank": {
            "questions": len(questions), "single_choice": 4,
            "multiple_choice": 2, "fill_blank": 5, "free_response": 0,
            "linkedAnswers": 9,
        },
        "partialQuestions": 1, "sourceBlocks": 2, "sourceOnlyBlocks": 1,
        "documents": [document],
    }
    _write_json(structured / document["json"], paper)
    _write_json(structured / "audit.json", audit)
    rows = []
    for question in questions:
        rows.append({
            "id": paper["id"] + ":" + question["id"], "paperId": paper["id"],
            "category": paper["category"], "year": paper["year"],
            "template": paper["template"], "number": question["number"],
            "questionType": question["questionType"],
            "sectionTitle": question["sectionTitle"], "stem": question["stem"],
            "context": question["context"], "options": question["options"],
            "answer": question["answer"], "sourcePages": question["sourcePages"],
            "sourceBlocks": question["sourceBlocks"], "status": question["status"],
        })
    (structured / "question-bank.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )
    return structured, output


class QuestionDatabaseTests(unittest.TestCase):
    def test_kaoyan_writing_keeps_numbered_directions_and_email_paragraphs(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            structured, output = _make_fixture(Path(folder))
            paper_path = structured / "papers/test/2025.json"
            paper = json.loads(paper_path.read_text(encoding="utf-8"))
            paper["category"] = "kaoyan"
            prompt = paper["questions"][0]
            prompt["questionType"] = "free_response"
            prompt["stem"] = "1. Directions:"
            prompt["sourceBlocks"] = ["b-1-1", "b-1-3", "b-1-4", "b-1-5"]
            paper["blocks"][0].update(
                role="question", text="1. Directions:", contentHtml="<p>1. Directions:</p>",
                questionId="q-1-1")
            paper["blocks"].extend([
                {"id": "b-1-3", "page": "1", "sourcePageIndex": 1,
                 "sourceBlockIndex": 3, "role": "question", "text": "1) describe the chart,",
                 "contentHtml": "<p>1) describe the chart,</p>", "formulas": [], "images": [],
                 "questionId": "q-1-1"},
                {"id": "b-1-4", "page": "1", "sourcePageIndex": 1,
                 "sourceBlockIndex": 4, "role": "content", "text": "Write 100 words. Do not sign.",
                 "contentHtml": "<p>Write 100 words. <strong>Do not</strong> sign.</p>",
                 "formulas": [], "images": [], "questionId": "q-1-1", "presentation": {
                     "layoutKind": "email", "instructions": [
                         {"text": "Write 100 words.", "strongPrefix": None},
                         {"text": "Do not sign.", "strongPrefix": "Do not"}],
                     "privateField": "must stay private"}},
                {"id": "b-1-5", "page": "1", "sourcePageIndex": 1,
                 "sourceBlockIndex": 5, "role": "content", "text": "Write 200 words. Do not sign.",
                 "contentHtml": "<p>Write 200 words. Do not sign.</p>",
                 "formulas": [], "images": [], "questionId": "q-1-1", "presentation": {
                     "version": 1, "layoutKind": "writing_instructions", "instructions": [
                         {"text": "Write 200 words.", "strongPrefix": None},
                         {"text": "Do not sign.", "strongPrefix": "Do not"}],
                     "privateField": "must stay private"}},
            ])
            _write_json(paper_path, paper)
            audit_path = structured / "audit.json"
            audit = json.loads(audit_path.read_text(encoding="utf-8"))
            audit["categories"] = {"kaoyan": 1}
            audit["sourceBlocks"] = 5
            audit["bank"]["single_choice"] = 3
            audit["bank"]["free_response"] = 1
            audit["documents"][0].update(category="kaoyan", sourceBlocks=5)
            _write_json(audit_path, audit)
            bank_path = structured / "question-bank.jsonl"
            rows = [json.loads(line) for line in bank_path.read_text(encoding="utf-8").splitlines()]
            for row in rows:
                row["category"] = "kaoyan"
            rows[0].update(questionType="free_response", stem=prompt["stem"],
                           sourceBlocks=prompt["sourceBlocks"])
            bank_path.write_text(
                "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
                encoding="utf-8")
            build_database(structured, output)
            with closing(question_database_api.connect(output)) as db:
                actual = question_database_api.question(db, "test:2025:q-1-1")["question"]
            self.assertEqual([item["text"] for item in actual["contentBlocks"]],
                             ["1) describe the chart,", "Write 100 words. Do not sign.",
                              "Write 200 words. Do not sign."])
            self.assertEqual(len(actual["contentBlocks"][1]["presentation"]["instructions"]), 2)
            self.assertNotIn("privateField", actual["contentBlocks"][1]["presentation"])
            self.assertEqual(actual["contentBlocks"][2]["presentation"]["layoutKind"],
                             "writing_instructions")
            self.assertEqual(len(actual["contentBlocks"][2]["presentation"]["instructions"]), 2)
            self.assertNotIn("privateField", actual["contentBlocks"][2]["presentation"])

    def test_diagram_choice_letters_remain_source_letters_when_shuffled(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            structured, output = _make_fixture(Path(folder))
            paper_path = structured / "papers/test/2025.json"
            paper = json.loads(paper_path.read_text(encoding="utf-8"))
            diagram_options = [
                {"label": f"{letter}.", "sourceLabel": f"{letter}.",
                 "text": letter, "sourceOrder": index}
                for index, letter in enumerate("BDEFG", 1)
            ]
            paper["questions"][2]["options"] = diagram_options
            paper["questions"][2]["context"] = {
                "kind": "ordering_diagram", "fixedLetters": ["A", "C", "H"],
            }
            _write_json(paper_path, paper)
            bank_path = structured / "question-bank.jsonl"
            rows = [json.loads(line) for line in bank_path.read_text(encoding="utf-8").splitlines()]
            rows[2]["options"] = diagram_options
            rows[2]["context"] = paper["questions"][2]["context"]
            bank_path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
            build_database(structured, output)
            with closing(question_database_api.connect(output)) as db:
                default = question_database_api.question(db, "test:2025:q-3-1")
                shuffled = question_database_api.question(db, "test:2025:q-3-1", "shuffle", "demo")
            self.assertEqual([option["displayLabel"] for option in default["question"]["options"]],
                             ["B.", "D.", "E.", "F.", "G."])
            self.assertEqual({option["displayLabel"] for option in shuffled["question"]["options"]},
                             {"B.", "D.", "E.", "F.", "G."})

    def test_repeated_printed_option_label_keeps_both_positions_without_scoring(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            structured, output = _make_fixture(Path(folder))
            paper_path = structured / "papers/test/2025.json"
            paper = json.loads(paper_path.read_text(encoding="utf-8"))
            options = [
                {"label": f"{letter}.", "sourceLabel": f"{letter}、",
                 "text": str(index), "sourceOrder": index}
                for index, letter in enumerate("ABCC", 1)
            ]
            paper["questions"][4]["options"] = options
            _write_json(paper_path, paper)
            bank_path = structured / "question-bank.jsonl"
            rows = [json.loads(line) for line in bank_path.read_text(encoding="utf-8").splitlines()]
            rows[4]["options"] = options
            bank_path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")

            build_database(structured, output)
            with sqlite3.connect(output) as db:
                actual = db.execute(
                    """SELECT id,label,source_label,default_position,source_position,is_correct
                         FROM options WHERE question_id='test:2025:q-5-1' ORDER BY default_position"""
                ).fetchall()
                self.assertEqual([row[1:5] for row in actual], [
                    (f"{letter}.", f"{letter}、", index, index)
                    for index, letter in enumerate("ABCC", 1)
                ])
                self.assertEqual(len({row[0] for row in actual}), 4)
                self.assertTrue(all(row[5] is None for row in actual))
            with closing(question_database_api.connect(output)) as db:
                response = question_database_api.question(db, "test:2025:q-5-1", "default", "")
                self.assertEqual([option["displayLabel"] for option in response["question"]["options"]],
                                 ["A、", "B、", "C、", "C、"])

    def test_embedded_answer_entries_are_records_but_not_exam_questions(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            structured, output = _make_fixture(Path(folder))
            paper_path = structured / "papers/test/2025.json"
            paper = json.loads(paper_path.read_text(encoding="utf-8"))
            answer_entry = {
                **paper["questions"][0], "id": "a-1-1", "recordType": "answer",
                "questionType": "free_response", "options": [],
                "stem": "Printed answer-page entry", "answer": _answer(None, "missing"),
            }
            paper["questions"].append(answer_entry)
            _write_json(paper_path, paper)

            stats = build_database(structured, output)
            self.assertEqual(stats.question_records, 12)
            self.assertEqual(stats.bank_questions, 11)
            with sqlite3.connect(output) as db:
                self.assertEqual(db.execute(
                    "SELECT question_count, record_count FROM papers").fetchone(), (11, 12))
                self.assertEqual(db.execute(
                    "SELECT in_bank FROM questions WHERE id='test:2025:a-1-1'").fetchone(), (0,))

    def test_marks_only_explicit_matching_choices_and_preserves_order(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            structured, output = _make_fixture(Path(folder))
            stats = build_database(structured, output)
            self.assertEqual(stats.marked_questions, 3)
            with sqlite3.connect(output) as db:
                db.execute("PRAGMA foreign_keys=ON")
                self.assertEqual(db.execute("PRAGMA foreign_key_check").fetchall(), [])
                self.assertEqual(db.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()[0],
                                 "question-bank.sqlite.v2")
                options = db.execute(
                    """SELECT question_id,label,default_position,source_position,is_correct
                       FROM options ORDER BY question_id,default_position"""
                ).fetchall()
                by_question: dict[str, list] = {}
                for question_id, label, default, source, marked in options:
                    by_question.setdefault(question_id, []).append((label, default, source, marked))
                self.assertEqual(by_question["test:2025:q-1-1"], [
                    ("A.", 1, 4, 0), ("B.", 2, 3, 1),
                    ("C.", 3, 2, 0), ("D.", 4, 1, 0),
                ])
                self.assertEqual([row[-1] for row in by_question["test:2025:q-2-1"]],
                                 [1, 0, 1, 0])
                self.assertEqual([row[-1] for row in by_question["test:2025:q-11-1"]],
                                 [1, 0, 1, 0, 1])
                for number in (3, 4, 5):
                    self.assertTrue(all(row[-1] is None for row in
                                        by_question[f"test:2025:q-{number}-1"]))
                for number in range(6, 11):
                    self.assertEqual(db.execute(
                        "SELECT COUNT(*) FROM options WHERE question_id=?",
                        (f"test:2025:q-{number}-1",)).fetchone()[0], 0)
                    self.assertEqual(db.execute(
                        "SELECT value FROM answers WHERE question_id=?",
                        (f"test:2025:q-{number}-1",)).fetchone()[0], str(number))
                self.assertEqual(db.execute("SELECT question_count,record_count FROM papers").fetchone(),
                                 (11, 11))
                self.assertEqual(db.execute("SELECT COUNT(*) FROM context_source_blocks").fetchone()[0], 11)
                self.assertEqual(db.execute("SELECT formulas_json,images_json FROM source_blocks LIMIT 1").fetchone(),
                                 ('["x^2"]', '["figure.png"]'))

    def test_rebuild_is_identical_and_failed_validation_keeps_prior_database(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            structured, output = _make_fixture(Path(folder))
            build_database(structured, output)
            original = hashlib.sha256(output.read_bytes()).digest()
            build_database(structured, output)
            self.assertEqual(hashlib.sha256(output.read_bytes()).digest(), original)
            self.assertEqual(hashlib.sha256(output.with_name(output.name + ".bak").read_bytes()).digest(), original)
            audit_path = structured / "audit.json"
            audit = json.loads(audit_path.read_text(encoding="utf-8"))
            audit["documents"][0]["questions"] -= 1
            _write_json(audit_path, audit)
            with self.assertRaisesRegex(ValueError, "question records"):
                build_database(structured, output)
            self.assertEqual(hashlib.sha256(output.read_bytes()).digest(), original)


if __name__ == "__main__":
    unittest.main()
