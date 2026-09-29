"""CS408 page-break stems remain complete when their choices move to another block."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import build_structured_exams as builder


class CS408ContinuationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        documents = json.loads((builder.ROOT / "documents.json").read_text(encoding="utf-8"))
        by_id = {document["id"]: document for document in documents}
        cls.papers = {}
        with tempfile.TemporaryDirectory() as folder, patch.object(builder, "OUT", Path(folder)):
            for year in range(2009, 2016):
                row = builder.build_one(by_id[f"cs408:{year}-complete"])
                cls.papers[year] = json.loads((Path(folder) / row["json"]).read_text(encoding="utf-8"))

    def question(self, year: int, number: int) -> dict:
        return next(question for question in self.papers[year]["questions"]
                    if question["recordType"] == "question" and question["number"] == str(number))

    def test_page_break_stems_keep_pre_choice_prose(self) -> None:
        expected = (
            (2009, 34, "则该通信链路的最大数据传输速率是"),
            (2010, 29, "页目录表中包含表项的个数至少是"),
            (2011, 31, "在单缓冲区和双缓冲区结构下，读入并分析完该文件的时间分别是"),
            (2012, 36, "为使信道利用率达到最高，帧序号的比特数至少为"),
            (2013, 1, "最坏情况下的时间复杂度是"),
            (2013, 3, "平衡因子为0 的分支结点的个数是"),
            (2013, 21, "磁盘控制器延迟为0.2 ms"),
            (2014, 18, "微指令地址，则微指令中下址字段的位数至少是"),
        )
        for year, number, phrase in expected:
            with self.subTest(year=year, question=number):
                question = self.question(year, number)
                self.assertIn(phrase, question["stem"])
                self.assertEqual([option["label"] for option in question["options"]],
                                 ["A.", "B.", "C.", "D."])
                self.assertEqual(question["stem"].count(phrase), 1)
                self.assertNotIn("解答：", question["stem"])

    def test_interleaved_solution_stays_out_of_stem_and_options(self) -> None:
        question = self.question(2011, 31)
        self.assertNotIn("单缓冲区下当上一个磁盘块", question["stem"])
        self.assertEqual(question["options"][1]["text"], "1550us、1100us")
        self.assertEqual(question["options"][3]["text"], "2000us、2000us")
        self.assertEqual(question["sourceBlocks"], ["b-5-15", "b-6-1"])
        block = next(block for block in self.papers[2011]["blocks"] if block["id"] == "b-6-1")
        self.assertEqual(block["questionId"], question["id"])
        self.assertIn("解答：B。", block["text"])

    def test_2011_interleaved_answer_is_not_practice_content(self) -> None:
        paper = self.papers[2011]
        blocks = {block["id"]: block for block in paper["blocks"]}
        first = self.question(2011, 1)
        self.assertEqual(first["sourceBlocks"], ["b-2-2", "b-2-3", "b-2-4", "b-2-5"])
        self.assertEqual(blocks["b-2-5"]["role"], "answer")
        self.assertEqual(builder.answer_entries(paper)["1"]["sourceBlocks"], ["b-2-5"])
        self.assertEqual(builder.answer_entries(paper)["1"]["value"], "A")
        for question in paper["questions"]:
            if question["recordType"] != "question":
                continue
            practice_blocks = (blocks[block_id] for block_id in question["sourceBlocks"]
                               if blocks[block_id]["role"] in {"content", "figure"})
            self.assertFalse(any(block["text"].lstrip().startswith("解答：")
                                 for block in practice_blocks), question["number"])

    def test_2015_page_break_choices_are_options_not_stem(self) -> None:
        expected = {
            7: ("180,500,200,450", "180,200,500,450", "b-2-1"),
            30: ("固定分配，全局置换", "固定分配，局部置换", "b-4-1"),
        }
        for number, (option_c, option_d, source_block) in expected.items():
            with self.subTest(number=number):
                question = self.question(2015, number)
                self.assertEqual([option["label"] for option in question["options"]],
                                 ["A.", "B.", "C.", "D."])
                self.assertEqual([option["text"] for option in question["options"]][2:],
                                 [option_c, option_d])
                self.assertEqual([option["sourceLabel"] for option in question["options"]][2:],
                                 ["C．", "D．"])
                self.assertIn(source_block, question["sourceBlocks"])
                self.assertNotIn("（续）", question["stem"])
                self.assertNotIn(option_c, question["stem"])
                self.assertEqual(question["status"], "complete")

    def test_2013_pdf_page_break_and_ocr_separator_keep_four_choices(self) -> None:
        twenty_second = self.question(2013, 22)
        self.assertEqual([option["label"] for option in twenty_second["options"]],
                         ["A.", "B.", "C.", "D."])
        self.assertEqual([option["sourceLabel"] for option in twenty_second["options"]],
                         ["A.", "B.", "C.", "D."])
        self.assertEqual(twenty_second["options"][3]["text"],
                         "中断I/O 方式适用于所有外部设备，DMA 方式仅适用于快速外部设备")
        self.assertEqual(twenty_second["sourcePages"], ["3", "4"])
        self.assertIn("b-4-1", twenty_second["sourceBlocks"])

        twenty_seventh = self.question(2013, 27)
        self.assertEqual([option["label"] for option in twenty_seventh["options"]],
                         ["A.", "B.", "C.", "D."])
        self.assertEqual([option["sourceLabel"] for option in twenty_seventh["options"]],
                         ["A.", "B.", "C.", "D."])
        self.assertEqual([option["text"] for option in twenty_seventh["options"]],
                         ["200", "295", "300", "390"])
        self.assertIn("b-4-14", twenty_seventh["sourceBlocks"])
        self.assertEqual(twenty_second["status"], twenty_seventh["status"])
        self.assertEqual(twenty_seventh["status"], "complete")


if __name__ == "__main__":
    unittest.main()
