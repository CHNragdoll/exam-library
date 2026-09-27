"""Source and geometry checks for the three verified combined option figures."""

import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import urljoin

from scripts import build_structured_exams as builder


TARGETS = (
    ("cs408:2009-complete", "4", "B"),
    ("cs408:2017-questions", "8", None),
    ("math3:2009-questions", "4", "D"),
)


class FigureOptionTests(unittest.TestCase):
    def test_target_figures_produce_source_backed_choices_without_rewriting_assets(self):
        documents = json.loads((builder.ROOT / "documents.json").read_text(encoding="utf-8"))
        by_id = {document["id"]: document for document in documents}
        with tempfile.TemporaryDirectory() as directory, patch.object(builder, "OUT", Path(directory).resolve()):
            for document_id, number, _ in TARGETS:
                with self.subTest(document_id=document_id):
                    document = by_id[document_id]
                    original = builder.source_path(document)
                    mapping = builder.FIGURE_OPTION_REGIONS[(document_id, number)]
                    asset = original.parent / "../assets/figures" / mapping["asset"]
                    before = hashlib.sha256(asset.read_bytes()).digest()
                    row = builder.build_one(document)
                    paper_path = Path(directory).resolve() / row["json"]
                    paper = json.loads(paper_path.read_text(encoding="utf-8"))
                    question = next(q for q in paper["questions"] if q["number"] == number)
                    self.assertEqual([o["label"] for o in question["options"]],
                                     ["A.", "B.", "C.", "D."])
                    self.assertEqual([o["sourceOrder"] for o in question["options"]], [1, 2, 3, 4])
                    self.assertEqual(question["status"], "complete")
                    self.assertEqual(hashlib.sha256(asset.read_bytes()).digest(), before)
                    self.assertEqual([tuple(o["image"]["crop"][key] for key in
                                            ("x", "y", "width", "height"))
                                      for o in question["options"]], list(mapping["regions"]))
                    for option in question["options"]:
                        image = option["image"]
                        self.assertEqual((paper_path.parent / image["src"]).resolve(), asset.resolve())
                        self.assertTrue((paper_path.parent / image["src"]).is_file())
                        self.assertIn(image["sourceBlockId"], question["sourceBlocks"])
                    published_json = builder.ROOT / "structured" / row["json"]
                    published_src = builder.rel(asset.resolve(), published_json)
                    reader_url = f"/exam-library/structured/{row['reader']}"
                    browser_path = urljoin(reader_url, published_src)
                    self.assertTrue((builder.ROOT.parent / browser_path.lstrip("/")).is_file())
                    figure = next(b for b in paper["blocks"] if b["id"] == question["options"][0]["image"]["sourceBlockId"])
                    self.assertEqual(figure["role"], "figure")
                    self.assertIn(mapping["asset"], figure["contentHtml"])
                    self.assertEqual(sum(q["number"] == number and len(q["options"]) == 4
                                         for q in paper["questions"]), 1)


if __name__ == "__main__":
    unittest.main()
