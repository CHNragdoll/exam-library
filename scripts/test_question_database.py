"""Regression tests for the source-preserving SQLite question bank build."""

from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from scripts.build_question_database import build_database


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
            "multiple_choice": 1, "fill_blank": 5, "free_response": 0,
            "linkedAnswers": 8,
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
    def test_marks_only_explicit_matching_choices_and_preserves_order(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            structured, output = _make_fixture(Path(folder))
            stats = build_database(structured, output)
            self.assertEqual(stats.marked_questions, 2)
            with sqlite3.connect(output) as db:
                db.execute("PRAGMA foreign_keys=ON")
                self.assertEqual(db.execute("PRAGMA foreign_key_check").fetchall(), [])
                self.assertEqual(db.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()[0],
                                 "question-bank.sqlite.v1")
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
                                 (10, 10))
                self.assertEqual(db.execute("SELECT COUNT(*) FROM context_source_blocks").fetchone()[0], 10)
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
