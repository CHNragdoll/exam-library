"""Stable raw-source anchors for reflow answer-choice translations."""

import importlib.util
from pathlib import Path
import unittest

from bs4 import BeautifulSoup


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("english_reflow_build", HERE / "build.py")
BUILD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUILD)


class OptionAnchorTests(unittest.TestCase):
    def test_options_keep_visible_labels_and_expose_raw_item_positions(self):
        block = {"type": "options", "items": [
            {"label": "A", "runs": [{"text": "First choice.", "flags": [False, False, False]}]},
            {"label": "B", "runs": [{"text": "Second choice.", "flags": [False, False, False]}]},
        ]}
        soup = BeautifulSoup(BUILD.html_options_block(block, "b-2-5"), "html.parser")
        group = soup.select_one("ul.options")
        self.assertEqual(group["data-source-block-id"], "b-2-5")
        self.assertEqual([item["data-source-option-index"] for item in group.select("li")],
                         ["0", "1"])
        self.assertEqual([item["data-source-block-id"] for item in group.select("li")],
                         ["b-2-5", "b-2-5"])
        self.assertEqual(group.get_text(" ", strip=True),
                         "A. First choice. B. Second choice.")

    def test_choice_row_exposes_same_positions_without_reordering(self):
        block = {"type": "choice_row", "runs": [{"text": "3.", "flags": [False, False, False]}], "items": [
            {"label": "A", "runs": [{"text": "First row choice.", "flags": [False, False, False]}]},
            {"label": "B", "runs": [{"text": "Second row choice.", "flags": [False, False, False]}]},
        ]}
        soup = BeautifulSoup(BUILD.html_choice_row_block(block, "b-3-2"), "html.parser")
        self.assertEqual(soup.select_one(".choice-scroll")["data-source-block-id"], "b-3-2")
        self.assertEqual([item["data-source-option-index"]
                          for item in soup.select(".choice-item")], ["0", "1"])
        self.assertEqual([item["data-source-block-id"]
                          for item in soup.select(".choice-item")], ["b-3-2", "b-3-2"])
        self.assertEqual([item.get_text(" ", strip=True)
                          for item in soup.select(".choice-item")],
                         ["A. First row choice.", "B. Second row choice."])


if __name__ == "__main__":
    unittest.main()
