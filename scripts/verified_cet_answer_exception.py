"""Apply the one independently checked CET answer-grid exception in memory.

The public capture has ``50-C-`` for this cell, which the general importer
correctly rejects. The live grid prints Q50 C. This adapter does not change
the general token parser or infer answers for any other question.
"""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
EVIDENCE = REPO / ".local/answer-keys/verified-cet6-2018-12-02-q50.json"
SOURCE_MANIFEST = REPO / "data/sources/english-exams-web-2026-09-26/manifest.json"
ORIGINAL_PDF = (REPO / "data/sources/english-exams-web-2026-09-26"
                / ".firecrawl/cet6/2018-12-02.pdf")
PAPER_ID = "cet6:2018-12-02"
SOURCE_URL = "https://zhenti.burningvocabulary.cn/cet6/2018-12/02"
PDF_URL = (
    "https://res-zhenti.burningvocabulary.cn/images/read/cet6/2018-12/02/"
    "f02973e0864d3101e6182c354cfbf6e2.pdf"
)
PDF_SHA256 = "42097d927722bbde222230d3b6046039bb7df4d2dfd06a9090b34dd462b6a798"


def verified_q50_plan(papers: dict[str, dict], evidence_path: Path = EVIDENCE,
                      manifest_path: Path = SOURCE_MANIFEST,
                      pdf_path: Path = ORIGINAL_PDF) -> tuple[dict, dict] | None:
    """Validate all source and target guards before proposing one attachment.

    A selected-paper build without this paper has nothing to attach. A build
    containing it requires the reviewed private fixture and matching source.
    """
    if PAPER_ID not in papers:
        return None
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    expected = {
        "schema": "verified-cet-answer-exception.v1",
        "paperId": PAPER_ID,
        "questionId": "q-50-1",
        "questionNumber": "50",
        "answerLetter": "C",
        "sourceUrl": SOURCE_URL,
        "sourceDocumentUrl": PDF_URL,
        "sourcePdfSha256": PDF_SHA256,
        "sourcePage": "7",
        "sourceBlocks": ["b-7-6", "b-7-7"],
        "printedStem": "50. What does Pamela Harris think should be the goal of math education?",
        "printedOptions": [
            "To enable learners to understand the world better.",
            "To help learners to tell fake math from real math.",
            "To broaden Americans' perspectives on math.",
            "To exert influence on world development.",
        ],
        "gridAnswers46To50": ["C", "A", "B", "A", "C"],
        "capturedAnswerToken": "50-C-",
    }
    for key, value in expected.items():
        if evidence.get(key) != value:
            raise ValueError(f"CET Q50 evidence {key} differs from reviewed source")
    if not isinstance(evidence.get("capturedAt"), str) or not evidence["capturedAt"]:
        raise ValueError("CET Q50 evidence capture time missing")

    source_rows = [row for row in json.loads(manifest_path.read_text(encoding="utf-8"))["papers"]
                   if row.get("source_url") == SOURCE_URL]
    if len(source_rows) != 1:
        raise ValueError("CET Q50 source paper is absent or duplicated")
    source = source_rows[0]
    if (source.get("category") != "cet6" or source.get("year") != 2018 or
            source.get("paper") != "02" or
            source.get("file") != "cet6/papers/2018-12-02.htm" or
            source.get("document_url") != PDF_URL or
            source.get("source_pdf_sha256") != PDF_SHA256):
        raise ValueError("CET Q50 source PDF provenance differs")
    if sha256(pdf_path.read_bytes()).hexdigest() != PDF_SHA256:
        raise ValueError("CET Q50 local original PDF hash differs")

    paper = papers[PAPER_ID]
    if (paper.get("id") != PAPER_ID or paper.get("category") != "cet6" or
            paper.get("kind") != "questions" or paper.get("year") != 2018 or
            not str(paper.get("source", {}).get("original", "")).endswith(
                "/english-exams-web-2026-09-26/cet6/papers/2018-12-02.htm")):
        raise ValueError("CET Q50 target paper differs")
    matches = [q for q in paper["questions"]
               if q.get("recordType") == "question" and q.get("number") == "50"]
    if len(matches) != 1:
        raise ValueError("CET Q50 target number is missing or duplicated")
    question = matches[0]
    if (question.get("id") != "q-50-1" or
            question.get("questionType") != "single_choice" or
            question.get("stem") != evidence["printedStem"] or
            question.get("sourceBlocks") != evidence["sourceBlocks"] or
            question.get("sourcePages") != [evidence["sourcePage"]]):
        raise ValueError("CET Q50 target question differs")
    options = question.get("options", [])
    if (len(options) != 4 or
            [option.get("label") for option in options] != ["A.", "B.", "C.", "D."] or
            [option.get("sourceOrder") for option in options] != [1, 2, 3, 4] or
            [option.get("text") for option in options] != evidence["printedOptions"]):
        raise ValueError("CET Q50 printed A-D options differ")
    blocks = {block["id"]: block for block in paper["blocks"]}
    if (blocks.get("b-7-6", {}).get("text") != evidence["printedStem"] or
            blocks.get("b-7-7", {}).get("text") !=
            " ".join(f"{label}. {option}" for label, option in
                     zip("ABCD", evidence["printedOptions"])) or
            [blocks.get(block_id, {}).get("page") for block_id in evidence["sourceBlocks"]]
            != [evidence["sourcePage"]] * 2):
        raise ValueError("CET Q50 printed source blocks differ")

    answer = question["answer"]
    if answer.get("status") == "explicit" and answer.get("value") == "C":
        return None
    if answer.get("status") != "missing" or any(
            answer.get(field) for field in
            ("value", "solution", "explanation", "commentary", "knowledge")):
        raise ValueError("CET Q50 existing answer conflicts")
    return question, evidence


def attach_verified_q50(papers: dict[str, dict], evidence_path: Path = EVIDENCE,
                        manifest_path: Path = SOURCE_MANIFEST,
                        pdf_path: Path = ORIGINAL_PDF) -> int:
    """Attach exactly one letter after all guards pass; zero for absent/known."""
    planned = verified_q50_plan(papers, evidence_path, manifest_path, pdf_path)
    if planned is None:
        return 0
    question, evidence = planned
    question["answer"].update({
        "value": "C",
        "status": "explicit",
        "externalSource": {
            "kind": "source_verified_cet_grid_exception",
            "url": SOURCE_URL,
            "capturedAt": evidence["capturedAt"],
            "answerToken": "50-C",
            "sourceDocumentUrl": PDF_URL,
            "sourcePdfSha256": PDF_SHA256,
            "sourcePage": "7",
        },
    })
    paper = papers[PAPER_ID]
    paper["audit"]["linkedAnswers"] = sum(
        q["answer"]["status"] == "explicit" for q in paper["questions"]
        if q.get("recordType") == "question"
    )
    return 1
