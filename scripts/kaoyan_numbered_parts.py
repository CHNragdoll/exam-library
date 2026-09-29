"""Recover printed English I reading tasks represented only as passage/figure content."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
import re

from bs4 import NavigableString, Tag


MARKER = re.compile(r"\((4[1-9]|50)\)")
CHOICE = re.compile(r"^([A-G])\s*[.)．）]\s*")


def numbered_parts(doc: dict, pages: list[Tag], pdf: Path, pdf_path: str,
                   plain) -> dict[str, list[dict]]:
    """Return source-anchored tasks only when all five printed slots are present."""
    if doc["category"] != "kaoyan" or doc["kind"] != "questions" or not doc["id"].endswith("-01"):
        return {}
    if not pdf.is_file():
        raise FileNotFoundError(pdf)
    sections: dict[str, list[tuple[int, str, Tag, str]]] = defaultdict(list)
    active = ""
    reading_started = False
    writing_started = False
    for page, element in enumerate(pages, 1):
        for index, child in enumerate(element.find_all(recursive=False), 1):
            value = plain(child)
            if value == "Section III Writing":
                active = ""
                writing_started = True
            elif value in {"Part B", "Part C"} and page >= 9 and not reading_started and not writing_started:
                active = value
                reading_started = True
            elif value in {"Part B", "Part C"} and reading_started and not writing_started:
                active = value
            if active:
                sections[active].append((page, f"b-{page}-{index}", child, value))

    anchored: dict[str, list[dict]] = defaultdict(list)
    for title, rows in sections.items():
        instruction = next(((block_id, value) for _, block_id, _, value in rows
                            if "underlined segments" in value.lower()), None)
        if not instruction:
            continue
        expected = range(41, 46) if title == "Part B" else range(46, 51)
        wanted = set(expected)
        passage = [(page, block_id, child, value) for page, block_id, child, value in rows
                   if child.name == "p" and child.select_one("u")]
        if not passage:
            continue
        found: dict[int, dict] = {}
        active_number = None
        for page, block_id, child, _ in passage:
            underline_index = 0
            def walk(node):
                nonlocal active_number, underline_index
                for part in node.contents:
                    if isinstance(part, NavigableString):
                        for marker in MARKER.finditer(str(part)):
                            number = int(marker.group(1))
                            if number in wanted:
                                if number in found:
                                    raise ValueError(f"duplicate English I translation {doc['id']} Q{number}")
                                found[number] = {"anchor": block_id, "fragments": [], "sourceBlocks": []}
                                active_number = number
                    elif isinstance(part, Tag) and part.name == "u":
                        underline_index += 1
                        if active_number in wanted:
                            found[active_number]["fragments"].append({
                                "sourceBlockId": block_id, "underlineIndex": underline_index,
                                "text": plain(part)})
                            found[active_number]["sourceBlocks"].append(block_id)
                    elif isinstance(part, Tag):
                        walk(part)
            walk(child)
        if set(found) != wanted or any(not item["fragments"] for item in found.values()):
            # A damaged source must not yield guessed question nodes.
            continue
        instruction_position = next(index for index, (_, block_id, _, _) in enumerate(rows)
                                    if block_id == instruction[0])
        passage_rows = rows[instruction_position + 1:]
        passage_blocks = [block_id for _, block_id, child, _ in passage_rows if child.name == "p"]
        source_pages = list(dict.fromkeys(block_id.split("-")[1] for block_id in passage_blocks))
        context = {
            "kind": "translation_passage", "id": f"{doc['id']}:{title.lower().replace(' ', '-')}",
            "text": instruction[1] + "\n\n" + "\n\n".join(
                value for _, _, child, value in passage_rows if child.name == "p" and value),
            "sourceBlocks": [instruction[0], *passage_blocks],
            "sourcePages": list(dict.fromkeys([instruction[0].split("-")[1], *source_pages])),
            "instructionSourceBlock": instruction[0],
            "pdfEvidence": {"path": pdf_path, "pages": [int(p) for p in
                                                       dict.fromkeys([instruction[0].split("-")[1], *source_pages])]},
        }
        for number in expected:
            item = found[number]
            fragments = item["fragments"]
            source_blocks = list(dict.fromkeys(item["sourceBlocks"]))
            anchored[item["anchor"]].append({
                "number": str(number), "sectionKind": "free_response", "sectionTitle": title,
                "sourceBlocks": source_blocks,
                "sourcePages": list(dict.fromkeys(block_id.split("-")[1] for block_id in source_blocks)),
                "stem": " ".join(" ".join(fragment["text"] for fragment in fragments).split()),
                "options": [], "context": context, "translationFragments": fragments,
            })

    rows = sections.get("Part B", [])
    if rows and not any(item["sectionTitle"] == "Part B" for group in anchored.values() for item in group):
        markers: dict[int, tuple[int, str, str]] = {}
        for position, (page, block_id, child, value) in enumerate(rows):
            for match in MARKER.finditer(value):
                number = int(match.group(1))
                if 41 <= number <= 45:
                    if number in markers:
                        raise ValueError(f"duplicate English I Part B slot {doc['id']} Q{number}")
                    markers[number] = (position, block_id, value)
        directions = " ".join(value for _, _, _, value in rows[:4]).lower()
        gap_directions = ("a-g" in directions or "a–g" in directions or
                          "sentences have been removed" in directions or "subheadings" in directions)
        if set(markers) == set(range(41, 46)) and gap_directions:
            bank_rows = rows[max(item[0] for item in markers.values()) + 1:]
            bank: dict[str, dict] = {}
            active_letter = None
            for page, block_id, child, value in bank_rows:
                if child.name == "ul":
                    for li in child.select(":scope > li"):
                        match = CHOICE.match(plain(li))
                        if not match:
                            continue
                        letter = match.group(1)
                        bank[letter] = {"text": plain(li)[match.end():].strip(),
                                        "sourceBlocks": [block_id]}
                        active_letter = letter
                    continue
                match = CHOICE.match(value)
                if match:
                    active_letter = match.group(1)
                    if active_letter in bank:
                        raise ValueError(f"duplicate English I Part B choice {doc['id']} {active_letter}")
                    bank[active_letter] = {"text": value[match.end():].strip(),
                                           "sourceBlocks": [block_id]}
                elif active_letter and child.name == "p" and value:
                    bank[active_letter]["text"] += " " + value
                    bank[active_letter]["sourceBlocks"].append(block_id)
            if list(bank) == list("ABCDEFG") and all(item["text"] for item in bank.values()):
                bank_blocks = list(dict.fromkeys(block_id for item in bank.values()
                                                  for block_id in item["sourceBlocks"]))
                passage_rows = rows[:max(item[0] for item in markers.values()) + 1]
                context_blocks = [bid for _, bid, _, _ in passage_rows] + bank_blocks
                context = {
                    "kind": "numbered_gap_passage", "id": f"{doc['id']}:part-b",
                    "taskForm": ("heading_match" if "description" in directions or
                                 "heading" in directions else "sentence_insertion"),
                    "text": "\n\n".join(value for _, _, _, value in passage_rows if value),
                    "sourceBlocks": context_blocks,
                    "sourcePages": list(dict.fromkeys(block_id.split("-")[1] for block_id in context_blocks)),
                    "choiceBankSourceBlocks": bank_blocks,
                    "choiceBank": [{"id": f"{doc['id']}:part-b:{letter}", "label": letter + ".",
                                    "text": bank[letter]["text"], "sourceOrder": order,
                                    "sourceBlocks": bank[letter]["sourceBlocks"]}
                                   for order, letter in enumerate("ABCDEFG", 1)],
                    "pdfEvidence": {"path": pdf_path, "pages": [int(p) for p in
                                                               dict.fromkeys(block_id.split("-")[1] for block_id in context_blocks)]},
                }
                for number in range(41, 46):
                    _, anchor, value = markers[number]
                    anchored[anchor].append({
                        "number": str(number), "sectionKind": "single_choice", "sectionTitle": "Part B",
                        "sourceBlocks": [anchor, *bank_blocks],
                        "sourcePages": list(dict.fromkeys(block_id.split("-")[1]
                                                              for block_id in [anchor, *bank_blocks])),
                        "stem": value, "options": [
                            {"label": letter + ".", "sourceLabel": letter + ".",
                             "text": bank[letter]["text"], "sourceOrder": order,
                             "sourceOptionId": f"{doc['id']}:part-b:{letter}"}
                            for order, letter in enumerate("ABCDEFG", 1)],
                        "context": context,
                    })
    return anchored
