"""Attach ten CET reading answers matched across differently numbered PDFs.

The university labels its source PDF "Set 1" while the matching local
reading passages are in CET4:2016-12-03. Only Q46–55 are authorized here.
The university's writing prompt differs, so this is not a paper-wide key.
"""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import re

import fitz


REPO = Path(__file__).resolve().parents[1]
PAPER_ID = "cet4:2016-12-03"
FIXTURE = REPO / ".local/answer-keys/verified-cet4-2016-12-03-reading.json"
SOURCE_MANIFEST = REPO / "data/sources/english-exams-web-2026-09-26/manifest.json"
SOURCE_PDF = (SOURCE_MANIFEST.parent / ".firecrawl/cet4/2016-12-03.pdf")
QUESTION_PDF = REPO / ".local/answer-keys/source-pdfs/gwng-cet4-2016-12-main-questions.pdf"
ANSWER_PDF = REPO / ".local/answer-keys/source-pdfs/gwng-cet4-2016-12-main-answers.pdf"
SOURCE_URL = "https://zhenti.burningvocabulary.cn/cet4/2016-12/03"
SOURCE_DOCUMENT_URL = (
    "https://res-zhenti.burningvocabulary.cn/images/read/cet4/2016-12/03/"
    "e0b1031cd900f52709eade10e1a0e84f.pdf"
)
SOURCE_SHA = "d890c2510e1a3e22bd8a3bfc278c2762129ad1c161ca18a8207466e23cdc3325"
PUBLISHER_INDEX_URL = "https://www.gwng.edu.cn/dyjxb/2019/0901/c540a43688/page.htm"
QUESTION_URL = (
    "https://www.gwng.edu.cn/_upload/article/files/67/aa/"
    "f51a0dd1431eadc255d5fe3d531c/b4760ce6-3be2-4bec-8121-d74c981d25ff.pdf"
)
QUESTION_SHA = "20e8c247f7ff5d63bfb9368dda16eadbf2c3a14ca1c68997b6d5cb5a46e8e3a4"
ANSWER_URL = (
    "https://www.gwng.edu.cn/_upload/article/files/67/aa/"
    "f51a0dd1431eadc255d5fe3d531c/f94518f9-3ff0-43c0-bfe4-4188aa7cd78b.pdf"
)
ANSWER_SHA = "daf34a94dd7680ca67247603024bda8172d0ce4e4c331b24b7f258eb5255ccd7"


def _normal(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.casefold())


def _checked_sha(path: Path, expected: str) -> None:
    if sha256(path.read_bytes()).hexdigest() != expected:
        raise ValueError(f"CET reading source PDF hash changed: {path.name}")


def verified_reading_plan(papers: dict[str, dict], fixture_path: Path = FIXTURE,
                          manifest_path: Path = SOURCE_MANIFEST,
                          source_pdf: Path = SOURCE_PDF,
                          question_pdf: Path = QUESTION_PDF,
                          answer_pdf: Path = ANSWER_PDF) -> list[tuple[dict, dict, dict]]:
    """Return staged updates only after every document and question matches."""
    if PAPER_ID not in papers:
        return []
    evidence = json.loads(fixture_path.read_text(encoding="utf-8"))
    expected = {
        "schema": "verified-cet-external-answers.v1", "paperId": PAPER_ID,
        "sourceUrl": SOURCE_URL, "sourceDocumentUrl": SOURCE_DOCUMENT_URL,
        "sourcePdfSha256": SOURCE_SHA, "publisherIndexUrl": PUBLISHER_INDEX_URL,
        "questionPdfUrl": QUESTION_URL, "questionPdfSha256": QUESTION_SHA,
        "answerPdfUrl": ANSWER_URL, "answerPdfSha256": ANSWER_SHA,
    }
    for key, value in expected.items():
        if evidence.get(key) != value:
            raise ValueError(f"CET reading fixture {key} changed")
    source_rows = [row for row in json.loads(manifest_path.read_text(encoding="utf-8"))["papers"]
                   if row.get("source_url") == SOURCE_URL]
    if len(source_rows) != 1:
        raise ValueError("CET reading original paper missing or duplicated")
    row = source_rows[0]
    if (row.get("category") != "cet4" or row.get("year") != 2016 or
            row.get("paper") != "03" or
            row.get("file") != "cet4/papers/2016-12-03.htm" or
            row.get("document_url") != SOURCE_DOCUMENT_URL or
            row.get("source_pdf_sha256") != SOURCE_SHA):
        raise ValueError("CET reading original paper provenance changed")
    for path, digest in ((source_pdf, SOURCE_SHA), (question_pdf, QUESTION_SHA),
                         (answer_pdf, ANSWER_SHA)):
        _checked_sha(path, digest)

    entries = evidence.get("questions")
    if (not isinstance(entries, list) or len(entries) != 10 or
            [entry.get("number") for entry in entries] != [str(n) for n in range(46, 56)]):
        raise ValueError("CET reading fixture must contain exactly Q46–55")
    paper = papers[PAPER_ID]
    if (paper.get("id") != PAPER_ID or paper.get("category") != "cet4" or
            paper.get("year") != 2016 or paper.get("kind") != "questions" or
            not str(paper.get("source", {}).get("original", "")).endswith(
                "/english-exams-web-2026-09-26/cet4/papers/2016-12-03.htm")):
        raise ValueError("CET reading local paper differs")
    with fitz.open(question_pdf) as source_questions, fitz.open(answer_pdf) as source_answers:
        source_text = "\n".join(page.get_text() for page in source_questions)
        updates = []
        for entry in entries:
            number = entry["number"]
            matches = [q for q in paper["questions"]
                       if q.get("recordType") == "question" and q.get("number") == number]
            if len(matches) != 1:
                raise ValueError(f"CET reading Q{number} missing or duplicated")
            question = matches[0]
            options = question.get("options", [])
            expected_options = entry.get("options")
            if (question.get("id") != entry.get("questionId") or
                    question.get("questionType") != "single_choice" or
                    question.get("stem") != entry.get("stem") or
                    question.get("sourceBlocks") != entry.get("sourceBlocks") or
                    question.get("sourcePages") != entry.get("sourcePages") or
                    not isinstance(expected_options, list) or len(options) != 4 or
                    [{"label": opt.get("label"), "text": opt.get("text"),
                      "sourceOrder": opt.get("sourceOrder")} for opt in options]
                    != expected_options or
                    [opt["label"] for opt in expected_options] != ["A.", "B.", "C.", "D."]):
                raise ValueError(f"CET reading Q{number} local stem/options differ")
            letter = entry.get("answerLetter")
            if not isinstance(letter, str) or letter not in "ABCD":
                raise ValueError(f"CET reading Q{number} answer letter differs")
            selected = expected_options["ABCD".index(letter)]["text"]
            question_matches = list(re.finditer(rf"(?m)^\s*{number}\.\s", source_text))
            if len(question_matches) != 1:
                raise ValueError(f"CET reading Q{number} university question number differs")
            start = question_matches[0].start()
            following = re.search(rf"(?m)^\s*{int(number) + 1}\.\s", source_text[start + 1:])
            end = start + 1 + following.start() if following else len(source_text)
            university_question = _normal(source_text[start:end])
            if (_normal(selected) not in university_question or
                    sum(_normal(opt["text"]) in university_question for opt in expected_options) < 3):
                raise ValueError(f"CET reading Q{number} university printed options differ")
            page_number = entry.get("answerPdfPage")
            if not isinstance(page_number, int) or not 1 <= page_number <= len(source_answers):
                raise ValueError(f"CET reading Q{number} answer page differs")
            printed = re.findall(rf"(?m)^\s*{number}\.\s*([A-D])\s*[)）]",
                                 source_answers[page_number - 1].get_text())
            if printed != [letter]:
                raise ValueError(f"CET reading Q{number} university answer differs")
            answer = question["answer"]
            if answer.get("status") == "explicit" and answer.get("value") == letter:
                continue
            if answer.get("status") != "missing" or any(answer.get(field) for field in
                    ("value", "solution", "explanation", "commentary", "knowledge")):
                raise ValueError(f"CET reading Q{number} existing answer conflicts")
            updates.append((question, entry, evidence))
    return updates


def attach_verified_reading(papers: dict[str, dict], **paths: Path) -> int:
    """Attach the staged answers after the complete ten-question audit."""
    updates = verified_reading_plan(papers, **paths)
    for question, entry, evidence in updates:
        answer = question["answer"]
        answer.update({
            "value": entry["answerLetter"], "status": "explicit",
            "externalSource": {
                "kind": "source_verified_cross_set_reading",
                "url": evidence["answerPdfUrl"],
                "publisherIndexUrl": PUBLISHER_INDEX_URL,
                "questionPdfUrl": QUESTION_URL,
                "questionPdfSha256": QUESTION_SHA,
                "answerPdfSha256": ANSWER_SHA,
                "answerPdfPage": entry["answerPdfPage"],
                "sourcePdfSha256": SOURCE_SHA,
                "capturedAt": evidence["capturedAt"],
            },
        })
    if PAPER_ID in papers:
        paper = papers[PAPER_ID]
        paper["audit"]["linkedAnswers"] = sum(
            q["answer"]["status"] == "explicit" for q in paper["questions"]
            if q.get("recordType") == "question"
        )
    return len(updates)
