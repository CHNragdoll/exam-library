"""HTTP checks for the read-only semantic API and answer separation."""

from __future__ import annotations

from contextlib import closing
from http.client import HTTPConnection
import json
from pathlib import Path
import shutil
import sqlite3
import tempfile
import threading
import unittest
from urllib.parse import quote

from scripts.build_question_database import build_database
from scripts.serve_exam_library import create_server, database_needs_rebuild
from scripts.test_question_database import _make_fixture


class SemanticApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory()
        root = Path(cls.temporary.name)
        cls.structured, cls.database = _make_fixture(root)
        paper_path = cls.structured / "papers/test/2025.json"
        paper = json.loads(paper_path.read_text(encoding="utf-8"))
        paper["toc"] = [
            {"id": "part", "kind": "section", "label": "Part I"},
            {"id": "section", "kind": "section", "label": "Section A", "parentId": "part"},
            {"id": "q-1-1", "kind": "question", "parentId": "section"},
        ]
        paper["questions"][0]["subquestions"] = [
            {"number": "a", "text": "Explain the choice"}]
        paper["questions"][0]["continuations"] = [
            {"sourceMarker": "Question 1 continued", "sourceBlockId": "b-1-2"}]
        paper["questions"][0]["answer"]["explanation"] = "PRIVATE ANSWER EXPLANATION"
        paper["blocks"][0]["questionId"] = "q-1-1"
        paper["blocks"][0]["contentHtml"] += (
            '<img src="/cs408-latex-2009-2017/assets/figures/2025-questions-p012-b001.svg" alt="题47图">')
        paper["blocks"][1]["contentHtml"] = (
            '<div class="paragraph-group"><p>First paragraph.</p>'
            '<p>Second paragraph.</p></div>')
        paper_path.write_text(json.dumps(paper, ensure_ascii=False), encoding="utf-8")
        bank_path = cls.structured / "question-bank.jsonl"
        bank_rows = [json.loads(line) for line in bank_path.read_text(encoding="utf-8").splitlines()]
        bank_rows[0]["answer"] = paper["questions"][0]["answer"]
        bank_path.write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in bank_rows),
            encoding="utf-8",
        )
        build_database(cls.structured, cls.database)
        cls.server = create_server(0, root, cls.database)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)
        cls.temporary.cleanup()

    def get(self, path: str, port: int | None = None) -> tuple[int, dict]:
        connection = HTTPConnection("127.0.0.1", port or self.server.server_address[1], timeout=3)
        try:
            connection.request("GET", path)
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    def test_ordered_hierarchy_provenance_and_linked_context(self) -> None:
        status, result = self.get("/api/v2/meta")
        self.assertEqual(status, 200)
        self.assertEqual(result["schemaVersion"], "question-bank.sqlite.v2")
        self.assertEqual(result["semanticSchemaVersion"], "question-bank.semantic.v3")
        status, result = self.get("/api/v2/papers/test%3A2025/semantic")
        self.assertEqual(status, 200)
        self.assertEqual(result["paper"]["id"], "test:2025")
        root = result["root"]
        self.assertEqual(root["type"], "paper")
        part = next(node for node in root["children"] if node["title"] == "Part I")
        section = next(node for node in part["children"] if node["title"] == "Section A")
        first = next(node for node in section["children"] if node["questionId"] == "test:2025:q-1-1")
        self.assertEqual(first["type"], "question")
        self.assertEqual(first["sourceJsonPath"], "$.questions[0]")
        self.assertEqual([child["type"] for child in first["children"]],
                         ["subquestion", "option", "option", "option", "option"])
        self.assertEqual([child["optionId"] for child in first["children"] if child["type"] == "option"],
                         [f"test:2025:q-1-1:{letter}" for letter in "ABCD"])
        self.assertEqual(first["units"][0]["provenance"]["jsonPath"], "$.questions[0].stem")
        self.assertEqual(len(first["units"][0]["provenance"]["sourceHash"]), 64)
        self.assertEqual(first["links"][0]["type"], "shared_context")
        self.assertNotIn("scoreability", first)
        all_text = json.dumps(result, ensure_ascii=False)
        self.assertNotIn("PRIVATE ANSWER EXPLANATION", all_text)
        self.assertNotIn('"type": "answer"', all_text)
        self.assertNotIn("correctOptionIds", all_text)
        self.assertNotIn("is_correct", all_text)
        self.assertNotIn("scoreability", all_text)
        section_units = [unit for child in root["children"] for unit in child["units"]]
        self.assertTrue(any(unit["provenance"]["sourceBlockId"] == "test:2025:b-1-2"
                            for unit in section_units))

        node_id = quote(first["id"], safe="")
        status, single = self.get(f"/api/v2/nodes/{node_id}")
        self.assertEqual(status, 200)
        self.assertEqual(single["node"]["id"], first["id"])
        self.assertEqual([item["link"]["type"] for item in single["linkedNodes"]],
                         ["shared_context", "continuation"])
        self.assertEqual(single["linkedNodes"][0]["node"]["units"][0]["text"], "Shared context")
        self.assertNotIn("PRIVATE ANSWER EXPLANATION", json.dumps(single))

    def test_explicit_answer_route_and_v1_compatibility(self) -> None:
        status, legacy_meta = self.get("/api/v1/meta")
        self.assertEqual(status, 200)
        self.assertEqual(legacy_meta, {"schemaVersion": "question-bank.sqlite.v2",
                                       "papers": 1, "questions": 11, "options": 24})
        status, legacy = self.get("/api/v1/papers/test%3A2025/questions?order=shuffle&seed=demo")
        self.assertEqual(status, 200)
        first = legacy["questions"][0]
        self.assertNotIn("PRIVATE ANSWER EXPLANATION", json.dumps(legacy))
        self.assertTrue(all("isCorrect" not in option for option in first["options"]))
        self.assertEqual(self.get("/api/v1/papers/test%3A2025/questions?order=shuffle&seed=demo")[1],
                         legacy)
        status, tree = self.get("/api/v2/papers/test%3A2025/semantic")
        part = next(node for node in tree["root"]["children"] if node["title"] == "Part I")
        section = next(node for node in part["children"] if node["title"] == "Section A")
        node = next(node for node in section["children"] if node["questionId"] == first["id"])
        node_id = quote(node["id"], safe="")
        status, answer = self.get(f"/api/v2/nodes/{node_id}/answer")
        self.assertEqual(status, 200)
        self.assertEqual(answer["answer"]["value"], "B")
        self.assertEqual(answer["answer"]["correctOptionIds"], ["test:2025:q-1-1:B"])
        self.assertEqual(answer["answer"]["explanation"], "PRIVATE ANSWER EXPLANATION")
        self.assertEqual(answer["answerNodes"][0]["type"], "answer")
        self.assertEqual(answer["scoreability"], {"scoreable": True, "reason": "marked_choice"})

    def test_practice_api_provides_existing_redraw_and_original(self) -> None:
        status, result = self.get("/api/v1/papers/test%3A2025/questions?order=default")
        self.assertEqual(status, 200)
        images = result["questions"][0]["contentBlocks"][0]["images"]
        self.assertEqual(images[0]["src"],
                         "/cs408-latex-2009-2017/assets/figures/2025-questions-p012-b001.svg")
        self.assertEqual(images[0]["redraw"]["src"],
                         "/exam-library/assets/redrawn/cs408-2025-questions-p012-b001-v4-color.png")

    def test_unknown_and_malicious_paths(self) -> None:
        for path in (
            "/api/v2/papers/unknown/semantic", "/api/v2/nodes/unknown",
            "/api/v2/nodes/%2e%2e", "/api/v2/nodes/%2e%2e/answer",
            "/api/v2/papers/test%3A2025%2F..%2Funknown/semantic",
        ):
            with self.subTest(path=path):
                self.assertEqual(self.get(path)[0], 404)

    def test_real_cs408_answer_patterns_are_suppressed_until_explicit_route(self) -> None:
        corpus = Path(__file__).resolve().parents[1] / "data/sources/exam-library/structured"
        audit = json.loads((corpus / "audit.json").read_text(encoding="utf-8"))
        for source_id, kind, local_block, predicate, reason in (
            ("cs408:2011-complete", "complete", "b-1-1",
             lambda block: (block.get("text") or "").startswith("解答："),
             "unresolved_answer_boundary"),
            ("cs408:2025-answers", "answers", "b-1-2",
             lambda block: block.get("status") == "source_only"
             and block.get("role") == "content" and "1. B" in (block.get("text") or ""),
             "answer_document_requires_explicit_route"),
        ):
            with self.subTest(source_id=source_id):
                document = next(item for item in audit["documents"] if item["id"] == source_id)
                source_paper = json.loads((corpus / document["json"]).read_text(encoding="utf-8"))
                private_text = next(block["text"] for block in source_paper["blocks"] if predicate(block))
                target = self.database.with_name(kind + ".sqlite3")
                shutil.copyfile(self.database, target)
                with closing(sqlite3.connect(target)) as connection:
                    with connection:
                        connection.execute("UPDATE papers SET kind = ? WHERE id = 'test:2025'", (kind,))
                        connection.execute(
                            """UPDATE content_units SET text = ?, content_html = NULL WHERE id IN (
                                   SELECT content_unit_id FROM unit_provenance WHERE source_block_id = ?)""",
                            (private_text, "test:2025:" + local_block),
                        )
                        if kind == "answers":
                            connection.execute(
                                """UPDATE semantic_nodes SET node_type = 'answer',
                                          answer_question_id = question_id
                                    WHERE question_id = 'test:2025:q-1-1' AND node_type = 'question'""")
                server = create_server(0, Path(self.temporary.name), target)
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                try:
                    port = server.server_address[1]
                    status, public = self.get("/api/v2/papers/test%3A2025/semantic", port)
                    self.assertEqual(status, 200)
                    self.assertEqual(public["root"]["suppressionReason"], reason)
                    def unit_texts(node: dict) -> list[str | None]:
                        return ([unit["text"] for unit in node["units"]]
                                + [text for child in node["children"] for text in unit_texts(child)])

                    self.assertNotIn(private_text, unit_texts(public["root"]))
                    if kind == "answers":
                        self.assertNotIn("Explain the choice", unit_texts(public["root"]))
                    status, explicit = self.get("/api/v2/papers/test%3A2025/answers", port)
                    self.assertEqual(status, 200)
                    self.assertIn(private_text, unit_texts(explicit["root"]))
                    if kind == "complete":
                        self.assertIn("Question 1", unit_texts(public["root"]))
                        part = next(node for node in public["root"]["children"]
                                    if node["title"] == "Part I")
                        section = next(node for node in part["children"]
                                       if node["title"] == "Section A")
                        first = next(node for node in section["children"]
                                     if node["questionId"] == "test:2025:q-1-1")
                        self.assertEqual(first["suppressionReason"], reason)
                        self.assertGreater(first["suppressedUnitCount"], 0)
                    else:
                        self.assertEqual(public["root"]["children"], [])
                finally:
                    server.shutdown()
                    server.server_close()
                    thread.join(timeout=2)

    def test_old_database_requires_rebuild_and_reports_clear_api_error(self) -> None:
        old = self.database.with_name("old.sqlite3")
        shutil.copyfile(self.database, old)
        with closing(sqlite3.connect(old)) as connection:
            with connection:
                connection.execute("DELETE FROM meta WHERE key='semantic_schema_version'")
        self.assertFalse(database_needs_rebuild(self.database, self.structured))
        self.assertTrue(database_needs_rebuild(old, self.structured))
        server = create_server(0, Path(self.temporary.name), old)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            status, result = self.get("/api/v2/meta", server.server_address[1])
            self.assertEqual(status, 503)
            self.assertIn("rebuild question database", result["error"])
            self.assertEqual(self.get("/api/v1/meta", server.server_address[1])[0], 200)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
