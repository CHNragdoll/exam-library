"""Regression for PDF-checked CET question labels and Kaoyan Part B figure slots."""

import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import build_structured_exams as builder
from scripts import build_question_database as database
from scripts.kaoyan_matching_cards import ORDERING_FIXED, ORDERING_PAPERS, TABLE_PAPERS


SOURCES = Path(__file__).resolve().parents[1] / "data/sources"
REFLOW = SOURCES / "english-exams-reflow-latex"
ORIGINAL = SOURCES / "english-exams-web-2026-09-26"

# The original PDF has a separate printed item at each of these physical pages.
MISSING = {
    ("cet4", "2021-12-01", 8): (47,),
    ("cet4", "2021-12-01", 10): (55,),
    ("cet4", "2021-12-03", 6): (47,),
    ("cet6", "2019-12-01", 2): (11, 13),
    ("cet6", "2019-12-01", 3): (15, 18),
    ("cet6", "2019-12-01", 8): (37,),
    ("cet6", "2019-12-01", 11): (51,),
    ("cet6", "2019-12-02", 2): (11, 13),
    ("cet6", "2019-12-02", 3): (15, 18),
    ("cet6", "2020-07-01", 8): (44,),
    ("cet6", "2020-09-01", 2): (11, 13),
    ("cet6", "2020-09-01", 3): (18,),
    ("cet6", "2020-09-01", 8): (36,),
    ("cet6", "2020-09-01", 11): (51,),
    ("cet6", "2020-12-01", 7): (47,),
    ("cet6", "2021-06-02", 8): (54,),
    ("cet6", "2021-12-02", 7): (37,),
    ("cet6", "2021-12-02", 9): (47,),
    ("cet6", "2021-12-02", 11): (55,),
    ("cet6", "2021-12-03", 5): (47,),
}
LISTENING = {
    ("cet6", "2015-06-03", 1): tuple(range(1, 11)),
    ("cet6", "2015-06-03", 2): tuple(range(11, 24)),
    ("cet6", "2015-06-03", 3): (24, 25),
    ("cet6", "2014-12-01", 3): (23, 24, 25),
}
MATCHING = {("cet6", "2020-07-01", 8, 44),
            ("cet6", "2019-12-01", 8, 37),
            ("cet6", "2020-09-01", 8, 36),
            ("cet6", "2021-12-02", 7, 37)}


class EnglishMissingCardTests(unittest.TestCase):
    def test_pdf_verified_fifteen_word_banks(self):
        expected = {
            ("cet6", "2021-06-02", 4): {"J": "overhaul", "K": "permanently", "O": "ultimately"},
            ("cet4", "2021-06-03", 1): {"J": "routinely", "O": "wonder"},
            ("cet6", "2020-09-01", 5): {"L": "realms", "N": "run", "O": "viciously"},
            ("cet6", "2020-09-02", 1): {"G": "leverage", "O": "undoubtedly"},
            ("cet6", "2019-12-03", 2): {"H": "consciousness", "O": "warrant"},
        }
        for (category, stem, page), corrections in expected.items():
            with self.subTest(paper=f"{category}:{stem}", page=page):
                paper = json.loads((REFLOW / category / "papers" / f"{stem}.json").read_text())
                banks = [block for block in paper["pages"][page - 1]["blocks"]
                         if block["type"] == "options" and len(block["items"]) == 15]
                self.assertEqual(len(banks), 1)
                choices = {item["label"]: "".join(run["text"] for run in item["runs"])
                           for item in banks[0]["items"]}
                self.assertEqual(list(choices), list("ABCDEFGHIJKLMNO"))
                for label, word in corrections.items():
                    self.assertEqual(choices[label], word)

    def test_original_sources_and_reflow_boundaries(self):
        self.assertEqual(sum(map(len, MISSING.values())), 25)
        self.assertEqual(sum(map(len, LISTENING.values())), 28)
        source_manifest = json.loads((ORIGINAL / "manifest.json").read_text())
        source_entries = {(row["category"], Path(row["file"]).stem): row
                          for row in source_manifest["papers"]}
        for (category, stem, page), numbers in MISSING.items() | LISTENING.items():
            with self.subTest(paper=f"{category}:{stem}", page=page):
                entry = source_entries[(category, stem)]
                pdf = (SOURCES / "kaoyan-web-2026-09-26" / ".firecrawl" / f"{stem}.pdf"
                       if category == "kaoyan" else ORIGINAL / ".firecrawl" / category / f"{stem}.pdf")
                self.assertEqual(hashlib.sha256(pdf.read_bytes()).hexdigest(),
                                 entry["source_pdf_sha256"])
                paper = json.loads((REFLOW / category / "papers" / f"{stem}.json").read_text())
                blocks = paper["pages"][page - 1]["blocks"]
                found = [int(text.split(".", 1)[0]) for block in blocks
                         if block["type"] == "question"
                         if (text := "".join(run["text"] for run in block["runs"]))
                         and text.split(".", 1)[0].isdigit()]
                for number in numbers:
                    self.assertEqual(found.count(number), 1, (category, stem, page, number))
                if (category, stem, page) in {("cet6", "2020-07-01", 8),
                                              ("cet6", "2021-06-02", 8)}:
                    self.assertTrue(any(block["type"] == "source_line" for block in blocks))

    def test_original_svg_figure_cards_and_targeted_structured_build(self):
        documents = {row["id"]: row for row in
                     json.loads((builder.ROOT / "documents.json").read_text())}
        source_rows = {Path(row["file"]).stem: row for row in
                       json.loads((ORIGINAL / "manifest.json").read_text())["papers"]
                       if row["category"] == "kaoyan"}
        for stem in TABLE_PAPERS | ORDERING_PAPERS:
            source = source_rows[stem]
            pdf = SOURCES / "kaoyan-web-2026-09-26" / ".firecrawl" / f"{stem}.pdf"
            selectable_html = ORIGINAL / "kaoyan" / "papers" / f"{stem}.htm"
            self.assertEqual(hashlib.sha256(pdf.read_bytes()).hexdigest(),
                             source["source_pdf_sha256"])
            self.assertEqual(hashlib.sha256(selectable_html.read_bytes()).hexdigest(),
                             source["htm_sha256"])
        cases = set((category, stem) for category, stem, _ in MISSING | LISTENING)
        cases.update(("kaoyan", stem) for stem in TABLE_PAPERS | ORDERING_PAPERS)
        with tempfile.TemporaryDirectory() as directory, patch.object(builder, "OUT", Path(directory)):
            built = {}
            for category, stem in sorted(cases):
                row = builder.build_one(documents[f"{category}:{stem}"])
                built[(category, stem)] = json.loads((Path(directory) / row["json"]).read_text())
            for (category, stem, page), numbers in MISSING.items() | LISTENING.items():
                paper = built[(category, stem)]
                for number in numbers:
                    matches = [q for q in paper["questions"] if q["recordType"] == "question"
                               and q["number"] == str(number) and str(page) in q["sourcePages"]]
                    self.assertEqual(len(matches), 1, (category, stem, page, number))
                    question = matches[0]
                    labels = [option["label"] for option in question["options"]]
                    if (category, stem, page, number) in MATCHING:
                        self.assertEqual(labels, [])
                    else:
                        self.assertEqual(labels, ["A.", "B.", "C.", "D."],
                                         (category, stem, page, number, labels))
                    self.assertEqual(question["answer"]["status"], "missing")
            # Q15 was already a numbered card, but its four listening choices
            # were trapped in one stem plus three plain paragraphs.
            q15 = next(q for q in built[("cet6", "2020-09-01")]["questions"]
                       if q["number"] == "15")
            self.assertEqual([option["label"] for option in q15["options"]],
                             ["A.", "B.", "C.", "D."])
            for stem in sorted(TABLE_PAPERS | ORDERING_PAPERS):
                paper = built[("kaoyan", stem)]
                questions = [q for q in paper["questions"] if q["recordType"] == "question"
                             and q["number"] in {str(i) for i in range(41, 46)}]
                self.assertEqual(len(questions), 5, stem)
                choice_bank = "ABCDEFGH" if stem == "2025-01" else "ABCDEFG"
                expected = [letter for letter in choice_bank
                            if letter not in ORDERING_FIXED.get(stem, ())]
                for question in questions:
                    self.assertEqual([o["label"][0] for o in question["options"]], expected)
                    self.assertEqual(question["context"]["fixedLetters"],
                                     list(ORDERING_FIXED.get(stem, ())))
                    self.assertEqual(question["answer"]["status"], "missing")
                    self.assertTrue(any(b["id"] in question["sourceBlocks"] and b["role"] == "figure"
                                        and b["page"] == "12" for b in paper["blocks"]))
                    self.assertTrue(all(option["text"].strip() for option in question["options"]))
                    labels = [option["label"][0] for option in question["options"]]
                    self.assertTrue(all(database.OPTION_LABEL.fullmatch(label + ".")
                                        for label in labels))
                    # A hypothetical sourced key can select an unplaced
                    # paragraph; a diagram's prefilled example cannot be
                    # mistaken for an answer to any blank.
                    with patch.dict(question["answer"],
                                    {"status": "explicit", "value": labels[0]}):
                        self.assertEqual(database._choice_letters(question, labels),
                                         {labels[0]})
                    if stem in ORDERING_FIXED:
                        with patch.dict(question["answer"],
                                        {"status": "explicit",
                                         "value": ORDERING_FIXED[stem][0]}):
                            self.assertIsNone(database._choice_letters(question, labels))


if __name__ == "__main__":
    unittest.main()
