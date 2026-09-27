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
            '<img src="../../../../assets/chart.svg" alt="source chart">'
            '<div class="paragraph-group">'
            '<p><span hidden>第38题（续）：</span>第一段</p>'
            '<p>第二段</p></div>')
        paper["blocks"][0]["text"] = "第38题（续）：第一段 第二段"
        paper["blocks"][0]["presentation"] = {"displayText": "第一段 第二段"}
        paper["blocks"][1]["text"] = "第6题（续）："
        paper["blocks"][1]["contentHtml"] = '<p><span hidden>第6题（续）：</span></p>'
        paper["blocks"][1]["presentation"] = {"displayText": ""}
        paper["questions"][0]["sourceBlocks"].append("b-1-2")
        paper["questions"][0]["options"][0]["image"] = {
            "src": "../../../../assets/chart.svg", "sourceBlockId": "b-1-1",
            "alt": "原卷选项 A 图", "crop": {
                "x": 0, "y": 0, "width": 40, "height": 30,
                "sourceWidth": 80, "sourceHeight": 60,
            },
        }
        paper_json.write_text(json.dumps(paper, ensure_ascii=False), encoding="utf-8")
        bank_path = structured / "question-bank.jsonl"
        bank_rows = [json.loads(line) for line in bank_path.read_text(encoding="utf-8").splitlines()]
        bank_rows[0]["options"][0]["image"] = paper["questions"][0]["options"][0]["image"]
        bank_rows[0]["sourceBlocks"] = paper["questions"][0]["sourceBlocks"]
        bank_path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in bank_rows), encoding="utf-8")
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
        self.assertEqual(first["contentBlocks"][0]["text"], "第一段 第二段")
        self.assertEqual(first["contentBlocks"][0]["paragraphs"], ["第一段", "第二段"])
        self.assertEqual(first["contentBlocks"][1]["text"], "")
        self.assertEqual(first["contentBlocks"][1]["paragraphs"], [])
        self.assertEqual(first["contentBlocks"][0]["images"],
                         [{"src": "/assets/chart.svg", "alt": "source chart"}])
        self.assertEqual(first["options"][0]["image"], {
            "src": "/assets/chart.svg", "sourceBlockId": "test:2025:b-1-1",
            "alt": "原卷选项 A 图", "crop": {
                "x": 0, "y": 0, "width": 40, "height": 30,
                "sourceWidth": 80, "sourceHeight": 60,
            },
        })
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
        five = next(item for item in result["questions"] if item["number"] == "11")
        self.assertEqual([o["displayLabel"] for o in five["options"]],
                         ["A.", "B.", "C.", "D.", "E."])
        status, five_answer = self.get(
            "/api/v1/questions/" + quote(five["id"], safe="") + "/answer")
        self.assertEqual(status, 200)
        self.assertEqual(five_answer["correctOptionIds"], [
            "test:2025:q-11-1:A", "test:2025:q-11-1:C", "test:2025:q-11-1:E"])

    def test_unknown_answers_and_unavailable_database(self) -> None:
        status, result = self.get("/api/v1/meta")
        self.assertEqual(status, 200)
        self.assertEqual((result["papers"], result["questions"]), (1, 11))
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
