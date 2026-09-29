"""Read private CET evidence and prepare fail-closed answer attachments.

The functions operate on in-memory data. They never write canonical papers,
translation sidecars, or the question database.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from verify_english_answer_evidence import DEFAULT_EVIDENCE, validate


def _load_verified(path: Path) -> dict:
    validate(path)
    return json.loads(path.read_text(encoding="utf-8"))


def dictation_manifest_evidence(path: Path = DEFAULT_EVIDENCE) -> dict:
    """Return the exact schema accepted by build_english_paragraph_manifest.

    A source locator such as "Section C answer list, questions 26–35" is
    copied verbatim into the builder's ``sourcePage`` field. No numeric page is
    invented when the cited web source has no page numbering.
    """
    evidence = _load_verified(path)
    papers = {}
    for paper_id, entry in evidence["listeningDictation"].items():
        source_location = entry["sourceLocation"].strip()
        if "Section C" not in source_location or "26–35" not in source_location:
            raise ValueError(f"{paper_id}: cannot use uncited dictation source location")
        papers[paper_id] = {
            "sourceUrl": entry["sourceUrl"],
            "sourcePage": source_location,
            "passageMatchEvidence": entry["passageMatchEvidence"],
            "answers": copy.deepcopy(entry["answers"]),
            "originalPdfPath": entry["originalPdfPath"],
            "originalPdfSha256": entry["originalPdfSha256"],
            "localPassageSha256": entry["localPassageSha256"],
            "sourceBlockIds": list(entry["sourceBlockIds"]),
        }
    return {"schema": "verified-listening-dictation.v1", "papers": papers}


def word_bank_attachment_plan(papers: dict[str, dict], path: Path = DEFAULT_EVIDENCE,
                              *, require_all: bool = True) -> list[tuple[dict, dict]]:
    """Validate selected cited groups; full builds require every target."""
    evidence = _load_verified(path)
    updates = []
    for paper_id, entry in evidence["wordBank"].items():
        if paper_id not in papers:
            if require_all:
                raise ValueError(f"{paper_id}: target paper missing")
            continue
        paper = papers[paper_id]
        if not paper or paper.get("id") != paper_id:
            raise ValueError(f"{paper_id}: target paper missing")
        numbers = set(entry["answers"])
        questions = [q for q in paper["questions"] if q.get("recordType") == "question"
                     and q.get("number") in numbers]
        if len(questions) != 10 or {q["number"] for q in questions} != numbers:
            raise ValueError(f"{paper_id}: target has missing or duplicate cloze numbers")
        for question in questions:
            number = question["number"]
            context = question.get("context") or {}
            if context.get("kind") != "word_bank_cloze" or context.get("id") != entry["localContextId"]:
                raise ValueError(f"{paper_id} Q{number}: target context differs")
            if hashlib.sha256(context["text"].encode()).hexdigest() != entry["localPassageSha256"]:
                raise ValueError(f"{paper_id} Q{number}: target passage differs")
            bank = {choice["label"].rstrip("."): choice["text"] for choice in context["wordBank"]}
            selected = entry["answers"][number]
            if bank.get(selected["letter"]) != selected["word"]:
                raise ValueError(f"{paper_id} Q{number}: local word-bank choice differs")
            answer = question["answer"]
            if answer["status"] == "explicit" and answer.get("value") == selected["letter"]:
                continue
            if answer["status"] != "missing" or answer.get("value"):
                raise ValueError(f"{paper_id} Q{number}: existing answer conflicts")
            replacement = copy.deepcopy(answer)
            replacement["value"] = selected["letter"]
            replacement["status"] = "explicit"
            replacement["externalSource"] = {
                "kind": "source_verified_word_bank",
                "url": entry["sourceUrl"],
                "sourceLocation": entry["sourceLocation"],
                "passageMatchEvidence": entry["passageMatchEvidence"],
                "originalPdfSha256": entry["originalPdfSha256"],
                "answerToken": f"{number}-{selected['letter']}",
                "word": selected["word"],
            }
            updates.append((answer, replacement))
    return updates


def attach_verified_word_bank_answers(papers: dict[str, dict], path: Path = DEFAULT_EVIDENCE,
                                      *, require_all: bool = True) -> int:
    """Attach verified letters to in-memory papers after all checks pass."""
    updates = word_bank_attachment_plan(papers, path, require_all=require_all)
    for answer, replacement in updates:
        answer.update(replacement)
    for paper_id in _load_verified(path)["wordBank"]:
        if paper_id not in papers:
            continue
        paper = papers[paper_id]
        paper["audit"]["linkedAnswers"] = sum(
            q["answer"]["status"] == "explicit" for q in paper["questions"]
            if q.get("recordType") == "question"
        )
    return len(updates)
