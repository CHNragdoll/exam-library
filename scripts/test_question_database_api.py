"""HTTP and answer-identity checks for the SQLite-backed practice API."""

from __future__ import annotations

from http.client import HTTPConnection
import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.parse import quote

from scripts.build_question_database import build_database
from scripts.serve_exam_library import create_server
from scripts.test_question_database import _make_fixture


class QuestionDatabaseApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory()
        root = Path(cls.temporary.name)
        structured, database = _make_fixture(root)
        paper_json = structured / "papers/test/2025.json"
        paper = json.loads(paper_json.read_text(encoding="utf-8"))
        paper["blocks"][0]["contentHtml"] = (
            '<pre><code>int x;\n  x++;</code></pre>'
            '<img src="../../../../assets/chart.svg" alt="source chart">')
        paper_json.write_text(json.dumps(paper, ensure_ascii=False), encoding="utf-8")
        build_database(structured, database)
        public = root / "public"
        (public / "exam-library").mkdir(parents=True)
        (public / "exam-library/index.htm").write_text("library", encoding="utf-8")
        (public / "assets").mkdir()
        (public / "assets/chart.svg").write_text("<svg/>", encoding="utf-8")
        cls.server = create_server(0, public, database)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)
        cls.temporary.cleanup()

    def get(self, path: str) -> tuple[int, dict]:
        conn = HTTPConnection("127.0.0.1", self.server.server_address[1], timeout=3)
        try:
            conn.request("GET", path)
            response = conn.getresponse()
            body = response.read()
            return response.status, json.loads(body) if response.getheader("Content-Type", "").startswith("application/json") else {}
        finally:
            conn.close()

    def test_default_order_shuffled_labels_and_stable_correct_option(self) -> None:
        paper_id = quote("test:2025", safe="")
        status, result = self.get(f"/api/v1/papers/{paper_id}/questions")
        self.assertEqual(status, 200)
        first = result["questions"][0]
        self.assertEqual([o["label"] for o in first["options"]], ["A.", "B.", "C.", "D."])
        self.assertEqual([o["displayLabel"] for o in first["options"]], ["A.", "B.", "C.", "D."])
        self.assertEqual([o["sourcePosition"] for o in first["options"]], [4, 3, 2, 1])
        self.assertEqual(first["contentBlocks"][0]["code"], "int x;\n  x++;")
        self.assertEqual(first["contentBlocks"][0]["images"],
                         [{"src": "/assets/chart.svg", "alt": "source chart"}])
        self.assertTrue(all("isCorrect" not in option for option in first["options"]))
        status, shuffled = self.get(f"/api/v1/papers/{paper_id}/questions?order=shuffle&seed=demo")
        self.assertEqual(status, 200)
        shuffled_first = shuffled["questions"][0]
        self.assertEqual({o["id"] for o in first["options"]},
                         {o["id"] for o in shuffled_first["options"]})
        self.assertEqual([o["displayLabel"] for o in shuffled_first["options"]],
                         ["A.", "B.", "C.", "D."])
        question_id = quote(first["id"], safe="")
        status, answer = self.get(f"/api/v1/questions/{question_id}/answer")
        self.assertEqual(status, 200)
        self.assertEqual(answer["correctOptionIds"], ["test:2025:q-1-1:B"])
        self.assertEqual(answer["value"], "B")

    def test_unknown_answers_and_unavailable_database(self) -> None:
        status, result = self.get("/api/v1/meta")
        self.assertEqual(status, 200)
        self.assertEqual((result["papers"], result["questions"]), (1, 10))
        for number in (3, 4, 5):
            with self.subTest(number=number):
                question_id = quote(f"test:2025:q-{number}-1", safe="")
                status, answer = self.get(f"/api/v1/questions/{question_id}/answer")
                self.assertEqual(status, 200)
                self.assertEqual(answer["correctOptionIds"], [])
        self.assertEqual(self.get("/api/v1/papers/no-such-paper/questions")[0], 404)
        self.assertEqual(self.get("/api/v1/papers/test%3A2025/questions?order=bad")[0], 400)
        self.assertEqual(self.get("/question-bank.sqlite3")[0], 404)


if __name__ == "__main__":
    unittest.main()
