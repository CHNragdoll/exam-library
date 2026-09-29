"""Recognize isolated, printed page numbers without touching exam content."""

import re


PAGE_FOOTER_RE = re.compile(r"\s*[•・·.\-—]?\s*(\d{1,3})\s*[•・·.\-—]?\s*")


def is_page_footer_line(text: str, page_number: int) -> bool:
    """Accept only a whole decorative line numbered for its physical page."""
    match = PAGE_FOOTER_RE.fullmatch(text)
    return bool(match and int(match.group(1)) == page_number)


def without_trailing_page_footer(text: str, page_number: int) -> str:
    """Remove a matching footer only when it is the final nonempty line."""
    lines = text.splitlines()
    last = next((i for i in range(len(lines) - 1, -1, -1) if lines[i].strip()), None)
    if last is not None and is_page_footer_line(lines[last], page_number):
        del lines[last]
    return "\n".join(lines)
