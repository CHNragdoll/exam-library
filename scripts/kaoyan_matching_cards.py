"""PDF-checked English Part B slots hidden inside retained source figures.

The 2011–26 English II matching tables and five English I ordering arrows are
intentionally kept as original figure images in reflow. Their selectable
original-HTM SVG text supplies the printed slot numbers and table choices;
English I paragraph choices come from the existing reflow source blocks.
"""

from __future__ import annotations

from pathlib import Path
import re

from lxml import html


TABLE_PAPERS = frozenset({"2011-02", "2012-02", "2014-02", "2017-02",
                          "2019-02", "2023-02", "2024-02", "2026-02"})
ORDERING_PAPERS = frozenset({"2010-01", "2011-01", "2014-01", "2017-01",
                            "2018-01", "2019-01", "2023-01", "2025-01", "2026-01"})
ORDERING_FIXED = {"2010-01": ("E",), "2014-01": ("A", "E"),
                  "2011-01": ("G", "E"), "2017-01": ("D", "B"),
                  "2018-01": ("C", "F"), "2019-01": ("C", "F"),
                  "2023-01": ("A", "E", "H"),
                  "2025-01": ("A", "C", "H"), "2026-01": ("F", "H", "C")}
SLOT = re.compile(r"(?<!\d)(4[1-5])\s*[.．]?(?!\d)")
CHOICE = re.compile(r"^([A-H])\s*[.．)）]\s*")


def _spans(original_html: Path) -> list[tuple[float, float, str]]:
    tree = html.parse(str(original_html))
    nodes = tree.xpath('//main/section[@data-page="12"]//svg[contains(@class,"text-overlay")]//text')
    if not nodes:
        raise ValueError(f"missing selectable original-HTM SVG: {original_html} p12")
    # Space-only SVG text nodes carry the gaps between individually positioned
    # words; dropping them turns "Andrew Lansley" into "AndrewLansley".
    return [(float(node.attrib["x"]), float(node.attrib["y"]), "".join(node.itertext()))
            for node in nodes if "".join(node.itertext())]


def _lines(spans: list[tuple[float, float, str]]) -> list[tuple[float, str]]:
    rows: list[list] = []
    for x, y, text in sorted(spans, key=lambda item: (item[1], item[0])):
        near = next((row for row in reversed(rows[-3:]) if abs(row[0] - y) < 2.5), None)
        if near is None:
            rows.append([y, [(x, text)]])
        else:
            near[1].append((x, text))
    return [(y, " ".join("".join(part for _, part in sorted(parts)).split()))
            for y, parts in rows]


def _groups(lines: list[tuple[float, str]], marker: re.Pattern,
            expected: list[str]) -> dict[str, str]:
    groups: dict[str, str] = {}
    current = None
    for _, text in lines:
        match = marker.match(text)
        if match:
            current = match.group(1)
            if current in groups:
                raise ValueError(f"duplicate source marker {current}")
            groups[current] = text[match.end():].strip()
        elif current and text:
            groups[current] += " " + text
    if list(groups) != expected or any(not value.strip() for value in groups.values()):
        raise ValueError(f"matching-table SVG groups changed: {list(groups)} != {expected}")
    return {key: " ".join(value.split()) for key, value in groups.items()}


def table_cards(stem: str, original_html: Path) -> list[dict]:
    """Read five left prompts and the shared A–G bank from printed columns."""
    if stem not in TABLE_PAPERS:
        return []
    spans = _spans(original_html)
    labels = [(x, y, text.strip()) for x, y, text in spans
              if re.fullmatch(r"[A-G]\.", text.strip()) and x > 150]
    if [label for _, _, label in labels] != [f"{letter}." for letter in "ABCDEFG"]:
        raise ValueError(f"table choice labels changed: {stem}: {labels}")
    x_choice = min(x for x, _, _ in labels)
    y_start, y_end = labels[0][1] - 2.5, labels[-1][1] + 42
    visible = [(x, y, text) for x, y, text in spans if y_start <= y <= y_end]
    prompts = _groups(_lines([(x, y, text) for x, y, text in visible
                              if x < x_choice - 8]),
                      SLOT, [str(number) for number in range(41, 46)])
    options = _groups(_lines([(x, y, text) for x, y, text in visible
                              if x >= x_choice - 8]),
                      CHOICE, list("ABCDEFG"))
    return [{"number": number, "stem": f"{number}. {prompts[number]}",
             "options": options, "kind": "matching_table"}
            for number in prompts]


def ordering_cards(stem: str, original_html: Path,
                   preceding_blocks: list[dict]) -> list[dict]:
    """Read diagram slots and the existing lettered paragraph source blocks."""
    if stem not in ORDERING_PAPERS:
        return []
    spans = _spans(original_html)
    visible = " ".join(text for _, _, text in spans)
    slots = SLOT.findall(visible)
    if slots != [str(number) for number in range(41, 46)]:
        raise ValueError(f"ordering diagram slots changed: {stem}: {slots}")
    diagram_y = next(y for _, y, text in spans if SLOT.search(text))
    diagram = " ".join(text for _, y, text in spans
                       if abs(y - diagram_y) < 2.5)
    fixed = ORDERING_FIXED[stem]
    printed_fixed = re.findall(r"(?<![A-Za-z])([A-H])(?=\s|→|$)", diagram)
    if sorted(printed_fixed) != sorted(fixed):
        raise ValueError(f"ordering diagram fixed letters changed: {stem}: {printed_fixed}")
    diagram_sequence = re.findall(r"(?<![A-Za-z0-9])(?:4[1-5]|[A-H])(?=\s|→|[.．]|$)", diagram)
    if ([item for item in diagram_sequence if item.isdigit()] != slots or
            [item for item in diagram_sequence if item.isalpha()] != printed_fixed):
        raise ValueError(f"ordering diagram sequence changed: {stem}: {diagram_sequence}")
    options: dict[str, str] = {}
    option_blocks: dict[str, list[str]] = {}
    current = None
    for block in preceding_blocks:
        if block["sourcePageIndex"] not in {11, 12} or block["role"] not in {"content", "heading"}:
            continue
        text = block["text"].strip()
        match = re.match(r"^([A-H])\s*[)）.]\s*", text)
        if match:
            current = match.group(1)
            if current in options:
                raise ValueError(f"duplicate ordering choice: {stem} {current}")
            options[current] = text[match.end():].strip()
            option_blocks[current] = [block["id"]]
        elif current and text:
            options[current] += " " + text
            option_blocks[current].append(block["id"])
    expected = list("ABCDEFGH" if stem in {"2023-01", "2025-01", "2026-01"} else "ABCDEFG")
    if list(options) != expected or any(len(value) < 30 for value in options.values()):
        raise ValueError(f"ordering paragraph choices changed: {stem}: {list(options)}")
    available = {letter: value for letter, value in options.items() if letter not in fixed}
    return [{"number": number, "stem": f"{number}.", "options": available,
             "kind": "ordering_diagram",
             "fixedLetters": list(fixed),
             "diagramSequence": diagram_sequence,
             "sourceDiagramText": diagram,
             "optionBlockIds": {letter: list(option_blocks[letter]) for letter in available},
             "optionSourceBlocks": [bid for ids in option_blocks.values() for bid in ids]}
            for number in slots]
