"""Image-only Kaoyan English II final pages must retain Writing Part B."""

import json
from pathlib import Path
import sys
import unittest

import fitz


ROOT = Path(__file__).resolve().parents[1]
REFLOW = ROOT / "data/sources/english-exams-reflow-latex"
sys.path.insert(0, str(REFLOW / "tools"))
sys.path.insert(0, str(REFLOW.parent / "layout-tools"))

from recover_image_writing import IMAGE_WRITING_PART_B, recover_image_writing  # noqa: E402
from repair_archive import source_pdf  # noqa: E402


class ImageWritingRecoveryTests(unittest.TestCase):
    def test_four_source_image_pages_recover_part_b_and_original_chart(self):
        manifest = json.loads((REFLOW.parent / "english-exams-web-2026-09-26/manifest.json").read_text())
        for stem, spec in IMAGE_WRITING_PART_B.items():
            with self.subTest(stem=stem):
                entry = next(p for p in manifest["papers"] if p["file"] == f"kaoyan/papers/{stem}.htm")
                with fitz.open(source_pdf(entry)) as document:
                    page = document[13]
                    self.assertEqual(page.get_text().strip(), "")
                    self.assertEqual(len(page.get_images(full=True)), 1)
                    blocks = []
                    recover_image_writing("kaoyan", stem, 14, blocks, page)
                    self.assertEqual([block["type"] for block in blocks[:2]], ["heading", "question"])
                    self.assertEqual(blocks[1]["runs"][0]["text"], "48. Directions:")
                    self.assertEqual(
                        [block["runs"][0]["text"] for block in blocks[2:-1]],
                        [text for _, text in spec["instructions"]],
                    )
                    self.assertEqual(blocks[-1], {"type": "figure", "bbox": list(spec["figure_bbox"])})
                    self.assertGreater(page.get_pixmap(clip=fitz.Rect(spec["figure_bbox"])).width, 100)

    def test_recovery_is_limited_to_verified_page_and_blank_extraction(self):
        blocks = [{"type": "paragraph", "runs": []}]
        recover_image_writing("kaoyan", "2011-02", 13, blocks, None)
        recover_image_writing("kaoyan", "2013-02", 14, blocks, None)
        self.assertEqual(len(blocks), 1)


if __name__ == "__main__":
    unittest.main()
