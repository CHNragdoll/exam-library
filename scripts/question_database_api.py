"""Read-only JSON views of the generated SQLite question bank.

The stable option ID is the answer key. A shuffled display label is never
stored back to SQLite or used to decide correctness.
"""

from __future__ import annotations

import json
from collections import Counter
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path
import random
import re
import sqlite3
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup


DEFAULT_DATABASE = Path(__file__).resolve().parents[1] / "data/question-bank.sqlite3"
SCHEMA_VERSION = "question-bank.sqlite.v2"
SEMANTIC_SCHEMA_VERSION = "question-bank.semantic.v3"
REDRAWS_PATH = Path(__file__).resolve().parents[1] / "data/sources/exam-library/image-redraws.json"
NUMBERED_ANSWER_MARKER = re.compile(
    r"(?<!\d)(\*?)\s*(\d{1,3})\s*[.．、]\s*【(?:参考)?答案】"
)


class SemanticSchemaUnavailable(sqlite3.DatabaseError):
    """The database predates the additive semantic read model."""


@lru_cache(maxsize=1)
def _image_redraws() -> dict[str, dict[str, str]]:
    """Use the same approved original-to-redraw map as the reflow reader."""
    if not REDRAWS_PATH.is_file():
        return {}
    entries = json.loads(REDRAWS_PATH.read_text(encoding="utf-8")).get("images", [])
    redraws = {}
    for entry in entries:
        original, replacement = entry.get("original"), entry.get("replacement")
        if not isinstance(original, str) or not isinstance(replacement, str):
            continue
        if not (Path(__file__).resolve().parents[1] / "data/sources" / replacement).is_file():
            continue
        redraws["/" + original.lstrip("/")] = {
            "src": "/" + replacement.lstrip("/"), "alt": entry.get("alt", "重绘图")
        }
    return redraws


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


def _material_paragraphs(markup: BeautifulSoup) -> list[dict[str, str]]:
    """Retain printed material labels and citations as safe text segments."""
    group = markup.select_one(".paragraph-group")
    if group is None or not group.select_one(".material-label, .material-source"):
        return []
    paragraphs = []
    for paragraph in group.find_all("p", recursive=False):
        if paragraph.has_attr("hidden"):
            continue
        for hidden in paragraph.select("[hidden]"):
            hidden.decompose()
        value = paragraph.get_text(" ", strip=True)
        if value:
            classes = paragraph.get("class", [])
            kind = ("material_label" if "material-label" in classes else
                    "material_source" if "material-source" in classes else "paragraph")
            paragraphs.append({"text": value, "kind": kind})
    return paragraphs


def _stem_material_paragraphs(stem: str, source_text: str,
                              markup: BeautifulSoup) -> list[dict[str, str]]:
    """Use source paragraph roles without reverting corrections in the question stem."""
    paragraphs = _material_paragraphs(markup)
    if not paragraphs:
        return []
    compact = lambda value: re.sub(r"\s+", "", value or "")
    if compact(source_text) == compact(stem):
        return paragraphs
    # A corrected OCR character may differ from the source HTML. Only reuse its
    # paragraph roles when the printed labels/citations and boundaries still match.
    edited = [part.strip() for part in re.split(r"\n\s*\n", stem) if part.strip()]
    if len(edited) != len(paragraphs):
        return []
    mismatches = 0
    for original, correction in zip(paragraphs, edited):
        before, after = compact(original["text"]), compact(correction)
        if before == after:
            continue
        if original["kind"] != "paragraph" or len(before) != len(after):
            return []
        if SequenceMatcher(None, before, after, autojunk=False).ratio() < 0.95:
            return []
        mismatches += 1
        if mismatches > 1:
            return []
    return [{**original, "text": correction}
            for original, correction in zip(paragraphs, edited)]


def _question_labels(connection: sqlite3.Connection, question_id: str) -> list[dict]:
    """Read additive printed-section labels; old v2 databases have none."""
    try:
        rows = connection.execute(
            """SELECT l.id,l.kind,l.text,l.source_title,l.source_block_id
                 FROM question_labels ql JOIN labels l ON l.id=ql.label_id
                WHERE ql.question_id=? ORDER BY ql.ordinal""", (question_id,),
        )
        return [{"id": row["id"], "kind": row["kind"], "text": row["text"],
                 "sourceTitle": row["source_title"],
                 "sourceBlockId": row["source_block_id"]} for row in rows]
    except sqlite3.OperationalError as exc:
        if "no such table" not in str(exc):
            raise
        return []


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
        context and context.get("kind") in {"ordering_diagram", "matching_table", "matching_comments"}
    )
    for index, option in enumerate(options):
        if source_letters_are_referenced:
            option["displayLabel"] = option["label"]
        elif order == "default":
            option["displayLabel"] = (option["sourceLabel"] or option["label"]
                                      if repeated_printed_label else option["label"])
        else:
            option["displayLabel"] = chr(ord("A") + index) + "."
    paper = connection.execute(
        "SELECT reader_path,category,kind FROM papers WHERE id = ?", (row["paper_id"],)
    ).fetchone()
    reader_url = "/exam-library/structured/" + paper["reader_path"]
    material_paper = paper["category"] == "politics" and paper["kind"] == "questions"
    stem_paragraphs = []
    if material_paper:
        for source in connection.execute(
            """SELECT b.text,b.content_html FROM question_source_blocks x
                 JOIN source_blocks b ON b.id=x.block_id
                WHERE x.question_id=? AND b.role='question' ORDER BY x.ordinal""",
            (row["id"],),
        ):
            stem_paragraphs = _stem_material_paragraphs(
                row["stem"] or "", source["text"] or "",
                BeautifulSoup(source["content_html"] or "", "html.parser"),
            )
            if stem_paragraphs:
                break
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
            WHERE x.question_id = ? AND b.role IN ('content', 'figure', 'question')
            ORDER BY x.ordinal""",
        (row["id"],),
    ):
        # A writing prompt can contain numbered directions after its question
        # heading. They are source question blocks, but the first block is
        # already rendered as the stem.
        if block["role"] == "question" and (
            row["question_type"] != "free_response"
            or paper["category"] != "kaoyan"
            or (block["text"] or "").strip() == (row["stem"] or "").strip()
        ):
            continue
        raw_block = json.loads(block["raw_json"])
        if raw_block.get("sourceSection") == "answers":
            continue
        markup = BeautifulSoup(block["content_html"] or "", "html.parser")
        presentation = raw_block.get("presentation") or {}
        display_text = presentation.get("displayText")
        answer_note = presentation.get("answerNote")
        if answer_note:
            if not isinstance(display_text, str):
                continue
            marker = answer_note.get("sourceMarker")
            paragraphs = markup.select(".paragraph-group > p")
            boundary = next((index for index, paragraph in enumerate(paragraphs)
                             if paragraph.get_text(" ", strip=True) == marker), None)
            if boundary is None:
                # The corrected plain text remains safe; uncertain rich markup
                # must not reintroduce the printed answer hint.
                markup = BeautifulSoup("", "html.parser")
            else:
                for paragraph in paragraphs[boundary:]:
                    paragraph.decompose()
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
                item = {"src": url, "alt": image.get("alt", "")}
                redraw = _image_redraws().get(url)
                if redraw:
                    item["redraw"] = redraw
                images.append(item)
        safe_presentation = None
        if presentation.get("layoutKind") == "email":
            safe_presentation = {
                key: presentation[key] for key in (
                    "version", "layoutKind", "segment", "framePart", "lines",
                    "signoffAlignment", "instructionsOutsideFrame", "instructions",
                ) if key in presentation
            }
        elif presentation.get("layoutKind") == "writing_instructions":
            safe_presentation = {
                key: presentation[key] for key in (
                    "version", "layoutKind", "instructions",
                ) if key in presentation
            }
        content_blocks.append({"id": block["id"], "role": block["role"],
                               "text": visible_text, "paragraphs": paragraphs,
                               "styledParagraphs": (_material_paragraphs(markup) if material_paper else []),
                               "code": code.get_text() if code else None,
                               "images": images,
                               **({"presentation": safe_presentation} if safe_presentation else {})})
    return {
        "id": row["id"], "number": row["number"], "questionType": row["question_type"],
        "sectionTitle": row["section_title"], "stem": row["stem"],
        "stemParagraphs": stem_paragraphs,
        "context": context,
        "labels": _question_labels(connection, row["id"]),
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
    source_content, source_base = _exclusive_answer_content(connection, row)
    resolved_reference_only = _resolved_reference_only(
        connection, question_id, row, source_content
    )
    return {"status": row["status"], "value": row["value"],
            "solution": row["solution"], "explanation": row["explanation"],
            "commentary": row["commentary"], "knowledge": row["knowledge"],
            "correctOptionIds": correct, "sourceDocumentId": row["source_document_id"],
            "sourceQuestionIds": json.loads(row["source_question_ids_json"] or "[]"),
            "sourceBlocks": json.loads(row["source_blocks_json"] or "[]"),
            "sourcePages": json.loads(row["source_pages_json"] or "[]"),
            "sourceContentBlocks": source_content, "sourceBaseUrl": source_base,
            "resolvedReferenceOnly": resolved_reference_only}


def _resolved_reference_only(connection: sqlite3.Connection, question_id: str,
                             answer_row: sqlite3.Row, source_content: list[dict]) -> bool:
    """Identify an original answer that only points to a resolved other form.

    The original excerpt is still displayed for provenance. Its resolved
    solution is added only when a trusted answer_references row confirms the
    target and the visible source excerpt contains no substantive answer.
    """
    if (answer_row["status"] != "explicit" or not answer_row["solution"]
            or len(source_content) != 1):
        return False
    try:
        references = connection.execute(
            """SELECT literal_text FROM answer_references
               WHERE question_id = ? AND source_field = 'solution'
                 AND status = 'resolved' AND target_question_id IS NOT NULL""",
            (question_id,),
        )
    except sqlite3.OperationalError as exc:
        if "no such table: answer_references" in str(exc):
            return False  # Legacy v2 databases do not have the semantic model.
        raise
    source_text = re.sub(r"\s+", " ", source_content[0]["text"]).strip()
    for reference in references:
        literal = re.sub(r"\s+", " ", reference["literal_text"]).strip()
        if not literal or not source_text.endswith(literal):
            continue
        printed_number = source_text[:-len(literal)].strip()
        if (re.fullmatch(r"[一二三四五六七八九十百零\d]+[、.．]?", printed_number)
                and answer_row["solution"].strip() != literal):
            return True
    return False


def _exclusive_answer_content(connection: sqlite3.Connection,
                              answer_row: sqlite3.Row) -> tuple[list[dict], str | None]:
    """Expose original layout only when both the answer entry and block are one-question-owned.

    Shared answer keys (for example, eight math choices in one paragraph) must
    never become the main answer to any one question.
    """
    document_id = answer_row["source_document_id"]
    if answer_row["status"] != "explicit" or not document_id:
        return [], None
    own_questions = json.loads(answer_row["source_question_ids_json"] or "[]")
    own_blocks = json.loads(answer_row["source_blocks_json"] or "[]")
    if not own_questions or not own_blocks:
        return [], None
    source = connection.execute(
        "SELECT reader_path, source_reflow FROM papers WHERE id = ?", (document_id,),
    ).fetchone()
    if source is None or not source["source_reflow"]:
        return [], None
    # content_html comes from the structured JSON, where relative asset paths
    # were rebased for the structured reader. The source reflow URL is not the
    # base for these stored fragments (its own HTML has different src values).
    source_url = urljoin("/exam-library/structured/", source["reader_path"])
    parsed = urlsplit(source_url)
    if parsed.scheme or parsed.netloc or not source_url.startswith("/exam-library/structured/"):
        return [], None

    question_owners: Counter[str] = Counter()
    block_owners: Counter[str] = Counter()
    for linked in connection.execute(
        """SELECT source_question_ids_json, source_blocks_json FROM answers
           WHERE source_document_id = ?""", (document_id,),
    ):
        linked_blocks = set(json.loads(linked["source_blocks_json"] or "[]"))
        if not linked_blocks:
            # Answer-paper records can repeat the printed question ID while
            # citing no source blocks. They do not own the question's answer
            # excerpt and must not suppress its real block-backed reference.
            continue
        question_owners.update(set(json.loads(linked["source_question_ids_json"] or "[]")))
        block_owners.update(linked_blocks)
    if not any(question_owners[local_id] == 1 for local_id in own_questions):
        return [], None
    own_numbers = {int(match.group(1)) for local_id in own_questions
                   if (match := re.fullmatch(r"q-(\d+)-\d+", local_id))}

    content = []
    included_blocks: set[str] = set()
    duplicate_references: set[str] = set()
    for local_id in dict.fromkeys(own_blocks):
        if block_owners[local_id] != 1:
            continue
        block = connection.execute(
            """SELECT id, role, text, content_html, status, raw_json FROM source_blocks
               WHERE paper_id = ? AND local_id = ?""", (document_id, local_id),
        ).fetchone()
        if block is None:
            return [], None
        duplicate_of = json.loads(block["raw_json"] or "{}").get("duplicateOf")
        if duplicate_of:
            # Keep duplicateOf provenance in SQLite, but render the canonical
            # PDF-page extraction once. If the canonical block is unavailable
            # for this answer, use the structured answer instead.
            duplicate_references.add(duplicate_of)
            continue
        if block["role"] == "tex_source" or block["status"] == "source_only":
            continue
        if block["content_html"]:
            # Some complete papers put the question continuation, options,
            # and solution in one source block. Ownership by one question does
            # not make that block an answer-only excerpt. Keep the structured
            # answer rather than repeating the stem and options in its panel.
            if block["role"] == "choices" or BeautifulSoup(
                block["content_html"], "html.parser"
            ).select_one(".source-choice-block, .choices, .choice"):
                return [], None
            clean = _without_foreign_answer_tail(block["text"] or "", block["content_html"],
                                                 own_numbers)
            if clean is None:
                return [], None
            clean_text, clean_html = clean
            content.append({"id": block["id"], "role": block["role"],
                            "text": clean_text, "contentHtml": clean_html})
            included_blocks.add(local_id)
    if not duplicate_references <= included_blocks:
        return [], None
    return (content, source_url) if content else ([], None)


def _without_foreign_answer_tail(text: str, html: str,
                                 own_numbers: set[int]) -> tuple[str, str] | None:
    """Trim only a next-question answer marker proven to end one paragraph.

    A marker embedded in prose or markup has no reliable boundary; callers
    fall back to the structured answer instead of showing another answer.
    """
    text_markers = [match for match in NUMBERED_ANSWER_MARKER.finditer(text)
                    if not own_numbers or int(match.group(2)) not in own_numbers]
    html_markers = [match for match in NUMBERED_ANSWER_MARKER.finditer(html)
                    if not own_numbers or int(match.group(2)) not in own_numbers]
    if not text_markers and not html_markers:
        return text, html
    if not own_numbers or len(text_markers) != 1 or len(html_markers) != 1:
        return None
    text_marker, html_marker = text_markers[0], html_markers[0]
    text_tail = re.fullmatch(r"\s*([A-D]{1,4})\s*", text[text_marker.end():], flags=re.I)
    html_tail = re.fullmatch(r"\s*([A-D]{1,4})\s*(</p>\s*)",
                             html[html_marker.end():], flags=re.I)
    if (text_marker.group(1) != "*" or text_marker.group(0) != html_marker.group(0)
            or text_tail is None or html_tail is None
            or text_tail.group(1) != html_tail.group(1)):
        return None
    return (text[:text_marker.start()].rstrip(),
            html[:html_marker.start()] + html_tail.group(2))


def metadata(connection: sqlite3.Connection) -> dict:
    version = connection.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()
    if version is None:
        raise sqlite3.DatabaseError("schema version missing")
    return {"schemaVersion": version[0],
            "papers": connection.execute("SELECT COUNT(*) FROM papers").fetchone()[0],
            "questions": connection.execute("SELECT COUNT(*) FROM questions WHERE in_bank = 1").fetchone()[0],
            "options": connection.execute("SELECT COUNT(*) FROM options").fetchone()[0]}


def require_semantic_schema(connection: sqlite3.Connection) -> None:
    version = connection.execute(
        "SELECT value FROM meta WHERE key = 'semantic_schema_version'"
    ).fetchone()
    if version is None or version[0] != SEMANTIC_SCHEMA_VERSION:
        raise SemanticSchemaUnavailable(
            f"semantic schema unavailable; rebuild question database for {SEMANTIC_SCHEMA_VERSION}"
        )


def semantic_metadata(connection: sqlite3.Connection) -> dict:
    require_semantic_schema(connection)
    return {
        "schemaVersion": metadata(connection)["schemaVersion"],
        "semanticSchemaVersion": SEMANTIC_SCHEMA_VERSION,
        "papers": connection.execute("SELECT COUNT(*) FROM papers").fetchone()[0],
        "nodes": connection.execute("SELECT COUNT(*) FROM semantic_nodes").fetchone()[0],
        "contentUnits": connection.execute("SELECT COUNT(*) FROM content_units").fetchone()[0],
    }


def _semantic_paper(connection: sqlite3.Connection, paper_id: str) -> dict:
    row = connection.execute(
        """SELECT id,title,category,category_label,kind,year,question_count
             FROM papers WHERE id = ?""", (paper_id,),
    ).fetchone()
    if row is None:
        raise LookupError("paper not found")
    return {"id": row["id"], "title": row["title"], "category": row["category"],
            "categoryLabel": row["category_label"], "kind": row["kind"],
            "year": row["year"], "questionCount": row["question_count"]}


def _semantic_tree(connection: sqlite3.Connection, paper_id: str,
                   include_answers: bool = False) -> tuple[dict, dict[str, dict]]:
    paper = _semantic_paper(connection, paper_id)
    rows = connection.execute(
        """SELECT id,parent_id,node_type,ordinal,title,question_id,option_id,source_json_path
             FROM semantic_nodes WHERE paper_id = ? ORDER BY id""", (paper_id,),
    ).fetchall()
    hidden: set[str] = set()
    if not include_answers:
        hidden = {row["id"] for row in rows if row["node_type"] == "answer"}
        # Answer records can own subquestions and other descendants. Hiding
        # only their parent would orphan those descendants at the paper root.
        while True:
            descendants = {row["id"] for row in rows if row["parent_id"] in hidden}
            if descendants <= hidden:
                break
            hidden.update(descendants)
        if paper["kind"] == "answers":
            hidden.update(row["id"] for row in rows if row["node_type"] != "paper")
        elif paper["kind"] == "complete":
            links = connection.execute(
                """SELECT l.from_node_id,l.to_node_id FROM semantic_links l
                     JOIN semantic_nodes n ON n.id = l.from_node_id WHERE n.paper_id = ?""",
                (paper_id,),
            ).fetchall()
            linked_from: dict[str, set[str]] = {}
            for link in links:
                linked_from.setdefault(link["to_node_id"], set()).add(link["from_node_id"])
            hidden.update(target for target, owners in linked_from.items() if owners <= hidden)
            while True:
                descendants = {row["id"] for row in rows if row["parent_id"] in hidden}
                if descendants <= hidden:
                    break
                hidden.update(descendants)
    nodes: dict[str, dict] = {}
    for row in rows:
        if row["id"] in hidden:
            continue
        nodes[row["id"]] = {
            "id": row["id"], "type": row["node_type"], "ordinal": row["ordinal"],
            "title": row["title"], "questionId": row["question_id"],
            "optionId": row["option_id"], "sourceJsonPath": row["source_json_path"],
            "units": [], "links": [], "issues": [], "children": [],
        }
        if row["question_id"]:
            nodes[row["id"]]["labels"] = _question_labels(connection, row["question_id"])

    answer_only_blocks = set()
    if not include_answers and paper["kind"] == "questions":
        answer_only_blocks = {row["id"] for row in connection.execute(
            "SELECT id,raw_json FROM source_blocks WHERE paper_id=?", (paper_id,)
        ) if json.loads(row["raw_json"]).get("sourceSection") == "answers"}

    for row in connection.execute(
        """SELECT u.id,u.node_id,u.ordinal,u.unit_type,u.text,u.content_html,
                  p.source_block_id,p.json_path,p.source_hash
             FROM content_units u JOIN unit_provenance p ON p.content_unit_id = u.id
            WHERE u.paper_id = ? ORDER BY u.node_id,u.ordinal""", (paper_id,),
    ):
        owner = nodes.get(row["node_id"])
        if owner is None:
            continue
        if not include_answers and row["source_block_id"] in answer_only_blocks:
            owner["suppressionReason"] = "printed_answer_requires_reveal"
            owner["suppressedUnitCount"] = owner.get("suppressedUnitCount", 0) + 1
            continue
        # Answer and mixed "complete" papers can place solutions in otherwise
        # unowned or question-owned source blocks. Keep proven structured
        # question fields available; mark raw content whose answer boundary is
        # unresolved and expose it only through an explicit answer route.
        if not include_answers and row["source_block_id"] and paper["kind"] != "questions":
            owner["suppressionReason"] = (
                "answer_document_requires_explicit_route" if paper["kind"] == "answers"
                else "unresolved_answer_boundary")
            owner["suppressedUnitCount"] = owner.get("suppressedUnitCount", 0) + 1
            continue
        owner["units"].append({
            "id": row["id"], "type": row["unit_type"], "ordinal": row["ordinal"],
            "text": row["text"], "contentHtml": row["content_html"],
            "provenance": {"sourceBlockId": row["source_block_id"],
                           "jsonPath": row["json_path"], "sourceHash": row["source_hash"]},
        })
    if not include_answers and paper["kind"] in {"answers", "complete"}:
        root = next((node for node in nodes.values() if node["type"] == "paper"), None)
        if root is not None:
            root["suppressionReason"] = (
                "answer_document_requires_explicit_route" if paper["kind"] == "answers"
                else "unresolved_answer_boundary")

    for row in connection.execute(
        """SELECT l.from_node_id,l.to_node_id,l.link_type,l.ordinal,l.source_json_path
             FROM semantic_links l JOIN semantic_nodes n ON n.id = l.from_node_id
            WHERE n.paper_id = ? ORDER BY l.from_node_id,l.ordinal,l.to_node_id""", (paper_id,),
    ):
        owner = nodes.get(row["from_node_id"])
        if owner is not None and row["to_node_id"] in nodes:
            owner["links"].append({"toNodeId": row["to_node_id"],
                                   "type": row["link_type"], "ordinal": row["ordinal"],
                                   "sourceJsonPath": row["source_json_path"]})

    for row in connection.execute(
        """SELECT node_id,issue_code,detail,source_json_path
             FROM quality_issues WHERE paper_id = ? ORDER BY id""", (paper_id,),
    ):
        owner = nodes.get(row["node_id"])
        if owner is not None and (include_answers or row["issue_code"] != "unsafe_choice_mapping"):
            owner["issues"].append({"code": row["issue_code"], "detail": row["detail"],
                                    "sourceJsonPath": row["source_json_path"]})

    roots = []
    for row in rows:
        current = nodes.get(row["id"])
        if current is None:
            continue
        parent = nodes.get(row["parent_id"])
        if parent is None:
            roots.append(current)
        else:
            parent["children"].append(current)
    if len(roots) != 1 or roots[0]["type"] != "paper":
        raise sqlite3.DatabaseError("semantic paper root mismatch")
    for node in nodes.values():
        node["children"].sort(key=lambda child: child["ordinal"])
    return paper, nodes


def semantic_paper(connection: sqlite3.Connection, paper_id: str) -> dict:
    require_semantic_schema(connection)
    paper, nodes = _semantic_tree(connection, paper_id)
    root = next(node for node in nodes.values() if node["type"] == "paper")
    return {"paper": paper, "root": root}


def semantic_paper_answers(connection: sqlite3.Connection, paper_id: str) -> dict:
    """Explicitly read answer nodes and source-only answer-key material."""
    require_semantic_schema(connection)
    paper, nodes = _semantic_tree(connection, paper_id, include_answers=True)
    root = next(node for node in nodes.values() if node["type"] == "paper")
    return {"paper": paper, "root": root}


def semantic_node(connection: sqlite3.Connection, node_id: str) -> dict:
    require_semantic_schema(connection)
    row = connection.execute("SELECT paper_id FROM semantic_nodes WHERE id = ?", (node_id,)).fetchone()
    if row is None:
        raise LookupError("node not found")
    paper, nodes = _semantic_tree(connection, row["paper_id"])
    node = nodes.get(node_id)
    if node is None:
        raise LookupError("node not found")
    # Linked passages and continuations are often siblings of a question.
    # Include their content so a single-question consumer has full context.
    linked = [{"link": link, "node": {**nodes[link["toNodeId"]], "children": []}}
              for link in node["links"]]
    return {"paper": paper, "node": node, "linkedNodes": linked}


def semantic_node_answer(connection: sqlite3.Connection, node_id: str) -> dict:
    require_semantic_schema(connection)
    row = connection.execute(
        """SELECT paper_id,node_type,question_id,answer_question_id
             FROM semantic_nodes WHERE id = ?""", (node_id,),
    ).fetchone()
    if row is None or row["node_type"] not in {"question", "answer"}:
        raise LookupError("answer node not found")
    question_id = row["question_id"] or row["answer_question_id"]
    answer_row = connection.execute(
        """SELECT value,solution,explanation,commentary,knowledge,status,
                  source_document_id,source_question_ids_json,source_blocks_json,source_pages_json
             FROM answers WHERE question_id = ?""", (question_id,),
    ).fetchone()
    if answer_row is None:
        raise LookupError("answer not found")
    paper, nodes = _semantic_tree(connection, row["paper_id"], include_answers=True)
    node = nodes[node_id]
    answer_nodes = ([node] if node["type"] == "answer" else
                    [child for child in node["children"] if child["type"] == "answer"])
    correct = []
    if answer_row["status"] == "explicit":
        correct = [option[0] for option in connection.execute(
            "SELECT id FROM options WHERE question_id = ? AND is_correct = 1 ORDER BY default_position",
            (question_id,),
        )]
    score_row = connection.execute(
        "SELECT scoreable,reason FROM scoreability WHERE question_id = ?", (question_id,),
    ).fetchone()
    return {
        "paper": paper, "nodeId": node_id, "questionId": question_id,
        "answerNodes": answer_nodes,
        "scoreability": ({"scoreable": bool(score_row["scoreable"]),
                          "reason": score_row["reason"]} if score_row else None),
        "answer": {"status": answer_row["status"], "value": answer_row["value"],
                   "solution": answer_row["solution"], "explanation": answer_row["explanation"],
                   "commentary": answer_row["commentary"], "knowledge": answer_row["knowledge"],
                   "correctOptionIds": correct,
                   "sourceDocumentId": answer_row["source_document_id"],
                   "sourceQuestionIds": json.loads(answer_row["source_question_ids_json"] or "[]"),
                   "sourceBlocks": json.loads(answer_row["source_blocks_json"] or "[]"),
                   "sourcePages": json.loads(answer_row["source_pages_json"] or "[]")},
    }
