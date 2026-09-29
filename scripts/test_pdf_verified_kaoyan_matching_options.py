"""Original-PDF and source drift checks for Kaoyan Part B option anchors."""

from __future__ import annotations

import copy
import json
import unittest

import fitz

from scripts.pdf_verified_kaoyan_matching_options import (
    ROOT,
    _fixture,
    verified_matching_option_anchors as _verified_matching_option_anchors,
)


STRUCTURED = ROOT / "data/sources/exam-library/structured/papers/kaoyan"
REFLOW = ROOT / "data/sources/english-exams-reflow-latex/kaoyan/papers"


def verified_matching_option_anchors(paper, raw, pdf_sha256):
    return _verified_matching_option_anchors(
        paper, raw, pdf_sha256, allow_missing_pdf=True)


def sources(paper_id: str) -> tuple[dict, dict]:
    name = paper_id.split(":", 1)[1]
    paper = json.loads((STRUCTURED / f"{name}.json").read_text(encoding="utf-8"))
    raw = json.loads((REFLOW / f"{name}.json").read_text(encoding="utf-8"))
    return paper, raw


class PdfVerifiedMatchingOptionTests(unittest.TestCase):
    def test_all_62_unique_choices_appear_once_on_cited_pdf_page(self):
        fixture = _fixture()
        if any(not (ROOT / entry["sourcePdfPath"]).is_file() for entry in fixture.values()):
            self.skipTest("original PDFs are absent from this checkout")
        self.assertEqual(len(fixture), 12)
        self.assertEqual(sum(len(p["choices"]) for p in fixture.values()), 62)
        for paper_id, entry in fixture.items():
            with self.subTest(paper_id=paper_id):
                doc = fitz.open(ROOT / entry["sourcePdfPath"])
                for label, choice in entry["choices"].items():
                    with self.subTest(choice=label):
                        page = doc[choice["pdfPage"] - 1]
                        printed = "".join(page.get_text().split())
                        exact = label + "." + "".join(choice["text"].split())
                        self.assertEqual(printed.count(exact), 1)

    def test_all_310_repeated_option_anchors_and_source_immutability(self):
        counts = {}
        for paper_id, entry in _fixture().items():
            with self.subTest(paper_id=paper_id):
                paper, raw = sources(paper_id)
                before = copy.deepcopy(raw)
                anchors = verified_matching_option_anchors(
                    paper, raw, entry["sourcePdfSha256"]
                )
                self.assertEqual(raw, before)
                self.assertEqual(len(anchors), 5 * len(entry["choices"]))
                self.assertEqual(
                    {a.source_pdf_page for a in anchors.values()},
                    {o["pdfPage"] for o in entry["choices"].values()},
                )
                counts[entry["kind"]] = counts.get(entry["kind"], 0) + len(anchors)
        self.assertEqual(counts, {"figure_bank": 280, "passage_option": 30})

    def test_two_structured_figure_ids_are_known_to_point_at_prose(self):
        fixture = _fixture()
        for paper_id, expected in (
            ("kaoyan:2012-02", ("b-12-3", "b-12-4")),
            ("kaoyan:2019-02", ("b-12-7", "b-12-8")),
        ):
            with self.subTest(paper_id=paper_id):
                entry = fixture[paper_id]
                self.assertEqual(
                    (entry["contextFigureBlockId"], entry["actualFigureBlockId"]),
                    expected,
                )
                _, raw = sources(paper_id)
                _, page, index = entry["actualFigureBlockId"].split("-")
                self.assertEqual(raw["pages"][int(page)-1]["blocks"][int(index)-1]["type"], "figure")

    def test_2005_split_option_joins_without_changing_raw(self):
        paper_id = "kaoyan:2005-01"
        paper, raw = sources(paper_id)
        anchors = verified_matching_option_anchors(
            paper, raw, _fixture()[paper_id]["sourcePdfSha256"]
        )
        self.assertEqual(len(anchors), 5)
        for anchor in anchors.values():
            self.assertEqual(anchor.reflow_block_ids, ("b-12-3", "b-12-4"))
            self.assertIn("14.3 percent to 26.8 percent!", anchor.derived_passage_text)

    def test_pdf_hash_mismatch_fails_closed(self):
        paper, raw = sources("kaoyan:2026-02")
        with self.assertRaisesRegex(ValueError, "reviewed original PDF changed"):
            verified_matching_option_anchors(paper, raw, "0" * 64)

    def test_raw_figure_change_fails_closed(self):
        paper_id = "kaoyan:2026-02"
        paper, raw = sources(paper_id)
        raw["pages"][11]["blocks"][3]["type"] = "paragraph"
        with self.assertRaisesRegex(ValueError, "reviewed table figure changed"):
            verified_matching_option_anchors(
                paper, raw, _fixture()[paper_id]["sourcePdfSha256"]
            )

    def test_structured_option_change_fails_closed(self):
        paper_id = "kaoyan:2026-02"
        paper, raw = sources(paper_id)
        q = next(q for q in paper["questions"] if q["id"] == "q-43-1")
        q["options"][0]["text"] += " Changed"
        with self.assertRaisesRegex(ValueError, "structured choice A changed"):
            verified_matching_option_anchors(
                paper, raw, _fixture()[paper_id]["sourcePdfSha256"]
            )

    def test_split_passage_change_fails_closed(self):
        paper_id = "kaoyan:2005-01"
        paper, raw = sources(paper_id)
        raw["pages"][11]["blocks"][3]["runs"][0]["text"] += "?"
        with self.assertRaisesRegex(ValueError, "reviewed passage option changed"):
            verified_matching_option_anchors(
                paper, raw, _fixture()[paper_id]["sourcePdfSha256"]
            )

    def test_unlisted_paper_is_untouched(self):
        self.assertEqual(verified_matching_option_anchors({"id": "kaoyan:2025-01"}, {}, ""), {})


if __name__ == "__main__":
    unittest.main()
