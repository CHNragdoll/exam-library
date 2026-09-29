#!/usr/bin/env python3
"""Validate private, source-cited CET answer evidence against local source files.

This checks provenance and local alignment only. It does not import answers into
the structured paper, translation sidecars, or database.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_EVIDENCE = ROOT / ".local/answer-keys/verified-english-answer-evidence.json"
PAPERS = ROOT / "data/sources/exam-library/structured/papers"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def validate_entry(entry: dict, paper_id: str, kind: str) -> int:
    require(entry.get("paperId") == paper_id, f"{paper_id}: paperId mismatch")
    require(entry.get("kind") == kind, f"{paper_id}: kind mismatch")
    require(str(entry.get("sourceUrl", "")).startswith("https://"), f"{paper_id}: missing HTTPS source")
    require(bool(entry.get("sourceLocation")), f"{paper_id}: missing source location")
    phrase = entry.get("passageMatchEvidence", "")
    require(len(phrase) >= 20, f"{paper_id}: passage match phrase too short")

    category, slug = paper_id.split(":", 1)
    paper = json.loads((PAPERS / category / f"{slug}.json").read_text())
    require(paper.get("id") == paper_id, f"{paper_id}: local paper mismatch")

    pdf = ROOT / entry["originalPdfPath"]
    require(pdf.is_file() and pdf.suffix == ".pdf", f"{paper_id}: original PDF missing")
    require(digest(pdf.read_bytes()) == entry["originalPdfSha256"], f"{paper_id}: original PDF changed")

    first, last = entry.get("questionRange", [None, None])
    require((first, last) in ((26, 35), (36, 45)), f"{paper_id}: unsupported question range")
    require(kind != "listening_section_c_dictation" or (first, last) == (26, 35),
            f"{paper_id}: dictation must use questions 26–35")
    answers = entry.get("answers")
    expected_numbers = [str(n) for n in range(first, last + 1)]
    require(isinstance(answers, dict) and list(answers) == expected_numbers, f"{paper_id}: incomplete or unordered answers")

    if kind == "word_bank_cloze":
        questions = [
            q for q in paper["questions"]
            if q.get("number") in expected_numbers and (q.get("context") or {}).get("kind") == "word_bank_cloze"
        ]
        require(len(questions) == 10, f"{paper_id}: expected 10 local word-bank questions")
        context = questions[0]["context"]
        require(all(q["context"]["id"] == entry["localContextId"] for q in questions), f"{paper_id}: word-bank context differs")
        require(context["id"] == entry["localContextId"], f"{paper_id}: context ID changed")
        require(phrase.casefold() in context["text"].casefold(), f"{paper_id}: passage match absent")
        require(digest(context["text"].encode()) == entry["localPassageSha256"], f"{paper_id}: passage changed")
        require(context["wordBankSourceBlocks"] == entry["wordBankSourceBlocks"], f"{paper_id}: word-bank source changed")
        bank = {word["label"].rstrip("."): word["text"] for word in context["wordBank"]}
        require(len(bank) == 15, f"{paper_id}: expected 15 local word-bank choices")
        for number, answer in answers.items():
            letter = answer.get("letter")
            require(letter in bank, f"{paper_id} Q{number}: unknown option {letter}")
            require(answer.get("word") == bank[letter], f"{paper_id} Q{number}: answer word disagrees with local choice")
    else:
        require(kind == "listening_section_c_dictation", f"{paper_id}: unsupported kind")
        by_id = {block["id"]: block for block in paper["blocks"]}
        source_ids = entry.get("sourceBlockIds")
        require(isinstance(source_ids, list) and source_ids, f"{paper_id}: missing passage blocks")
        require(all(block_id in by_id for block_id in source_ids), f"{paper_id}: missing local passage block")
        passage = "\n".join(by_id[block_id]["text"] for block_id in source_ids)
        require(phrase.casefold() in passage.casefold(), f"{paper_id}: passage match absent")
        require(digest(passage.encode()) == entry["localPassageSha256"], f"{paper_id}: passage changed")
        blanks = []
        for block_id in source_ids:
            blanks.extend(re.findall(r'<span class="blank">\s*(\d+)\s*</span>', by_id[block_id]["contentHtml"]))
        require(blanks == expected_numbers, f"{paper_id}: local printed blank sequence differs: {blanks}")
        require(all(bool(answer.get("word", "").strip()) for answer in answers.values()), f"{paper_id}: empty dictation answer")

    return len(answers)


def validate(path: Path = DEFAULT_EVIDENCE) -> tuple[int, int, int]:
    data = json.loads(path.read_text())
    require(data.get("schema") == "verified-english-answer-evidence.v1", "unsupported evidence schema")
    require(data.get("questionRanges") == [[26, 35], [36, 45]], "unexpected question ranges")
    groups = 0
    answers = 0
    for section, kind in (("wordBank", "word_bank_cloze"), ("listeningDictation", "listening_section_c_dictation")):
        entries = data.get(section)
        require(isinstance(entries, dict), f"missing {section} evidence")
        for paper_id, entry in entries.items():
            answers += validate_entry(entry, paper_id, kind)
            groups += 1
    return groups, answers, len(data["wordBank"])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", nargs="?", type=Path, default=DEFAULT_EVIDENCE)
    args = parser.parse_args()
    groups, answers, word_bank_groups = validate(args.path)
    print(f"Validated {groups} source-cited groups, {answers} answers: "
          f"{word_bank_groups} word-bank and {groups - word_bank_groups} dictation groups")


if __name__ == "__main__":
    main()
