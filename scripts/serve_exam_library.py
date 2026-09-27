#!/usr/bin/env python3
"""Serve the offline exam library on localhost without external dependencies."""

from __future__ import annotations

import argparse
import errno
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path, PurePosixPath
import sys
from urllib.parse import unquote, urlsplit


SOURCES = (Path(__file__).resolve().parents[1] / "data" / "sources").resolve()
DEFAULT_PORT = 8765


class ExamLibraryHandler(SimpleHTTPRequestHandler):
    """Static files under data/sources, with a stable library landing URL."""

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


def create_server(port: int = DEFAULT_PORT, root: Path = SOURCES) -> ThreadingHTTPServer:
    if not (0 <= port <= 65535):
        raise ValueError("port must be between 0 and 65535")
    return ThreadingHTTPServer(
        ("127.0.0.1", port),
        partial(ExamLibraryHandler, directory=str(root.resolve())),
    )


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
