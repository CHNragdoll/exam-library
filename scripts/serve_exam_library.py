#!/usr/bin/env python3
"""Serve the offline exam library on localhost without external dependencies."""

from __future__ import annotations

import argparse
from contextlib import closing
import errno
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path, PurePosixPath
import sqlite3
import subprocess
import sys
from urllib.parse import parse_qs, unquote, urlsplit

if __package__:
    from . import question_database_api as dbapi
else:
    import question_database_api as dbapi


SOURCES = (Path(__file__).resolve().parents[1] / "data" / "sources").resolve()
DEFAULT_PORT = 8765


class ExamLibraryHandler(SimpleHTTPRequestHandler):
    """Static files under data/sources, with a stable library landing URL."""

    def __init__(self, *args, database_path: str | None = None, **kwargs):
        self.database_path = Path(database_path) if database_path else dbapi.DEFAULT_DATABASE
        super().__init__(*args, **kwargs)

    def _json_response(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _api_response(self) -> dict:
        parsed = urlsplit(self.path)
        parts = unquote(parsed.path).strip("/").split("/")
        query = parse_qs(parsed.query, max_num_fields=8)
        order = query.get("order", ["default"])[0]
        seed = query.get("seed", [""])[0]
        with closing(dbapi.connect(self.database_path)) as connection:
            if parts == ["api", "v1", "meta"]:
                return dbapi.metadata(connection)
            if parts == ["api", "v1", "papers"]:
                return dbapi.list_papers(connection, query.get("category", [None])[0])
            if len(parts) == 5 and parts[:3] == ["api", "v1", "papers"] and parts[4] == "questions":
                return dbapi.paper_questions(connection, parts[3], order, seed)
            if len(parts) == 4 and parts[:3] == ["api", "v1", "questions"]:
                return dbapi.question(connection, parts[3], order, seed)
            if len(parts) == 5 and parts[:3] == ["api", "v1", "questions"] and parts[4] == "answer":
                return dbapi.answer(connection, parts[3])
        raise LookupError("endpoint not found")

    def do_GET(self) -> None:
        if urlsplit(self.path).path.startswith("/api/"):
            try:
                self._json_response(200, self._api_response())
            except FileNotFoundError:
                self._json_response(503, {"error": "question database is not built"})
            except ValueError:
                self._json_response(400, {"error": "invalid query"})
            except LookupError:
                self._json_response(404, {"error": "not found"})
            except sqlite3.DatabaseError:
                self._json_response(503, {"error": "question database unavailable"})
            return
        super().do_GET()

    def _target(self, request_path: str) -> Path | None:
        raw_path = unquote(urlsplit(request_path).path)
        if "\x00" in raw_path or ".." in PurePosixPath(raw_path).parts:
            return None
        root = Path(self.directory).resolve()
        target = (root / raw_path.lstrip("/")).resolve()
        return target if target.is_relative_to(root) else None

    def translate_path(self, path: str) -> str:
        # send_head rejects an invalid target before SimpleHTTPRequestHandler
        # can read it. This fallback keeps translate_path safe if called alone.
        target = self._target(path)
        return str(target) if target is not None else str(Path(self.directory) / "__invalid_path__")

    def send_head(self):
        if urlsplit(self.path).path == "/":
            self.send_response(302)
            self.send_header("Location", "/exam-library/index.htm")
            self.end_headers()
            return None
        target = self._target(self.path)
        if target is None:
            self.send_error(404, "Not Found")
            return None
        return super().send_head()

    def list_directory(self, path: str):
        self.send_error(404, "Not Found")
        return None

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store, max-age=0")
        super().end_headers()


def create_server(port: int = DEFAULT_PORT, root: Path = SOURCES,
                  database: Path = dbapi.DEFAULT_DATABASE) -> ThreadingHTTPServer:
    if not (0 <= port <= 65535):
        raise ValueError("port must be between 0 and 65535")
    return ThreadingHTTPServer(
        ("127.0.0.1", port),
        partial(ExamLibraryHandler, directory=str(root.resolve()), database_path=str(database.resolve())),
    )


def database_inputs_newer(database: Path, structured: Path) -> bool:
    """Detect edits to every structured input consumed by the SQLite builder."""
    if not database.is_file():
        return True
    database_mtime = database.stat().st_mtime_ns
    inputs = (structured / "audit.json", structured / "question-bank.jsonl")
    for source in (*inputs, *(structured / "papers").rglob("*.json")):
        if source.is_file() and source.stat().st_mtime_ns > database_mtime:
            return True
    return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="在 localhost 打开真题库")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"监听端口（默认 {DEFAULT_PORT}）")
    args = parser.parse_args(argv)
    if not (1 <= args.port <= 65535):
        parser.error("--port 必须在 1 到 65535 之间")
    if not (SOURCES / "exam-library" / "index.htm").is_file():
        print("真题库入口不存在：请在 exam-library 项目内运行此脚本。", file=sys.stderr)
        return 1
    try:
        server = create_server(args.port)
    except OSError as exc:
        if exc.errno == errno.EADDRINUSE:
            print(f"端口 {args.port} 已被占用；可用 --port 指定其他端口。", file=sys.stderr)
        else:
            print(f"无法启动本地服务：{exc}", file=sys.stderr)
        return 1
    stale = database_inputs_newer(dbapi.DEFAULT_DATABASE,
                                  SOURCES / "exam-library/structured")
    if not stale:
        try:
            with closing(dbapi.connect()) as connection:
                stale = dbapi.metadata(connection)["schemaVersion"] != dbapi.SCHEMA_VERSION
        except (OSError, sqlite3.DatabaseError):
            stale = True
    if stale:
        print("正在从结构化试卷生成本地题库数据库…", flush=True)
        try:
            subprocess.run([sys.executable, str(Path(__file__).with_name("build_question_database.py"))],
                           check=True)
        except subprocess.CalledProcessError:
            server.server_close()
            print("题库数据库生成失败；请检查结构化试卷数据。", file=sys.stderr)
            return 1
    print(f"真题库已启动：http://localhost:{args.port}/", flush=True)
    print("按 Ctrl+C 停止服务。", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n服务已停止。", flush=True)
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
