"""Read-only JSON views of the generated SQLite question bank.

The stable option ID is the answer key. A shuffled display label is never
stored back to SQLite or used to decide correctness.
"""

from __future__ import annotations

import json
from pathlib import Path
import random
import sqlite3
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup


DEFAULT_DATABASE = Path(__file__).resolve().parents[1] / "data/question-bank.sqlite3"
SCHEMA_VERSION = "question-bank.sqlite.v2"


def connect(database: Path = DEFAULT_DATABASE) -> sqlite3.Connection:
    if not database.is_file():
        raise FileNotFoundError(database)
    connection = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    return connection


def list_papers(connection: sqlite3.Connection, category: str | None = None) -> dict:
    sql = """SELECT id, title, category, category_label, year, kind, question_count
             FROM papers WHERE question_count > 0"""
    params: tuple[str, ...] = ()
    if category:
        sql += " AND category = ?"
        params = (category,)
    sql += " ORDER BY category, year DESC, id"
    return {"papers": [{"id": row["id"], "title": row["title"],
                        "category": row["category"], "categoryLabel": row["category_label"],
                        "year": row["year"], "kind": row["kind"],
                        "questionCount": row["question_count"]}
                       for row in connection.execute(sql, params)]}


def _paper(connection: sqlite3.Connection, paper_id: str) -> dict:
    row = connection.execute(
        "SELECT id, title, category, category_label, kind, year, question_count FROM papers WHERE id = ?",
        (paper_id,),
    ).fetchone()
    if row is None or not row["question_count"]:
        raise LookupError("paper not found")
    return {"id": row["id"], "title": row["title"], "category": row["category"],
            "categoryLabel": row["category_label"], "kind": row["kind"],
            "year": row["year"], "questionCount": row["question_count"]}


def _question(connection: sqlite3.Connection, row: sqlite3.Row,
              order: str, seed: str) -> dict:
    context = json.loads(row["context_json"]) if row["context_json"] else None
    option_rows = list(connection.execute(
        """SELECT id, label, source_label, text, default_position, source_position, raw_json
           FROM options WHERE question_id = ? ORDER BY default_position""",
        (row["id"],)))
    options = [{"id": option["id"], "label": option["label"],
                "sourceLabel": option["source_label"], "text": option["text"],
                "defaultPosition": option["default_position"],
                "sourcePosition": option["source_position"]}
               for option in option_rows]
    if order == "shuffle":
        random.Random(f"{seed}:{row['id']}").shuffle(options)
    repeated_printed_label = len({option["label"] for option in options}) < len(options)
    source_letters_are_referenced = bool(
        context and context.get("kind") in {"ordering_diagram", "matching_table"}
    )
    for index, option in enumerate(options):
        if source_letters_are_referenced:
            option["displayLabel"] = option["label"]
        elif order == "default":
            option["displayLabel"] = (option["sourceLabel"] or option["label"]
                                      if repeated_printed_label else option["label"])
        else:
            option["displayLabel"] = chr(ord("A") + index) + "."
    paper = connection.execute("SELECT reader_path FROM papers WHERE id = ?", (row["paper_id"],)).fetchone()
    reader_url = "/exam-library/structured/" + paper["reader_path"]
    raw_options = {record["id"]: json.loads(record["raw_json"]) for record in option_rows}
    for option in options:
        image = raw_options[option["id"]].get("image")
        if not isinstance(image, dict):
            continue
        parsed = urlsplit(image.get("src", ""))
        if parsed.scheme or parsed.netloc or not parsed.path:
            continue
        url = urljoin(reader_url, image["src"])
        if url.startswith("/"):
            source_block_id = image.get("sourceBlockId")
            option["image"] = {**image, "src": url}
            if source_block_id:
                option["image"]["sourceBlockId"] = f"{row['paper_id']}:{source_block_id}"
    content_blocks = []
    for block in connection.execute(
        """SELECT b.id, b.role, b.text, b.content_html, b.raw_json FROM question_source_blocks x
             JOIN source_blocks b ON b.id = x.block_id
            WHERE x.question_id = ? AND b.role IN ('content', 'figure') ORDER BY x.ordinal""",
        (row["id"],),
    ):
        markup = BeautifulSoup(block["content_html"] or "", "html.parser")
        presentation = json.loads(block["raw_json"]).get("presentation") or {}
        display_text = presentation.get("displayText")
        visible_text = display_text if isinstance(display_text, str) else block["text"]
        paragraphs = []
        for paragraph in markup.select(".paragraph-group > p"):
            if paragraph.has_attr("hidden"):
                continue
            for hidden in paragraph.select("[hidden]"):
                hidden.decompose()
            value = paragraph.get_text(" ", strip=True)
            if value:
                paragraphs.append(value)
        code = markup.find("pre")
        images = []
        for image in markup.find_all("img", src=True):
            src = image["src"]
            parsed = urlsplit(src)
            if parsed.scheme or parsed.netloc:
                continue
            url = urljoin(reader_url, src)
            if url.startswith("/"):
                images.append({"src": url, "alt": image.get("alt", "")})
        content_blocks.append({"id": block["id"], "role": block["role"],
                               "text": visible_text, "paragraphs": paragraphs,
                               "code": code.get_text() if code else None,
                               "images": images})
    return {
        "id": row["id"], "number": row["number"], "questionType": row["question_type"],
        "sectionTitle": row["section_title"], "stem": row["stem"],
        "context": context,
        "options": options, "contentBlocks": content_blocks,
        "status": row["status"], "answerStatus": row["answer_status"],
        "sourcePages": json.loads(row["source_pages_json"] or "[]"),
        "sourceBlocks": [r[0] for r in connection.execute(
            "SELECT block_id FROM question_source_blocks WHERE question_id = ? ORDER BY ordinal",
            (row["id"],))],
    }


def paper_questions(connection: sqlite3.Connection, paper_id: str,
                    order: str = "default", seed: str = "") -> dict:
    if order not in {"default", "shuffle"} or len(seed) > 128:
        raise ValueError("invalid option order or seed")
    paper = _paper(connection, paper_id)
    rows = connection.execute(
        """SELECT q.id, q.paper_id, q.number, q.question_type, q.section_title, q.stem,
                  q.context_json, q.status, q.source_pages_json, a.status AS answer_status
             FROM questions q JOIN answers a ON a.question_id = q.id
            WHERE q.paper_id = ? AND q.in_bank = 1 ORDER BY q.ordinal""",
        (paper_id,),
    )
    questions = [_question(connection, row, order, seed) for row in rows]
    if len(questions) != paper["questionCount"]:
        raise sqlite3.DatabaseError("paper question count mismatch")
    return {"paper": paper, "questions": questions, "order": order, "seed": seed}


def question(connection: sqlite3.Connection, question_id: str,
             order: str = "default", seed: str = "") -> dict:
    if order not in {"default", "shuffle"} or len(seed) > 128:
        raise ValueError("invalid option order or seed")
    row = connection.execute(
        """SELECT q.id, q.paper_id, q.number, q.question_type, q.section_title,
                  q.stem, q.context_json, q.status, q.source_pages_json,
                  a.status AS answer_status
             FROM questions q JOIN answers a ON a.question_id = q.id
            WHERE q.id = ? AND q.in_bank = 1""",
        (question_id,),
    ).fetchone()
    if row is None:
        raise LookupError("question not found")
    return {"paper": _paper(connection, row["paper_id"]),
            "question": _question(connection, row, order, seed),
            "order": order, "seed": seed}


def answer(connection: sqlite3.Connection, question_id: str) -> dict:
    row = connection.execute(
        """SELECT a.value, a.solution, a.explanation, a.commentary, a.knowledge,
                  a.status, a.source_document_id, a.source_question_ids_json,
                  a.source_blocks_json, a.source_pages_json
             FROM answers a JOIN questions q ON q.id = a.question_id
            WHERE q.id = ? AND q.in_bank = 1""",
        (question_id,),
    ).fetchone()
    if row is None:
        raise LookupError("answer not found")
    correct = []
    if row["status"] == "explicit":
        correct = [option[0] for option in connection.execute(
            "SELECT id FROM options WHERE question_id = ? AND is_correct = 1 ORDER BY default_position",
            (question_id,),
        )]
    return {"status": row["status"], "value": row["value"],
            "solution": row["solution"], "explanation": row["explanation"],
            "commentary": row["commentary"], "knowledge": row["knowledge"],
            "correctOptionIds": correct, "sourceDocumentId": row["source_document_id"],
            "sourceQuestionIds": json.loads(row["source_question_ids_json"] or "[]"),
            "sourceBlocks": json.loads(row["source_blocks_json"] or "[]"),
            "sourcePages": json.loads(row["source_pages_json"] or "[]")}


def metadata(connection: sqlite3.Connection) -> dict:
    version = connection.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()
    if version is None:
        raise sqlite3.DatabaseError("schema version missing")
    return {"schemaVersion": version[0],
            "papers": connection.execute("SELECT COUNT(*) FROM papers").fetchone()[0],
            "questions": connection.execute("SELECT COUNT(*) FROM questions WHERE in_bank = 1").fetchone()[0],
            "options": connection.execute("SELECT COUNT(*) FROM options").fetchone()[0]}
