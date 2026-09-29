"""Build the versioned SQLite question bank from the structured exam export.

The JSON files remain the source of truth. A failed validation never replaces an
existing database; a successful build is published with one atomic rename.
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
import hashlib
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import tempfile

from bs4 import BeautifulSoup


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STRUCTURED_DIR = REPO_ROOT / "data/sources/exam-library/structured"
DEFAULT_OUTPUT = REPO_ROOT / "data/question-bank.sqlite3"
SCHEMA_PATH = Path(__file__).with_name("question_bank_schema.sql")
SCHEMA_VERSION = "question-bank.sqlite.v2"
SEMANTIC_SCHEMA_VERSION = "question-bank.semantic.v3"
PAPER_SCHEMA = "exam-paper.v1"
CHOICE_TYPES = frozenset(("single_choice", "multiple_choice"))
OPTION_LABEL = re.compile(r"^([A-H])\.$")
ANSWER_SEPARATORS = re.compile(r"[\s,，、/&+;；()（）\[\]【】]+")
FORM_HEADING = re.compile(r"试卷\s*(IV|V)(?![A-Za-z])", re.IGNORECASE)
REFERENCE = re.compile(
    r"同试卷\s*(IV|V)\s*第([一二三四五六七八九十]+)"
    r"(?:[、，,]\s*[（(]([0-9]+)[）)])?\s*题",
    re.IGNORECASE,
)
CHOICE_LABEL = re.compile(r"(?<!\S)([A-O])\.\s+")
PARAGRAPH_LABEL = re.compile(r"^\s*([A-L])\)\s*(.+)", re.DOTALL)


@dataclass(frozen=True)
class BuildStats:
    papers: int
    question_records: int
    bank_questions: int
    source_blocks: int
    options: int
    marked_questions: int


class _ParagraphGroupParser(HTMLParser):
    """Extract paragraphs only from an explicit paragraph-group container."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.group_depth: int | None = None
        self.paragraph_depth: int | None = None
        self.parts: list[str] = []
        self.paragraphs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"br", "hr", "img", "input", "meta", "link", "wbr"}:
            if tag == "br" and self.paragraph_depth is not None:
                self.parts.append("\n")
            return
        self.depth += 1
        classes = dict(attrs).get("class") or ""
        if self.group_depth is None and "paragraph-group" in classes.split():
            self.group_depth = self.depth
        elif self.group_depth is not None and tag == "p" and self.paragraph_depth is None:
            self.paragraph_depth = self.depth
            self.parts = []

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"br", "hr", "img", "input", "meta", "link", "wbr"}:
            self.handle_starttag(tag, attrs)
        else:
            self.handle_starttag(tag, attrs)
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag == "p" and self.paragraph_depth == self.depth:
            self.paragraphs.append("".join(self.parts).strip())
            self.paragraph_depth = None
            self.parts = []
        if self.group_depth == self.depth:
            self.group_depth = None
        self.depth = max(self.depth - 1, 0)

    def handle_data(self, data: str) -> None:
        if self.paragraph_depth is not None:
            self.parts.append(data)


def _block_units(block: dict) -> list[tuple[str, str | None, str | None]]:
    presentation = block.get("presentation") or {}
    if presentation.get("answerNote") and isinstance(presentation.get("displayText"), str):
        # The raw source block may mix question material with a printed hint.
        # Preserve source paragraph classes only when clipping the printed
        # hint reproduces the builder's independently checked displayText.
        display = presentation["displayText"]
        safe_html = None
        markup = BeautifulSoup(block.get("contentHtml") or "", "html.parser")
        group = markup.select_one(".paragraph-group")
        marker = presentation["answerNote"].get("sourceMarker")
        if group is not None and marker and display:
            paragraphs = group.find_all("p", recursive=False)
            boundary = next((index for index, paragraph in enumerate(paragraphs)
                             if paragraph.get_text(" ", strip=True) == marker), None)
            if boundary is not None:
                for paragraph in paragraphs[boundary:]:
                    paragraph.decompose()
                compact = lambda value: re.sub(r"\s+", "", value or "")
                if compact(group.get_text(" ", strip=True)) == compact(display):
                    safe_html = str(group)
        # The unmodified source block remains in source_blocks for explicit
        # answer inspection, even when no safe rich fragment can be proven.
        return [("paragraph", display, safe_html)]
    html = block.get("contentHtml") or ""
    if "paragraph-group" in html:
        parser = _ParagraphGroupParser()
        parser.feed(html)
        # Keep a block whole if markup is incomplete or the group is unclear.
        if len(parser.paragraphs) > 1 and all(parser.paragraphs):
            return [("paragraph", paragraph, None) for paragraph in parser.paragraphs]
    role = block.get("role")
    if block.get("images") or role == "figure" or "<figure" in html or "<img" in html:
        unit_type = "figure"
    elif role == "tex_source" or "<pre" in html or "<code" in html:
        unit_type = "code"
    elif block.get("formulas") and not block.get("text"):
        unit_type = "formula"
    elif role == "question":
        unit_type = "instruction"
    elif role == "content":
        unit_type = "paragraph"
    else:
        unit_type = "other"
    return [(unit_type, block.get("text"), block.get("contentHtml"))]


def _record_input_hash(connection: sqlite3.Connection, root: Path,
                       path: Path, input_kind: str) -> None:
    data = path.read_bytes()
    connection.execute(
        "INSERT INTO input_hashes VALUES (?,?,?,?)",
        (path.relative_to(root).as_posix(), input_kind,
         hashlib.sha256(data).hexdigest(), len(data)),
    )


def _verify_input_hashes(connection: sqlite3.Connection, root: Path) -> None:
    for relative, expected_hash, expected_size in connection.execute(
        "SELECT relative_path,sha256,byte_length FROM input_hashes"
    ):
        path = _safe_input_path(root, relative)
        data = path.read_bytes()
        _require(len(data) == expected_size and hashlib.sha256(data).hexdigest() == expected_hash,
                 f"Input changed during database build: {relative}")


def _insert_semantics(connection: sqlite3.Connection, paper: dict) -> None:
    """Add evidence-backed hierarchy while retaining every unassigned source block."""
    paper_id = paper["id"]
    source_by_id = {block["id"]: block for block in paper["blocks"]}
    sibling_orders: Counter[str] = Counter()
    unit_orders: Counter[str] = Counter()
    node_serial = 0
    unit_serial = 0

    def node(kind: str, parent: str | None, title: str | None = None,
             question_id: str | None = None, option_id: str | None = None,
             answer_question_id: str | None = None,
             path: str | None = None) -> str:
        nonlocal node_serial
        node_serial += 1
        node_id = f"{paper_id}:node:{node_serial}"
        sibling_orders[parent or ""] += 1
        connection.execute(
            """INSERT INTO semantic_nodes
               (id,paper_id,parent_id,node_type,ordinal,title,question_id,
                option_id,answer_question_id,source_json_path)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (node_id, paper_id, parent, kind, sibling_orders[parent or ""],
             title, question_id, option_id, answer_question_id, path),
        )
        return node_id

    def unit(owner: str, kind: str, value: str | None, html: str | None,
             block_id: str | None = None, path: str | None = None,
             source_hash: str | None = None) -> None:
        nonlocal unit_serial
        unit_serial += 1
        unit_id = f"{paper_id}:unit:{unit_serial}"
        unit_orders[owner] += 1
        connection.execute(
            "INSERT INTO content_units VALUES (?,?,?,?,?,?,?)",
            (unit_id, paper_id, owner, unit_orders[owner], kind, value, html),
        )
        connection.execute(
            "INSERT INTO unit_provenance VALUES (?,?,?,?,?)",
            (unit_id, paper_id, block_id, path,
             source_hash or hashlib.sha256(_json(value).encode("utf-8")).hexdigest()),
        )

    root = node("paper", None, paper.get("title"), path="$")
    block_indices = {block["id"]: index for index, block in enumerate(paper["blocks"])}
    for set_id, source_block_id in connection.execute(
        """SELECT id,source_block_id FROM choice_sets
           WHERE paper_id=? AND status='unresolved_source_labels'""", (paper_id,)
    ):
        local_block_id = source_block_id.removeprefix(f"{paper_id}:")
        connection.execute(
            "INSERT INTO quality_issues VALUES (?,?,?,?,?,?)",
            (f"{set_id}:issue", paper_id, root,
             "unresolved_choice_set_labels",
             "Printed choice labels are incomplete or ambiguous",
             f"$.blocks[{block_indices[local_block_id]}].text"),
        )
        connection.execute(
            "INSERT INTO quality_issue_source_spans VALUES (?,?)",
            (f"{set_id}:issue", source_block_id),
        )
    sections: dict[str, str] = {}
    toc_sections: dict[str, str] = {}
    toc_question_parents: dict[str, str] = {}
    for toc_index, entry in enumerate(paper.get("toc") or []):
        if entry.get("kind") == "section":
            parent_id = entry.get("parentId")
            _require(not parent_id or parent_id in toc_sections,
                     f"Unresolved TOC section parent: {paper_id}:{entry.get('id')}")
            toc_sections[entry["id"]] = node(
                "section", toc_sections.get(parent_id, root), entry.get("label"),
                path=f"$.toc[{toc_index}]")
        elif entry.get("kind") == "question" and entry.get("parentId") in toc_sections:
            toc_question_parents[entry["id"]] = toc_sections[entry["parentId"]]

    def section(title: str | None) -> str:
        label = (title or "").strip() or "Unassigned source material"
        if label not in sections:
            sections[label] = node("section", root, label)
        return sections[label]

    questions: dict[str, str] = {}
    question_sections: dict[str, str] = {}
    for index, question in enumerate(paper["questions"]):
        full_id = f"{paper_id}:{question['id']}"
        parent = toc_question_parents.get(question["id"]) or section(question.get("sectionTitle"))
        kind = "question" if question["recordType"] == "question" else "answer"
        question_node = node(kind, parent, question.get("number"), full_id,
                             answer_question_id=full_id if kind == "answer" else None,
                             path=f"$.questions[{index}]")
        questions[question["id"]] = question_node
        question_sections[question["id"]] = parent
        if question.get("stem"):
            unit(question_node, "instruction", question["stem"], None,
                 path=f"$.questions[{index}].stem")
        for subindex, subquestion in enumerate(question.get("subquestions") or []):
            subnode = node("subquestion", question_node, subquestion.get("number"),
                           path=f"$.questions[{index}].subquestions[{subindex}]")
            if subquestion.get("text"):
                unit(subnode, "instruction", subquestion["text"], None,
                     path=f"$.questions[{index}].subquestions[{subindex}].text")
        option_rows = connection.execute(
            "SELECT id,text FROM options WHERE question_id=? ORDER BY default_position",
            (full_id,),
        ).fetchall()
        for option_index, (option_id, text) in enumerate(option_rows):
            option_node = node("option", question_node, question["options"][option_index]["label"],
                               option_id=option_id,
                               path=f"$.questions[{index}].options[{option_index}]")
            unit(option_node, "paragraph", text, None,
                 path=f"$.questions[{index}].options[{option_index}].text")
        answer = question["answer"]
        answer_fields = ("value", "solution", "explanation", "commentary", "knowledge")
        if any(answer.get(field) for field in answer_fields):
            answer_node = node("answer", question_node, answer.get("status"),
                               answer_question_id=full_id,
                               path=f"$.questions[{index}].answer")
            for field in answer_fields:
                if answer.get(field):
                    unit(answer_node, "paragraph", answer[field], None,
                         path=f"$.questions[{index}].answer.{field}")
        if question["recordType"] == "question":
            marks = connection.execute(
                "SELECT COUNT(*),SUM(is_correct IS NOT NULL) FROM options WHERE question_id=?",
                (full_id,),
            ).fetchone()
            if question.get("status") != "complete" and not _is_numbered_cloze_slot(question):
                reason = "incomplete_question"
                connection.execute(
                    "INSERT INTO quality_issues VALUES (?,?,?,?,?,?)",
                    (f"{paper_id}:issue:{index}:partial", paper_id, question_node,
                     "incomplete_question", question.get("status"),
                     f"$.questions[{index}].status"),
                )
            elif answer["status"] != "explicit":
                reason = f"answer_{answer['status']}"
            elif marks[0] and marks[1] != marks[0]:
                reason = "unsafe_choice_mapping"
            elif marks[0]:
                reason = "marked_choice"
            else:
                reason = "manual_review_required"
            connection.execute("INSERT INTO scoreability VALUES (?,?,?)",
                               (full_id, int(reason == "marked_choice"), reason))
            if reason == "unsafe_choice_mapping":
                connection.execute(
                    "INSERT INTO quality_issues VALUES (?,?,?,?,?,?)",
                    (f"{paper_id}:issue:{index}:choice", paper_id, question_node,
                     "unsafe_choice_mapping", None,
                     f"$.questions[{index}].answer"),
                )
            labels = [option.get("label") for option in question["options"]]
            if len(labels) != len(set(labels)):
                connection.execute(
                    "INSERT INTO quality_issues VALUES (?,?,?,?,?,?)",
                    (f"{paper_id}:issue:{index}:labels", paper_id, question_node,
                     "duplicate_option_label", None,
                     f"$.questions[{index}].options"),
                )

    # One unit or a reliable paragraph split for every raw block. The source
    # block remains intact in v2 and is never silently assigned to a question.
    current_section: str | None = None
    for block in paper["blocks"]:
        if block.get("role") == "section" and block.get("text"):
            current_section = toc_sections.get(block["id"]) or section(block["text"])
        owner = questions.get(block.get("questionId"))
        if block.get("status") == "source_only" or owner is None:
            owner = current_section or section(None)
        full_block_id = f"{paper_id}:{block['id']}"
        block_hash = hashlib.sha256(_json(block).encode("utf-8")).hexdigest()
        for kind, value, html in _block_units(block):
            unit(owner, kind, value, html, block_id=full_block_id,
                 source_hash=block_hash)
        # Formula tokens are ordered semantic content even when embedded in a
        # larger question, paragraph, or option block.
        for formula in block.get("formulas") or []:
            unit(owner, "formula", formula, None, block_id=full_block_id,
                 source_hash=block_hash)
    if paper_id == "tem4:2022":
        for block_index, block in enumerate(paper["blocks"]):
            if block.get("role") in {"heading", "content"} and "补充卷说明" in (block.get("text") or ""):
                connection.execute(
                    "INSERT INTO quality_issues VALUES (?,?,?,?,?,?)",
                    (f"{paper_id}:issue:supplement-year", paper_id, root,
                     "unresolved_paper_year_conflict",
                     "Supplement heading prints a different year from the catalog paper",
                     f"$.blocks[{block_index}].text"),
                )
                connection.execute(
                    "INSERT INTO quality_issue_source_spans VALUES (?,?)",
                    (f"{paper_id}:issue:supplement-year", f"{paper_id}:{block['id']}"),
                )
                break

    contexts: dict[str, str] = {}
    for index, question in enumerate(paper["questions"]):
        question_node = questions[question["id"]]
        context = question.get("context") or {}
        if context.get("kind"):
            # blankNumber identifies this question's position in a shared
            # passage; every other context field must agree before sharing.
            context_key = _json((question_sections[question["id"]],
                                 {key: value for key, value in context.items()
                                  if key != "blankNumber"}))
            if context_key not in contexts:
                context_kind = "passage" if context["kind"] == "passage" else "material"
                material = node(context_kind, question_sections[question["id"]],
                                context["kind"], path=f"$.questions[{index}].context")
                contexts[context_key] = material
                if context.get("text"):
                    context_hash = hashlib.sha256(_json(context["text"]).encode("utf-8")).hexdigest()
                    if context.get("passageSourceBlocks"):
                        for block_id in context.get("instructionSourceBlocks") or []:
                            source = source_by_id[block_id]
                            unit(material, "instruction", source["text"], None,
                                 block_id=f"{paper_id}:{block_id}",
                                 source_hash=hashlib.sha256(_json(source).encode("utf-8")).hexdigest())
                        for block_id in context["passageSourceBlocks"]:
                            source = source_by_id[block_id]
                            unit(material, "paragraph", source["text"], None,
                                 block_id=f"{paper_id}:{block_id}",
                                 source_hash=hashlib.sha256(_json(source).encode("utf-8")).hexdigest())
                    else:
                        paragraphs = re.split(r"\n\s*\n", context["text"])
                        for paragraph in paragraphs:
                            if paragraph.strip():
                                unit(material, "paragraph", paragraph.strip(), None,
                                     path=f"$.questions[{index}].context.text",
                                     source_hash=context_hash)
            connection.execute(
                "INSERT INTO semantic_links VALUES (?,?,?,?,?)",
                (question_node, contexts[context_key], "shared_context", 1,
                 f"$.questions[{index}].context"),
            )
        for continuation_index, continuation in enumerate(question.get("continuations") or []):
            material = node("material", question_sections[question["id"]],
                            continuation.get("sourceMarker") or "Continuation",
                            path=f"$.questions[{index}].continuations[{continuation_index}]")
            if continuation.get("sourceMarker"):
                unit(material, "instruction", continuation["sourceMarker"], None,
                     path=f"$.questions[{index}].continuations[{continuation_index}].sourceMarker")
            connection.execute(
                "INSERT INTO semantic_links VALUES (?,?,?,?,?)",
                (question_node, material, "continuation", continuation_index + 1,
                 f"$.questions[{index}].continuations[{continuation_index}]"),
            )


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _read_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    _require(isinstance(value, dict), f"Expected JSON object: {path}")
    return value


def _safe_input_path(root: Path, relative: str) -> Path:
    _require(isinstance(relative, str) and relative, "Missing paper JSON path")
    path = (root / relative).resolve()
    _require(path.is_relative_to(root.resolve()), f"Paper JSON escapes structured directory: {relative}")
    _require(path.is_file(), f"Missing paper JSON: {path}")
    return path


def _load_bank(root: Path) -> dict[str, dict]:
    bank_path = root / "question-bank.jsonl"
    bank: dict[str, dict] = {}
    with bank_path.open(encoding="utf-8") as handle:
        for number, line in enumerate(handle, 1):
            _require(bool(line.strip()), f"Empty JSONL line {number}")
            row = json.loads(line)
            _require(isinstance(row, dict), f"Invalid JSONL object on line {number}")
            question_id = row.get("id")
            _require(isinstance(question_id, str) and question_id, f"Missing JSONL id on line {number}")
            _require(question_id not in bank, f"Duplicate JSONL question id: {question_id}")
            bank[question_id] = row
    return bank


def _is_numbered_cloze_slot(question: dict) -> bool:
    context = question.get("context") or {}
    # Cloze blanks legitimately have no standalone stem: their numbered slot
    # lives in the shared passage. The parser marks those records partial, but
    # a matching blank number and complete printed options still identify the
    # selected choice unambiguously.
    return (question.get("status") == "partial" and
            context.get("kind") == "passage" and
            str(context.get("blankNumber")) == str(question.get("number")) and
            not (question.get("stem") or "").strip())


def _choice_letters(question: dict, labels: list[str]) -> set[str] | None:
    answer = question["answer"]
    context = question.get("context") or {}
    cloze_without_stem = _is_numbered_cloze_slot(question)
    matching_bank = context.get("kind") in {"matching_table", "matching_comments", "ordering_diagram"}
    if context.get("kind") == "ordering_diagram":
        full = "ABCDEFGH" if "H" in context.get("fixedLetters", []) else "ABCDEFG"
        valid_labels = [letter for letter in full if letter not in context["fixedLetters"]]
        # The 2010 diagram has one extra paragraph as a distractor; the
        # other four diagrams offer exactly five unplaced paragraphs.
        if len(valid_labels) not in {5, 6}:
            return None
        valid_labels = (valid_labels,)
    elif matching_bank:
        valid_labels = (list("ABCDEFG"),)
    else:
        valid_labels = (list("ABCD"), list("ABCDE"))
    if (question.get("questionType") not in CHOICE_TYPES
            or not (question.get("status") == "complete" or cloze_without_stem)
            or labels not in valid_labels
            or answer.get("status") != "explicit"):
        return None
    value = answer.get("value")
    if not isinstance(value, str) or not value.strip():
        return None
    letters = ANSWER_SEPARATORS.sub("", value.strip())
    if not letters or re.fullmatch(r"[A-H]+" if matching_bank else r"[A-E]+", letters) is None:
        return None
    selected = set(letters)
    if len(selected) != len(letters) or not selected.issubset(set(labels)):
        return None
    if question["questionType"] == "single_choice" and len(selected) != 1:
        return None
    if question["questionType"] == "multiple_choice" and len(selected) < 2:
        return None
    return selected


def _validate_bank_row(row: dict, paper: dict, question: dict, full_id: str) -> None:
    expected = {
        "id": full_id,
        "paperId": paper["id"],
        "category": paper["category"],
        "year": paper.get("year"),
        "template": paper.get("template"),
        "number": question["number"],
        "questionType": question["questionType"],
        "sectionTitle": question["sectionTitle"],
        "stem": question["stem"],
        "context": question["context"],
        **({"labels": question["labels"]} if "labels" in question else {}),
        "options": question["options"],
        "answer": question["answer"],
        "sourcePages": question["sourcePages"],
        "sourceBlocks": question["sourceBlocks"],
        "status": question["status"],
    }
    _require(row == expected, f"JSONL and paper JSON differ for {full_id}")


def _check_audit_count(actual: int, expected: object, label: str) -> None:
    _require(type(expected) is int and actual == expected, f"{label}: expected {expected}, found {actual}")


def _validate_paper(paper: dict, document: dict, path: Path) -> None:
    _require(paper.get("schema") == PAPER_SCHEMA, f"Unexpected schema in {path}")
    for key in ("id", "category", "kind", "title", "template"):
        _require(paper.get(key) == document.get(key), f"{path}: {key} disagrees with audit")
    _require(isinstance(paper.get("source"), dict), f"{path}: missing source paths")
    _require(isinstance(paper.get("questions"), list), f"{path}: questions must be a list")
    _require(isinstance(paper.get("blocks"), list), f"{path}: blocks must be a list")
    _check_audit_count(sum(paper["kind"] != "questions" or q.get("recordType") == "question"
                           for q in paper["questions"]),
                       document.get("questions"), f"{path}: question records")
    _check_audit_count(len(paper["blocks"]), document.get("sourceBlocks"), f"{path}: source blocks")
    _check_audit_count(sum(q.get("status") == "partial" for q in paper["questions"]), document.get("partialQuestions"), f"{path}: partial questions")
    _check_audit_count(sum(b.get("status") == "source_only" for b in paper["blocks"]), document.get("sourceOnlyBlocks"), f"{path}: source-only blocks")


def _insert_question(connection: sqlite3.Connection, paper: dict, question: dict, ordinal: int, in_bank: bool) -> tuple[int, int]:
    paper_id = paper["id"]
    local_id = question["id"]
    question_id = f"{paper_id}:{local_id}"
    answer = question["answer"]
    _require(isinstance(answer, dict), f"Missing answer object: {question_id}")
    _require(answer.get("status") in ("explicit", "ambiguous", "missing"), f"Invalid answer status: {question_id}")
    context = question.get("context")
    _require(context is None or isinstance(context, dict), f"Invalid context: {question_id}")
    connection.execute(
        """INSERT INTO questions
           (id,paper_id,local_id,ordinal,number,question_type,record_type,
            section_kind,section_title,stem,status,context_json,source_pages_json,
            subquestions_json,continuations_json,in_bank,raw_json)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (question_id, paper_id, local_id, ordinal, question.get("number"),
         question.get("questionType"), question["recordType"], question.get("sectionKind"),
         question.get("sectionTitle"), question.get("stem"), question.get("status"),
         _json(context) if context is not None else None, _json(question["sourcePages"]),
         _json(question["subquestions"]) if "subquestions" in question else None,
         _json(question["continuations"]) if "continuations" in question else None,
         int(in_bank), _json(question)),
    )
    source_document_id = answer.get("sourceDocumentId")
    connection.execute(
        """INSERT INTO answers
           (question_id,value,solution,explanation,commentary,knowledge,status,
            source_document_id,source_question_ids_json,source_blocks_json,
            source_pages_json,ambiguity_reason,raw_json)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (question_id, answer.get("value"), answer.get("solution"),
         answer.get("explanation"), answer.get("commentary"), answer.get("knowledge"),
         answer["status"], source_document_id, _json(answer["sourceQuestionIds"]),
         _json(answer["sourceBlocks"]), _json(answer["sourcePages"]),
         answer.get("ambiguityReason"), _json(answer)),
    )
    options = question["options"]
    _require(isinstance(options, list), f"Invalid options: {question_id}")
    labels: list[str] = []
    positions: set[int] = set()
    for option in options:
        _require(isinstance(option, dict), f"Invalid option: {question_id}")
        match = OPTION_LABEL.fullmatch(option.get("label", ""))
        _require(match is not None, f"Invalid option label: {question_id}")
        labels.append(match.group(1))
    # A few printed papers repeat a label (for example A/B/C/C). Preserve
    # every source option and its position; an ambiguous sequence is never
    # eligible for automatic marking in _choice_letters.
    correct = _choice_letters(question, labels)
    for position, option in enumerate(options, 1):
        source_position = option.get("sourceOrder", position)
        _require(type(source_position) is int and source_position >= 0,
                 f"Invalid sourceOrder: {question_id}")
        _require(source_position not in positions, f"Duplicate sourceOrder: {question_id}")
        positions.add(source_position)
        letter = labels[position - 1]
        connection.execute(
            """INSERT INTO options
               (id,question_id,label,source_label,text,default_position,
                source_position,is_correct,raw_json)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (f"{question_id}:{letter}" + (f":{position}" if labels.count(letter) > 1 else ""),
             question_id, option["label"],
             option.get("sourceLabel"), option["text"], position,
             source_position, int(letter in correct) if correct is not None else None,
             _json(option)),
        )
    return len(options), int(correct is not None)


def _insert_blocks(connection: sqlite3.Connection, paper: dict) -> None:
    paper_id = paper["id"]
    for ordinal, block in enumerate(paper["blocks"], 1):
        local_id = block["id"]
        assigned_question = block.get("questionId")
        connection.execute(
            """INSERT INTO source_blocks
               (id,paper_id,local_id,ordinal,page,source_page_index,
                source_block_index,role,text,content_html,formulas_json,
                images_json,status,question_id,raw_json)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (f"{paper_id}:{local_id}", paper_id, local_id, ordinal,
             block.get("page"), block.get("sourcePageIndex"),
             block.get("sourceBlockIndex"), block.get("role"), block.get("text"),
             block.get("contentHtml"), _json(block["formulas"]),
             _json(block["images"]), block.get("status"),
             f"{paper_id}:{assigned_question}" if assigned_question else None,
             _json(block)),
        )
        connection.execute(
            "INSERT INTO source_spans VALUES (?,?,?,?,?,?,?)",
            (f"{paper_id}:{local_id}", paper_id, block.get("page"),
             block.get("sourcePageIndex"), block.get("sourceBlockIndex"),
             f"$.blocks[{ordinal - 1}]", "block"),
        )


def _insert_paper_forms(connection: sqlite3.Connection, paper: dict) -> None:
    paper_id = paper["id"]
    blocks = paper["blocks"]
    block_order = {block["id"]: index for index, block in enumerate(blocks)}
    boundaries: list[tuple[int, str, dict | None, str, int | None]] = []
    if (paper["category"] == "math3" and paper["kind"] in {"questions", "answers"}
            and isinstance(paper.get("year"), int) and 1987 <= paper["year"] <= 1996):
        seen_forms: set[str] = set()
        for index, block in enumerate(blocks):
            if block.get("role") != "heading":
                continue
            match = FORM_HEADING.search(block.get("text") or "")
            if match:
                label = match.group(1).upper()
                if label not in seen_forms:
                    boundaries.append((index, label, block, "explicit", paper["year"]))
                    seen_forms.add(label)
        _require(seen_forms == {"IV", "V"}, f"Expected printed IV/V forms: {paper_id}")
    elif paper_id == "tem4:2022":
        boundaries.append((0, "main", None, "default", paper.get("year")))
        for index, block in enumerate(blocks):
            text_value = block.get("text") or ""
            if block.get("role") in {"heading", "content"} and "补充卷说明" in text_value:
                match = re.search(r"20\d{2}", text_value)
                printed_year = int(match.group()) if match else None
                boundaries.append((index, "supplement", block,
                                   "unresolved_year_conflict", printed_year))
                break
    else:
        boundaries.append((0, "main", None, "default", paper.get("year")))

    for ordinal, (_, label, block, status, printed_year) in enumerate(boundaries, 1):
        connection.execute(
            "INSERT INTO paper_forms VALUES (?,?,?,?,?,?,?,?)",
            (f"{paper_id}:form:{label}", paper_id, ordinal, label, status,
             printed_year, f"{paper_id}:{block['id']}" if block else None,
             block.get("text") if block else None),
        )
    for question in paper["questions"]:
        question_id = f"{paper_id}:{question['id']}"
        available = [block_order[local_id] for local_id in question["sourceBlocks"]
                     if local_id in block_order]
        first = min(available) if available else None
        chosen = boundaries[0]
        if first is not None:
            for boundary in boundaries:
                if boundary[0] <= first:
                    chosen = boundary
        label = chosen[1]
        connection.execute(
            "INSERT INTO question_paper_forms VALUES (?,?,?,?)",
            (question_id, f"{paper_id}:form:{label}",
             f"{paper_id}:{question['sourceBlocks'][0]}" if question["sourceBlocks"] else None,
             "explicit_boundary" if first is not None and chosen[3] != "default" else "default"),
        )


def _insert_choice_sets(connection: sqlite3.Connection, paper: dict) -> None:
    if paper["category"] not in {"cet4", "cet6"} or paper["kind"] != "questions":
        return
    paper_id = paper["id"]
    form_id = f"{paper_id}:form:main"
    word_bank: tuple[dict, list[tuple[str, str]], str] | None = None
    paragraph_bank: list[tuple[dict, str, str]] = []
    for block in paper["blocks"]:
        content = block.get("text") or ""
        if block.get("role") == "choices":
            matches = list(CHOICE_LABEL.finditer(content))
            labels = [match.group(1) for match in matches]
            if labels == list("ABCDEFGHIJKLMNO"):
                options = [(match.group(1), content[match.end():matches[index + 1].start()
                                                       if index + 1 < len(matches) else len(content)].strip())
                           for index, match in enumerate(matches)]
                if all(text_value for _, text_value in options):
                    word_bank = (block, options, "explicit")
            elif (len(labels) >= 10 and len(labels) == len(set(labels))
                  and labels[0] == "A" and word_bank is None):
                # Keep a damaged or incomplete printed bank visible, but do
                # not invent an O label or expose polluted option text.
                word_bank = (block, [], "unresolved_source_labels")
        elif block.get("role") == "content":
            match = PARAGRAPH_LABEL.match(content)
            if match and len(match.group(2).strip()) >= 20:
                paragraph_bank.append((block, match.group(1), match.group(2).strip()))

    def save_set(kind: str, source_block: dict, options: list[tuple[dict, str, str]],
                 status: str, raw_text: str) -> None:
        set_id = f"{paper_id}:choices:{kind}"
        connection.execute(
            "INSERT INTO choice_sets VALUES (?,?,?,?,?,?,?)",
            (set_id, paper_id, form_id, kind, status,
             f"{paper_id}:{source_block['id']}", raw_text),
        )
        for position, (block, label, text_value) in enumerate(options, 1):
            connection.execute(
                "INSERT INTO choice_set_options VALUES (?,?,?,?,?,?)",
                (f"{set_id}:{label}", set_id, label, position, text_value,
                 f"{paper_id}:{block['id']}"),
            )
        block_positions = {block["id"]: index for index, block in enumerate(paper["blocks"])}
        final_bank_position = max(block_positions[block["id"]] for block, _, _ in options) if options else block_positions[source_block["id"]]
        linked_paragraph_questions = 0
        for question in paper["questions"]:
            if question.get("recordType") != "question":
                continue
            if kind == "word_bank":
                # Older CET papers number this section 36–45; newer ones use
                # 26–35. The source context, not a year-specific number, owns it.
                linked = (question.get("sectionTitle") == "Section A"
                          and source_block["id"] in (question.get("context") or {}).get("sourceBlocks", []))
            else:
                first_position = min((block_positions[block_id] for block_id in question.get("sourceBlocks", [])
                                      if block_id in block_positions), default=-1)
                linked = (question.get("sectionTitle") == "Section B"
                          and question.get("questionType") == "free_response"
                          and first_position > final_bank_position
                          and linked_paragraph_questions < 10)
            if linked:
                connection.execute("INSERT INTO question_choice_sets VALUES (?,?)",
                                   (f"{paper_id}:{question['id']}", set_id))
                if kind == "paragraph_bank":
                    linked_paragraph_questions += 1

    if word_bank:
        block, parsed, status = word_bank
        save_set("word_bank", block, [(block, label, text_value)
                                      for label, text_value in parsed],
                 status, block.get("text") or "")
    paragraph_labels = [label for _, label, _ in paragraph_bank]
    if len(paragraph_labels) >= 8 and paragraph_labels == list("ABCDEFGHIJKL"[:len(paragraph_labels)]):
        save_set("paragraph_bank", paragraph_bank[0][0], paragraph_bank,
                 "explicit", "\n\n".join(block.get("text") or ""
                                          for block, _, _ in paragraph_bank))
    elif len(paragraph_bank) >= 8:
        save_set("paragraph_bank", paragraph_bank[0][0], [],
                 "unresolved_source_labels",
                 "\n\n".join(block.get("text") or "" for block, _, _ in paragraph_bank))


def _chinese_number(value: str) -> int | None:
    digits = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
              "六": 6, "七": 7, "八": 8, "九": 9}
    if value in digits:
        return digits[value]
    if value == "十":
        return 10
    if "十" in value:
        left, right = value.split("十", 1)
        if (not left or left in digits) and (not right or right in digits):
            return (digits.get(left, 1) * 10) + digits.get(right, 0)
    return None


def _insert_answer_references(connection: sqlite3.Connection) -> None:
    rows = connection.execute(
        """SELECT q.id,q.paper_id,q.ordinal,p.year,a.raw_json FROM questions q
           JOIN papers p ON p.id=q.paper_id JOIN answers a ON a.question_id=q.id
           WHERE p.category='math3'"""
    ).fetchall()
    for question_id, paper_id, question_ordinal, year, raw_answer in rows:
        answer = json.loads(raw_answer)
        explicit_references = answer.get("references") or []
        if explicit_references:
            for ordinal, reference in enumerate(explicit_references, 1):
                field = reference.get("sourceField") or "solution"
                target_paper = reference.get("targetPaperId") or paper_id
                local_target = reference.get("targetQuestionId")
                target_id = f"{target_paper}:{local_target}" if local_target else None
                status = reference.get("resolutionStatus", "unresolved")
                _require(status in {"resolved", "unresolved", "ambiguous"},
                         f"Invalid answer reference status: {question_id}")
                if target_id:
                    _require(connection.execute("SELECT 1 FROM questions WHERE id=?", (target_id,)).fetchone(),
                             f"Missing answer reference target: {target_id}")
                source_path = f"$.questions[{question_ordinal - 1}].answer.references[{ordinal - 1}]"
                reference_id = f"{question_id}:reference:{field}:{ordinal}"
                reason = reference.get("unresolvedReason")
                connection.execute(
                    """INSERT INTO answer_references VALUES
                       (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (reference_id, question_id, field, ordinal,
                     reference.get("originalAnswerText") or reference["printedText"],
                     year, reference.get("targetForm"), reference.get("targetSection"),
                     reference.get("targetNumber"), target_id, status, reason, source_path),
                )
                if status != "resolved":
                    semantic_node = connection.execute(
                        "SELECT id FROM semantic_nodes WHERE question_id=? AND node_type='question'",
                        (question_id,),
                    ).fetchone()
                    if semantic_node:
                        connection.execute(
                            "INSERT INTO quality_issues VALUES (?,?,?,?,?,?)",
                            (f"{reference_id}:issue", paper_id, semantic_node[0],
                             "unresolved_answer_reference", reason, source_path),
                        )
            continue
        for field in ("value", "solution", "explanation", "commentary", "knowledge"):
            value = answer.get(field)
            if not isinstance(value, str) or "同试卷" not in value:
                continue
            for ordinal, match in enumerate(REFERENCE.finditer(value), 1):
                target_form = match.group(1).upper()
                target_section = match.group(2)
                section_number = _chinese_number(target_section)
                target_number = match.group(3) or (str(section_number) if section_number else None)
                candidates = connection.execute(
                    """SELECT q.id,q.section_title FROM questions q
                       JOIN papers p ON p.id=q.paper_id
                       JOIN question_paper_forms qf ON qf.question_id=q.id
                       JOIN paper_forms f ON f.id=qf.form_id
                       WHERE p.category='math3' AND p.kind='questions' AND p.year=?
                       AND f.label=? AND q.in_bank=1 AND q.number=?""",
                    (year, target_form, target_number),
                ).fetchall()
                if match.group(3):
                    prefix = f"{target_section}、"
                    candidates = [row for row in candidates
                                  if (row[1] or "").startswith(prefix)]
                else:
                    candidates = [row for row in candidates if not (row[1] or "").strip()]
                if len(candidates) == 1:
                    status, target_id, reason = "resolved", candidates[0][0], None
                elif candidates:
                    status, target_id, reason = "ambiguous", None, "multiple_matching_targets"
                else:
                    status, target_id, reason = "unresolved", None, "no_unique_target"
                reference_id = f"{question_id}:reference:{field}:{ordinal}"
                source_path = f"$.questions[{question_ordinal - 1}].answer.{field}"
                connection.execute(
                    """INSERT INTO answer_references VALUES
                       (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (reference_id, question_id, field, ordinal, match.group(0),
                     year, target_form, target_section, target_number, target_id,
                     status, reason, source_path),
                )
                if status != "resolved":
                    semantic_node = connection.execute(
                        "SELECT id FROM semantic_nodes WHERE question_id=? AND node_type='question'",
                        (question_id,),
                    ).fetchone()
                    if semantic_node:
                        connection.execute(
                            "INSERT INTO quality_issues VALUES (?,?,?,?,?,?)",
                            (f"{reference_id}:issue", paper_id, semantic_node[0],
                             "unresolved_answer_reference", reason, source_path),
                        )


def _insert_block_links(connection: sqlite3.Connection, paper: dict) -> None:
    paper_id = paper["id"]
    for question in paper["questions"]:
        question_id = f"{paper_id}:{question['id']}"
        for table, blocks in (
            ("question_source_blocks", question["sourceBlocks"]),
            ("context_source_blocks", (question.get("context") or {}).get("sourceBlocks", [])),
        ):
            _require(isinstance(blocks, list), f"Invalid {table}: {question_id}")
            for ordinal, local_id in enumerate(blocks, 1):
                connection.execute(
                    f"INSERT INTO {table} (question_id,block_id,ordinal) VALUES (?,?,?)",
                    (question_id, f"{paper_id}:{local_id}", ordinal),
                )


def _insert_labels(connection: sqlite3.Connection, paper: dict) -> None:
    """Index printed section groups without copying answer-choice labels."""
    paper_id = paper["id"]
    seen: dict[str, tuple[str, str, str, str]] = {}
    for question in paper["questions"]:
        question_id = f"{paper_id}:{question['id']}"
        labels = question.get("labels") or []
        _require(isinstance(labels, list), f"Invalid labels: {question_id}")
        for ordinal, label in enumerate(labels, 1):
            _require(isinstance(label, dict), f"Invalid label: {question_id}")
            label_id = label.get("id")
            block_id = label.get("sourceBlockId")
            values = (label.get("kind"), label.get("text"),
                      label.get("sourceTitle"), block_id)
            _require(isinstance(label_id, str) and
                     label_id == f"{paper_id}:group:{str(block_id).removeprefix(f'{paper_id}:')}",
                     f"Invalid label id: {question_id}")
            _require(all(isinstance(value, str) and value for value in values),
                     f"Incomplete label: {question_id}")
            source = connection.execute(
                "SELECT role FROM source_blocks WHERE id=? AND paper_id=?", (block_id, paper_id)
            ).fetchone()
            _require(source is not None and source[0] == "section",
                     f"Label lacks printed section provenance: {question_id}")
            _require(label_id not in seen or seen[label_id] == values,
                     f"Conflicting shared label: {label_id}")
            if label_id not in seen:
                connection.execute(
                    "INSERT INTO labels VALUES (?,?,?,?,?,?)",
                    (label_id, paper_id, *values),
                )
                seen[label_id] = values
            connection.execute(
                "INSERT INTO question_labels VALUES (?,?,?)",
                (question_id, label_id, ordinal),
            )


def _verify_database(connection: sqlite3.Connection, audit: dict, stats: BuildStats) -> None:
    fk = connection.execute("PRAGMA foreign_key_check").fetchall()
    _require(not fk, f"Foreign key violations: {fk[:3]}")
    integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
    _require(integrity == "ok", f"SQLite integrity check failed: {integrity}")
    for table, expected in (("papers", stats.papers), ("questions", stats.question_records),
                            ("source_blocks", stats.source_blocks), ("options", stats.options),
                            ("answers", stats.question_records)):
        actual = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        _check_audit_count(actual, expected, f"database {table}")
    bank_count = connection.execute("SELECT COUNT(*) FROM questions WHERE in_bank=1").fetchone()[0]
    _check_audit_count(bank_count, audit["bank"]["questions"], "database bank questions")
    bad_papers = connection.execute(
        """SELECT p.id FROM papers p LEFT JOIN questions q ON q.paper_id=p.id
           GROUP BY p.id HAVING p.record_count<>COUNT(q.id)
           OR p.question_count<>SUM(CASE WHEN q.in_bank=1 THEN 1 ELSE 0 END)"""
    ).fetchall()
    _require(not bad_papers, f"Per-paper counts disagree: {bad_papers[:3]}")
    bad_options = connection.execute(
        """SELECT q.id FROM questions q JOIN options o ON o.question_id=q.id
           GROUP BY q.id HAVING MIN(o.default_position)<>1
           OR MAX(o.default_position)<>COUNT(*)
           OR COUNT(DISTINCT o.source_position)<>COUNT(*)"""
    ).fetchall()
    _require(not bad_options, f"Option order invalid: {bad_options[:3]}")
    bad_marks = connection.execute(
        """SELECT q.id FROM questions q JOIN answers a ON a.question_id=q.id
           JOIN options o ON o.question_id=q.id GROUP BY q.id
           HAVING (a.status<>'explicit' OR q.question_type NOT IN ('single_choice','multiple_choice'))
           AND SUM(o.is_correct IS NOT NULL)>0"""
    ).fetchall()
    _require(not bad_marks, f"Unsupported answer marked correct: {bad_marks[:3]}")
    unrepresented = connection.execute(
        """SELECT b.id FROM source_blocks b LEFT JOIN unit_provenance p
           ON p.source_block_id=b.id WHERE p.source_block_id IS NULL LIMIT 3"""
    ).fetchall()
    _require(not unrepresented, f"Source blocks missing semantic provenance: {unrepresented}")
    represented = connection.execute(
        "SELECT COUNT(DISTINCT source_block_id) FROM unit_provenance WHERE source_block_id IS NOT NULL"
    ).fetchone()[0]
    _check_audit_count(represented, stats.source_blocks, "semantic source block conservation")
    scoreable = connection.execute(
        "SELECT COUNT(*) FROM scoreability WHERE scoreable=1"
    ).fetchone()[0]
    _check_audit_count(scoreable, stats.marked_questions, "scoreable marked choices")
    score_rows = connection.execute("SELECT COUNT(*) FROM scoreability").fetchone()[0]
    _check_audit_count(score_rows, stats.bank_questions, "scoreability questions")
    _check_audit_count(connection.execute("SELECT COUNT(*) FROM source_spans").fetchone()[0],
                       stats.source_blocks, "source spans")
    _check_audit_count(connection.execute("SELECT COUNT(*) FROM question_paper_forms").fetchone()[0],
                       stats.question_records, "question form membership")


def build_database(structured_dir: Path = DEFAULT_STRUCTURED_DIR,
                   output_path: Path | None = None) -> BuildStats:
    """Validate every input and atomically publish a complete SQLite database."""
    root = Path(structured_dir).resolve()
    output = Path(output_path or DEFAULT_OUTPUT).resolve()
    audit = _read_json(root / "audit.json")
    _require(audit.get("schema") == PAPER_SCHEMA, "Unexpected audit schema")
    documents = audit.get("documents")
    _require(isinstance(documents, list), "Audit documents must be a list")
    bank = _load_bank(root)
    _check_audit_count(len(documents), audit.get("papers"), "audit papers")
    _check_audit_count(len(bank), audit["bank"].get("questions"), "JSONL questions")
    _require(len({d["id"] for d in documents}) == len(documents), "Duplicate audit paper id")
    _require(len({d["json"] for d in documents}) == len(documents), "Duplicate audit JSON path")
    document_ids = {d["id"] for d in documents}
    bank_per_paper = Counter(row.get("paperId") for row in bank.values())
    _require(set(bank_per_paper).issubset(document_ids), "JSONL refers to unknown paper")

    output.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    connection: sqlite3.Connection | None = None
    try:
        with tempfile.NamedTemporaryFile(prefix=f".{output.name}.", suffix=".tmp",
                                         dir=output.parent, delete=False) as temp:
            temp_path = Path(temp.name)
        connection = sqlite3.connect(temp_path)
        connection.execute("PRAGMA foreign_keys=ON")
        connection.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        connection.execute("INSERT INTO meta(key,value) VALUES (?,?)", ("schema_version", SCHEMA_VERSION))
        connection.execute("INSERT INTO meta(key,value) VALUES (?,?)",
                           ("semantic_schema_version", SEMANTIC_SCHEMA_VERSION))
        connection.execute("INSERT INTO meta(key,value) VALUES (?,?)", ("source_schema", PAPER_SCHEMA))
        _record_input_hash(connection, root, root / "audit.json", "audit")
        _record_input_hash(connection, root, root / "question-bank.jsonl", "bank")

        categories = Counter()
        totals = Counter()
        for ordinal, document in enumerate(documents, 1):
            path = _safe_input_path(root, document["json"])
            _record_input_hash(connection, root, path, "paper")
            paper = _read_json(path)
            _validate_paper(paper, document, path)
            source = paper["source"]
            connection.execute(
                """INSERT INTO papers
                   (id,ordinal,category,category_label,kind,title,year,template,
                    json_path,reader_path,source_original,source_reflow,pages,
                    question_count,record_count,block_count,raw_json)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (paper["id"], ordinal, paper["category"], paper.get("categoryLabel"),
                 paper["kind"], paper["title"], paper.get("year"), paper.get("template"),
                 document["json"], document.get("reader"), source.get("original"),
                 source.get("reflow"), paper.get("pages"), bank_per_paper[paper["id"]],
                 len(paper["questions"]), len(paper["blocks"]), _json({k: v for k, v in paper.items()
                     if k not in ("blocks", "questions")})),
            )
            categories[paper["category"]] += 1
            totals["questionRecords"] += sum(
                paper["kind"] != "questions" or q.get("recordType") == "question"
                for q in paper["questions"])
            totals["allRecords"] += len(paper["questions"])
            totals["partialQuestions"] += sum(q["status"] == "partial" for q in paper["questions"])
            totals["sourceBlocks"] += len(paper["blocks"])
            totals["sourceOnlyBlocks"] += sum(b.get("status") == "source_only" for b in paper["blocks"])
        _require(dict(categories) == audit["categories"], "Audit category counts disagree")
        for name in ("questionRecords", "partialQuestions", "sourceBlocks", "sourceOnlyBlocks"):
            _check_audit_count(totals[name], audit[name], f"audit {name}")

        bank_seen: set[str] = set()
        bank_counts = Counter()
        options_count = 0
        marked_count = 0
        for document in documents:
            paper = _read_json(_safe_input_path(root, document["json"]))
            paper_id = paper["id"]
            local_question_ids = [q["id"] for q in paper["questions"]]
            local_block_ids = [b["id"] for b in paper["blocks"]]
            _require(len(local_question_ids) == len(set(local_question_ids)), f"Duplicate question id: {paper_id}")
            _require(len(local_block_ids) == len(set(local_block_ids)), f"Duplicate block id: {paper_id}")
            for ordinal, question in enumerate(paper["questions"], 1):
                full_id = f"{paper_id}:{question['id']}"
                in_bank = question["recordType"] == "question"
                _require((full_id in bank) == in_bank, f"JSONL membership disagrees: {full_id}")
                if in_bank:
                    _validate_bank_row(bank[full_id], paper, question, full_id)
                    bank_seen.add(full_id)
                    bank_counts[question["questionType"]] += 1
                    if question["answer"]["status"] == "explicit":
                        bank_counts["linkedAnswers"] += 1
                source_doc = question["answer"].get("sourceDocumentId")
                _require(not source_doc or source_doc in document_ids,
                         f"Unknown answer source document: {full_id}")
                option_count, marked = _insert_question(connection, paper, question, ordinal, in_bank)
                options_count += option_count
                marked_count += marked
            _insert_blocks(connection, paper)
            _insert_block_links(connection, paper)
            _insert_labels(connection, paper)
            _insert_paper_forms(connection, paper)
            _insert_choice_sets(connection, paper)
            _insert_semantics(connection, paper)
        _require(bank_seen == set(bank), "JSONL contains unmapped question IDs")
        _require(bank_counts["linkedAnswers"] == audit["bank"]["linkedAnswers"],
                 "Audit linked answer count disagrees")
        for question_type in CHOICE_TYPES | {"free_response", "fill_blank"}:
            _check_audit_count(bank_counts[question_type], audit["bank"].get(question_type),
                               f"bank {question_type}")

        _insert_answer_references(connection)

        stats = BuildStats(len(documents), totals["allRecords"], len(bank),
                           totals["sourceBlocks"], options_count, marked_count)
        _verify_database(connection, audit, stats)
        _verify_input_hashes(connection, root)
        connection.commit()
        connection.close()
        connection = None
        with temp_path.open("rb") as handle:
            os.fsync(handle.fileno())
        if output.exists():
            backup = output.with_name(output.name + ".bak")
            with tempfile.NamedTemporaryFile(prefix=f".{backup.name}.", suffix=".tmp",
                                             dir=output.parent, delete=False) as backup_temp:
                backup_temp_path = Path(backup_temp.name)
            try:
                shutil.copy2(output, backup_temp_path)
                with backup_temp_path.open("rb") as handle:
                    os.fsync(handle.fileno())
                os.replace(backup_temp_path, backup)
            finally:
                backup_temp_path.unlink(missing_ok=True)
        os.replace(temp_path, output)
        temp_path = None
        dir_fd = os.open(output.parent, os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
        return stats
    finally:
        if connection is not None:
            connection.close()
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--structured-dir", type=Path, default=DEFAULT_STRUCTURED_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    stats = build_database(args.structured_dir, args.output)
    print(_json({"output": str(args.output.resolve()), **stats.__dict__}))


if __name__ == "__main__":
    main()
