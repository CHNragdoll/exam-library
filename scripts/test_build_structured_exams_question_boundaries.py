"""Questions printed as plain paragraphs must still start a new record."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import build_structured_exams as builder


class QuestionBoundaryTests(unittest.TestCase):
    def test_numbered_content_between_choice_questions_is_recovered(self):
        documents = {doc["id"]: doc for doc in json.loads(
            (builder.ROOT / "documents.json").read_text(encoding="utf-8"))}
        cases = (
            ("cs408:2014-complete", ("9", "10", "11")),
            ("politics:2019-questions", ("10", "11", "12", "13")),
            ("cet6:2014-12-01", ("21", "22")),
        )
        for document_id, numbers in cases:
            with self.subTest(document=document_id), tempfile.TemporaryDirectory() as folder:
                with patch.object(builder, "OUT", Path(folder)):
                    row = builder.build_one(documents[document_id])
                paper = json.loads((Path(folder) / row["json"]).read_text(encoding="utf-8"))
                questions = [q for q in paper["questions"] if q["recordType"] == "question"]
                positions = [next(i for i, q in enumerate(questions) if q["number"] == number)
                             for number in numbers]
                self.assertEqual(positions, list(range(positions[0], positions[0] + len(numbers))))
                recovered = numbers[1:-1] if len(numbers) > 2 else numbers[1:]
                for number in recovered:
                    question = questions[next(i for i, q in enumerate(questions) if q["number"] == number)]
                    self.assertEqual([o["label"] for o in question["options"]],
                                     ["A.", "B.", "C.", "D."])
                    self.assertNotIn(f"{int(number) + 1}．", question["options"][-1]["text"])


if __name__ == "__main__":
    unittest.main()
