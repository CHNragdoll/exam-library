"""Regression checks for political-paper continuation and scan artifacts."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from bs4 import BeautifulSoup

from scripts import build_structured_exams as builder


class PoliticsPresentationTests(unittest.TestCase):
    def test_multiple_choice_answer_letters_are_not_truncated(self):
        for source, expected in (
            ("【答案】ABC", "ABC"),
            ("【参考答案】BCD", "BCD"),
            ("【答案】A、C、D", "ACD"),
            ("【答案】B", "B"),
        ):
            match = builder.ANSWER_RE.search(source)
            self.assertIsNotNone(match, source)
            self.assertEqual(builder.normalize_choice_answer(match.group(1)), expected)

    @classmethod
    def setUpClass(cls):
        cls.doc = next(doc for doc in json.loads((builder.ROOT / "documents.json").read_text())
                       if doc["id"] == "politics:2023-questions")

    def test_2023_preview_and_json_keep_source_but_clean_display(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(builder, "OUT", Path(directory)):
            row = builder.build_one(self.doc)
            paper = json.loads((Path(directory) / row["json"]).read_text())
            preview = BeautifulSoup((Path(directory) / row["reader"]).read_text(), "html.parser")

        self.assertEqual(len(paper["questions"]), 38)
        self.assertEqual({key: paper["audit"][key] for key in (
            "politicsContinuations", "politicsPageArtifacts", "politicsSubquestions", "politicsVerifiedCorrections",
        )}, {"politicsContinuations": 8, "politicsPageArtifacts": 2,
             "politicsSubquestions": 10, "politicsVerifiedCorrections": 2})
        blocks = {block["id"]: block for block in paper["blocks"]}
        self.assertIn("二。二O年", blocks["b-7-1"]["text"])
        self.assertIn("二〇二〇年", blocks["b-7-1"]["presentation"]["displayText"])
        self.assertEqual(blocks["b-7-1"]["presentation"]["corrections"][0]["evidence"],
                         {"kind": "original_pdf_visual", "sourceDocumentId": "politics:2023-questions",
                          "sourcePageIndex": 7})
        self.assertIn("二〇二〇年", preview.find(id="b-7-1").get_text())
        self.assertNotIn("二。二O年", preview.find(id="b-7-1").get_text())
        self.assertIn("-8 -", blocks["b-8-2"]["text"])
        self.assertNotIn("-8 -", preview.find(id="b-8-2").get_text())
        self.assertTrue(preview.find(id="b-4-1").has_attr("hidden"))
        self.assertNotIn("续", preview.find(id="b-9-1").get_text())
        self.assertEqual(len(preview.find(id="b-8-1").select("br.politics-subquestion-break")), 1)
        self.assertEqual(len(preview.find(id="b-10-1").select("br.politics-subquestion-break")), 2)

        q18 = next(q for q in paper["questions"] if q["number"] == "18")
        self.assertEqual([option["label"] for option in q18["options"]], ["A.", "B.", "C.", "D."])
        self.assertEqual(q18["options"][0]["text"], "评价客体没有自身固有的本质和特性")
        self.assertIn("-3 •", q18["options"][0]["sourceText"])
        self.assertEqual(q18["sourceBlocks"], ["b-3-14", "b-3-15", "b-4-1", "b-4-2"])
        for number in range(34, 39):
            q = next(q for q in paper["questions"] if q["number"] == str(number))
            self.assertEqual([part["number"] for part in q["subquestions"]], ["1", "2"])
            self.assertTrue(set(part["sourceBlockId"] for part in q["subquestions"]).issubset(q["sourceBlocks"]))

    def test_artifact_detection_requires_matching_page_and_question(self):
        doc = self.doc
        self.assertIsNone(builder.politics_presentation(doc, "题干 -8 -", 7, "question", "other", "36"))
        self.assertIsNone(builder.politics_presentation(doc, "第36题（续）：正文", 9, "content", "other", "35"))
        self.assertIsNone(builder.politics_presentation(doc, "2018-2022 年", 8, "content", "other", "35"))

    def test_corpus_audit_covers_all_politics_question_years(self):
        papers = sorted((builder.ROOT.parent / "politics-latex-2003-2023/papers").glob("*-questions.htm"))
        self.assertEqual(len(papers), 21)
        continuations = artifacts = 0
        for paper in papers:
            soup = BeautifulSoup(paper.read_text(), "html.parser")
            for page_index, page in enumerate(soup.select("main [data-source-page]"), 1):
                for child in page.find_all(recursive=False):
                    value = builder.plain(child)
                    continuations += bool(builder.POLITICS_CONTINUATION_RE.match(value))
                    marker = builder.POLITICS_PAGE_ARTIFACT_RE.search(value)
                    artifacts += bool(marker and int(marker["number"]) == page_index)
        self.assertEqual((continuations, artifacts), (8, 2))


if __name__ == "__main__":
    unittest.main()
