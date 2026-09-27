#!/usr/bin/env python3
"""Read-only, evidence-first audit of structured papers against their source PDFs.

This script never repairs source material. Findings are candidates for a human to
check against the cited PDF page; text extraction cannot prove semantic parity.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import unicodedata

import fitz

fitz.TOOLS.mupdf_display_errors(False)


ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "data/sources"
LIBRARY = SOURCES / "exam-library"
NUMBERED_BLOCK = re.compile(r"^\s*(?:第\s*)?([1-9]\d{0,2})\s*[.．、)]\s*\S")
SUBPART = re.compile(r"[（(]([1-9]\d?)[）)]")
SUSPECT_TYPO = re.compile(r"\ufffd|[，。；：、]{2,}")
LEADING_SUBPART = re.compile(r"(?m)^\s*[（(]([1-9]\d?)[）)]")
ENGLISH = {"kaoyan", "cet4", "cet6", "tem4", "tem8"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalized(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).lower()
    return re.sub(r"[^\w\u4e00-\u9fff]+", "", text)


def paragraph_coverage(source_text: str, rendered_text: str) -> float:
    """Fraction of source character shingles represented in structured blocks."""
    source = normalized(source_text)
    rendered = normalized(rendered_text)
    if not source or not rendered:
        return 0.0
    width = 12 if re.search(r"[\u4e00-\u9fff]", source) else 24
    if len(source) < width * 3:
        return 1.0
    samples = [source[i : i + width] for i in range(0, len(source) - width + 1, width)]
    return sum(item in rendered for item in samples) / len(samples)


@dataclass(frozen=True)
class Source:
    path: Path | None
    expected_hash: str | None
    pages: list[int]
    reference: str


def source_index() -> dict[str, Source]:
    result: dict[str, Source] = {}
    for name in ("cs408-original", "politics-original", "cs408-answers-latex-2016-2025", "politics-answers-latex-2009-2023"):
        parent = SOURCES / name
        records = json.loads((parent / "sources.json").read_text())
        category = "cs408" if name.startswith("cs408") else "politics"
        for record in records:
            key = f"{category}:{record['id']}"
            # Original indexes are authoritative when duplicated by a reflow index.
            if key not in result or name.endswith("original"):
                result[key] = Source(Path(record["path"]), record.get("sha256"),
                                     list(range(1, record["pages"] + 1)), str(parent / "sources.json"))
    for name in ("math3-latex-1987-2009", "math3-latex-2009-2019"):
        path = SOURCES / name / "manifest.json"
        manifest = json.loads(path.read_text())
        pdf = manifest["source"]
        for record in manifest["documents"]:
            key = f"math3:{record['year']}-{record['kind']}"
            result[key] = Source(Path(pdf["path"]), pdf.get("sha256"), record["source_pages"], str(path))
    for name in ("english-exams-web-2026-09-26", "kaoyan-web-2026-09-26"):
        path = SOURCES / name / "manifest.json"
        manifest = json.loads(path.read_text())
        for record in manifest["papers"]:
            if name.startswith("kaoyan"):
                key = f"kaoyan:{record['year']}-{record['paper']}"
                pdf = SOURCES / name / ".firecrawl" / f"{record['year']}-{record['paper']}.pdf"
            else:
                file = Path(record["file"])
                key = f"{record['category']}:{file.stem}"
                pdf = SOURCES / name / ".firecrawl" / record["category"] / f"{file.stem}.pdf"
            if key.startswith("kaoyan:") and name.startswith("english"):
                continue  # the dedicated kaoyan manifest gives the authoritative local PDF
            result[key] = Source(pdf, record.get("source_pdf_sha256"),
                                 list(range(1, record["pages"] + 1)), str(path))
    return result


def check_numbering(paper: dict) -> list[dict]:
    questions = [q for q in paper["questions"] if q.get("recordType") == "question"]
    category = paper["category"]
    buckets: dict[str, list[dict]] = defaultdict(list)
    for q in questions:
        if not str(q.get("number", "")).isdigit():
            continue
        bucket = q.get("sectionKind", "") if category == "math3" else "paper"
        buckets[bucket].append(q)
    findings = []
    for bucket, rows in buckets.items():
        by_number: dict[int, list[dict]] = defaultdict(list)
        for row in rows:
            by_number[int(row["number"])].append(row)
        for number, copies in by_number.items():
            if len(copies) > 1:
                findings.append(dict(code="duplicate_question_number", severity="review", number=number,
                                     questionIds=[q["id"] for q in copies], pages=sorted({p for q in copies for p in q.get("sourcePages", [])}),
                                     evidence=f"{bucket}: {len(copies)} records for number {number}"))
        if category in {"cs408", "politics", "math3"} and len(by_number) >= 4:
            numbers = sorted(by_number)
            for number in range(numbers[0] + 1, numbers[-1]):
                if number not in by_number:
                    prev = by_number.get(number - 1, [])
                    nxt = by_number.get(number + 1, [])
                    findings.append(dict(code="missing_question_number", severity="review", number=number,
                                         questionIds=[q["id"] for q in prev + nxt],
                                         pages=sorted({p for q in prev + nxt for p in q.get("sourcePages", [])}),
                                         evidence=f"{bucket}: gap between {numbers[0]} and {numbers[-1]}"))
    return findings


def check_paper(paper: dict, all_ids: set[str]) -> list[dict]:
    findings = check_numbering(paper)
    blocks = {b["id"]: b for b in paper["blocks"]}
    question_numbers = {str(q.get("number")) for q in paper["questions"]}
    for q in paper["questions"]:
        pages = q.get("sourcePages", [])
        options = q.get("options", [])
        if q.get("questionType") in {"single_choice", "multiple_choice"}:
            labels = [str(opt.get("label", "")).rstrip(".") for opt in options]
            context = q.get("context") or {}
            if paper["category"] == "kaoyan" and context.get("kind") in {"matching_table", "ordering_diagram"}:
                fixed = set(context.get("fixedLetters") or [])
                alphabet = "ABCDEFGH" if "H" in fixed or "H" in labels else "ABCDEFG"
                expected = [letter for letter in alphabet if letter not in fixed]
                valid_labels = labels == expected
            else:
                valid_labels = labels in (list("ABCD"), list("ABCDE"))
            if not valid_labels:
                findings.append(dict(code="incomplete_choices", severity="high", questionIds=[q["id"]],
                                     pages=pages, blockIds=q.get("sourceBlocks", []),
                                     evidence=f"option labels: {labels}"))
        if q.get("status") == "partial":
            findings.append(dict(code="partial_question", severity="review", questionIds=[q["id"]],
                                 pages=pages, blockIds=q.get("sourceBlocks", []), evidence=q.get("stem", "")[:120]))
        answer_fields = q.get("answer") or {}
        text_fields = {"stem": q.get("stem") or ""}
        text_fields.update({f"answer.{key}": answer_fields.get(key) or ""
                            for key in ("value", "solution", "explanation", "commentary", "knowledge")})
        for field, value in text_fields.items():
            match = SUSPECT_TYPO.search(value)
            if match:
                findings.append(dict(code="suspect_typo", severity="review", questionIds=[q["id"]],
                                     pages=pages, blockIds=q.get("sourceBlocks", []),
                                     evidence=f"{field}: {value[max(0, match.start()-35):match.end()+35]}"))
        answer = q.get("answer") or {}
        target = answer.get("sourceDocumentId")
        if target and target not in all_ids:
            findings.append(dict(code="broken_answer_document", severity="high", questionIds=[q["id"]],
                                 pages=pages, evidence=target))
        if answer.get("status") == "explicit" and not target and paper["kind"] != "answers":
            findings.append(dict(code="answer_without_source", severity="high", questionIds=[q["id"]],
                                 pages=pages, evidence="explicit answer has no sourceDocumentId"))
        text = "\n".join(blocks[bid].get("text", "") for bid in q.get("sourceBlocks", []) if bid in blocks)
        if q.get("subquestions"):
            declared = {str(item.get("number")) for item in q["subquestions"] if isinstance(item, dict)}
            markers = {x for x in SUBPART.findall(text) if int(x) <= 12}
            if declared and markers and not markers.issubset(declared):
                findings.append(dict(code="subquestion_mismatch", severity="review", questionIds=[q["id"]],
                                     pages=pages, blockIds=q.get("sourceBlocks", []),
                                     evidence=f"source markers {sorted(markers)}; records {sorted(declared)}"))
        elif paper["category"] in {"politics", "cs408"} and q.get("questionType") == "free_response":
            markers = set(LEADING_SUBPART.findall(text))
            if {"1", "2"}.issubset(markers):
                findings.append(dict(code="possible_missing_subquestions", severity="review", questionIds=[q["id"]],
                                     pages=pages, blockIds=q.get("sourceBlocks", []),
                                     evidence=f"numbered source subparts {sorted(markers)} without subquestion records"))
    for block in paper["blocks"]:
        if block.get("status") != "source_only" or block.get("role") not in {"content", "question", "choices"}:
            continue
        match = NUMBERED_BLOCK.match(block.get("text", ""))
        if match and match.group(1) not in question_numbers:
            findings.append(dict(code="unassigned_numbered_block", severity="review",
                                 blockIds=[block["id"]], pages=[block.get("page")],
                                 evidence=block.get("text", "")[:140]))
    return findings


def audit(root: Path = ROOT, *, compare_text: bool = True) -> dict:
    catalog_path = root / "data/sources/exam-library/documents.json"
    catalog = json.loads(catalog_path.read_text())
    source_map = source_index()
    all_ids = {row["id"] for row in catalog}
    report: dict = {"scope": "all catalog documents", "documents": len(catalog),
                    "catalogSha256": sha256(catalog_path), "papers": [], "findings": [], "sourcePdfCount": 0}
    pdf_cache: dict[Path, tuple[str, int]] = {}
    paper_cache: dict[str, dict] = {}
    for item in catalog:
        doc_id = item["id"]
        category, name = doc_id.split(":", 1)
        paper_path = root / "data/sources/exam-library/structured/papers" / category / f"{name}.json"
        source = source_map.get(doc_id)
        summary = {"documentId": doc_id, "structured": str(paper_path.relative_to(root)),
                   "sourcePdf": str(source.path) if source and source.path else None,
                   "sourceIndex": source.reference if source else None,
                   "sourcePages": source.pages if source else [], "questionCount": 0}
        report["papers"].append(summary)
        findings: list[dict] = []
        if not paper_path.is_file():
            findings.append(dict(code="missing_structured_paper", severity="high", evidence=str(paper_path)))
        else:
            paper = json.loads(paper_path.read_text())
            paper_cache[doc_id] = paper
            summary["structuredSha256"] = sha256(paper_path)
            summary["questionCount"] = len(paper["questions"])
            findings.extend(check_paper(paper, all_ids))
            if item["kind"] in {"questions", "complete"} and category in {"math3", "politics", "cs408"}:
                answer_id = f"{category}:{item['year']}-answers"
                if answer_id in all_ids:
                    missing = [q for q in paper["questions"] if q.get("recordType") == "question"
                               and (q.get("answer") or {}).get("status") == "missing"]
                    if missing:
                        findings.append(dict(code="answer_source_available_but_unlinked", severity="review",
                                             questionIds=[q["id"] for q in missing],
                                             pages=sorted({p for q in missing for p in q.get("sourcePages", [])}),
                                             evidence=f"{len(missing)} questions lack an answer link although {answer_id} exists"))
        if not source:
            findings.append(dict(code="missing_source_index", severity="high", evidence="No source manifest entry"))
        elif not source.path or not source.path.is_file():
            findings.append(dict(code="missing_source_pdf", severity="high", evidence=str(source.path)))
        else:
            if source.path not in pdf_cache:
                try:
                    with fitz.open(source.path) as pdf:
                        pdf_cache[source.path] = (sha256(source.path), len(pdf))
                except Exception as exc:
                    findings.append(dict(code="unreadable_source_pdf", severity="high", evidence=str(exc)))
            if source.path in pdf_cache:
                actual_hash, page_count = pdf_cache[source.path]
                summary.update(sourceSha256=actual_hash, sourcePdfPages=page_count)
                if source.expected_hash and actual_hash != source.expected_hash:
                    findings.append(dict(code="source_hash_mismatch", severity="high",
                                         evidence=f"expected {source.expected_hash}; actual {actual_hash}"))
                if source.pages and (min(source.pages) < 1 or max(source.pages) > page_count):
                    findings.append(dict(code="source_page_out_of_range", severity="high", pages=source.pages,
                                         evidence=f"PDF has {page_count} pages"))
                if category != "math3" and source.pages and len(source.pages) != page_count:
                    findings.append(dict(code="source_page_count_mismatch", severity="high",
                                         evidence=f"index lists {len(source.pages)} pages; PDF has {page_count}"))
                if paper_path.is_file() and source.pages:
                    actual_pages = {int(str(b.get("page"))) for b in paper["blocks"] if str(b.get("page", "")).isdigit()}
                    missing_pages = sorted(actual_pages - set(source.pages))
                    if missing_pages:
                        findings.append(dict(code="structured_page_outside_source", severity="high", pages=missing_pages,
                                             evidence=f"indexed source pages {source.pages[0]}..{source.pages[-1]}"))
                    if compare_text and not any(f["code"] == "source_hash_mismatch" for f in findings):
                        findings.extend(compare_paragraphs(source.path, source.pages, paper, category))
        for finding in findings:
            finding["documentId"] = doc_id
            finding.setdefault("pages", [])
            finding.setdefault("questionIds", [])
            finding.setdefault("blockIds", [])
            report["findings"].append(finding)
    for document_id, paper in paper_cache.items():
        for question in paper["questions"]:
            answer = question.get("answer") or {}
            source_id = answer.get("sourceDocumentId")
            if not source_id or source_id not in all_ids:
                continue
            source_paper = paper_cache.get(source_id)
            if not source_paper:
                continue
            source_blocks = {b["id"] for b in source_paper["blocks"]}
            source_questions = {q["id"] for q in source_paper["questions"]}
            source_pages = {str(b.get("page")) for b in source_paper["blocks"]}
            invalid_blocks = sorted(set(answer.get("sourceBlocks", [])) - source_blocks)
            invalid_questions = sorted(set(answer.get("sourceQuestionIds", [])) - source_questions)
            invalid_pages = sorted(set(map(str, answer.get("sourcePages", []))) - source_pages)
            if invalid_blocks or invalid_questions or invalid_pages:
                report["findings"].append(dict(
                    code="broken_answer_reference", severity="high", documentId=document_id,
                    questionIds=[question["id"]], blockIds=invalid_blocks,
                    pages=question.get("sourcePages", []),
                    evidence=f"{source_id}: missing blocks {invalid_blocks}, questions {invalid_questions}, pages {invalid_pages}"))
    report["sourcePdfCount"] = len(pdf_cache)
    report["counts"] = dict(sorted(Counter(f["code"] for f in report["findings"]).items()))
    return report


def compare_paragraphs(path: Path, source_pages: list[int], paper: dict, category: str) -> list[dict]:
    findings = []
    # Reflow may join text spanning two PDF pages into one source block whose
    # page label denotes its start. Search the entire paper before flagging loss.
    rendered = " ".join(b.get("text", "") for b in paper["blocks"])
    rendered_prose = "".join(re.findall(r"[\u4e00-\u9fff]", rendered)) if category == "math3" else ""
    with fitz.open(path) as pdf:
        for source_page in source_pages:
            if source_page > len(pdf):
                continue
            page = pdf[source_page - 1]
            source_blocks = page.get_text("blocks", sort=True)
            if sum(len(normalized(str(block[4]))) for block in source_blocks) < 30:
                findings.append(dict(code="source_page_text_unextractable", severity="review", pages=[source_page],
                                     evidence="PDF text extraction returned fewer than 30 characters; this does not assess selectable text in the original HTM/SVG"))
                continue
            candidates = []
            for index, block in enumerate(source_blocks, 1):
                text = str(block[4]).strip()
                if category == "math3":
                    # OCR/formulas do not map character-for-character to TeX.
                    # Compare only substantial Chinese prose within a PDF block.
                    prose = "".join(re.findall(r"[\u4e00-\u9fff]", text))
                    if len(prose) < 65 or len(prose) / max(len(normalized(text)), 1) < 0.5:
                        continue
                    score = paragraph_coverage(prose, rendered_prose)
                else:
                    if len(normalized(text)) < (115 if category in ENGLISH else 75):
                        continue
                    score = paragraph_coverage(text, rendered)
                if score < 0.32:
                    candidates.append((score, index, text))
            for score, index, text in candidates[:5]:
                findings.append(dict(code="possible_missing_paragraph", severity="review", pages=[source_page],
                                     evidence=f"PDF text block {index}, shingle coverage {score:.0%}: {text[:160]}"))
    return findings


def markdown(report: dict, json_path: Path | None = None, markdown_path: Path | None = None) -> str:
    command = "./.venv/bin/python scripts/audit_source_integrity.py"
    if json_path:
        command += f" --json {json_path}"
    if markdown_path:
        command += f" --markdown {markdown_path}"
    lines = ["# 原始 PDF 与结构化题库核查", "", "自动核查仅提供复核线索；PDF 抽取顺序、公式和图片可能造成误报。未报告的文字也不能证明无错字或漏段。", "",
             f"复现：`{command}`。脚本只读取目录、结构化 JSON 和原始 PDF；输出仅为两份报告。", "",
             "逐份校验来源 SHA-256 与 PDF 页数/页段。段落检测搜索整份结构化卷，避开跨页合并误报；数学卷只比较足够长的中文文字，公式及图像须人工视觉核对。可提取文字不足的 PDF 页单独列出。题号、选项、小问、答案引用及重复标点均是候选，不作自动修订。", "",
             f"目录文档：{report['documents']}；实际读取的唯一 PDF：{report['sourcePdfCount']}；线索：{len(report['findings'])}。", "", "## 分类统计", ""]
    for code, count in report["counts"].items():
        lines.append(f"- `{code}`：{count}")
    lines.extend(["", "## 高优先级线索", ""])
    for finding in report["findings"]:
        if finding["severity"] != "high":
            continue
        lines.append(f"- `{finding['documentId']}` `{finding['code']}` 页 {','.join(map(str, finding['pages'])) or '?'}；题 {','.join(finding['questionIds']) or '?'}；{finding['evidence']}")
    lines.extend(["", "逐条复核请使用同名 JSON 中的 `documentId`、`sourcePdf`、`pages`、`blockIds` 和 `questionIds`。", ""])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=Path, help="write detailed JSON report")
    parser.add_argument("--markdown", type=Path, help="write summary Markdown report")
    parser.add_argument("--skip-text", action="store_true", help="skip approximate PDF paragraph comparison")
    args = parser.parse_args()
    report = audit(compare_text=not args.skip_text)
    if args.json:
        args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    if args.markdown:
        args.markdown.write_text(markdown(report, args.json, args.markdown))
    print(json.dumps({k: report[k] for k in ("documents", "sourcePdfCount", "counts")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
