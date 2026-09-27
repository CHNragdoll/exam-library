#!/usr/bin/env python3
"""Build additive, source-traceable structured exam data and reading pages."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from copy import deepcopy
from html import escape
import json
import os
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit
from xml.etree import ElementTree

from bs4 import BeautifulSoup, NavigableString, Tag

sys.path.insert(0, str(Path(__file__).resolve().parent))
from kaoyan_matching_cards import ORDERING_PAPERS, TABLE_PAPERS, ordering_cards, table_cards


ROOT = Path(__file__).resolve().parents[1] / "data/sources/exam-library"
OUT = ROOT / "structured"
SCHEMA = "exam-paper.v1"
PROFILES = {
    "kaoyan": ("考研英语", "english-kaoyan", "考研英语试卷"),
    "cet4": ("大学英语四级", "english-cet4", "大学英语四级试卷"),
    "cet6": ("大学英语六级", "english-cet6", "大学英语六级试卷"),
    "tem4": ("英语专业四级", "english-tem4", "英语专业四级试卷"),
    "tem8": ("英语专业八级", "english-tem8", "英语专业八级试卷"),
    "cs408": ("408 计算机统考", "cs408", "408 计算机统考试卷"),
    "math3": ("考研数学三", "math3", "考研数学三试卷"),
    "politics": ("考研政治", "politics", "考研政治试卷"),
}
QUESTION_RE = re.compile(r"^\s*(?:[（(]\s*(\d{1,3})\s*[）)]|(\d{1,3})\s*[.．、])")
BARE_QUESTION_RE = re.compile(r"^\s*(\d{1,3})\s*[.．、]")
NUMBERED_FIRST_OPTION_RE = re.compile(r"^\s*\d{1,3}\s*[.．、]\s*([A-E])\s*[)）.．、]\s*(.+)$")
LABEL_RE = re.compile(r"[（(]?\s*([A-E])\s*[)）.．、]?")
ANSWER_RE = re.compile(r"【(?:参考|标准)?答案】\s*([A-E](?:\s*[,，、]\s*[A-E]){1,4}|[A-E]{1,5})")
POLITICS_ESSAY_ANSWER_RE = re.compile(r"^\s*\d{2}[.．、]\s*【(?:标准)?答案】\s*$")
CS408_SOLUTION_RE = re.compile(r"(?<!\S)解答[：:]\s*")
CS408_PRINTED_CHOICE_RE = re.compile(r"^\s*(\d{1,3})\s*[.．、]\s*([A-E])(?=\s|[。.．、，,；;：:]|解析|$)")
CS408_ANSWER_MARKER_RE = re.compile(r"(?:解析[：:]|解答[：:]|【解析】)")
CS408_SPACED_KEY_RE = re.compile(r"(?<![A-Za-z0-9])(\d{1,2})\s+([A-E])(?=\s|$)")
NUMBERED_LETTER_RE = re.compile(r"(?:[（(]\s*(\d{1,3})\s*[）)]|(\d{1,3})\s*[.．、])\s*([A-E])(?=[.。\s（(]|$)")
NUMBERED_MATH_RE = re.compile(r"[（(]\s*(\d{1,3})\s*[）)]")
MATH_TEX_RE = re.compile(r"\\\((?:.|\n)*?\\\)|\\\[(?:.|\n)*?\\\]")
MATH_OLD_MAIN_RE = re.compile(r"^\s*(十四|十三|十二|十一|十|九|八|七|六|五|四|三)\s*[、.．](?!\s*[（(]续[）)])")
MATH_OLD_MAIN_NUMBERS = {name: number for number, name in enumerate(
    ("一", "二", "三", "四", "五", "六", "七", "八", "九", "十", "十一", "十二", "十三", "十四"), 1)}
# These continuation pages prefix a numbered item with its section label.
# Each prefix was checked against the original PDF's physical page.
MATH_OLD_PREFIXED_ITEMS = {
    ("math3:1995-questions", "54"): ("二、（5）【同试卷 IV 第二、（5）题】", "5"),
    ("math3:1996-questions", "56"): ("二、（4）设有任意两个", "4"),
    ("math3:1996-questions", "58"): ("一、（5）一实习生", "5"),
}
POLITICS_2022_SPLIT_STEM_BLOCKS = {
    "27": ["b-7-11", "b-8-1"],
    "34": ["b-9-11", "b-10-1"],
    "35": ["b-10-2", "b-11-1", "b-12-1"],
    "36": ["b-12-2", "b-13-1"],
    "37": ["b-13-2", "b-14-1", "b-15-1"],
    "38": ["b-15-2", "b-16-1"],
}
# PDF text extraction often joins a Chinese option value directly to the next
# Latin label (e.g. “用完B.”); a generic word boundary misses that label.
INLINE_OPTION_RE = re.compile(r"(?<![A-Za-z0-9])([A-E])\s*([.．、])(?=\s|\S)")
POLITICS_CONTINUATION_RE = re.compile(r"^第\s*(?P<number>\d{1,3})\s*题\s*[（(]续[）)]\s*[:：]?\s*")
POLITICS_PAGE_ARTIFACT_RE = re.compile(r"\s+(?P<marker>-\s*(?P<number>\d{1,2})\s*[-•·])\s*$")
POLITICS_SUBQUESTION_RE = re.compile(r"[（(]\s*(?P<number>[1-9])\s*[）)]")
POLITICS_STANDALONE_SUBQUESTION_RE = re.compile(
    r"^\s*(?:[（(]\s*(?P<number>[1-9])\s*[）)]|(?P<circled>[①②③④⑤]))"
)
POLITICS_ANSWER_NOTE_RE = re.compile(r"答题思路\s*[:：]")
# These paragraphs are numbered explanations printed in the question PDF,
# rather than requests to the candidate. Keep their source blocks intact.
POLITICS_NUMBERED_EXPLANATION_PREFIXES = {
    "politics:2007-questions": (
        "从地图中可以看出，中东地处", "中东地区是世界能源的供给中心",
        "错综复杂的民族和宗教问题也是",
    ),
    "politics:2008-questions": (
        "人是自然属性和社会属性的统一体", "矛盾是客观、普遍存在的",
    ),
}
POLITICS_UNNUMBERED_QUESTIONS = {
    # The printed PDF has the table and both prompts between 35 and 37,
    # without a 36 label (page 4).
    ("politics:2004-questions", 4, 10): "36",
    # The printed PDF has a separate stem and A-D choices between 24 and 26,
    # without a 25 label (page 3).
    ("politics:2011-questions", 3, 12): "25",
}
# The source PDF's selectable text has the same OCR error as the reflow source;
# its visible page 7 reads 二〇二〇年 and 二〇三五年.
POLITICS_VERIFIED_CORRECTIONS = {
    ("politics:2023-questions", 7): (
        ("二。二O年", "二〇二〇年"),
        ("二O三五年", "二〇三五年"),
    ),
}
EMAIL_GREETING_RE = re.compile(r"^(?:Dear|Hi)\s+[^,]{1,80},")
EMAIL_SIGNOFF_RE = re.compile(r"\bYours,\s+Paul\b")
# These source PDFs append answer material to the question paper. The boundary
# is a physical PDF page, not a section heading: some headers are plain <p>s.
# Keep the printed marker as a guard against a shifted/replaced source file.
EMBEDDED_ENGLISH_ANSWER_PAGES = {
    "cet4:2015-06-01": (9, "2015 年6 月大学英语四级考试真题答案与详解"),
    "cet6:2012-06-01": (20, "2012 年 6 月大学英语六级 (CET-6) 参考答案"),
    "cet6:2012-12-01": (16, "2012 年 12 月大学英语六级 (CET-6) 参考答案"),
    "cet6:2012-12-02": (16, "2012 年 12 月大学英语六级 (CET-6) 参考答案"),
    "cet6:2012-12-03": (15, "2012 年 12 月大学英语六级 (CET-6) 参考答案"),
}
ENGLISH_PRINTED_CHOICE_RE = re.compile(r"^\s*([A-D])\s*[)）.．]")
ENGLISH_EXPLICIT_CHOICE_RE = re.compile(r"(?:故(?:本题)?答案为|故选|参考答案[：:]\s*)\s*([A-D])\s*[)）.．]?")
ENGLISH_NUMBERED_KEY_RE = re.compile(r"^\s*(\d{1,2})\s*[,，]\s*([A-D])\s*[).．]")
ENGLISH_ANSWER_PHRASE_RE = re.compile(r"答案\s*[：:]\s*(.+?)(?=【(?:解析|点评|精析)】|$)")
ENGLISH_TRANSCRIPT_QUESTION_RE = re.compile(r"^Q\s*(\d{1,2})(?:[.．?？\s])")
CHINESE_SECTION_RE = re.compile(r"^(?:第[一二三四五六七八九十]+[部章]|[一二三四五六七八九十]+[、.．]|\d+\s*[、.．]\s*(?:单项|多项|选择|填空|解答))")
PART_RE = re.compile(r"^(?i:part)\s*([A-ZⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]+)(?=\s|$)")
SECTION_RE = re.compile(r"^(?i:section)\s+([A-ZⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]+)(?=\s|$)")
PASSAGE_RE = re.compile(r"^(?:Text\s+\d+|Passage\s+(?:One|Two|Three|Four|Five|\d+)|Conversation\s+(?:One|Two|Three|Four|Five|\d+))\b", re.I)
IGNORE_SCHEMES = ("data:", "http:", "https:", "mailto:", "javascript:", "#")

# Coordinates are in the original SVG viewBox. These three printed option
# figures contain four choices in one image; keep that image intact and expose
# source-backed regions for the practice interface. Each entry was checked
# against the visible PDF figure and its matching reflow asset.
FIGURE_OPTION_REGIONS = {
    ("cs408:2009-complete", "4"): {
        "asset": "2009-complete-p001-b007.svg", "size": (373, 86),
        "regions": ((0, 0, 72, 86), (72, 0, 84, 86),
                    (156, 0, 73, 86), (229, 0, 72, 86)),
        "sourceLabels": ("A.", "B.", "C.", "D."),
    },
    ("cs408:2017-questions", "8"): {
        "asset": "2017-questions-p001-b013.svg", "size": (402, 139),
        "regions": ((0, 0, 200, 67), (200, 0, 202, 67),
                    (0, 67, 200, 72), (200, 67, 202, 72)),
        "sourceLabels": ("A.", "B.", "C.", "D."),
    },
    ("math3:2009-questions", "4"): {
        "asset": "page-051-07.svg", "size": (304, 158),
        "regions": ((0, 0, 152, 79), (152, 0, 152, 79),
                    (0, 79, 152, 79), (152, 79, 152, 79)),
        "sourceLabels": ("（A）", "（B）", "（C）", "（D）"),
    },
}


def source_path(doc: dict) -> Path:
    return (ROOT / doc["reflow"]).resolve()


def rel(target: Path, page: Path) -> str:
    return os.path.relpath(target, page.parent).replace(os.sep, "/")


def normalized_number(value: str) -> str | None:
    match = QUESTION_RE.match(value)
    return str(int(next(g for g in match.groups() if g))) if match else None


def is_old_math_paper(doc: dict) -> bool:
    return doc["category"] == "math3" and 1997 <= doc["year"] <= 2003


def is_dual_form_math_paper(doc: dict) -> bool:
    return doc["category"] == "math3" and 1993 <= doc["year"] <= 1996


def uses_old_math_problem_boundaries(doc: dict) -> bool:
    return doc["category"] == "math3" and 1987 <= doc["year"] <= 2003


def old_math_main_heading(doc: dict, text: str, form: str | None) -> re.Match | None:
    """Distinguish numbered main problems from the early calculation sections."""
    if not uses_old_math_problem_boundaries(doc):
        return None
    match = MATH_OLD_MAIN_RE.match(text)
    if not match:
        return None
    year, label = doc["year"], match.group(1)
    if (year <= 1990 and label == "三") or (year == 1988 and form == "IV" and label == "四"):
        return None
    return match


def plain(element: Tag) -> str:
    copy = deepcopy(element)
    for node in copy.select("mjx-container, pre.tex-source"):
        node.decompose()
    for node in copy.select(".formula[data-tex]"):
        node.string = "\\(" + node.get("data-tex", "") + "\\)"
    return " ".join(copy.get_text(" ", strip=True).split())


def normalize_choice_answer(value: str) -> str:
    """Retain the printed choice letters, dropping only their separators."""
    return re.sub(r"[\s,，、]", "", value)


def section_level_for(value: str, category: str) -> int | None:
    """Classify printed exam headings without mistaking ordinary prose for TOC nodes."""
    if CHINESE_SECTION_RE.match(value):
        return 0
    if PASSAGE_RE.match(value):
        return 2
    part = PART_RE.match(value)
    section = SECTION_RE.match(value)
    if category == "kaoyan":
        if section and section.group(1) in {"I", "II", "III", "IV", "V", "Ⅰ", "Ⅱ", "Ⅲ", "Ⅳ", "Ⅴ"}:
            return 0
        if part and len(part.group(1)) == 1 and part.group(1) in "ABCDEFGH":
            return 1
    else:
        if part:
            return 0
        if section:
            return 1
    return None


def portable_html(element: Tag, original: Path, target: Path) -> str:
    """Small rich-text form for downstream clients; formulas retain their TeX."""
    copy = deepcopy(element)
    for node in copy.select("mjx-container"):
        node.decompose()
    for node in copy.select(".formula[data-tex]"):
        node.clear()
        node.string = "\\(" + node.get("data-tex", "") + "\\)"
    rewrite_links(copy, original, target)
    return str(copy)


def role_for(element: Tag, doc: dict) -> str:
    classes = set(element.get("class", []))
    if "page-label" in classes:
        return "page_label"
    if "tex-source" in classes:
        return "tex_source"
    if "choice-row" in classes:
        return "choices"
    if "choice-scroll" in classes and element.select_one(":scope > .choice-row"):
        return "choices"
    if classes & {"options", "choices", "math-options"}:
        return "choices"
    if "question" in classes:
        return "question"
    if element.name in {"h1", "h2", "h3"}:
        value = plain(element)
        if doc["kind"] == "answers" and normalized_number(value):
            return "question"
        return "section" if section_level_for(value, doc["category"]) is not None else "heading"
    if element.name in {"img", "figure", "table"}:
        return "figure"
    return "content"


def options_from(element: Tag) -> list[dict]:
    classes = set(element.get("class", []))
    if "choice-scroll" in classes:
        row = element.select_one(":scope > .choice-row")
        return options_from(row) if row else []
    if "choice-row" in classes:
        items = element.select(":scope > .choice-item")
        marker = "strong"
    elif "math-options" in classes:
        items = element.select(":scope > .math-option")
        marker = ".math-option-label"
    elif "options" in classes:
        items = element.select(":scope > li")
        marker = ".option-label"
    elif "choices" in classes:
        items = element.select(":scope > .choice")
        marker = "b"
    else:
        return []
    result = []
    for item in items:
        label_node = item.select_one(marker)
        if not label_node:
            continue
        source_label = label_node.get_text(" ", strip=True)
        match = LABEL_RE.fullmatch(source_label)
        if not match:
            continue
        letter = match.group(1)
        value = deepcopy(item)
        value.select_one(marker).decompose()
        result.append({"label": letter + ".", "sourceLabel": source_label, "text": plain(value)})
    # Keep the source sequence until the question has recorded it. The
    # normalized A-E display order is applied after merging choice blocks.
    return result


def add_figure_options(doc: dict, question: dict, blocks: list[dict],
                       original: Path, json_path: Path) -> None:
    """Map a verified combined source figure to four selectable source regions."""
    mapping = FIGURE_OPTION_REGIONS.get((doc["id"], question["number"]))
    if not mapping:
        return
    if question["options"]:
        raise ValueError(f"Figure choices overlap extracted choices: {doc['id']} {question['number']}")
    figures = [block for block in blocks if block["id"] in question["sourceBlocks"]
               and block["role"] == "figure" and len(block["images"]) == 1
               and Path(block["images"][0]).name == mapping["asset"]]
    if len(figures) != 1:
        raise ValueError(f"Expected one option figure: {doc['id']} {question['number']}")
    figure = figures[0]
    asset = (original.parent / figure["images"][0]).resolve()
    svg = ElementTree.parse(asset).getroot()
    width, height = mapping["size"]
    if (svg.attrib.get("viewBox") != f"0 0 {width} {height}" or
            svg.attrib.get("width") != str(width) or svg.attrib.get("height") != str(height)):
        raise ValueError(f"Source figure dimensions changed: {asset}")
    src = rel(asset, json_path)
    for index, (label, region) in enumerate(zip("ABCD", mapping["regions"]), 1):
        x, y, crop_width, crop_height = region
        if min(x, y) < 0 or min(crop_width, crop_height) <= 0 or x + crop_width > width or y + crop_height > height:
            raise ValueError(f"Invalid figure choice region: {doc['id']} {label}")
        question["options"].append({
            "label": f"{label}.", "sourceLabel": mapping["sourceLabels"][index - 1],
            "text": "", "sourceOrder": index,
            "image": {"src": src, "sourceBlockId": figure["id"],
                      "alt": f"原卷选项 {label} 图",
                      "crop": {"x": x, "y": y, "width": crop_width, "height": crop_height,
                               "sourceWidth": width, "sourceHeight": height}},
        })
    question["status"] = "complete"


def rewrite_links(element: Tag, original: Path, target: Path) -> None:
    for node in [element, *element.find_all(True)]:
        for attr in ("src", "href", "poster"):
            value = node.get(attr)
            if not value or value.startswith(IGNORE_SCHEMES):
                continue
            parsed = urlsplit(value)
            if parsed.scheme or parsed.netloc or not parsed.path:
                continue
            resolved = (original.parent / parsed.path).resolve()
            node[attr] = rel(resolved, target) + ("?" + parsed.query if parsed.query else "") + ("#" + parsed.fragment if parsed.fragment else "")


def email_lines(value: str, *, greeting: bool = False, signoff: bool = False,
                split_signature: bool = False) -> tuple[list[dict], str]:
    """Extract letter lines for the reusable presentation model."""
    pieces: list[dict] = []
    if greeting:
        match = EMAIL_GREETING_RE.match(value)
        if match:
            pieces.append({"role": "greeting", "text": match.group().strip()})
            value = value[match.end():].strip()
    if signoff:
        match = EMAIL_SIGNOFF_RE.search(value)
        if match:
            if value[:match.start()].strip():
                pieces.append({"role": "body", "text": value[:match.start()].strip()})
            pieces.extend(({"role": "closing", "text": "Yours,"}, {"role": "signature", "text": "Paul"}))
            value = value[match.end():].strip()
        elif split_signature:
            match = re.match(r"Paul(?=\s|$)", value)
            assert match, value
            pieces.append({"role": "signature", "text": "Paul"})
            value = value[match.end():].strip()
    elif value.endswith("Yours,"):
        body = value[:-len("Yours,")].strip()
        if body:
            pieces.append({"role": "body", "text": body})
        pieces.append({"role": "closing", "text": "Yours,"})
        value = ""
    elif value:
        pieces.append({"role": "body", "text": value})
        value = ""
    return pieces, value


def email_instructions(value: str) -> list[dict]:
    """Separate the two printed writing instructions."""
    match = re.search(r"ANSWER SHEET\.", value)
    parts = [value[:match.end()].strip(), value[match.end():].strip()] if match else [value.strip()]
    return [{"text": part, "strongPrefix": "Do not" if part.startswith("Do not") else None}
            for part in parts if part]


def email_presentation(element: Tag, mode: str, signoff_right: bool,
                       split_signature: bool = False) -> dict:
    value = plain(element)
    lines: list[dict] = []
    if mode == "after":
        trailing = value
    else:
        lines, trailing = email_lines(value, greeting=mode in {"start", "single"},
                                      signoff=mode in {"end", "single"},
                                      split_signature=split_signature)
    instructions = email_instructions(trailing) if trailing else []
    return {
        "version": 1, "layoutKind": "email", "segment": mode,
        "framePart": "none" if mode == "after" else mode,
        "lines": lines, "signoffAlignment": "right" if signoff_right else "left",
        "instructionsOutsideFrame": bool(instructions),
        "instructions": instructions,
    }


def display_email_block(presentation: dict) -> str:
    result = ""
    if presentation["lines"]:
        lines = "".join(
            f'<p class="email-line email-{line["role"]}">{escape(line["text"])}</p>'
            for line in presentation["lines"]
        )
        result = f'<div class="email-card-part">{lines}</div>'
    if presentation["instructions"]:
        parts = []
        for instruction in presentation["instructions"]:
            content = escape(instruction["text"])
            prefix = instruction["strongPrefix"]
            if prefix and content.startswith(escape(prefix)):
                content = f"<strong>{escape(prefix)}</strong>" + content[len(escape(prefix)):]
            parts.append(f"<p>{content}</p>")
        result += '<div class="email-instructions">' + "".join(parts) + '</div>'
    return result


def math_option_width(element: Tag) -> float:
    """Estimate visible width in em; MathJax SVG reports its own width in ex."""
    def width(node: Tag | NavigableString) -> float:
        if isinstance(node, NavigableString):
            return sum(1 if ord(char) > 0x7f else .55 for char in str(node).strip())
        if "formula" in node.get("class", []):
            svg = node.select_one("mjx-container > svg[width]")
            match = re.fullmatch(r"([\d.]+)ex", svg["width"]) if svg else None
            return float(match.group(1)) / 2 if match else 20
        if node.name in {"img", "table", "svg"}:
            return 20
        return sum(width(child) for child in node.contents)

    return width(element)


def trim_math_option_stop(content: Tag) -> None:
    """Drop only a trailing printed full stop, leaving formulas and source data intact."""
    for node in reversed(list(content.descendants)):
        if not isinstance(node, NavigableString) or node.parent is None:
            continue
        if node.find_parent(("mjx-container", "svg", "pre")):
            continue
        value = str(node)
        if not value.strip():
            continue
        fixed = re.sub(r"(?<![.．。])[.．。]\s*$", "", value)
        if fixed != value:
            node.replace_with(fixed)
        break


def display_math_question(copy: Tag) -> None:
    """Align option rows with the stem and normalize only its final full stop."""
    if copy.contents and isinstance(copy.contents[0], NavigableString):
        first = copy.contents[0]
        match = QUESTION_RE.match(str(first))
        if match:
            number = next(group for group in match.groups() if group)
            marker = BeautifulSoup("", "html.parser").new_tag("span")
            marker["class"] = "math-question-number"
            marker["data-digits"] = str(len(number))
            marker.string = match.group(0)
            remainder = str(first)[match.end():]
            first.replace_with(marker)
            marker.insert_after(remainder)
    for node in reversed(list(copy.descendants)):
        if not isinstance(node, NavigableString) or node.parent is None:
            continue
        if node.find_parent(("mjx-container", "svg", "pre")):
            continue
        value = str(node)
        if not value.strip():
            continue
        fixed = re.sub(r"。(?=\s*$)", ".", value)
        if fixed != value:
            node.replace_with(fixed)
        break


def politics_presentation(doc: dict, text: str, page_index: int, role: str,
                          section_kind: str, current_number: str | None) -> dict | None:
    """Describe source-preserving political-paper cleanup for every client."""
    if doc["category"] != "politics" or doc["kind"] != "questions":
        return None
    display = text
    presentation: dict = {"version": 1, "layoutKind": "politics"}
    continuation = POLITICS_CONTINUATION_RE.match(display)
    if continuation and continuation["number"] == current_number:
        presentation["continuation"] = {
            "questionNumber": current_number, "sourceMarker": continuation.group().strip(),
        }
        display = display[continuation.end():].lstrip()
    artifact = POLITICS_PAGE_ARTIFACT_RE.search(display)
    if artifact and int(artifact["number"]) == page_index:
        presentation["pageArtifacts"] = [{
            "kind": "printed_page_number", "sourceText": artifact["marker"],
            "sourcePageIndex": page_index,
        }]
        display = display[:artifact.start()].rstrip()
    corrections = []
    for source, corrected in POLITICS_VERIFIED_CORRECTIONS.get((doc["id"], page_index), ()):
        if source in display:
            corrections.append({
                "sourceText": source, "displayText": corrected,
                "evidence": {"kind": "original_pdf_visual", "sourceDocumentId": doc["id"],
                             "sourcePageIndex": page_index},
            })
            display = display.replace(source, corrected)
    if corrections:
        presentation["corrections"] = corrections
    if section_kind == "other" and role in {"question", "content"}:
        # The 2022 source appends numbered answer notes after its two printed
        # prompts in the same block. Only the region before 答题思路 is a prompt.
        answer_note = POLITICS_ANSWER_NOTE_RE.search(display)
        prompt_region = display[:answer_note.start()] if answer_note else display
        matches = list(POLITICS_SUBQUESTION_RE.finditer(prompt_region))
        # A pair of sequential prompts is much less likely to be a numbered
        # citation or a list embedded in source material.
        if len(matches) >= 2 and [m["number"] for m in matches] == [str(n) for n in range(1, len(matches) + 1)]:
            presentation["subquestions"] = [
                {"number": match["number"], "text": prompt_region[
                    match.start():matches[i + 1].start() if i + 1 < len(matches) else len(prompt_region)
                ].strip()}
                for i, match in enumerate(matches)
            ]
            for match in reversed(matches):
                if display[:match.start()].strip():
                    display = display[:match.start()].rstrip() + "\n" + display[match.start():]
        elif match := POLITICS_STANDALONE_SUBQUESTION_RE.match(prompt_region):
            body = prompt_region[match.end():].strip()
            explanations = POLITICS_NUMBERED_EXPLANATION_PREFIXES.get(doc["id"], ())
            if body and not any(body.startswith(prefix) for prefix in explanations):
                number = match["number"] or str("①②③④⑤".index(match["circled"]) + 1)
                presentation["subquestions"] = [{"number": number, "text": prompt_region.strip()}]
    if len(presentation) == 2:
        return None
    presentation["displayText"] = display
    return presentation


def display_politics_block(copy: Tag, presentation: dict) -> None:
    """Apply only annotated edits to a copy; source HTML and JSON stay intact."""
    nodes = [node for node in copy.descendants if isinstance(node, NavigableString) and node.parent
             and not node.find_parent(("svg", "mjx-container", "pre", "script", "style"))]
    if not nodes:
        return
    continuation = presentation.get("continuation")
    if continuation:
        node = nodes[0]
        node.replace_with(POLITICS_CONTINUATION_RE.sub("", str(node), count=1).lstrip())
    for correction in presentation.get("corrections", []):
        for node in list(copy.descendants):
            if (isinstance(node, NavigableString) and node.parent
                    and not node.find_parent(("svg", "mjx-container", "pre", "script", "style"))
                    and correction["sourceText"] in str(node)):
                node.replace_with(str(node).replace(correction["sourceText"], correction["displayText"]))
    if presentation.get("pageArtifacts"):
        nodes = [node for node in copy.descendants if isinstance(node, NavigableString) and node.parent
                 and not node.find_parent(("svg", "mjx-container", "pre", "script", "style"))]
        for node in reversed(nodes):
            if POLITICS_PAGE_ARTIFACT_RE.search(str(node)):
                node.replace_with(POLITICS_PAGE_ARTIFACT_RE.sub("", str(node)).rstrip())
                break
    if presentation.get("subquestions"):
        remaining = [item["number"] for item in presentation["subquestions"]]
        in_answer_notes = False
        for node in list(copy.descendants):
            if not remaining or in_answer_notes:
                break
            if not isinstance(node, NavigableString) or node.parent is None or node.find_parent(("svg", "pre", "script", "style")):
                continue
            value = str(node)
            answer_note = POLITICS_ANSWER_NOTE_RE.search(value)
            prompt_region = value[:answer_note.start()] if answer_note else value
            matches = []
            for match in POLITICS_SUBQUESTION_RE.finditer(prompt_region):
                if match["number"] == remaining[0]:
                    matches.append(match)
                    remaining.pop(0)
                    if not remaining:
                        break
            in_answer_notes = bool(answer_note)
            if not matches:
                continue
            last_end = 0
            for match in matches:
                before = value[last_end:match.start()]
                if before:
                    node.insert_before(NavigableString(before))
                if (before.strip() or node.previous_sibling and str(node.previous_sibling).strip()):
                    br = BeautifulSoup("", "html.parser").new_tag("br")
                    br["class"] = "politics-subquestion-break"
                    node.insert_before(br)
                node.insert_before(NavigableString(match.group()))
                last_end = match.end()
            rest = value[last_end:]
            if rest:
                node.insert_before(NavigableString(rest))
            node.extract()


def display_block(element: Tag, original: Path, target: Path, presentation: dict | None = None,
                  math_questions: bool = False) -> str:
    if presentation and presentation["layoutKind"] == "email":
        return display_email_block(presentation)
    copy = deepcopy(element)
    if presentation and presentation["layoutKind"] == "politics":
        display_politics_block(copy, presentation)
    choice_rows = ([copy] if "choice-row" in copy.get("class", []) else []) + copy.select(".choice-row")
    for row in choice_rows:
        choices = row.select(":scope > .choice-item")
        lengths = [len(plain(item)) for item in choices]
        if len(lengths) == 4 and max(lengths) <= 22 and sum(lengths) <= 70:
            row["class"] = [*row.get("class", []), "compact-choice-row"]
    math_rows = ([copy] if "math-options" in copy.get("class", []) else []) + copy.select(".math-options")
    for row in math_rows:
        items = row.select(":scope > .math-option")
        contents = [item.select_one(":scope > .math-option-content") for item in items]
        if len(contents) == 4 and all(content and math_option_width(content) <= 9 for content in contents):
            row["class"] = [*row.get("class", []), "compact-math-options"]
        for content in contents:
            if content:
                trim_math_option_stop(content)
    option_selectors = {"choice-row": ".choice-item", "math-options": ".math-option",
                        "options": "li", "choices": ".choice"}
    for class_name, selector in option_selectors.items():
        if class_name not in copy.get("class", []):
            continue
        items = copy.select(f":scope > {selector}")
        def option_order(item: Tag) -> int:
            label_node = item.select_one("strong, .math-option-label, .option-label, b")
            match = LABEL_RE.fullmatch(label_node.get_text(" ", strip=True)) if label_node else None
            return "ABCDE".index(match.group(1)) if match else 99
        for item in sorted(items, key=option_order):
            item.extract()
            copy.append(item)
    for node in copy.select(".choice-item > strong, .math-option-label, .options > li > .option-label, .choices > .choice > b"):
        match = LABEL_RE.fullmatch(node.get_text(" ", strip=True))
        if match:
            node.string = match.group(1) + "."
    if "question" in copy.get("class", []):
        for node in list(copy.descendants):
            if isinstance(node, NavigableString) and node.parent and node.parent.name not in {"svg", "path", "style", "script"}:
                fixed = INLINE_OPTION_RE.sub(lambda m: m.group(1) + ".", str(node))
                if fixed != str(node):
                    node.replace_with(fixed)
        if math_questions:
            display_math_question(copy)
    rewrite_links(copy, original, target)
    return str(copy)


def build_one(doc: dict) -> dict:
    original = source_path(doc)
    if not original.is_file():
        raise FileNotFoundError(original)
    stem = original.stem
    folder = OUT / "papers" / doc["category"]
    folder.mkdir(parents=True, exist_ok=True)
    json_path = folder / (stem + ".json")
    html_path = folder / (stem + ".htm")
    soup = BeautifulSoup(original.read_text(encoding="utf-8"), "html.parser")
    reader_config_node = soup.find(id="exam-reader-config")
    reader_config = json.loads(reader_config_node.get_text()) if reader_config_node else {}
    email_signoff_right = doc["category"] == "kaoyan" and reader_config.get("emailSignoffRight") is True
    main = soup.select_one("main")
    if not main:
        raise ValueError(f"no main: {original}")
    # Inline source-position spans also carry data-source-page. Only the
    # direct page sections define the physical pages and block coordinates.
    pages = main.select(":scope > section[data-source-page]")
    if not pages:
        raise ValueError(f"no source pages: {original}")
    blocks: list[dict] = []
    questions: list[dict] = []
    toc: list[dict] = []
    rendered: list[str] = []
    current: dict | None = None
    occurrences: Counter = Counter()
    source_only = 0
    malformed = 0
    in_answer_section = doc["kind"] == "answers"
    embedded_answer = EMBEDDED_ENGLISH_ANSWER_PAGES.get(doc["id"])

    def close_question() -> None:
        nonlocal current
        if current:
            if doc["id"] == "politics:2022-questions" and current["number"] in POLITICS_2022_SPLIT_STEM_BLOCKS:
                expected = POLITICS_2022_SPLIT_STEM_BLOCKS[current["number"]]
                parts = [block for block in blocks if block["id"] in expected
                         and block["id"] in current["sourceBlocks"]
                         and block["role"] in {"question", "content"}]
                if [block["id"] for block in parts] != expected:
                    raise ValueError(f"2022 politics split stem changed: {current['number']}")
                # The PDF's page breaks fall inside Chinese words. Preserve
                # each block verbatim and join those seams without a space.
                current["stem"] = "".join(block["text"] for block in parts)
            if not current["options"] and current["sectionKind"] in {"single_choice", "multiple_choice"}:
                body = " ".join(b["text"] for b in blocks if b["id"] in current["sourceBlocks"] and b["role"] not in {"tex_source", "page_label"})
                matches = list(INLINE_OPTION_RE.finditer(body))
                printed_duplicate = doc["id"] == "cs408:2015-complete" and current["number"] == "1"
                for start in range(len(matches)):
                    group = next((candidate for size in (5, 4)
                                  if (candidate := matches[start:start + size])
                                  and ([m.group(1) for m in candidate] == list("ABCDE"[:size])
                                       or (printed_duplicate and len(candidate) == 4
                                           and [m.group(1) for m in candidate] == list("ABBD")))), None)
                    if group is None:
                        continue
                    for i, match in enumerate(group):
                        end = group[i + 1].start() if i + 1 < len(group) else len(body)
                        current["options"].append({"label": match.group(1) + ".", "sourceLabel": match.group(0).strip(),
                                                   "text": body[match.end():end].strip()})
                    current["stem"] = body[:group[0].start()].strip()
                    if printed_duplicate:
                        current["status"] = "partial"
                    break
            if doc["kind"] != "answers" and not current["options"] and current["number"] and current["sectionKind"] in {"single_choice", "multiple_choice"}:
                current["status"] = "partial"
            rendered.append("</article>")
            current = None

    section_kind = "other"
    section_title = ""
    section_level = 0
    section_stack: dict[int, str] = {}
    section_context_blocks: list[dict] = []
    section_choice_rows_seen = False
    email_pending = False
    email_open = False
    email_followup = False
    email_closing_pending = False
    math_form: str | None = None
    for page_index, page in enumerate(pages, 1):
        duplicate_cs408_page = doc["id"] == "cs408:2024-answers" and page_index == 4
        if duplicate_cs408_page:
            # The original PDF itself repeats page 3 verbatim as page 4.
            # Keep both source pages, but do not create a second Q42/Q43 or
            # attach Q41's repeated code tail to Q43.
            previous = pages[2].find_all(recursive=False)
            repeated = page.find_all(recursive=False)
            if [plain(child) for child in previous] != [plain(child) for child in repeated]:
                raise ValueError("CS408 2024 answer PDF duplicate page changed")
        if embedded_answer and page_index == embedded_answer[0]:
            page_texts = [plain(child) for child in page.find_all(recursive=False)]
            if embedded_answer[1] not in page_texts:
                raise ValueError(f"embedded answer page marker changed: {doc['id']} p{page_index}")
            close_question()
            in_answer_section = True
        page_number = page.get("data-source-page") or str(page_index)
        for child_index, child in enumerate(page.find_all(recursive=False), 1):
            role = role_for(child, doc)
            # A cloze blank at the start of a paragraph can be mislabelled as a
            # question by the source extractor. Until the option table begins,
            # it remains part of the shared passage.
            if (role == "question" and doc["category"] == "kaoyan" and
                    "Use of English" in section_title and not section_choice_rows_seen):
                role = "content"
            text = plain(child)
            if not text and not child.select_one("img, svg, table"):
                # Invisible empty wrappers carry no readable source content.
                continue
            if doc["category"] == "math3" and role == "heading":
                form_heading = re.search(r"试卷\s*(IV|V)(?=[）)（(\s]|$)", text)
                if form_heading:
                    math_form = form_heading.group(1)
            if (doc["id"] == "math3:1996-questions" and page_number == "56"
                    and role == "heading" and text == "试卷 IV（续）"):
                # The previous page already contains all of choice (3).
                # This page heading belongs to neither adjacent question.
                close_question()
            old_math = uses_old_math_problem_boundaries(doc)
            old_math_main = (old_math_main_heading(doc, text, math_form)
                             if role != "tex_source" else None)
            if (old_math_main and doc["year"] in {1994, 1995} and current
                    and current["sectionKind"] == "other"
                    and current["number"] == str(MATH_OLD_MAIN_NUMBERS[old_math_main.group(1)])
                    and re.match(r"^\s*[一二三四五六七八九十]+[、.．]\s*[（(]\d+[）)]", text)):
                # Page 49 says 九、（2） and page 53 says 十、（2）: both
                # continue the current problem rather than starting another.
                old_math_main = None
            if old_math_main:
                # These papers print problems 三、... after the two numbered
                # sections. The 1997-2003 answer sheets use the same labels.
                role = "question"
                section_kind = "other"
                section_title = ""
                section_level = 0
                section_stack = {}
            elif (old_math and role == "section" and
                  re.match(r"^二、选择题\s*[（(]续[）)]", text)):
                # A page break inside the final choice does not end it.
                role = "content"
            elif (old_math and section_kind == "other" and role == "question"
                  and current and MATH_OLD_MAIN_RE.match(current["stem"])):
                # (1)/(2) inside a Chinese-numbered problem are subquestions.
                role = "content"
            absent_printed_number = POLITICS_UNNUMBERED_QUESTIONS.get((doc["id"], page_index, child_index))
            prefixed_item = MATH_OLD_PREFIXED_ITEMS.get((doc["id"], page_number))
            if role != "tex_source" and prefixed_item and text.startswith(prefixed_item[0]):
                absent_printed_number = prefixed_item[1]
            if absent_printed_number:
                role = "question"
            if (doc["id"] == "politics:2013-questions" and page_index == 5 and
                    role == "question" and text.startswith("5.8 万元")):
                # PDF page 5 begins this continuation with an amount, not a
                # second question 5. Other questions can start "17.1971".
                role = "content"
            if (doc["category"] == "politics" and doc["kind"] == "questions" and
                    role == "section" and section_kind == "other" and current and
                    current["number"].isdigit() and int(current["number"]) >= 34):
                # Analysis material may use numbered internal headings such as
                # "一、秸秆种蘑菇". They remain inside the printed question.
                role = "content"
            promoted_numbered_content = False
            # Some PDF transcriptions put a whole numbered question in a
            # plain paragraph. Recognize only the next bare question number;
            # parenthesized (1)/(2) subparts must remain in the current stem.
            bare_number = BARE_QUESTION_RE.match(text) if role == "content" else None
            if (bare_number and current and current["recordType"] == "question"
                    and current["number"].isdigit()
                    and int(bare_number.group(1)) == int(current["number"]) + 1):
                role = "question"
                promoted_numbered_content = True
            email_mode = None
            email_split_signature = False
            if doc["category"] == "kaoyan" and doc["kind"] == "questions" and role == "section":
                email_pending = email_open = email_followup = email_closing_pending = False
            if doc["category"] == "kaoyan" and doc["kind"] == "questions" and child.name == "p":
                if "Read the following email" in text and "reply" in text:
                    email_pending, email_open, email_followup, email_closing_pending = True, False, False, False
                elif email_pending and EMAIL_GREETING_RE.match(text):
                    email_mode = "single" if EMAIL_SIGNOFF_RE.search(text) else "start"
                    email_pending = False
                    email_open = email_mode == "start"
                    email_followup = email_mode == "single"
                elif email_open:
                    email_split_signature = bool(email_closing_pending and re.match(r"Paul(?=\s|$)", text))
                    email_mode = "end" if EMAIL_SIGNOFF_RE.search(text) or email_split_signature else "middle"
                    if email_mode == "end":
                        email_open = False
                        email_closing_pending = False
                        email_followup = not bool(re.search(r"ANSWER SHEET\.", text))
                    else:
                        email_closing_pending = text.endswith("Yours,")
                elif email_followup and re.match(r"^(?:You should write|Write your answer)\b", text):
                    email_mode = "after"
                    email_followup = False
            presentation = email_presentation(child, email_mode, email_signoff_right,
                                              email_split_signature) if email_mode else None
            if doc["category"] == "politics":
                presentation = politics_presentation(
                    doc, text, page_index, role, section_kind,
                    current["number"] if current else None,
                )
            displayed_text = (presentation.get("displayText", text)
                              if presentation else text)
            if role == "question" and child.select(".paragraph-group > p"):
                # The original question block already carries PDF paragraph
                # boundaries. Keep them in the database stem as well as in
                # the structured reader, after applying verified corrections.
                visible_copy = deepcopy(child)
                if presentation and presentation["layoutKind"] == "politics":
                    display_politics_block(visible_copy, presentation)
                paragraphs = [paragraph.get_text(" ", strip=True)
                              for paragraph in visible_copy.select(".paragraph-group > p")]
                if any(paragraphs):
                    displayed_text = "\n\n".join(paragraph for paragraph in paragraphs if paragraph)
            block_id = f"b-{page_index}-{child_index}"
            block = {
                "id": block_id, "page": page_number, "sourcePageIndex": page_index,
                "sourceBlockIndex": child_index, "role": role, "text": text,
                "contentHtml": portable_html(child, original, json_path),
                "formulas": [n.get("data-tex", "") for n in child.select(".formula[data-tex]")],
                "images": [n.get("src", "") for n in child.select("img")],
            }
            if embedded_answer:
                block["sourceSection"] = "answers" if in_answer_section else "questions"
            if presentation:
                block["presentation"] = presentation
            blocks.append(block)
            if duplicate_cs408_page:
                original_id = f"b-3-{child_index}"
                original_block = next((candidate for candidate in blocks
                                       if candidate["id"] == original_id), None)
                if original_block is None or original_block["role"] != role:
                    raise ValueError(f"CS408 2024 duplicate block changed: {block_id}")
                question_id = original_block.get("questionId")
                original_question = next((candidate for candidate in questions
                                          if candidate["id"] == question_id), None)
                if original_question is None:
                    raise ValueError(f"CS408 2024 duplicate owner missing: {block_id}")
                block["duplicateOf"] = original_id
                block["questionId"] = question_id
                original_question["sourceBlocks"].append(block_id)
                if page_number not in original_question["sourcePages"]:
                    original_question["sourcePages"].append(page_number)
                rendered.append(
                    f'<div class="source-block role-{role}" id="{block_id}" '
                    f'data-source-page="{escape(str(page_number))}" '
                    f'data-source-block="{child_index}" data-duplicate-of="{original_id}" hidden>'
                    f'{display_block(child, original, html_path, presentation, False)}</div>'
                )
                continue
            if role == "page_label":
                rendered.append(f'<div class="source-block role-page_label" id="{block_id}" data-source-page="{escape(str(page_number))}" data-source-block="{child_index}">{escape(text)}</div>')
                continue
            number = (str(MATH_OLD_MAIN_NUMBERS[old_math_main.group(1)]) if old_math_main else
                      absent_printed_number or (normalized_number(text) if role == "question" else None))
            if doc["kind"] == "complete" and doc["category"] == "cs408":
                # "请将答案写在答题纸" is a question-section instruction in
                # the 2011 source, not the beginning of an answer key.
                if re.search(r"参考答案|答案[及与]解析|选择题部分解析", text) and len(text) < 90:
                    close_question()
                    in_answer_section = True
            elif child.name in {"h1", "h2", "h3"} and doc["kind"] == "complete" and "答案" in text:
                in_answer_section = True
            if role == "choices" and child.select_one(".choice-number"):
                label = child.select_one(".choice-number")
                number = normalized_number(label.get_text(" ", strip=True)) if label else None
                if number:
                    section_choice_rows_seen = True
            same_choice_row = role == "choices" and number and current and current["number"] == number and not current["options"]
            continued = (role == "question" and number and current and current["number"] == number
                         and re.match(r"^\s*(?:[（(]\d+[）)]|\d+[.．、])\s*[（(]续[）)]", text))
            if continued and doc["category"] == "cs408" and doc["kind"] == "answers":
                block["answerContinuation"] = True
            starts_question = ((role == "question" and number and not continued)
                               or (role == "choices" and number and not same_choice_row))
            if starts_question:
                close_question()
                occurrences[number] += 1
                qid = f"q-{number}-{occurrences[number]}"
                current = {
                    "id": qid, "number": number, "sectionKind": section_kind,
                    "sectionTitle": section_title,
                    "recordType": "answer" if in_answer_section else "question",
                    "sourceBlocks": [], "sourcePages": [], "stem": displayed_text if role == "question" else "",
                    "options": [], "answer": None, "status": "complete" if role == "question" else "partial",
                    "context": ({"kind": "passage", "blankNumber": number,
                                 "text": "\n\n".join(b["text"] for b in section_context_blocks),
                                 "sourceBlocks": [b["id"] for b in section_context_blocks],
                                 "sourcePages": list(dict.fromkeys(b["page"] for b in section_context_blocks))}
                                if role == "choices" and doc["category"] == "kaoyan"
                                and "Use of English" in section_title and section_context_blocks else None),
                }
                first_option = NUMBERED_FIRST_OPTION_RE.match(text) if promoted_numbered_content else None
                if first_option:
                    current["stem"] = text[:first_option.start(1)].strip()
                    current["options"].append({"label": first_option.group(1) + ".",
                                               "sourceLabel": text[first_option.start(1):first_option.start(2)].strip(),
                                               "text": first_option.group(2).strip(), "sourceOrder": 1})
                if doc["category"] == "politics" and doc["kind"] == "questions":
                    current["subquestions"] = []
                    current["continuations"] = []
                    if absent_printed_number:
                        current["sourceNumberAbsent"] = True
                questions.append(current)
                q_label = f"第 {number} 题" + ("答案" if in_answer_section else "")
                toc.append({"kind": "question", "id": qid, "label": q_label, "number": number,
                            "level": section_level + 1,
                            "parentId": section_stack.get(section_level),
                            "sourceBlockId": block_id})
                rendered.append(f'<article class="question-card" id="{qid}" data-question="{escape(number)}"><div class="question-anchor">{q_label} <a href="#{qid}" aria-label="复制第 {escape(number)} 题位置">#</a></div>')
            elif role == "section":
                close_question()
                section_title = text
                section_level = section_level_for(text, doc["category"])
                assert section_level is not None
                section_kind = ("multiple_choice" if "多项" in text or "至少有一项" in text else
                                "fill_blank" if "填空题" in text else
                                "single_choice" if any(token in text for token in ("选择题", "单项", "Multiple Choice")) else "other")
                parent_id = next((section_stack[level] for level in range(section_level - 1, -1, -1)
                                  if level in section_stack), None)
                section_stack = {level: value for level, value in section_stack.items() if level < section_level}
                section_stack[section_level] = block_id
                section_context_blocks = []
                section_choice_rows_seen = False
                toc.append({"kind": "section", "id": block_id, "label": text[:90],
                            "level": section_level, "parentId": parent_id, "sourceBlockId": block_id})
            if current:
                block["questionId"] = current["id"]
                current["sourceBlocks"].append(block_id)
                if page_number not in current["sourcePages"]:
                    current["sourcePages"].append(page_number)
                if continued:
                    current["stem"] += " " + displayed_text
                if presentation and presentation["layoutKind"] == "politics":
                    if presentation.get("continuation"):
                        current["continuations"].append({
                            **presentation["continuation"], "sourceBlockId": block_id,
                            "sourcePage": page_number,
                        })
                    for subquestion in presentation.get("subquestions", []):
                        current["subquestions"].append({
                            **subquestion, "sourceBlockId": block_id,
                            "sourcePage": page_number,
                        })
                if role == "choices":
                    opts = options_from(child)
                    if opts:
                        if presentation and presentation.get("pageArtifacts"):
                            for option in opts:
                                cleaned = POLITICS_PAGE_ARTIFACT_RE.sub("", option["text"]).rstrip()
                                if cleaned != option["text"]:
                                    option["sourceText"] = option["text"]
                                    option["text"] = cleaned
                        # Most repeated labels across blocks are page/OCR
                        # carryover. These two printed questions genuinely
                        # repeat C with distinct option text.
                        printed_duplicate_c = (
                            (doc["id"] == "cet6:2014-12-01" and current["number"] == "61")
                            or (doc["id"] == "politics:2005-questions" and current["number"] == "3")
                        )
                        existing = {o["label"] for o in current["options"]}
                        for option in opts:
                            is_printed_second_c = (printed_duplicate_c and option["label"] == "C."
                                                   and len([o for o in current["options"]
                                                            if o["label"] == "C."]) == 1
                                                   and option["text"] != next(
                                                       o["text"] for o in current["options"]
                                                       if o["label"] == "C."))
                            if option["label"] not in existing or is_printed_second_c:
                                option["sourceOrder"] = len(current["options"]) + 1
                                current["options"].append(option)
                                existing.add(option["label"])
                        current["options"].sort(key=lambda option: "ABCDE".index(option["label"][0]))
                    elif text:
                        current["status"] = "partial"
                if doc["kind"] == "answers":
                    match = ANSWER_RE.search(text)
                    if match:
                        current["answer"] = normalize_choice_answer(match.group(1))
            else:
                block["status"] = "source_only"
                source_only += 1
                if role == "content" and doc["category"] == "kaoyan" and "Use of English" in section_title:
                    section_context_blocks.append(block)
            email_class = f' email-{presentation["segment"]}' if presentation and presentation["layoutKind"] == "email" else ""
            if presentation and presentation.get("signoffAlignment") == "right":
                email_class += " email-signoff-right"
            hidden = ' hidden' if presentation and presentation.get("continuation") and not presentation["displayText"] else ''
            rendered.append(f'<div class="source-block role-{role}{email_class}" id="{block_id}" data-source-page="{escape(str(page_number))}" data-source-block="{child_index}"{hidden}>{display_block(child, original, html_path, presentation, doc["category"] == "math3" and doc["kind"] == "questions")}</div>')
            if (doc["category"] == "kaoyan" and doc["kind"] == "questions"
                    and page_index == 12 and role == "figure"
                    and stem in TABLE_PAPERS | ORDERING_PAPERS):
                if current:
                    raise ValueError(f"matching figure unexpectedly inside question: {doc['id']}")
                source_html = (ROOT / doc["svg"]).resolve()
                if stem in TABLE_PAPERS:
                    if "flowchart" in child.get("class", []):
                        raise ValueError(f"expected matching table image: {doc['id']}")
                    cards = table_cards(stem, source_html)
                else:
                    if "flowchart" not in child.get("class", []):
                        raise ValueError(f"expected ordering diagram image: {doc['id']}")
                    cards = ordering_cards(stem, source_html, blocks[:-1])
                if [card["number"] for card in cards] != [str(n) for n in range(41, 46)]:
                    raise ValueError(f"Part B source slots changed: {doc['id']}")
                for card in cards:
                    number = card["number"]
                    occurrences[number] += 1
                    if occurrences[number] != 1:
                        raise ValueError(f"duplicate Part B question: {doc['id']} Q{number}")
                    qid = f"q-{number}-1"
                    option_sources = card.get("optionSourceBlocks", [])
                    source_ids = list(dict.fromkeys([*option_sources, block_id]))
                    source_pages = list(dict.fromkeys(
                        next(source_block["page"] for source_block in blocks
                             if source_block["id"] == source_id)
                        for source_id in source_ids))
                    questions.append({
                        "id": qid, "number": number,
                        "sectionKind": "single_choice", "sectionTitle": "Part B",
                        "recordType": "question", "sourceBlocks": source_ids,
                        "sourcePages": source_pages, "stem": card["stem"],
                        "options": [{"label": letter + ".", "sourceLabel": letter + ".",
                                     "text": value, "sourceOrder": order}
                                    for order, (letter, value) in enumerate(card["options"].items(), 1)],
                        "answer": None, "status": "complete",
                        "context": {"kind": card["kind"], "text": section_title,
                                    "sourceBlocks": source_ids,
                                    "sourcePages": source_pages, "figureBlockId": block_id,
                                    "fixedLetters": card.get("fixedLetters", [])},
                    })
                    toc.append({"kind": "question", "id": qid,
                                "label": f"第 {number} 题", "number": number,
                                "level": section_level + 1,
                                "parentId": section_stack.get(section_level),
                                "sourceBlockId": block_id})
                    guidance = ("选项见上方原卷表格。" if card["kind"] == "matching_table"
                                else "请结合上方 Part B 段落和原卷流程图作答。")
                    rendered.append(
                        f'<article class="question-card" id="{qid}" data-question="{number}">'
                        f'<div class="question-anchor">第 {number} 题 <a href="#{qid}" '
                        f'aria-label="复制第 {number} 题位置">#</a></div>'
                        f'<p>{escape(card["stem"])}</p>'
                        f'<p>{guidance}</p>'
                        '</article>')
    close_question()

    for question in questions:
        if question["recordType"] == "question":
            add_figure_options(doc, question, blocks, original, json_path)

    if doc["category"] in {"cs408", "politics"} and doc["kind"] == "questions":
        for question in questions:
            if question["recordType"] != "question":
                continue
            labels = [option["label"] for option in question["options"]]
            expected_labels = [f"{letter}." for letter in ("ABCDE" if "E." in labels else "ABCD")]
            if question["sectionKind"] in {"single_choice", "multiple_choice"} and labels == expected_labels:
                # Intermediate page fragments can have only A or A/B, while
                # the completed printed question has all four choices.
                question["status"] = "complete"
            elif labels:
                # A B C C, B-E, or another noncanonical sequence is not a
                # verified complete choice set even if it has four entries.
                question["status"] = "partial"
                malformed += 1

    for question in questions:
        if (doc["category"] == "cs408" and doc["kind"] in {"questions", "complete"}
                and question["recordType"] == "question" and question["number"].isdigit()
                and 41 <= int(question["number"]) <= 47 and not question["options"]
                and question["sourceBlocks"]):
            # The 2013 complete scan omits the Section II heading from its
            # extracted text. Q41–47 are the printed written-work section.
            question["sectionKind"] = "free_response"
            question["status"] = "complete"
        if (doc["id"] == "kaoyan:2000-01" and question["recordType"] == "question"
                and question["number"] == "36" and question["sectionTitle"] == "Section III Writing"):
            # The printed A/B/C are writing directions, not candidate answers.
            if [option["label"] for option in question["options"]] != ["A.", "B.", "C."]:
                raise ValueError("2000 English writing directions changed")
            source_blocks = {block["id"]: block for block in blocks}
            question["stem"] = "\n".join(
                source_blocks[block_id]["text"] for block_id in question["sourceBlocks"]
                if source_blocks[block_id]["role"] in {"question", "choices"}
            )
            question["options"] = []
            question["sectionKind"] = "free_response"
        if question["recordType"] == "answer":
            question["questionType"] = "answer"
            # Lettered explanations on an answer page are source prose, not
            # another selectable copy of the exam question's options.
            question["options"] = []
            # Answer-key records do not have choices of their own. Their
            # completeness is determined by the transcribed answer text.
            if question["sourceBlocks"]:
                question["status"] = "complete"
        elif question["options"]:
            question["questionType"] = "multiple_choice" if question["sectionKind"] == "multiple_choice" else "single_choice"
            if len({option["label"] for option in question["options"]}) != len(question["options"]):
                question["status"] = "partial"
        elif question["sectionKind"] == "fill_blank":
            question["questionType"] = "fill_blank"
        elif question["sectionKind"] in {"single_choice", "multiple_choice"}:
            question["questionType"] = question["sectionKind"]
            question["status"] = "partial"
        else:
            question["questionType"] = "free_response"
        question["answer"] = {
            "value": question["answer"], "solution": None, "explanation": None,
            "commentary": None, "knowledge": None,
            "sourceDocumentId": doc["id"] if question["answer"] else None,
            "sourceQuestionIds": [question["id"]] if question["answer"] else [],
            "sourceBlocks": [], "sourcePages": list(question["sourcePages"]) if question["answer"] else [],
            "status": "explicit" if question["answer"] else "missing",
        }

    # Preserve traceability without copying large MathJax SVGs into JSON.
    profile = PROFILES[doc["category"]]
    payload = {
        "schema": SCHEMA, "id": doc["id"], "title": doc["title"], "category": doc["category"],
        "categoryLabel": doc["categoryLabel"], "kind": doc["kind"], "year": doc["year"],
        "template": profile[1], "source": {
            "original": rel((ROOT / doc["svg"]).resolve(), json_path),
            "reflow": rel(original, json_path),
        },
        "pages": len(pages), "blocks": blocks, "questions": questions, "toc": toc,
        "audit": {"sourceBlocks": len(blocks), "renderedBlocks": len(blocks),
                  "pageLabels": sum(b["role"] == "page_label" for b in blocks),
                  "politicsContinuations": sum(bool(b.get("presentation", {}).get("continuation")) for b in blocks),
                  "politicsPageArtifacts": sum(len(b.get("presentation", {}).get("pageArtifacts", [])) for b in blocks),
                  "politicsSubquestions": sum(len(q.get("subquestions", [])) for q in questions),
                  "politicsVerifiedCorrections": sum(len(b.get("presentation", {}).get("corrections", [])) for b in blocks),
                  "sourceOnlyBlocks": source_only, "partialQuestions": sum(q["status"] == "partial" for q in questions),
                  "malformedOptionGroups": malformed},
    }
    if embedded_answer:
        payload["audit"]["embeddedAnswerStartPage"] = embedded_answer[0]
        payload["audit"]["embeddedAnswerRecords"] = sum(
            question["recordType"] == "answer" for question in questions)
    json_path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    source_styles = []
    for link in soup.head.select('link[rel="stylesheet"][href]') if soup.head else []:
        href = link["href"]
        if href.startswith(IGNORE_SCHEMES):
            continue
        source_styles.append(f'<link rel="stylesheet" href="{escape(rel((original.parent / href).resolve(), html_path), quote=True)}">')
    nav = []
    for entry in toc:
        css = ("toc-section" if entry["kind"] == "section" else "toc-question") + f' toc-level-{entry["level"]}'
        nav.append(f'<a class="{css}" href="#{escape(entry["id"])}">{escape(entry["label"])}</a>')
    links = {
        "index": rel(OUT / "index.htm", html_path),
        "original": rel((ROOT / doc["svg"]).resolve(), html_path),
        "reflow": rel(original, html_path),
        "json": rel(json_path, html_path),
        "css": rel(OUT / "structured.css", html_path),
        "code_css": rel(ROOT / "ui" / "code-highlight.css", html_path),
        "code_js": rel(ROOT / "ui" / "code-highlight.js", html_path),
    }
    html = f'''<!doctype html><html lang="zh-CN" data-template="{profile[1]}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{escape(doc["title"])} · 结构化试卷</title>{''.join(source_styles)}<link rel="stylesheet" href="{links["css"]}"><link rel="stylesheet" href="{links["code_css"]}"></head><body><header class="structured-top"><a href="{links["index"]}">← 结构化试卷目录</a><strong>{escape(doc["title"])}</strong><span>{escape(profile[2])}</span><nav><a href="{links["original"]}">原版</a><a href="{links["reflow"]}">重排版</a><a href="{links["json"]}">JSON</a></nav></header><div class="structured-layout"><aside class="structured-toc"><strong>试卷目录</strong><a href="#paper-top">卷首</a>{''.join(nav)}</aside><main class="structured-main" id="paper-top"><div class="paper-intro"><p>{escape(doc["categoryLabel"])} · {escape(doc["kind"])} · {doc["year"]}</p><h1>{escape(doc["title"])}</h1><p>题号和章节目录由结构化数据生成。选项按卷面字母顺序显示；原标记保留在 JSON 中。</p></div>{''.join(rendered)}</main></div><script defer src="{links["code_js"]}"></script></body></html>'''
    html_path.write_text(html, encoding="utf-8")
    return {"id": doc["id"], "category": doc["category"], "kind": doc["kind"], "title": doc["title"],
            "template": profile[1], "json": rel(json_path, OUT / "index.htm"), "reader": rel(html_path, OUT / "index.htm"),
            "questions": (sum(question["recordType"] == "question" for question in questions)
                          if embedded_answer else len(questions)),
            "partialQuestions": payload["audit"]["partialQuestions"],
            "sourceBlocks": len(blocks), "sourceOnlyBlocks": source_only}


def answer_fields(question: dict, blocks: dict[str, dict]) -> dict:
    """Extract explicitly labelled answer parts; absent parts remain null."""
    fields = {key: None for key in ("value", "solution", "explanation", "commentary", "knowledge")}
    sources = question["sourceBlocks"]
    head = question["stem"]
    match = ANSWER_RE.search(head)
    if match:
        fields["value"] = normalize_choice_answer(match.group(1))
    part = "solution" if "答案要点" in head or "解答" in head else None
    collected = defaultdict(list)
    for bid in sources:
        block = blocks[bid]
        if block.get("duplicateOf"):
            continue
        value = block["text"]
        if block["role"] == "tex_source":
            continue
        if block["role"] == "heading":
            if "点拨" in value or "点评" in value:
                part = "commentary"
            elif "解析" in value or "简析" in value:
                part = "explanation"
            elif "知识还原" in value or "考点知识" in value:
                part = "knowledge"
            elif "解答" in value or "答案要点" in value:
                part = "solution"
            continue
        if block["role"] == "question":
            if "答案要点" in value or "解答" in value:
                suffix = re.sub(r"^\s*(?:[（(]\d+[）)]|\d+[.．、])\s*(?:[（(]续[）)])?\s*", "", value)
                suffix = re.sub(r"^【答案要点】", "", suffix).strip()
                if suffix and suffix != "解答：":
                    collected["solution"].append(suffix)
            elif block.get("answerContinuation"):
                suffix = re.sub(r"^\s*\d+[.．、]\s*[（(]续[）)]\s*", "", value, count=1).strip()
                if suffix:
                    collected["solution"].append(suffix)
            continue
        if part and value:
            collected[part].append(value)
    for key, values in collected.items():
        fields[key] = "\n".join(values) if values else None
    return fields


def math_answer_numbers(text: str) -> list[re.Match]:
    """Find printed answer numbers outside TeX and inline function arguments."""
    visible = MATH_TEX_RE.sub(lambda match: " " * len(match.group()), text)
    return [match for match in NUMBERED_MATH_RE.finditer(visible)
            if match.start() == 0 or visible[match.start() - 1].isspace()
            or visible[match.start() - 1] in "。；;，,、：:"]


def math_answer_body(question: dict, blocks: dict[str, dict]) -> str:
    """Collect one answer's printed parts, including following subquestion lines."""
    parts = []
    for block_id in question["sourceBlocks"]:
        block = blocks[block_id]
        if block["role"] not in {"question", "content"}:
            continue
        value = block["text"]
        if block["role"] == "question":
            value = re.sub(r"^\s*[（(]\s*\d{1,3}\s*[）)]\s*", "", value, count=1)
        if value.strip():
            parts.append(value.strip())
    return "\n".join(parts)


def cs408_interleaved_answer(question: dict, blocks: dict[str, dict]) -> dict | None:
    """Read an answer printed after its question, keeping only answer blocks."""
    if question["recordType"] != "question":
        return None
    answer_blocks = []
    parts = []
    for block_id in question["sourceBlocks"]:
        block = blocks[block_id]
        if not answer_blocks:
            marker = CS408_SOLUTION_RE.search(block["text"])
            if not marker or block["role"] != "content":
                continue
            text = block["text"][marker.end():].strip()
        else:
            if block["role"] in {"page_label", "tex_source"}:
                continue
            text = block["text"].strip()
        answer_blocks.append(block_id)
        if text:
            parts.append(text)
    if not answer_blocks:
        return None

    value = None
    if question["sectionKind"] in {"single_choice", "multiple_choice"} and parts:
        match = re.match(r"^([A-E])(?=[。.．、，,；;：:\s]|$)", parts[0])
        if match:
            value = match.group(1)
            parts[0] = parts[0][match.end():].lstrip("。.．、，,；;：: ").strip()
    solution = "\n".join(part for part in parts if part) or None
    if not value and not solution:
        return None
    return {
        "value": value, "solution": solution, "explanation": None,
        "commentary": None, "knowledge": None,
        "sourceQuestionIds": [question["id"]], "sourceBlocks": answer_blocks,
    }


def cs408_answer_record_body(question: dict, blocks: dict[str, dict]) -> tuple[str, str] | None:
    """Read an explicitly labelled 2016–23 answer, excluding appended questions."""
    head = re.sub(r"^\s*\d{1,3}\s*[.．、]\s*", "", question["stem"], count=1)
    marker = CS408_ANSWER_MARKER_RE.search(head)
    if not marker or marker.start() > 25:
        return None
    prefix = head[:marker.start()].strip()
    if prefix and not re.fullmatch(r"(?:[A-E][。.．]?|【参考答案】\s*[A-E])", prefix):
        return None
    parts = [head[marker.end():].lstrip(" 。．.").strip()]
    for block_id in question["sourceBlocks"][1:]:
        block = blocks[block_id]
        if block["role"] not in {"question", "content", "figure"}:
            continue
        if block["text"].strip():
            parts.append(block["text"].strip())
    body = "\n".join(part for part in parts if part)
    if not body:
        return None
    field = "explanation" if int(question["number"]) <= 40 else "solution"
    return field, body


def answer_entries(paper: dict) -> dict[str, dict]:
    blocks = {block["id"]: block for block in paper["blocks"]}
    answers: dict[str, dict] = {}
    # Some answer books print the A-D key as one paragraph before detailed items.
    for block in paper["blocks"] if paper["category"] == "cs408" else []:
        if block["role"] != "content" or block.get("duplicateOf"):
            continue
        matches = list(NUMBERED_LETTER_RE.finditer(block["text"]))
        if (len(matches) < 3 and paper["kind"] == "answers" and
                2016 <= paper["year"] <= 2023):
            # These first-page tables omit punctuation: "1 D 2 C ... 40 B".
            # Require the complete printed 1–40 sequence before linking it.
            spaced = CS408_SPACED_KEY_RE.findall(block["text"])
            if [int(number) for number, _ in spaced] == list(range(1, 41)):
                for number, letter in spaced:
                    entry = answers.setdefault(str(int(number)), {key: None for key in (
                        "value", "solution", "explanation", "commentary", "knowledge")})
                    entry["value"] = letter
                    entry.setdefault("sourceQuestionIds", [])
                    entry.setdefault("sourceBlocks", []).append(block["id"])
            continue
        if len(matches) < 3:
            continue
        for match in matches:
            number = str(int(next(g for g in match.groups()[:2] if g)))
            entry = answers.setdefault(number, {key: None for key in ("value", "solution", "explanation", "commentary", "knowledge")})
            entry["value"] = match.group(3)
            entry.setdefault("sourceQuestionIds", [])
            entry.setdefault("sourceBlocks", []).append(block["id"])
    for question in paper["questions"]:
        if question["recordType"] != "answer":
            continue
        text = question["stem"]
        if (paper["category"] == "politics" and 2010 <= paper["year"] <= 2020
                and question["number"].isdigit() and 34 <= int(question["number"]) <= 38):
            # These answer books put the response directly below the printed
            # answer heading. The 2019 PDF appends an unrelated 2020 fragment;
            # stop at that heading and ignore its unlabelled duplicate numbers.
            if not POLITICS_ESSAY_ANSWER_RE.fullmatch(text):
                continue
            source_ids = []
            parts = []
            for block_id in question["sourceBlocks"]:
                block = blocks[block_id]
                if block["role"] == "heading":
                    break
                if block["role"] == "question":
                    source_ids.append(block_id)
                elif block["role"] == "content" and block["text"]:
                    source_ids.append(block_id)
                    parts.append(block["text"])
            if not parts:
                continue
            entry = answers.setdefault(question["number"], {key: None for key in (
                "value", "solution", "explanation", "commentary", "knowledge")})
            entry["solution"] = "\n".join(parts)
            entry.setdefault("sourceQuestionIds", []).append(question["id"])
            entry.setdefault("sourceBlocks", []).extend(source_ids)
            continue
        letter_matches = list(NUMBERED_LETTER_RE.finditer(text))
        if len(letter_matches) >= 3:
            for match in letter_matches:
                number = next(g for g in match.groups()[:2] if g)
                entry = answers.setdefault(str(int(number)), {key: None for key in ("value", "solution", "explanation", "commentary", "knowledge")})
                entry["value"] = match.group(3)
                entry.setdefault("sourceQuestionIds", []).append(question["id"])
                entry.setdefault("sourceBlocks", []).extend(question["sourceBlocks"])
            continue
        if paper["category"] == "math3":
            math_matches = math_answer_numbers(text)
            numbers = [int(match.group(1)) for match in math_matches]
            if (len(math_matches) >= 2 and math_matches[0].start() == 0
                    and numbers[0] == int(question["number"])
                    and numbers == list(range(numbers[0], numbers[0] + len(numbers)))):
                for i, match in enumerate(math_matches):
                    number = str(int(match.group(1)))
                    end = math_matches[i + 1].start() if i + 1 < len(math_matches) else len(text)
                    value = text[match.end():end].strip().rstrip("。 ")
                    entry = answers.setdefault(number, {key: None for key in ("value", "solution", "explanation", "commentary", "knowledge")})
                    entry["value"] = value or None
                    entry.setdefault("sourceQuestionIds", []).append(question["id"])
                    entry.setdefault("sourceBlocks", []).extend(question["sourceBlocks"])
                continue
        fields = answer_fields(question, blocks)
        if (paper["category"] == "cs408" and paper["kind"] == "answers" and
                2016 <= paper["year"] <= 2023):
            printed_body = cs408_answer_record_body(question, blocks)
            if printed_body:
                field, body = printed_body
                if not fields[field]:
                    fields[field] = body
            elif not any(fields.values()):
                # 2020's final PDF page contains 2019 question stems, not
                # answer records, despite sharing numbers 1–6.
                continue
        if paper["category"] == "cs408" and paper["kind"] == "complete":
            # Some complete papers print each key as "1. D", with the
            # explanation in the following paragraph or joined to the key.
            printed = CS408_PRINTED_CHOICE_RE.match(question["stem"])
            if printed and str(int(printed.group(1))) == question["number"]:
                fields["value"] = printed.group(2)
                explanation = []
                suffix = question["stem"][printed.end():].strip()
                if suffix.startswith("解析："):
                    explanation.append(suffix.removeprefix("解析：").strip())
                for block_id in question["sourceBlocks"][1:]:
                    block = blocks[block_id]
                    if block["role"] not in {"content", "figure"}:
                        continue
                    content = block["text"].strip()
                    if content.startswith("解析："):
                        content = content.removeprefix("解析：").strip()
                    if content:
                        explanation.append(content)
                fields["explanation"] = "\n".join(explanation) or None
        if paper["category"] == "math3" and not any(fields.values()):
            raw = math_answer_body(question, blocks)
            if raw:
                destination = "solution" if int(question["number"]) >= 15 else "value"
                fields[destination] = raw
        if paper["category"] == "math3" and int(question["number"]) >= 15:
            captured = "\n".join(value or "" for value in fields.values())
            missing = [blocks[bid]["text"] for bid in question["sourceBlocks"]
                       if blocks[bid]["role"] == "content" and blocks[bid]["text"]
                       and blocks[bid]["text"] not in captured]
            if missing:
                fields["solution"] = "\n".join(part for part in [fields["solution"], *missing] if part)
        number = question["number"]
        entry = answers.setdefault(number, {key: None for key in ("value", "solution", "explanation", "commentary", "knowledge")})
        for key, value in fields.items():
            if value:
                entry[key] = (entry[key] + "\n" + value) if entry[key] and entry[key] != value else value
        entry.setdefault("sourceQuestionIds", []).append(question["id"])
        entry.setdefault("sourceBlocks", []).extend(question["sourceBlocks"])
    if paper["category"] == "cs408" and paper["kind"] == "complete":
        for question in paper["questions"]:
            interleaved = cs408_interleaved_answer(question, blocks)
            if interleaved and question["number"] not in answers:
                answers[question["number"]] = interleaved
    return answers


def embedded_english_answer_entries(paper: dict) -> dict[str, dict]:
    """Read only numbered answers printed after this PDF's answer-page boundary.

    These five books mix answer keys, listening transcripts, explanations and
    (in one case) reprinted translation prompts. A repeated number alone is
    never evidence of a key; ambiguous candidates stay unlinked.
    """
    blocks = {block["id"]: block for block in paper["blocks"]}
    candidates: dict[str, list[tuple[str, dict]]] = defaultdict(list)
    answer_blocks = [block for block in paper["blocks"] if block.get("sourceSection") == "answers"]
    # In the second December set, the printed "54 【定位】" is joined to
    # question 53's preceding paragraph; the next block is its B) key.
    if paper["id"] == "cet6:2012-12-02":
        markers = [index for index, block in enumerate(answer_blocks)
                   if re.search(r"(?<!\w)54\s+【定位】", block["text"])]
        if len(markers) != 1:
            raise ValueError("CET6 2012-12 set 2 answer 54 marker changed")
        marker_index = markers[0]
        marker, key_block = answer_blocks[marker_index:marker_index + 2]
        key = ENGLISH_PRINTED_CHOICE_RE.match(key_block["text"])
        if not key or key.group(1) != "B":
            raise ValueError("CET6 2012-12 set 2 answer 54 key changed")
        entry = {field: None for field in ("value", "solution", "explanation", "commentary", "knowledge")}
        entry.update(value="B", sourceQuestionIds=[], sourceBlocks=[marker["id"], key_block["id"]])
        candidates["54"].append(("B", entry))
    if paper["id"] == "cet6:2012-12-03":
        record = next((question for question in paper["questions"]
                       if question["recordType"] == "answer" and question["number"] == "60"), None)
        if record:
            evidence = [blocks[bid] for bid in record["sourceBlocks"]
                        if bid in blocks and "A)" in blocks[bid]["text"]
                        and "故为答案" in blocks[bid]["text"]]
            if len(evidence) == 1:
                entry = {field: None for field in ("value", "solution", "explanation", "commentary", "knowledge")}
                entry.update(value="A", sourceQuestionIds=[record["id"]],
                             sourceBlocks=[evidence[0]["id"]])
                candidates["60"].append(("A", entry))
    for prompt, reply in zip(answer_blocks, answer_blocks[1:]):
        question_match = ENGLISH_TRANSCRIPT_QUESTION_RE.match(prompt["text"])
        answer_match = ENGLISH_ANSWER_PHRASE_RE.match(reply["text"])
        if not (question_match and answer_match):
            continue
        number = str(int(question_match.group(1)))
        value = answer_match.group(1).strip().rstrip("。 ")
        if value:
            entry = {field: None for field in ("value", "solution", "explanation", "commentary", "knowledge")}
            entry.update(value=value, sourceQuestionIds=[], sourceBlocks=[prompt["id"], reply["id"]])
            candidates[number].append((value, entry))
    key_table_open = False
    for block in paper["blocks"]:
        if block.get("sourceSection") != "answers":
            continue
        content = block["text"].strip()
        if content == "答案：" or content == "答案:":
            key_table_open = True
            continue
        if content.startswith("【解析】") or content.startswith("【点评】"):
            key_table_open = False
        key = ENGLISH_NUMBERED_KEY_RE.match(content) if key_table_open else None
        if key:
            number, value = str(int(key.group(1))), key.group(2)
            entry = {field: None for field in ("value", "solution", "explanation", "commentary", "knowledge")}
            entry.update(value=value, sourceQuestionIds=[], sourceBlocks=[block["id"]])
            candidates[number].append((value, entry))
    for record in paper["questions"]:
        if record["recordType"] != "answer":
            continue
        source_blocks = [blocks[bid] for bid in record["sourceBlocks"]
                         if bid in blocks and blocks[bid]["role"] not in {"page_label", "tex_source"}]
        if not source_blocks:
            continue
        number = record["number"]
        if not number.isdigit():
            continue
        # The printed conclusion outranks an isolated A)/B) marker in a
        # transcript, which may introduce an option being discussed.
        conclusions = set()
        for block in source_blocks:
            conclusions.update(ENGLISH_EXPLICIT_CHOICE_RE.findall(block["text"]))
        if len(conclusions) > 1:
            value = None
        elif conclusions:
            value = next(iter(conclusions))
        else:
            labels = [match.group(1) for block in source_blocks[:8]
                      if (match := ENGLISH_PRINTED_CHOICE_RE.match(block["text"]))
                      and not re.match(r"^\s*[A-D]\s*[)）.．]\s*(?:和\s*[A-D]|[。.，,;；])",
                                       block["text"])]
            value = labels[0] if labels else None
        if not value:
            head = re.sub(r"^\s*\d{1,3}\s*[.．、]\s*", "", record["stem"]).strip()
            printed_phrases = [match.group(1).strip().rstrip("。 ")
                               for block in source_blocks
                               for match in ENGLISH_ANSWER_PHRASE_RE.finditer(block["text"])
                               if match.group(1).strip()]
            if len(set(printed_phrases)) == 1 and printed_phrases:
                value = printed_phrases[0]
            # These printed sections provide a word/phrase or translation as
            # the answer itself. Exclude prompts, blanks and locator notes.
            direct_ranges = (8 <= int(number) <= 10 or
                             (paper["category"] == "cet4" and 26 <= int(number) <= 35) or
                             (paper["category"] == "cet6" and 19 <= int(number) <= 25 and
                              paper["id"].startswith("cet6:2012-12-")) or
                             (paper["category"] == "cet6" and 36 <= int(number) <= 51) or
                             (paper["category"] == "cet6" and 82 <= int(number) <= 86 and
                              paper["id"] != "cet6:2012-06-01"))
            if (not value and direct_ranges and head and "_" not in head and "?" not in head and
                    "【线索词】" not in head and "【定位】" not in head and
                    not re.search(r"[（(][^）)]*[\u3400-\u9fff]", head)):
                value = head.split("。", 1)[0] if paper["category"] == "cet4" and 26 <= int(number) <= 35 else head
        if not value:
            continue
        entry = {key: None for key in ("value", "solution", "explanation", "commentary", "knowledge")}
        entry.update(value=value, sourceQuestionIds=[record["id"]],
                     sourceBlocks=list(record["sourceBlocks"]))
        candidates[number].append((value, entry))
    result = {}
    for number, matches in candidates.items():
        if len({value for value, _ in matches}) == 1:
            result[number] = matches[0][1]
        else:
            result[number] = {"ambiguous": True,
                              "sourceQuestionIds": [qid for _, entry in matches
                                                    for qid in entry["sourceQuestionIds"]],
                              "sourceBlocks": list(dict.fromkeys(
                                  bid for _, entry in matches for bid in entry["sourceBlocks"]))}
    return result


def old_math_answer_entries(paper: dict) -> dict[tuple[str, str], dict]:
    """Keep 1997-2003 repeated 1-5/6 labels distinct from problems 三、 onward."""
    blocks = {block["id"]: block for block in paper["blocks"]}
    answers: dict[tuple[str, str], dict] = {}

    def add(kind: str, number: str, field: str, value: str, question: dict) -> None:
        key = (kind, number)
        if key in answers:
            raise ValueError(f"duplicate old mathematics answer: {paper['id']} {key}")
        entry = {name: None for name in ("value", "solution", "explanation", "commentary", "knowledge")}
        entry[field] = value or None
        entry["sourceQuestionIds"] = [question["id"]]
        entry["sourceBlocks"] = list(question["sourceBlocks"])
        answers[key] = entry

    for question in paper["questions"]:
        if question["recordType"] != "answer":
            continue
        kind = question["sectionKind"]
        if kind == "other":
            body = math_answer_body(question, blocks)
            body = MATH_OLD_MAIN_RE.sub("", body, count=1).strip()
            add(kind, question["number"], "solution", body, question)
            continue
        text = question["stem"]
        if kind == "single_choice":
            visible = MATH_TEX_RE.sub(lambda match: " " * len(match.group()), text)
            matches = list(NUMBERED_MATH_RE.finditer(visible))
            numbers = [int(match.group(1)) for match in matches]
            if numbers != list(range(1, len(numbers) + 1)):
                raise ValueError(f"unexpected old mathematics choice key: {paper['id']} {numbers}")
            for index, match in enumerate(matches):
                end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
                body = text[match.end():end].strip().rstrip("。 ")
                letter = re.match(r"^([A-D])(?=[。.\s]|$)", body)
                if letter:
                    add(kind, str(int(match.group(1))), "value", letter.group(1), question)
                else:
                    add(kind, str(int(match.group(1))), "value", body, question)
        elif kind == "fill_blank":
            matches = math_answer_numbers(text)
            for index, match in enumerate(matches):
                end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
                value = text[match.end():end].strip().rstrip("。 ")
                add(kind, str(int(match.group(1))), "value", value, question)
    return answers


def dual_form_math_question_forms(paper: dict) -> dict[str, str]:
    """Read the printed IV/V headings before each numbered question block."""
    forms: dict[str, str] = {}
    current_form = None
    for block in paper["blocks"]:
        if block["role"] == "heading":
            heading = re.search(r"试卷\s*(IV|V)(?=[）)（(\s]|$)", block["text"])
            if heading:
                current_form = heading.group(1)
        if block["role"] == "question" and block.get("questionId") and current_form:
            forms.setdefault(block["questionId"], current_form)
    return forms


def dual_form_math_main_answers(paper: dict) -> dict[tuple[str, str], dict]:
    """Keep the 1993-1996 IV and V main-problem answers separate."""
    blocks = {block["id"]: block for block in paper["blocks"]}
    forms = dual_form_math_question_forms(paper)
    answers: dict[tuple[str, str], dict] = {}
    for question in paper["questions"]:
        if question["recordType"] != "answer" or question["sectionKind"] != "other":
            continue
        form = forms.get(question["id"])
        if not form:
            continue
        key = (form, question["number"])
        if key in answers:
            raise ValueError(f"duplicate dual-form mathematics answer: {paper['id']} {key}")
        body = MATH_OLD_MAIN_RE.sub("", math_answer_body(question, blocks), count=1).strip()
        if not body:
            continue
        # A following form heading may be attached to the preceding answer
        # record by the generic parser; it is not part of that answer's source.
        source_blocks = [block_id for block_id in question["sourceBlocks"]
                         if blocks[block_id]["role"] in {"question", "content", "tex_source"}]
        answers[key] = {
            "value": None, "solution": body, "explanation": None,
            "commentary": None, "knowledge": None,
            "sourceQuestionIds": [question["id"]], "sourceBlocks": source_blocks,
        }
    return answers


def dual_form_math_numbered_answers(paper: dict) -> dict[tuple[str, str, str], dict]:
    """Index old IV/V answer rows by printed form, section and item number."""
    answers: dict[tuple[str, str, str], dict] = {}
    form = None
    section = None
    active_key = None
    numbered_sections = {"一", "二"} | ({"三"} if paper["year"] <= 1990 else set())
    if paper["year"] == 1988:
        numbered_sections.add("四")
    for block in paper["blocks"]:
        text = block["text"]
        if block["role"] == "heading":
            heading = re.search(r"试卷\s*(IV|V)(?=[）)（(\s]|$)", text)
            if heading:
                form, section, active_key = heading.group(1), None, None
            continue
        if block["role"] == "section":
            match = re.match(r"^\s*([一二三四])\s*[、.．]", text)
            section = match.group(1) if match and match.group(1) in numbered_sections else None
            active_key = None
            continue
        if block["role"] not in {"question", "content"} or not form:
            continue
        main = re.match(r"^\s*([一二三四五六七八九十]+)\s*[、.．]", text)
        if main:
            section = main.group(1) if main.group(1) in numbered_sections else None
            active_key = None
        if not section:
            continue
        # The reference target repeats a number inside 【同试卷 IV ...（1）题】;
        # only the leading item label starts an answer entry.
        visible = re.sub(r"【[^】]*】", lambda match: " " * len(match.group()), text)
        matches = math_answer_numbers(visible)
        if not matches:
            if active_key and text.strip():
                entry = answers[active_key]
                entry["value"] = "\n".join(part for part in (entry["value"], text.strip()) if part)
                entry["sourceBlocks"].append(block["id"])
            continue
        for index, match in enumerate(matches):
            end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            number = str(int(match.group(1)))
            key = (form, section, number)
            if key in answers:
                # A repeated label in one form/section cannot be assigned
                # safely, even when its bare number happens to match.
                answers.pop(key)
                active_key = None
                continue
            value = text[match.end():end].strip().rstrip("。 ")
            answers[key] = {
                "value": value or None, "solution": None, "explanation": None,
                "commentary": None, "knowledge": None,
                "sourceQuestionIds": [block["questionId"]] if block.get("questionId") else [],
                "sourceBlocks": [block["id"]],
            }
            active_key = key
    return answers


def legacy_dual_form_math_main_answers(paper: dict) -> dict[tuple[str, str], dict]:
    """Index 1987-1992 Chinese-numbered main answers without bare-number matching."""
    answers: dict[tuple[str, str], dict] = {}
    form = None
    active_key = None
    marker = re.compile(r"(?<!\S)(十四|十三|十二|十一|十|九|八|七|六|五|四|三)[、.．]")
    for block in paper["blocks"]:
        text = block["text"]
        if block["role"] == "heading":
            heading = re.search(r"试卷\s*(IV|V)(?=[）)（(\s]|$)", text)
            if heading:
                form, active_key = heading.group(1), None
            continue
        if block["role"] == "section":
            active_key = None
            continue
        if block["role"] not in {"question", "content"} or not form:
            continue
        visible = MATH_TEX_RE.sub(lambda match: " " * len(match.group()), text)
        matches = list(marker.finditer(visible))
        if matches:
            for index, match in enumerate(matches):
                if paper["year"] <= 1990 and match.group(1) == "三":
                    active_key = None  # 三、 is a numbered calculation section.
                    continue
                number = str(MATH_OLD_MAIN_NUMBERS[match.group(1)])
                key = (form, number)
                if key in answers:
                    raise ValueError(f"duplicate old mathematics main answer: {paper['id']} {key}")
                end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
                body = text[match.end():end].strip()
                answers[key] = {
                    "value": None, "solution": body, "explanation": None,
                    "commentary": None, "knowledge": None,
                    "sourceQuestionIds": [], "sourceBlocks": [block["id"]],
                }
                active_key = key
            continue
        if active_key and text.strip():
            entry = answers[active_key]
            entry["solution"] = "\n".join(part for part in (entry["solution"], text.strip()) if part)
            entry["sourceBlocks"].append(block["id"])
    return answers


def legacy_math_subanswer(entry: dict, number: str) -> dict | None:
    """Select a printed (1)/(2) part from a Chinese-numbered main answer."""
    body = entry["solution"] or ""
    visible = re.sub(r"【[^】]*】", lambda match: " " * len(match.group()), body)
    matches = math_answer_numbers(visible)
    for index, match in enumerate(matches):
        if str(int(match.group(1))) != number:
            continue
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        value = body[match.end():end].strip()
        if value:
            return {**entry, "solution": value}
    return None


def math_roman_twenty_first_answer(paper: dict) -> dict | None:
    """Join the two explicitly printed (21)(I)/(II) answer records of 2004/06."""
    if paper.get("category") != "math3" or paper.get("year") not in {2004, 2006}:
        return None
    records = [question for question in paper["questions"]
               if question["recordType"] == "answer" and question["number"] == "21"]
    if len(records) != 2 or not all(
            re.match(r"^\s*[（(]21[）)]\s*[（(][ⅠⅡ][）)]", record["stem"])
            for record in records):
        return None
    blocks = {block["id"]: block for block in paper["blocks"]}
    bodies = [math_answer_body(record, blocks) for record in records]
    if not all(bodies) or not bodies[0].startswith("（Ⅰ）") or not bodies[1].startswith("（Ⅱ）"):
        return None
    return {
        "value": None, "solution": "\n".join(bodies), "explanation": None,
        "commentary": None, "knowledge": None,
        "sourceQuestionIds": [record["id"] for record in records],
        "sourceBlocks": list(dict.fromkeys(block_id for record in records
                                                for block_id in record["sourceBlocks"])),
    }


def attach_answers(rows: list[dict]) -> None:
    """Link unambiguous question numbers only; historical papers restart numbering."""
    papers = {row["id"]: json.loads((OUT / row["json"]).read_text(encoding="utf-8")) for row in rows}
    for row in rows:
        paper = papers[row["id"]]
        if paper["kind"] == "answers":
            continue
        answer_id = paper["id"] if paper["kind"] == "complete" else paper["id"].replace("-questions", "-answers")
        answer_paper = papers.get(answer_id)
        if not answer_paper:
            continue
        by_number = (embedded_english_answer_entries(answer_paper)
                     if paper["id"] in EMBEDDED_ENGLISH_ANSWER_PAGES
                     else answer_entries(answer_paper))
        by_old_math_section = old_math_answer_entries(answer_paper) if is_old_math_paper(paper) else None
        by_dual_form_main = dual_form_math_main_answers(answer_paper) if is_dual_form_math_paper(paper) else None
        by_dual_form_section = (dual_form_math_numbered_answers(answer_paper)
                                if paper["category"] == "math3" and 1987 <= paper["year"] <= 1996 else None)
        by_legacy_math_main = (legacy_dual_form_math_main_answers(answer_paper)
                               if paper["category"] == "math3" and 1987 <= paper["year"] <= 1992 else None)
        roman_math_21 = math_roman_twenty_first_answer(answer_paper)
        question_forms = dual_form_math_question_forms(paper) if by_dual_form_section is not None else None
        main_counts = Counter(
            (question_forms.get(q["id"]), match.group(1))
            for q in paper["questions"] if q["recordType"] == "question"
            if (match := MATH_OLD_MAIN_RE.match(q.get("sectionTitle", "")) or
                MATH_OLD_MAIN_RE.match(q.get("stem", "")))
        ) if by_legacy_math_main is not None else Counter()
        question_counts = Counter(q["number"] for q in paper["questions"] if q["recordType"] == "question")
        answer_blocks = {block["id"]: block for block in answer_paper["blocks"]}
        for question in paper["questions"]:
            if question["recordType"] != "question":
                continue
            dual_form_main = by_dual_form_main is not None and question["sectionKind"] == "other"
            section_title = question.get("sectionTitle", "")
            section_match = re.match(r"^\s*([一二三四])\s*[、.．]", section_title)
            section = section_match.group(1) if section_match else None
            dual_form_section = (by_dual_form_section is not None and section is not None and
                                 (section in {"一", "二"} or paper["year"] <= 1990 and section == "三"
                                  or paper["year"] == 1988 and section == "四"))
            main_heading = MATH_OLD_MAIN_RE.match(section_title) or MATH_OLD_MAIN_RE.match(question.get("stem", ""))
            main_key = ((question_forms.get(question["id"]),
                         str(MATH_OLD_MAIN_NUMBERS[main_heading.group(1)]))
                        if by_legacy_math_main is not None and main_heading else None)
            legacy_main = main_key in by_legacy_math_main if main_key and by_legacy_math_main else False
            if dual_form_main:
                source_answer = by_dual_form_main.get((question_forms.get(question["id"]), question["number"]))
            elif dual_form_section:
                source_answer = by_dual_form_section.get((question_forms.get(question["id"]), section, question["number"]))
            elif legacy_main:
                source_answer = by_legacy_math_main[main_key]
                if (question["number"] != main_key[1] and
                        (question["number"] != "1" or
                         main_counts[(main_key[0], main_heading.group(1))] > 1)):
                    source_answer = legacy_math_subanswer(source_answer, question["number"])
            elif roman_math_21 is not None and question["number"] == "21":
                source_answer = roman_math_21
            elif by_old_math_section is not None:
                source_answer = by_old_math_section.get((question["sectionKind"], question["number"]))
            else:
                source_answer = by_number.get(question["number"])
            if not source_answer:
                continue
            answer = question["answer"]
            if paper["id"] in EMBEDDED_ENGLISH_ANSWER_PAGES and (
                    question_counts[question["number"]] > 1 or source_answer.get("ambiguous")):
                answer["status"] = "ambiguous"
                answer["ambiguityReason"] = "原卷答案页同题号存在多个互不一致的答案，暂不关联"
                answer["sourceDocumentId"] = answer_id
                answer["sourceQuestionIds"] = list(source_answer.get("sourceQuestionIds", []))
                answer["sourceBlocks"] = list(source_answer.get("sourceBlocks", []))
                answer["sourcePages"] = list(dict.fromkeys(
                    answer_blocks[bid]["page"] for bid in answer["sourceBlocks"] if bid in answer_blocks))
                continue
            if ((paper["category"] == "math3" and by_old_math_section is None and
                 not dual_form_main and not dual_form_section and not legacy_main and
                 not (roman_math_21 is not None and question["number"] == "21") and
                 (question_counts[question["number"]] > 1 or
                  len(set(source_answer.get("sourceQuestionIds", []))) > 1)) or
                (paper["category"] == "cs408" and paper["kind"] == "complete" and
                 question_counts[question["number"]] > 1)):
                for key in ("value", "solution", "explanation", "commentary", "knowledge"):
                    answer[key] = None
                answer["status"] = "ambiguous"
                answer["ambiguityReason"] = "题号在试卷或答案中重复，无法仅凭题号可靠对应"
                answer["sourceDocumentId"] = answer_id
                answer["sourceQuestionIds"] = []
                answer["sourceBlocks"] = []
                answer["sourcePages"] = []
                continue
            for key in ("value", "solution", "explanation", "commentary", "knowledge"):
                answer[key] = source_answer[key]
            answer["sourceDocumentId"] = answer_id
            answer["sourceQuestionIds"] = list(dict.fromkeys(source_answer["sourceQuestionIds"]))
            answer["sourceBlocks"] = list(dict.fromkeys(source_answer["sourceBlocks"]))
            answer["sourcePages"] = list(dict.fromkeys(
                answer_blocks[block_id]["page"] for block_id in answer["sourceBlocks"]
                if block_id in answer_blocks))
            answer["status"] = "explicit" if any(answer[key] for key in ("value", "solution", "explanation", "commentary", "knowledge")) else "missing"
        paper["audit"]["linkedAnswers"] = sum(q["answer"]["status"] == "explicit" for q in paper["questions"] if q["recordType"] == "question")
        paper["audit"]["ambiguousAnswers"] = sum(q["answer"]["status"] == "ambiguous" for q in paper["questions"] if q["recordType"] == "question")
    for row in rows:
        paper = papers[row["id"]]
        (OUT / row["json"]).write_text(json.dumps(paper, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    labels = {"value": "标准答案", "solution": "解答过程", "explanation": "解析", "commentary": "点评", "knowledge": "考点知识"}
    for row in rows:
        paper = papers[row["id"]]
        if paper["kind"] == "answers":
            continue
        page = OUT / row["reader"]
        content = page.read_text(encoding="utf-8")
        by_id = {q["id"]: q for q in paper["questions"]}

        def panel(match: re.Match) -> str:
            question = by_id.get(match.group(2))
            if not question or question["recordType"] != "question":
                return match.group(0)
            answer = question["answer"]
            fields = []
            if answer["status"] == "explicit":
                for key, label in labels.items():
                    if answer[key]:
                        fields.append(f'<div class="answer-field"><strong>{label}</strong><p>{escape(answer[key])}</p></div>')
            elif answer["status"] == "ambiguous":
                fields.append(f'<p class="answer-status">{escape(answer.get("ambiguityReason") or "题号对应不明确，暂不显示答案。")}</p>')
            else:
                fields.append('<p class="answer-status">此题暂无可用答案。</p>')
            source = ""
            source_id = (answer["sourceDocumentId"]
                         if answer["status"] == "explicit" or
                         answer["status"] == "ambiguous" and
                         (answer["sourceQuestionIds"] or answer["sourceBlocks"])
                         else None)
            if source_id in papers:
                source_row = next(r for r in rows if r["id"] == source_id)
                interleaved_cs408 = (paper["category"] == "cs408" and paper["kind"] == "complete" and
                                     answer["sourceQuestionIds"] == [question["id"]])
                anchors = ((answer["sourceBlocks"] or answer["sourceQuestionIds"])
                           if interleaved_cs408 else
                           (answer["sourceQuestionIds"] or answer["sourceBlocks"]))
                anchor = (anchors or [""])[0]
                href = rel(OUT / source_row["reader"], page) + ("#" + anchor if anchor else "")
                source = f'<a class="answer-source" href="{escape(href, quote=True)}">查看答案原卷位置 →</a>'
            body = '<details class="answer-panel"><summary>点击查看答案</summary>' + ''.join(fields) + source + '</details>'
            return match.group(1) + match.group(3) + body + match.group(4)

        content = re.sub(r'(<article class="question-card" id="([^"]+)"[^>]*>)(.*?)(</article>)', panel, content, flags=re.S)
        math_script = escape(rel(ROOT / "ui" / "answer-math.js", page), quote=True)
        content = content.replace('</body>', f'<script defer src="{math_script}"></script></body>')
        page.write_text(content, encoding="utf-8")


def build_index(rows: list[dict]) -> None:
    groups = defaultdict(list)
    for row in rows:
        groups[row["category"]].append(row)
    sections = []
    for category, (label, template, _) in PROFILES.items():
        cards = []
        for row in groups[category]:
            cards.append(f'<article class="paper-row"><div><a href="{escape(row["reader"])}">{escape(row["title"])}</a><small>{escape(row["kind"])} · {row["questions"]} 题 · {row["partialQuestions"]} 题待核</small></div><a href="{escape(row["json"])}">JSON</a></article>')
        sections.append(f'<section id="{category}"><h2>{escape(label)} <small>{len(cards)} 份 · 模板 {template}</small></h2>{''.join(cards)}</section>')
    nav = ''.join(f'<a href="#{k}">{escape(v[0])} <span>{len(groups[k])}</span></a>' for k, v in PROFILES.items())
    (OUT / "index.htm").write_text(f'<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>结构化试卷审阅</title><link rel="stylesheet" href="structured.css"></head><body class="structured-index"><header><a href="../index.htm">← 返回资料库</a><h1>结构化试卷审阅</h1><p>{len(rows)} 份资料 · 8 类排版模板 · 每份附原版、重排版和 JSON。题目解析不确定时请以原卷核对。</p></header><nav>{nav}</nav><main>{"".join(sections)}</main></body></html>', encoding="utf-8")


def write_templates() -> None:
    common = {
        "schema": SCHEMA,
        "optionLabels": ["A.", "B.", "C.", "D."],
        "answerFields": ["value", "solution", "explanation", "commentary", "knowledge"],
        "sourceTrace": ["sourceDocumentId", "sourceQuestionIds", "sourceBlocks", "sourcePages"],
    }
    category_rules = {
        "kaoyan": {"family": "english", "sections": ["writing", "cloze", "reading", "translation"], "choiceColumns": 2},
        "cet4": {"family": "english", "sections": ["writing", "listening", "reading", "translation"], "choiceColumns": 2},
        "cet6": {"family": "english", "sections": ["writing", "listening", "reading", "translation"], "choiceColumns": 2},
        "tem4": {"family": "english", "sections": ["dictation", "listening", "language", "reading", "writing"], "choiceColumns": 2},
        "tem8": {"family": "english", "sections": ["listening", "reading", "language", "translation", "writing"], "choiceColumns": 2},
        "cs408": {"family": "technical", "sections": ["single_choice", "free_response"], "choiceColumns": 2},
        "math3": {"family": "mathematics", "sections": ["single_choice", "fill_blank", "free_response"], "choiceColumns": 2},
        "politics": {"family": "humanities", "sections": ["single_choice", "multiple_choice", "free_response"], "choiceColumns": 2},
    }
    templates = {"version": 1, "common": common,
                 "templates": {PROFILES[k][1]: {"category": k, "label": PROFILES[k][0], **category_rules[k]}
                               for k in PROFILES}}
    (OUT / "templates.json").write_text(json.dumps(templates, ensure_ascii=False, indent=2), encoding="utf-8")


def write_question_bank(rows: list[dict]) -> dict:
    counts = Counter()
    with (OUT / "question-bank.jsonl").open("w", encoding="utf-8") as handle:
        for row in rows:
            paper = json.loads((OUT / row["json"]).read_text(encoding="utf-8"))
            for question in paper["questions"]:
                if question["recordType"] != "question":
                    continue
                item = {
                    "id": paper["id"] + ":" + question["id"], "paperId": paper["id"],
                    "category": paper["category"], "year": paper["year"], "template": paper["template"],
                    "number": question["number"], "questionType": question["questionType"],
                    "sectionTitle": question["sectionTitle"], "stem": question["stem"],
                    "context": question["context"],
                    "options": question["options"], "answer": question["answer"],
                    "sourcePages": question["sourcePages"], "sourceBlocks": question["sourceBlocks"],
                    "status": question["status"],
                }
                handle.write(json.dumps(item, ensure_ascii=False, separators=(",", ":")) + "\n")
                counts["questions"] += 1
                counts[question["questionType"]] += 1
                if question["answer"]["status"] == "explicit":
                    counts["linkedAnswers"] += 1
    return dict(counts)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="build only the first N papers for local debugging")
    args = parser.parse_args()
    docs = json.loads((ROOT / "documents.json").read_text(encoding="utf-8"))
    if args.limit:
        docs = docs[:args.limit]
    OUT.mkdir(parents=True, exist_ok=True)
    rows = [build_one(doc) for doc in docs]
    attach_answers(rows)
    write_templates()
    bank_counts = write_question_bank(rows)
    build_index(rows)
    report = {"schema": SCHEMA, "papers": len(rows), "categories": dict(Counter(r["category"] for r in rows)),
              "questionRecords": sum(r["questions"] for r in rows), "bank": bank_counts,
              "partialQuestions": sum(r["partialQuestions"] for r in rows),
              "sourceBlocks": sum(r["sourceBlocks"] for r in rows), "sourceOnlyBlocks": sum(r["sourceOnlyBlocks"] for r in rows),
              "documents": rows}
    (OUT / "audit.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "documents"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
