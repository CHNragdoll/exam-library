"""Regression checks for political-paper continuation and page furniture."""

import json
from pathlib import Path
import re
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

    def test_2023_preview_and_json_keep_pdf_content_without_page_footers(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(builder, "OUT", Path(directory)):
            row = builder.build_one(self.doc)
            paper = json.loads((Path(directory) / row["json"]).read_text())
            preview = BeautifulSoup((Path(directory) / row["reader"]).read_text(), "html.parser")

        self.assertEqual(len(paper["questions"]), 38)
        self.assertEqual({key: paper["audit"][key] for key in (
            "politicsContinuations", "politicsPageArtifacts", "politicsSubquestions", "politicsVerifiedCorrections",
        )}, {"politicsContinuations": 8, "politicsPageArtifacts": 0,
             "politicsSubquestions": 10, "politicsVerifiedCorrections": 2})
        blocks = {block["id"]: block for block in paper["blocks"]}
        self.assertIn("二。二O年", blocks["b-7-1"]["text"])
        self.assertIn("二〇二〇年", blocks["b-7-1"]["presentation"]["displayText"])
        self.assertEqual(blocks["b-7-1"]["presentation"]["corrections"][0]["evidence"],
                         {"kind": "original_pdf_visual", "sourceDocumentId": "politics:2023-questions",
                          "sourcePageIndex": 7})
        self.assertIn("二〇二〇年", preview.find(id="b-7-1").get_text())
        self.assertNotIn("二。二O年", preview.find(id="b-7-1").get_text())
        self.assertTrue(blocks["b-8-2"]["text"].endswith("摘自《邓小平文选》第二卷"))
        self.assertNotIn("-8 -", blocks["b-8-2"]["text"])
        self.assertNotIn("-8 -", preview.find(id="b-8-2").get_text())
        self.assertTrue(preview.find(id="b-4-1").has_attr("hidden"))
        self.assertNotIn("续", preview.find(id="b-9-1").get_text())
        for block_id in ("b-8-1", "b-10-1", "b-11-1"):
            prompts = [node.get_text(" ", strip=True) for node in preview.find(id=block_id).select("p")
                       if node.get_text(" ", strip=True).startswith(("(1)", "(2)", "（1）", "（2）"))]
            self.assertEqual(len(prompts), 2, block_id)
            self.assertTrue(prompts[0].startswith(("(1)", "（1）")), block_id)
            self.assertTrue(prompts[1].startswith(("(2)", "（2）")), block_id)
        material = [node.get_text(" ", strip=True) for node in preview.find(id="b-11-1").select("p")]
        start = material.index("材料2")
        self.assertEqual([part[:9] for part in material[start + 1:start + 5]],
                         ["当前世界经济面临衰", "作为在全球范围内以", "中国提出的全球发展", "针对人类发展面临的"])
        for amount in ("34.6万个", "2.8%", "9.7%", "2.9%"):
            self.assertIn(amount, material[start + 2])
            self.assertIn(amount, blocks["b-11-1"]["text"])
        self.assertNotIn("34. 6", blocks["b-11-1"]["text"])

        q18 = next(q for q in paper["questions"] if q["number"] == "18")
        self.assertEqual([option["label"] for option in q18["options"]], ["A.", "B.", "C.", "D."])
        self.assertEqual(q18["options"][0]["text"], "评价客体没有自身固有的本质和特性")
        self.assertEqual(blocks["b-3-15"]["text"], "A. 评价客体没有自身固有的本质和特性")
        self.assertNotIn("-3 •", preview.find(id="b-3-15").get_text())
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
        self.assertEqual((continuations, artifacts), (8, 0))

    def test_pdf_paragraph_boundaries_preserve_source_text(self):
        source = builder.ROOT.parent / "politics-latex-2003-2023/source"
        papers = sorted(source.glob("20??.json"))
        self.assertEqual(len(papers), 21)
        groups = breaks = 0
        for file in papers:
            for page in json.loads(file.read_text())["pages"]:
                if page["source_id"] != f"{file.stem}-questions":
                    continue
                for block in page["blocks"]:
                    parts = block.get("paragraphs")
                    if not parts:
                        continue
                    self.assertGreater(len(parts), 1)
                    self.assertEqual(re.sub(r"\s+", "", "".join(parts)),
                                     re.sub(r"\s+", "", block["text"]),
                                     (file.name, page["source_page"]))
                    groups += 1
                    breaks += len(parts) - 1
        self.assertGreaterEqual(groups, 100)
        self.assertGreaterEqual(breaks, 250)

    def test_2003_question_29_keeps_all_five_options_across_pdf_pages(self):
        doc = next(doc for doc in json.loads((builder.ROOT / "documents.json").read_text())
                   if doc["id"] == "politics:2003-questions")
        with tempfile.TemporaryDirectory() as directory, patch.object(builder, "OUT", Path(directory)):
            row = builder.build_one(doc)
            paper = json.loads((Path(directory) / row["json"]).read_text())
        question = next(q for q in paper["questions"] if q["number"] == "29")
        self.assertEqual(question["sourcePages"], ["3", "4"])
        self.assertEqual([option["label"] for option in question["options"]],
                         ["A.", "B.", "C.", "D.", "E."])
        self.assertEqual(question["status"], "complete")

    def test_pdf_continuation_pages_are_not_empty_in_reflow(self):
        source = builder.ROOT.parent / "politics-latex-2003-2023/source"
        cases = ((2015, 10, "十月十五日丁祭过后的第二天"),
                 (2017, 13, "共抵彼岸"))
        for year, page_number, first_line in cases:
            paper = json.loads((source / f"{year}.json").read_text())
            page = next(page for page in paper["pages"]
                        if page["source_id"] == f"{year}-questions"
                        and page["source_page"] == page_number)
            self.assertTrue(page["blocks"], (year, page_number))
            self.assertTrue(page["blocks"][0]["text"].startswith(first_line))
            html = builder.ROOT.parent / f"politics-latex-2003-2023/papers/{year}-questions.htm"
            preview = BeautifulSoup(html.read_text(), "html.parser")
            page_node = preview.select_one(f'main > section[data-source-page="{page_number}"]')
            self.assertIn(first_line, page_node.get_text())

    def test_reflow_hides_only_synthetic_continuation_labels(self):
        source = builder.ROOT.parent / "politics-latex-2003-2023"
        raw = json.loads((source / "source/2023.json").read_text())
        self.assertTrue(any("第38题（续）" in block.get("text", "")
                            for page in raw["pages"] if page["source_id"] == "2023-questions"
                            for block in page["blocks"]))
        reader = BeautifulSoup((source / "papers/2023-questions.htm").read_text(), "html.parser")
        main = reader.select_one("main.paper")
        self.assertEqual(len(main.select(".source-continuation-label[hidden]")), 8)
        for hidden in main.select("[hidden]"):
            hidden.decompose()
        body = main.get_text(" ", strip=True)
        self.assertNotRegex(body, r"第\s*\d+\s*题\s*[（(]续[）)]")
        self.assertIn("当前世界经济面临衰退风险", body)
        self.assertNotRegex((source / "tex/2023-questions.tex").read_text(),
                            r"第\s*\d+\s*题\s*[（(]续[）)]")

    def test_scanned_continuation_pages_keep_their_pdf_page_ownership(self):
        docs = {doc["id"]: doc for doc in json.loads((builder.ROOT / "documents.json").read_text())}
        with tempfile.TemporaryDirectory() as directory, patch.object(builder, "OUT", Path(directory)):
            for doc_id, expected in (
                ("politics:2022-questions", {
                    2: "C. 监事会", 3: "C. 推进社会主义", 5: "少有两个选项", 6: "A. 社会心态",
                    8: "的转折点", 10: "维、居安思危", 11: "的重大历史关头",
                    12: "答题思路:", 13: "是一个主题", 14: "件更为艰苦", 16: "世界到推动构建",
                }),
                ("politics:2023-answers", {14: "及什么是以人民为中心的发展思想"}),
            ):
                row = builder.build_one(docs[doc_id])
                paper = json.loads((Path(directory) / row["json"]).read_text())
                reader = BeautifulSoup((Path(directory) / row["reader"]).read_text(), "html.parser")
                for page_number, page_start in expected.items():
                    blocks = [block for block in paper["blocks"] if block["sourcePageIndex"] == page_number]
                    self.assertTrue(blocks, (doc_id, page_number))
                    self.assertTrue(blocks[0]["text"].startswith(page_start), (doc_id, page_number))
                    rendered_block = reader.find(id=blocks[0]["id"])
                    if doc_id == "politics:2022-questions" and page_number == 12:
                        self.assertTrue(rendered_block.has_attr("hidden"))
                        self.assertEqual(rendered_block.get_text(strip=True), "")
                    else:
                        self.assertIn("".join(page_start.split()),
                                      "".join(rendered_block.get_text().split()), (doc_id, page_number))
                if doc_id == "politics:2022-questions":
                    by_number = {q["number"]: q for q in paper["questions"]}
                    for number, pages in {
                        "4": ["1", "2"], "8": ["2", "3"], "20": ["5", "6"], "27": ["7", "8"],
                        "34": ["9", "10"], "35": ["10", "11", "12"], "36": ["12", "13"],
                        "37": ["13", "14", "15"], "38": ["15", "16"],
                    }.items():
                        self.assertEqual(by_number[number]["sourcePages"], pages, number)
                    for number in ("4", "8", "20", "27"):
                        self.assertEqual([option["label"] for option in by_number[number]["options"]],
                                         ["A.", "B.", "C.", "D."], number)
                    by_id = {block["id"]: block for block in paper["blocks"]}
                    for number, expected_boundary in (
                        ("27", "生死攸关的转折点"),
                        ("34", "底线思维、居安思危"),
                        ("35", "目标迈进的重大历史关头"),
                        ("36", "归结起来就是一个主题"),
                        ("37", "到条件更为艰苦"),
                        ("38", "建设和谐世界到推动构建"),
                    ):
                        question = by_number[number]
                        source_blocks = {
                            "27": ["b-7-11", "b-8-1"], "34": ["b-9-11", "b-10-1"],
                            "35": ["b-10-2", "b-11-1", "b-12-1"], "36": ["b-12-2", "b-13-1"],
                            "37": ["b-13-2", "b-14-1", "b-15-1"], "38": ["b-15-2", "b-16-1"],
                        }[number]
                        full_source_text = "".join(
                            by_id[block_id].get("presentation", {}).get("displayText", by_id[block_id]["text"])
                            for block_id in source_blocks)
                        self.assertIn(expected_boundary, question["stem"])
                        self.assertEqual(question["stem"], full_source_text)
                    self.assertIn("新时代青年应该以认真", by_number["37"]["answer"]["solution"])
                    self.assertEqual(len(reader.find(id="b-9-11").select("p")), 3)
                    self.assertEqual(len(reader.find(id="b-12-2").select("p")), 8)

    def test_2022_answer_hints_are_kept_out_of_prompts_and_linked_as_answers(self):
        docs = {doc["id"]: doc for doc in json.loads((builder.ROOT / "documents.json").read_text())}
        with tempfile.TemporaryDirectory() as directory, patch.object(builder, "OUT", Path(directory)):
            rows = [builder.build_one(docs[doc_id]) for doc_id in
                    ("politics:2022-questions", "politics:2022-answers")]
            builder.attach_answers(rows)
            row = next(row for row in rows if row["kind"] == "questions")
            paper = json.loads((Path(directory) / row["json"]).read_text())
            reader = BeautifulSoup((Path(directory) / row["reader"]).read_text(), "html.parser")

        blocks = {block["id"]: block for block in paper["blocks"]}
        expected_hint_blocks = {
            "34": ["b-10-1"], "35": ["b-12-1"], "36": ["b-13-1"],
            "37": ["b-14-1", "b-15-1"], "38": ["b-16-1"],
        }
        for number, source_ids in expected_hint_blocks.items():
            question = next(q for q in paper["questions"] if q["number"] == number)
            note = question["embeddedAnswerNote"]
            self.assertEqual([part["number"] for part in question["subquestions"]], ["1", "2"])
            self.assertEqual(note["sourceBlocks"], source_ids)
            self.assertNotIn("答题思路", question["stem"])
            self.assertNotIn("第一问考查", question["stem"])
            self.assertEqual(question["answer"]["status"], "explicit")
            self.assertIn(note["text"], question["answer"]["solution"])
            self.assertTrue(question["answer"]["explanation"])
            self.assertEqual(question["answer"]["embeddedSource"]["sourceBlocks"], source_ids)
            visible = reader.find(id=question["id"]).get_text(" ", strip=True)
            self.assertNotIn("答题思路", visible)
            for source_id in source_ids:
                self.assertIn(source_id, question["sourceBlocks"])
                self.assertIn("printed_answer_hint", blocks[source_id]["presentation"]["answerNote"]["kind"])
                self.assertEqual(blocks[source_id]["text"],
                                 BeautifulSoup(blocks[source_id]["contentHtml"], "html.parser").get_text(" ", strip=True))
        self.assertTrue(reader.find(id="b-12-1").has_attr("hidden"))
        self.assertTrue(reader.find(id="b-15-1").has_attr("hidden"))
        self.assertIn("青年应该以认真", next(q for q in paper["questions"] if q["number"] == "37")["answer"]["solution"])

    def test_pdf_specific_choice_labels_are_parsed_without_guessing(self):
        docs = {doc["id"]: doc for doc in json.loads((builder.ROOT / "documents.json").read_text())}
        with tempfile.TemporaryDirectory() as directory, patch.object(builder, "OUT", Path(directory)):
            for year, number in ((2019, "2"), (2020, "1")):
                row = builder.build_one(docs[f"politics:{year}-questions"])
                paper = json.loads((Path(directory) / row["json"]).read_text())
                question = next(q for q in paper["questions"] if q["number"] == number)
                self.assertEqual([option["label"] for option in question["options"]],
                                 ["A.", "B.", "C.", "D."], year)
                self.assertEqual(question["status"], "complete")
            row = builder.build_one(docs["politics:2005-questions"])
            paper = json.loads((Path(directory) / row["json"]).read_text())
            question = next(q for q in paper["questions"] if q["number"] == "3")
            self.assertEqual([option["label"] for option in question["options"]],
                             ["A.", "B.", "C.", "C."])
            self.assertEqual([option["sourceLabel"] for option in question["options"]],
                             ["A、", "B、", "C、", "C、"])
            self.assertEqual(question["status"], "partial")
        source_2005 = json.loads((builder.ROOT.parent / "politics-latex-2003-2023/source/2005.json").read_text())
        question_three = next(block["text"] for page in source_2005["pages"]
                              if page["source_id"] == "2005-questions" for block in page["blocks"]
                              if block.get("text", "").startswith("A、认识总是滞后"))
        self.assertIn("C、实践高于认识 C、实践与认识是合一的", question_three)


if __name__ == "__main__":
    unittest.main()
