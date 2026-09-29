"""Checks for the additive semantic layer and its source provenance."""

from __future__ import annotations

from collections import Counter
from contextlib import closing
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest

from scripts.build_question_database import REPO_ROOT, SCHEMA_PATH, build_database
from scripts.test_question_database import _make_fixture, _write_json


CORPUS = REPO_ROOT / "data/sources/exam-library/structured"


def _prepare_sample(destination: Path, initial_ids: set[str]) -> tuple[Path, dict]:
    audit = json.loads((CORPUS / "audit.json").read_text(encoding="utf-8"))
    sample = destination / "structured"
    sample.mkdir()
    by_id = {document["id"]: document for document in audit["documents"]}
    ids = set(initial_ids)
    # Answer sheets are separate documents for some exams. Preserve the
    # source-document foreign key by including their dependency closure.
    pending = list(ids)
    while pending:
        paper_id = pending.pop()
        document = by_id[paper_id]
        paper = json.loads((CORPUS / document["json"]).read_text(encoding="utf-8"))
        for question in paper["questions"]:
            source_id = question["answer"].get("sourceDocumentId")
            if source_id and source_id not in ids:
                ids.add(source_id)
                pending.append(source_id)
    documents = [document for document in audit["documents"] if document["id"] in ids]
    for document in documents:
        target = sample / document["json"]
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(CORPUS / document["json"], target)
    rows = [json.loads(line) for line in (CORPUS / "question-bank.jsonl").read_text(
        encoding="utf-8").splitlines()]
    rows = [row for row in rows if row["paperId"] in ids]
    (sample / "question-bank.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    question_counts = Counter(row["questionType"] for row in rows)
    sample_audit = {
        "schema": audit["schema"], "papers": len(documents),
        "categories": dict(Counter(document["category"] for document in documents)),
        "questionRecords": sum(document["questions"] for document in documents),
        "bank": {"questions": len(rows),
                 "linkedAnswers": sum(row["answer"]["status"] == "explicit" for row in rows),
                 **{kind: question_counts[kind] for kind in
                    ("single_choice", "multiple_choice", "fill_blank", "free_response")}},
        "partialQuestions": sum(document["partialQuestions"] for document in documents),
        "sourceBlocks": sum(document["sourceBlocks"] for document in documents),
        "sourceOnlyBlocks": sum(document["sourceOnlyBlocks"] for document in documents),
        "documents": documents,
    }
    _write_json(sample / "audit.json", sample_audit)
    return sample, sample_audit


def _prepare_eight_category_sample(destination: Path) -> tuple[Path, dict]:
    audit = json.loads((CORPUS / "audit.json").read_text(encoding="utf-8"))
    chosen = {}
    for document in audit["documents"]:
        chosen.setdefault(document["category"], document)
    if len(chosen) != 8:
        raise AssertionError(f"Expected eight exam categories, found {sorted(chosen)}")
    return _prepare_sample(destination, {document["id"] for document in chosen.values()})


class SemanticDatabaseTests(unittest.TestCase):
    def test_explicit_hierarchy_and_provenance_keep_unknown_ownership(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            structured, output = _make_fixture(Path(folder))
            paper_path = structured / "papers/test/2025.json"
            paper = json.loads(paper_path.read_text(encoding="utf-8"))
            paper["blocks"][1]["text"] = "First paragraph.\nSecond line.\n\nSecond paragraph."
            paper["blocks"][1]["contentHtml"] = (
                '<div class="paragraph-group"><p>First paragraph.<br/>Second line.</p>'
                '<p>Second paragraph.</p></div>')
            paper["questions"][0]["subquestions"] = [{
                "number": "a", "text": "Explain the choice", "sourceBlockId": "b-1-1"}]
            paper["questions"][0]["continuations"] = [{
                "questionNumber": "1", "sourceMarker": "Question 1 continued",
                "sourceBlockId": "b-1-2", "sourcePage": "1"}]
            _write_json(paper_path, paper)
            build_database(structured, output)
            with closing(sqlite3.connect(output)) as db:
                self.assertEqual(db.execute(
                    "SELECT value FROM meta WHERE key='semantic_schema_version'"
                ).fetchone()[0], "question-bank.semantic.v3")
                self.assertEqual(db.execute(
                    "SELECT COUNT(*) FROM semantic_nodes WHERE node_type='paper'"
                ).fetchone()[0], 1)
                self.assertEqual(db.execute(
                    "SELECT COUNT(*) FROM semantic_nodes WHERE node_type='subquestion'"
                ).fetchone()[0], 1)
                self.assertEqual(db.execute(
                    "SELECT COUNT(*) FROM semantic_links WHERE link_type='shared_context'"
                ).fetchone()[0], 11)
                self.assertEqual(db.execute(
                    "SELECT COUNT(*) FROM semantic_links WHERE link_type='continuation'"
                ).fetchone()[0], 1)
                raw = db.execute("SELECT text,content_html,question_id FROM source_blocks WHERE local_id='b-1-2'").fetchone()
                self.assertEqual(raw, (paper["blocks"][1]["text"], paper["blocks"][1]["contentHtml"], None))
                rows = db.execute(
                    """SELECT n.node_type,u.unit_type,u.text FROM unit_provenance p
                       JOIN content_units u ON u.id=p.content_unit_id
                       JOIN semantic_nodes n ON n.id=u.node_id
                       WHERE p.source_block_id='test:2025:b-1-2'
                       AND u.unit_type='paragraph' ORDER BY u.ordinal"""
                ).fetchall()
                self.assertEqual([row[0] for row in rows], ["section", "section"])
                self.assertEqual([row[1] for row in rows], ["paragraph", "paragraph"])
                self.assertEqual(len(rows), 2)  # The physical line break is not a paragraph.
                self.assertEqual(db.execute(
                    "SELECT COUNT(*) FROM content_units WHERE unit_type='formula'"
                ).fetchone()[0], 2)
                self.assertEqual(db.execute("SELECT COUNT(*) FROM input_hashes").fetchone()[0], 3)
                self.assertEqual(db.execute(
                    "SELECT sha256 FROM input_hashes WHERE relative_path='papers/test/2025.json'"
                ).fetchone()[0], hashlib.sha256(paper_path.read_bytes()).hexdigest())
                self.assertEqual(db.execute("SELECT scoreable,reason FROM scoreability WHERE question_id='test:2025:q-5-1'").fetchone(),
                                 (0, "incomplete_question"))
                self.assertEqual(db.execute("SELECT scoreable,reason FROM scoreability WHERE question_id='test:2025:q-3-1'").fetchone(),
                                 (0, "answer_missing"))
                self.assertEqual(db.execute("SELECT scoreable,reason FROM scoreability WHERE question_id='test:2025:q-4-1'").fetchone(),
                                 (0, "answer_ambiguous"))

    def test_explicit_but_unsafe_choice_has_no_option_marks(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            structured, output = _make_fixture(Path(folder))
            paper_path = structured / "papers/test/2025.json"
            paper = json.loads(paper_path.read_text(encoding="utf-8"))
            paper["questions"][0]["options"][3]["label"] = "C."
            _write_json(paper_path, paper)
            bank_path = structured / "question-bank.jsonl"
            rows = [json.loads(line) for line in bank_path.read_text(encoding="utf-8").splitlines()]
            rows[0]["options"] = paper["questions"][0]["options"]
            bank_path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
            build_database(structured, output)
            with closing(sqlite3.connect(output)) as db:
                self.assertEqual(db.execute(
                    "SELECT scoreable,reason FROM scoreability WHERE question_id='test:2025:q-1-1'"
                ).fetchone(), (0, "unsafe_choice_mapping"))
                self.assertEqual(db.execute(
                    "SELECT COUNT(*) FROM options WHERE question_id='test:2025:q-1-1' AND is_correct IS NOT NULL"
                ).fetchone()[0], 0)
                self.assertEqual(db.execute(
                    """SELECT issue_code FROM quality_issues i JOIN semantic_nodes n
                       ON n.id=i.node_id WHERE n.question_id='test:2025:q-1-1'
                       ORDER BY issue_code"""
                ).fetchall(), [("duplicate_option_label",), ("unsafe_choice_mapping",)])

    def test_printed_cross_form_answer_is_flagged_without_resolution(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            structured, output = _make_fixture(Path(folder))
            paper_path = structured / "papers/test/2025.json"
            paper = json.loads(paper_path.read_text(encoding="utf-8"))
            paper["category"] = "math3"
            paper["questions"][5]["answer"]["value"] = "【同试卷 IV 第一题】"
            _write_json(paper_path, paper)
            audit_path = structured / "audit.json"
            audit = json.loads(audit_path.read_text(encoding="utf-8"))
            audit["categories"] = {"math3": 1}
            audit["documents"][0]["category"] = "math3"
            _write_json(audit_path, audit)
            bank_path = structured / "question-bank.jsonl"
            rows = [json.loads(line) for line in bank_path.read_text(encoding="utf-8").splitlines()]
            for row in rows:
                row["category"] = "math3"
            rows[5]["answer"] = paper["questions"][5]["answer"]
            bank_path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
            build_database(structured, output)
            with closing(sqlite3.connect(output)) as db:
                self.assertEqual(db.execute(
                    """SELECT i.issue_code,i.source_json_path FROM quality_issues i
                       JOIN semantic_nodes n ON n.id=i.node_id
                       WHERE n.question_id='test:2025:q-6-1'"""
                ).fetchall(), [("unresolved_answer_reference", "$.questions[5].answer.value")])
                self.assertEqual(db.execute(
                    "SELECT value,status FROM answers WHERE question_id='test:2025:q-6-1'"
                ).fetchone(), ("【同试卷 IV 第一题】", "explicit"))
                self.assertEqual(db.execute(
                    "SELECT scoreable FROM scoreability WHERE question_id='test:2025:q-6-1'"
                ).fetchone()[0], 0)
                self.assertEqual(db.execute(
                    "SELECT status,target_question_id FROM answer_references WHERE question_id='test:2025:q-6-1'"
                ).fetchone(), ("unresolved", None))

    @unittest.skipUnless((CORPUS / "audit.json").is_file(), "Local exam corpus is unavailable")
    def test_forms_references_choice_sets_and_year_conflict(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            structured, _ = _prepare_sample(Path(folder), {
                "math3:1990-questions", "math3:1991-questions", "math3:1996-questions", "tem4:2022",
                "cet4:2014-06-01",
                "cet4:2022-06-01", "cet6:2026-06-02",
            })
            output = Path(folder) / "sample.sqlite3"
            stats = build_database(structured, output)
            with closing(sqlite3.connect(output)) as db:
                forms = db.execute(
                    "SELECT label,status FROM paper_forms WHERE paper_id='math3:1990-questions' ORDER BY ordinal"
                ).fetchall()
                self.assertEqual(forms, [("IV", "explicit"), ("V", "explicit")])
                self.assertEqual(db.execute(
                    """SELECT f.label FROM question_paper_forms qf
                       JOIN paper_forms f ON f.id=qf.form_id
                       WHERE qf.question_id='math3:1990-questions:q-4-8'"""
                ).fetchone()[0], "V")
                self.assertEqual(db.execute(
                    """SELECT target_question_id,status FROM answer_references
                       WHERE question_id='math3:1990-questions:q-4-8'"""
                ).fetchone(), ("math3:1990-questions:q-4-4", "resolved"))
                self.assertGreater(db.execute(
                    """SELECT COUNT(*) FROM questions WHERE paper_id='math3:1990-questions'
                       AND number='4'"""
                ).fetchone()[0], 2)
                self.assertEqual(db.execute(
                    """SELECT target_question_id,status FROM answer_references
                       WHERE question_id='math3:1991-questions:q-13-2'"""
                ).fetchone(), ("math3:1991-questions:q-12-1", "resolved"))
                self.assertIn("67", db.execute(
                    "SELECT solution FROM answers WHERE question_id='math3:1991-questions:q-13-2'"
                ).fetchone()[0])
                self.assertEqual(db.execute(
                    """SELECT source_field,literal_text,target_number,target_question_id,status
                       FROM answer_references WHERE question_id='math3:1996-questions:q-6-2'"""
                ).fetchone(), ("solution", "【同试卷 IV 第六题】", "7",
                               "math3:1996-questions:q-7-1", "resolved"))
                self.assertEqual(db.execute(
                    "SELECT status,printed_year FROM paper_forms WHERE paper_id='tem4:2022' AND label='supplement'"
                ).fetchone(), ("unresolved_year_conflict", 2023))
                self.assertEqual(db.execute(
                    """SELECT f.label FROM question_paper_forms qf
                       JOIN paper_forms f ON f.id=qf.form_id
                       WHERE qf.question_id='tem4:2022:q-11-2'"""
                ).fetchone()[0], "supplement")
                self.assertEqual(db.execute(
                    """SELECT COUNT(*) FROM quality_issues WHERE paper_id='tem4:2022'
                       AND issue_code='unresolved_paper_year_conflict'"""
                ).fetchone()[0], 1)
                self.assertEqual(db.execute(
                    """SELECT qss.source_block_id FROM quality_issue_source_spans qss
                       JOIN quality_issues qi ON qi.id=qss.issue_id
                       WHERE qi.paper_id='tem4:2022'
                       AND qi.issue_code='unresolved_paper_year_conflict'"""
                ).fetchone()[0], "tem4:2022:b-10-1")
                self.assertEqual(db.execute(
                    """SELECT COUNT(*) FROM choice_set_options o JOIN choice_sets s
                       ON s.id=o.choice_set_id WHERE s.paper_id='cet6:2026-06-02'
                       AND s.kind='word_bank'"""
                ).fetchone()[0], 15)
                self.assertEqual(db.execute(
                    """SELECT COUNT(*) FROM choice_set_options o JOIN choice_sets s
                       ON s.id=o.choice_set_id WHERE s.paper_id='cet4:2022-06-01'
                       AND s.kind='paragraph_bank'"""
                ).fetchone()[0], 12)
                self.assertEqual(db.execute(
                    """SELECT COUNT(*) FROM question_choice_sets qcs JOIN choice_sets s
                       ON s.id=qcs.choice_set_id WHERE s.paper_id='cet4:2022-06-01'
                       AND s.kind='paragraph_bank'"""
                ).fetchone()[0], 10)
                self.assertEqual(db.execute(
                    """SELECT COUNT(*) FROM question_choice_sets qcs JOIN choice_sets s
                       ON s.id=qcs.choice_set_id WHERE s.paper_id='cet4:2014-06-01'
                       AND s.kind='word_bank'"""
                ).fetchone()[0], 10)
                self.assertEqual(db.execute(
                    """SELECT COUNT(*) FROM question_choice_sets qcs JOIN choice_sets s
                       ON s.id=qcs.choice_set_id WHERE s.paper_id='cet4:2014-06-01'
                       AND s.kind='paragraph_bank'"""
                ).fetchone()[0], 10)
                self.assertEqual(db.execute("SELECT COUNT(*) FROM source_spans").fetchone()[0],
                                 stats.source_blocks)

    @unittest.skipUnless((CORPUS / "audit.json").is_file(), "Local exam corpus is unavailable")
    def test_eight_exam_categories_and_all_source_blocks_are_represented(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            structured, audit = _prepare_eight_category_sample(Path(folder))
            output = Path(folder) / "sample.sqlite3"
            stats = build_database(structured, output)
            self.assertGreaterEqual(stats.papers, 8)
            self.assertEqual(stats.source_blocks, audit["sourceBlocks"])
            with closing(sqlite3.connect(output)) as db:
                categories = db.execute(
                    """SELECT DISTINCT p.category FROM semantic_nodes n
                       JOIN papers p ON p.id=n.paper_id WHERE n.node_type='question'"""
                ).fetchall()
                self.assertEqual({row[0] for row in categories},
                                 {"kaoyan", "cet4", "cet6", "tem4", "tem8", "math3", "politics", "cs408"})
                self.assertEqual(db.execute(
                    "SELECT COUNT(DISTINCT source_block_id) FROM unit_provenance WHERE source_block_id IS NOT NULL"
                ).fetchone()[0], stats.source_blocks)
                self.assertEqual(db.execute(
                    """SELECT COUNT(*) FROM source_blocks b LEFT JOIN unit_provenance p
                       ON p.source_block_id=b.id WHERE p.source_block_id IS NULL"""
                ).fetchone()[0], 0)
                self.assertEqual(db.execute("PRAGMA foreign_key_check").fetchall(), [])
                self.assertEqual(db.execute("SELECT COUNT(*) FROM input_hashes").fetchone()[0],
                                 stats.papers + 2)
                # Printed TOC section parents take precedence over repeated
                # labels such as "Section A" under different parts.
                for document in audit["documents"]:
                    paper = json.loads((structured / document["json"]).read_text(encoding="utf-8"))
                    section_paths = {entry["id"]: f"$.toc[{index}]" for index, entry in
                                     enumerate(paper["toc"]) if entry["kind"] == "section"}
                    node_rows = db.execute(
                        """SELECT id,parent_id,source_json_path FROM semantic_nodes
                           WHERE paper_id=? AND node_type='section'""", (paper["id"],)
                    ).fetchall()
                    node_by_path = {path: (node_id, parent) for node_id, parent, path in node_rows}
                    for entry in paper["toc"]:
                        if entry["kind"] == "section" and entry.get("parentId"):
                            child = node_by_path[section_paths[entry["id"]]]
                            parent = node_by_path[section_paths[entry["parentId"]]]
                            self.assertEqual(child[1], parent[0])

    def test_failed_migration_preserves_existing_v2_database(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            structured, output = _make_fixture(Path(folder))
            v2_schema = SCHEMA_PATH.read_text(encoding="utf-8").split(
                "-- Additive semantic model.", 1)[0]
            with closing(sqlite3.connect(output)) as db:
                db.executescript(v2_schema)
                db.execute("INSERT INTO meta VALUES ('schema_version','question-bank.sqlite.v2')")
                db.commit()
            before = hashlib.sha256(output.read_bytes()).digest()
            paper_path = structured / "papers/test/2025.json"
            paper = json.loads(paper_path.read_text(encoding="utf-8"))
            paper["questions"][0]["options"][1]["sourceOrder"] = 4
            _write_json(paper_path, paper)
            bank_path = structured / "question-bank.jsonl"
            rows = [json.loads(line) for line in bank_path.read_text(encoding="utf-8").splitlines()]
            rows[0]["options"] = paper["questions"][0]["options"]
            bank_path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Duplicate sourceOrder"):
                build_database(structured, output)
            self.assertEqual(hashlib.sha256(output.read_bytes()).digest(), before)
            self.assertFalse(output.with_name(output.name + ".bak").exists())


if __name__ == "__main__":
    unittest.main()
