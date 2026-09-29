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
from kaoyan_numbered_parts import numbered_parts as kaoyan_numbered_parts
from tem_public_answer_keys import attach_from_private_capture
from verified_cet_answer_exception import attach_verified_q50
from verified_cet_external_answers import attach_verified_reading
from verified_english_answer_import import attach_verified_word_bank_answers


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
CET_PDF_DOTTED_OPTION_PAPERS = frozenset({"cet6:2018-06-02", "cet6:2018-06-03"})


def valid_cet_source_label(paper_id: str, option: dict) -> bool:
    """Accept the literal A). label printed on two PDF-verified CET-6 papers."""
    source_label = option["sourceLabel"]
    match = LABEL_RE.fullmatch(source_label)
    if match and match.group(1) + "." == option["label"]:
        return True
    return (paper_id in CET_PDF_DOTTED_OPTION_PAPERS and
            source_label == option["label"][0] + ").")
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
MATH_CROSS_FORM_REFERENCE_RE = re.compile(
    r"【同试卷\s*(IV|V)\s*第(十四|十三|十二|十一|十|九|八|七|六|五|四|三|二|一)"
    r"(?:、[（(](\d{1,2})[）)])?题】"
)
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
ENGLISH_EXPLICIT_CHOICE_RE = re.compile(r"(?:故(?:本题)?(?:答案为|选择|选)|参考答案[：:]\s*)\s*([A-D])\s*[)）.．]?")
ENGLISH_NUMBERED_KEY_RE = re.compile(r"^\s*(\d{1,2})\s*[,，]\s*([A-D])\s*[).．]")
ENGLISH_ANSWER_PHRASE_RE = re.compile(r"答案\s*[：:]\s*(.+?)(?=【(?:解析|点评|精析)】|$)")
ENGLISH_TRANSCRIPT_QUESTION_RE = re.compile(r"^Q\s*(\d{1,2})(?:[.．?？\s])")
CET_CLOZE_LETTERS = "ABCDEFGHIJKLMNO"
CET_CLOZE_BLANK_RE = re.compile(r"(?<!\d)(2[6-9]|3\d|4[0-5])(?:\s*[.．])?(?!\d)")
CET_CLOZE_EMBEDDED_WORD_RE = re.compile(r"\s+([A-O0])\s*([)）.．])\s*")
TEM4_CLOZE_BLANK_RE = re.compile(r"\(\s*(3[1-9]|40)\s*\)")
ENGLISH_DECIMAL_PROSE_RE = re.compile(r"^\d+[.．]\s*\d")
# These line-leading numbers are continuation prose or a numbered list in
# the original PDF, not exam questions. Keep the source text unchanged.
ENGLISH_PROSE_QUESTION_BLOCKS = {
    ("cet4:2019-06-01", 5, 22): "50.",  # age 50, passage continues on p6
    ("cet4:2023-06-02", 5, 6): "14. About 100",  # aged 14
    ("cet6:2015-12-01", 8, 7): "1. Per-capita",
    ("cet6:2015-12-01", 8, 8): "2. Prevalence",
    ("cet6:2015-12-01", 8, 9): "3. Per-capita",
}
# In these ten papers the original PDF text on the recorded pages exposes
# every printed blank, while the reflow HTML loses one or more markers.
# The page bounds guard against silently applying the evidence to a new scan.
CET_CLOZE_PDF_VERIFIED = {
    "cet4:2015-06-01": (36, 3, 4),
    "cet4:2020-12-01": (26, 3, 4),
    "cet4:2021-06-02": (26, 3, 4),
    "cet4:2021-06-03": (26, 1, 2),
    "cet6:2019-12-01": (26, 4, 5),
    "cet6:2014-06-03": (36, 3, 4),
    "cet6:2019-12-02": (26, 4, 5),
    "cet6:2019-12-03": (26, 1, 2),
    "cet6:2020-07-01": (26, 4, 5),
    "cet6:2021-06-01": (26, 3, 4),
}
# The visible source PDF, page 5, prints "O) underneath"; HTML OCR merged it
# into "G. dental 0) underneath". Other zero/O cases remain unresolved.
CET_CLOZE_VERIFIED_ZERO_O = {"cet4:2022-06-01"}
# These two original PDFs print word-bank labels as "A). word". The reflow
# renderer keeps that exact label in data-source-label and normalizes the
# visible label to A.; the word text must already be free of label punctuation.
CET_CLOZE_PDF_DOT_WORD_BANKS = {"cet6:2018-06-02", "cet6:2018-06-03"}
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


KAOYAN_CLOZE_DIRECTIONS = re.compile(
    r"^(?:Read the following text\.\s*Choose the best word|"
    r"For each numbered blank in the following passage)", re.I,
)


def kaoyan_cloze_context(blocks: list[dict], number: str) -> dict:
    """Keep printed instructions separate from the shared cloze passage."""
    directions = blocks[:1] if blocks and KAOYAN_CLOZE_DIRECTIONS.match(blocks[0]["text"]) else []
    passage = blocks[len(directions):]
    return {
        "kind": "passage", "blankNumber": number,
        "text": "\n\n".join(block["text"] for block in passage),
        "instructionText": "\n\n".join(block["text"] for block in directions),
        "sourceBlocks": [block["id"] for block in blocks],
        "instructionSourceBlocks": [block["id"] for block in directions],
        "passageSourceBlocks": [block["id"] for block in passage],
        "sourcePages": list(dict.fromkeys(block["page"] for block in blocks)),
    }


def assign_kaoyan_group_labels(paper_id: str, questions: list[dict], toc: list[dict]) -> None:
    """Label questions by their printed section hierarchy, never by number ranges."""
    sections = {entry["id"]: entry for entry in toc if entry["kind"] == "section"}
    parents = {entry["id"]: entry.get("parentId") for entry in toc
               if entry["kind"] == "question"}
    for question in questions:
        question["labels"] = []
        if question["recordType"] != "question":
            continue
        leaf_id = parents.get(question["id"])
        leaf = sections.get(leaf_id)
        if leaf is None:
            continue
        ancestors = []
        current = leaf
        while current is not None:
            ancestors.append(current["label"])
            current = sections.get(current.get("parentId"))
        source_title = leaf["label"]
        if any("Use of English" in title for title in ancestors):
            kind, text = "cloze", "完形填空"
        elif any("Reading Comprehension" in title for title in ancestors):
            if re.fullmatch(r"Text\s+\d+", source_title, re.I):
                kind, text = "reading", f"阅读理解 · {source_title}"
            elif source_title == "Part B":
                if (question["questionType"] == "free_response" and
                        (question.get("context") or {}).get("kind") == "translation_passage"):
                    kind, text = "translation", "翻译 · Part B"
                else:
                    kind, text = "matching", "阅读匹配 · Part B"
            elif source_title == "Part C":
                kind, text = "translation", "翻译 · Part C"
            else:
                continue
        elif any("Writing" in title for title in ancestors):
            kind, text = "writing", f"写作 · {source_title}"
        elif any("Translation" in title for title in ancestors):
            kind, text = "translation", f"翻译 · {source_title}"
        else:
            continue
        question["labels"] = [{
            "id": f"{paper_id}:group:{leaf_id}", "kind": kind, "text": text,
            "sourceTitle": source_title,
            "sourceBlockId": f"{paper_id}:{leaf_id}",
        }]


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
    if "source-choice-block" in classes:
        # The source generator keeps a printed question and its options in
        # one coordinate block. Classify that block by its contained stem;
        # a page-break continuation may contain only the remaining choices.
        return "question" if element.select_one(":scope > .question") else "choices"
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
    if "source-choice-block" in classes:
        choices = element.select_one(":scope > .choices")
        return options_from(choices) if choices else []
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
        displayed_label = label_node.get_text(" ", strip=True)
        match = LABEL_RE.fullmatch(displayed_label)
        if not match:
            continue
        letter = match.group(1)
        source_label = label_node.get("data-source-label", displayed_label)
        value = deepcopy(item)
        value.select_one(marker).decompose()
        result.append({"label": letter + ".", "sourceLabel": source_label, "text": plain(value)})
    # Keep the source sequence until the question has recorded it. The
    # normalized A-E display order is applied after merging choice blocks.
    return result


def cs408_stem_continuation(element: Tag, role: str, text: str) -> str:
    """Return question prose before choices, never the options or an answer tail."""
    classes = set(element.get("class", []))
    if role == "choices" and "source-choice-block" in classes:
        paragraphs = []
        for child in element.find_all(recursive=False):
            if "choices" in child.get("class", []):
                break
            if child.name == "p" and "paragraph" in child.get("class", []):
                paragraphs.append(plain(child))
        return "".join(paragraphs)
    if role != "content" or element.name != "p" or "paragraph" not in classes:
        return ""
    if re.match(r"^\s*(?:解答|解析|答案)\s*[：:]", text):
        return ""
    if ("参考答案" in text or "综合应用题" in text or
            re.search(r"(?:^|\s|[。！？])A[.．]\s*\S", text)):
        return ""
    return text


def append_cs408_stem(stem: str, continuation: str) -> str:
    """Join OCR page fragments without inserting a space inside a Chinese word."""
    continuation = continuation.strip()
    if not continuation:
        return stem
    stem = stem.rstrip()
    separator = (" " if stem and stem[-1].isascii() and stem[-1].isalnum()
                 and continuation[0].isascii() and continuation[0].isalnum() else "")
    return stem + separator + continuation


def cs408_continued_options(text: str) -> list[dict]:
    """Parse only a numbered '(续)' line consisting of the remaining C/D choices."""
    prefix = re.match(r"^\s*\d{1,2}\s*[.．、]\s*[（(]续[）)]\s*", text)
    if not prefix:
        return []
    printed = text[prefix.end():]
    matches = list(INLINE_OPTION_RE.finditer(printed))
    if len(matches) != 2 or matches[0].start() != 0 or [match.group(1) for match in matches] != ["C", "D"]:
        return []
    options = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(printed)
        value = printed[match.end():end].strip()
        if not value:
            return []
        options.append({"label": match.group(1) + ".", "sourceLabel": match.group(0).strip(),
                        "text": value})
    return options


def repair_cs408_2013_choice_options(question: dict, blocks: list[dict]) -> None:
    """Restore two page-four choices checked against the original 2013 PDF."""
    by_id = {block["id"]: block for block in blocks}
    owned = [by_id[block_id] for block_id in question["sourceBlocks"] if block_id in by_id]
    labels = [option["label"] for option in question["options"]]
    if question["number"] == "22" and labels == ["A.", "B.", "C."]:
        continuation = next((block for block in owned if block["page"] == "4"
                             and block["role"] == "content"
                             and block["text"] == "D. 中断I/O 方式适用于所有外部设备，DMA 方式仅适用于快速外部设备"), None)
        if continuation:
            question["options"].append({
                "label": "D.", "sourceLabel": "D.",
                "text": continuation["text"][len("D. "):], "sourceOrder": 4,
            })
    if question["number"] != "27":
        return
    source = next((block for block in owned if block["page"] == "4"
                   and block["text"] == "A. 200 B. 295 C. 300 D .390"), None)
    if not source:
        return
    correction = {"kind": "original_pdf_visual", "page": "4", "sourceLabel": "D ."}
    if labels == ["A.", "B.", "C."] and question["options"][2]["text"] == "300 D .390":
        question["options"][2]["sourceText"] = question["options"][2]["text"]
        question["options"][2]["text"] = "300"
        question["options"].append({
            "label": "D.", "sourceLabel": "D.", "text": "390", "sourceOrder": 4,
            "transcriptionCorrection": correction,
        })
    elif labels == ["A.", "B.", "C.", "D."] and question["options"][3]["sourceLabel"] == "D .":
        question["options"][3]["sourceLabel"] = "D."
        question["options"][3]["transcriptionCorrection"] = correction


def cet_word_bank_from(element: Tag, source_block_id: str, document_id: str,
                       word_id_prefix: str | None = None) -> tuple[list[dict], list[dict]]:
    """Read one A–O word bank, retaining OCR text when a label was joined to a word."""
    if "options" not in element.get("class", []):
        return [], []
    words = []
    unresolved = []
    for item in element.select(":scope > li"):
        label_node = item.select_one(":scope > .option-label")
        if label_node is None:
            continue
        displayed_label = label_node.get_text(" ", strip=True)
        match = re.fullmatch(r"([A-O])\s*[)）.．]", displayed_label)
        if not match:
            continue
        source_label = displayed_label
        value = deepcopy(item)
        value.select_one(":scope > .option-label").decompose()
        source_value = plain(value)
        raw_item = plain(item)
        if document_id in CET_CLOZE_PDF_DOT_WORD_BANKS:
            source_label = label_node.get("data-source-label")
            if (source_label != match.group(1) + ")." or
                    not source_value.strip() or re.match(r"^\.\s+", source_value)):
                raise ValueError(f"CET PDF word-bank punctuation changed: {document_id} {raw_item}")
        markers = list(CET_CLOZE_EMBEDDED_WORD_RE.finditer(source_value))
        pieces = [(match.group(1), source_label, source_value[:markers[0].start()] if markers else source_value)]
        for index, marker in enumerate(markers):
            end = markers[index + 1].start() if index + 1 < len(markers) else len(source_value)
            printed_label = marker.group(1) + marker.group(2)
            printed_text = source_value[marker.end():end]
            if marker.group(1) == "0" and document_id not in CET_CLOZE_VERIFIED_ZERO_O:
                unresolved.append({"sourceLabel": printed_label, "sourceText": raw_item,
                                   "text": printed_text.strip(" _·"), "sourceBlockId": source_block_id})
            else:
                pieces.append(("O" if marker.group(1) == "0" else marker.group(1),
                               printed_label, printed_text))
        for letter, printed_label, printed_text in pieces:
            word = {"id": f"{word_id_prefix or document_id}:word-bank:{letter}", "label": letter + ".",
                    "sourceLabel": printed_label, "text": printed_text.strip(" _·"),
                    "sourceOrder": CET_CLOZE_LETTERS.index(letter) + 1,
                    "sourceBlockId": source_block_id, "sourceText": raw_item}
            if printed_label.startswith("0"):
                word["transcriptionCorrection"] = {"sourceLabel": printed_label,
                                                     "displayLabel": "O.",
                                                     "reason": "OCR zero in the printed A–O word bank"}
            words.append(word)
    return words, unresolved


def cet_cloze_sections(doc: dict, pages: list[Tag]) -> tuple[dict[str, tuple[range, dict]], list[dict]]:
    """Select only Reading Section A banks with a PDF-verified printed range."""
    if doc["category"] not in {"cet4", "cet6"} or doc["kind"] != "questions":
        return {}, []
    entries = [(f"b-{page_index}-{index}", page_index, child)
               for page_index, page in enumerate(pages, 1)
               for index, child in enumerate(page.find_all(recursive=False), 1)]
    result = {}
    issues = []
    reading_part = False
    for index, (block_id, page, element) in enumerate(entries):
        heading = plain(element)
        if re.match(r"^Part", heading, re.I) and "Reading Comprehension" in heading:
            # OCR can render "Part III" as "Part ][" and classify it as <p>.
            reading_part = True
        if element.name not in {"h1", "h2", "h3"}:
            continue
        if PART_RE.match(heading) and "Reading Comprehension" not in heading:
            reading_part = "Reading Comprehension" in heading
        if heading != "Section A":
            continue
        end = next((position for position in range(index + 1, len(entries))
                    if entries[position][2].name in {"h1", "h2", "h3"}
                    and plain(entries[position][2]) == "Section B"), None)
        if end is None:
            continue
        verified = CET_CLOZE_PDF_VERIFIED.get(doc["id"])
        if not reading_part and not (verified and (page, entries[end][1]) == verified[1:]):
            continue
        region = entries[index + 1:end]
        bank = [entry for entry in region if "options" in entry[2].get("class", [])]
        source_text = " ".join(plain(element) for _, _, element in region
                               if "options" not in element.get("class", []))
        markers = {int(match.group(1)) for match in CET_CLOZE_BLANK_RE.finditer(source_text)}
        printed = next((range(first, first + 10) for first in (26, 36)
                        if set(range(first, first + 10)) <= markers), None)
        evidence = {"kind": "source_html_number_sequence",
                    "sourcePages": list(range(page, entries[end][1] + 1))}
        if printed is None and verified and (page, entries[end][1]) == verified[1:]:
            printed = range(verified[0], verified[0] + 10)
            evidence["kind"] = "verified_original_pdf_text"
        if printed is not None and bank:
            result[block_id] = printed, evidence
        elif doc["year"] >= 2013 and (re.search(r"ten\s+blanks|word\s+bank", source_text, re.I) or sum(
                len(element.select(":scope > li")) for _, _, element in bank) >= 10):
            issues.append({
                "code": "reading_section_a_cloze_unverified",
                "sourceBlockId": block_id, "sourcePages": evidence["sourcePages"],
                "observedBlankNumbers": sorted(markers),
                "wordBankSourceBlocks": [bank_id for bank_id, _, _ in bank],
            })
    return result, issues


def tem4_cloze_sections(doc: dict, pages: list[Tag]) -> dict[str, tuple[range, dict]]:
    """Find each printed Part IV, including a supplemental alternate form."""
    if doc["category"] != "tem4" or doc["kind"] != "questions":
        return {}
    entries = [(f"b-{page_index}-{index}", page_index, child)
               for page_index, page in enumerate(pages, 1)
               for index, child in enumerate(page.find_all(recursive=False), 1)]
    result = {}
    for index, (block_id, page, element) in enumerate(entries):
        if element.name not in {"h1", "h2", "h3"} or not re.match(
                r"^PART\s+IV\b.*\bCLOZE\b", plain(element), re.I):
            continue
        end = next((position for position in range(index + 1, len(entries))
                    if entries[position][2].name in {"h1", "h2", "h3"}
                    and re.match(r"^PART\s+(?:IV|V)\b", plain(entries[position][2]), re.I)),
                   len(entries))
        region = entries[index + 1:end]
        if not any("options" in child.get("class", []) for _, _, child in region):
            continue
        markers = {int(match.group(1)) for _, _, child in region
                   for match in TEM4_CLOZE_BLANK_RE.finditer(plain(child))}
        if markers != set(range(31, 41)):
            # Do not synthesize a blank omitted from the reflow source.
            continue
        result[block_id] = range(31, 41), {
            "kind": "source_html_number_sequence",
            "sourcePages": list(range(page, entries[end - 1][1] + 1)),
        }
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
    """Separate only sentences explicitly starting a new 'Do not' direction."""
    parts = re.split(r"(?<=\.)\s+(?=Do not\b)", value.strip())
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


def display_writing_instructions(instructions: list[dict], extra_class: str = "") -> str:
    parts = []
    for instruction in instructions:
        content = escape(instruction["text"])
        prefix = instruction["strongPrefix"]
        if prefix and content.startswith(escape(prefix)):
            content = f"<strong>{escape(prefix)}</strong>" + content[len(escape(prefix)):]
        parts.append(f"<p>{content}</p>")
    return f'<div class="email-instructions{extra_class}">' + "".join(parts) + '</div>'


def display_email_block(presentation: dict) -> str:
    result = ""
    if presentation["lines"]:
        lines = "".join(
            f'<p class="email-line email-{line["role"]}">{escape(line["text"])}</p>'
            for line in presentation["lines"]
        )
        result = f'<div class="email-card-part">{lines}</div>'
    if presentation["instructions"]:
        result += display_writing_instructions(presentation["instructions"])
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
                          section_kind: str, current_number: str | None,
                          answer_note_active: bool = False) -> dict | None:
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
    if (doc["id"] == "politics:2022-questions" and section_kind == "other"
            and current_number in {"34", "35", "36", "37", "38"} and role == "content"):
        answer_note = POLITICS_ANSWER_NOTE_RE.search(display)
        if answer_note:
            presentation["answerNote"] = {
                "kind": "printed_answer_hint", "sourceMarker": answer_note.group(),
                "text": display[answer_note.end():].strip(),
            }
            display = display[:answer_note.start()].rstrip()
        elif answer_note_active:
            presentation["answerNote"] = {
                "kind": "printed_answer_hint_continuation", "sourceMarker": None,
                "text": display.strip(),
            }
            display = ""
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
    if presentation.get("answerNote"):
        if not presentation["displayText"]:
            copy.clear()
            return
        paragraphs = copy.select(":scope > p")
        for index, paragraph in enumerate(paragraphs):
            if POLITICS_ANSWER_NOTE_RE.match(paragraph.get_text(" ", strip=True)):
                for trailing in paragraphs[index:]:
                    trailing.decompose()
                break
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
    if presentation and presentation["layoutKind"] == "writing_instructions":
        return display_writing_instructions(presentation["instructions"], " writing-instructions")
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


def kaoyan_2024_source_segments(doc: dict, pages: list[Tag], json_path: Path) -> dict[str, list[dict]]:
    """Recover printed matching names and underlined translations from one verified PDF."""
    if doc["id"] != "kaoyan:2024-01":
        return {}
    if len(pages) < 13:
        raise ValueError("2024 English I source no longer has pages 11–13")

    def source_element(page: int, index: int) -> Tag:
        children = pages[page - 1].find_all(recursive=False)
        if len(children) < index:
            raise ValueError(f"2024 English I source block b-{page}-{index} missing")
        return children[index - 1]

    if (plain(source_element(11, 1)) != "Part B" or
            plain(source_element(12, 4)) != "Part C" or
            "(41-45)" not in plain(source_element(11, 3)) or
            "underlined segments" not in plain(source_element(12, 6))):
        raise ValueError("2024 English I matching/translation source boundary changed")
    pdf = ROOT.parent / "kaoyan-web-2026-09-26" / ".firecrawl" / "2024-01.pdf"
    if not pdf.is_file():
        raise FileNotFoundError(pdf)
    pdf_path = rel(pdf.resolve(), json_path.resolve())
    anchored: dict[str, list[dict]] = defaultdict(list)

    # The next name can share the preceding comment's paragraph. Preserve
    # that source block for both tasks rather than assigning it to one.
    comment_blocks = [(f"b-{page}-{index}", plain(source_element(page, index)))
                      for page, indices in ((11, range(4, 8)), (12, range(1, 3)))
                      for index in indices]
    names: dict[int, dict] = {}
    active: int | None = None
    for block_id, value in comment_blocks:
        cursor = 0
        for match in re.finditer(r"\((4[1-5])\)\s*([A-Za-z]+)", value):
            prefix = value[cursor:match.start()].strip()
            if prefix:
                if active is None:
                    raise ValueError("2024 English I comment precedes its printed name")
                names[active]["parts"].append(prefix)
                names[active]["sourceBlocks"].append(block_id)
            number = int(match.group(1))
            if number in names:
                raise ValueError(f"2024 English I duplicate printed name {number}")
            names[number] = {"name": match.group(2), "anchor": block_id,
                             "parts": [], "sourceBlocks": [block_id]}
            active = number
            cursor = match.end()
        suffix = value[cursor:].strip()
        if suffix:
            if active is None:
                raise ValueError("2024 English I comment has no printed name")
            names[active]["parts"].append(suffix)
            names[active]["sourceBlocks"].append(block_id)
    if set(names) != set(range(41, 46)) or any(not item["parts"] for item in names.values()):
        raise ValueError("2024 English I matching names/comments incomplete")

    bank_block = "b-12-3"
    bank_element = source_element(12, 3)
    if "options" not in bank_element.get("class", []):
        raise ValueError("2024 English I A–G statement bank missing")
    bank = []
    for order, item in enumerate(bank_element.select(":scope > li"), 1):
        label_node = item.select_one(":scope > .option-label")
        source_label = plain(label_node) if label_node else ""
        match = re.fullmatch(r"([A-G])\s*[.)．）]", source_label)
        if not match:
            raise ValueError(f"2024 English I statement label changed: {source_label!r}")
        content = deepcopy(item)
        content.select_one(":scope > .option-label").decompose()
        bank.append({"id": f"kaoyan:2024-01:part-b:{match.group(1)}",
                     "label": match.group(1) + ".", "sourceLabel": source_label,
                     "text": plain(content), "sourceOrder": order,
                     "sourceBlockId": bank_block})
    if [item["label"] for item in bank] != [f"{letter}." for letter in "ABCDEFG"] or any(
            not item["text"] for item in bank):
        raise ValueError("2024 English I statement bank is not complete A–G")

    matching_context = {
        "kind": "matching_comments", "id": "kaoyan:2024-01:part-b",
        "text": plain(source_element(11, 3)) + "\n\n" + "\n\n".join(
            names[number]["name"] + "\n" + " ".join(names[number]["parts"])
            for number in range(41, 46)),
        "sourceBlocks": ["b-11-3", *(block_id for block_id, _ in comment_blocks), bank_block],
        "sourcePages": ["11", "12"], "choiceBankSourceBlock": bank_block,
        "choiceBank": bank, "pdfEvidence": {"path": pdf_path, "pages": [11, 12]},
    }
    for number in range(41, 46):
        item = names[number]
        source_blocks = list(dict.fromkeys([*item["sourceBlocks"], bank_block]))
        anchored[item["anchor"]].append({
            "number": str(number), "sectionKind": "single_choice", "sectionTitle": "Part B",
            "sourceBlocks": source_blocks,
            "sourcePages": list(dict.fromkeys(block_id.split("-")[1] for block_id in source_blocks)),
            "stem": item["name"] + "\n\n" + " ".join(item["parts"]),
            "options": [{"label": option["label"], "sourceLabel": option["sourceLabel"],
                         "text": option["text"], "sourceOrder": option["sourceOrder"],
                         "sourceOptionId": option["id"]} for option in bank],
            "context": matching_context,
        })

    passage_blocks = [f"b-13-{index}" for index in range(1, 8)]
    translation_context = {
        "kind": "translation_passage", "id": "kaoyan:2024-01:part-c",
        "text": "\n\n".join(plain(source_element(13, index)) for index in range(1, 8)),
        "sourceBlocks": ["b-12-6", *passage_blocks], "sourcePages": ["12", "13"],
        "instructionSourceBlock": "b-12-6",
        "pdfEvidence": {"path": pdf_path, "pages": [12, 13]},
    }
    translations: dict[int, dict] = {}
    for index in range(1, 8):
        block_id = f"b-13-{index}"
        active = None
        underline_index = 0
        for node in source_element(13, index).contents:
            if isinstance(node, NavigableString):
                for match in re.finditer(r"\((4[6-9]|50)\)", str(node)):
                    number = int(match.group(1))
                    if number in translations:
                        raise ValueError(f"2024 English I duplicate translation {number}")
                    translations[number] = {"sourceBlockId": block_id, "fragments": []}
                    active = number
            elif isinstance(node, Tag) and node.name == "u":
                underline_index += 1
                if active is None:
                    raise ValueError(f"2024 English I unnumbered underline in {block_id}")
                translations[active]["fragments"].append({
                    "sourceBlockId": block_id, "underlineIndex": underline_index,
                    "text": plain(node),
                })
    if set(translations) != set(range(46, 51)) or any(
            not value["fragments"] for value in translations.values()):
        raise ValueError("2024 English I numbered underlined translation spans incomplete")
    for number in range(46, 51):
        item = translations[number]
        stem = re.sub(r"\s+", " ", " ".join(
            fragment["text"] for fragment in item["fragments"])).strip()
        anchored[item["sourceBlockId"]].append({
            "number": str(number), "sectionKind": "free_response", "sectionTitle": "Part C",
            "sourceBlocks": [item["sourceBlockId"]], "sourcePages": ["13"],
            "stem": stem, "options": [], "context": translation_context,
            "translationFragments": item["fragments"],
        })
    return anchored


def add_cet_free_response_questions(doc: dict, blocks: list[dict], questions: list[dict],
                                    toc: list[dict], rendered: list[str]) -> int:
    """Index the printed CET writing task and Chinese-to-English passage.

    These tasks have no printed question number. Keep their section IDs apart
    from numbered choice questions, and require the actual directions/passage
    rather than manufacturing a task from a heading alone.
    """
    if doc["category"] not in {"cet4", "cet6"} or doc["kind"] != "questions":
        return 0

    positions = {block["id"]: index for index, block in enumerate(blocks)}
    first_numbered = next((index for index, block in enumerate(blocks)
                           if block["role"] in {"question", "choices"}), len(blocks))
    writing_directions = re.compile(r"\bDirections?\s*[:：,，]|\bFor this part\b", re.I)
    translation_directions = re.compile(r"\btranslate\b", re.I)
    section_boundary = re.compile(r"^\s*(?:Part\s+.{0,20}Listening Comprehension|"
                                  r"Part\s+.{0,20}Reading Comprehension)", re.I)
    page_furniture = re.compile(r"^(?:第\s*\d+\s*页\s*共\s*\d+\s*页|\d+)$")
    owned = 0

    for kind, directions_re in (("writing", writing_directions),
                                ("translation", translation_directions)):
        def model_text(block: dict) -> str:
            value = block["text"]
            if kind == "writing":
                # A few PDF text layers append the next part and ruled answer
                # lines to the writing paragraph. The raw block stays intact.
                value = re.split(r"\bPart.{0,12}Listening Comprehension\b",
                                 value, maxsplit=1, flags=re.I)[0]
                value = re.sub(r"(?:_\s*){8,}$", "", value)
            return value.strip()

        task_count = 0
        used_source_ids: set[str] = set()
        used_heading_ids: set[str] = set()
        candidates = [(index, False) for index in range(len(blocks))]
        if kind == "translation":
            candidates.extend((index, True) for index, block in enumerate(blocks)
                              if re.match(r"^\s*Part.{0,12}Translation\b", block["text"], re.I))
        for index, heading_fallback in candidates:
            direction = blocks[index]
            if direction.get("sourceSection") == "answers" or (
                    not heading_fallback and not directions_re.search(direction["text"])):
                continue
            if (direction["id"] in used_source_ids or
                    heading_fallback and direction["id"] in used_heading_ids):
                continue
            if kind == "translation" and not heading_fallback and not (
                    re.search(r"\bChinese\b|\bEnglish\b|\bpassage\b", direction["text"], re.I)
                    and (re.search(r"\bDirections?\s*[:：,，]|\bFor this part\b", direction["text"], re.I)
                         or "Translation" in direction["text"])):
                continue

            source = [direction]
            for block in blocks[index + 1:]:
                if (block.get("sourceSection") == "answers" or
                        block["role"] in {"section", "question", "choices"} or
                        section_boundary.match(block["text"])):
                    break
                if block["role"] not in {"content", "heading", "figure"}:
                    continue
                if (page_furniture.fullmatch(block["text"]) or
                        re.fullmatch(r"[_\s]+", block["text"]) or
                        block["text"].startswith("本页部分文字层异常")):
                    continue
                if block["text"] or block["images"]:
                    source.append(block)

            source_text = " ".join(model_text(block) for block in source)
            if kind == "translation":
                if heading_fallback and not any(block["images"] for block in source):
                    continue
                passage = [block for block in source if
                           len(re.findall(r"[\u4e00-\u9fff]", block["text"])) >= 15]
                image_passage = [block for block in source if block["images"]]
                if not passage and not image_passage:
                    # A second scan can repeat the directions without its
                    # Chinese text or image. Prefer a complete source region.
                    continue
                stem_blocks = passage if passage else [direction]
                status = "complete" if passage else "partial"
            else:
                if (not re.search(r"\bwrite\b", source_text, re.I) or
                        not re.search(r"\b(?:essay|composition|proposal|letter|advertisement|"
                                      r"speech|report|story|topic|words)\b", source_text, re.I) or
                        not (re.search(r"\bFor this part\b|\bSuppose\b", direction["text"], re.I)
                             or index > 0 and blocks[index - 1]["role"] == "section"
                             and "Writing" in blocks[index - 1]["text"]
                             or index < first_numbered and "Directions" in direction["text"]) or
                        re.search(r"\btranslate\s+a\s+passage\b", source_text, re.I)):
                    continue
                stem_blocks = source
                status = "complete"

            # A heading may be missing or fused with the direction paragraph
            # in the PDF extraction. It is supporting evidence, not the sole
            # criterion for creating a question.
            heading = next((block for block in reversed(blocks[:index])
                            if block["role"] == "section" and
                            ("Writing" if kind == "writing" else "Translation") in block["text"] and
                            block.get("sourceSection") != "answers"), None)
            if (kind == "writing" and heading and index > 0 and
                    positions[heading["id"]] == index - 2 and blocks[index - 1]["images"]):
                # Some PDF text layers retain a source image immediately
                # before the readable writing directions.
                source.insert(0, blocks[index - 1])
            source_ids = [block["id"] for block in source]
            source_pages = list(dict.fromkeys(block["page"] for block in source))
            task_count += 1
            qid = f"q-{kind}-{task_count}"
            if any(question["id"] == qid for question in questions):
                raise ValueError(f"duplicate CET {kind} task: {doc['id']}")
            question = {
                "id": qid,
                "number": kind.title() if task_count == 1 else f"{kind.title()} {task_count}",
                "sectionKind": "free_response",
                "sectionTitle": heading["text"] if heading else f"Part {'I' if kind == 'writing' else 'IV'} {kind.title()}",
                "recordType": "question", "sourceBlocks": source_ids,
                "sourcePages": source_pages,
                "stem": "\n\n".join(model_text(block) for block in stem_blocks if model_text(block)),
                "options": [], "answer": None, "status": status,
                "context": {
                    "kind": "writing_task" if kind == "writing" else "translation_passage",
                    "text": "\n\n".join(model_text(block) for block in source if model_text(block)),
                    "instructionText": model_text(direction),
                    "sourceBlocks": source_ids, "sourcePages": source_pages,
                    "instructionSourceBlocks": [direction["id"]],
                    "passageSourceBlocks": [block["id"] for block in stem_blocks],
                    "figureSourceBlocks": [block["id"] for block in source if block["images"]],
                },
            }
            if heading:
                question["labels"] = [{
                    "id": f"{doc['id']}:group:{heading['id']}",
                    "kind": kind, "text": f"{'写作' if kind == 'writing' else '翻译'} · {heading['text']}",
                    "sourceTitle": heading["text"],
                    "sourceBlockId": f"{doc['id']}:{heading['id']}",
                }]
            insertion = next((offset for offset, existing in enumerate(questions)
                              if existing["sourceBlocks"] and
                              positions[existing["sourceBlocks"][0]] > index), len(questions))
            questions.insert(insertion, question)
            toc_entry = {
                "kind": "question", "id": qid, "label": kind.title(),
                "number": question["number"], "level": 1,
                "parentId": heading["id"] if heading else None,
                "sourceBlockId": direction["id"],
            }
            toc_index = next((offset for offset, entry in enumerate(toc)
                              if positions.get(entry.get("sourceBlockId", ""), len(blocks)) > index), len(toc))
            toc.insert(toc_index, toc_entry)
            for block in source:
                # A fused OCR paragraph can remain attached to the preceding
                # numbered question. Keep that legacy ownership and ID stable;
                # the new task still cites the same printed source block.
                if not block.get("questionId"):
                    block["questionId"] = qid
                    if block.pop("status", None) == "source_only":
                        owned += 1
            used_source_ids.update(source_ids)
            if heading:
                used_heading_ids.add(heading["id"])
            anchor = next((offset for offset, html in enumerate(rendered)
                           if f'id="{direction["id"]}"' in html), None)
            hidden_anchor = (f'<article class="question-card recovered-question" '
                             f'id="{qid}" hidden></article>')
            if anchor is not None and direction.get("questionId") == qid:
                rendered.insert(anchor + 1, hidden_anchor)
            else:
                rendered.append(hidden_anchor)
    return owned


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
    kaoyan_extra_by_anchor = kaoyan_2024_source_segments(doc, pages, json_path)
    if doc["category"] == "kaoyan" and doc["id"] != "kaoyan:2024-01":
        pdf = ROOT.parent / "kaoyan-web-2026-09-26" / ".firecrawl" / (stem + ".pdf")
        kaoyan_extra_by_anchor.update(kaoyan_numbered_parts(
            doc, pages, pdf, rel(pdf.resolve(), json_path.resolve()), plain))
    cet_cloze_by_section, cet_cloze_quality_issues = cet_cloze_sections(doc, pages)
    tem4_cloze_by_section = tem4_cloze_sections(doc, pages)
    word_bank_cloze_by_section = {**cet_cloze_by_section, **tem4_cloze_by_section}
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
    cs408_answer_tail_active = False

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
                current["stem"] = "".join(
                    block.get("presentation", {}).get("displayText", block["text"])
                    for block in parts)
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
            if (doc["id"] == "cs408:2013-complete" and current["recordType"] == "question"
                    and current["number"] in {"22", "27"}):
                repair_cs408_2013_choice_options(current, blocks)
            if doc["category"] in {"cet4", "cet6"} and (
                    0 < len(current["options"]) < 4 or any(
                        not valid_cet_source_label(doc["id"], option)
                        for option in current["options"])):
                current["status"] = "partial"
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
    cet_cloze_active = False
    cet_cloze_region: list[tuple[dict, Tag]] = []
    cet_cloze_numbers = range(0)
    cet_cloze_evidence: dict = {}
    cet_cloze_section_id = ""

    def add_cet_cloze_questions() -> None:
        """Index printed blanks without converting a shared word bank into choices."""
        if not cet_cloze_region:
            return
        tem4_cloze = doc["category"] == "tem4"
        banks = [(block, element) for block, element in cet_cloze_region
                 if "options" in element.get("class", [])]
        first_bank = next((index for index, (_, element) in enumerate(cet_cloze_region)
                           if "options" in element.get("class", [])), len(cet_cloze_region))
        if tem4_cloze:
            direction_blocks = [block for block, _ in cet_cloze_region[:first_bank]
                                if block["role"] in {"content", "heading"}]
            last_bank = max(index for index, (_, element) in enumerate(cet_cloze_region)
                            if "options" in element.get("class", []))
            passage = [block for block, _ in cet_cloze_region[last_bank + 1:]
                       if block["role"] in {"content", "question"}]
        else:
            before_bank = [block for block, _ in cet_cloze_region[:first_bank]
                           if block["role"] not in {"page_label", "tex_source"}]
            directions_end = next((index for index in range(len(before_bank) - 1, -1, -1)
                                   if "more than once" in before_bank[index]["text"].lower()), None)
            if directions_end is not None:
                passage_start = directions_end + 1
            else:
                passage_start = next((index for index, block in enumerate(before_bank)
                                      if any(int(match.group(1)) in cet_cloze_numbers
                                             for match in CET_CLOZE_BLANK_RE.finditer(block["text"]))), 0)
            direction_blocks = before_bank[:passage_start]
            passage = [block for block in before_bank[passage_start:]
                       if block["role"] != "heading"
                       and not re.match(r"^Questions\s+\d+\s+to\s+\d+", block["text"], re.I)]
        if not passage:
            raise ValueError(f"word-bank cloze passage missing: {doc['id']} {cet_cloze_section_id}")
        word_bank, unresolved = [], []
        for block, element in banks:
            words, fragments = cet_word_bank_from(
                element, block["id"], doc["id"],
                f"{doc['id']}:{cet_cloze_section_id}" if tem4_cloze else None)
            word_bank.extend(words)
            unresolved.extend(fragments)
        labels = [word["label"] for word in word_bank]
        bank_complete = labels and len(labels) == 15 and set(labels) == {letter + "." for letter in CET_CLOZE_LETTERS}
        if not bank_complete:
            cet_cloze_quality_issues.append({
                "code": "word_bank_incomplete", "sourceBlockId": cet_cloze_section_id,
                "sourcePages": list(dict.fromkeys(block["page"] for block, _ in banks)),
                "wordBankSourceBlocks": [block["id"] for block, _ in banks],
                "missingLabels": [letter + "." for letter in CET_CLOZE_LETTERS
                                  if letter + "." not in labels],
                "unresolvedFragments": unresolved,
            })
        marker_blocks_by_number = {
            number: [block for block in passage
                     if any(int(match.group(1)) == number
                            for match in (TEM4_CLOZE_BLANK_RE if tem4_cloze else CET_CLOZE_BLANK_RE)
                            .finditer(block["text"]))]
            for number in cet_cloze_numbers
        }
        missing_markers = [number for number, matched in marker_blocks_by_number.items() if not matched]
        for number in missing_markers:
            cet_cloze_quality_issues.append({
                "code": "reflow_blank_marker_missing", "number": str(number),
                "sourceBlockId": cet_cloze_section_id,
                "sourcePages": cet_cloze_evidence["sourcePages"],
                "passageSourceBlocks": [block["id"] for block in passage],
                "pdfNumberEvidence": cet_cloze_evidence["kind"],
            })
        context_blocks = [*passage, *(block for block, _ in banks)]
        context = {
            "kind": "word_bank_cloze", "id": (f"{doc['id']}:{cet_cloze_section_id}"
                                             if tem4_cloze else f"{doc['id']}:reading-section-a"),
            "text": "\n\n".join(block["text"] for block in passage),
            "instructionText": "\n\n".join(block["text"] for block in direction_blocks),
            "instructionSourceBlocks": [block["id"] for block in direction_blocks],
            "sourceText": "\n\n".join(block["text"] for block in passage),
            "sourceBlocks": [block["id"] for block in context_blocks],
            "sourcePages": list(dict.fromkeys(block["page"] for block in context_blocks)),
            "passageSourceBlocks": [block["id"] for block in passage],
            "wordBankSourceBlocks": [block["id"] for block, _ in banks],
            "wordBankSourceText": "\n\n".join(block["text"] for block, _ in banks),
            "wordBank": sorted(word_bank, key=lambda word: word["sourceOrder"]),
            "unresolvedWordBankFragments": unresolved,
            "wordBankStatus": "complete" if bank_complete else "partial",
            "printedBlankNumbers": list(cet_cloze_numbers),
            "sourceNumberUnverifiedNumbers": missing_markers,
            "numberEvidence": cet_cloze_evidence,
        }
        for number in cet_cloze_numbers:
            marker_blocks = marker_blocks_by_number[number]
            anchor_block = marker_blocks[0] if marker_blocks else passage[0]
            occurrences[str(number)] += 1
            qid = f"q-{number}-{occurrences[str(number)]}"
            question = {
                "id": qid, "number": str(number), "sectionKind": "fill_blank",
                "sectionTitle": "PART IV CLOZE (10 MIN)" if tem4_cloze else "Section A",
                "recordType": "question",
                "sourceBlocks": [block["id"] for block in marker_blocks] or [block["id"] for block in passage],
                "sourcePages": list(dict.fromkeys(block["page"] for block in marker_blocks or passage)),
                "stem": f"{number}.", "options": [], "answer": None,
                "status": "complete" if marker_blocks and bank_complete else "partial",
                "context": context,
            }
            if not marker_blocks:
                question["sourceNumberUnverified"] = True
            questions.append(question)
            toc.append({"kind": "question", "id": qid, "label": f"第 {number} 题",
                        "number": str(number), "level": section_level + 1,
                        "parentId": cet_cloze_section_id, "sourceBlockId": anchor_block["id"]})
            rendered.append(
                f'<article id="{qid}" class="question-card cloze-question-anchor" '
                'style="height:0;overflow:hidden;margin:0;padding:0;border:0"></article>'
            )

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
            if cet_cloze_active and role == "section":
                add_cet_cloze_questions()
                cet_cloze_active = False
                cet_cloze_region = []
            if cet_cloze_active and role == "question":
                # A line-leading blank is still passage prose, not a question stem.
                role = "content"
            # A cloze blank at the start of a paragraph can be mislabelled as a
            # question by the source extractor. Until the option table begins,
            # it remains part of the shared passage.
            if (role == "question" and doc["category"] == "kaoyan" and
                    "Use of English" in section_title and not section_choice_rows_seen):
                role = "content"
            text = plain(child)
            if (doc["id"] == "kaoyan:2012-02" and page_index == 1
                    and child_index == 7 and role == "choices"
                    and text.startswith("G. I. Joe had a 11 career")):
                # The original PDF prints G.I. Joe as passage prose. The
                # reflow extractor mistook its leading G. for an option and
                # placed the sentence, including blank 11, in <ul.options>.
                role = "content"
            if (doc["category"] in {"kaoyan", "cet4", "cet6", "tem4", "tem8"}
                    and role == "question" and ENGLISH_DECIMAL_PROSE_RE.match(text)):
                # A decimal at the start of an extracted line remains prose.
                # The original PDFs include 5.5%, 15.2 percent and 25.5 米.
                role = "content"
            expected_prose = ENGLISH_PROSE_QUESTION_BLOCKS.get(
                (doc["id"], page_index, child_index))
            if expected_prose:
                if not text.startswith(expected_prose) or role != "question":
                    raise ValueError(f"English prose boundary changed: {doc['id']} "
                                     f"p{page_index} b{child_index}")
                role = "content"
            if (doc["category"] == "kaoyan" and section_title == "Part B"
                    and text == "1. (10 points)" and role == "question"):
                # In 2005 the PDF split "ANSWER SHEET 1. (10 points)" across
                # source blocks; the trailing page number is not a new task.
                role = "content"
            if (doc["category"] == "kaoyan" and role == "question"
                    and re.match(r"^\d+\.\d+(?:%|\s)", text)):
                # A leading decimal measurement in passage prose is not a
                # numbered exam item (2012 English II p13: "3.3%";
                # 2006 p3: "69.8 percent"; 2019 p13: "1.17 times").
                role = "content"
            if (doc["id"] in {"kaoyan:2002-01", "kaoyan:2003-01", "kaoyan:2004-01"}
                    and section_title == "Section III Writing" and current
                    and current["number"] == "46" and role == "question"
                    and re.match(r"^[12]\.\s+", text)):
                # The original PDF prints 1./2. as the outline inside Q46.
                role = "content"
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
            if (presentation is None and doc["category"] == "kaoyan"
                    and doc["kind"] == "questions" and current
                    and current["sectionTitle"] in {"Part A", "Section III Writing"}
                    and role == "content" and child.name == "p"
                    and re.search(r"\.\s+Do not\b", text)
                    and "ANSWER SHEET" in text.upper()):
                instructions = email_instructions(text)
                if len(instructions) > 1 and any(item["strongPrefix"] for item in instructions):
                    presentation = {"version": 1, "layoutKind": "writing_instructions",
                                    "instructions": instructions}
            if doc["category"] == "politics":
                presentation = politics_presentation(
                    doc, text, page_index, role, section_kind,
                    current["number"] if current else None,
                    bool(current and current.get("embeddedAnswerNote")),
                )
            displayed_text = (presentation.get("displayText", text)
                              if presentation else text)
            if role == "question" and "source-choice-block" in child.get("class", []):
                stem_node = child.select_one(":scope > .question")
                if stem_node is not None:
                    displayed_text = plain(stem_node)
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
            elif (doc["category"] == "politics" and doc["kind"] == "questions"
                  and role == "content" and
                  re.fullmatch(r"\s*答案\s*[:：]\s*[A-E]{1,5}\s*", text)):
                # The printed 2022 question sheet has standalone choice keys
                # immediately after Q1–33. Preserve the source block but
                # place it behind the explicit-answer boundary.
                block["sourceSection"] = "answers"
            if presentation:
                block["presentation"] = presentation
                if presentation.get("answerNote") and not presentation.get("displayText"):
                    block["sourceSection"] = "answers"
            blocks.append(block)
            if cet_cloze_active and role not in {"section", "page_label"}:
                cet_cloze_region.append((block, child))
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
                cs408_answer_tail_active = False
                occurrences[number] += 1
                qid = f"q-{number}-{occurrences[number]}"
                current = {
                    "id": qid, "number": number, "sectionKind": section_kind,
                    "sectionTitle": section_title,
                    "recordType": "answer" if in_answer_section else "question",
                    "sourceBlocks": [], "sourcePages": [], "stem": displayed_text if role == "question" else "",
                    "options": [], "answer": None, "status": "complete" if role == "question" else "partial",
                    "context": (kaoyan_cloze_context(section_context_blocks, number)
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
                cs408_answer_tail_active = False
                if block_id in word_bank_cloze_by_section:
                    cet_cloze_numbers, cet_cloze_evidence = word_bank_cloze_by_section[block_id]
                    cet_cloze_section_id = block_id
                    cet_cloze_active = True
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
            if doc["id"] == "cs408:2011-complete" and current:
                # This printed edition places each solution directly after its
                # question. Keep its source link for the explicit answer route,
                # but do not expose a solution paragraph or figure as v1
                # question content before the learner reveals the answer.
                if role in {"content", "choices"} and CS408_SOLUTION_RE.search(text):
                    cs408_answer_tail_active = True
                if cs408_answer_tail_active and role in {"content", "figure"}:
                    role = block["role"] = "answer"
            if current:
                block["questionId"] = current["id"]
                current["sourceBlocks"].append(block_id)
                if page_number not in current["sourcePages"]:
                    current["sourcePages"].append(page_number)
                if continued:
                    continued_options = (cs408_continued_options(text)
                                         if doc["category"] == "cs408" and doc["kind"] == "complete"
                                         else [])
                    if continued_options and [option["label"] for option in current["options"]] == ["A.", "B."]:
                        for option in continued_options:
                            option["sourceOrder"] = len(current["options"]) + 1
                            current["options"].append(option)
                    else:
                        current["stem"] += " " + displayed_text
                if (doc["category"] == "cs408" and doc["kind"] == "complete"
                        and current["recordType"] == "question" and not current["options"]
                        and current["number"].isdigit() and int(current["number"]) <= 40):
                    continuation_text = cs408_stem_continuation(child, role, text)
                    if continuation_text:
                        current["stem"] = append_cs408_stem(current["stem"], continuation_text)
                if presentation and presentation["layoutKind"] == "politics":
                    if presentation.get("answerNote"):
                        note = current.setdefault("embeddedAnswerNote", {
                            "version": 1, "kind": "printed_answer_hint", "field": "solution",
                            "text": "", "sourceDocumentId": doc["id"],
                            "sourceBlocks": [], "sourcePages": [],
                        })
                        note["text"] += presentation["answerNote"]["text"]
                        note["sourceBlocks"].append(block_id)
                        if page_number not in note["sourcePages"]:
                            note["sourcePages"].append(page_number)
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
                if role == "choices" or (role == "question" and
                                         "source-choice-block" in child.get("class", [])):
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
            hidden = (' hidden' if presentation and not presentation.get("displayText")
                      and (presentation.get("continuation") or presentation.get("answerNote")) else '')
            rendered.append(f'<div class="source-block role-{role}{email_class}" id="{block_id}" data-source-page="{escape(str(page_number))}" data-source-block="{child_index}"{hidden}>{display_block(child, original, html_path, presentation, doc["category"] == "math3" and doc["kind"] == "questions")}</div>')
            for recovered in kaoyan_extra_by_anchor.get(block_id, []):
                if current is not None or section_title != recovered["sectionTitle"]:
                    raise ValueError(f"English I recovered task has wrong section: {doc['id']} "
                                     f"{block_id} current={current and current['number']} "
                                     f"section={section_title!r} expected={recovered['sectionTitle']!r}")
                number = recovered["number"]
                occurrences[number] += 1
                if occurrences[number] != 1:
                    raise ValueError(f"English I duplicate recovered question {number}")
                qid = f"q-{number}-1"
                questions.append({"id": qid, "recordType": "question", "answer": None,
                                  "status": "complete", **recovered})
                toc.append({"kind": "question", "id": qid, "label": f"第 {number} 题",
                            "number": number, "level": section_level + 1,
                            "parentId": section_stack.get(section_level),
                            "sourceBlockId": block_id})
                rendered.append(
                    f'<article class="question-card recovered-question" id="{qid}" '
                    f'data-question="{number}" '
                    'style="height:0;overflow:hidden;margin:0;padding:0;border:0"></article>'
                )
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
                    cards = ordering_cards(stem, source_html, blocks[:-1])
                if [card["number"] for card in cards] != [str(n) for n in range(41, 46)]:
                    raise ValueError(f"Part B source slots changed: {doc['id']}")
                instruction_blocks: list[dict] = []
                if stem in ORDERING_PAPERS:
                    part_b_start = next((index for index in range(len(blocks) - 2, -1, -1)
                                         if blocks[index]["text"] == "Part B"), None)
                    if part_b_start is None:
                        raise ValueError(f"Part B instruction heading missing: {doc['id']}")
                    for source_block in blocks[part_b_start + 1:-1]:
                        if re.match(r"^[A-H]\s*[)）.．]", source_block["text"]):
                            break
                        if source_block["role"] in {"section", "heading", "content"} and source_block["text"]:
                            instruction_blocks.append(source_block)
                    if not instruction_blocks:
                        raise ValueError(f"Part B instructions missing: {doc['id']}")
                for card in cards:
                    number = card["number"]
                    occurrences[number] += 1
                    if occurrences[number] != 1:
                        raise ValueError(f"duplicate Part B question: {doc['id']} Q{number}")
                    qid = f"q-{number}-1"
                    option_sources = card.get("optionSourceBlocks", [])
                    source_ids = list(dict.fromkeys([*(item["id"] for item in instruction_blocks),
                                                     *option_sources, block_id]))
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
                                     "text": value, "sourceOrder": order,
                                     "sourceOptionId": f"{doc['id']}:part-b:{letter}",
                                     "sourceBlocks": card.get("optionBlockIds", {}).get(letter, [])}
                                    for order, (letter, value) in enumerate(card["options"].items(), 1)],
                        "answer": None, "status": "complete",
                        "context": {"kind": card["kind"],
                                    "text": "\n\n".join(item["text"] for item in instruction_blocks)
                                            if instruction_blocks else section_title,
                                    "sourceBlocks": source_ids,
                                    "sourcePages": source_pages, "figureBlockId": block_id,
                                    "instructionSourceBlocks": [item["id"] for item in instruction_blocks],
                                    "diagramSequence": card.get("diagramSequence", []),
                                    "sourceDiagramText": card.get("sourceDiagramText", ""),
                                    "choiceBank": [{"id": f"{doc['id']}:part-b:{letter}",
                                                    "label": letter + ".", "text": value,
                                                    "sourceOrder": order,
                                                    "sourceBlocks": card.get("optionBlockIds", {}).get(letter, [])}
                                                   for order, (letter, value)
                                                   in enumerate(card["options"].items(), 1)],
                                    "fixedLetters": card.get("fixedLetters", []),
                                    "pdfEvidence": {"path": rel(pdf.resolve(), json_path.resolve()),
                                                    "pages": [11, 12]}},
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
    if cet_cloze_active:
        add_cet_cloze_questions()
    source_only -= add_cet_free_response_questions(doc, blocks, questions, toc, rendered)

    if doc["id"] in {"kaoyan:2002-01", "kaoyan:2003-01", "kaoyan:2004-01"}:
        writing = [question for question in questions if question["recordType"] == "question"
                   and question["number"] == "46"
                   and question["sectionTitle"] == "Section III Writing"]
        if len(writing) != 1:
            raise ValueError(f"old English I writing task boundary changed: {doc['id']}")
        question = writing[0]
        owned = [block for block in blocks if block["id"] in question["sourceBlocks"]]
        requirements = [block for block in owned if re.match(r"^[12]\.\s+", block["text"])]
        if [block["text"][:2] for block in requirements] != ["1.", "2."]:
            raise ValueError(f"old English I writing outline changed: {doc['id']}")
        question["writingRequirements"] = [
            {"text": block["text"], "sourceBlockId": block["id"]} for block in requirements]
        question["stem"] = "\n".join(block["text"] for block in owned
                                       if block["role"] in {"question", "content"})

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
        embedded_note = question.get("embeddedAnswerNote")
        question["answer"] = {
            "value": question["answer"], "solution": embedded_note["text"] if embedded_note else None,
            "explanation": None,
            "commentary": None, "knowledge": None,
            "sourceDocumentId": doc["id"] if question["answer"] or embedded_note else None,
            "sourceQuestionIds": [question["id"]] if question["answer"] or embedded_note else [],
            "sourceBlocks": embedded_note["sourceBlocks"] if embedded_note else [],
            "sourcePages": embedded_note["sourcePages"] if embedded_note else
                           list(question["sourcePages"]) if question["answer"] else [],
            "status": "explicit" if question["answer"] or embedded_note else "missing",
        }

    if doc["category"] == "kaoyan" and doc["kind"] == "questions":
        assign_kaoyan_group_labels(doc["id"], questions, toc)

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
                  "cetClozeQualityIssues": cet_cloze_quality_issues,
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
            # A page-break choice wrapper can also contain the printed
            # 解答 line after its last option (2011 Q31).
            if not marker or block["role"] not in {"answer", "content", "choices"}:
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
            elif (int(question["number"]) <= 40 and
                  not fields["explanation"] and not fields["solution"]):
                # The 2009–15 complete papers also print a key table before
                # numbered prose such as "12．考查符号位的扩展。". Those prose
                # records have no explicit 解析 marker, but are the original
                # explanation for their own numbered item.
                heading = re.match(r"^\s*(\d{1,3})\s*[.．、]\s*(.+)", question["stem"], re.S)
                if heading and str(int(heading.group(1))) == question["number"]:
                    parts = [heading.group(2).strip()]
                    parts.extend(blocks[block_id]["text"].strip()
                                 for block_id in question["sourceBlocks"][1:]
                                 if blocks[block_id]["role"] in {"content", "question", "figure"}
                                 and blocks[block_id]["text"].strip())
                    fields["explanation"] = "\n".join(parts) or None
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


def pdf_verified_embedded_english_entries(paper: dict, blocks: dict[str, dict]) -> dict[str, dict]:
    """Resolve two damaged answer sections only where the original PDF is decisive.

    The 2015 CET4 guide puts answer 50 inside record 49 and merges later
    explanations into records 55/61. The 2012 CET6 guide sometimes prints a
    letter from another option order; its answer words uniquely match the
    options printed in this question paper. Keep the exact source blocks.
    """
    if paper["id"] not in {"cet4:2015-06-01", "cet6:2012-06-01"}:
        return {}
    questions = {q["number"]: q for q in paper["questions"] if q["recordType"] == "question"}
    records = {q["number"]: q for q in paper["questions"] if q["recordType"] == "answer"}
    result = {}

    def entry(value: str, record: dict | None, evidence: list[dict]) -> dict:
        if not value or not evidence or any(block["sourceSection"] != "answers" for block in evidence):
            raise ValueError(f"English answer evidence changed: {paper['id']}")
        fields = {key: None for key in ("value", "solution", "explanation", "commentary", "knowledge")}
        fields.update(value=value, sourceQuestionIds=[record["id"]] if record else [],
                      sourceBlocks=[block["id"] for block in evidence])
        return fields

    if paper["id"] == "cet4:2015-06-01":
        # The original PDF prints ten word-bank explanations on pp 15–16.
        # Its OCR corrupts several leading question numbers, so match each
        # printed answer word to the intact A–O bank and retain the exact
        # explanation block as provenance. No letter is inferred from prose.
        cloze_keys = (
            (36, "A", "announcing", "15"), (37, "K", "entitled", "15"),
            (38, "G", "critically", "15"), (39, "L", "potential", "16"),
            (40, "D", "commitment", "16"), (41, "H", "develop", "16"),
            (42, "J", "enhance", "16"), (43, "O", "retain", "16"),
            (44, "E", "component", "16"), (45, "C", "challenges", "16"),
        )
        for number, letter, word, page in cloze_keys:
            question = questions.get(str(number))
            bank = (question or {}).get("context") or {}
            if (bank.get("kind") != "word_bank_cloze" or
                    [(item["label"], item["text"]) for item in bank["wordBank"]
                     if item["label"] == letter + "."] != [(letter + ".", word)]):
                raise ValueError(f"CET4 2015-06 word-bank question {number} changed")
            printed = re.compile(r"^.{0,12}(?<![A-Z])" + letter +
                                 r"[)）.．]\s*" + re.escape(word) + r"(?![A-Za-z])", re.I)
            evidence = [block for block in paper["blocks"]
                        if block["page"] == page and block.get("sourceSection") == "answers"
                        and printed.search(block["text"])
                        and "辨析题" in block["text"][:100]]
            if len(evidence) != 1:
                raise ValueError(f"CET4 2015-06 cloze answer {number} evidence changed")
            result[str(number)] = entry(letter, None, evidence)
        # Pages 17–20 print the complete A–K paragraph matching key. PDF
        # page 18's final glyph for 48 is garbled, but its G) paragraph and
        # "定位到文章G)" locator agree. The reflow drops the heading for 50.
        matching = {46: ("K", "18"), 47: ("A", "18"), 48: ("G", "18"),
                    49: ("I", "18"), 50: ("B", "19"), 51: ("D", "19"),
                    52: ("E", "19"), 53: ("H", "20"), 54: ("F", "20"),
                    55: ("J", "20")}
        for number, (value, page) in matching.items():
            if str(number) not in questions:
                raise ValueError(f"CET4 2015-06 question {number} changed")
            record = records.get("49" if number == 50 else str(number))
            if not record:
                raise ValueError(f"CET4 2015-06 answer {number} changed")
            source = [blocks[bid] for bid in record["sourceBlocks"] if bid in blocks]
            if number == 48:
                evidence = [block for block in source if block["page"] == page and
                            (re.match(r"^G\.\s*Companies are also trying", block["text"]) or
                             "定位到文章G)段画线处" in block["text"])]
                if len(evidence) != 2:
                    raise ValueError("CET4 2015-06 answer 48 PDF locator changed")
            else:
                evidence = [block for block in source if block["page"] == page and
                            re.search(r"故\s*(?:本题)?\s*答案为\s*" + value + r"\s*[)）]", block["text"])]
                if len(evidence) != 1:
                    raise ValueError(f"CET4 2015-06 answer {number} PDF conclusion changed")
            result[str(number)] = entry(value, record, evidence)
        # The answer to 4 continues at the top of page 11 without a repeated
        # number; record 4 on page 25 is merely a listening transcript.
        fourth = [block for block in paper["blocks"] if block["page"] == "11" and
                  "rather disappointing" in block["text"] and
                  re.search(r"故本题答案为\s*A", block["text"])]
        if len(fourth) != 1 or "4" not in questions:
            raise ValueError("CET4 2015-06 answer 4 PDF continuation changed")
        result["4"] = entry("A", None, fourth)
        # Record 61 contains explanations for 62–65 as well. Restrict the
        # provenance to the first printed conclusion on PDF page 22.
        sixty_first = records.get("61")
        if not sixty_first or "61" not in questions:
            raise ValueError("CET4 2015-06 answer 61 changed")
        source = [blocks[bid] for bid in sixty_first["sourceBlocks"] if bid in blocks]
        evidence = [block for block in source if block["page"] == "22" and
                    ("rich countries" in block["text"] or re.search(r"故答案为\s*B", block["text"]))]
        if len(evidence) != 2:
            raise ValueError("CET4 2015-06 answer 61 PDF conclusion changed")
        result["61"] = entry("B", sixty_first, evidence)
        return result

    def normalized_words(value: str) -> str:
        return re.sub(r"[\W_]+", "", value).casefold()

    for number in range(11, 19):
        question, record = questions.get(str(number)), records.get(str(number))
        if not question or not record:
            raise ValueError(f"CET6 2012-06 listening answer {number} changed")
        source = [blocks[bid] for bid in record["sourceBlocks"] if bid in blocks]
        marked = [(block, match) for block in source
                  if (match := re.match(r"^【答案】\s*([A-D])\s*[)）.．]\s*(.+)$", block["text"]))]
        if len(marked) != 1:
            raise ValueError(f"CET6 2012-06 listening key {number} changed")
        block, printed = marked[0]
        words = re.sub(r"\s+\d+\s*/\s*\d+\s*$", "", printed.group(2)).strip()
        matching_options = [option for option in question["options"]
                            if normalized_words(option["text"]) == normalized_words(words)]
        if len(matching_options) != 1:
            raise ValueError(f"CET6 2012-06 listening answer {number} does not match one source option")
        result[str(number)] = entry(matching_options[0]["label"].rstrip("."), record, [block])

    for number in range(82, 87):
        question, record = questions.get(str(number)), records.get(str(number))
        if not question or not record:
            raise ValueError(f"CET6 2012-06 translation answer {number} changed")
        question_text = " ".join(blocks[bid]["text"] for bid in question["sourceBlocks"] if bid in blocks)
        source = [blocks[bid] for bid in record["sourceBlocks"] if bid in blocks]
        answer_text = " ".join(block["text"] for block in source)
        question_body = re.sub(r"^\s*\d+[.．]\s*", "", question_text)
        answer_body = re.sub(r"^\s*\d+[.．]\s*", "", answer_text)
        blank = re.search(r"_{5,}", question_body)
        question_hint = re.search(r"[（(]\s*([\u3400-\u9fff][^）)]*)[）)]", question_body)
        answer_hint = re.search(r"[（(]\s*([\u3400-\u9fff][^）)]*)[）)]", answer_body)
        if not blank or not question_hint or not answer_hint:
            raise ValueError(f"CET6 2012-06 translation evidence {number} changed")
        prefix = question_body[:blank.start()].strip()
        if (not answer_body.startswith(prefix) or
                re.sub(r"\s+", "", question_hint.group(1)) !=
                re.sub(r"\s+", "", answer_hint.group(1))):
            raise ValueError(f"CET6 2012-06 translation prompt {number} disagrees with answer")
        value = answer_body[len(prefix):answer_hint.start()].strip()
        result[str(number)] = entry(value, record, source)
    return result


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
    result.update(pdf_verified_embedded_english_entries(paper, blocks))
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


def resolve_math_cross_form_references(papers: dict[str, dict]) -> None:
    """Resolve printed V-to-IV answer references with both sources intact."""
    fields = ("value", "solution", "explanation", "commentary", "knowledge")
    for paper in papers.values():
        if paper["category"] != "math3" or paper["kind"] != "questions" or not 1987 <= paper["year"] <= 1996:
            continue
        forms = dual_form_math_question_forms(paper)
        target_index: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
        for question in paper["questions"]:
            if question["recordType"] != "question":
                continue
            section = re.match(r"^\s*([一二三四])\s*[、.．]", question.get("sectionTitle", ""))
            target_index[(forms.get(question["id"]), section.group(1) if section else "main",
                          question["number"])].append(question)

        for question in paper["questions"]:
            if question["recordType"] != "question":
                continue
            answer = question["answer"]
            printed_fields = [(key, answer[key]) for key in fields
                              if answer[key] and "【同试卷" in answer[key]]
            if not printed_fields:
                continue
            field, original = printed_fields[0]
            matches = list(MATH_CROSS_FORM_REFERENCE_RE.finditer(original))
            marker = matches[0].group(0) if matches else original
            reference = {
                "printedText": marker, "originalAnswerText": original,
                "sourceField": field,
                "sourceDocumentId": answer["sourceDocumentId"],
                "sourceQuestionIds": list(answer["sourceQuestionIds"]),
                "sourceBlocks": list(answer["sourceBlocks"]),
                "sourcePages": list(answer["sourcePages"]),
                "targetPaperId": paper["id"], "targetForm": None,
                "targetSection": None, "targetNumber": None,
                "targetQuestionId": None, "targetAnswerSourceDocumentId": None,
                "targetAnswerSourceQuestionIds": [], "targetAnswerSourceBlocks": [],
                "targetAnswerSourcePages": [], "scope": None,
                "resolutionStatus": "unresolved",
            }
            answer["references"] = [reference]

            def unresolved(reason: str) -> None:
                for key in fields:
                    answer[key] = None
                answer["status"] = "ambiguous"
                answer["ambiguityReason"] = "跨卷答案引用未能唯一核对，暂不可判分"
                reference["unresolvedReason"] = reason

            if len(printed_fields) != 1 or len(matches) != 1 or forms.get(question["id"]) != "V":
                unresolved("来源卷别或引用格式不唯一")
                continue
            source_marker = marker
            if (paper["year"] == 1996 and question["id"] == "q-6-2" and
                    source_marker == "【同试卷 IV 第六题】" and
                    source_marker in question["stem"]):
                # The original PDF prints 第七题 on both the V question (p. 58)
                # and answer (p. 79); the reflow transcription says 第六题.
                marker = "【同试卷 IV 第七题】"
                reference["printedText"] = marker
                reference["pdfVerifiedCorrection"] = {
                    "transcribedText": source_marker, "questionPage": "58",
                    "answerPage": "79",
                    "sourceSha256": "1c50e01719d065bc79f96f283bbd513245533d98789d8bc487a51e9a0f158a83",
                }
            match = MATH_CROSS_FORM_REFERENCE_RE.fullmatch(marker)
            if match is None:
                unresolved("引用未完整匹配")
                continue
            form, section_label, item = match.groups()
            section = section_label if item else "main"
            number = str(int(item)) if item else str(MATH_OLD_MAIN_NUMBERS[section_label])
            reference.update(targetForm=form, targetSection=section, targetNumber=number)
            targets = target_index.get((form, section, number), [])
            if len(targets) != 1:
                unresolved(f"目标题数量为 {len(targets)}")
                continue
            target = targets[0]
            target_answer = target["answer"]
            reference.update(
                targetQuestionId=target["id"],
                targetAnswerSourceDocumentId=target_answer["sourceDocumentId"],
                targetAnswerSourceQuestionIds=list(target_answer["sourceQuestionIds"]),
                targetAnswerSourceBlocks=list(target_answer["sourceBlocks"]),
                targetAnswerSourcePages=list(target_answer["sourcePages"]),
            )
            if (target["id"] == question["id"] or target_answer["status"] != "explicit" or
                    not any(target_answer[key] for key in fields) or
                    any("【同试卷" in (target_answer[key] or "") for key in fields)):
                unresolved("目标答案缺失或仍为引用")
                continue

            # Most V questions print the same reference in their question
            # text. The one verified exception adds a local second subpart.
            stem_reference = MATH_CROSS_FORM_REFERENCE_RE.search(question["stem"])
            whole_answer = (original.strip() == source_marker and stem_reference and
                            stem_reference.group(0) == source_marker)
            partial = (paper["year"] == 1991 and question["id"] == "q-13-2" and
                       field == "solution" and target_answer["solution"] and
                       re.fullmatch(r"（1）\s*" + re.escape(marker) + r"\s*（2）\s*.+", original, re.S))
            if whole_answer:
                for key in fields:
                    answer[key] = target_answer[key]
                reference["scope"] = "whole_answer"
            elif partial:
                answer["solution"] = original.replace(marker, target_answer["solution"], 1)
                reference["scope"] = "part:1"
            else:
                unresolved("引用与题文或小问范围不符")
                continue
            reference["resolutionStatus"] = "resolved"
            answer["status"] = "explicit"


def printed_cet_matching_labels(paper: dict) -> set[str]:
    """Find the shared paragraph labels printed before question 36 in Section B.

    Older scans sometimes lose individual labels, so this is used to check
    letters beyond the usual A–O bank, not to infer missing answers.
    """
    question = next((q for q in paper["questions"]
                     if q["recordType"] == "question" and q["number"] == "36"), None)
    if not question or not question["sourceBlocks"]:
        return set()
    blocks = paper["blocks"]
    anchor = next((index for index, block in enumerate(blocks)
                   if block["id"] == question["sourceBlocks"][0]), None)
    if anchor is None:
        return set()
    start = next((index for index in range(anchor - 1, -1, -1)
                  if blocks[index]["text"].strip() == "Section B"), max(0, anchor - 90))
    labels = set()
    for block in blocks[start:anchor]:
        printed = block["text"].strip()
        match = re.match(r"^(?:\[([A-Z])\]|([A-Z])[.)])\s+", printed)
        if match and len(printed) > 70:
            labels.add(match.group(1) or match.group(2))
    return labels


def attach_public_english_answer_keys(papers: dict[str, dict]) -> dict[str, int]:
    """Apply only unambiguous letters from a matching public paper and question number."""
    manifest_path = Path(__file__).resolve().parents[1] / ".local/answer-keys/burningvocabulary.json"
    if not manifest_path.exists():
        return {}
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    counts = Counter()
    for source in manifest["papers"]:
        paper = papers.get(source["paperId"])
        if not paper or paper["category"] not in {"kaoyan", "cet4", "cet6"}:
            counts["unmatchedPapers"] += 1
            continue
        if paper["kind"] == "answers":
            continue
        matching_labels = printed_cet_matching_labels(paper) if paper["category"] in {"cet4", "cet6"} else set()
        keys = defaultdict(set)
        for token in source["answers"]:
            match = re.fullmatch(r"(\d{1,3})-([A-Z])", token)
            if match:
                keys[match.group(1)].add(match.group(2))
            else:
                counts["emptyOrMalformedSourceKeys"] += 1
        numbers = Counter(q["number"] for q in paper["questions"] if q["recordType"] == "question")
        for question in paper["questions"]:
            if question["recordType"] != "question":
                continue
            values = keys.get(question["number"])
            if not values:
                continue
            if numbers[question["number"]] != 1 or len(values) != 1:
                counts["ambiguousNumberOrKey"] += 1
                continue
            value = next(iter(values))
            labels = [option["label"].rstrip(".").upper() for option in question["options"]]
            if labels and (value not in labels or labels.count(value) != 1):
                counts["optionMismatch"] += 1
                continue
            # CET matching questions use one paragraph bank for 36–45, so the
            # individual question records have no options. Several public
            # grids contain P–R despite the local paper ending at O. Retain
            # extended letters only when that paragraph is actually printed.
            if (paper["category"] in {"cet4", "cet6"} and not labels
                    and question["number"].isdigit() and 36 <= int(question["number"]) <= 45
                    and value > "O" and value not in matching_labels):
                counts["sharedBankMismatch"] += 1
                continue
            answer = question["answer"]
            if answer["status"] == "explicit":
                if answer["value"] and answer["value"].strip().upper() != value:
                    counts["existingAnswerConflict"] += 1
                continue
            if answer["status"] != "missing":
                counts["otherExistingAnswer"] += 1
                continue
            answer["value"] = value
            answer["status"] = "explicit"
            answer["externalSource"] = {
                "url": source["sourceUrl"],
                "capturedAt": manifest["capturedAt"],
                "answerToken": f'{question["number"]}-{value}',
            }
            counts["attached"] += 1
        paper["audit"]["linkedAnswers"] = sum(
            q["answer"]["status"] == "explicit" for q in paper["questions"]
            if q["recordType"] == "question")
    return dict(counts)


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
            embedded_note = question.get("embeddedAnswerNote")
            if embedded_note and paper["id"] == "politics:2022-questions":
                note_text = embedded_note["text"]
                if note_text and note_text not in (answer["solution"] or ""):
                    answer["solution"] = "\n\n".join(
                        part for part in (answer["solution"], note_text) if part)
                answer["embeddedSource"] = {
                    "sourceDocumentId": embedded_note["sourceDocumentId"],
                    "sourceBlocks": embedded_note["sourceBlocks"],
                    "sourcePages": embedded_note["sourcePages"],
                    "kind": embedded_note["kind"],
                }
            answer["sourceDocumentId"] = answer_id
            answer["sourceQuestionIds"] = list(dict.fromkeys(source_answer["sourceQuestionIds"]))
            answer["sourceBlocks"] = list(dict.fromkeys(source_answer["sourceBlocks"]))
            answer["sourcePages"] = list(dict.fromkeys(
                answer_blocks[block_id]["page"] for block_id in answer["sourceBlocks"]
                if block_id in answer_blocks))
            answer["status"] = "explicit" if any(answer[key] for key in ("value", "solution", "explanation", "commentary", "knowledge")) else "missing"
        paper["audit"]["linkedAnswers"] = sum(q["answer"]["status"] == "explicit" for q in paper["questions"] if q["recordType"] == "question")
        paper["audit"]["ambiguousAnswers"] = sum(q["answer"]["status"] == "ambiguous" for q in paper["questions"] if q["recordType"] == "question")
    resolve_math_cross_form_references(papers)
    public_key_audit = attach_public_english_answer_keys(papers)
    tem_key_audit = attach_from_private_capture(
        papers,
        Path(__file__).resolve().parents[1] / ".local/answer-keys/burningvocabulary-tem.json",
        ROOT.parent / "english-exams-web-2026-09-26/manifest.json",
    )
    public_key_audit.update({f"tem{key[0].upper()}{key[1:]}": value
                             for key, value in tem_key_audit.items()})
    complete_corpus = set(papers) == {doc["id"] for doc in json.loads(
        (ROOT / "documents.json").read_text(encoding="utf-8"))}
    public_key_audit["sourceVerifiedWordBankAttached"] = attach_verified_word_bank_answers(
        papers, require_all=complete_corpus)
    public_key_audit["sourceVerifiedCetGridExceptionAttached"] = attach_verified_q50(papers)
    public_key_audit["sourceVerifiedCetReadingAttached"] = attach_verified_reading(papers)
    for paper in papers.values():
        if paper["category"] == "math3" and paper["kind"] == "questions":
            paper["audit"]["linkedAnswers"] = sum(
                q["answer"]["status"] == "explicit" for q in paper["questions"]
                if q["recordType"] == "question")
            paper["audit"]["ambiguousAnswers"] = sum(
                q["answer"]["status"] == "ambiguous" for q in paper["questions"]
                if q["recordType"] == "question")
    for row in rows:
        paper = papers[row["id"]]
        (OUT / row["json"]).write_text(json.dumps(paper, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    if public_key_audit:
        (OUT / "public-english-answer-audit.json").write_text(
            json.dumps(public_key_audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
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
            elif answer.get("externalSource"):
                source = (f'<a class="answer-source" href="{escape(answer["externalSource"]["url"], quote=True)}" '
                          'target="_blank" rel="noopener noreferrer">查看公开答案来源 →</a>')
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
                    **({"labels": question["labels"]} if "labels" in question else {}),
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
    parser.add_argument("--english-only", action="store_true",
                        help="rebuild English papers and merge their audit rows with existing other subjects")
    args = parser.parse_args()
    if args.english_only and args.limit:
        parser.error("--english-only and --limit cannot be combined")
    docs = json.loads((ROOT / "documents.json").read_text(encoding="utf-8"))
    previous_audit = None
    if args.english_only:
        previous_audit = json.loads((OUT / "audit.json").read_text(encoding="utf-8"))
        if previous_audit.get("schema") != SCHEMA or not isinstance(previous_audit.get("documents"), list):
            raise ValueError("a complete existing audit is required for English-only rebuild")
        docs = [doc for doc in docs if doc["category"] in {"kaoyan", "cet4", "cet6", "tem4", "tem8"}]
    if args.limit:
        docs = docs[:args.limit]
    OUT.mkdir(parents=True, exist_ok=True)
    rows = [build_one(doc) for doc in docs]
    attach_answers(rows)
    if previous_audit is not None:
        updates = {row["id"]: row for row in rows}
        existing = previous_audit["documents"]
        if not set(updates).issubset({row["id"] for row in existing}):
            raise ValueError("English-only rebuild found a paper absent from the previous full audit")
        rows = [updates.get(row["id"], row) for row in existing]
    if previous_audit is None:
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
