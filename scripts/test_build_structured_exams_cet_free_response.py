"""Source-backed CET writing and translation question boundaries."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from scripts import build_structured_exams as builder


DOCUMENTS = {doc["id"]: doc for doc in json.loads(
    (builder.ROOT / "documents.json").read_text(encoding="utf-8"))}
TASK_IDS = {"q-writing-1", "q-translation-1"}


def is_cet_task(question: dict) -> bool:
    return question["id"].startswith(("q-writing-", "q-translation-"))


class CETFreeResponseTests(unittest.TestCase):
    def build(self, document_id: str) -> dict:
        doc = DOCUMENTS[document_id]
        with tempfile.TemporaryDirectory() as directory, patch.object(builder, "OUT", Path(directory)):
            builder.build_one(doc)
            output = Path(directory) / "papers" / doc["category"] / (Path(doc["reflow"]).stem + ".json")
            return json.loads(output.read_text(encoding="utf-8"))

    def test_2017_cet4_writing_and_translation_keep_printed_source_and_choice_ids(self) -> None:
        paper = self.build("cet4:2017-06-01")
        pdf = builder.ROOT.parent / "english-exams-web-2026-09-26/.firecrawl/cet4/2017-06-01.pdf"
        for page, phrase in ((1, "to sell a bicycle you used at college"),
                             (12, "黄河是亚洲第三")):
            source = subprocess.run(["pdftotext", "-f", str(page), "-l", str(page),
                                     "-layout", str(pdf), "-"], check=True,
                                    capture_output=True, text=True).stdout
            self.assertIn(phrase, source)
        original = json.loads((builder.OUT / "papers/cet4/2017-06-01.json").read_text(encoding="utf-8"))
        numbered = [question["id"] for question in paper["questions"] if question["id"] not in TASK_IDS]
        self.assertEqual(numbered, [question["id"] for question in original["questions"]
                                    if question["id"] not in TASK_IDS])
        self.assertEqual(len(numbered), 55)
        tasks = {question["id"]: question for question in paper["questions"]
                 if question["id"] in TASK_IDS}
        self.assertEqual(set(tasks), TASK_IDS)
        writing, translation = tasks["q-writing-1"], tasks["q-translation-1"]
        self.assertIn("to sell a bicycle you used at college", writing["stem"])
        self.assertEqual(writing["sourceBlocks"], ["b-1-3"])
        self.assertEqual(translation["sourceBlocks"], ["b-12-7", "b-12-8"])
        self.assertIn("黄河是亚洲第三", translation["stem"])
        self.assertNotIn("Directions:", translation["stem"])
        self.assertEqual(translation["context"]["instructionSourceBlocks"], ["b-12-7"])
        self.assertEqual(writing["labels"][0]["sourceBlockId"],
                         "cet4:2017-06-01:b-1-2")
        self.assertEqual(translation["labels"][0]["kind"], "translation")
        for task in tasks.values():
            self.assertEqual((task["questionType"], task["sectionKind"], task["options"]),
                             ("free_response", "free_response", []))
            self.assertEqual(task["answer"]["status"], "missing")
            self.assertEqual(task["context"]["sourceBlocks"], task["sourceBlocks"])

    def test_partial_2022_third_sets_have_only_the_two_printed_tasks(self) -> None:
        for document_id, passage in (("cet4:2022-06-03", "从前，有个农夫正在地里耕作"),
                                     ("cet6:2022-06-03", "赵州桥建于隋朝")):
            with self.subTest(document=document_id):
                paper = self.build(document_id)
                self.assertEqual([question["id"] for question in paper["questions"]],
                                 ["q-writing-1", "q-translation-1"])
                self.assertIn(passage, paper["questions"][1]["stem"])
                self.assertEqual(paper["questions"][0]["sourcePages"], ["1"])
                self.assertEqual(paper["questions"][1]["sourcePages"], ["1"])

    def test_image_only_translation_is_partial_and_cites_original_image(self) -> None:
        paper = self.build("cet4:2020-09-01")
        translation = next(question for question in paper["questions"]
                           if question["id"] == "q-translation-1")
        self.assertEqual(translation["status"], "partial")
        self.assertEqual(translation["context"]["figureSourceBlocks"], ["b-8-17"])
        image = next(block for block in paper["blocks"] if block["id"] == "b-8-17")
        self.assertTrue(image["images"])
        self.assertIn(image["id"], translation["sourceBlocks"])

    def test_combined_2020_cet6_pdf_keeps_both_printed_forms(self) -> None:
        paper = self.build("cet6:2020-09-02")
        tasks = {question["id"]: question for question in paper["questions"] if is_cet_task(question)}
        self.assertEqual(set(tasks), TASK_IDS | {"q-writing-2", "q-translation-2"})
        self.assertIn("What is worth doing is worth doing well", tasks["q-writing-1"]["stem"])
        self.assertIn("Wealth of the mind is the only true wealth", tasks["q-writing-2"]["stem"])
        self.assertIn("《红楼梦》", tasks["q-translation-1"]["stem"])
        self.assertEqual(tasks["q-translation-2"]["status"], "partial")
        self.assertEqual(tasks["q-translation-2"]["context"]["figureSourceBlocks"], ["b-8-11"])
        self.assertEqual(tasks["q-writing-2"]["number"], "Writing 2")
        self.assertEqual(tasks["q-translation-2"]["number"], "Translation 2")

    def test_fused_next_part_does_not_enter_writing_prompt(self) -> None:
        paper = self.build("cet4:2019-06-01")
        writing = next(question for question in paper["questions"] if question["id"] == "q-writing-1")
        raw = next(block for block in paper["blocks"]
                   if block["id"] == writing["context"]["instructionSourceBlocks"][0])
        self.assertIn("Listening Comprehension", raw["text"])
        self.assertNotIn("Listening Comprehension", writing["stem"])
        self.assertNotIn("Listening Comprehension", writing["context"]["text"])
        self.assertFalse(writing["stem"].rstrip().endswith("_"))

    def test_embedded_answer_pages_are_excluded_and_old_translation_stays_numbered(self) -> None:
        cet4 = self.build("cet4:2015-06-01")
        by_id = {block["id"]: block for block in cet4["blocks"]}
        for question in cet4["questions"]:
            if question["id"] in TASK_IDS:
                self.assertTrue(all(by_id[source_id].get("sourceSection") == "questions"
                                    for source_id in question["sourceBlocks"]))
        writing = next(question for question in cet4["questions"] if question["id"] == "q-writing-1")
        self.assertIn("b-1-4", writing["context"]["figureSourceBlocks"])
        old_cet6 = self.build("cet6:2012-06-01")
        self.assertIn("q-writing-1", {question["id"] for question in old_cet6["questions"]})
        self.assertNotIn("q-translation-1", {question["id"] for question in old_cet6["questions"]})
        self.assertTrue(any(question["number"] == "82" for question in old_cet6["questions"]))

    def test_all_cet_papers_have_source_backed_tasks_without_renumbering(self) -> None:
        counts = {"cet4": {"writing": 0, "translation": 0},
                  "cet6": {"writing": 0, "translation": 0}}
        paper_counts = {"cet4": 0, "cet6": 0}
        partial = 0
        with tempfile.TemporaryDirectory() as directory, patch.object(builder, "OUT", Path(directory)):
            for doc in DOCUMENTS.values():
                if doc["category"] not in counts:
                    continue
                paper_counts[doc["category"]] += 1
                builder.build_one(doc)
                stem = Path(doc["reflow"]).stem
                output = Path(directory) / "papers" / doc["category"] / (stem + ".json")
                paper = json.loads(output.read_text(encoding="utf-8"))
                original = json.loads((builder.ROOT / "structured/papers" / doc["category"] /
                                       (stem + ".json")).read_text(encoding="utf-8"))
                self.assertEqual([q["id"] for q in paper["questions"] if not is_cet_task(q)],
                                 [q["id"] for q in original["questions"] if not is_cet_task(q)],
                                 doc["id"])
                tasks = [q for q in paper["questions"] if is_cet_task(q)]
                self.assertTrue(tasks, doc["id"])
                partial += sum(q["status"] == "partial" for q in tasks)
                for q in tasks:
                    kind = "writing" if q["id"].startswith("q-writing-") else "translation"
                    counts[doc["category"]][kind] += 1
                    self.assertTrue(q["sourceBlocks"] and q["stem"], doc["id"])
        self.assertEqual(counts, {"cet4": {"writing": 71, "translation": 71},
                                  "cet6": {"writing": 82, "translation": 80}})
        self.assertEqual(paper_counts, {"cet4": 71, "cet6": 83})
        self.assertEqual(partial, 7)


if __name__ == "__main__":
    unittest.main()
