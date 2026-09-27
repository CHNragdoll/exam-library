"""Recover PDF-verified question text from the original reader's SVG text layer.

The reflow extractor retains unreadable PDF text as ``source_line`` images.
For the bounded pages below, the older reader also contains selectable SVG
``<text>`` elements with the printed lines and their PDF coordinates. Read
only lines inside each retained image crop, then add searchable blocks after
that crop. The image remains the visual source of truth.
"""

from collections import defaultdict
from pathlib import Path
import re

from lxml import html


RECOVERY_CASES: dict[tuple[str, str, int], tuple[int, ...]] = {
    ("cet4", "2020-09-01", 8): (51, 52, 53, 54, 55),
    ("cet4", "2020-12-01", 6): (40,),
    ("cet4", "2020-12-02", 2): (16, 17, 18),
    ("cet4", "2020-12-03", 6): (51,),
    ("cet4", "2021-06-02", 7): (46, 47, 48, 49, 50),
    ("cet6", "2019-12-01", 12): (53, 54, 55),
    ("cet6", "2019-12-02", 12): (51, 52, 53, 54, 55),
    ("cet6", "2019-12-03", 8): (51, 52, 53, 54, 55),
    ("cet6", "2020-07-01", 8): (37, 39, 40, 41, 43, 44, 45),
    ("cet6", "2020-09-01", 12): (53, 54, 55),
    ("cet6", "2020-09-02", 7): (51, 52, 53, 54, 55),
    ("cet6", "2020-12-01", 2): (9, 10, 11, 12, 13, 14),
    ("cet6", "2020-12-01", 6): (38, 39, 40, 41, 42, 43),
    ("cet6", "2020-12-02", 1): (5, 6),
    ("cet6", "2020-12-03", 6): (51, 52, 53, 54, 55),
    ("cet6", "2021-06-02", 6): tuple(range(36, 46)),
    ("cet6", "2021-06-02", 8): (51, 52, 53, 54, 55),
    ("cet6", "2021-06-03", 6): (51, 52, 53, 54, 55),
}
MATCHING_CASES = {
    ("cet4", "2020-12-01", 6),
    ("cet6", "2020-07-01", 8),
    ("cet6", "2020-12-01", 6),
    ("cet6", "2021-06-02", 6),
}

QUESTION = re.compile(r"^\s*(\d{1,2})\s*[.．]\s*")
SPACED_51 = re.compile(r"^\s*5\s+1\s*[.．]\s*")
OPTION = re.compile(r"(?<![A-Za-z])([A-D])\s*[)）]\s*")
WHITESPACE = re.compile(r"\s+")
SECTION = re.compile(r"^(?:Section\s+[A-D]|Part\s+[IVX]+|Directions\s*[:：,]|"
                     r"Questions?\s+\d+\s+to\b|Passage\s+(?:One|Two|Three|\d+))\b", re.I)

# Each replacement was checked against the printed PDF page. Do not extend
# this table by spellchecking or guessing from nearby answers.
PDF_CONFIRMED_REPLACEMENTS = {
    ("cet4", "2020-12-01", 6): (("t05iay", "today"), ("qu\x8dtionable", "questionable")),
    ("cet4", "2020-12-02", 2): (("Dis® .of", "Dispose of"),
                                ("i\xad accidental", "in accidental"),
                                ("C) • To", "C) To")),
    ("cet4", "2020-12-03", 6): (("politic[ans", "politicians"),),
    ("cet4", "2021-06-02", 7): (("tǃtrack", "to track"),),
    ("cet6", "2019-12-03", 8): (("tum out", "turn out"),),
    ("cet6", "2020-07-01", 8): (("\U001001b3", "’"),
                                ("two - year - olds", "two-year-olds")),
    ("cet6", "2020-09-01", 12): (("j oint", "joint"),),
    ("cet6", "2020-12-01", 2): (("of ten", "often"),
                                ("fashion-consci01:JS", "fashion-conscious")),
    ("cet6", "2020-12-01", 6): (("know-the", "know the"),
                                ("in tum", "in turn"),
                                ("AI t\x81chnology", "AI technology"),
                                ("_yields", "yields")),
    ("cet6", "2020-12-02", 1): (("isn't. so", "isn't so"),
                                ("doesc't", "doesn't")),
    ("cet6", "2020-12-03", 6): (("and·her", "and her"),
                                ("coll±gues", "colleagues"),
                                ("cµlture", "culture"),
                                ("characteristics· of", "characteristics of"),
                                ("culturally-based.entities", "culturally-based entities"),
                                ("species.before", "species before")),
    ("cet6", "2021-06-02", 6): (("pamage", "damage"),),
    ("cet6", "2021-06-02", 8): (("C).Only", "C) Only"),
                                ("jamsin", "jams in"),
                                ("eas,ing", "easing"),
                                ("coµgestion", "congestion"),
                                ("D),", "D)"),
                                ("techn'ology", "technology")),
    ("cet6", "2021-06-03", 6): (("I.t", "It"),
                                ("It .can", "It can"),
                                ("writing ..", "writing."),
                                ("Jt", "It")),
}
PDF_CONFIRMED_OPTION_VALUES = {
    ("cet6", "2021-06-03", 6, 54, "B"):
        ("lt helps tÃ:t prottxt _ont!'S intellectµal pr9perty rights.",
         "It helps to protect one's intellectual property rights."),
}

# The source-line crop stops before these already-extracted plain paragraphs.
# Move the exact continuation into the recovered stem so the question card is
# complete and the reflow does not repeat the line.
PRINTED_CONTINUATIONS = {
    ("cet6", "2020-07-01", 8, 43): "answer questions.",
    ("cet6", "2020-07-01", 8, 44): "thinking abilities has become less and less influential.",
    ("cet6", "2020-12-01", 6, 43): "fields.",
}


def _clean(text: str, case: tuple[str, str, int]) -> str:
    text = WHITESPACE.sub(" ", text).strip()
    for old, new in PDF_CONFIRMED_REPLACEMENTS.get(case, ()):
        text = text.replace(old, new)
    return text


def _svg_rows(original_html: Path, page_number: int) -> list[tuple[float, float, str]]:
    tree = html.parse(str(original_html))
    nodes = tree.xpath(
        f'//main/section[@data-page="{page_number}"]//svg[contains(@class,"text-overlay")]//text'
    )
    if not nodes:
        raise ValueError(f"missing original SVG text layer: {original_html} p{page_number}")
    pieces = []
    for node in nodes:
        text = "".join(node.itertext())
        if not text.strip():
            continue
        x, y = float(node.attrib["x"]), float(node.attrib["y"])
        width = float(node.attrib.get("textlength", "0"))
        size = float(node.attrib.get("font-size", "12"))
        pieces.append((x, y, width, size, text))
    rows: list[list] = []
    for piece in sorted(pieces, key=lambda item: (item[1], item[0])):
        nearest = next((row for row in reversed(rows[-3:]) if abs(row[0] - piece[1]) <= 3.2), None)
        if nearest is None:
            rows.append([piece[1], [piece]])
        else:
            nearest[1].append(piece)
    result = []
    for y, fragments in sorted(rows, key=lambda row: row[0]):
        fragments.sort(key=lambda item: item[0])
        combined = ""
        right = None
        for x, _, width, size, text in fragments:
            if right is not None and x - right > max(1.8, size * .16):
                combined += " "
            combined += text
            right = max(right or x, x + width)
        result.append((y, fragments[0][0], combined))
    return result


def _question_start(text: str) -> tuple[int, str] | None:
    spaced = SPACED_51.match(text)
    if spaced:
        return 51, text[spaced.end():].strip()
    match = QUESTION.match(text)
    return (int(match.group(1)), text[match.end():].strip()) if match else None


def _run(value: str) -> dict:
    return {"text": value, "flags": [False, False, False]}


def _pdf_verified_option(case: tuple[str, str, int], number: int,
                         label: str, value: str) -> str:
    correction = PDF_CONFIRMED_OPTION_VALUES.get((*case, number, label))
    if correction is None:
        return value
    old, new = correction
    if value != old:
        raise ValueError(f"PDF-verified option source changed: {case} Q{number} {label}")
    return new


def _append(previous: str, value: str) -> str:
    if not previous:
        return value
    if not value:
        return previous
    return previous + ("" if previous.endswith("-") else " ") + value


def _recovered_blocks(rows: list[tuple[float, float, str]], targets: set[int],
                      case: tuple[str, str, int]) -> list[tuple[int, list[dict]]]:
    found = []
    current = None
    for _, x, raw in rows:
        text = _clean(raw, case)
        if SECTION.match(text):
            if current:
                found.append(current)
                current = None
            continue
        start = _question_start(text)
        if start:
            if current:
                found.append(current)
            number, text = start
            current = {"number": number, "stem": "", "options": {}, "last_left": None,
                       "last_right": None} if number in targets else None
        if current is None:
            continue
        labels = list(OPTION.finditer(text))
        if labels:
            prefix = text[:labels[0].start()].strip()
            if prefix:
                current["stem"] = _append(current["stem"], prefix)
            for index, match in enumerate(labels):
                end = labels[index + 1].start() if index + 1 < len(labels) else len(text)
                label = match.group(1)
                value = text[match.end():end].strip()
                current["options"][label] = _append(current["options"].get(label, ""), value)
                # On two-column source rows A/C and B/D share a baseline.
                side = "right" if label in "CD" and len(labels) > 1 or x > 250 else "left"
                current[f"last_{side}"] = label
        elif current["options"]:
            side = "right" if x > 250 else "left"
            label = current[f"last_{side}"] or current["last_left"] or current["last_right"]
            if label:
                current["options"][label] = _append(current["options"][label], text)
        else:
            current["stem"] = _append(current["stem"], text)
    if current:
        found.append(current)
    result = []
    for item in found:
        number = item["number"]
        if not item["stem"] and not item["options"]:
            raise ValueError(f"empty SVG question: {case} Q{number}")
        blocks = [{"type": "question", "runs": [_run(f"{number}." +
                                                     (f" {item['stem']}" if item["stem"] else ""))]}]
        if case in MATCHING_CASES:
            item["options"] = {}
        if item["options"]:
            blocks.append({"type": "options", "items": [
                {"label": label, "runs": [_run(_pdf_verified_option(
                    case, number, label, item["options"][label]))]}
                for label in "ABCD" if label in item["options"]
            ]})
        result.append((number, blocks))
    return result


def recover_image_questions(category: str, stem: str, page_number: int,
                            blocks: list[dict], original_html: Path) -> None:
    """Insert the confirmed image-only questions after their original crops."""
    case = (category, stem, page_number)
    targets = set(RECOVERY_CASES.get(case, ()))
    if not targets:
        return
    rows = _svg_rows(original_html, page_number)
    recovered = []
    additions = defaultdict(list)
    for index, block in enumerate(blocks):
        if block["type"] != "source_line":
            continue
        _, top, _, bottom = block["bbox"]
        crop_rows = [row for row in rows if top - 2.5 <= row[0] <= bottom + 2.5]
        for number, extra in _recovered_blocks(crop_rows, targets, case):
            if number in recovered:
                raise ValueError(f"duplicate SVG question: {case} Q{number}")
            recovered.append(number)
            additions[index].extend(extra)
    if set(recovered) != targets:
        raise ValueError(f"SVG question coverage mismatch: {case}; "
                         f"expected {sorted(targets)}, found {sorted(recovered)}")
    for index in sorted(additions, reverse=True):
        blocks[index + 1:index + 1] = additions[index]
    for (paper_category, paper_stem, pn, number), continuation in PRINTED_CONTINUATIONS.items():
        if case != (paper_category, paper_stem, pn):
            continue
        question = next(block for block in blocks if block["type"] == "question" and
                        _question_start(block["runs"][0]["text"]) and
                        _question_start(block["runs"][0]["text"])[0] == number)
        expected_next = blocks.index(question) + 1
        while expected_next < len(blocks) and blocks[expected_next]["type"] == "options":
            expected_next += 1
        following = blocks[expected_next]
        if following["type"] != "paragraph" or "".join(run["text"] for run in following["runs"]) != continuation:
            raise ValueError(f"image-question continuation changed: {case} Q{number}")
        question["runs"][0]["text"] = _append(question["runs"][0]["text"], continuation)
        blocks.pop(expected_next)
