"""Keep printed political analysis answers linked to questions 34–38."""

import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch

from scripts import build_structured_exams as builder


PRINTED_ESSAY_KEY = re.compile(r"^\s*(\d{2})[.．、]\s*【(?:标准)?答案】\s*$")


class PoliticsEssayAnswerTests(unittest.TestCase):
    def test_2023_question_stems_use_pdf_verified_display_corrections(self):
        documents = {doc["id"]: doc for doc in json.loads(
            (builder.ROOT / "documents.json").read_text(encoding="utf-8"))}
        with tempfile.TemporaryDirectory() as directory, patch.object(builder, "OUT", Path(directory)):
            row = builder.build_one(documents["politics:2023-questions"])
            paper = json.loads((Path(directory) / row["json"]).read_text(encoding="utf-8"))
        questions = {question["number"]: question for question in paper["questions"]
                     if question["recordType"] == "question"}
        self.assertIn("二〇二〇年", questions["35"]["stem"])
        self.assertNotIn("二。二O年", questions["35"]["stem"])
        self.assertIn("\n\n材料1\n\n", questions["35"]["stem"])
        self.assertIn("\n\n材料2\n\n", questions["35"]["stem"])
        self.assertNotIn("-8 -", questions["36"]["stem"])
        source = {block["id"]: block for block in paper["blocks"]}
        self.assertIn("二。二O年", source["b-7-1"]["text"])
        self.assertTrue(source["b-8-2"]["text"].endswith("摘自《邓小平文选》第二卷"))
        self.assertNotIn("-8 -", source["b-8-2"]["text"])

    def test_2010_to_2020_source_essays_link_without_attached_2020_residue(self):
        documents = {doc["id"]: doc for doc in json.loads(
            (builder.ROOT / "documents.json").read_text(encoding="utf-8"))}
        with tempfile.TemporaryDirectory() as directory, patch.object(builder, "OUT", Path(directory)):
            for year in range(2010, 2021):
                with self.subTest(year=year):
                    answer_row = builder.build_one(documents[f"politics:{year}-answers"])
                    question_row = builder.build_one(documents[f"politics:{year}-questions"])
                    answer_paper = json.loads((Path(directory) / answer_row["json"]).read_text(encoding="utf-8"))
                    blocks = {block["id"]: block for block in answer_paper["blocks"]}
                    entries = builder.answer_entries(answer_paper)

                    for number in range(34, 39):
                        key = str(number)
                        printed = [question for question in answer_paper["questions"]
                                   if question["recordType"] == "answer"
                                   and question["number"] == key
                                   and PRINTED_ESSAY_KEY.fullmatch(question["stem"])]
                        self.assertEqual(len(printed), 1, (year, number))
                        question = printed[0]
                        used_blocks = []
                        for block_id in question["sourceBlocks"]:
                            block = blocks[block_id]
                            if block["role"] == "heading":
                                break  # The 2019 PDF appends an unrelated 2020 answer fragment.
                            used_blocks.append(block_id)
                        paragraphs = [blocks[block_id]["text"] for block_id in used_blocks
                                      if blocks[block_id]["role"] == "content"]
                        self.assertTrue(paragraphs, (year, number))
                        entry = entries[key]
                        self.assertEqual(entry["solution"], "\n".join(paragraphs), (year, number))
                        self.assertEqual(entry["sourceQuestionIds"], [question["id"]])
                        self.assertEqual(entry["sourceBlocks"], used_blocks)

                    builder.attach_answers([question_row, answer_row])
                    linked = json.loads((Path(directory) / question_row["json"]).read_text(encoding="utf-8"))
                    for number in range(34, 39):
                        question = next(question for question in linked["questions"]
                                        if question["recordType"] == "question"
                                        and question["number"] == str(number))
                        self.assertEqual(question["answer"]["status"], "explicit", (year, number))
                        self.assertEqual(question["answer"]["solution"], entries[str(number)]["solution"])
                        self.assertEqual(question["answer"]["sourceDocumentId"], f"politics:{year}-answers")
                    if year == 2019:
                        answer = next(question["answer"] for question in linked["questions"]
                                      if question["number"] == "38" and question["recordType"] == "question")
                        self.assertEqual(answer["sourcePages"], ["5"])
                        self.assertNotIn("中国特色社会主义制度行得通", answer["solution"])


if __name__ == "__main__":
    unittest.main()
