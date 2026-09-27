"""HTTP regression checks for the localhost exam-library entry point."""

from contextlib import redirect_stderr
from http.client import HTTPConnection
from io import StringIO
from pathlib import Path
import tempfile
import threading
import unittest

from scripts.serve_exam_library import create_server, main


class ExamLibraryServerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._files = tempfile.TemporaryDirectory()
        cls._outside = tempfile.TemporaryDirectory()
        cls.root = Path(cls._files.name)
        (cls.root / "exam-library").mkdir()
        (cls.root / "assets").mkdir()
        (cls.root / "exam-library" / "index.htm").write_text(
            '<a href="../assets/figure.svg">figure</a>', encoding="utf-8"
        )
        (cls.root / "assets" / "figure.svg").write_text(
            '<svg xmlns="http://www.w3.org/2000/svg"/>', encoding="utf-8"
        )
        (cls.root / "assets" / "paper.tex").write_text(
            "\\documentclass{article}", encoding="utf-8"
        )
        (cls.root / "assets" / "style.css").write_text(
            "body { color: black; }", encoding="utf-8"
        )
        (Path(cls._outside.name) / "private.txt").write_text("outside", encoding="utf-8")
        (cls.root / "assets" / "escape.txt").symlink_to(Path(cls._outside.name) / "private.txt")
        cls.server = create_server(0, cls.root)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)
        cls._files.cleanup()
        cls._outside.cleanup()

    def request(self, path: str, port: int | None = None) -> tuple[int, dict[str, str], bytes]:
        connection = HTTPConnection("127.0.0.1", port or self.port, timeout=3)
        try:
            connection.request("GET", path)
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()

    def test_root_redirects_to_library(self) -> None:
        status, headers, _ = self.request("/")
        self.assertEqual(status, 302)
        self.assertEqual(headers["Location"], "/exam-library/index.htm")
        self.assertIn("no-store", headers["Cache-Control"])

    def test_html_and_relative_assets_are_accessible(self) -> None:
        status, headers, html = self.request("/exam-library/index.htm")
        self.assertEqual(status, 200)
        self.assertIn(b'../assets/figure.svg', html)
        self.assertIn("no-store", headers["Cache-Control"])
        for path, content in (
            ("/assets/figure.svg", b"<svg"),
            ("/assets/paper.tex", b"\\documentclass"),
            ("/assets/style.css", b"body"),
        ):
            with self.subTest(path=path):
                status, asset_headers, body = self.request(path)
                self.assertEqual(status, 200)
                self.assertIn(content, body)
                self.assertIn("no-store", asset_headers["Cache-Control"])

    def test_missing_listing_and_directory_escape_return_404(self) -> None:
        for path in (
            "/missing.htm",
            "/assets/",
            "/%2e%2e/private.txt",
            "/assets/%2e%2e/%2e%2e/private.txt",
            "/assets/escape.txt",
        ):
            with self.subTest(path=path):
                status, _, body = self.request(path)
                self.assertEqual(status, 404)
                self.assertNotIn(b"outside", body)

    def test_occupied_port_has_actionable_error(self) -> None:
        output = StringIO()
        with redirect_stderr(output):
            result = main(["--port", str(self.port)])
        self.assertEqual(result, 1)
        self.assertIn(f"端口 {self.port} 已被占用", output.getvalue())
        self.assertIn("--port", output.getvalue())

    def test_real_library_reflow_structured_and_svg_assets(self) -> None:
        server = create_server(0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            for path, expected in (
                ("/exam-library/index.htm", "考研真题大全".encode()),
                ("/exam-library/structured/index.htm", "结构化".encode()),
                ("/english-exams-reflow-latex/kaoyan/papers/2026-01.htm", b"2026"),
                ("/english-exams-reflow-latex/kaoyan/papers/2026-01.assets/figure-012-004.svg", b"<svg"),
            ):
                with self.subTest(path=path):
                    status, _, body = self.request(path, server.server_address[1])
                    self.assertEqual(status, 200)
                    self.assertTrue(expected in body, f"missing expected content at {path}")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
