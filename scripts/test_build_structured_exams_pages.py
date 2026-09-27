"""Use physical source pages, not inline source-position annotations."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from bs4 import BeautifulSoup

from scripts import build_structured_exams as builder


class PhysicalPageTests(unittest.TestCase):
    def test_cet6_2015_12_02_has_nine_pages_and_stable_block_ids(self):
        doc = next(item for item in json.loads((builder.ROOT / "documents.json").read_text())
                   if item["id"] == "cet6:2015-12-02")
        source = BeautifulSoup(builder.source_path(doc).read_text(), "html.parser")
        main = source.select_one("main")
        pages = main.select(":scope > section[data-source-page]")
        self.assertEqual(len(pages), 9)
        self.assertEqual(len(main.select("[data-source-page]")), 12)

        with tempfile.TemporaryDirectory() as directory, patch.object(builder, "OUT", Path(directory)):
            row = builder.build_one(doc)
            paper = json.loads((Path(directory) / row["json"]).read_text())
            rendered = BeautifulSoup((Path(directory) / row["reader"]).read_text(), "html.parser")

        self.assertEqual(paper["pages"], 9)
        self.assertEqual(len(paper["blocks"]), sum(len(page.find_all(recursive=False)) for page in pages))
        self.assertEqual(len(rendered.select(".source-block")), len(paper["blocks"]))
        for block in paper["blocks"]:
            page_index, block_index = block["sourcePageIndex"], block["sourceBlockIndex"]
            self.assertEqual(block["id"], f"b-{page_index}-{block_index}")
            self.assertEqual(block["page"], pages[page_index - 1]["data-source-page"])
            self.assertEqual(block["text"], builder.plain(pages[page_index - 1].find_all(recursive=False)[block_index - 1]))
        self.assertTrue(all(block["sourcePageIndex"] <= 9 for block in paper["blocks"]))


if __name__ == "__main__":
    unittest.main()
