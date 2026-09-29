"""Source-PDF regression checks for 47 CET options with unusual raw layout."""

from __future__ import annotations

import copy
import json
import unittest

import fitz

from scripts.pdf_verified_cet_missing_options import (
    ROOT,
    _fixture,
    verified_cet_missing_option_anchors as _verified_cet_missing_option_anchors,
)


STRUCTURED = ROOT / "data/sources/exam-library/structured/papers"
REFLOW = ROOT / "data/sources/english-exams-reflow-latex"


def verified_cet_missing_option_anchors(paper, raw, pdf_sha256):
    # CI checks committed hashes and source anchors; local runs also hash any
    # original PDF that is present.
    return _verified_cet_missing_option_anchors(
        paper, raw, pdf_sha256, allow_missing_pdf=True)


def sources(paper_id: str) -> tuple[dict, dict]:
    suite, name = paper_id.split(":", 1)
    paper = json.loads((STRUCTURED / suite / f"{name}.json").read_text(encoding="utf-8"))
    raw = json.loads((REFLOW / suite / "papers" / f"{name}.json").read_text(encoding="utf-8"))
    return paper, raw


class PdfVerifiedCetMissingOptionsTests(unittest.TestCase):
    def test_47_option_texts_each_have_unique_printed_pdf_anchor(self):
        entries = _fixture()
        if any(not (ROOT / entry["sourcePdfPath"]).is_file() for entry in entries.values()):
            self.skipTest("original PDFs are absent from this checkout")
        self.assertEqual(len(entries), 17)
        self.assertEqual(sum(len(e["options"]) for e in entries.values()), 47)
        for paper_id, entry in entries.items():
            with self.subTest(paper_id=paper_id):
                doc = fitz.open(ROOT / entry["sourcePdfPath"])
                for option_id, choice in entry["options"].items():
                    with self.subTest(option_id=option_id):
                        printed = "".join(doc[choice["pdfPage"] - 1].get_text().split())
                        exact = choice["pdfPrintedPrefix"] + "".join(choice["sourceText"].split())
                        self.assertEqual(printed.count(exact), 1)

    def test_all_47_verified_anchors_leave_raw_source_unchanged(self):
        count = 0
        for paper_id, entry in _fixture().items():
            with self.subTest(paper_id=paper_id):
                paper, raw = sources(paper_id)
                original = copy.deepcopy(raw)
                anchors = verified_cet_missing_option_anchors(
                    paper, raw, entry["sourcePdfSha256"]
                )
                self.assertEqual(raw, original)
                self.assertEqual(set(anchors), set(entry["options"]))
                count += len(anchors)
        self.assertEqual(count, 47)

    def test_2014_option_a_is_printed_on_preceding_page(self):
        paper_id = "cet6:2014-12-01"
        paper, raw = sources(paper_id)
        anchor = verified_cet_missing_option_anchors(
            paper, raw, _fixture()[paper_id]["sourcePdfSha256"]
        )[f"{paper_id}:q-22-1:A"]
        self.assertEqual(anchor.reflow_block_id, "b-2-33")
        self.assertIsNone(anchor.reflow_option_index)
        self.assertEqual(anchor.source_pdf_page, 2)
        self.assertEqual(anchor.structured_source_block_ids, ("b-2-33", "b-3-1"))

    def test_2018_cet6_normalized_raw_values_match_all_30_printed_choices(self):
        for paper_id in ("cet6:2018-06-02", "cet6:2018-06-03"):
            with self.subTest(paper_id=paper_id):
                paper, raw = sources(paper_id)
                entry = _fixture()[paper_id]
                anchors = verified_cet_missing_option_anchors(
                    paper, raw, entry["sourcePdfSha256"]
                )
                self.assertEqual(len(anchors), 15)
                self.assertEqual(
                    {a.source_pdf_page for a in anchors.values()},
                    {choice["pdfPage"] for choice in entry["options"].values()},
                )
                for option_id, anchor in anchors.items():
                    choice = entry["options"][option_id]
                    self.assertEqual(choice["rawItemText"], choice["sourceText"])
                    self.assertEqual(choice["wordSpan"], [0, len(choice["sourceText"])])
                    self.assertEqual(anchor.source_text, choice["sourceText"])

    def test_2020_december_corrected_and_prior_word_bank_shapes(self):
        paper_id = "cet4:2020-12-01"
        paper, raw = sources(paper_id)
        entry = _fixture()[paper_id]
        option_id = f"{paper_id}:word-bank:J"
        corrected = verified_cet_missing_option_anchors(
            paper, raw, entry["sourcePdfSha256"]
        )[option_id]
        self.assertEqual(corrected.source_text, "records")

        prior = copy.deepcopy(raw)
        block = prior["pages"][3]["blocks"][3]
        item = block["items"][entry["options"][option_id]["rawItemIndex"]]
        item["runs"] = [{"text": "records 0) watching"}]
        self.assertEqual(block["items"].pop()["label"], "O")
        old = verified_cet_missing_option_anchors(
            paper, prior, entry["sourcePdfSha256"]
        )[option_id]
        self.assertEqual(old.source_text, "records")

    def test_pdf_mismatch_fails_closed(self):
        paper, raw = sources("cet6:2014-12-01")
        with self.assertRaisesRegex(ValueError, "reviewed CET original PDF changed"):
            verified_cet_missing_option_anchors(paper, raw, "0" * 64)

    def test_tampered_merged_item_fails_closed(self):
        paper_id = "cet4:2022-06-01"
        paper, raw = sources(paper_id)
        raw["pages"][4]["blocks"][0]["items"][6]["runs"][0]["text"] += "!"
        with self.assertRaisesRegex(ValueError, "reviewed CET word-bank shape changed"):
            verified_cet_missing_option_anchors(
                paper, raw, _fixture()[paper_id]["sourcePdfSha256"]
            )

    def test_structured_word_change_fails_closed(self):
        paper_id = "cet6:2018-06-02"
        paper, raw = sources(paper_id)
        item_id = f"{paper_id}:word-bank:A"
        for question in paper["questions"]:
            for item in (question.get("context") or {}).get("wordBank", []):
                if item.get("id") == item_id:
                    item["text"] = "different"
        with self.assertRaisesRegex(ValueError, "structured CET word-bank item changed"):
            verified_cet_missing_option_anchors(
                paper, raw, _fixture()[paper_id]["sourcePdfSha256"]
            )

    def test_unlisted_paper_has_no_special_anchors(self):
        self.assertEqual(verified_cet_missing_option_anchors({"id": "cet4:2025-06-01"}, {}, ""), {})


if __name__ == "__main__":
    unittest.main()
