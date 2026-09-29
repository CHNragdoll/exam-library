"""Attach only uniquely aligned, source-verified public TEM answer letters."""

from __future__ import annotations

from collections import Counter, defaultdict
from hashlib import sha256
import json
from pathlib import Path
import re


WORKER_SHA256 = "e6f00de05cb36730674615aa5e1d33532dd6ae58d7290732b269476208736195"
ORIGIN = "https://zhenti.burningvocabulary.cn"
PDF_ORIGIN = "https://res-zhenti.burningvocabulary.cn/images/read/"
SUPPLEMENTARY_HEADINGS = {
    # The 2022 PDF appends a 2023 supplementary set after its own main paper.
    "tem4:2022": "2023 年英语专业四级真题补充卷说明：本次考试全国出现了两套试题",
    "tem4:2023": "2023 年英语专业四级真题补充卷说明：本次考试全国出现了两套试题",
    "tem4:2025": "2025 年英语专业四级真题补充卷说明：本次考试全国出现了两套试题",
}


def _main_choice_before_supplement(paper: dict, number: str,
                                   matches: list[dict]) -> dict | None:
    """Select a main-paper choice only when the PDF marks a second set.

    The public grid has one 1–50 answer sequence for the main paper. These
    PDFs append a separately headed supplementary LANGUAGE USAGE/CLOZE set,
    reusing some question numbers. Never apply that grid to the appendix.
    """
    heading = SUPPLEMENTARY_HEADINGS.get(paper.get("id"))
    if (not heading or not number.isdigit() or not 11 <= int(number) <= 30 or
            len(matches) != 2):
        return None
    blocks = {block["id"]: block for block in paper["blocks"]}
    supplement_heading = blocks.get("b-10-1", {})
    if (supplement_heading.get("page") != "10" or
            not str(supplement_heading.get("text", "")).startswith(heading)):
        return None
    main = [question for question in matches
            if question.get("id") == f"q-{number}-1" and
            question.get("questionType") == "single_choice" and
            question.get("sourcePages") in (["2"], ["3"]) and
            question.get("sourceBlocks") and
            all(blocks.get(block_id, {}).get("page") in {"2", "3"}
                for block_id in question["sourceBlocks"])]
    supplement = [question for question in matches
                  if question.get("id") == f"q-{number}-2" and
                  question.get("sourcePages") == ["10"] and
                  question.get("sourceBlocks") and
                  all(blocks.get(block_id, {}).get("page") == "10"
                      for block_id in question["sourceBlocks"])]
    return main[0] if len(main) == len(supplement) == 1 else None


def _validated_tokens(source: dict, category: str) -> dict[str, str]:
    expected = 50 if category == "tem4" else 24
    tokens = source.get("answers")
    if not isinstance(tokens, list) or len(tokens) != expected:
        raise ValueError(f'{source.get("paperId")}: expected {expected} answer tokens')
    result = {}
    for number, token in enumerate(tokens, 1):
        match = re.fullmatch(r"(\d{1,3})-([A-O])", token) if isinstance(token, str) else None
        if not match or int(match.group(1)) != number:
            raise ValueError(f'{source["paperId"]}: invalid answer token {number}')
        letter = match.group(2)
        if category == "tem8" or number <= 30 or number >= 41:
            if letter not in "ABCD":
                raise ValueError(f'{source["paperId"]}: unexpected choice letter {number}')
        result[str(number)] = letter
    if category == "tem4" and len({result[str(number)] for number in range(31, 41)}) != 10:
        raise ValueError(f'{source["paperId"]}: duplicate TEM4 word-bank answer letter')
    return result


def _printed_labels(question: dict, category: str) -> list[str] | None:
    if question.get("recordType") != "question":
        return None
    if question.get("questionType") == "single_choice":
        labels = [str(option.get("label", "")).rstrip(".").upper()
                  for option in question.get("options", [])]
        return labels if sorted(labels) == list("ABCD") else None
    if category != "tem4" or question.get("questionType") != "fill_blank":
        return None
    context = question.get("context") or {}
    number = str(question.get("number"))
    if (context.get("kind") != "word_bank_cloze" or
            context.get("wordBankStatus") != "complete" or
            context.get("unresolvedWordBankFragments") or
            not str(context.get("text") or "").strip() or
            not context.get("passageSourceBlocks") or
            number not in {str(value) for value in context.get("printedBlankNumbers", [])} or
            number in {str(value) for value in context.get("sourceNumberUnverifiedNumbers", [])}):
        return None
    labels = [str(option.get("label", "")).rstrip(".").upper()
              for option in context.get("wordBank", [])]
    return labels if sorted(labels) == list("ABCDEFGHIJKLMNO") else None


def attach_tem_public_answer_keys(
    papers: dict[str, dict], capture: dict, original_manifest: dict
) -> dict[str, int]:
    """Validate all source records, then attach only unambiguous missing answers.

    The capture is produced after hashing the live PDF. The original manifest
    provides the canonical paper URL and PDF SHA-256 independently of the key.
    """
    if capture.get("source") != ORIGIN or capture.get("workerSha256") != WORKER_SHA256:
        raise ValueError("TEM answer capture origin or reviewed worker hash changed")
    rows = {f'{row["category"]}:{row["year"]}': row for row in original_manifest["papers"]
            if row.get("category") in {"tem4", "tem8"}}
    sources = capture.get("papers")
    if not isinstance(sources, list) or len(sources) != 8 or len(rows) != 8:
        raise ValueError("Expected eight canonical TEM source papers")
    if len({row.get("paperId") for row in sources}) != 8:
        raise ValueError("Duplicate TEM answer paper ID")
    staged = []
    counts = Counter()
    for source in sources:
        paper_id = source.get("paperId")
        row = rows.get(paper_id)
        paper = papers.get(paper_id)
        if not row:
            raise ValueError(f"Unknown TEM source paper: {paper_id}")
        category = row["category"]
        if (category not in {"tem4", "tem8"} or
                row.get("file") != f'{category}/papers/{row["year"]}.htm' or
                source.get("sourceUrl") != row.get("source_url") or
                source.get("sourceUrl") != f'{ORIGIN}/{category}/{row["year"]}' or
                source.get("sourceDocumentUrl") != row.get("document_url") or
                not str(source.get("sourceDocumentUrl", "")).startswith(PDF_ORIGIN) or
                source.get("sourcePdfSha256") != row.get("source_pdf_sha256") or
                not re.fullmatch(r"[a-f0-9]{64}", str(source.get("sourcePdfSha256", "")))):
            raise ValueError(f"TEM paper/PDF provenance mismatch: {paper_id}")
        keys = _validated_tokens(source, category)
        if paper is None:
            counts["unmatchedPapers"] += 1
            continue
        if (paper.get("id") != paper_id or paper.get("category") != category or
                paper.get("year") != row["year"] or paper.get("kind") != "questions"):
            raise ValueError(f"Mismatched TEM local paper: {paper_id}")
        by_number = defaultdict(list)
        for question in paper["questions"]:
            if question.get("recordType") == "question":
                by_number[str(question.get("number"))].append(question)
        for number, value in keys.items():
            matches = by_number[number]
            main_paper_duplicate = len(matches) != 1
            if len(matches) == 1:
                question = matches[0]
            else:
                question = _main_choice_before_supplement(paper, number, matches)
            if question is None:
                counts["duplicateOrMissingNumber"] += 1
                continue
            labels = _printed_labels(question, category)
            if labels is None or labels.count(value) != 1:
                counts["printedOptionOrBankMismatch"] += 1
                continue
            answer = question.get("answer") or {}
            if answer.get("status") == "explicit":
                counts["alreadyKnown" if answer.get("value") == value else "existingAnswerConflict"] += 1
                continue
            if answer.get("status") != "missing":
                counts["otherExistingAnswer"] += 1
                continue
            staged.append((question, value, source, number, main_paper_duplicate))
    for question, value, source, number, main_paper_duplicate in staged:
        answer = question["answer"]
        answer["value"] = value
        answer["status"] = "explicit"
        answer["externalSource"] = {
            "url": source["sourceUrl"],
            "capturedAt": capture["capturedAt"],
            "answerToken": f"{number}-{value}",
            "sourceDocumentUrl": source["sourceDocumentUrl"],
            "sourcePdfSha256": source["sourcePdfSha256"],
            "workerSha256": WORKER_SHA256,
        }
        if main_paper_duplicate:
            answer["externalSource"]["sourceSet"] = "main_paper_before_pdf_supplement"
            answer["externalSource"]["supplementHeadingSourceBlock"] = "b-10-1"
        counts["attached"] += 1
    for paper_id in rows:
        paper = papers.get(paper_id)
        if paper is None:
            continue
        paper["audit"]["linkedAnswers"] = sum(
            q["answer"]["status"] == "explicit" for q in paper["questions"]
            if q["recordType"] == "question")
    return dict(counts)


def attach_from_private_capture(
    papers: dict[str, dict], capture_path: Path, original_manifest_path: Path
) -> dict[str, int]:
    if not capture_path.exists() or not any(
            paper_id.startswith(("tem4:", "tem8:")) for paper_id in papers):
        return {}
    capture = json.loads(capture_path.read_text(encoding="utf-8"))
    original = json.loads(original_manifest_path.read_text(encoding="utf-8"))
    # The capture verifies the public PDF against the manifest. Confirm that
    # the archived PDF used to build these local questions still has those
    # exact bytes before associating its printed choices with answer letters.
    for row in original["papers"]:
        if row.get("category") not in {"tem4", "tem8"}:
            continue
        source_pdf = (original_manifest_path.parent / ".firecrawl" /
                      row["category"] / f'{row["year"]}.pdf')
        if (not source_pdf.is_file() or
                sha256(source_pdf.read_bytes()).hexdigest() != row["source_pdf_sha256"]):
            raise ValueError(f'TEM archived source PDF changed: {row["category"]}:{row["year"]}')
    return attach_tem_public_answer_keys(papers, capture, original)
