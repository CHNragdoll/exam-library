"""Regression checks for source-linked answers printed beside CS408 questions."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from bs4 import BeautifulSoup

from scripts import build_structured_exams as builder


class CS408InterleavedAnswerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        docs = json.loads((builder.ROOT / "documents.json").read_text(encoding="utf-8"))
        cls.docs = {doc["id"]: doc for doc in docs}

    def build_papers(self, years):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            with patch.object(builder, "OUT", output):
                rows = [builder.build_one(self.docs[f"cs408:{year}-complete"]) for year in years]
                builder.attach_answers(rows)
            return {row["id"]: json.loads((output / row["json"]).read_text(encoding="utf-8"))
                    for row in rows}

    def test_2011_interleaved_answers_cover_choices_and_written_work(self):
        paper = self.build_papers((2011,))["cs408:2011-complete"]
        questions = {question["number"]: question for question in paper["questions"]
                     if question["recordType"] == "question"}
        self.assertEqual(len(questions), 47)
        self.assertEqual(paper["audit"]["linkedAnswers"], 47)
        self.assertTrue(all(question["answer"]["status"] == "explicit"
                            for question in questions.values()))
        blocks = {block["id"]: block for block in paper["blocks"]}
        for question in questions.values():
            answer = question["answer"]
            self.assertTrue(answer["sourceBlocks"], question["number"])
            self.assertTrue(set(answer["sourceBlocks"]).issubset(question["sourceBlocks"]))
            self.assertEqual(answer["sourcePages"], list(dict.fromkeys(
                blocks[block_id]["page"] for block_id in answer["sourceBlocks"])))

        choice = questions["7"]["answer"]
        self.assertEqual(choice["value"], "A")
        self.assertIn("后面的94就错了", choice["solution"])
        self.assertEqual(choice["sourceDocumentId"], paper["id"])
        self.assertEqual(choice["sourceQuestionIds"], [questions["7"]["id"]])
        self.assertEqual(choice["sourceBlocks"], ["b-3-1"])
        self.assertEqual(choice["sourcePages"], ["3"])

        embedded = questions["31"]["answer"]
        self.assertEqual(embedded["value"], "B")
        self.assertIn("单缓冲区", embedded["solution"])
        self.assertNotIn("D．2000us", embedded["solution"])

        written = questions["41"]["answer"]
        self.assertIsNone(written["value"])
        self.assertIn("邻接矩阵", written["solution"])
        self.assertIn("关键路径", written["solution"])
        self.assertEqual(written["sourceBlocks"][0], "b-8-3")
        self.assertNotIn("b-7-13", written["sourceBlocks"])

    def test_separate_answer_sections_still_link_normally(self):
        papers = self.build_papers((2009, 2010, 2012, 2013, 2014, 2015))
        for paper in papers.values():
            questions = [question for question in paper["questions"]
                         if question["recordType"] == "question"]
            self.assertEqual(len(questions), 47)
            self.assertEqual(paper["audit"]["linkedAnswers"], 47)
            self.assertTrue(all(question["answer"]["status"] == "explicit"
                                for question in questions))
        paper = papers["cs408:2013-complete"]
        first = next(question for question in paper["questions"]
                     if question["recordType"] == "question" and question["number"] == "1")
        self.assertEqual(first["answer"]["value"], "D")
        self.assertIn("升序链表", first["answer"]["explanation"])
        self.assertEqual(first["answer"]["sourceQuestionIds"], ["q-1-2"])
        self.assertEqual(first["answer"]["sourceBlocks"], ["b-10-4", "b-10-5"])
        written = [question for question in paper["questions"]
                   if question["recordType"] == "question"
                   and question["number"] in {str(n) for n in range(41, 48)}]
        self.assertEqual(len(written), 7)
        self.assertTrue(all(question["sectionKind"] == "free_response"
                            and question["questionType"] == "free_response"
                            and question["status"] == "complete"
                            and not question["options"] for question in written))
        printed_duplicate = next(question for question in papers["cs408:2015-complete"]["questions"]
                                 if question["recordType"] == "question" and question["number"] == "1")
        self.assertEqual([option["sourceLabel"] for option in printed_duplicate["options"]],
                         ["A．", "B．", "B．", "D．"])
        self.assertEqual(printed_duplicate["status"], "partial")

    def test_unmarked_or_prompt_text_is_not_an_answer(self):
        question = {"id": "q-1-1", "number": "1", "recordType": "question",
                    "sectionKind": "single_choice", "sourceBlocks": ["b-1", "b-2"]}
        blocks = {"b-1": {"role": "question", "text": "1．请解答：下列问题"},
                  "b-2": {"role": "content", "text": "A．甲 B．乙 C．丙 D．丁"}}
        self.assertIsNone(builder.cs408_interleaved_answer(question, blocks))

    def test_reader_links_to_the_printed_answer_block(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            with patch.object(builder, "OUT", output):
                row = builder.build_one(self.docs["cs408:2011-complete"])
                builder.attach_answers([row])
            reader = BeautifulSoup((output / row["reader"]).read_text(encoding="utf-8"), "html.parser")
            panel = reader.select_one("#q-7-1 .answer-panel")
            self.assertIsNotNone(panel)
            self.assertEqual(panel.select_one(".answer-source")["href"], "2011-complete.htm#b-3-1")

    def test_2016_to_2023_pdf_answer_records_link_all_printed_answers(self):
        years = tuple(range(2016, 2024))
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            with patch.object(builder, "OUT", output):
                rows = [builder.build_one(self.docs[f"cs408:{year}-{kind}"])
                        for year in years for kind in ("questions", "answers")]
                builder.attach_answers(rows)
            papers = {row["id"]: json.loads((output / row["json"]).read_text(encoding="utf-8"))
                      for row in rows}

        for year in years:
            source = json.loads((builder.ROOT.parent / "cs408-answers-latex-2016-2025" /
                                 "source" / f"{year}.json").read_text(encoding="utf-8"))
            paper = papers[f"cs408:{year}-questions"]
            answers = papers[f"cs408:{year}-answers"]
            questions = {question["number"]: question for question in paper["questions"]
                         if question["recordType"] == "question"}
            answer_blocks = {block["id"]: block for block in answers["blocks"]}
            self.assertEqual(len(questions), 47, year)
            self.assertEqual(paper["audit"]["linkedAnswers"], 47, year)
            for number in range(1, 48):
                answer = questions[str(number)]["answer"]
                self.assertEqual(answer["status"], "explicit", (year, number))
                self.assertEqual(answer["sourceDocumentId"], answers["id"])
                self.assertTrue(answer["sourceBlocks"], (year, number))
                self.assertTrue(set(answer["sourceBlocks"]).issubset(answer_blocks))
                self.assertEqual(answer["sourcePages"], list(dict.fromkeys(
                    answer_blocks[block_id]["page"] for block_id in answer["sourceBlocks"])))
                if number <= 40:
                    self.assertEqual(answer["value"], source["answer_key"][str(number)], (year, number))
                else:
                    self.assertTrue(answer["solution"], (year, number))
                    self.assertEqual(len(answer["sourceQuestionIds"]), 1)
            if year == 2020:
                # The final PDF page is an unrelated 2019 question sheet.
                self.assertEqual(len(answers["questions"]), 53)
                first = questions["1"]["answer"]
                self.assertEqual(first["sourceQuestionIds"], ["q-1-1"])
                self.assertTrue(all(not block_id.startswith("b-13-")
                                    for block_id in first["sourceBlocks"]))

    def test_2024_duplicate_pdf_page_keeps_one_answer_card_per_question(self):
        original = builder.ROOT.parent / "cs408-original" / "papers" / "2024-answers.assets"
        self.assertEqual((original / "page-003.svg").read_bytes(),
                         (original / "page-004.svg").read_bytes())
        source = json.loads((builder.ROOT.parent / "cs408-answers-latex-2016-2025" /
                             "source" / "2024.json").read_text(encoding="utf-8"))
        self.assertEqual(source["pages"][2]["blocks"], source["pages"][3]["blocks"])

        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            with patch.object(builder, "OUT", output):
                row = builder.build_one(self.docs["cs408:2024-answers"])
            paper = json.loads((output / row["json"]).read_text(encoding="utf-8"))
            reader = BeautifulSoup((output / row["reader"]).read_text(encoding="utf-8"),
                                   "html.parser")

        questions = {question["number"]: question for question in paper["questions"]}
        self.assertEqual(len(paper["questions"]), 7)
        self.assertEqual(set(questions), {str(number) for number in range(41, 48)})
        self.assertEqual(len(reader.select('.question-card[data-question="42"]')), 1)
        self.assertEqual(len(reader.select('.question-card[data-question="43"]')), 1)

        blocks = {block["id"]: block for block in paper["blocks"]}
        for child_index, number in ((1, "41"), (2, "42"), (3, "42"),
                                    (4, "42"), (5, "43")):
            duplicate = blocks[f"b-4-{child_index}"]
            self.assertEqual(duplicate["duplicateOf"], f"b-3-{child_index}")
            self.assertEqual(duplicate["questionId"], questions[number]["id"])
            self.assertIn(duplicate["id"], questions[number]["sourceBlocks"])
            self.assertIn("4", questions[number]["sourcePages"])

        entries = builder.answer_entries(paper)
        self.assertIn("Ext取值", entries["43"]["solution"])
        self.assertEqual(entries["43"]["solution"].count("最多有"), 1)
        self.assertNotIn("if(in0==-1)", entries["43"]["solution"])
        self.assertEqual(entries["43"]["sourceQuestionIds"], [questions["43"]["id"]])

    def test_2024_and_2025_pdf_answer_continuations_are_included(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            with patch.object(builder, "OUT", output):
                rows = [builder.build_one(self.docs[f"cs408:{year}-answers"])
                        for year in (2024, 2025)]
            papers = {row["id"]: json.loads((output / row["json"]).read_text(encoding="utf-8"))
                      for row in rows}

        for year, number, page, phrase in ((2024, "43", "5", "Ext取值"),
                                           (2024, "45", "6", "页框号"),
                                           (2025, "41", "2", "算法实现"),
                                           (2025, "43", "3", "Cache")):
            with self.subTest(year=year, number=number):
                paper = papers[f"cs408:{year}-answers"]
                question = next(q for q in paper["questions"] if q["number"] == number)
                blocks = {block["id"]: block for block in paper["blocks"]}
                continuations = [blocks[bid] for bid in question["sourceBlocks"]
                                 if blocks[bid].get("answerContinuation")]
                self.assertEqual([block["page"] for block in continuations], [page])
                self.assertIn(phrase, builder.answer_entries(paper)[number]["solution"])

    def test_2016_q28_pdf_segment_entry_sentence_survives_source_and_answer_link(self):
        sentence = "从这句话我们可以看出，段表项实际上只有两部分，前几位是段长，后几位是起始地址。"
        source = json.loads((builder.ROOT.parent / "cs408-answers-latex-2016-2025" /
                             "source" / "2016.json").read_text(encoding="utf-8"))
        self.assertIn(sentence, source["pages"][5]["blocks"][7]["text"])

        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            with patch.object(builder, "OUT", output):
                row = builder.build_one(self.docs["cs408:2016-answers"])
            paper = json.loads((output / row["json"]).read_text(encoding="utf-8"))
        question = next(q for q in paper["questions"] if q["number"] == "28")
        self.assertIn("b-6-8", question["sourceBlocks"])
        self.assertEqual(question["sourcePages"], ["6"])
        answer = builder.answer_entries(paper)["28"]
        self.assertIn(sentence, answer["explanation"])
        self.assertIn("b-6-8", answer["sourceBlocks"])


if __name__ == "__main__":
    unittest.main()
