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
    # Some scanned/OCR fonts map visible Chinese to printable ASCII. Preserve
    # the full affected line instead of trusting the other characters in it.
    if unknown:
        bad_origins={(round(g['origin'][0],3),round(g['origin'][1],3)) for g in unknown}
        total=defaultdict(int);bad=defaultdict(int)
        traces=page.get_texttrace()
        for span in traces:total[span['font']]+=len(span['chars'])
        for g in unknown:bad[g['font']]+=1
        suspect={f for f,n in bad.items() if n>=2 and n/max(1,total[f])>=.01}
        affected=set()
        for block in page.get_text('rawdict')['blocks']:
            for line in block.get('lines',[]):
                positions={(round(c['origin'][0],3),round(c['origin'][1],3)) for sp in line['spans'] for c in sp['chars']}
                if positions & bad_origins or any(sp['font'] in suspect for sp in line['spans']):affected.update(positions)
        by_origin={(round(g['origin'][0],3),round(g['origin'][1],3)):g for g in unknown}
        for span in traces:
            for cp,gid,origin,bbox in span['chars']:
                key=(round(origin[0],3),round(origin[1],3))
                if key not in affected or cp in (9,10,13,32):continue
                if key not in by_origin:
                    by_origin[key]={'page':page.number+1,'font':span['font'],'gid':gid,'origin':tuple(origin),'bbox':tuple(bbox),'font_size':span['size'],'unicode':None,'reason':'source line contains unreliable OCR/font encoding'}
        unknown=list(by_origin.values())
    return unknown
