"""Conservative, offline detection of unmapped source-PDF glyphs.

The source PDFs contain CID fonts whose ToUnicode CMaps explicitly map some
character codes to U+FFFD. PyMuPDF's rawdict can expose the CID itself as a
printable character, so scanning rawdict for control characters misses many
glyphs. ``get_texttrace()`` reports U+FFFD for all of them.

This module never guesses a replacement character. Callers can keep each
unresolved glyph as a small inline rendering of its source-PDF bbox.
"""

from __future__ import annotations

from collections import defaultdict
import re
from typing import Any

import fitz


_REPLACEMENT_CID = re.compile(rb"<([0-9A-Fa-f]+)>\s*<FFFD>", re.IGNORECASE)


def _replacement_cids(doc: fitz.Document, font_xref: int) -> set[int]:
    """Read explicit CID -> U+FFFD entries from a font's ToUnicode stream."""
    kind, value = doc.xref_get_key(font_xref, "ToUnicode")
    if kind != "xref":
        return set()
    cmap_xref = int(value.split()[0])
    return {int(match, 16) for match in _REPLACEMENT_CID.findall(doc.xref_stream(cmap_xref))}


def _page_fonts(page: fitz.Page) -> dict[str, list[tuple[int, set[int]]]]:
    fonts: dict[str, list[tuple[int, set[int]]]] = defaultdict(list)
    doc = page.parent
    for xref, _ext, _type, name, _ref, encoding, _referencer in page.get_fonts(full=True):
        if encoding != "Identity-H":
            continue
        trace_name = name.removesuffix("-Identity-H")
        item = (xref, _replacement_cids(doc, xref))
        if item not in fonts[trace_name]:
            fonts[trace_name].append(item)
    return fonts


def get_font_maps(doc: fitz.Document) -> dict[str, dict[str, str]]:
    """Return only independently verified replacements for broken glyphs.

    The investigated PDFs have CID-only CFF glyph names and explicit FFFD
    ToUnicode entries. Their glyph IDs do not have a verified Unicode
    equivalent in the same source font. Consequently this strict function
    returns an empty map. It is intentionally unsuitable for OCR guesses or
    document-independent substitutions such as U+0084 -> a fixed letter.
    """
    return {}


def _fallback_positions_for_line(
    chars: list[dict[str, Any]], unknown_origins: set[tuple[float, float]]
) -> set[tuple[float, float]]:
    """Keep a broken glossary together without rasterizing surrounding prose.

    PDF text layers may map the other Chinese characters in a glossary to
    printable Latin letters. A true unmapped glyph inside the same pair of
    parentheses is evidence for that *parenthetical*, but not for the entire
    English line or every line using the same font.
    """
    positions = [
        (round(char["origin"][0], 3), round(char["origin"][1], 3))
        for char in chars
    ]
    hits = [
        index
        for index, (x, y) in enumerate(positions)
        if any(abs(x - ux) <= 0.15 and abs(y - uy) <= 0.15 for ux, uy in unknown_origins)
    ]
    if not hits:
        return set()

    open_to_close = {"(": ")", "（": "）"}
    stack: list[tuple[str, int]] = []
    pairs: list[tuple[int, int]] = []
    for index, char in enumerate(chars):
        value = char["c"]
        if value in open_to_close:
            stack.append((value, index))
        elif stack and value == open_to_close[stack[-1][0]]:
            _, start = stack.pop()
            pairs.append((start, index))

    affected: set[tuple[float, float]] = set()
    for hit in hits:
        enclosing = [(start, end) for start, end in pairs if start <= hit <= end]
        if not enclosing:
            # A missing mapping outside a bounded gloss cannot be localized
            # safely; retain the source line as a visual fallback.
            return {origin for char, origin in zip(chars, positions) if char["c"].strip()}
        start, end = min(enclosing, key=lambda pair: pair[1] - pair[0])
        affected.update(positions[start : end + 1])
    return affected


def get_unknown_glyphs(page: fitz.Page) -> list[dict[str, Any]]:
    """Locate glyphs with missing Unicode mappings on one PDF page.

    Each result includes the exact source bbox, origin and font for pairing
    with ``page.get_text('rawdict')``. ``gid`` comes directly from PyMuPDF.
    ``charcode`` is supplied only when the font is uniquely resolved to an
    Identity-H CID font and its ToUnicode CMap explicitly maps that same CID
    to FFFD. Otherwise it is ``None``; do not infer it from rawdict text.

    Bboxes are in PDF page coordinates. For a visual fallback, clip the source
    page or its SVG to this bbox with a small safety margin, preserving the
    glyph's aspect ratio and baseline in the flowing line.
    """
    fonts = _page_fonts(page)
    unknown: list[dict[str, Any]] = []
    for span in page.get_texttrace():
        name = span["font"]
        for unicode_value, gid, origin, bbox in span["chars"]:
            if not (unicode_value == 0xFFFD or 0xE000 <= unicode_value <= 0xF8FF or 0xF0000 <= unicode_value <= 0x10FFFD or unicode_value < 32 and unicode_value not in (9,10,13) or 0x80 <= unicode_value <= 0x9F):
                continue
            matching_xrefs = sorted({xref for xref, cids in fonts.get(name, []) if gid in cids})
            confirmed = bool(matching_xrefs)
            unknown.append(
                {
                    "page": page.number + 1,
                    "font": name,
                    "font_xref": matching_xrefs[0] if len(matching_xrefs) == 1 else None,
                    "font_xrefs": matching_xrefs,
                    "gid": gid,
                    "charcode": gid if confirmed else None,
                    "origin": tuple(origin),
                    "bbox": tuple(bbox),
                    "font_size": span["size"],
                    "unicode": None,
                    "reason": (
                        "ToUnicode maps this CID to U+FFFD"
                        if confirmed
                        else "replacement glyph; CID/font resolution needs review"
                    ),
                }
            )
    # Some source fonts map the other characters of a Chinese gloss to
    # printable ASCII. Preserve only the parenthetical containing an actually
    # unmapped glyph; unrelated English text and same-font lines remain text.
    if unknown:
        bad_origins = {
            (round(g["origin"][0], 3), round(g["origin"][1], 3)) for g in unknown
        }
        traces = page.get_texttrace()
        affected: set[tuple[float, float]] = set()
        raw_affected: dict[tuple[float, float], dict[str, Any]] = {}
        for block in page.get_text("rawdict")["blocks"]:
            for line in block.get("lines", []):
                chars = [char for span in line["spans"] for char in span["chars"]]
                line_affected = _fallback_positions_for_line(chars, bad_origins)
                affected.update(line_affected)
                for span in line["spans"]:
                    for char in span["chars"]:
                        key = (round(char["origin"][0], 3), round(char["origin"][1], 3))
                        if key in line_affected:
                            raw_affected[key] = {
                                "page": page.number + 1,
                                "font": span["font"],
                                "gid": None,
                                "origin": tuple(char["origin"]),
                                "bbox": tuple(char["bbox"]),
                                "font_size": span["size"],
                                "unicode": None,
                                "reason": "source gloss or line contains unreliable font encoding",
                            }
        # rawdict and texttrace occasionally report slightly different origins
        # for the same printable glyph (about 0.05 pt in the source PDFs).
        # Match geometrically, while keeping the tolerance much smaller than
        # ordinary character spacing so adjacent English stays selectable.
        affected_grid: dict[tuple[int, int], list[tuple[float, float]]] = defaultdict(list)
        for x, y in affected:
            affected_grid[(round(x * 5), round(y * 5))].append((x, y))

        def in_affected_area(x: float, y: float) -> bool:
            cell_x, cell_y = round(x * 5), round(y * 5)
            return any(
                abs(x - ax) <= 0.15 and abs(y - ay) <= 0.15
                for dx in (-1, 0, 1)
                for dy in (-1, 0, 1)
                for ax, ay in affected_grid.get((cell_x + dx, cell_y + dy), ())
            )

        by_origin = {
            (round(g["origin"][0], 3), round(g["origin"][1], 3)): g for g in unknown
        }
        for span in traces:
            for cp, gid, origin, bbox in span["chars"]:
                key = (round(origin[0], 3), round(origin[1], 3))
                if not in_affected_area(*key) or cp in (9, 10, 13, 32):
                    continue
                if key not in by_origin:
                    by_origin[key] = {
                        "page": page.number + 1,
                        "font": span["font"],
                        "gid": gid,
                        "origin": tuple(origin),
                        "bbox": tuple(bbox),
                        "font_size": span["size"],
                        "unicode": None,
                        "reason": "source gloss or line contains unreliable font encoding",
                    }
        # The extractor matches rawdict origins exactly. Retain those records
        # even when texttrace gives a neighboring printable glyph a slightly
        # shifted origin; otherwise stray ASCII remains between glyph boxes.
        for key, record in raw_affected.items():
            by_origin.setdefault(key, record)
        unknown = list(by_origin.values())
    return unknown
