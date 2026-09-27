"""Verify PDF-confirmed English questions on image-fallback pages are searchable.

The inventory was checked against the original PDFs on 2026-09-28. A question
only visible in a page image does not count as a structured question here.
"""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PAPERS = ROOT / "data/sources/exam-library/structured/papers"

# (category, paper, source PDF page): expected printed question numbers.
EXPECTED = {
    ("cet4", "2020-09-01", 8): range(51, 56),
    ("cet4", "2020-12-01", 6): (40,),
    ("cet4", "2020-12-02", 2): range(16, 19),
    ("cet4", "2020-12-03", 6): (51,),
    ("cet4", "2021-06-02", 7): range(46, 51),
    ("cet6", "2019-12-01", 12): range(53, 56),
    ("cet6", "2019-12-02", 12): range(51, 56),
    ("cet6", "2019-12-03", 8): range(51, 56),
    ("cet6", "2020-07-01", 8): (37, 39, 40, 41, 43, 45),
    ("cet6", "2020-09-01", 12): range(53, 56),
    ("cet6", "2020-09-02", 7): range(51, 56),
    ("cet6", "2020-12-01", 2): range(9, 15),
    ("cet6", "2020-12-01", 6): range(38, 44),
    ("cet6", "2020-12-02", 1): (5, 6),
    ("cet6", "2020-12-03", 6): range(51, 56),
    ("cet6", "2021-06-02", 6): range(36, 46),
    ("cet6", "2021-06-02", 8): (51, 52, 53, 55),
    ("cet6", "2021-06-03", 6): range(51, 56),
}


def verify(papers_dir: Path = PAPERS) -> list[str]:
    errors = []
    cache = {}
    for (category, paper, page), numbers in EXPECTED.items():
        path = papers_dir / category / f"{paper}.json"
        if path not in cache:
            cache[path] = json.loads(path.read_text(encoding="utf-8"))
        questions = cache[path]["questions"]
        for number in numbers:
            matching = [q for q in questions if q.get("number") == str(number)]
            if len(matching) != 1:
                errors.append(f"{category}/{paper} p{page} Q{number}: {len(matching)} records")
                continue
            if str(page) not in matching[0].get("sourcePages", []):
                errors.append(f"{category}/{paper} p{page} Q{number}: wrong source page")
            if not matching[0].get("sourceBlocks"):
                errors.append(f"{category}/{paper} p{page} Q{number}: no source blocks")
    return errors


if __name__ == "__main__":
    problems = verify()
    for problem in problems:
        print(problem)
    print(f"{sum(map(len, EXPECTED.values()))} PDF-confirmed image-fallback questions; {len(problems)} issues")
    raise SystemExit(bool(problems))
