"""Source-backed boundaries in mathematics papers with split choices and old numbering."""

import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch

from bs4 import BeautifulSoup

from scripts import build_structured_exams as builder


class MathPdfQuestionBoundariesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        documents = json.loads((builder.ROOT / "documents.json").read_text(encoding="utf-8"))
        cls.question_docs = {
            doc["year"]: doc for doc in documents
            if doc["category"] == "math3" and doc["kind"] == "questions"
        }
        cls.answer_docs = {
            doc["year"]: doc for doc in documents
            if doc["category"] == "math3" and doc["kind"] == "answers"
        }

    def build_paper(self, year: int, folder: Path) -> dict:
        with patch.object(builder, "OUT", folder):
            row = builder.build_one(self.question_docs[year])
        return json.loads((folder / row["json"]).read_text(encoding="utf-8"))

    def test_2015_sixth_question_keeps_options_on_the_next_pdf_page(self):
        source = json.loads((builder.ROOT.parent / "math3-latex-2009-2019/source/2015.json")
                            .read_text(encoding="utf-8"))
        page_22 = next(page for page in source["pages"] if page["source_page"] == 22)
        self.assertTrue(page_22["blocks"][0]["text"].startswith("(A) "))
        reflow = BeautifulSoup((builder.ROOT.parent / "math3-latex-2009-2019/papers/2015-questions.htm")
                               .read_text(encoding="utf-8"), "html.parser")
        first = reflow.select_one('section[data-source-page="22"] > .math-options')
        self.assertIsNotNone(first)
        self.assertEqual(len(first.select(":scope > .math-option")), 4)
        with tempfile.TemporaryDirectory() as temp:
            paper = self.build_paper(2015, Path(temp))
        sixth = [question for question in paper["questions"] if question["number"] == "6"]
        self.assertEqual(len(sixth), 1)
        self.assertEqual([option["label"] for option in sixth[0]["options"]],
                         ["A.", "B.", "C.", "D."])
        self.assertEqual(sixth[0]["sourcePages"], ["21", "22"])
        self.assertEqual(sixth[0]["status"], "complete")

    def test_split_option_rows_are_complete_when_all_four_choices_are_present(self):
        cases = {1997: (3,), 2012: (3,), 2013: (4,), 2015: (1, 3),
                 2018: (8,), 2019: (4, 7, 8)}
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            for year, numbers in cases.items():
                paper = self.build_paper(year, folder)
                for number in numbers:
                    with self.subTest(year=year, number=number):
                        matches = [question for question in paper["questions"]
                                   if question["number"] == str(number)
                                   and question["sectionKind"] == "single_choice"
                                   and len(question["options"]) == 4]
                        self.assertEqual(len(matches), 1)
                        self.assertEqual(matches[0]["status"], "complete")

    def test_2009_fourth_choice_uses_the_printed_graphs(self):
        with tempfile.TemporaryDirectory() as temp:
            paper = self.build_paper(2009, Path(temp))
        fourth = next(q for q in paper["questions"] if q["number"] == "4")
        linked = [block for block in paper["blocks"] if block["id"] in fourth["sourceBlocks"]]
        self.assertEqual([option["label"] for option in fourth["options"]],
                         ["A.", "B.", "C.", "D."])
        self.assertEqual([option["image"]["sourceBlockId"] for option in fourth["options"]],
                         ["b-1-16"] * 4)
        self.assertEqual(fourth["status"], "complete")
        self.assertEqual(sum(block["role"] == "figure" for block in linked), 2)
        self.assertTrue(any("图形选项（A）、（B）、（C）、（D）" in block["text"]
                            for block in linked))

    def test_1994_and_1995_numbered_subparts_stay_with_their_main_problem(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            for year, main_number, subpart in (
                (1994, "九、", "（1）证明："),
                (1995, "十一、", "（1）全部能出厂"),
            ):
                with self.subTest(year=year):
                    paper = self.build_paper(year, folder)
                    self.assertFalse(any(q["stem"].startswith(subpart) for q in paper["questions"]))
                    main = next(q for q in paper["questions"] if q["stem"].startswith(main_number))
                    self.assertEqual(main["questionType"], "free_response")
                    self.assertTrue(any(block["text"].startswith(subpart)
                                        for block in paper["blocks"]
                                        if block["id"] in main["sourceBlocks"]))

    def test_printed_old_form_references_have_one_card_per_number(self):
        # These PDF pages print several separate IV/V questions on one line.
        # Each cross-reference remains literal, but it needs its own block.
        cases = (
            (1988, 24, "第三", (3, 4)),
            (1989, 27, "第二", (1, 2, 3)),
            (1990, 31, "第一", (1, 2, 3, 4)),
            (1990, 31, "第二", (1, 2, 3)),
            (1991, 35, "第一", (1, 2, 3)),
            (1994, 49, "第一", (1, 2, 3, 4)),
            (1995, 53, "第一", (2, 3, 4)),
            (1995, 53, "第二", (1, 2)),
            (1996, 57, "第一", (1, 2)),
            (1996, 58, "第二", (3, 4)),
        )
        for year, page_number, section, numbers in cases:
            with self.subTest(year=year, pdf_page=page_number, section=section):
                source = json.loads((builder.ROOT.parent / "math3-latex-1987-2009/source" / f"{year}.json")
                                    .read_text(encoding="utf-8"))
                page = next(page for page in source["pages"]
                            if page["kind"] == "questions" and page["source_page"] == page_number)
                refs = [block["text"] for block in page["blocks"]
                        if block["type"] == "paragraph" and f"{section}、" in block["text"]
                        and "【同试卷" in block["text"]]
                found = [int(match.group(1)) for text in refs
                         for match in re.finditer(r"（(\d+)）(?=【同试卷)", text)]
                self.assertEqual(found, list(numbers))
                self.assertEqual(len(refs), len(numbers))
        # Includes the separate Chinese-numbered main problems which the
        # original PDF prints after the numbered sections.
        expected_cards = {1987: 46, 1988: 36, 1989: 42, 1990: 44,
                          1991: 44, 1992: 44, 1993: 38, 1994: 40,
                          1995: 40, 1996: 41}
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            for year, count in expected_cards.items():
                with self.subTest(year=year, structured_cards=True):
                    paper = self.build_paper(year, folder)
                    self.assertEqual(len(paper["questions"]), count)
                    self.assertFalse(any(len(re.findall(r"（\d+）(?=【同试卷)", q["stem"])) > 1
                                         for q in paper["questions"]))

    def test_1997_to_2003_chinese_numbered_problems_are_separate_questions(self):
        # The printed papers restart (1)-(5/6) inside two sections, then use
        # 三、... for the free response problems. Their internal (1)/(2) parts
        # belong to that problem and do not start cards of their own.
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            for year, expected_count, last_problem in (
                (1997, 21, "十三、"),
                (1998, 20, "十二、"),
                (1999, 20, "十二、"),
                (2000, 20, "十二、"),
                (2001, 20, "十二、"),
                (2002, 20, "十二、"),
                (2003, 22, "十二、"),
            ):
                with self.subTest(year=year):
                    paper = self.build_paper(year, folder)
                    questions = paper["questions"]
                    self.assertEqual(len(questions), expected_count)
                    self.assertEqual(sum(q["stem"].startswith(last_problem) for q in questions), 1)
                    self.assertEqual(sum(q["stem"].startswith("三、") for q in questions), 1)
                    last = next(q for q in questions if q["stem"].startswith(last_problem))
                    self.assertEqual(last["questionType"], "free_response")
            paper = self.build_paper(1997, folder)
            choices = next(q for q in paper["questions"]
                           if q["number"] == "5" and q["sectionKind"] == "single_choice")
            self.assertEqual([option["label"] for option in choices["options"]],
                             ["A.", "B.", "C.", "D."])
            self.assertEqual(choices["sourcePages"], ["80", "81"])
            self.assertNotIn("十一、", " ".join(
                block["text"] for block in paper["blocks"]
                if block["id"] in choices["sourceBlocks"]))

    def test_old_math_answer_sections_match_their_own_question_sections(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            with patch.object(builder, "OUT", folder):
                rows = [builder.build_one(doc) for year in range(1997, 2004)
                        for doc in (self.question_docs[year], self.answer_docs[year])]
                builder.attach_answers(rows)
            for year, expected_count in ((1997, 21), (1998, 20), (1999, 20),
                                         (2000, 20), (2001, 20), (2002, 20), (2003, 22)):
                paper = json.loads((folder / "papers/math3" / f"{year}-questions.json")
                                   .read_text(encoding="utf-8"))
                self.assertEqual(len(paper["questions"]), expected_count)
                self.assertTrue(all(question["answer"]["status"] == "explicit"
                                    for question in paper["questions"]), year)
                by_kind = {(question["sectionKind"], question["number"]): question
                           for question in paper["questions"]}
                for key in (("fill_blank", "3"), ("single_choice", "3"), ("other", "3")):
                    self.assertEqual(by_kind[key]["answer"]["status"], "explicit", (year, key))
                self.assertNotEqual(by_kind[("fill_blank", "3")]["answer"]["value"],
                                    by_kind[("single_choice", "3")]["answer"]["value"])
                seventh = next(question for question in paper["questions"]
                               if question["stem"].startswith("七、"))
                self.assertEqual(seventh["answer"]["status"], "explicit", year)
                self.assertTrue(seventh["answer"]["solution"], year)
                if year == 2002:
                    self.assertIn("无正确答案", by_kind[("single_choice", "2")]["answer"]["value"])

    def test_1994_and_1995_answer_keys_match_chinese_problems_by_printed_form(self):
        # PDF pages 74-77 print separate IV and V answer keys. Both forms
        # restart at 三、; matching on the bare problem number would cross-link.
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            with patch.object(builder, "OUT", folder):
                rows = [builder.build_one(doc) for year in (1994, 1995)
                        for doc in (self.question_docs[year], self.answer_docs[year])]
                builder.attach_answers(rows)
            for year in (1994, 1995):
                with self.subTest(year=year):
                    paper = json.loads((folder / "papers/math3" / f"{year}-questions.json")
                                       .read_text(encoding="utf-8"))
                    main = [q for q in paper["questions"] if q["sectionKind"] == "other"]
                    self.assertEqual(len(main), 20)
                    for number in range(3, 13):
                        matches = [q for q in main if q["number"] == str(number)]
                        self.assertEqual(len(matches), 2)
                        self.assertTrue(all(q["answer"]["status"] == "explicit" for q in matches))
                        self.assertTrue(all(q["answer"]["solution"] for q in matches))
                        self.assertNotEqual(matches[0]["answer"]["sourceQuestionIds"],
                                            matches[1]["answer"]["sourceQuestionIds"])
                    if year == 1994:
                        seven = [q for q in main if q["number"] == "7"]
                        self.assertIn(r"\pi", seven[0]["answer"]["solution"])
                        self.assertIn(r"S=", seven[1]["answer"]["solution"])
                        ten = [q for q in main if q["number"] == "10"]
                        self.assertEqual(ten[1]["answer"]["solution"],
                                         ten[0]["answer"]["solution"])
                        self.assertEqual(ten[1]["answer"]["references"][0]["printedText"],
                                         "【同试卷 IV 第十题】")
                        self.assertEqual([q["answer"]["sourcePages"] for q in ten],
                                         [["74"], ["75"]])
                    else:
                        ten = [q for q in main if q["number"] == "10"]
                        self.assertIn("（2）令", ten[0]["answer"]["solution"])
                        self.assertIn("A=", ten[1]["answer"]["solution"])
                        self.assertEqual([q["answer"]["sourcePages"] for q in ten],
                                         [["76"], ["77"]])
                        twelve = [q for q in main if q["number"] == "12"]
                        self.assertIn("证明略", twelve[1]["answer"]["solution"])

    def test_old_dual_form_numbered_sections_use_printed_form_and_section(self):
        # The old answer PDFs have separate IV/V keys, and each form restarts
        # numbering in 一、 and 二、. A bare answer number is not sufficient.
        samples = (
            (1987, "IV", "一", "1", "×", "60"),
            (1987, "IV", "二", "1", "A", "60"),
            (1989, "IV", "二", "1", "B", "64"),
            (1989, "V", "二", "1", "B", "65"),
            (1994, "IV", "二", "1", "B", "74"),
            (1994, "V", "二", "2", "B", "75"),
            (1995, "IV", "二", "1", "D", "76"),
            (1995, "V", "二", "3", "C", "77"),
            (1996, "IV", "二", "1", "D", "78"),
            (1996, "V", "二", "3", "C", "79"),
        )
        years = sorted({sample[0] for sample in samples})
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            with patch.object(builder, "OUT", folder):
                rows = [builder.build_one(doc) for year in years
                        for doc in (self.question_docs[year], self.answer_docs[year])]
                builder.attach_answers(rows)
            for year, form, section, number, expected, answer_page in samples:
                with self.subTest(year=year, form=form, section=section, number=number):
                    paper = json.loads((folder / "papers/math3" / f"{year}-questions.json")
                                       .read_text(encoding="utf-8"))
                    forms = builder.dual_form_math_question_forms(paper)
                    matches = [q for q in paper["questions"]
                               if forms.get(q["id"]) == form and q["number"] == number
                               and q["sectionTitle"].startswith(f"{section}、")]
                    self.assertEqual(len(matches), 1)
                    answer = matches[0]["answer"]
                    self.assertEqual(answer["status"], "explicit")
                    self.assertIn(expected, answer["value"] or answer["solution"])
                    self.assertEqual(answer["sourcePages"], [answer_page])

    def test_old_dual_form_main_answers_keep_their_printed_subparts(self):
        samples = (
            (1987, "IV", "四", r"\pi", "60"),
            (1987, "IV", "十一", "F(x)=", "60"),
            (1987, "V", "六", "边际成本", "61"),
            (1989, "IV", "四", "收益函数", "64"),
            (1990, "IV", "六", "基础解系", "66"),
            (1992, "IV", "九", "x=0,y=-2", "70"),
            (1992, "V", "九", "所求长度", "71"),
        )
        years = sorted({sample[0] for sample in samples})
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            with patch.object(builder, "OUT", folder):
                rows = [builder.build_one(doc) for year in years
                        for doc in (self.question_docs[year], self.answer_docs[year])]
                builder.attach_answers(rows)
            for year, form, section, expected, answer_page in samples:
                with self.subTest(year=year, form=form, section=section):
                    paper = json.loads((folder / "papers/math3" / f"{year}-questions.json")
                                       .read_text(encoding="utf-8"))
                    forms = builder.dual_form_math_question_forms(paper)
                    matches = [q for q in paper["questions"] if forms.get(q["id"]) == form
                               and q["stem"].startswith(f"{section}、")]
                    self.assertEqual(len(matches), 1)
                    answer = matches[0]["answer"]
                    self.assertEqual(answer["status"], "explicit")
                    self.assertIn(expected, answer["solution"] or answer["value"])
                    self.assertEqual(answer["sourcePages"], [answer_page])

    def test_1992_form_v_ninth_and_both_fourteenth_problems_follow_pdf_boundaries(self):
        # PDF p41 begins 九(1) in a premise paragraph, and p42 prints 九(2).
        # PDF p40/p42 both label a separate 十四 problem; the answer key
        # prints those under IV/V on p70/p71.
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            with patch.object(builder, "OUT", folder):
                rows = [builder.build_one(doc) for doc in
                        (self.question_docs[1992], self.answer_docs[1992])]
                builder.attach_answers(rows)
            paper = json.loads((folder / "papers/math3/1992-questions.json")
                               .read_text(encoding="utf-8"))
            forms = builder.dual_form_math_question_forms(paper)
            self.assertEqual(len(paper["questions"]), 44)
            ninth = [q for q in paper["questions"] if forms.get(q["id"]) == "V"
                     and q["stem"].startswith("九、")]
            self.assertEqual([(q["number"], q["sourcePages"]) for q in ninth],
                             [("9", ["41", "42"])])
            self.assertTrue(all(q["answer"]["status"] == "explicit" for q in ninth))
            self.assertIn("切线方程", ninth[0]["answer"]["solution"])
            self.assertIn("所求长度", ninth[0]["answer"]["solution"])
            fourteenth = [q for q in paper["questions"] if q["number"] == "14"]
            self.assertEqual([(forms[q["id"]], q["sourcePages"], q["answer"]["sourcePages"])
                              for q in fourteenth],
                             [("IV", ["40"], ["70"]), ("V", ["42"], ["71"])])
            self.assertTrue(all(q["answer"]["status"] == "explicit" for q in fourteenth))
            self.assertIn("【同试卷IV 第十三题】", fourteenth[1]["stem"])
            self.assertEqual(fourteenth[1]["answer"]["solution"],
                             next(q for q in paper["questions"] if q["id"] == "q-13-1")["answer"]["solution"])
            self.assertEqual(fourteenth[1]["answer"]["references"][0]["printedText"],
                             "【同试卷IV 第十三题】")
            self.assertTrue(any(block["text"].startswith("（1）求")
                                for block in paper["blocks"]
                                if block["id"] in fourteenth[0]["sourceBlocks"]))

    def test_2004_and_2006_twenty_first_answers_join_printed_roman_parts(self):
        # The PDF prints one question 21, then the answer key repeats (21)
        # for parts (I) and (II). Those records belong to the same question.
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            with patch.object(builder, "OUT", folder):
                rows = [builder.build_one(doc) for year in (2004, 2006)
                        for doc in (self.question_docs[year], self.answer_docs[year])]
                builder.attach_answers(rows)
            for year, answer_page in ((2004, "126"), (2006, "129")):
                with self.subTest(year=year):
                    paper = json.loads((folder / "papers/math3" / f"{year}-questions.json")
                                       .read_text(encoding="utf-8"))
                    question = next(q for q in paper["questions"] if q["number"] == "21")
                    answer = question["answer"]
                    self.assertEqual(answer["status"], "explicit")
                    self.assertEqual(len(answer["sourceQuestionIds"]), 2)
                    self.assertEqual(answer["sourcePages"], [answer_page])
                    self.assertIn("（Ⅰ）", answer["solution"])
                    self.assertIn("（Ⅱ）", answer["solution"])
                    if year == 2006:
                        self.assertIn("（Ⅲ）", answer["solution"])

    def test_1996_fourth_choice_starts_on_pdf_page_56(self):
        # The continuation page prints "二、（4）" rather than bare "（4）".
        # PDF p56 gives its own A-D; form V p58 only refers back to it.
        with tempfile.TemporaryDirectory() as temp:
            paper = self.build_paper(1996, Path(temp))
        forms = builder.dual_form_math_question_forms(paper)
        choices = [q for q in paper["questions"] if forms.get(q["id"]) == "IV"
                   and q["sectionKind"] == "single_choice"]
        self.assertEqual([q["number"] for q in choices], ["1", "2", "3", "4", "5"])
        self.assertTrue(all([option["label"] for option in q["options"]]
                            == ["A.", "B.", "C.", "D."] for q in choices))
        self.assertEqual(choices[2]["sourcePages"], ["55"])
        self.assertEqual(choices[3]["sourcePages"], ["56"])
        self.assertTrue(choices[3]["stem"].startswith("二、（4）设有任意两个"))
        referenced = [q for q in paper["questions"] if forms.get(q["id"]) == "V"
                      and q["sectionKind"] == "single_choice" and q["number"] == "4"]
        self.assertEqual(len(referenced), 1)
        self.assertEqual(referenced[0]["sourcePages"], ["58"])
        self.assertEqual(referenced[0]["stem"], "（4）【同试卷 IV 第二、（4）题】")
        self.assertEqual(referenced[0]["options"], [])

    def test_1987_to_1996_main_problems_match_printed_forms_and_answer_keys(self):
        # Original PDF physical pages 11-58 print one card per Chinese main
        # problem. Earlier 三、 (and 1988 IV 四、) instead introduce numbered
        # calculation sections; their numbered items remain separate cards.
        main_ranges = {
            1987: (range(4, 13), range(4, 12)),
            1988: (range(5, 13), range(4, 13)),
            1989: (range(4, 12), range(4, 11)),
            1990: (range(4, 12), range(4, 12)),
            1991: (range(3, 15), range(3, 15)),
            1992: (range(3, 15), range(3, 15)),
            1993: (range(3, 12), range(3, 12)),
            1994: (range(3, 13), range(3, 13)),
            1995: (range(3, 13), range(3, 13)),
            1996: (range(3, 14), range(3, 13)),
        }
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            with patch.object(builder, "OUT", folder):
                rows = [builder.build_one(doc) for year in main_ranges
                        for doc in (self.question_docs[year], self.answer_docs[year])]
                builder.attach_answers(rows)
            for year, (iv_range, v_range) in main_ranges.items():
                paper = json.loads((folder / "papers/math3" / f"{year}-questions.json")
                                   .read_text(encoding="utf-8"))
                forms = builder.dual_form_math_question_forms(paper)
                self.assertTrue(all(q["answer"]["status"] == "explicit"
                                    for q in paper["questions"]), year)
                for form, expected in (("IV", iv_range), ("V", v_range)):
                    with self.subTest(year=year, form=form):
                        main = [q for q in paper["questions"] if forms.get(q["id"]) == form
                                and builder.MATH_OLD_MAIN_RE.match(q["stem"])]
                        self.assertEqual([int(q["number"]) for q in main], list(expected))
                        self.assertTrue(all(q["sectionKind"] == "other" and
                                            q["questionType"] == "free_response" and
                                            q["answer"]["solution"] for q in main))

    def test_page_break_prefixed_items_keep_their_own_cards(self):
        # Original PDF p54 has 1995 V choice (5); p58 has 1996 V fill (5).
        # The source prefixes each with its section number after a page break.
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            with patch.object(builder, "OUT", folder):
                rows = [builder.build_one(doc) for year in (1995, 1996)
                        for doc in (self.question_docs[year], self.answer_docs[year])]
                builder.attach_answers(rows)
            for year, section_kind, page, prefix in (
                (1995, "single_choice", "54", "二、（5）"),
                (1996, "fill_blank", "58", "一、（5）"),
            ):
                paper = json.loads((folder / "papers/math3" / f"{year}-questions.json")
                                   .read_text(encoding="utf-8"))
                forms = builder.dual_form_math_question_forms(paper)
                matches = [q for q in paper["questions"] if forms.get(q["id"]) == "V"
                           and q["sectionKind"] == section_kind and q["number"] == "5"]
                self.assertEqual(len(matches), 1)
                self.assertEqual(matches[0]["sourcePages"], [page])
                self.assertTrue(matches[0]["stem"].startswith(prefix))
                self.assertEqual(matches[0]["answer"]["status"], "explicit")

    def test_1988_fourth_heading_is_a_section_only_in_form_iv(self):
        # PDF p22: IV 四、 is a two-item calculation section. PDF p24:
        # V 四、 is one independent problem; its answer is on PDF p63.
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            with patch.object(builder, "OUT", folder):
                rows = [builder.build_one(doc) for doc in
                        (self.question_docs[1988], self.answer_docs[1988])]
                builder.attach_answers(rows)
            paper = json.loads((folder / "papers/math3/1988-questions.json")
                               .read_text(encoding="utf-8"))
            forms = builder.dual_form_math_question_forms(paper)
            iv_parts = [q for q in paper["questions"] if forms.get(q["id"]) == "IV"
                        and q["sectionTitle"].startswith("四、")]
            self.assertEqual([q["number"] for q in iv_parts], ["1", "2"])
            self.assertEqual([q["answer"]["sourcePages"] for q in iv_parts], [["62"], ["62"]])
            self.assertIn("级数收敛", iv_parts[0]["answer"]["value"])
            self.assertIn("证明略", iv_parts[1]["answer"]["value"])
            v_four = [q for q in paper["questions"] if forms.get(q["id"]) == "V"
                      and q["stem"].startswith("四、")]
            self.assertEqual(len(v_four), 1)
            self.assertEqual(v_four[0]["number"], "4")
            self.assertEqual(v_four[0]["sourcePages"], ["24"])
            self.assertEqual(v_four[0]["answer"]["sourcePages"], ["63"])

    def test_reference_only_choices_point_to_existing_iv_options(self):
        # The original V papers print only 【同试卷 IV 第二、（n）题】, not
        # duplicate A-D choices. Their empty options are source-faithful.
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            reference_count = 0
            for year in range(1987, 1997):
                paper = self.build_paper(year, folder)
                forms = builder.dual_form_math_question_forms(paper)
                iv = {q["number"]: q for q in paper["questions"]
                      if forms.get(q["id"]) == "IV" and q["sectionKind"] == "single_choice"}
                for q in paper["questions"]:
                    if forms.get(q["id"]) != "V" or q["sectionKind"] != "single_choice":
                        continue
                    target = re.search(r"【同试卷\s*IV\s*第二、（(\d+)）题】", q["stem"])
                    if not target:
                        continue
                    reference_count += 1
                    with self.subTest(year=year, number=q["number"]):
                        self.assertEqual(q["options"], [])
                        self.assertEqual(q["status"], "partial")
                        self.assertEqual([o["label"] for o in iv[target.group(1)]["options"]],
                                         ["A.", "B.", "C.", "D."])
            self.assertEqual(reference_count, 24)


if __name__ == "__main__":
    unittest.main()
