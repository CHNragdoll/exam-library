"""Regressions for source-PDF heading and option geometry."""

import json
import unittest

import fitz

import build


def text(block):
    return "".join(run["text"] for run in block.get("runs", []))


class HeadingAndOptionExtractionTests(unittest.TestCase):
    def test_centered_reading_title_is_separate_from_directions(self):
        manifest = json.loads(
            (build.ROOT.parent / "english-exams-web-2026-09-26/manifest.json").read_text()
        )
        entry = next(
            paper for paper in manifest["papers"]
            if paper["file"] == "cet6/papers/2021-12-03.htm"
        )
        with fitz.open(build.source_pdf(entry)) as document:
            page = document[0]
            blocks = build.extract(page, unknown_glyphs=build.source_chars(page))["blocks"]

        title = "Why facts don't change our minds"
        self.assertEqual(
            [block["type"] for block in blocks if text(block) == title],
            ["heading"],
        )
        directions = next(block for block in blocks if text(block).startswith("Directions: In this section"))
        self.assertTrue(text(directions).endswith("Answer sheet 2."))
        self.assertNotIn(title, text(directions))
        paragraph = next(block for block in blocks if text(block).startswith("A) The economist"))
        self.assertEqual(paragraph["type"], "paragraph")
        self.assertIn("J. K. Galbraith once wrote", text(paragraph))
        self.assertIn('busy with the proof."', text(paragraph))
        self.assertFalse(any(
            item["label"] in {"J", "K"}
            for block in blocks for item in block.get("items", [])
        ))

    def test_same_row_option_bank_remains_four_options(self):
        with fitz.open() as document:
            page = document.new_page(width=600, height=300)
            page.insert_text((50, 70), "1. Choose a word.", fontsize=11)
            for x, choice in ((70, "A. Still"), (180, "B. Therefore"),
                              (320, "C. Afterward"), (470, "D. Instead")):
                page.insert_text((x, 95), choice, fontsize=11)
            blocks = build.extract(page)["blocks"]
        option_blocks = [block for block in blocks if block["type"] == "options"]
        self.assertEqual(len(option_blocks), 1)
        self.assertEqual(
            [(item["label"], text(item)) for item in option_blocks[0]["items"]],
            [("A", "Still"), ("B", "Therefore"), ("C", "Afterward"), ("D", "Instead")],
        )


if __name__ == "__main__":
    unittest.main()
