"""Build source-traceable English prose and translation sidecars.

This is an additive index over the canonical reflow and structured paper JSON.
It never changes either source.  A translation is reusable only while both the
printed source and the (possibly restored) translation input hashes agree.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from collections import Counter, defaultdict
from pathlib import Path

from pdf_verified_cet_bilingual_joins import verified_bilingual_completion_joins
from pdf_verified_cet_missing_options import verified_cet_missing_option_anchors
from pdf_verified_kaoyan_matching_options import verified_matching_option_anchors

ROOT = Path(__file__).resolve().parents[1]
REFLOW = ROOT / "data/sources/english-exams-reflow-latex"
STRUCTURED = ROOT / "data/sources/exam-library/structured"
CATEGORIES = {"kaoyan", "cet4", "cet6", "tem4", "tem8"}
BLANK_RUN = re.compile(r"^(\s*)(\d{1,3})(\s*)$")
INSTRUCTION = re.compile(
    r"^(?:directions\s*[:：]|questions?\s+\d+\s+(?:to|[-–])\s+\d+\b|"
    r"read\s+the\s+following|choose\s+the\s+best|for\s+this\s+part|"
    r"answer\s+the\s+following|you\s+(?:should|are\s+required)\b)", re.I
)
MAJOR_SECTION = re.compile(r"^(?:part\s*[ivxn]+|section\s*[ivx]+|section\s+iii|"
                           r"test\s+for\s+english\s+majors)\b", re.I)
DICTATION_NUMBER = re.compile(r"(?<!\d)(2[6-9]|3[0-5])(?!\d)")
PAGE_FOOTER = re.compile(r"第\s*(\d+)\s*页(?:\s*共\s*(\d+)\s*页)?")
# The short footers below were checked on the matching source PDF images, at
# the bottom of the specified page. A PDF hash guards against applying this
# exception to a different document with the same paper ID.
PDF_VERIFIED_SHORT_PAGE_FOOTERS = {
    ("cet6:2018-06-02", "deaa6e2ed08156b34f11c3e2ff71a4426790912adc20d5b2fe9c2b3945080c20"): {6},
    ("cet6:2018-06-03", "976c64492aa905cbd21a241414dc6fb406d88b5b97838da68e7689746c39db14"): {4, 5},
}
# On this PDF page the 26–35 cloze passage is split into heading and content
# blocks by its damaged text layer.  None of the fragments is safe to translate
# until the whole passage and its printed blanks have been recovered.
PDF_VERIFIED_DAMAGED_CLOZE_BLOCKS = {
    ("cet4:2021-12-02", "a7c3240ab8227732026cf0b7b0bd0841111d4c361bc078e2147aa1c954e44f1b"):
        {f"b-4-{number}" for number in range(9, 28)},
}
PDF_VERIFIED_UNFILLED_CLOZE = {
    ("cet6:2012-06-01", "b0923d500beaef575eccc6ee67a3518f609f637cac54fd25be8db1f6238731e0", "b-11-3"): "e6860ab8c76449a4225f0d92e26888c512141f10cd20c36aa2b151c33d5a8b04",
    ("cet6:2012-06-01", "b0923d500beaef575eccc6ee67a3518f609f637cac54fd25be8db1f6238731e0", "b-11-4"): "047665e3dc5bddfcac9f648e1b590ccaf0acfebcf4da34e0c3bae6a7ad8af628",
    ("cet6:2012-12-01", "587e72763ae07d4df3e5d94dafcf5d951b9ce2e5dbadc90ac74a498d5fe6f508", "b-13-8"): "7ca61b5f442bca2b51735fe773647a89472c4c88c752dc4976ac14ed0145bd8d",
    ("tem8:2022", "199db0425be520acad33f6c88858735144e5370d4ac97a9e208635ae5f13905b", "b-10-3"): "e0e59c4215b09b4e5573ad7f83cea8e9521c4ec3cf3ab37dfd9c339a8d405a0f",
    ("tem8:2022", "199db0425be520acad33f6c88858735144e5370d4ac97a9e208635ae5f13905b", "b-10-5"): "eb1032010d9173e6d583533400d18c9bc1faec4da0f1852f6d0a8b8685640fc5",
    ("tem8:2022", "199db0425be520acad33f6c88858735144e5370d4ac97a9e208635ae5f13905b", "b-11-7"): "41ad06c51b5c99b02abd7b48503d63594a83853164c96d8eabbd8c356b87df3f",
    ("tem8:2022", "199db0425be520acad33f6c88858735144e5370d4ac97a9e208635ae5f13905b", "b-11-8"): "ede554a001a2ae51a438253bf7d3e06c578fe30ae4c73882de3cc75dc842ea80",
    ("tem8:2025", "7bf9e8b344c9327f4e7be42376c2fee993a955c6d9ca8d54296c6fa1c66ec51d", "b-10-4"): "6fb39cac3434b850d225dd95344bbcd9fac149883ff838357af4962263ad3c32",
    ("tem8:2025", "7bf9e8b344c9327f4e7be42376c2fee993a955c6d9ca8d54296c6fa1c66ec51d", "b-10-5"): "6b38f1fb366dca2ad0a786c6e060a8d01fe188d66c4464dcda66203065652490",
}
PDF_VERIFIED_TEM_COVER = {
    "tem4:2022": "455847a702d9538ccf666f40863fb016fd3774341ca7375e2c14a7e7b5bce41f",
    "tem4:2023": "d3c2a59b11c320fc1ea545874888595f19fa99020767aced78429122ea5ef088",
    "tem4:2024": "eed081c9c6a046fd4eb1779e46c7adc75f5564b7ff543e5fd2bbdaa15a48c31b",
    "tem4:2025": "dba4e06838b9d36c49108d7c55b91fa351bd507cc65346eec14d862935748fea",
    "tem8:2022": "199db0425be520acad33f6c88858735144e5370d4ac97a9e208635ae5f13905b",
    "tem8:2023": "da8e307cb39c1c7a3229e3a5d75a15d5ee35f6e1170cb0c2e72e5b03330d2155",
    "tem8:2024": "cb2ea7588169de5d9f5dee6b8a8247926239d99d6cdd58f9a6b656438c3f6139",
    "tem8:2025": "7bf9e8b344c9327f4e7be42376c2fee993a955c6d9ca8d54296c6fa1c66ec51d",
}
PDF_VERIFIED_SINGLE_OPTION_PARAGRAPH = {
    ("cet6:2014-12-01", "cet6:2014-12-01:p:b-2-33"):
        ("32237ba2134b9f441aa766a02e09e4a1e71e738aee16df7274076ff34d6795e7",
         "468947bedff694915a724be5023b71dce632ed081f0e7864d8a20ad495bbb35d"),
}
PDF_VERIFIED_SINGLE_PRINTED_BLANKS = {
    ("cet6:2012-12-02", "e75b7941475cf515f43b58bed01ec452ca8431dbaf5181a6e9c49d081f42cdbc",
     "cet6:2012-12-02:p:b-4-12", "3e025e89595d21b8f12d385980489ab7ddf247e44180b600a5fd58666172e131"):
        ["_"],
}
# These notices were checked against the matching source PDFs. They remain in
# sourceText/sourceHash; only the derived text sent for translation omits them.
# Identity includes the exact paragraph and source PDF hashes so an OCR or
# edition change cannot silently apply an old exception.
PDF_VERIFIED_DIRECTION_NOTICES = {
    (
        "cet4:2016-06-02",
        "cet4:2016-06-02:p:b-7-18",
        "940b9083cb79d2f1916a55b7b80b5b262cd09a394e7da8c7eb5a374b0c25f9fe",
        "97907b3053ebf8224849fa9c8152083f4826c3541fbc4f9b2c208c0044255b64",
    ): ("prefix", "自测用时 minutes "),
    (
        "cet4:2017-06-01",
        "cet4:2017-06-01:p:b-1-3",
        "9b01017b16cb59b25f7fb4f97d1e7240e551359473a1d4e66c6b6c26fd5b2b49",
        "6432dfe655dea52e1d972937db67201728259a6debff8566f45dc59341eb0ad3",
    ): ("prefix", "(请于正式开考后半小时内完成该部分，之后将进行听力考试) "),
    (
        "cet4:2017-06-02",
        "cet4:2017-06-02:p:b-1-3",
        "1d955f8dba8ca20489940fe5fa560cefa34b6554ec7a59d22caaa35ed657c2a1",
        "5d18e4c84361263437dd6b47cc3e5ef9b84492c1a7b6cbdc8763d8e2273f06cf",
    ): ("prefix", "(请于正式开考后半小时内完成该部分，之后将进行听力考试) "),
    (
        "cet4:2017-06-03",
        "cet4:2017-06-03:p:b-1-3",
        "8c5295e229fc60f5409dc5420db0d4b932147d8dcd1c58bcbc2ce505cbb94355",
        "49f4568251d35ff1bb61cb2fb7986921f5f15fc476203973fd6a1fffe9b67217",
    ): ("prefix", "(请于正式开考后半小时内完成该部分，之后将进行听力考试) "),
    (
        "cet4:2017-12-01",
        "cet4:2017-12-01:p:b-1-3",
        "445dd376621ce712000e71bc90811fdfb9f4b9f7e57c17e4dceca9f960bf15a2",
        "9cd866a9767966b076d2f067dd34a777bbbd07b37f88bc665c0325f2da827509",
    ): ("prefix", "（请于正式开考后半小时内完成该部分，之后将进行听力考试） "),
    (
        "cet6:2012-06-01",
        "cet6:2012-06-01:p:b-1-4",
        "f016a1c843b7fd450508a32281064e3db05586d828918ae7a2e41e7a8a239e8c",
        "b0923d500beaef575eccc6ee67a3518f609f637cac54fd25be8db1f6238731e0",
    ): ("prefix", "注意：此部分试题在答题卡1 上。 "),
    (
        "cet6:2014-06-02",
        "cet6:2014-06-02:p:b-1-6",
        "67efbed35c9841c8eef6543674b0e80f94e949b7e5ad96b566b13ff4292810b4",
        "430a6e88ea19d6a08d28ddb04a6459d6fe378b8d94cb5f644904d167aa4d9404",
    ): ("suffix", " 注意：此部分试题请在答题卡1 上作答。"),
    (
        "cet6:2015-06-03",
        "cet6:2015-06-03:p:b-3-8",
        "c2f0298d4f7480c4c1a8b2f01cc980a185e40c17bc1a68e911693e5018089717",
        "37b1a6800448029599d6f4f34ee5b538980503a5c942b10d1956b42f524de969",
    ): ("suffix", " 注意：此部分试题请在答题卡1 上作答。"),
    (
        "cet6:2017-06-01",
        "cet6:2017-06-01:p:b-1-3",
        "50384f54b5155755749e78b9e3c89d9858e8e52eae3ab6de72f0b497c7a4c5d1",
        "216d0376df880ab7eae1a16bbf98d13e904a04a6e48a9b388d5feb2813411fb8",
    ): ("prefix", "(请于正式开考后半小时内完成该部分，之后将进行听力考试) "),
    (
        "cet6:2017-12-01",
        "cet6:2017-12-01:p:b-1-3",
        "521ec9462ede8a7f7dab81e58a0c8250d3f7fca8fb7fb4216bc12f17b75da7c5",
        "b97eed17980d88068daac1f0c10d90e5ac6645a25bab10328029368b587d9b03",
    ): ("prefix", "请于正式开考后半小时内完成该部分，之后将进行听力考试 "),
    (
        "cet6:2017-12-02",
        "cet6:2017-12-02:p:b-1-3",
        "a828385052a9e3f8461f5cbd66ded0ee05ff040822a0dfeda93b9f7892147320",
        "f16aa2a6b6fdd8c701633235ea4f2db51c24c27542568ee50d627f0a2a818167",
    ): ("prefix", "（请于正式开考后半小时内完成该部分，之后将进行听力考试） "),
    (
        "cet6:2017-12-03",
        "cet6:2017-12-03:p:b-1-3",
        "3419afefd02160f2f1b050228d4a86107e3974341083bca8525d336b78f87ffb",
        "c1e87ec25e9487c8a104c12b743505f6a68bc4d7ea861a2cbbec65f0ba898222",
    ): ("prefix", "（请于正式开考后半小时内完成该部分，之后将进行听力考试） "),
}
for _fixture_name, _fixture_schema in (
        ("pdf_verified_english_notice_suffixes.json", "pdf-verified-english-notice-suffixes.v1"),
        ("pdf_verified_english_numeric_footer_suffixes.json",
         "pdf-verified-english-numeric-footer-suffixes.v1")):
    _fixture = json.loads((Path(__file__).with_name(_fixture_name)).read_text(encoding="utf-8"))
    assert _fixture["schema"] == _fixture_schema
    for _notice in _fixture["entries"]:
        _notice_key = (_notice["paperId"], _notice["paragraphId"],
                       _notice["sourceHash"], _notice["pdfSha256"])
        assert _notice_key not in PDF_VERIFIED_DIRECTION_NOTICES
        PDF_VERIFIED_DIRECTION_NOTICES[_notice_key] = (_notice["edge"], _notice["notice"])
_verified_cross_page = json.loads(
    (Path(__file__).with_name("pdf_verified_english_cross_page_joins.json"))
    .read_text(encoding="utf-8"))
assert _verified_cross_page["schema"] == "pdf-verified-english-cross-page-joins.v1"
PDF_VERIFIED_CROSS_PAGE_JOINS = {
    (row["paperId"], row["pdfSha256"], row["toBlockId"]): row
    for row in _verified_cross_page["entries"]
}


def sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def raw_text(block: dict) -> str:
    return "".join(run.get("text", "") for run in block.get("runs", []))


def passage_option_text(block: dict) -> str:
    item = block["items"][0]
    return f"{item['label']}. " + raw_text(item)


def paragraph_choice_body(value: str) -> str:
    """Remove a printed option label, optionally preceded by its question number."""
    return re.sub(r"^(?:\d+[、.]\s*)?[A-P][).]\s*", "", value)


def same_printed_choice(paragraph: dict, option_text: str,
                        source_ids: list[str]) -> bool:
    """Allow layout-space drift, never a changed printed glyph or block."""
    return (bool(set(paragraph["sourceBlockIds"]) & set(source_ids)) and
            comparison_key(paragraph_choice_body(paragraph["sourceText"])) ==
            comparison_key(option_text))


def block_id(page: int, block: int) -> str:
    return f"b-{page}-{block}"


def is_prose(text: str) -> bool:
    words = re.findall(r"[A-Za-z][A-Za-z’'-]*", text)
    return len(words) >= 8 and not INSTRUCTION.match(text.strip())


def is_english_body(text: str) -> bool:
    words = re.findall(r"[A-Za-z][A-Za-z’'-]*", text)
    chinese = len(re.findall(r"[\u3400-\u9fff]", text))
    letters = sum(len(word) for word in words)
    return len(words) >= 3 and letters >= chinese * 2


def mixed_instruction_prefix(text: str) -> str | None:
    """Recover a complete English direction before a Chinese translation task.

    Some printed papers place both languages in one source paragraph. The
    Chinese task text must remain in sourceText but is not translation input.
    """
    chinese = re.search(r"[\u3400-\u9fff]", text)
    if not chinese:
        return None
    prefix = text[:chinese.start()].rstrip()
    if (re.search(r"\bdirections\s*[:：]", prefix, re.I) and
            len(re.findall(r"[A-Za-z]+", prefix)) >= 12 and
            re.search(r"[.!?。！？]$", prefix)):
        return prefix
    return None


def listening_dictation_blocks(raw: dict) -> dict[str, list[str]]:
    """Find printed Section C dictation blanks without guessing their words."""
    in_section_c = False
    in_dictation = False
    result = {}
    for pn, page in enumerate(raw["pages"], 1):
        for bi, block in enumerate(page["blocks"], 1):
            text = raw_text(block)
            lower = text.lower()
            if block.get("type") == "heading":
                if re.match(r"^section\s+c\b", text, re.I):
                    in_section_c = True
                    in_dictation = False
                elif ("reading comprehension" in lower or "translation" in lower or
                      "writing" in lower or re.match(r"^section\s*[ab]\b", text, re.I)):
                    in_section_c = False
                    in_dictation = False
            if (in_section_c and re.search(r"hear\s+a\s+passage\s+three\s+times", lower) and
                    re.search(r"fill\s+(?:in\s+)?the\s+blanks", lower)):
                in_dictation = True
                continue
            if in_dictation and block.get("type") == "paragraph" and is_prose(text):
                numbers = DICTATION_NUMBER.findall(text)
                if numbers:
                    result[block_id(pn, bi)] = numbers
    return result


def verified_dictation_words(blocks: dict[str, list[str]], evidence: dict | None) -> dict[str, str] | None:
    """Accept only a complete, ordered ten-blank passage with cited answer words."""
    if not blocks or not isinstance(evidence, dict):
        return None
    expected = [str(number) for number in range(26, 36)]
    printed = [number for numbers in blocks.values() for number in numbers]
    if printed != expected:
        return None
    if not all(str(evidence.get(field) or "").strip()
               for field in ("sourceUrl", "sourcePage", "passageMatchEvidence")):
        return None
    answers = evidence.get("answers")
    if not isinstance(answers, dict) or set(answers) != set(expected):
        return None
    words = {}
    for number in expected:
        item = answers[number]
        word = item.get("word") if isinstance(item, dict) else item
        if not isinstance(word, str) or not re.fullmatch(r"[A-Za-z][A-Za-z’' -]*", word.strip()):
            return None
        words[number] = word.strip()
    return words


def strip_verified_page_footers(text: str, source_blocks: list[tuple[int, str]],
                                total_pages: int,
                                pdf_verified_short_pages: set[int] | frozenset[int] = frozenset()) -> str | None:
    """Remove printed page furniture only when its page and total match source provenance."""
    matches = list(PAGE_FOOTER.finditer(text))
    if not matches:
        return text
    printed = []
    for page_number, block_text in source_blocks:
        for match in PAGE_FOOTER.finditer(block_text):
            if (int(match.group(1)) != page_number or
                    (match.group(2) is not None and int(match.group(2)) != total_pages) or
                    (match.group(2) is None and page_number not in pdf_verified_short_pages)):
                return None
            printed.append(match.groups())
    if Counter(printed) != Counter(match.groups() for match in matches):
        return None
    return PAGE_FOOTER.sub("", text).strip()


def protected_blanks(text: str) -> list[str]:
    """Keep visible prompt placeholders intact without inventing answers."""
    result = []
    for match in re.finditer(r"(?:\(\s*\d{1,3}\s*\)\s*)?[_＿](?:\s*[_＿])*", text):
        token = match.group()
        if len(re.findall(r"[_＿]", token)) == 1 and not token.lstrip().startswith("("):
            before = text[match.start() - 1:match.start()] if match.start() else ""
            after = text[match.end():match.end() + 1]
            if re.match(r"[A-Za-z0-9]", before) or re.match(r"[A-Za-z0-9]", after):
                continue  # A stray OCR underscore in a word, e.g. _genders.
        result.append(token)
    return result


def strip_verified_direction_notice(paper_id: str, pdf_hash: str, entry: dict) -> str | None:
    """Omit a PDF-verified edge notice from translation, preserving printed source."""
    original = entry.get("translationInput")
    if not original:
        return None
    key = (paper_id, entry["id"], entry["sourceHash"], pdf_hash)
    verified = PDF_VERIFIED_DIRECTION_NOTICES.get(key)
    if not verified:
        return None
    edge, notice = verified
    source = entry["sourceText"]
    if edge == "prefix" and source.startswith(notice) and original.startswith(notice):
        return original[len(notice):]
    if edge == "suffix" and source.endswith(notice) and original.endswith(notice):
        return original[:-len(notice)]
    return None


def comparison_key(text: str) -> str:
    """Ignore layout whitespace only; preserve every printed nonspace glyph."""
    return "".join(char for char in text if not char.isspace())


def selected_answer(question: dict, context: dict) -> dict | None:
    answer = question.get("answer") or {}
    if answer.get("status") != "explicit":
        return None
    letter = str(answer.get("value") or "").strip().rstrip(".").upper()
    if not re.fullmatch("[A-Z]", letter):
        return None
    choices = (context.get("wordBank", []) if context.get("kind") == "word_bank_cloze"
               else question.get("options", []))
    matches = [item for item in choices
               if str(item.get("label", "")).strip().rstrip(".").upper() == letter]
    return matches[0] if len(matches) == 1 and matches[0].get("text", "").strip() else None


def source_mapping(paper: dict, raw: dict) -> tuple[dict, dict, dict, list]:
    """Resolve raw reflow coordinates to generated structured block IDs.

    Structured IDs are assigned after layout repair, so their page/block
    numbers are not a reliable proxy for the reflow JSON coordinates.
    """
    raw_blocks = {block_id(pn, bi): (pn, block)
                  for pn, page in enumerate(raw["pages"], 1)
                  for bi, block in enumerate(page["blocks"], 1)}
    structured = {block["id"]: block for block in paper["blocks"]}
    raw_to_structured = defaultdict(list)
    structured_to_raw = defaultdict(list)
    issues = []
    for sid, block in structured.items():
        markers = re.findall(r'data-source-block-id="(b-\d+-\d+)"',
                             block.get("contentHtml") or "")
        for rid in markers:
            if rid not in raw_blocks:
                issues.append({"code": "missing_reflow_block", "blockId": sid,
                               "reflowBlockId": rid})
                continue
            if sid not in raw_to_structured[rid]:
                raw_to_structured[rid].append(sid)
            if rid not in structured_to_raw[sid]:
                structured_to_raw[sid].append(rid)
    # Options do not yet carry HTML source markers. A long, single lettered
    # reading choice can be matched only by exact normalized text on its page.
    choices_by_page_text = defaultdict(list)
    for sid, block in structured.items():
        if block.get("role") == "choices" and not structured_to_raw[sid]:
            page = int(sid.split("-")[1])
            choices_by_page_text[(page, comparison_key(block.get("text", "")))].append(sid)
    for rid, (page, block) in raw_blocks.items():
        if block.get("type") != "options" or len(block.get("items", [])) != 1:
            continue
        item = block["items"][0]
        if not re.fullmatch(r"[A-P]", item.get("label", "")) or not is_prose(raw_text(item)):
            continue
        candidates = choices_by_page_text[(page, comparison_key(passage_option_text(block)))]
        if len(candidates) == 1:
            sid = candidates.pop()
            raw_to_structured[rid].append(sid)
            structured_to_raw[sid].append(rid)
        elif len(candidates) > 1:
            issues.append({"code": "ambiguous_option_mapping", "reflowBlockId": rid})
    # Marker-free miniature fixtures retain their same-coordinate mapping.
    if not any(block.get("contentHtml") for block in structured.values()):
        for rid in raw_blocks:
            if rid in structured and not raw_to_structured[rid]:
                raw_to_structured[rid].append(rid)
                structured_to_raw[rid].append(rid)
    return raw_to_structured, structured_to_raw, structured, issues


def answer_option_records(paper: dict, raw: dict, paragraphs: list[dict],
                          verified_matching: dict | None = None,
                          verified_cet: dict | None = None) -> tuple[list[dict], dict]:
    """Inventory each API option, retaining only uniquely proven raw anchors."""
    paper_id = paper["id"]
    structured = {block["id"]: block for block in paper["blocks"]}
    raw_groups = defaultdict(list)
    raw_items = defaultdict(list)
    for page_number, page in enumerate(raw["pages"], 1):
        for block_number, block in enumerate(page["blocks"], 1):
            if block.get("type") not in {"options", "choice_row"}:
                continue
            items = block.get("items", [])
            rid = f"{paper_id}:{block_id(page_number, block_number)}"
            group_key = tuple((str(item.get("label", "")).upper(),
                               comparison_key(raw_text(item))) for item in items)
            raw_groups[(page_number, group_key)].append((rid, items))
            for index, item in enumerate(items):
                raw_items[(page_number, str(item.get("label", "")).upper(),
                           comparison_key(raw_text(item)))].append((rid, index, raw_text(item)))

    passage_by_source = defaultdict(list)
    passage_by_raw = defaultdict(list)
    for paragraph in paragraphs:
        if paragraph["kind"] == "passage_option":
            for source_id in paragraph["sourceBlockIds"]:
                passage_by_source[source_id].append(paragraph)
            for raw_id in paragraph["reflowBlockIds"]:
                passage_by_raw[raw_id].append(paragraph)

    options = []
    raw_owners = {}
    pdf_owners = {}
    verified_matching = verified_matching or {}
    verified_cet = verified_cet or {}
    counts = Counter()
    for question in paper.get("questions", []):
        choices = question.get("options") or []
        if not choices:
            continue
        question_id = f"{paper_id}:{question['id']}"
        labels = [str(choice.get("label", "")).strip().rstrip(".)").upper()
                  for choice in choices]
        pages = {int(page) for page in question.get("sourcePages", []) if str(page).isdigit()}
        group_key = tuple((label, comparison_key(choice.get("text", "")))
                          for label, choice in zip(labels, choices))
        group_candidates = [candidate for page in pages
                            for candidate in raw_groups.get((page, group_key), [])]
        group_match = group_candidates[0] if len(group_candidates) == 1 else None
        context = question.get("context") or {}
        bank_sources = {item.get("id"): item.get("sourceBlocks", [])
                        for item in context.get("choiceBank", [])}
        for position, (choice, label) in enumerate(zip(choices, labels), 1):
            option_id = f"{question_id}:{label}" + (f":{position}" if labels.count(label) > 1 else "")
            source_text = choice.get("text", "")
            if not isinstance(source_text, str):
                source_text = ""
            input_text = source_text
            printed_label = str(choice.get("label", ""))
            if printed_label and re.match(rf"^\s*{re.escape(printed_label)}\s+", input_text):
                input_text = re.sub(rf"^\s*{re.escape(printed_label)}\s+", "", input_text, count=1)
            source_option_id = choice.get("sourceOptionId")
            source_sids = [sid for sid in bank_sources.get(source_option_id, []) if sid in structured]
            if not source_sids:
                source_sids = [sid for sid in question.get("sourceBlocks", [])
                               if sid in structured and comparison_key(source_text) and
                               comparison_key(source_text) in comparison_key(structured[sid].get("text", ""))]
            if not source_sids:
                source_sids = [sid for sid in question.get("sourceBlocks", [])
                               if sid in structured and structured[sid].get("role") == "choices"]
            source_ids = [f"{paper_id}:{sid}" for sid in source_sids]
            record = {"id": option_id, "kind": "answer_option", "paperId": paper_id,
                      "questionId": question_id, "optionId": option_id,
                      "sourceText": source_text, "sourceHash": sha256(source_text),
                      "sourceBlockIds": source_ids, "translationInput": None,
                      "translationInputHash": None, "translationEligible": False,
                      "translationZh": None, "protectedBlanks": []}
            if group_match and position <= len(group_match[1]):
                rid, items = group_match
                mapped = [(rid, position - 1, raw_text(items[position - 1]))]
            else:
                mapped = [candidate for page in pages
                          for candidate in raw_items.get((page, label, comparison_key(source_text)), [])]
            if len(mapped) == 1:
                rid, item_index, raw_source = mapped[0]
                record.update(reflowBlockId=rid, reflowOptionIndex=item_index,
                              reflowSourceText=raw_source)
                anchor = (rid, item_index)
                overlapping = passage_by_raw[rid]
                if overlapping:
                    exact = [paragraph for paragraph in overlapping
                             if paragraph["translationEligible"] and
                             same_printed_choice(paragraph, source_text, source_ids)]
                    if len(exact) == 1:
                        reason = "covered_by_paragraph"
                        record["coverageStatus"] = reason
                        record["translationRef"] = exact[0]["id"]
                    else:
                        reason = "overlaps_passage_paragraph"
                elif anchor in raw_owners:
                    owner_id, owner_text = raw_owners[anchor]
                    if owner_text == source_text:
                        reason = "covered_by_option"
                        record["coverageStatus"] = reason
                        record["translationRef"] = owner_id
                    else:
                        reason = "duplicate_raw_option_anchor"
                elif source_text != raw_source and comparison_key(source_text) != comparison_key(raw_source):
                    reason = "structured_raw_option_text_mismatch"
                elif not re.search(r"[A-Za-z]", input_text):
                    reason = "no_english_option_text"
                elif "\ufffd" in input_text:
                    reason = "source_unreadable"
                elif not input_text.strip():
                    reason = "empty_option_text"
                else:
                    reason = ("translate_verified_spacing" if source_text != raw_source
                              else "translate")
                    raw_owners[anchor] = (option_id, source_text)
                    record["translationEligible"] = True
                    record["translationInput"] = (raw_source if source_text != raw_source
                                                  else input_text)
                    record["translationInputHash"] = sha256(record["translationInput"])
                    record["protectedBlanks"] = protected_blanks(record["translationInput"])
            elif len(mapped) > 1:
                reason = "ambiguous_raw_option_anchor"
            else:
                reason = "missing_raw_option_anchor"
                # The PDF-backed split A choice is represented by an exact
                # source paragraph, and must be reused rather than requested.
                cet_anchor = verified_cet.get(option_id)
                if cet_anchor and cet_anchor.anchor_kind != "answer_option":
                    raise ValueError(f"{option_id}: unexpected CET option anchor")
                # Long matching choices are already covered by their own
                # source-traceable passage paragraph. Keep an explicit alias
                # for practice without sending the same prose to Google twice.
                candidates = {paragraph["id"]: paragraph for source_id in source_ids
                              for paragraph in passage_by_source[source_id]}
                candidates.update({paragraph["id"]: paragraph for paragraph in paragraphs
                                   if (paper_id, paragraph["id"]) in PDF_VERIFIED_SINGLE_OPTION_PARAGRAPH
                                   and (paragraph["source"]["pdfSha256"], paragraph["sourceHash"])
                                   == PDF_VERIFIED_SINGLE_OPTION_PARAGRAPH[(paper_id, paragraph["id"])]
                                   and set(paragraph["sourceBlockIds"]) & set(source_ids)})
                exact = [paragraph for paragraph in candidates.values()
                         if paragraph["translationEligible"] and
                         same_printed_choice(paragraph, source_text, source_ids)]
                if len(exact) == 1:
                    reason = "covered_by_paragraph"
                    record["coverageStatus"] = reason
                    record["translationRef"] = exact[0]["id"]
                verified = verified_matching.get(option_id)
                if verified and verified.anchor_kind == "figure_bank":
                    if verified.source_text != source_text:
                        raise ValueError(f"{option_id}: PDF-verified option text changed")
                    record["sourceBlockIds"] = []  # The table is a raw figure, absent from semantic blocks.
                    record["reflowBlockIds"] = [f"{paper_id}:{bid}" for bid in verified.reflow_block_ids]
                    record["pdfVerifiedSource"] = {
                        "sourcePdfSha256": verified.source_pdf_sha256,
                        "pdfPage": verified.source_pdf_page,
                        "anchorKind": verified.anchor_kind,
                        "reflowBlockIds": record["reflowBlockIds"],
                        "sourceOptionId": verified.source_option_id,
                    }
                    owner = pdf_owners.get(verified.source_option_id)
                    if owner:
                        reason = "covered_by_option"
                        record["coverageStatus"] = reason
                        record["translationRef"] = owner
                    else:
                        reason = "translate_pdf_verified"
                        pdf_owners[verified.source_option_id] = option_id
                        record["translationEligible"] = True
                        record["translationInput"] = source_text
                        record["translationInputHash"] = sha256(source_text)
                        record["protectedBlanks"] = protected_blanks(source_text)
            record["eligibilityReason"] = reason
            counts["eligible" if record["translationEligible"] else "ineligible"] += 1
            counts[f"reason:{reason}"] += 1
            options.append(record)
    bank_seen = set()
    for question in paper.get("questions", []):
        context = question.get("context") or {}
        if context.get("kind") != "word_bank_cloze":
            continue
        question_id = f"{paper_id}:{question['id']}"
        for bank_item in context.get("wordBank", []):
            option_id = bank_item.get("id")
            if (not isinstance(option_id, str) or not option_id.startswith(paper_id + ":") or
                    ":word-bank:" not in option_id):
                raise ValueError(f"invalid word-bank option ID: {paper_id}")
            if option_id in bank_seen:
                continue
            bank_seen.add(option_id)
            source_text = bank_item.get("text", "")
            if not isinstance(source_text, str):
                source_text = ""
            source_sid = bank_item.get("sourceBlockId")
            source_ids = ([f"{paper_id}:{source_sid}"] if source_sid in structured else [])
            record = {"id": option_id, "kind": "word_bank_option", "paperId": paper_id,
                      "questionId": question_id, "optionId": option_id,
                      "sourceText": source_text, "sourceHash": sha256(source_text),
                      "sourceBlockIds": source_ids, "translationInput": None,
                      "translationInputHash": None, "translationEligible": False,
                      "translationZh": None, "protectedBlanks": []}
            label = str(bank_item.get("label", "")).strip().rstrip(".)").upper()
            page = int(source_sid.split("-")[1]) if source_ids else None
            mapped = raw_items.get((page, label, comparison_key(source_text)), []) if page else []
            if len(mapped) == 1:
                rid, item_index, raw_source = mapped[0]
                record.update(reflowBlockId=rid, reflowOptionIndex=item_index,
                              reflowSourceText=raw_source)
                anchor = (rid, item_index)
                if anchor in raw_owners:
                    owner_id, owner_text = raw_owners[anchor]
                    if owner_text == source_text:
                        reason = "covered_by_option"
                        record["coverageStatus"] = reason
                        record["translationRef"] = owner_id
                    else:
                        reason = "duplicate_raw_option_anchor"
                elif source_text != raw_source and comparison_key(source_text) != comparison_key(raw_source):
                    reason = "structured_raw_option_text_mismatch"
                elif "\ufffd" in source_text:
                    reason = "source_unreadable"
                elif not re.search(r"[A-Za-z]", source_text):
                    reason = "no_english_option_text"
                else:
                    reason = ("translate_verified_spacing" if source_text != raw_source
                              else "translate")
                    raw_owners[anchor] = (option_id, source_text)
                    record["translationEligible"] = True
                    record["translationInput"] = raw_source
                    record["translationInputHash"] = sha256(raw_source)
                    record["protectedBlanks"] = protected_blanks(raw_source)
            elif len(mapped) > 1:
                reason = "ambiguous_raw_option_anchor"
            else:
                reason = "missing_raw_option_anchor"
                verified = verified_cet.get(option_id)
                if verified:
                    if verified.anchor_kind != "word_bank_option" or verified.source_text != source_text:
                        raise ValueError(f"{option_id}: PDF-verified CET word changed")
                    record["sourceBlockIds"] = [f"{paper_id}:{sid}"
                                                for sid in verified.structured_source_block_ids]
                    record["reflowBlockIds"] = [f"{paper_id}:{verified.reflow_block_id}"]
                    record["pdfVerifiedSource"] = {
                        "sourcePdfSha256": verified.source_pdf_sha256,
                        "pdfPage": verified.source_pdf_page,
                        "anchorKind": verified.anchor_kind,
                        "reflowBlockIds": record["reflowBlockIds"],
                        "reflowOptionIndex": verified.reflow_option_index,
                        "sourceOptionId": option_id,
                    }
                    reason = "translate_pdf_verified"
                    record["translationEligible"] = True
                    record["translationInput"] = source_text
                    record["translationInputHash"] = sha256(source_text)
                    record["protectedBlanks"] = protected_blanks(source_text)
            record["eligibilityReason"] = reason
            counts["eligible" if record["translationEligible"] else "ineligible"] += 1
            counts[f"reason:{reason}"] += 1
            options.append(record)
    ids = [record["id"] for record in options]
    if len(ids) != len(set(ids)):
        raise ValueError(f"duplicate option translation ID: {paper_id}")
    return options, dict(sorted(counts.items()))


def cloze_groups(paper: dict, raw: dict, structured_to_raw: dict | None = None) -> tuple[dict, list]:
    """Map each printed passage block to verified replacement runs.

    A whole passage is ineligible if even one expected answer, printed marker,
    or source word is uncertain.  This keeps partial passages out of the queue.
    """
    by_block = {}
    issues = []
    grouped = defaultdict(list)
    for question in paper.get("questions", []):
        context = question.get("context") or {}
        if context.get("kind") not in {"passage", "word_bank_cloze"}:
            continue
        source_ids = tuple(rid for sid in (context.get("passageSourceBlocks") or ())
                           for rid in (structured_to_raw.get(sid, [])
                                       if structured_to_raw is not None else [sid]))
        if source_ids:
            grouped[source_ids].append(question)
    raw_by_id = {block_id(pn, bi): block
                 for pn, page in enumerate(raw["pages"], 1)
                 for bi, block in enumerate(page["blocks"], 1)}
    for source_ids, questions in grouped.items():
        context = questions[0]["context"]
        numbers = {str(q.get("number")): q for q in questions}
        found = defaultdict(list)
        invalid = []
        for bid in source_ids:
            block = raw_by_id.get(bid)
            if not block:
                invalid.append(f"missing_source_block:{bid}")
                continue
            if block.get("type") != "paragraph":
                invalid.append(f"nonparagraph_source_block:{bid}")
            if any(run.get("glyph") for run in block.get("runs", [])):
                invalid.append(f"image_glyph:{bid}")
            for index, run in enumerate(block.get("runs", [])):
                value = run.get("text", "")
                if run.get("flags", [False, False])[1]:
                    match = BLANK_RUN.fullmatch(value)
                    if match:
                        found[match.group(2)].append((bid, index, match.start(2), match.end(2)))
                    else:
                        invalid.append(f"unreadable_blank_run:{bid}:{index}")
                elif context.get("kind") == "word_bank_cloze":
                    # Some CET PDFs print markers as plain text ("__26__" or
                    # "(26)____") rather than styled blank runs.  Accept only
                    # a number that occurs exactly once across the passage.
                    for match in re.finditer(r"(?<!\d)(2[6-9]|3\d|4[0-5])(?!\d)", value):
                        if match.group(1) not in numbers:
                            continue
                        start, end = match.span(1)
                        left = re.search(r"(?:_{2,}\s*|\(\s*)$", value[:start])
                        right = re.match(r"(?:\s*_{2,}|\s*\)\s*_{1,})", value[end:])
                        if not (left and right):
                            # A bare number can be a date, count, or citation;
                            # it is never proof of a printed cloze blank.
                            continue
                        start = left.start()
                        end += right.end()
                        found[match.group(1)].append((bid, index, start, end))
        if context.get("kind") == "word_bank_cloze":
            if context.get("wordBankStatus") != "complete":
                invalid.append("incomplete_word_bank")
            printed = {str(number) for number in context.get("printedBlankNumbers", [])}
            if printed and printed != set(numbers):
                invalid.append("question_printed_number_mismatch")
            for number in context.get("sourceNumberUnverifiedNumbers", []):
                invalid.append(f"unverified_source_number:{number}")
            ordered = [(str(number), flat_position)
                       for number, occurrences in found.items() for flat_position in occurrences]
            ordered.sort(key=lambda item: (int(item[1][0].split('-')[1]),
                                           int(item[1][0].split('-')[2]), item[1][1], item[1][2]))
            if [number for number, _ in ordered] != sorted(numbers, key=int):
                invalid.append("printed_blank_sequence_mismatch")
        replacements = {}
        for number, question in numbers.items():
            positions = found.get(number, [])
            if len(positions) != 1:
                invalid.append(f"blank_marker_count:{number}:{len(positions)}")
                continue
            choice = selected_answer(question, context)
            if choice is None:
                invalid.append(f"unresolved_answer:{number}")
                continue
            replacements[positions[0]] = {"number": number, "word": choice["text"].strip(),
                                          "questionId": question["id"],
                                          "optionLabel": choice["label"],
                                          "optionSourceBlockIds": ([choice["sourceBlockId"]]
                                                                   if choice.get("sourceBlockId") else
                                                                   question.get("sourceBlocks", [])),
                                          "answerSource": (question.get("answer") or {}).get("externalSource")}
        for number in found.keys() - numbers.keys():
            invalid.append(f"unlinked_printed_blank:{number}")
        if len(set(source_ids)) != len(source_ids):
            invalid.append("duplicate_passage_source_block")
        # An image-only line between the first and last text blocks may carry
        # missing passage words.  Never claim that such a passage is complete.
        flat = [block_id(pn, bi) for pn, page in enumerate(raw["pages"], 1)
                for bi, _ in enumerate(page["blocks"], 1)]
        positions = [flat.index(bid) for bid in source_ids if bid in flat]
        if positions:
            source_lines = [flat[i] for i in range(min(positions), max(positions) + 1)
                            if raw_by_id[flat[i]].get("type") == "source_line"]
            invalid.extend(f"image_source_line:{bid}" for bid in source_lines)
        info = {"kind": "cloze", "sourceIds": list(source_ids),
                "replacements": replacements, "unresolved": sorted(set(invalid)),
                "eligible": not invalid}
        for bid in source_ids:
            if bid in by_block:
                issues.append({"code": "duplicate_cloze_source_block", "blockId": bid})
            by_block[bid] = info
        if invalid:
            issues.append({"code": "incomplete_cloze", "sourceBlockIds": list(source_ids),
                           "reasons": sorted(set(invalid))})
    return by_block, issues


def restored_text(block: dict, bid: str, info: dict) -> str:
    parts = []
    for index, run in enumerate(block.get("runs", [])):
        value = run.get("text", "")
        spans = [(start, end, replacement)
                 for (source_bid, run_index, start, end), replacement in info["replacements"].items()
                 if source_bid == bid and run_index == index]
        for start, end, replacement in sorted(spans, reverse=True):
            value = value[:start] + replacement["word"] + value[end:]
        parts.append(value)
    return "".join(parts)


def build_paper(paper: dict, raw: dict, source_json: str, pdf_hash: str,
                dictation_answers: dict | None = None, *,
                allow_missing_pdf: bool = False) -> dict:
    paper_id = paper["id"]
    raw_to_structured, structured_to_raw, structured, issues = source_mapping(paper, raw)
    verified_matching = verified_matching_option_anchors(
        paper, raw, pdf_hash, allow_missing_pdf=allow_missing_pdf)
    verified_cet = verified_cet_missing_option_anchors(
        paper, raw, pdf_hash, allow_missing_pdf=allow_missing_pdf)
    verified_passage_joins = {
        anchor.reflow_block_ids[-1]: anchor
        for anchor in verified_matching.values()
        if anchor.anchor_kind == "passage_option" and len(anchor.reflow_block_ids) == 2
    }
    cloze, cloze_issues = cloze_groups(paper, raw, structured_to_raw)
    issues.extend(cloze_issues)
    dictation = listening_dictation_blocks(raw) if paper["category"] in {"cet4", "cet6"} else {}
    verified_dictation = verified_dictation_words(dictation, dictation_answers)
    paragraphs = []
    inventory = []
    reading = False
    translation_section = False
    unparsed_cloze = False
    cet_cloze_region = False
    kaoyan_cloze_region = False
    passage_option_active = False
    section_mode = "front_matter"
    other_block_types = Counter()
    previous = None
    raw_ids = set()
    bilingual_joins = verified_bilingual_completion_joins(
        paper_id, pdf_hash, raw, allow_missing_pdf=allow_missing_pdf)
    bilingual_continuations = {join.to_block_id: join for join in bilingual_joins.values()}
    cross_page_from = {(row["paperId"], row["pdfSha256"], row["fromBlockId"]): row
                       for row in _verified_cross_page["entries"]}
    for pn, page in enumerate(raw["pages"], 1):
        for bi, block in enumerate(page["blocks"], 1):
            bid = block_id(pn, bi)
            raw_ids.add(bid)
            sids = raw_to_structured.get(bid, [])
            if bid in bilingual_continuations:
                join = bilingual_continuations[bid]
                expected_id = f"{paper_id}:p:{join.from_block_id}"
                if not previous or previous["id"] != expected_id:
                    raise ValueError(f"{paper_id}: verified bilingual continuation lost its prompt")
                inventory.append({"sourceBlockId": f"{paper_id}:{bid}",
                                  "classification": "included",
                                  "reason": "pdf_verified_bilingual_continuation",
                                  "paragraphId": expected_id})
                continue
            bilingual_join = bilingual_joins.get(bid)
            verified_passage_join = verified_passage_joins.get(bid)
            if bilingual_join:
                sids = list(dict.fromkeys(sids + raw_to_structured.get(bilingual_join.to_block_id, [])))
            sb = structured.get(sids[0]) if (len(sids) == 1 or bilingual_join) and sids else None
            option_starter = bool(
                block.get("type") == "options" and sb and
                sb.get("role") == "choices" and not sb.get("questionId") and
                sb.get("sourceSection") != "answers" and
                len(block.get("items", [])) == 1 and
                re.fullmatch(r"[A-P]", block["items"][0].get("label", "")) and
                is_prose(raw_text(block["items"][0]))
            )
            misparsed_direction_option = bool(
                option_starter and re.match(r"^\.\s*You should decide on the best choice\b",
                                            raw_text(block["items"][0]), re.I)
            )
            text = (bilingual_join.joined_text if bilingual_join else
                    passage_option_text(block) if option_starter else raw_text(block))
            cross_page_join = PDF_VERIFIED_CROSS_PAGE_JOINS.get((paper_id, pdf_hash, bid))
            if cross_page_join:
                assert sha256(text) == cross_page_join["toBlockHash"], (paper_id, bid)
            mixed_direction = mixed_instruction_prefix(text)
            if not sb and block.get("type") in {"paragraph", "heading", "instruction", "question"}:
                issues.append({"code": "missing_structured_block", "blockId": bid})
            source_mismatch = bool(not bilingual_join and sb and len(structured_to_raw[sids[0]]) == 1 and
                                   (option_starter or block.get("type") in
                                             {"paragraph", "heading", "instruction", "question"})
                                   and "\ufffd" not in text
                                   and comparison_key(text) != comparison_key(sb.get("text", "")))
            if source_mismatch:
                issues.append({"code": "source_block_mismatch", "blockId": bid})
            # A major non-reading section ends the prose region.  Part B/C in
            # Kaoyan remain within Section II and are not major stops.
            if (sb and sb.get("role") == "section") or block.get("type") == "heading":
                label = text.lower().strip()
                if MAJOR_SECTION.match(label):
                    for token, mode in (("reading", "reading"), ("listening", "listening"),
                                        ("writing", "writing"), ("cloze", "cloze"),
                                        ("language usage", "language_usage"),
                                        ("translation", "translation"), ("answer", "answers")):
                        if token in label:
                            section_mode = mode
                            break
                if paper["category"] == "tem4" and re.match(r"^part\s+iv\s+cloze\b", label):
                    unparsed_cloze = True
                elif paper["category"] == "tem4" and MAJOR_SECTION.match(label) and label.startswith("part"):
                    unparsed_cloze = False
                if "reading comprehension" in label:
                    reading = True
                    translation_section = False
                    kaoyan_cloze_region = False
                elif paper["category"] == "kaoyan" and "use of english" in label:
                    kaoyan_cloze_region = True
                elif paper["category"] == "kaoyan" and "translation" in label and "section" in label:
                    reading = True
                    translation_section = True
                elif (MAJOR_SECTION.match(label) and
                      ((paper["category"] == "kaoyan" and "writing" in label)
                       or (paper["category"] != "kaoyan" and
                           not re.match(r"^(?:part|section)\s+[abc]\b", label)
                           and ("translation" in label or "writing" in label
                                or "listening" in label or "language usage" in label
                                or "cloze" in label or "answer" in label)))):
                    reading = False
                    translation_section = False
                if paper["category"] in {"cet4", "cet6"} and reading and (sb or {}).get("role") == "section":
                    if re.fullmatch(r"section\s*a", label):
                        cet_cloze_region = True
                    elif re.fullmatch(r"section\s*[bc]", label) or "translation" in label:
                        cet_cloze_region = False
            if block.get("type") not in {"paragraph", "heading", "instruction", "question"} and not option_starter:
                other_block_types[block.get("type", "unknown")] += 1
                if block.get("type") in {"question", "options", "choice_row"}:
                    passage_option_active = False
                continue
            if not text.strip():
                inventory.append({"sourceBlockId": f"{paper_id}:{bid}",
                                  "classification": "excluded", "reason": "empty"})
                continue
            info = cloze.get(bid)
            role = (sb or {}).get("role")
            answer_side = (sb or {}).get("sourceSection") == "answers"
            heading_continuation = (block.get("type") == "heading" and previous and
                                    previous["kind"] == "reading" and reading and
                                    role == "heading" and text[:1].islower() and
                                    not re.search(r"[.!?。！？][\"'’”)]?\s*$", previous["sourceText"]))
            damaged_cloze = bid in PDF_VERIFIED_DAMAGED_CLOZE_BLOCKS.get(
                (paper_id, pdf_hash), frozenset())
            unfilled_cloze_hash = PDF_VERIFIED_UNFILLED_CLOZE.get((paper_id, pdf_hash, bid))
            if unfilled_cloze_hash is not None and sha256(text) != unfilled_cloze_hash:
                raise ValueError(f"{paper_id}:{bid}: unfilled cloze source changed")
            unfilled_cloze = unfilled_cloze_hash is not None
            if (bid == "b-1-3" and pdf_hash == PDF_VERIFIED_TEM_COVER.get(paper_id) and
                    text != ("TIME LIMIT: 130 MIN" if paper["category"] == "tem4"
                             else "TIME LIMIT: 150 MIN")):
                raise ValueError(f"{paper_id}:{bid}: cover metadata source changed")
            tem_cover = (bid == "b-1-3" and
                         pdf_hash == PDF_VERIFIED_TEM_COVER.get(paper_id) and
                         text == ("TIME LIMIT: 130 MIN" if paper["category"] == "tem4"
                                  else "TIME LIMIT: 150 MIN"))
            pdf_verified_short_option = (
                paper_id == "cet4:2020-07-01" and
                pdf_hash == "5529c8dc34ac9fafdbed192a5b41c79f08ca157a4899e47dcb86936bd5316517" and
                bid == "b-4-7" and
                text == ("A) Why do so many Americans eat tons of processed food, the stuff"
                         " that is correctly called junk (垃圾) and should really carry warning labels?"))
            pdf_verified_page_furniture = (
                paper_id == "cet6:2020-07-01" and
                pdf_hash == "be125ae4035ebd1bea079cf0248d391c023c533433dccf4427da930df743e612" and
                bid == "b-13-2" and text == "I I I I I I I I I I I I I I I I")
            split_option_guard = PDF_VERIFIED_SINGLE_OPTION_PARAGRAPH.get(
                (paper_id, f"{paper_id}:p:{bid}"))
            if split_option_guard and pdf_hash == split_option_guard[0] and sha256(text) != split_option_guard[1]:
                raise ValueError(f"{paper_id}:{bid}: verified split option source changed")
            verified_split_option = split_option_guard == (pdf_hash, sha256(text))
            if tem_cover:
                classification, reason, kind = "excluded", "pdf_verified_cover_metadata", None
            elif unfilled_cloze:
                classification, reason, kind = "ineligible", "pdf_verified_unfilled_cloze", "cloze"
            elif bilingual_join:
                classification, reason, kind = "included", "pdf_verified_bilingual_prompt", "question_prompt"
            elif verified_split_option:
                classification, reason, kind = "included", "pdf_verified_split_option", "question_prompt"
            elif verified_passage_join:
                classification, reason, kind = "included", "pdf_verified_option_continuation", "passage_option"
            elif pdf_verified_page_furniture:
                classification, reason, kind = "excluded", "pdf_verified_page_furniture", None
            elif damaged_cloze:
                classification, reason, kind = "ineligible", "pdf_verified_damaged_cloze", "cloze"
            elif info and not is_english_body(text):
                has_fill = any(source_bid == bid for source_bid, _, _, _ in info["replacements"])
                classification = "ineligible" if has_fill else "excluded"
                reason, kind = "cloze_non_prose", "cloze" if has_fill else None
            elif info:
                eligible = info["eligible"] and sb is not None and not source_mismatch
                classification, reason, kind = ("included" if eligible else "ineligible",
                                                "cloze" if eligible else "unresolved_cloze_or_source_mismatch", "cloze")
            elif heading_continuation:
                classification, reason, kind = "included", "heading_continuation", "reading"
            elif (unparsed_cloze and paper["category"] == "tem4" and
                  block.get("type") == "paragraph" and role == "content" and
                  is_prose(text)):
                classification, reason, kind = "ineligible", "unparsed_tem4_cloze", "cloze"
            elif ((cet_cloze_region or kaoyan_cloze_region) and
                  block.get("type") == "paragraph" and role == "content" and
                  is_prose(text)):
                classification, reason, kind = "ineligible", "unparsed_cloze_region", "cloze"
            elif misparsed_direction_option:
                classification, reason, kind = "included", "recovered_direction_option", "instruction"
            elif option_starter:
                classification, reason, kind = "included", "reading_choice_paragraph", "passage_option"
            elif (passage_option_active and previous and previous["kind"] == "passage_option" and
                  block.get("type") == "paragraph" and role == "content" and not answer_side and
                  is_english_body(text) and
                  not re.match(r"^[A-P][).]", text.lstrip())):
                classification, reason, kind = "included", "reading_choice_continuation", "passage_option"
            elif answer_side:
                classification, reason, kind = "excluded", "answer_side", None
            elif role == "section" or (block.get("type") == "heading" and
                                       (MAJOR_SECTION.match(text.strip()) or
                                        text.strip().lower() in {"directions:", "directions"})):
                classification, reason, kind = "excluded", "section_label", None
            elif mixed_direction:
                classification, reason, kind = "included", "mixed_language_instruction", "instruction"
            elif not is_english_body(text):
                classification, reason, kind = "excluded", "non_english_or_fragment", None
            elif (block.get("type") == "paragraph" and
                  re.match(r"^[A-P][).]", text.lstrip()) and
                  role == "content" and
                  (reading or passage_option_active or pdf_verified_short_option or
                   len(re.findall(r"[A-Za-z]+", text)) >= 30)):
                classification, reason, kind = "included", "reading_choice_paragraph", "passage_option"
            elif re.match(r"^[A-D][).]\s+[A-Za-z]", text):
                classification, reason, kind = "excluded", "ordinary_choice", None
            elif block.get("type") == "question":
                classification, reason, kind = "included", "question_prompt", "question_prompt"
            elif block.get("type") == "instruction" or INSTRUCTION.match(text.strip()):
                classification, reason, kind = "included", "instruction", "instruction"
            elif block.get("type") == "heading":
                classification, reason, kind = "included", "heading_prose", "heading_prose"
            elif translation_section:
                classification, reason, kind = "included", "translation_passage", "translation_passage"
            elif reading:
                classification, reason, kind = "included", "reading_prose", "reading"
            else:
                kind = {"writing": "writing_prompt", "listening": "listening_text",
                        "language_usage": "language_prompt", "translation": "translation_prompt"}.get(
                            section_mode, "general_prose")
                classification, reason = "included", f"section_{section_mode}"
            if (block.get("continues_previous_page") and previous and sids and
                    any(f"{paper_id}:{sid}" in previous["sourceBlockIds"] for sid in sids)):
                # The renderer already joined this raw continuation into one
                # structured paragraph. Keep its semantic kind across pages.
                kind = previous["kind"]
                classification = "included" if previous["translationEligible"] else "ineligible"
                reason = "cross_page_continuation"
            if cross_page_join:
                assert previous is not None and previous["reflowBlockIds"][-1] == (
                    f"{paper_id}:{cross_page_join['fromBlockId']}")
                from_id = cross_page_join["fromBlockId"]
                _, from_page, from_index = from_id.split("-")
                from_block = raw["pages"][int(from_page) - 1]["blocks"][int(from_index) - 1]
                assert sha256(raw_text(from_block)) == cross_page_join["fromBlockHash"]
                assert previous["sourceText"].endswith(cross_page_join["footer"])
                kind = previous["kind"]
                classification = ("ineligible" if cross_page_join["unverifiedCloze"] or
                                  not previous["translationEligible"] else "included")
                reason = "pdf_verified_cross_page_continuation"
            if source_mismatch and classification == "included":
                classification, reason = "ineligible", "source_block_mismatch"
            inventory_row = {"sourceBlockId": f"{paper_id}:{bid}",
                             "classification": classification, "reason": reason}
            inventory.append(inventory_row)
            if classification == "excluded":
                bridge = (cross_page_from.get((paper_id, pdf_hash,
                                               previous["reflowBlockIds"][-1].rsplit(":", 1)[-1]))
                          if previous else None)
                expected_header = f"b-{pn}-1"
                if not (bridge and bridge.get("interveningHeader") == text and
                        bid == expected_header and
                        int(bridge["toBlockId"].split("-")[1]) == pn):
                    previous = None
                continue
            join = bool(block.get("continues_previous_page") or heading_continuation or
                        reason in {"reading_choice_continuation",
                                   "pdf_verified_cross_page_continuation",
                                   "pdf_verified_option_continuation"})
            if join and (previous is None or previous["kind"] != kind):
                issues.append({"code": "malformed_paragraph_join", "blockId": bid})
                classification = inventory_row["classification"] = "ineligible"
                inventory_row["reason"] = "malformed_paragraph_join"
                join = False
            direction_input = (re.sub(r"^\.\s*", "", raw_text(block["items"][0]))
                               if misparsed_direction_option else None)
            derived = (restored_text(block, bid, info)
                       if info and classification == "included" else
                       direction_input if direction_input and classification == "included" else
                       mixed_direction if mixed_direction and classification == "included" else text)
            restored_blanks = ([{"sourceBlockId": f"{paper_id}:{bid}", "runIndex": index,
                                 "runStart": start, "runEnd": end,
                                 **replacement}
                                for (source_bid, index, start, end), replacement in info["replacements"].items()
                                if source_bid == bid] if info and classification == "included" else [])
            if join:
                separator = (cross_page_join["separator"] if cross_page_join else
                             "" if previous["sourceText"].rstrip().endswith("-") else " ")
                if verified_passage_join:
                    if (previous["reflowBlockIds"][-1] !=
                            f"{paper_id}:{verified_passage_join.reflow_block_ids[0]}"):
                        raise ValueError(f"{paper_id}:{bid}: verified option predecessor changed")
                previous["sourceText"] += " " + text if cross_page_join else separator + text
                if (verified_passage_join and
                        comparison_key(previous["sourceText"]) !=
                        comparison_key(verified_passage_join.derived_passage_text)):
                    raise ValueError(f"{paper_id}:{bid}: verified passage join changed")
                if cross_page_join:
                    prior_input = previous["translationInput"] or ""
                    assert prior_input.endswith(cross_page_join["footer"])
                    prior_input = prior_input[:-len(cross_page_join["footer"])].rstrip()
                    previous["translationInput"] = (prior_input + separator + derived
                                                    if previous["translationEligible"] and
                                                    classification == "included" else None)
                    previous.setdefault("verifiedCrossPageFooters", []).append(
                        cross_page_join["footer"])
                    if cross_page_join["unverifiedCloze"]:
                        previous["unresolvedBlanks"].append("cross_page_cloze_answer_unverified")
                else:
                    previous["translationInput"] = ((previous["translationInput"] or "") + separator + derived
                                                    if previous["translationEligible"] and classification == "included"
                                                    else None)
                for sid in sids:
                    qualified = f"{paper_id}:{sid}"
                    if qualified not in previous["sourceBlockIds"]:
                        previous["sourceBlockIds"].append(qualified)
                        previous["source"]["blockIds"].append(sid)
                        previous["source"]["blockParagraphIndices"].append(0)
                previous["reflowBlockIds"].append(f"{paper_id}:{bid}")
                previous["source"]["reflowBlockIds"].append(bid)
                previous["restoredBlanks"].extend(restored_blanks)
                previous["protectedBlanks"].extend(protected_blanks(derived) if classification == "included" else [])
                if str(pn) not in previous["source"]["pages"]:
                    previous["source"]["pages"].append(str(pn))
                if classification != "included":
                    previous["translationEligible"] = False
                    previous["unresolvedBlanks"] = sorted(set(previous["unresolvedBlanks"] + info["unresolved"])) if info else previous["unresolvedBlanks"]
                inventory_row["paragraphId"] = previous["id"]
                passage_option_active = kind == "passage_option"
                continue
            entry = {
                "id": f"{paper_id}:p:{bid}", "paperId": paper_id, "kind": kind,
                "sourceText": text, "sourceHash": "",
                "sourceBlockIds": [f"{paper_id}:{sid}" for sid in sids],
                "reflowBlockIds": ([f"{paper_id}:{bid}", f"{paper_id}:{bilingual_join.to_block_id}"]
                                   if bilingual_join else [f"{paper_id}:{bid}"]),
                "paragraphIndex": 0, "translationInput": derived if classification == "included" else None,
                "translationInputHash": None, "translationEligible": classification == "included",
                "translationZh": None,
                "unresolvedBlanks": info["unresolved"] if info else [],
                "restoredBlanks": restored_blanks,
                "protectedBlanks": protected_blanks(derived) if classification == "included" else [],
                "source": {"blockIds": list(sids),
                           "reflowBlockIds": ([bid, bilingual_join.to_block_id]
                                              if bilingual_join else [bid]),
                           "blockParagraphIndices": [0] * len(sids),
                           "pages": [str(pn)], "sourceJson": source_json,
                           "pdfSha256": pdf_hash,
                           "originalHtml": paper.get("source", {}).get("original"),
                           "reflowHtml": paper.get("source", {}).get("reflow")},
            }
            if reason == "unparsed_tem4_cloze":
                entry["unresolvedBlanks"] = ["unparsed_tem4_cloze"]
            elif reason == "unparsed_cloze_region":
                entry["unresolvedBlanks"] = ["unparsed_cloze_region"]
            elif reason == "pdf_verified_unfilled_cloze":
                entry["unresolvedBlanks"] = ["numbered_cloze_answers_unverified"]
            if bilingual_join:
                entry["protectedCues"] = [bilingual_join.chinese_cue]
                entry["verifiedBilingualJoin"] = {
                    "sourceBlockIds": [f"{paper_id}:{source_id}"
                                       for source_id in bilingual_join.source_block_ids],
                    "pdfPage": bilingual_join.pdf_page,
                    "originalPdfSha256": bilingual_join.original_pdf_sha256,
                    "chineseCueSpan": list(bilingual_join.chinese_cue_span),
                }
            paragraphs.append(entry)
            inventory_row["paragraphId"] = entry["id"]
            previous = entry
            passage_option_active = kind == "passage_option"
    for bid, block in structured.items():
        if not structured_to_raw[bid] and block.get("role") in {"content", "heading", "question"}:
            html = block.get("contentHtml") or ""
            if "source-line" in html:
                other_block_types["structured_image_source_line"] += 1
            elif 'class="notice"' in html and not is_english_body(block.get("text", "")):
                other_block_types["structured_source_notice"] += 1
            else:
                issues.append({"code": "orphan_structured_block", "blockId": bid})
    raw_sequence = [(block_id(pn, bi), block)
                    for pn, page in enumerate(raw["pages"], 1)
                    for bi, block in enumerate(page["blocks"], 1)]
    raw_positions = {bid: index for index, (bid, _) in enumerate(raw_sequence)}
    raw_by_id = {bid: block for bid, block in raw_sequence}
    for entry in paragraphs:
        entry["sourceHash"] = sha256(entry["sourceText"])
        rendered = " ".join(structured[sid.rsplit(":", 1)[-1]].get("text", "")
                            for sid in entry["sourceBlockIds"])
        if not entry["sourceBlockIds"]:
            issues.append({"code": "missing_structured_paragraph", "paragraphId": entry["id"]})
            entry["translationEligible"] = False
        elif ("\ufffd" not in entry["sourceText"] and
              comparison_key(entry["sourceText"]) != comparison_key(rendered)):
            issues.append({"code": "source_render_mismatch", "paragraphId": entry["id"]})
            entry["translationEligible"] = False
        if "\ufffd" in entry["sourceText"]:
            issues.append({"code": "source_unreadable", "paragraphId": entry["id"],
                           "replacementCharacters": entry["sourceText"].count("\ufffd"),
                           "sourceRenderMismatch": (comparison_key(entry["sourceText"]) !=
                                                    comparison_key(rendered))})
            entry["translationEligible"] = False
            for row in inventory:
                if row.get("paragraphId") == entry["id"]:
                    row["classification"] = "ineligible"
                    row["reason"] = "source_unreadable"
        if len(entry["reflowBlockIds"]) > 1:
            positions = [raw_positions[rid.rsplit(":", 1)[-1]]
                         for rid in entry["reflowBlockIds"]]
            image_gaps = [rid for rid, block in raw_sequence[min(positions):max(positions) + 1]
                          if block.get("type") == "source_line"]
            if image_gaps:
                issues.append({"code": "unreadable_intervening_source_line",
                               "paragraphId": entry["id"], "reflowBlockIds": image_gaps})
                entry["translationEligible"] = False
                for row in inventory:
                    if row.get("paragraphId") == entry["id"]:
                        row["classification"] = "ineligible"
                        row["reason"] = "source_unreadable_image_gap"
        dictation_numbers = [number for qualified in entry["reflowBlockIds"]
                             for number in dictation.get(qualified.rsplit(":", 1)[-1], [])]
        if dictation_numbers:
            exact_markers = DICTATION_NUMBER.findall(entry["sourceText"]) == dictation_numbers
            if verified_dictation and exact_markers and entry["translationEligible"]:
                entry["translationInput"] = DICTATION_NUMBER.sub(
                    lambda match: verified_dictation[match.group(1)], entry["sourceText"])
                entry["protectedBlanks"] = protected_blanks(entry["translationInput"])
                entry["restoredBlanks"].extend(
                    {"number": number, "word": verified_dictation[number],
                     "answerSourceUrl": dictation_answers["sourceUrl"],
                     "answerSourcePage": dictation_answers["sourcePage"],
                     "passageMatchEvidence": dictation_answers["passageMatchEvidence"]}
                    for number in dictation_numbers)
            else:
                issues.append({"code": "unverified_listening_dictation", "paragraphId": entry["id"],
                               "blankNumbers": dictation_numbers})
                entry["translationEligible"] = False
                entry["unresolvedBlanks"] = sorted(set(entry["unresolvedBlanks"] +
                                                         [f"dictation_answer_unverified:{number}"
                                                          for number in dictation_numbers]))
                for row in inventory:
                    if row.get("paragraphId") == entry["id"]:
                        row["classification"] = "ineligible"
                        row["reason"] = "unverified_listening_dictation"
        if entry.get("verifiedCrossPageFooters"):
            issues.append({"code": "verified_cross_page_footer", "paragraphId": entry["id"],
                           "removedFromTranslationInput": entry["translationEligible"]})
        elif PAGE_FOOTER.search(entry["sourceText"]):
            source_blocks = []
            for qualified in entry["reflowBlockIds"]:
                bid = qualified.rsplit(":", 1)[-1]
                block = raw_by_id[bid]
                page_number = int(bid.split("-")[1])
                block_text = (passage_option_text(block)
                              if block.get("type") == "options" and len(block.get("items", [])) == 1
                              else raw_text(block))
                source_blocks.append((page_number, block_text))
            cleaned = strip_verified_page_footers(
                entry["translationInput"] or entry["sourceText"],
                source_blocks, len(raw["pages"]),
                PDF_VERIFIED_SHORT_PAGE_FOOTERS.get((paper_id, pdf_hash), frozenset()))
            if cleaned is None:
                issues.append({"code": "unverified_page_footer", "paragraphId": entry["id"]})
                entry["translationEligible"] = False
                for row in inventory:
                    if row.get("paragraphId") == entry["id"]:
                        row["classification"] = "ineligible"
                        row["reason"] = "unverified_page_footer"
            else:
                issues.append({"code": "verified_page_footer", "paragraphId": entry["id"],
                               "removedFromTranslationInput": entry["translationEligible"]})
                if entry["translationEligible"]:
                    entry["translationInput"] = cleaned
                    entry["protectedBlanks"] = protected_blanks(cleaned)
        if entry["translationEligible"]:
            without_notice = strip_verified_direction_notice(paper_id, pdf_hash, entry)
            if without_notice is not None:
                entry["translationInput"] = without_notice
                entry["protectedBlanks"] = protected_blanks(without_notice)
                issues.append({"code": "verified_direction_notice", "paragraphId": entry["id"],
                               "removedFromTranslationInput": True})
        if not entry["translationEligible"]:
            entry["translationInput"] = None
            entry["protectedBlanks"] = []
            entry["restoredBlanks"] = []
        if entry["translationEligible"]:
            if (entry["kind"] in {"question_prompt", "language_prompt"} and
                    entry["protectedBlanks"] and not entry.get("protectedCues")):
                entry["protectedCues"] = [match.group() for match in
                                          re.finditer(r"[(（][^()（）]*[)）]", entry["translationInput"])
                                          if re.search(r"[\u3400-\u9fff]", match.group())]
            single_printed = PDF_VERIFIED_SINGLE_PRINTED_BLANKS.get(
                (paper_id, pdf_hash, entry["id"], entry["sourceHash"]))
            if single_printed and all(token in entry["translationInput"] for token in single_printed):
                entry["protectedBlanks"].extend(single_printed)
            entry["translationInputHash"] = sha256(entry["translationInput"])
    ids = [entry["id"] for entry in paragraphs]
    if len(ids) != len(set(ids)):
        issues.append({"code": "duplicate_paragraph_id"})
    source_uses = Counter(source_id for entry in paragraphs for source_id in entry["reflowBlockIds"])
    for row in inventory:
        if row["classification"] != "excluded" and (
                not row.get("paragraphId") or source_uses[row["sourceBlockId"]] != 1):
            issues.append({"code": "paragraph_inventory_mismatch",
                           "sourceBlockId": row["sourceBlockId"]})
    counts = Counter(row["classification"] for row in inventory)
    reasons = Counter(row["reason"] for row in inventory)
    kinds = Counter(entry["kind"] for entry in paragraphs)
    options, option_counts = answer_option_records(paper, raw, paragraphs,
                                                   verified_matching, verified_cet)
    return {"schema": "english-paragraph-translations.v1", "paperId": paper_id,
            "category": paper["category"], "sourceJson": source_json,
            "sourcePdfSha256": pdf_hash, "paragraphs": paragraphs,
            "options": options, "optionReconciliation": option_counts,
            "sourceInventory": inventory, "reconciliation": dict(sorted(counts.items())),
            "reasonCounts": dict(sorted(reasons.items())),
            "kindCounts": dict(sorted(kinds.items())),
            "otherSourceBlockCounts": dict(sorted(other_block_types.items())),
            "issues": issues}


def preserve_translations(new: dict, old: dict | None) -> None:
    if not old:
        return
    prior = {entry.get("id"): entry for entry in old.get("paragraphs", [])}
    stale = list(old.get("staleTranslations", []))
    for entry in new["paragraphs"]:
        former = prior.pop(entry["id"], None)
        if not former or not former.get("translationZh"):
            continue
        if (former.get("sourceHash") == entry["sourceHash"] and
                former.get("translationInputHash") == entry["translationInputHash"] and
                entry["translationEligible"]):
            entry["translationZh"] = former["translationZh"]
            if former.get("translationMeta"):
                entry["translationMeta"] = former["translationMeta"]
        else:
            stale.append(former)
            new["issues"].append({"code": "stale_translation", "paragraphId": entry["id"]})
    stale.extend(former for former in prior.values() if former.get("translationZh"))
    if stale:
        new["staleTranslations"] = stale
    prior_options = {entry.get("id"): entry for entry in old.get("options", [])}
    stale_options = list(old.get("staleOptionTranslations", []))
    for entry in new["options"]:
        former = prior_options.pop(entry["id"], None)
        if not former or not former.get("translationZh"):
            continue
        if (entry["translationEligible"] and former.get("sourceHash") == entry["sourceHash"] and
                former.get("translationInputHash") == entry["translationInputHash"]):
            entry["translationZh"] = former["translationZh"]
            if former.get("translationMeta"):
                entry["translationMeta"] = former["translationMeta"]
        else:
            stale_options.append(former)
    stale_options.extend(former for former in prior_options.values() if former.get("translationZh"))
    if stale_options:
        new["staleOptionTranslations"] = stale_options


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def build_all(output: Path = STRUCTURED, check: bool = False,
              verified_dictation_path: Path | None = None) -> dict:
    manifest = json.loads((REFLOW / "manifest.json").read_text(encoding="utf-8"))
    verified_by_paper = {}
    if verified_dictation_path is not None:
        verified_file = json.loads(verified_dictation_path.read_text(encoding="utf-8"))
        if verified_file.get("schema") != "verified-listening-dictation.v1" or not isinstance(
                verified_file.get("papers"), dict):
            raise ValueError("invalid verified listening dictation file")
        verified_by_paper = verified_file["papers"]
    papers = []
    seen = set()
    global_counts = Counter()
    global_reasons = Counter()
    global_kinds = Counter()
    global_other = Counter()
    global_options = Counter()
    all_issues = []
    for source in manifest["papers"]:
        category = source["category"]
        if category not in CATEGORIES:
            continue
        stem = Path(source["file"]).stem
        paper_id = f"{category}:{stem}"
        if paper_id in seen:
            raise ValueError(f"duplicate canonical paper: {paper_id}")
        seen.add(paper_id)
        source_path = REFLOW / category / "papers" / f"{stem}.json"
        structured_path = STRUCTURED / "papers" / category / f"{stem}.json"
        paper = json.loads(structured_path.read_text(encoding="utf-8"))
        if paper["id"] != paper_id:
            raise ValueError(f"canonical paper mismatch: {structured_path}")
        raw = json.loads(source_path.read_text(encoding="utf-8"))
        source_json = str(source_path.relative_to(ROOT))
        result = build_paper(paper, raw, source_json, source["source_pdf_sha256"],
                             verified_by_paper.get(paper_id))
        path = output / "translations" / category / f"{stem}.json"
        old = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
        preserve_translations(result, old)
        if not check:
            write_json(path, result)
        papers.append({"paperId": paper_id, "path": str(path.relative_to(output)),
                       "paragraphs": len(result["paragraphs"]),
                       "options": len(result["options"]),
                       "optionReconciliation": result["optionReconciliation"],
                       "reconciliation": result["reconciliation"],
                       "issues": len(result["issues"])})
        global_counts.update(result["reconciliation"])
        global_reasons.update(result["reasonCounts"])
        global_kinds.update(result["kindCounts"])
        global_other.update(result["otherSourceBlockCounts"])
        global_options.update(result["optionReconciliation"])
        all_issues.extend({"paperId": paper_id, **issue} for issue in result["issues"])
    summary = {"schema": "english-paragraph-manifest.v1", "source": str((REFLOW / "manifest.json").relative_to(ROOT)),
               "papers": papers, "reconciliation": dict(sorted(global_counts.items())),
               "reasonCounts": dict(sorted(global_reasons.items())),
               "kindCounts": dict(sorted(global_kinds.items())),
               "optionReconciliation": dict(sorted(global_options.items())),
               "otherSourceBlockCounts": dict(sorted(global_other.items())),
               "issueCounts": dict(sorted(Counter(issue["code"] for issue in all_issues).items())),
               "issues": all_issues}
    summary["staleTranslationCount"] = summary["issueCounts"].get("stale_translation", 0)
    summary["structuralIssueCount"] = sum(
        count for code, count in summary["issueCounts"].items()
        if code not in {"incomplete_cloze", "source_unreadable",
                        "unreadable_intervening_source_line",
                        "unverified_listening_dictation", "verified_page_footer",
                        "verified_direction_notice", "verified_cross_page_footer",
                        "stale_translation"})
    if not check:
        write_json(output / "english-paragraphs.json", summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="audit source without writing sidecars")
    parser.add_argument("--verified-dictation", type=Path,
                        help="private, source-cited complete 26–35 listening answer groups")
    args = parser.parse_args()
    summary = build_all(check=args.check, verified_dictation_path=args.verified_dictation)
    print(json.dumps({"papers": len(summary["papers"]),
                      "reconciliation": summary["reconciliation"],
                      "reasonCounts": summary["reasonCounts"],
                      "kindCounts": summary["kindCounts"],
                      "optionReconciliation": summary["optionReconciliation"],
                      "issueCounts": summary["issueCounts"],
                      "staleTranslationCount": summary["staleTranslationCount"],
                      "structuralIssueCount": summary["structuralIssueCount"]}, ensure_ascii=False))
    if args.check and summary["structuralIssueCount"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
