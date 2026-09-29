"""PDF-anchored option text missing from the Kaoyan reflow option blocks.

The eight English II matching tables are figures in the reflow source, so
their printed A–G choices cannot be found as raw ``options`` items. Four
English I papers also have passage choices represented as prose, including
one choice split by the reflow parser. This module validates a narrowly
reviewed fixture and returns derived anchors without changing source data.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
FIXTURE_PATH = Path(__file__).with_name("pdf_verified_kaoyan_matching_options.json")
OPTION_PREFIX = re.compile(r"^[A-G][.)]\s*")


@dataclass(frozen=True)
class VerifiedMatchingOption:
    option_id: str
    source_option_id: str
    source_text: str
    source_pdf_page: int
    source_pdf_sha256: str
    anchor_kind: str
    reflow_block_ids: tuple[str, ...]
    derived_passage_text: str | None = None


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _glyphs(text: str) -> str:
    """Discard layout whitespace only; preserve punctuation and every glyph."""
    return "".join(char for char in text if not char.isspace())


def _raw_block(raw: dict, block_id: str) -> dict:
    match = re.fullmatch(r"b-(\d+)-(\d+)", block_id)
    if not match:
        raise ValueError(f"invalid reflow block ID: {block_id}")
    page, index = map(int, match.groups())
    try:
        return raw["pages"][page - 1]["blocks"][index - 1]
    except (IndexError, KeyError, TypeError) as exc:
        raise ValueError(f"missing reflow block: {block_id}") from exc


def _raw_text(block: dict) -> str:
    return "".join(run.get("text", "") for run in block.get("runs", []))


@lru_cache(maxsize=1)
def _fixture() -> dict:
    data = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    if data.get("schema") != "pdf-verified-kaoyan-matching-options.v1":
        raise ValueError("unexpected Kaoyan matching option fixture schema")
    return data["papers"]


def verified_matching_option_anchors(
    paper: dict, raw: dict, pdf_sha256: str
) -> dict[str, VerifiedMatchingOption]:
    """Validate one paper and return verified per-question option anchors.

    Figure choices get the real table block as a source anchor. Passage
    choices carry their own prose block(s), and the 2005 split choice has
    ``derived_passage_text`` for a source-preserving paragraph join. A
    missing target or any fixture, PDF, raw, or structured drift fails closed.
    """
    paper_id = paper["id"]
    entry = _fixture().get(paper_id)
    if entry is None:
        return {}
    expected_pdf_sha = entry["sourcePdfSha256"]
    pdf = ROOT / entry["sourcePdfPath"]
    if (pdf_sha256 != expected_pdf_sha or not pdf.is_file() or
            _sha256(pdf.read_bytes()) != expected_pdf_sha):
        raise ValueError(f"{paper_id}: reviewed original PDF changed")

    if entry["kind"] == "figure_bank":
        actual_figure = entry["actualFigureBlockId"]
        figure_block = _raw_block(raw, actual_figure)
        if (figure_block.get("type") != "figure" or
                _sha256(json.dumps(figure_block, sort_keys=True,
                                   ensure_ascii=False).encode()) != entry["figureBlockSha256"]):
            raise ValueError(f"{paper_id}: reviewed table figure changed")
        block_ids = (actual_figure,)
    elif entry["kind"] != "passage_option":
        raise ValueError(f"{paper_id}: unknown verified anchor kind")

    questions = {question["id"]: question for question in paper.get("questions", [])}
    expected_questions = {f"q-{number}-1" for number in range(41, 46)}
    if not expected_questions.issubset(questions):
        raise ValueError(f"{paper_id}: matching questions 41–45 changed")
    anchored: dict[str, VerifiedMatchingOption] = {}
    for label, choice in entry["choices"].items():
        if choice["label"] != label or choice["sourceOptionId"] != f"{paper_id}:part-b:{label}":
            raise ValueError(f"{paper_id}: reviewed choice ID changed")
        source_text = choice["text"]
        if _sha256(source_text.encode()) != choice["textSha256"]:
            raise ValueError(f"{paper_id}: reviewed choice text changed")
        if entry["kind"] == "passage_option":
            block_ids = tuple(choice["passageBlockIds"])
            parts = []
            for block_id in block_ids:
                block = _raw_block(raw, block_id)
                text = _raw_text(block)
                if (block.get("type") != choice["passageBlockTypes"][block_id] or
                        _sha256(text.encode()) != choice["passageBlockTextSha256"][block_id]):
                    raise ValueError(f"{paper_id}: reviewed passage option changed")
                parts.append(text)
            if len(parts) not in (1, 2) or (len(parts) == 2 and choice["joinSeparator"] != " "):
                raise ValueError(f"{paper_id}: unexpected passage join")
            derived_text = choice["joinSeparator"].join(parts)
            if _glyphs(OPTION_PREFIX.sub("", derived_text)) != _glyphs(source_text):
                raise ValueError(f"{paper_id}: printed passage option differs from choice")
        else:
            derived_text = None
        for question_id in sorted(expected_questions):
            question = questions[question_id]
            context = question.get("context") or {}
            bank = [item for item in context.get("choiceBank", [])
                    if item.get("id") == choice["sourceOptionId"]]
            options = [option for option in question.get("options", [])
                       if option.get("sourceOptionId") == choice["sourceOptionId"]]
            if len(bank) != 1 or len(options) != 1:
                raise ValueError(f"{paper_id}: choice {label} no longer occurs once per question")
            if (bank[0].get("text") != source_text or options[0].get("text") != source_text or
                    str(options[0].get("label", "")).strip().rstrip(".)") != label):
                raise ValueError(f"{paper_id}: structured choice {label} changed")
            if (entry["kind"] == "figure_bank" and
                    context.get("figureBlockId") != entry["contextFigureBlockId"]):
                raise ValueError(f"{paper_id}: structured table anchor changed")
            option_id = f"{paper_id}:{question_id}:{label}"
            anchored[option_id] = VerifiedMatchingOption(
                option_id=option_id,
                source_option_id=choice["sourceOptionId"],
                source_text=source_text,
                source_pdf_page=choice["pdfPage"],
                source_pdf_sha256=expected_pdf_sha,
                anchor_kind=entry["kind"],
                reflow_block_ids=block_ids,
                derived_passage_text=derived_text,
            )
    return anchored
