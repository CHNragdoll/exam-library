"""Regression checks for source-faithful choices in 2009-2015 complete readers."""

from __future__ import annotations

import json
from pathlib import Path
import unittest

from lxml import html


ROOT = Path(__file__).resolve().parent


def _page(year: int):
    return html.fromstring((ROOT / f"papers/{year}-complete.htm").read_text(encoding="utf-8"))


def _text(element) -> str:
    return " ".join(element.text_content().split())


class CompleteChoiceTests(unittest.TestCase):
    def test_2009_first_three_questions_have_separate_source_choices(self) -> None:
        page = _page(2009)
        first_page = page.xpath('//section[@data-source-page="1"]')[0]
        expected = {
            1: ["栈", "队列", "树", "图"],
            2: ["1", "2", "3", "4"],
            3: ["LRN", "NRL", "RLN", "RNL"],
        }
        for number, values in expected.items():
            with self.subTest(question=number):
                stem = next(p for p in first_page.xpath('.//p[contains(@class,"question")]')
                            if _text(p).startswith(f"{number}. "))
                self.assertNotIn("A．", _text(stem))
                choices = stem.getnext()
                self.assertEqual(choices.tag, "div")
                self.assertIn("choices", choices.get("class", "").split())
                self.assertEqual([_text(cell.find("b")) for cell in choices],
                                 ["A.", "B.", "C.", "D."])
                self.assertEqual([_text(cell.find("span")) for cell in choices], values)

    def test_complete_years_render_choices_without_splitting_explanations(self) -> None:
        for year in range(2009, 2016):
            with self.subTest(year=year):
                page = _page(year)
                self.assertGreaterEqual(len(page.xpath('//div[contains(@class,"choices")]')), 10)
                source = json.loads((ROOT / f"source/{year}.json").read_text(encoding="utf-8"))
                sections = page.xpath('//section[@data-source-page]')
                self.assertEqual([len(section) for section in sections],
                                 [len(item["blocks"]) for item in source["pages"]])
        page = _page(2011)
        explanation = next(p for p in page.xpath('//p[contains(@class,"paragraph")]')
                           if _text(p).startswith("解答：A。程序中"))
        self.assertFalse(explanation.getnext() is not None
                         and "choices" in explanation.getnext().get("class", "").split())
        self.assertIn("x=2*x", _text(explanation))

    def test_2009_answers_12_through_16_keep_their_source_block_alignment(self) -> None:
        page = _page(2009)
        source = json.loads((ROOT / "source/2009.json").read_text(encoding="utf-8"))
        structured = json.loads((ROOT.parent / "exam-library/structured/papers/cs408/2009-complete.json")
                                .read_text(encoding="utf-8"))
        config = json.loads(page.xpath('//*[@id="exam-reader-config"]')[0].text)
        embedded = {tuple(item["sourceBlocks"]): item for item in config["structuredAnswers"]}
        expected = {12: ("D", "b-14-7"), 13: ("D", "b-14-8"),
                    14: ("C", "b-14-9"), 15: ("D", "b-15-2"),
                    16: ("C", "b-15-3")}

        for number, (value, explanation_block) in expected.items():
            with self.subTest(question=number):
                question = next(item for item in structured["questions"]
                                if item["id"] == f"q-{number}-1")
                embedded_question = embedded[tuple(question["sourceBlocks"])]
                self.assertEqual(embedded_question["answer"]["value"], value)
                self.assertEqual(embedded_question["answer"]["sourceHref"], "2009-complete.htm")
                self.assertEqual(embedded_question["answer"]["sourceBlocks"],
                                 question["answer"]["sourceBlocks"])
                self.assertIn(explanation_block, question["answer"]["sourceBlocks"])
                self.assertIn(f"q-{number}-2", question["answer"]["sourceQuestionIds"])

                question_block = question["sourceBlocks"][0]
                page_number, block_number = map(int, question_block.split("-")[1:])
                rendered = page.xpath(f'//section[@data-source-page="{page_number}"]')[0][block_number - 1]
                self.assertEqual(rendered.get("class"), "source-choice-block")
                self.assertTrue(_text(rendered).startswith(f"{number}. "))

                answer_page, answer_position = map(int, explanation_block.split("-")[1:])
                raw = source["pages"][answer_page - 1]["blocks"][answer_position - 1]
                self.assertTrue(raw["text"].startswith(f"{number}．"))
                rendered_answer = page.xpath(f'//section[@data-source-page="{answer_page}"]')[0][answer_position - 1]
                self.assertTrue(_text(rendered_answer).startswith(f"{number}．"))

    def test_2010_question_26_retains_joined_printed_choice_labels(self) -> None:
        page = _page(2010)
        source_block = page.xpath('//section[@data-source-page="3"]')[0][6]
        self.assertEqual(source_block.get("class"), "source-choice-block")
        choices = source_block.xpath('./div[contains(@class,"choices")]/div[contains(@class,"choice")]')
        self.assertEqual([_text(choice.find("b")) for choice in choices],
                         ["A.", "B.", "C.", "D."])
        self.assertEqual([_text(choice.find("span")) for choice in choices], [
            "进程的时间片用完", "进程刚完成I/O，进入就绪列队",
            "进程长期处于就绪列队中", "进程从就绪态转为运行态",
        ])


if __name__ == "__main__":
    unittest.main()
