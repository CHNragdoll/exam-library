"""Build the versioned SQLite question bank from the structured exam export.

The JSON files remain the source of truth. A failed validation never replaces an
existing database; a successful build is published with one atomic rename.
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import tempfile


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STRUCTURED_DIR = REPO_ROOT / "data/sources/exam-library/structured"
DEFAULT_OUTPUT = REPO_ROOT / "data/question-bank.sqlite3"
SCHEMA_PATH = Path(__file__).with_name("question_bank_schema.sql")
SCHEMA_VERSION = "question-bank.sqlite.v2"
PAPER_SCHEMA = "exam-paper.v1"
CHOICE_TYPES = frozenset(("single_choice", "multiple_choice"))
OPTION_LABEL = re.compile(r"^([A-H])\.$")
ANSWER_SEPARATORS = re.compile(r"[\s,，、/&+;；()（）\[\]【】]+")


@dataclass(frozen=True)
class BuildStats:
    papers: int
    question_records: int
    bank_questions: int
    source_blocks: int
    options: int
    marked_questions: int


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


def _choice_letters(question: dict, labels: list[str]) -> set[str] | None:
    answer = question["answer"]
    context = question.get("context") or {}
    matching_bank = context.get("kind") in {"matching_table", "ordering_diagram"}
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
            or question.get("status") != "complete"
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
        connection.execute("INSERT INTO meta(key,value) VALUES (?,?)", ("source_schema", PAPER_SCHEMA))

        categories = Counter()
        totals = Counter()
        for ordinal, document in enumerate(documents, 1):
            path = _safe_input_path(root, document["json"])
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
        _require(bank_seen == set(bank), "JSONL contains unmapped question IDs")
        _require(bank_counts["linkedAnswers"] == audit["bank"]["linkedAnswers"],
                 "Audit linked answer count disagrees")
        for question_type in CHOICE_TYPES | {"free_response", "fill_blank"}:
            _check_audit_count(bank_counts[question_type], audit["bank"].get(question_type),
                               f"bank {question_type}")

        stats = BuildStats(len(documents), totals["allRecords"], len(bank),
                           totals["sourceBlocks"], options_count, marked_count)
        _verify_database(connection, audit, stats)
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
