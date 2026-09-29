"""Exact PDF-backed anchors for 47 CET options omitted by raw-item matching.

Sixteen source items contain joined columns or shifted source-block IDs;
two 2018 CET-6 banks add a printed dot to each raw option value. One 2014
CET-6 choice starts as prose at the foot of the preceding page. The reviewed
fixture pins the original PDFs, printed text, structured choice, and exact
raw item shape. No source, translation, or answer data is changed here.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
FIXTURE_PATH = Path(__file__).with_name("pdf_verified_cet_missing_options.json")


@dataclass(frozen=True)
class VerifiedCetOption:
    option_id: str
    source_text: str
    source_pdf_page: int
    source_pdf_sha256: str
    reflow_block_id: str
    reflow_option_index: int | None
    structured_source_block_ids: tuple[str, ...]
    anchor_kind: str


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _raw_text(block: dict) -> str:
    return "".join(run.get("text", "") for run in block.get("runs", []))


def _block(raw: dict, block_id: str) -> dict:
    match = re.fullmatch(r"b-(\d+)-(\d+)", block_id)
    if not match:
        raise ValueError(f"invalid CET block ID: {block_id}")
    page, index = map(int, match.groups())
    try:
        return raw["pages"][page - 1]["blocks"][index - 1]
    except (IndexError, KeyError, TypeError) as exc:
        raise ValueError(f"missing CET block: {block_id}") from exc


def _option_shape(block: dict) -> str:
    shape = [(item.get("label"), _raw_text(item)) for item in block.get("items", [])]
    return _sha256(json.dumps(shape, ensure_ascii=False).encode())


@lru_cache(maxsize=1)
def _fixture() -> dict:
    data = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    if data.get("schema") != "pdf-verified-cet-missing-options.v1":
        raise ValueError("unexpected CET option fixture schema")
    return data["papers"]


def verified_cet_missing_option_anchors(
    paper: dict, raw: dict, pdf_sha256: str, *, allow_missing_pdf: bool = False
) -> dict[str, VerifiedCetOption]:
    """Return exact derived anchors for this paper, rejecting any source drift.

    The caller may translate each returned ``source_text`` once. Existing
    reflow content remains unchanged; this helper does not invent a missing
    raw option item or fill a cloze blank.
    """
    paper_id = paper["id"]
    entry = _fixture().get(paper_id)
    if entry is None:
        return {}
    pdf = ROOT / entry["sourcePdfPath"]
    expected_pdf_sha = entry["sourcePdfSha256"]
    pdf_exists = pdf.exists()
    if (pdf_sha256 != expected_pdf_sha or
            (pdf_exists and (not pdf.is_file() or _sha256(pdf.read_bytes()) != expected_pdf_sha)) or
            (not pdf_exists and not allow_missing_pdf)):
        raise ValueError(f"{paper_id}: reviewed CET original PDF changed")
    result = {}
    for option_id, choice in entry["options"].items():
        if option_id != choice["optionId"] or not option_id.startswith(paper_id + ":"):
            raise ValueError(f"{paper_id}: reviewed CET option ID changed")
        source_text = choice["sourceText"]
        if _sha256(source_text.encode()) != choice["sourceTextSha256"]:
            raise ValueError(f"{paper_id}: reviewed CET option text changed")
        raw_block_id = choice["rawBlockId"]
        block = _block(raw, raw_block_id)

        if entry["kind"] == "word_bank":
            if block.get("type") not in ("options", "choice_row"):
                raise ValueError(f"{paper_id}: reviewed CET word-bank block changed")
            if _option_shape(block) not in choice["rawBlockShapeSha256"]:
                raise ValueError(f"{paper_id}: reviewed CET word-bank shape changed")
            index = choice["rawItemIndex"]
            try:
                item = block["items"][index]
            except (IndexError, KeyError, TypeError) as exc:
                raise ValueError(f"{paper_id}: reviewed CET raw item missing") from exc
            raw_item_text = _raw_text(item)
            accepted = choice.get("acceptedRawItemTexts", [choice["rawItemText"]])
            if (item.get("label") != choice["rawItemLabel"] or
                    raw_item_text not in accepted or
                    (raw_item_text == choice["rawItemText"] and
                     _sha256(raw_item_text.encode()) != choice["rawItemTextSha256"])):
                raise ValueError(f"{paper_id}: reviewed CET raw item changed")
            start, end = choice["wordSpan"]
            if raw_item_text[start:end] != source_text:
                raise ValueError(f"{paper_id}: exact CET word span changed")
            structured_source_ids = tuple(choice.get("acceptedStructuredSourceBlockIds",
                                                     [choice["structuredSourceBlockId"]]))
            matches = [item for question in paper.get("questions", [])
                       for item in (question.get("context") or {}).get("wordBank", [])
                       if item.get("id") == option_id]
            if (not matches or any(item.get("text") != source_text or
                                   item.get("sourceBlockId") not in structured_source_ids
                                   for item in matches)):
                raise ValueError(f"{paper_id}: structured CET word-bank item changed")
            structured_source_ids = (matches[0]["sourceBlockId"],)
            kind = "word_bank_option"
        elif entry["kind"] == "cross_page_single_choice":
            index = None
            raw_text = _raw_text(block)
            if (block.get("type") != choice["rawBlockType"] or
                    raw_text != choice["rawBlockText"] or
                    _sha256(raw_text.encode()) != choice["rawBlockTextSha256"] or
                    not raw_text.startswith(choice["rawPrintedPrefix"]) or
                    "".join(raw_text[len(choice["rawPrintedPrefix"]):].split()) !=
                    "".join(source_text.split())):
                raise ValueError(f"{paper_id}: reviewed cross-page CET choice changed")
            companion = _block(raw, choice["companionOptionsBlockId"])
            if (companion.get("type") != "options" or
                    _option_shape(companion) != choice["companionOptionsShapeSha256"]):
                raise ValueError(f"{paper_id}: cross-page CET companion options changed")
            question = next((q for q in paper.get("questions", []) if q["id"] == "q-22-1"), None)
            options = [o for o in (question or {}).get("options", []) if o.get("label") == "A."]
            if (question is None or question.get("sourceBlocks") != choice["structuredSourceBlockIds"] or
                    len(options) != 1 or options[0].get("text") != source_text):
                raise ValueError(f"{paper_id}: structured cross-page CET choice changed")
            structured_source_ids = tuple(choice["structuredSourceBlockIds"])
            kind = "answer_option"
        else:
            raise ValueError(f"{paper_id}: unknown CET option fixture kind")

        result[option_id] = VerifiedCetOption(
            option_id=option_id,
            source_text=source_text,
            source_pdf_page=choice["pdfPage"],
            source_pdf_sha256=expected_pdf_sha,
            reflow_block_id=raw_block_id,
            reflow_option_index=index,
            structured_source_block_ids=structured_source_ids,
            anchor_kind=kind,
        )
    return result
