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
from urllib.parse import urlsplit

from bs4 import BeautifulSoup, NavigableString, Tag


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
NUMBERED_FIRST_OPTION_RE = re.compile(r"^\s*\d{1,3}\s*[.．、]\s*([A-D])\s*[)）.．、]\s*(.+)$")
LABEL_RE = re.compile(r"[（(]?\s*([A-D])\s*[)）.．、]?")
ANSWER_RE = re.compile(r"【(?:参考)?答案】\s*([A-D](?:\s*[,，、]\s*[A-D]){1,3}|[A-D]{1,4})")
NUMBERED_LETTER_RE = re.compile(r"(?:[（(]\s*(\d{1,3})\s*[）)]|(\d{1,3})\s*[.．、])\s*([A-D])(?=[.。\s（(]|$)")
NUMBERED_MATH_RE = re.compile(r"[（(]\s*(\d{1,3})\s*[）)]")
MATH_TEX_RE = re.compile(r"\\\((?:.|\n)*?\\\)|\\\[(?:.|\n)*?\\\]")
INLINE_OPTION_RE = re.compile(r"(?<![\w])([A-D])\s*([.．、])(?=\s|\S)")
POLITICS_CONTINUATION_RE = re.compile(r"^第\s*(?P<number>\d{1,3})\s*题\s*[（(]续[）)]\s*[:：]?\s*")
POLITICS_PAGE_ARTIFACT_RE = re.compile(r"\s+(?P<marker>-\s*(?P<number>\d{1,2})\s*[-•·])\s*$")
POLITICS_SUBQUESTION_RE = re.compile(r"[（(]\s*(?P<number>[1-9])\s*[）)]")
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
CHINESE_SECTION_RE = re.compile(r"^(?:第[一二三四五六七八九十]+[部章]|[一二三四五六七八九十]+[、.．]|\d+\s*[、.．]\s*(?:单项|多项|选择|填空|解答))")
PART_RE = re.compile(r"^(?i:part)\s*([A-ZⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]+)(?=\s|$)")
SECTION_RE = re.compile(r"^(?i:section)\s+([A-ZⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]+)(?=\s|$)")
PASSAGE_RE = re.compile(r"^(?:Text\s+\d+|Passage\s+(?:One|Two|Three|Four|Five|\d+)|Conversation\s+(?:One|Two|Three|Four|Five|\d+))\b", re.I)
IGNORE_SCHEMES = ("data:", "http:", "https:", "mailto:", "javascript:", "#")


def source_path(doc: dict) -> Path:
    return (ROOT / doc["reflow"]).resolve()


def rel(target: Path, page: Path) -> str:
    return os.path.relpath(target, page.parent).replace(os.sep, "/")


def normalized_number(value: str) -> str | None:
    match = QUESTION_RE.match(value)
    return str(int(next(g for g in match.groups() if g))) if match else None


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
    # normalized A-D display order is applied after merging choice blocks.
    return result


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


def email_lines(value: str, *, greeting: bool = False, signoff: bool = False) -> tuple[list[dict], str]:
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


def email_presentation(element: Tag, mode: str, signoff_right: bool) -> dict:
    value = plain(element)
    lines: list[dict] = []
    if mode == "after":
        trailing = value
    else:
        lines, trailing = email_lines(value, greeting=mode in {"start", "single"},
                                      signoff=mode in {"end", "single"})
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
        matches = list(POLITICS_SUBQUESTION_RE.finditer(display))
        # A pair of sequential prompts is much less likely to be a numbered
        # citation or a list embedded in source material.
        if len(matches) >= 2 and [m["number"] for m in matches] == [str(n) for n in range(1, len(matches) + 1)]:
            presentation["subquestions"] = [
                {"number": match["number"], "text": display[match.start():matches[i + 1].start() if i + 1 < len(matches) else len(display)].strip()}
                for i, match in enumerate(matches)
            ]
            for match in reversed(matches):
                if display[:match.start()].strip():
                    display = display[:match.start()].rstrip() + "\n" + display[match.start():]
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
        wanted = {item["number"] for item in presentation["subquestions"]}
        for node in list(copy.descendants):
            if not isinstance(node, NavigableString) or node.parent is None or node.find_parent(("svg", "pre", "script", "style")):
                continue
            value = str(node)
            matches = [match for match in POLITICS_SUBQUESTION_RE.finditer(value) if match["number"] in wanted]
            if not matches:
                continue
            rest = value
            for match in matches:
                before, rest = rest.split(match.group(), 1)
                if before:
                    node.insert_before(NavigableString(before))
                if (before.strip() or node.previous_sibling and str(node.previous_sibling).strip()):
                    br = BeautifulSoup("", "html.parser").new_tag("br")
                    br["class"] = "politics-subquestion-break"
                    node.insert_before(br)
                node.insert_before(NavigableString(match.group()))
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
            return "ABCD".index(match.group(1)) if match else 99
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

    def close_question() -> None:
        nonlocal current
        if current:
            if not current["options"] and current["sectionKind"] in {"single_choice", "multiple_choice"}:
                body = " ".join(b["text"] for b in blocks if b["id"] in current["sourceBlocks"] and b["role"] not in {"tex_source", "page_label"})
                matches = list(INLINE_OPTION_RE.finditer(body))
                for start in range(max(0, len(matches) - 3)):
                    group = matches[start:start + 4]
                    if [m.group(1) for m in group] != list("ABCD"):
                        continue
                    for i, match in enumerate(group):
                        end = group[i + 1].start() if i < 3 else len(body)
                        current["options"].append({"label": match.group(1) + ".", "sourceLabel": match.group(0).strip(),
                                                   "text": body[match.end():end].strip()})
                    current["stem"] = body[:group[0].start()].strip()
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
    for page_index, page in enumerate(pages, 1):
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
            if doc["category"] == "kaoyan" and doc["kind"] == "questions" and child.name == "p":
                if "Read the following email" in text and "reply" in text:
                    email_pending, email_open, email_followup = True, False, False
                elif email_pending and EMAIL_GREETING_RE.match(text):
                    email_mode = "single" if EMAIL_SIGNOFF_RE.search(text) else "start"
                    email_pending = False
                    email_open = email_mode == "start"
                    email_followup = email_mode == "single"
                elif email_open:
                    email_mode = "end" if EMAIL_SIGNOFF_RE.search(text) else "middle"
                    if email_mode == "end":
                        email_open = False
                        email_followup = not bool(re.search(r"ANSWER SHEET\.", text))
                elif email_followup and re.match(r"^(?:You should write|Write your answer)\b", text):
                    email_mode = "after"
                    email_followup = False
            presentation = email_presentation(child, email_mode, email_signoff_right) if email_mode else None
            if doc["category"] == "politics":
                presentation = politics_presentation(
                    doc, text, page_index, role, section_kind,
                    current["number"] if current else None,
                )
            block_id = f"b-{page_index}-{child_index}"
            block = {
                "id": block_id, "page": page_number, "sourcePageIndex": page_index,
                "sourceBlockIndex": child_index, "role": role, "text": text,
                "contentHtml": portable_html(child, original, json_path),
                "formulas": [n.get("data-tex", "") for n in child.select(".formula[data-tex]")],
                "images": [n.get("src", "") for n in child.select("img")],
            }
            if presentation:
                block["presentation"] = presentation
            blocks.append(block)
            if role == "page_label":
                rendered.append(f'<div class="source-block role-page_label" id="{block_id}" data-source-page="{escape(str(page_number))}" data-source-block="{child_index}">{escape(text)}</div>')
                continue
            number = normalized_number(text) if role == "question" else None
            if child.name in {"h1", "h2", "h3"} and doc["kind"] == "complete" and "答案" in text:
                in_answer_section = True
            if role == "choices" and child.select_one(".choice-number"):
                label = child.select_one(".choice-number")
                number = normalized_number(label.get_text(" ", strip=True)) if label else None
                if number:
                    section_choice_rows_seen = True
            same_choice_row = role == "choices" and number and current and current["number"] == number and not current["options"]
            continued = (role == "question" and number and current and current["number"] == number
                         and re.match(r"^\s*(?:[（(]\d+[）)]|\d+[.．、])\s*[（(]续[）)]", text))
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
                    "sourceBlocks": [], "sourcePages": [], "stem": text if role == "question" else "",
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
                section_kind = ("multiple_choice" if "多项" in text else
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
                    current["stem"] += " " + text
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
                        existing = {o["label"] for o in current["options"]}
                        for option in opts:
                            if option["label"] not in existing:
                                option["sourceOrder"] = len(current["options"]) + 1
                                current["options"].append(option)
                                existing.add(option["label"])
                        current["options"].sort(key=lambda option: "ABCD".index(option["label"][0]))
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
            if role == "choices" and current and len(current["options"]) not in (0, 4) and doc["kind"] == "questions":
                current["status"] = "partial"
                malformed += 1
            email_class = f' email-{presentation["segment"]}' if presentation and presentation["layoutKind"] == "email" else ""
            if presentation and presentation.get("signoffAlignment") == "right":
                email_class += " email-signoff-right"
            hidden = ' hidden' if presentation and presentation.get("continuation") and not presentation["displayText"] else ''
            rendered.append(f'<div class="source-block role-{role}{email_class}" id="{block_id}" data-source-page="{escape(str(page_number))}" data-source-block="{child_index}"{hidden}>{display_block(child, original, html_path, presentation, doc["category"] == "math3" and doc["kind"] == "questions")}</div>')
    close_question()

    for question in questions:
        if question["recordType"] == "answer":
            question["questionType"] = "answer"
        elif question["options"]:
            question["questionType"] = "multiple_choice" if question["sectionKind"] == "multiple_choice" else "single_choice"
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
    html = f'''<!doctype html><html lang="zh-CN" data-template="{profile[1]}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{escape(doc["title"])} · 结构化试卷</title>{''.join(source_styles)}<link rel="stylesheet" href="{links["css"]}"><link rel="stylesheet" href="{links["code_css"]}"></head><body><header class="structured-top"><a href="{links["index"]}">← 结构化试卷目录</a><strong>{escape(doc["title"])}</strong><span>{escape(profile[2])}</span><nav><a href="{links["original"]}">原版</a><a href="{links["reflow"]}">重排版</a><a href="{links["json"]}">JSON</a></nav></header><div class="structured-layout"><aside class="structured-toc"><strong>试卷目录</strong><a href="#paper-top">卷首</a>{''.join(nav)}</aside><main class="structured-main" id="paper-top"><div class="paper-intro"><p>{escape(doc["categoryLabel"])} · {escape(doc["kind"])} · {doc["year"]}</p><h1>{escape(doc["title"])}</h1><p>题号和章节目录由结构化数据生成。选项统一显示 A.、B.、C.、D.；原标记保留在 JSON 中。</p></div>{''.join(rendered)}</main></div><script defer src="{links["code_js"]}"></script></body></html>'''
    html_path.write_text(html, encoding="utf-8")
    return {"id": doc["id"], "category": doc["category"], "kind": doc["kind"], "title": doc["title"],
            "template": profile[1], "json": rel(json_path, OUT / "index.htm"), "reader": rel(html_path, OUT / "index.htm"),
            "questions": len(questions), "partialQuestions": payload["audit"]["partialQuestions"],
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


def answer_entries(paper: dict) -> dict[str, dict]:
    blocks = {block["id"]: block for block in paper["blocks"]}
    answers: dict[str, dict] = {}
    # Some answer books print the A-D key as one paragraph before detailed items.
    for block in paper["blocks"] if paper["category"] == "cs408" else []:
        if block["role"] != "content":
            continue
        matches = list(NUMBERED_LETTER_RE.finditer(block["text"]))
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
    return answers


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
        by_number = answer_entries(answer_paper)
        question_counts = Counter(q["number"] for q in paper["questions"] if q["recordType"] == "question")
        answer_blocks = {block["id"]: block for block in answer_paper["blocks"]}
        for question in paper["questions"]:
            if question["recordType"] != "question":
                continue
            source_answer = by_number.get(question["number"])
            if not source_answer:
                continue
            answer = question["answer"]
            if (paper["category"] == "math3" and
                    (question_counts[question["number"]] > 1 or
                     len(set(source_answer.get("sourceQuestionIds", []))) > 1)):
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
            source_id = answer["sourceDocumentId"] if answer["status"] == "explicit" else None
            if source_id in papers:
                source_row = next(r for r in rows if r["id"] == source_id)
                anchor = (answer["sourceQuestionIds"] or answer["sourceBlocks"] or [""])[0]
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
