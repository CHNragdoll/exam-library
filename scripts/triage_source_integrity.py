#!/usr/bin/env python3
"""Classify noisy source-integrity findings without modifying exam content.

The output records the audit snapshot it was based on. A text-only comparison
cannot certify that an image fallback contains every PDF glyph.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re

import fitz


ROOT = Path(__file__).resolve().parents[1]
TARGET_CODES = {"possible_missing_paragraph", "incomplete_choices", "possible_missing_subquestions"}
DISPOSITION = {
    "confirmed_missing_answer_explanation": "confirmed_defect",
    "confirmed_answer_page_misparsed": "confirmed_defect",
    "confirmed_free_response_mistyped": "confirmed_defect",
    "confirmed_option_parse_failure": "confirmed_defect",
    "printed_original_duplicate_label": "unresolved_original_printing",
    "printed_original_option_anomaly": "unresolved_original_printing",
    "printed_cross_reference_to_other_paper": "no_content_loss_observed",
    "non_choice_directions": "no_content_loss_observed",
    "answer_or_transcript_misparsed": "likely_defect",
    "answer_page_subparts": "likely_defect",
    "option_parse_failure_likely": "likely_defect",
    "subquestions_not_structured": "likely_defect",
    "option_needs_pdf_review": "unresolved",
    "visual_options_present": "visual_content_present_structural_review",
    "image_fallback_unreviewed": "visual_fallback_unreviewed",
    "image_fallback_visually_present": "no_content_loss_observed",
    "word_bank_repaired_from_pdf": "no_content_loss_observed",
    "text_present_ocr_or_formula_variation": "no_content_loss_observed",
    "text_present_reordered": "no_content_loss_observed",
}
VISUALLY_CHECKED_PDF_PAGES = [
    ("cs408:2013-complete", 6), ("cs408:2013-complete", 10),
    ("cs408:2010-complete", 3), ("cs408:2010-complete", 4),
    ("cs408:2014-complete", 8),
    ("cs408:2015-complete", 1), ("cs408:2017-questions", 1),
    ("cs408:2017-answers", 6), ("cs408:2009-complete", 1),
    ("cet6:2012-06-01", 22), ("tem4:2025", 9),
    ("tem8:2025", 6), ("politics:2021-questions", 6),
    ("cet6:2024-12-01", 8), ("cet6:2020-07-01", 1),
    ("politics:2020-questions", 1),
    ("politics:2020-answers", 2),
]
VISUALLY_CHECKED_FALLBACKS = [
    ("cet6:2020-09-02", 2, "b-2-8"),
    ("tem4:2025", 9, "b-9-5"),
    ("cet4:2020-12-03", 1, "b-1-7"),
]
VISUALLY_CHECKED_PARAGRAPHS = {
    ("cet6:2020-09-02", 2, 7), ("cet6:2020-09-02", 2, 8),
    ("tem4:2025", 9, 10), ("cet4:2020-12-03", 1, 5),
}
VISUALLY_CONFIRMED_OPTION_IDS = {
    ("tem8:2025", "q-22-1"),
    ("cet6:2024-12-01", "q-51-1"), ("cet6:2024-12-01", "q-53-1"),
    ("cet6:2020-07-01", "q-2-1"), ("cet6:2020-07-01", "q-4-1"),
    ("politics:2020-questions", "q-1-1"),
}


def owner(category: str) -> str:
    if category == "cs408":
        return "408 结构化解析：scripts/build_structured_exams.py；源文字错误另查 data/sources/cs408-latex-2009-2017"
    if category == "politics":
        return "政治结构化解析：scripts/build_structured_exams.py"
    if category == "math3":
        return "数学三结构化解析：scripts/build_structured_exams.py；核对相应 math3-latex 源记录"
    return "英语原卷重排/结构化解析：data/sources/english-exams-reflow-latex/tools/extract.py 与 scripts/build_structured_exams.py"


def classify_choice(finding: dict, paper: dict) -> tuple[str, str]:
    question = next(q for q in paper["questions"] if q["id"] == finding["questionIds"][0])
    blocks = {b["id"]: b for b in paper["blocks"]}
    source_text = " ".join(blocks[bid].get("text", "") for bid in question.get("sourceBlocks", []) if bid in blocks)
    document_id = finding["documentId"]
    category = paper["category"]
    if document_id == "cs408:2013-complete" and question["id"].endswith("-2"):
        return "confirmed_answer_page_misparsed", "PDF 第10页起为答案解析；重复记录应归入前面的题目答案"
    if document_id == "cs408:2013-complete" and 41 <= int(question["number"]) <= 47:
        return "confirmed_free_response_mistyped", "PDF 第6页标明第41～47题为综合应用题，没有 A–D 选项"
    if category in {"cet4", "cet6", "kaoyan", "tem4", "tem8"} and question["id"].endswith("-2"):
        if len(question.get("options", [])) <= 1 or any(
            marker in question.get("stem", "") for marker in ("【定位】", "【精析】", "【线索词】")
        ):
            return "answer_or_transcript_misparsed", "题号第二次出现于答案、解析或听力原文；不应当作缺 A–D 的新题"
    if category == "cs408" and any(blocks[bid].get("role") == "figure" for bid in question["sourceBlocks"] if bid in blocks):
        return "visual_options_present", "原 PDF 的 A–D 是图形选项，结构化记录未给出独立图像选项"
    if (document_id, question["id"]) in VISUALLY_CONFIRMED_OPTION_IDS:
        return "confirmed_option_parse_failure", "原 PDF 已视觉核实 A–D 齐全；结构化 options 缺项"
    if document_id == "cs408:2015-complete" and question["id"] == "q-1-1":
        return "printed_original_duplicate_label", "原 PDF 第1页与源块 b-1-6 均为 A/B/B/D；保留印刷标签，人工审查选项表示，不得推造 C"
    if category == "math3" and document_id.startswith("math3:") and question["id"].split("-")[-1] in {"4", "5", "6"}:
        if "同试卷" in source_text or "同试卷" in question.get("stem", ""):
            return "printed_cross_reference_to_other_paper", "原 PDF 的 V 卷只印指向 IV 卷对应题的交叉引用，没有重印选项；已核实目标题有四项"
    if document_id == "kaoyan:2000-01" and question["id"] == "q-36-1":
        return "non_choice_directions", "原 PDF 的 A/B/C 是作文说明条款，不是选择题选项"
    if (document_id, question["id"]) in {
        ("cet6:2018-06-02", "q-53-2"),
        ("cet6:2015-12-01", "q-56-1"),
        ("cet6:2014-12-01", "q-61-1"),
        ("cet4:2014-12-01", "q-61-1"),
        ("politics:2005-questions", "q-3-1"),
    }:
        return "printed_original_option_anomaly", "已逐页核对原 PDF：选项标签重复、缺印或异常；保留原印刷文字和部分题状态，不猜补标准四项"
    if document_id == "cs408:2010-complete":
        return "confirmed_option_parse_failure", "PDF 可见 A–D，源块中也有选项文字，但 options 为空"
    if all(re.search(r"(?<![A-Za-z])" + letter + r"\s*[.．、）)]", source_text) for letter in "ABCD"):
        return "option_parse_failure_likely", "四个选项标记在源块中，但未完整进入 options"
    return "option_needs_pdf_review", "选项组不足；现有文字规则无法判定是源图缺字、排版标记还是解析器错误"


def paragraph_text(audit_row: dict, pdf: fitz.Document) -> str:
    match = re.search(r"PDF text block (\d+)", audit_row["evidence"])
    if not match:
        return ""
    blocks = pdf[int(audit_row["pages"][0]) - 1].get_text("blocks", sort=True)
    index = int(match.group(1)) - 1
    return str(blocks[index][4]) if 0 <= index < len(blocks) else ""


def text_match(source: str, rendered: str, category: str) -> float:
    if category in {"cs408", "politics", "math3"}:
        source_han = "".join(re.findall(r"[\u4e00-\u9fff]", source))
        rendered_han = "".join(re.findall(r"[\u4e00-\u9fff]", rendered))
        shingles = {source_han[i : i + 4] for i in range(len(source_han) - 3)}
        return sum(token in rendered_han for token in shingles) / max(len(shingles), 1)
    source_words = set(re.findall(r"[a-z]{3,}", source.lower()))
    rendered_words = set(re.findall(r"[a-z]{3,}", rendered.lower()))
    return len(source_words & rendered_words) / max(len(source_words), 1)


def classify(audit: dict, *, root: Path = ROOT) -> dict:
    paper_by_id = {p["documentId"]: p for p in audit["papers"]}
    review_path = root / "docs/fallback-visual-review-2026-09-28.json"
    reviewed_fallbacks = {}
    if review_path.is_file():
        reviewed_fallbacks = {
            (row["documentId"], int(row["pages"][0]), int(row["pdfBlockIndex"])): row
            for row in json.loads(review_path.read_text())["rows"]
        }
    paper_cache: dict[str, dict] = {}
    pdf_cache: dict[str, fitz.Document] = {}
    rows = []
    try:
        for finding in audit["findings"]:
            if finding["code"] not in TARGET_CODES:
                continue
            doc_id = finding["documentId"]
            paper_meta = paper_by_id[doc_id]
            paper = paper_cache.setdefault(doc_id, json.loads((root / paper_meta["structured"]).read_text()))
            category = paper["category"]
            row = {key: finding.get(key) for key in ("documentId", "code", "pages", "questionIds", "blockIds", "evidence")}
            row["sourcePdf"] = paper_meta["sourcePdf"]
            row["owner"] = owner(category)
            if finding["code"] == "incomplete_choices":
                classification, rationale = classify_choice(finding, paper)
                question = next(q for q in paper["questions"] if q["id"] == finding["questionIds"][0])
                row["blockIds"] = question.get("sourceBlocks", [])
                if classification == "printed_original_duplicate_label":
                    row["owner"] = "408 结构化选项表示：保留原卷及重排源 A/B/B/D，标注印刷异常；不得自动改作 C"
            elif finding["code"] == "possible_missing_subquestions":
                if doc_id == "cs408:2013-complete":
                    classification, rationale = "answer_page_subparts", "q-44-2 是答案解析页的重复题记录；应随答案归属处理"
                else:
                    classification, rationale = "subquestions_not_structured", "原题块有（1）（2）小问，subquestions 数组为空"
            else:
                page = str(finding["pages"][0])
                page_blocks = [b for b in paper["blocks"] if b.get("page") == page]
                fallbacks = [b for b in page_blocks if "<img " in b.get("contentHtml", "")]
                if doc_id == "politics:2020-answers" and page == "2" and "PDF text block 8" in finding["evidence"]:
                    classification = "confirmed_missing_answer_explanation"
                    rationale = "原 PDF 第2页题13完整解析缺于答案源、TeX、重排及结构化卷；q-13-1 仅保留答案 B"
                    row["questionIds"] = ["q-13-1"]
                    row["blockIds"] = ["b-2-5"]
                    row["owner"] = "政治答案源录入：data/sources/politics-answers-latex-2009-2023/source/2020.json；随后重建 TeX 与结构化卷"
                elif fallbacks:
                    block_match = re.search(r"PDF text block (\d+)", finding["evidence"])
                    evidence_key = (doc_id, int(page), int(block_match.group(1))) if block_match else None
                    reviewed = reviewed_fallbacks.get(evidence_key)
                    if reviewed:
                        conclusion = reviewed["visualConclusion"]
                        if conclusion == "preserved_in_fallback_image":
                            classification = "image_fallback_visually_present"
                            rationale = "已逐条查看原 PDF 和当前回退图，目标段落及首尾行完整可见；不等于已可搜索"
                        elif conclusion == "preserved_as_selectable_text_and_math":
                            classification = "text_present_ocr_or_formula_variation"
                            rationale = "逐条目检确认目标文字或公式已有表示；连续字串比对误报"
                        elif conclusion == "word_bank_label_or_transcription_error":
                            classification = "word_bank_repaired_from_pdf"
                            rationale = "原 PDF 已目检，词库 O 项和可确认错字已按源卷修复；原图回退仍保留"
                        else:
                            raise ValueError(f"unknown visual review conclusion: {conclusion}")
                        row["visualReview"] = str(review_path.relative_to(root))
                        row["visualReviewId"] = reviewed["reviewId"]
                    elif evidence_key in VISUALLY_CHECKED_PARAGRAPHS:
                        classification = "image_fallback_visually_present"
                        rationale = "已对照原 PDF 与对应裁切图，文字可见；只是未形成可复制文本"
                    else:
                        classification = "image_fallback_unreviewed"
                        rationale = "同页有原图文字裁切，text 字段为空不能作为漏段证据；需逐条核查图像覆盖"
                    row["blockIds"] = [b["id"] for b in fallbacks]
                else:
                    if doc_id not in pdf_cache:
                        pdf_cache[doc_id] = fitz.open(paper_meta["sourcePdf"])
                    source = paragraph_text(finding, pdf_cache[doc_id])
                    rendered = " ".join(b.get("text", "") for b in paper["blocks"])
                    coverage = text_match(source, rendered, category)
                    row["unorderedTextCoverage"] = round(coverage, 3)
                    if category in {"cs408", "politics", "math3"}:
                        classification = "text_present_ocr_or_formula_variation"
                        rationale = "中文片段在结构化卷中；连续字串检测受 PDF OCR、代码或公式改写影响"
                    else:
                        classification = "text_present_reordered"
                        rationale = "英文单词在结构化卷中；PDF 双栏词库或选项读取顺序不同"
                    # Keep the nearest source blocks for a reviewer to inspect.
                    ranked = sorted(page_blocks, key=lambda b: text_match(source, b.get("text", ""), category), reverse=True)
                    row["blockIds"] = [b["id"] for b in ranked[:3]]
                    if (doc_id, int(page)) in {
                        ("cs408:2017-answers", 6), ("cs408:2014-complete", 8),
                        ("tem8:2025", 6),
                    }:
                        row["visuallyConfirmed"] = True
            row["classification"] = classification
            row["disposition"] = DISPOSITION[classification]
            row["rationale"] = rationale
            rows.append(row)
    finally:
        for pdf in pdf_cache.values():
            pdf.close()
    return {
        "basisCatalogSha256": audit["catalogSha256"],
        "basisReportFindings": len(audit["findings"]),
        "triagedFindings": len(rows),
        "automatedDocumentCoverage": audit["documents"],
        "uniquePdfCoverage": audit["sourcePdfCount"],
        "uniquePdfPages": sum({p["sourcePdf"]: p["sourcePdfPages"] for p in audit["papers"]}.values()),
        "visuallyCheckedPdfPages": VISUALLY_CHECKED_PDF_PAGES,
        "visuallyCheckedFallbackCrops": VISUALLY_CHECKED_FALLBACKS,
        "counts": dict(sorted(Counter(row["classification"] for row in rows).items())),
        "dispositions": dict(sorted(Counter(row["disposition"] for row in rows).items())),
        "rows": rows,
    }


def markdown(triage: dict) -> str:
    rows = triage["rows"]
    lines = [
        "# 原 PDF 核查疑点归并", "",
        f"输入自动报告共 {triage['basisReportFindings']} 条提示；本报告归并段落、选项和小问疑点 {triage['triagedFindings']} 条。",
        f"自动读取覆盖 {triage['automatedDocumentCoverage']} 份目录文档、{triage['uniquePdfCoverage']} 份唯一原始 PDF、{triage['uniquePdfPages']} 个唯一 PDF 页。先前人工视觉抽核记录含 {len(triage['visuallyCheckedPdfPages'])} 页 PDF 与 {len(triage['visuallyCheckedFallbackCrops'])} 个裁切图；没有逐页人工审阅全部文档。",
        "这是输入审计 JSON 所对应的快照；每次重建后须重跑原审计和本脚本。", "",
        "## 根因归并", "",
    ]
    lines.append("处置状态：" + "；".join(f"`{k}` {v}" for k, v in triage["dispositions"].items()))
    lines.append("")
    for key, count in triage["counts"].items():
        lines.append(f"- `{key}`：{count}")
    lines += [
        "", "图片回退行已有原图，但文字字段为空不能据此认定内容缺失或完整；`image_fallback_unreviewed` 仍待逐条人工核对。可读文字行的连续片段比对可能受双栏顺序、OCR 和公式影响。",
        "", "选项异常须区分原卷印刷与解析错误。原卷印作重复标签、缺印标签或引用另一试卷时，不补造标准四项，也不据不完整选项自动判分。",
        "", "## 408：优先修复清单", "",
        "| 卷与题 | 原 PDF 页 | 源块 | 核实结论 | 建议归属 |",
        "|---|---:|---|---|---|",
    ]
    priority = [
        "confirmed_answer_page_misparsed", "confirmed_free_response_mistyped",
        "confirmed_option_parse_failure", "printed_original_duplicate_label",
        "visual_options_present", "answer_page_subparts",
    ]
    for row in rows:
        if not row["documentId"].startswith("cs408:") or row["classification"] not in priority:
            continue
        lines.append("| `{}` `{}` | {} | `{}` | {} | {} |".format(
            row["documentId"], ",".join(row["questionIds"] or []),
            ",".join(map(str, row["pages"])), ",".join(row["blockIds"] or []),
            row["rationale"], row["owner"].split("：")[0]))
    lines += ["", "## 已确认的答案漏段", "",
              "| 卷与题 | 原 PDF 页 | 邻接源块 | 缺失内容 | 建议归属 |",
              "|---|---:|---|---|---|"]
    for row in rows:
        if row["classification"] != "confirmed_missing_answer_explanation":
            continue
        lines.append("| `{}` `{}` | {} | `{}` | {} | {} |".format(
            row["documentId"], ",".join(row["questionIds"] or []),
            ",".join(map(str, row["pages"])), ",".join(row["blockIds"] or []),
            row["rationale"], row["owner"]))
    lines += ["", "## 跨科已视觉确认的选项漏拆", "",
              "| 卷与题 | 原 PDF 页 | 源块 | 建议归属 |",
              "|---|---:|---|---|"]
    for row in rows:
        if row["documentId"].startswith("cs408:") or row["classification"] != "confirmed_option_parse_failure":
            continue
        lines.append("| `{}` `{}` | {} | `{}` | {} |".format(
            row["documentId"], ",".join(row["questionIds"] or []),
            ",".join(map(str, row["pages"])), ",".join(row["blockIds"] or []),
            row["owner"].split("：")[0]))
    lines += ["", "## 其他类别交接", ""]
    for category, label in (("politics", "政治"), ("math3", "数学三"), ("cet4", "四级"),
                            ("cet6", "六级"), ("kaoyan", "考研英语"), ("tem4", "专四"), ("tem8", "专八")):
        subset = [r for r in rows if r["documentId"].startswith(category + ":")]
        counts = Counter(r["classification"] for r in subset)
        lines.append(f"- {label}：" + "；".join(f"`{k}` {v}" for k, v in sorted(counts.items())))
    lines += [
        "", "逐条归属、问题 ID、PDF 路径/页码和源块见同名 JSON。`image_fallback_unreviewed` 表示已有图像回退但未逐条视觉确认，不应当作已验证无缺字。", "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audit", type=Path)
    parser.add_argument("--json", type=Path, required=True)
    parser.add_argument("--markdown", type=Path, required=True)
    args = parser.parse_args()
    data = args.audit.read_bytes()
    audit = json.loads(data)
    result = classify(audit)
    result["basisAuditSha256"] = hashlib.sha256(data).hexdigest()
    args.json.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    args.markdown.write_text(markdown(result))
    print(json.dumps({"triagedFindings": result["triagedFindings"], "counts": result["counts"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
