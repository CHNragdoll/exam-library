import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_english_paragraph_manifest import (PDF_VERIFIED_DIRECTION_NOTICES,
                                              PDF_VERIFIED_CROSS_PAGE_JOINS,
                                              PDF_VERIFIED_UNFILLED_CLOZE,
                                              PDF_VERIFIED_TEM_COVER,
                                              REFLOW, STRUCTURED, answer_option_records,
                                              build_paper as _build_paper, cloze_groups,
                                              listening_dictation_blocks,
                                              preserve_translations, protected_blanks,
                                              restored_text, sha256, strip_verified_direction_notice,
                                              strip_verified_page_footers)


def build_paper(*args, **kwargs):
    kwargs.setdefault("allow_missing_pdf", True)
    return _build_paper(*args, **kwargs)


def run(text, answer="A", continuation=False):
    first = {"type": "heading", "runs": [{"text": "Section I Use of English", "flags": [False, False, False]}]}
    prose = {"type": "paragraph", "runs": [
        {"text": text[0], "flags": [False, False, False]},
        {"text": " 1 ", "flags": [False, True, False]},
        {"text": text[1], "flags": [False, False, False]},
    ]}
    if continuation:
        prose["continues_previous_page"] = True
    raw = {"pages": [{"blocks": [first, prose]}]}
    context = {"kind": "passage", "passageSourceBlocks": ["b-1-2"], "text": ""}
    question = {"id": "q-1-1", "number": "1", "context": context,
                "answer": {"status": "explicit" if answer else "missing", "value": answer},
                "options": [{"label": "A.", "text": "enrich"}, {"label": "B.", "text": "damage"}]}
    paper = {"id": "kaoyan:2026-01", "category": "kaoyan", "questions": [question],
             "blocks": [{"id": "b-1-1", "role": "section", "text": "Section I Use of English"},
                        {"id": "b-1-2", "role": "content", "text": text[0] + " 1 " + text[1]}]}
    return build_paper(paper, raw, "source.json", "abc")


class ParagraphManifestTests(unittest.TestCase):
    def test_pdf_verified_bilingual_prompts_join_and_preserve_complete_cue(self):
        manifest = json.loads((REFLOW / "manifest.json").read_text())
        hashes = {f"{source['category']}:{Path(source['file']).stem}": source['source_pdf_sha256']
                  for source in manifest["papers"]}
        for paper_id, expected in (("cet6:2012-06-01", 3), ("cet6:2012-12-02", 2)):
            with self.subTest(paper_id=paper_id):
                category, stem = paper_id.split(":")
                raw = json.loads((REFLOW / category / "papers" / f"{stem}.json").read_text())
                paper = json.loads((STRUCTURED / "papers" / category / f"{stem}.json").read_text())
                result = build_paper(paper, raw, "source.json", hashes[paper_id])
                joined = [row for row in result["paragraphs"] if row.get("verifiedBilingualJoin")]
                self.assertEqual(len(joined), expected)
                self.assertTrue(all(row["translationEligible"] for row in joined))
                for row in joined:
                    self.assertEqual(len(row["sourceBlockIds"]), 2)
                    self.assertEqual(len(row["reflowBlockIds"]), 2)
                    self.assertEqual(len(row["protectedCues"]), 1)
                    self.assertIn(row["protectedCues"][0], row["translationInput"])
                    self.assertEqual(row["sourceHash"], sha256(row["sourceText"]))
                    attached = [source for source in result["sourceInventory"]
                                if source.get("paragraphId") == row["id"]]
                    self.assertEqual(len(attached), 2)

    def test_intact_bilingual_completion_marks_exact_chinese_cue(self):
        category, stem = "cet6", "2012-06-01"
        raw = json.loads((REFLOW / category / "papers" / f"{stem}.json").read_text())
        paper = json.loads((STRUCTURED / "papers" / category / f"{stem}.json").read_text())
        result = build_paper(paper, raw, "source.json",
                             "b0923d500beaef575eccc6ee67a3518f609f637cac54fd25be8db1f6238731e0")
        row = next(entry for entry in result["paragraphs"]
                   if entry["id"] == "cet6:2012-06-01:p:b-19-5")
        self.assertTrue(row["translationEligible"])
        self.assertTrue(row["protectedBlanks"])
        self.assertEqual(len(row["protectedCues"]), 1)
        self.assertIn(row["protectedCues"][0], row["translationInput"])

    def test_pdf_verified_cover_and_unanswered_cloze_are_excluded_or_ineligible(self):
        self.assertEqual(len(PDF_VERIFIED_TEM_COVER), 8)
        self.assertEqual(len(PDF_VERIFIED_UNFILLED_CLOZE), 9)
        for paper_id, pdf_hash in PDF_VERIFIED_TEM_COVER.items():
            category, stem = paper_id.split(":")
            raw = json.loads((REFLOW / category / "papers" / f"{stem}.json").read_text())
            paper = json.loads((STRUCTURED / "papers" / category / f"{stem}.json").read_text())
            result = build_paper(paper, raw, "source.json", pdf_hash)
            cover = next(row for row in result["sourceInventory"]
                         if row["sourceBlockId"] == f"{paper_id}:b-1-3")
            self.assertEqual((cover["classification"], cover["reason"]),
                             ("excluded", "pdf_verified_cover_metadata"))
            self.assertFalse(any(row["id"] == f"{paper_id}:p:b-1-3"
                                 for row in result["paragraphs"]))
        for paper_id, pdf_hash, block_id in PDF_VERIFIED_UNFILLED_CLOZE:
            category, stem = paper_id.split(":")
            raw = json.loads((REFLOW / category / "papers" / f"{stem}.json").read_text())
            paper = json.loads((STRUCTURED / "papers" / category / f"{stem}.json").read_text())
            result = build_paper(paper, raw, "source.json", pdf_hash)
            row = next(entry for entry in result["paragraphs"]
                       if f"{paper_id}:{block_id}" in entry["reflowBlockIds"])
            self.assertFalse(row["translationEligible"])
            self.assertIsNone(row["translationInput"])

    def test_pdf_verified_split_cet6_answer_option_aliases_existing_paragraph(self):
        category, stem = "cet6", "2014-12-01"
        raw = json.loads((REFLOW / category / "papers" / f"{stem}.json").read_text())
        paper = json.loads((STRUCTURED / "papers" / category / f"{stem}.json").read_text())
        result = build_paper(paper, raw, "source.json",
                             "32237ba2134b9f441aa766a02e09e4a1e71e738aee16df7274076ff34d6795e7")
        option = next(row for row in result["options"]
                      if row["id"] == "cet6:2014-12-01:q-22-1:A")
        self.assertEqual(option["coverageStatus"], "covered_by_paragraph")
        self.assertEqual(option["translationRef"], "cet6:2014-12-01:p:b-2-33")
        self.assertEqual(option["sourceBlockIds"], ["cet6:2014-12-01:b-2-33"])
        paragraph = next(row for row in result["paragraphs"]
                         if row["id"] == option["translationRef"])
        self.assertEqual(paragraph["kind"], "question_prompt")

    def test_pdf_verified_english_two_table_translates_each_choice_once(self):
        category, stem = "kaoyan", "2026-02"
        raw = json.loads((REFLOW / category / "papers" / f"{stem}.json").read_text())
        paper = json.loads((STRUCTURED / "papers" / category / f"{stem}.json").read_text())
        result = build_paper(paper, raw, "source.json",
                             "99477c6b3d2fafe0c66c26662c6143ca1e7488d73d0e651a3693744c455ade64")
        table = [row for row in result["options"] if row.get("pdfVerifiedSource")]
        self.assertEqual(len(table), 35)
        self.assertEqual(sum(row["translationEligible"] for row in table), 7)
        self.assertEqual(sum(row.get("coverageStatus") == "covered_by_option" for row in table), 28)
        first = next(row for row in table if row["id"] == "kaoyan:2026-02:q-41-1:A")
        repeat = next(row for row in table if row["id"] == "kaoyan:2026-02:q-42-1:A")
        self.assertEqual(first["reflowBlockIds"], ["kaoyan:2026-02:b-12-4"])
        self.assertEqual(first["sourceBlockIds"], [])
        self.assertEqual(repeat["translationRef"], first["id"])

    def test_repaired_cet_word_bank_uses_exact_raw_item_anchor(self):
        category, stem = "cet4", "2020-12-01"
        raw = json.loads((REFLOW / category / "papers" / f"{stem}.json").read_text())
        paper = json.loads((STRUCTURED / "papers" / category / f"{stem}.json").read_text())
        manifest = json.loads((REFLOW / "manifest.json").read_text())
        source = next(row for row in manifest["papers"]
                      if row["category"] == category and Path(row["file"]).stem == stem)
        result = build_paper(paper, raw, "source.json", source["source_pdf_sha256"])
        word = next(row for row in result["options"]
                    if row["id"] == "cet4:2020-12-01:word-bank:J")
        self.assertTrue(word["translationEligible"])
        self.assertEqual(word["eligibilityReason"], "translate")
        self.assertEqual(word["sourceText"], "records")
        self.assertEqual(word["translationInput"], "records")
        self.assertEqual(word["reflowBlockId"], "cet4:2020-12-01:b-4-4")
        self.assertEqual(word["reflowOptionIndex"], 9)
        self.assertEqual(word["reflowSourceText"], "records")
        self.assertNotIn("pdfVerifiedSource", word)

    def test_option_spacing_uses_exact_raw_input_but_never_changes_a_glyph(self):
        paper = {"id": "cet4:fixture", "blocks": [{"id": "b-1-1", "role": "choices",
                 "text": "A. furniture ."}], "questions": [{"id": "q-1-1", "sourcePages": [1],
                 "sourceBlocks": ["b-1-1"], "options": [{"label": "A.", "text": "furniture ."}]}]}
        raw = {"pages": [{"blocks": [{"type": "options", "items": [
            {"label": "A", "runs": [{"text": "furniture."}]}]}]}]}
        rows, _ = answer_option_records(paper, raw, [])
        option = rows[0]
        self.assertTrue(option["translationEligible"])
        self.assertEqual(option["sourceText"], "furniture .")
        self.assertEqual(option["sourceHash"], sha256("furniture ."))
        self.assertEqual(option["reflowSourceText"], "furniture.")
        self.assertEqual(option["translationInput"], "furniture.")
        paper["questions"][0]["options"][0]["text"] = "furniturf ."
        rows, _ = answer_option_records(paper, raw, [])
        self.assertFalse(rows[0]["translationEligible"])
        self.assertEqual(rows[0]["eligibilityReason"], "missing_raw_option_anchor")

    def test_real_choice_row_and_word_bank_options_keep_api_and_raw_provenance(self):
        for category, stem, option_id, raw_id, index, expected_text in (
            ("kaoyan", "2026-01", "kaoyan:2026-01:q-1-1:A",
             "kaoyan:2026-01:b-2-1", 0, "Still"),
            ("cet4", "2020-12-01", "cet4:2020-12-01:word-bank:A",
             None, None, "constantly"),
        ):
            with self.subTest(option_id=option_id):
                raw = json.loads((REFLOW / category / "papers" / f"{stem}.json").read_text())
                paper = json.loads((STRUCTURED / "papers" / category / f"{stem}.json").read_text())
                pdf_hash = ("5ae3d9b5333e3cf3d02922dc4bc329e016dd2c3738307fe12a525a4e55535f37"
                            if category == "cet4" else "abc")
                result = build_paper(paper, raw, "source.json", pdf_hash)
                option = next(row for row in result["options"] if row["id"] == option_id)
                self.assertEqual(option["sourceText"], expected_text)
                self.assertEqual(option["sourceHash"], sha256(expected_text))
                self.assertTrue(option["translationEligible"])
                self.assertEqual(option["translationInput"], expected_text)
                if raw_id:
                    self.assertEqual(option["reflowBlockId"], raw_id)
                    self.assertEqual(option["reflowOptionIndex"], index)

    def test_shared_part_b_option_alias_requires_complete_exact_paragraph(self):
        raw = json.loads((REFLOW / "kaoyan/papers/2005-01.json").read_text())
        paper = json.loads((STRUCTURED / "papers/kaoyan/2005-01.json").read_text())
        result = build_paper(paper, raw, "source.json",
                             "5cb2fbee199b3aa63f1edd42989963dd2d7d617df241ecd135199f7c721d2003")
        options = {row["id"]: row for row in result["options"]}
        complete = options["kaoyan:2005-01:q-41-1:B"]
        self.assertEqual(complete["coverageStatus"], "covered_by_paragraph")
        self.assertFalse(complete["translationEligible"])
        self.assertEqual(complete["translationRef"], "kaoyan:2005-01:p:b-12-5")
        restored = options["kaoyan:2005-01:q-41-1:A"]
        self.assertEqual(restored["coverageStatus"], "covered_by_paragraph")
        self.assertEqual(restored["translationRef"], "kaoyan:2005-01:p:b-12-3")
        passage = next(row for row in result["paragraphs"]
                       if row["id"] == restored["translationRef"])
        self.assertEqual(passage["reflowBlockIds"],
                         ["kaoyan:2005-01:b-12-3", "kaoyan:2005-01:b-12-4"])

    def test_part_b_option_alias_accepts_only_same_block_layout_spaces(self):
        category, stem = "kaoyan", "2017-01"
        raw = json.loads((REFLOW / category / "papers" / f"{stem}.json").read_text())
        paper = json.loads((STRUCTURED / "papers" / category / f"{stem}.json").read_text())
        result = build_paper(paper, raw, "source.json",
                             "ea30380d06d08b084f915cd757c7e96dbf5b3ecdc0f05afbdfeca99fa6ad223d")
        aliased = [row for row in result["options"]
                   if row["id"].startswith("kaoyan:2017-01:q-41-1:") and
                   row.get("coverageStatus") == "covered_by_paragraph"]
        self.assertEqual(len(aliased), 5)
        self.assertEqual(aliased[0]["sourceBlockIds"], ["kaoyan:2017-01:b-11-4"])
        paragraph = next(row for row in result["paragraphs"]
                         if row["id"] == aliased[0]["translationRef"])
        self.assertEqual(paragraph["sourceBlockIds"], aliased[0]["sourceBlockIds"])

    def test_pdf_verified_page_furniture_is_not_translated(self):
        raw = json.loads((REFLOW / "cet6/papers/2020-07-01.json").read_text())
        paper = json.loads((STRUCTURED / "papers/cet6/2020-07-01.json").read_text())
        result = build_paper(paper, raw, "source.json",
                             "be125ae4035ebd1bea079cf0248d391c023c533433dccf4427da930df743e612")
        record = next(row for row in result["sourceInventory"]
                      if row["sourceBlockId"] == "cet6:2020-07-01:b-13-2")
        self.assertEqual((record["classification"], record["reason"]),
                         ("excluded", "pdf_verified_page_furniture"))

    def test_pdf_verified_cross_page_pairs_join_without_footer_or_unanswered_cloze(self):
        self.assertEqual(len(PDF_VERIFIED_CROSS_PAGE_JOINS), 17)
        for (paper_id, pdf_hash, to_id), case in PDF_VERIFIED_CROSS_PAGE_JOINS.items():
            with self.subTest(paper_id=paper_id, to_id=to_id):
                category, stem = paper_id.split(":")
                raw = json.loads((REFLOW / category / "papers" / f"{stem}.json").read_text())
                paper = json.loads((STRUCTURED / "papers" / category / f"{stem}.json").read_text())
                result = build_paper(paper, raw, "source.json", pdf_hash)
                matches = [row for row in result["paragraphs"]
                           if f"{paper_id}:{to_id}" in row["reflowBlockIds"]]
                self.assertEqual(len(matches), 1)
                entry = matches[0]
                self.assertIn(f"{paper_id}:{case['fromBlockId']}", entry["reflowBlockIds"])
                self.assertIn(case["footer"], entry["sourceText"])
                self.assertIn(case["footer"], entry["verifiedCrossPageFooters"])
                if case["unverifiedCloze"]:
                    self.assertFalse(entry["translationEligible"])
                    self.assertIsNone(entry["translationInput"])
                else:
                    self.assertTrue(entry["translationEligible"])
                    self.assertNotIn(case["footer"], entry["translationInput"])
        paper_id = "cet6:2017-06-01"
        raw = json.loads((REFLOW / "cet6/papers/2017-06-01.json").read_text())
        paper = json.loads((STRUCTURED / "papers/cet6/2017-06-01.json").read_text())
        pdf_hash = next(key[1] for key in PDF_VERIFIED_CROSS_PAGE_JOINS if key[0] == paper_id)
        result = build_paper(paper, raw, "source.json", pdf_hash)
        inputs = "\n".join(row["translationInput"] or "" for row in result["paragraphs"])
        self.assertIn("thereby add", inputs)
        self.assertIn("multidisciplinary repository", inputs)
        self.assertIn("those roles", inputs)

    def test_pdf_verified_direction_notices_only_leave_translation_input(self):
        self.assertEqual(len(PDF_VERIFIED_DIRECTION_NOTICES), 53)
        manifest = json.loads((REFLOW / "manifest.json").read_text())
        pdf_by_paper = {f"{item['category']}:{Path(item['file']).stem}": item["source_pdf_sha256"]
                        for item in manifest["papers"]}
        for (paper_id, paragraph_id, source_hash, pdf_hash), (edge, notice) in PDF_VERIFIED_DIRECTION_NOTICES.items():
            with self.subTest(paper_id=paper_id):
                self.assertEqual(pdf_by_paper[paper_id], pdf_hash)
                category, stem = paper_id.split(":")
                raw = json.loads((REFLOW / category / "papers" / f"{stem}.json").read_text())
                paper = json.loads((STRUCTURED / "papers" / category / f"{stem}.json").read_text())
                result = build_paper(paper, raw, "source.json", pdf_hash)
                entry = next(row for row in result["paragraphs"] if row["id"] == paragraph_id)
                self.assertTrue(entry["translationEligible"])
                self.assertEqual(entry["sourceHash"], source_hash)
                self.assertEqual(entry["sourceHash"], sha256(entry["sourceText"]))
                expected = (entry["sourceText"][len(notice):] if edge == "prefix"
                            else entry["sourceText"][:-len(notice)])
                if entry.get("verifiedCrossPageFooters"):
                    self.assertNotIn(notice, entry["translationInput"])
                    for footer in entry["verifiedCrossPageFooters"]:
                        self.assertNotIn(footer, entry["translationInput"])
                else:
                    self.assertEqual(entry["translationInput"], expected)
                self.assertEqual(entry["translationInputHash"], sha256(entry["translationInput"]))
                self.assertIn("verified_direction_notice", [issue["code"] for issue in result["issues"]])

        paper_id, paragraph_id, source_hash, pdf_hash = next(iter(PDF_VERIFIED_DIRECTION_NOTICES))
        notice = PDF_VERIFIED_DIRECTION_NOTICES[(paper_id, paragraph_id, source_hash, pdf_hash)][1]
        entry = {"id": paragraph_id, "sourceHash": source_hash,
                 "sourceText": notice + "Directions: Answer the questions.",
                 "translationInput": notice + "Directions: Answer the questions."}
        self.assertIsNone(strip_verified_direction_notice(paper_id, "wrong PDF", entry))
        self.assertIsNone(strip_verified_direction_notice(paper_id, pdf_hash,
                          {**entry, "sourceHash": "changed source"}))
        self.assertIsNone(strip_verified_direction_notice(paper_id, pdf_hash,
                          {**entry, "translationInput": "Directions: " + notice + "Answer."}))

    def test_underscore_in_printed_word_is_not_a_blank(self):
        text = "37. People from different races, _genders, and regions all suffer from a lack of financial security."
        self.assertEqual(protected_blanks(text), [])
        self.assertEqual(protected_blanks("Students chose (31) ______ before answering _genders."),
                         ["(31) ______"])
        self.assertEqual(protected_blanks("expresses________. (36) _______dangerous"),
                         ["________", "(36) _______"])
        self.assertEqual(protected_blanks("that__________________. (36)_________improvement"),
                         ["__________________", "(36)_________"])
        raw = json.loads((REFLOW / "cet4/papers/2020-12-02.json").read_text())
        paper = json.loads((STRUCTURED / "papers/cet4/2020-12-02.json").read_text())
        rows = build_paper(paper, raw, "source.json", "irrelevant PDF")["paragraphs"]
        entry = next(row for row in rows if row["id"] == "cet4:2020-12-02:p:b-6-3")
        self.assertEqual(entry["sourceText"], text)
        self.assertEqual(entry["translationInput"], text)
        self.assertEqual(entry["protectedBlanks"], [])
        raw = json.loads((REFLOW / "cet6/papers/2012-12-02.json").read_text())
        paper = json.loads((STRUCTURED / "papers/cet6/2012-12-02.json").read_text())
        rows = build_paper(paper, raw, "source.json",
                           "e75b7941475cf515f43b58bed01ec452ca8431dbaf5181a6e9c49d081f42cdbc")
        printed = next(row for row in rows["paragraphs"]
                       if row["id"] == "cet6:2012-12-02:p:b-4-12")
        self.assertEqual(printed["protectedBlanks"], ["_"])

    def test_verified_cloze_restores_only_translation_input(self):
        result = run(("Thoughtful reading can ", " our daily lives and improve our judgment."))
        paragraph = result["paragraphs"][0]
        self.assertEqual(paragraph["sourceText"],
                         "Thoughtful reading can  1  our daily lives and improve our judgment.")
        self.assertEqual(paragraph["translationInput"],
                         "Thoughtful reading can  enrich  our daily lives and improve our judgment.")
        self.assertTrue(paragraph["translationEligible"])
        self.assertEqual(paragraph["sourceBlockIds"], ["kaoyan:2026-01:b-1-2"])
        self.assertEqual(paragraph["translationInputHash"], sha256(paragraph["translationInput"]))

    def test_missing_answer_keeps_source_and_excludes_translation(self):
        result = run(("Thoughtful reading can ", " our daily lives and improve our judgment."), answer=None)
        paragraph = result["paragraphs"][0]
        self.assertFalse(paragraph["translationEligible"])
        self.assertIsNone(paragraph["translationInput"])
        self.assertIn("unresolved_answer:1", paragraph["unresolvedBlanks"])

    def test_stale_translation_retained_for_recovery(self):
        result = run(("Thoughtful reading can ", " our daily lives and improve our judgment."))
        old = {"paragraphs": [{**result["paragraphs"][0], "translationZh": "经过核实的旧译文"}]}
        preserve_translations(result, old)
        self.assertEqual(result["paragraphs"][0]["translationZh"], "经过核实的旧译文")
        changed = run(("Thoughtful reading may ", " our daily lives and improve our judgment."))
        preserve_translations(changed, old)
        self.assertIsNone(changed["paragraphs"][0]["translationZh"])
        self.assertEqual(changed["staleTranslations"][0]["translationZh"], "经过核实的旧译文")

    def test_reading_paragraph_option_and_writing_boundary(self):
        texts = ["Section II Reading Comprehension",
                 "A) This is a complete reading paragraph with enough English words to be meaningful.",
                 "Section III Writing",
                 "Write a short essay about a topic of your own choosing and explain it."]
        raw = {"pages": [{"blocks": [
            {"type": "heading" if index in {0, 2} else "paragraph",
             "runs": [{"text": text, "flags": [False, False, False]}]}
            for index, text in enumerate(texts)]}]}
        paper = {"id": "kaoyan:2026-01", "category": "kaoyan", "questions": [],
                 "blocks": [{"id": f"b-1-{index+1}",
                             "role": "section" if index in {0, 2} else "content", "text": text}
                            for index, text in enumerate(texts)]}
        result = build_paper(paper, raw, "source.json", "abc")
        self.assertEqual([item["kind"] for item in result["paragraphs"]],
                         ["passage_option", "writing_prompt"])
        self.assertEqual(result["sourceInventory"][-1]["reason"], "section_writing")

    def test_unparsed_tem4_cloze_is_visible_but_ineligible(self):
        texts = ["PART IV CLOZE (10 MIN)",
                 "The scholar wrote (31) ______ and then explained the result in several clear sentences."]
        raw = {"pages": [{"blocks": [
            {"type": "heading" if index == 0 else "paragraph",
             "runs": [{"text": text, "flags": [False, False, False]}]}
            for index, text in enumerate(texts)]}]}
        paper = {"id": "tem4:2024", "category": "tem4", "questions": [],
                 "blocks": [{"id": "b-1-1", "role": "section", "text": texts[0]},
                            {"id": "b-1-2", "role": "content", "text": texts[1]}]}
        paragraph = build_paper(paper, raw, "source.json", "abc")["paragraphs"][0]
        self.assertEqual(paragraph["kind"], "cloze")
        self.assertFalse(paragraph["translationEligible"])
        self.assertIsNone(paragraph["translationInput"])

    def test_changed_structured_block_never_enters_translation_queue(self):
        text = "A) This is a full reading paragraph with enough words to check source identity."
        raw = {"pages": [{"blocks": [
            {"type": "heading", "runs": [{"text": "Section II Reading Comprehension"}]},
            {"type": "paragraph", "runs": [{"text": text}]},
        ]}]}
        paper = {"id": "kaoyan:2026-01", "category": "kaoyan", "questions": [],
                 "blocks": [{"id": "b-1-1", "role": "section", "text": "Section II Reading Comprehension"},
                            {"id": "b-1-2", "role": "content", "text": "A different paragraph was here."}]}
        result = build_paper(paper, raw, "source.json", "abc")
        self.assertFalse(result["paragraphs"][0]["translationEligible"])
        self.assertIn("source_block_mismatch", [issue["code"] for issue in result["issues"]])

    def test_structured_punctuation_change_is_not_normalized_away(self):
        text = "The author measured the change, then checked the result carefully."
        raw = {"pages": [{"blocks": [{"type": "paragraph", "runs": [{"text": text}]}]}]}
        paper = {"id": "cet4:2024-06-01", "category": "cet4", "questions": [],
                 "blocks": [{"id": "b-1-1", "role": "content",
                             "text": text.replace("change,", "change.")}]}
        result = build_paper(paper, raw, "source.json", "abc")
        self.assertFalse(result["paragraphs"][0]["translationEligible"])
        self.assertIn("source_block_mismatch", [issue["code"] for issue in result["issues"]])

    def test_plain_cet_marker_restoration_requires_unique_number(self):
        value = "Careful readers can __26__ confusing claims and make better decisions."
        raw = {"pages": [{"blocks": [{"type": "paragraph", "runs": [{"text": value, "flags": [False, False, False]}]}]}]}
        context = {"kind": "word_bank_cloze", "passageSourceBlocks": ["b-1-1"],
                   "wordBankStatus": "complete", "printedBlankNumbers": [26],
                   "sourceNumberUnverifiedNumbers": [],
                   "wordBank": [{"label": "A.", "text": "identify"}]}
        question = {"id": "q-26-1", "number": "26", "context": context,
                    "answer": {"status": "explicit", "value": "A"}}
        by_block, issues = cloze_groups({"questions": [question]}, raw)
        self.assertFalse(issues)
        self.assertEqual(restored_text(raw["pages"][0]["blocks"][0], "b-1-1", by_block["b-1-1"]),
                         "Careful readers can identify confusing claims and make better decisions.")
        raw["pages"][0]["blocks"][0]["runs"][0]["text"] += " Number 26 appears twice."
        by_block, issues = cloze_groups({"questions": [question]}, raw)
        self.assertFalse(issues)
        self.assertTrue(by_block["b-1-1"]["eligible"])

    def test_bare_cet_number_is_not_a_verified_blank(self):
        value = "The report counted 26 distinct claims before making a careful final decision."
        raw = {"pages": [{"blocks": [{"type": "paragraph", "runs": [
            {"text": value, "flags": [False, False, False]}]}]}]}
        context = {"kind": "word_bank_cloze", "passageSourceBlocks": ["b-1-1"],
                   "wordBankStatus": "complete", "printedBlankNumbers": [26],
                   "wordBank": [{"label": "A.", "text": "identify"}]}
        question = {"id": "q-26-1", "number": "26", "context": context,
                    "answer": {"status": "explicit", "value": "A"}}
        by_block, issues = cloze_groups({"questions": [question]}, raw)
        self.assertFalse(by_block["b-1-1"]["eligible"])
        self.assertEqual(by_block["b-1-1"]["replacements"], {})
        self.assertIn("blank_marker_count:26:0", issues[0]["reasons"])

    def test_unreadable_ocr_replacement_never_enters_translation_queue(self):
        value = "The researcher explained the surprising result ���� before the next experiment."
        raw = {"pages": [{"blocks": [{"type": "paragraph", "runs": [{"text": value}]}]}]}
        paper = {"id": "cet6:2024-06-01", "category": "cet6", "questions": [],
                 "blocks": [{"id": "b-1-1", "role": "content", "text": value}]}
        result = build_paper(paper, raw, "source.json", "abc")
        self.assertFalse(result["paragraphs"][0]["translationEligible"])
        self.assertIsNone(result["paragraphs"][0]["translationInput"])
        self.assertEqual(result["sourceInventory"][0]["reason"], "source_unreadable")
        self.assertIn("source_unreadable", [issue["code"] for issue in result["issues"]])

    def test_cross_page_prose_has_one_paragraph_and_two_source_blocks(self):
        left = "An original reading passage describes how people across several communities can"
        right = "work together to solve a shared problem in a thoughtful way."
        raw = {"pages": [
            {"blocks": [{"type": "heading", "runs": [{"text": "Section II Reading Comprehension"}]},
                        {"type": "paragraph", "runs": [{"text": left}]}]},
            {"blocks": [{"type": "paragraph", "continues_previous_page": True,
                         "runs": [{"text": right}]}]},
        ]}
        paper = {"id": "kaoyan:2026-01", "category": "kaoyan", "questions": [],
                 "blocks": [{"id": "b-1-1", "role": "section", "text": "Section II Reading Comprehension"},
                            {"id": "b-1-2", "role": "content", "text": left},
                            {"id": "b-2-1", "role": "content", "text": right}]}
        result = build_paper(paper, raw, "source.json", "abc")
        self.assertEqual(len(result["paragraphs"]), 1)
        paragraph = result["paragraphs"][0]
        self.assertEqual(paragraph["sourceText"], left + " " + right)
        self.assertEqual(paragraph["sourceBlockIds"],
                         ["kaoyan:2026-01:b-1-2", "kaoyan:2026-01:b-2-1"])
        self.assertEqual(paragraph["sourceHash"], sha256(left + " " + right))

    def test_question_prompt_retains_visible_blank_without_answer_guessing(self):
        text = "Which result did the researcher _______ after observing the experiment?"
        raw = {"pages": [{"blocks": [{"type": "question", "runs": [{"text": text}]}]}]}
        paper = {"id": "cet4:2024-06-01", "category": "cet4", "questions": [],
                 "blocks": [{"id": "b-1-1", "role": "question", "text": text}]}
        paragraph = build_paper(paper, raw, "source.json", "abc")["paragraphs"][0]
        self.assertEqual(paragraph["kind"], "question_prompt")
        self.assertTrue(paragraph["translationEligible"])
        self.assertEqual(paragraph["translationInput"], text)
        self.assertEqual(paragraph["protectedBlanks"], ["_______"])

    def test_lettered_reading_option_and_continuation_form_one_paragraph(self):
        first = "What motivates readers to finish difficult books? Curiosity, for some. The promise of"
        tail = "new knowledge, for others. Both reasons can sustain a careful reading practice."
        raw = {"pages": [{"blocks": [
            {"type": "heading", "runs": [{"text": "Part III Reading Comprehension"}]},
            {"type": "heading", "runs": [{"text": "Section B"}]},
            {"type": "options", "items": [{"label": "A", "runs": [{"text": first}]}]},
            {"type": "paragraph", "runs": [{"text": tail}]},
            {"type": "paragraph", "runs": [{"text":
                "B) A separate reading paragraph explains why practice can improve memory over time."}]},
        ]}]}
        paper = {"id": "cet4:2024-06-01", "category": "cet4", "questions": [],
                 "blocks": [{"id": "b-1-1", "role": "section", "text": "Part III Reading Comprehension"},
                            {"id": "b-1-2", "role": "section", "text": "Section B"},
                            {"id": "b-1-3", "role": "choices", "text": "A. " + first},
                            {"id": "b-1-4", "role": "content", "text": tail},
                            {"id": "b-1-5", "role": "content", "text":
                             "B) A separate reading paragraph explains why practice can improve memory over time."}]}
        result = build_paper(paper, raw, "source.json", "abc")
        self.assertEqual(len(result["paragraphs"]), 2)
        paragraph = result["paragraphs"][0]
        self.assertEqual(paragraph["kind"], "passage_option")
        self.assertEqual(paragraph["sourceText"], "A. " + first + " " + tail)
        self.assertEqual(paragraph["sourceBlockIds"],
                         ["cet4:2024-06-01:b-1-3", "cet4:2024-06-01:b-1-4"])
        self.assertEqual(result["reconciliation"]["included"], 3)

    def test_markerless_roman_reading_option_o_keeps_its_continuation(self):
        first = "A careful reader can learn from a demanding book, although the first chapter"
        tail = "may be difficult. The rest of the argument then becomes much clearer."
        raw = {"pages": [{"blocks": [
            {"type": "paragraph", "runs": [{"text": "Part ⅢReading Comprehension"}]},
            {"type": "options", "items": [{"label": "O", "runs": [{"text": first}]}]},
            {"type": "paragraph", "runs": [{"text": tail}]},
        ]}]}
        paper = {"id": "cet4:2024-06-01", "category": "cet4", "questions": [],
                 "blocks": [{"id": "b-1-1", "role": "section", "text": "Part ⅢReading Comprehension"},
                            {"id": "b-1-2", "role": "choices", "text": "O. " + first},
                            {"id": "b-1-3", "role": "content", "text": tail}]}
        result = build_paper(paper, raw, "source.json", "abc")
        self.assertEqual(len(result["paragraphs"]), 1)
        entry = result["paragraphs"][0]
        self.assertEqual(entry["kind"], "passage_option")
        self.assertEqual(entry["sourceText"], "O. " + first + " " + tail)
        self.assertTrue(entry["translationEligible"])

    def test_new_lettered_paragraph_is_never_joined_to_previous_choice(self):
        choices = [
            "F) This paragraph describes why careful reading helps people think through hard problems.",
            "G) “A different paragraph begins with a quotation and develops another useful idea.”",
            "P) . A final paragraph starts with a damaged punctuation mark but still has its own label.",
        ]
        raw = {"pages": [{"blocks": [
            {"type": "heading", "runs": [{"text": "Part III Reading Comprehension"}]},
            *({"type": "paragraph", "runs": [{"text": value}]} for value in choices),
        ]}]}
        paper = {"id": "cet4:2024-06-01", "category": "cet4", "questions": [],
                 "blocks": [{"id": "b-1-1", "role": "section", "text": "Part III Reading Comprehension"},
                            *({"id": f"b-1-{index}", "role": "content", "text": value}
                              for index, value in enumerate(choices, 2))]}
        result = build_paper(paper, raw, "source.json", "abc")
        self.assertEqual([entry["sourceText"] for entry in result["paragraphs"]], choices)
        self.assertTrue(all(entry["kind"] == "passage_option" for entry in result["paragraphs"]))

    def test_pdf_verified_damaged_cloze_heading_cannot_be_translated(self):
        raw = json.loads((REFLOW / "cet4/papers/2021-12-02.json").read_text())
        paper = json.loads((STRUCTURED / "papers/cet4/2021-12-02.json").read_text())
        pdf_hash = "a7c3240ab8227732026cf0b7b0bd0841111d4c361bc078e2147aa1c954e44f1b"
        result = build_paper(paper, raw, "source.json", pdf_hash)
        for number in range(9, 28):
            entry = next((row for row in result["paragraphs"]
                          if row["id"] == f"cet4:2021-12-02:p:b-4-{number}"), None)
            if entry is not None:
                self.assertFalse(entry["translationEligible"])
                self.assertIsNone(entry["translationInput"])

    def test_shifted_structured_ids_follow_embedded_source_markers(self):
        left = "Thoughtful reading can "
        right = " our daily lives and improve our judgment."
        raw = {"pages": [{"blocks": [
            {"type": "heading", "runs": [{"text": "Section I Use of English"}]},
            {"type": "paragraph", "runs": [
                {"text": left, "flags": [False, False, False]},
                {"text": " 1 ", "flags": [False, True, False]},
                {"text": right, "flags": [False, False, False]},
            ]},
        ]}]}
        paper = {"id": "kaoyan:2026-01", "category": "kaoyan",
                 "questions": [{"id": "q-1-1", "number": "1",
                                "context": {"kind": "passage", "passageSourceBlocks": ["b-1-3"]},
                                "answer": {"status": "explicit", "value": "A"},
                                "options": [{"label": "A.", "text": "enrich"}]}],
                 "blocks": [
                     {"id": "b-1-2", "role": "section", "text": "Section I Use of English",
                      "contentHtml": '<h2 data-source-block-id="b-1-1">Section I Use of English</h2>'},
                     {"id": "b-1-3", "role": "content", "text": left + " 1 " + right,
                      "contentHtml": '<p data-source-block-id="b-1-2">passage</p>'},
                 ]}
        result = build_paper(paper, raw, "source.json", "abc")
        self.assertFalse(result["issues"])
        paragraph = result["paragraphs"][0]
        self.assertEqual(paragraph["sourceBlockIds"], ["kaoyan:2026-01:b-1-3"])
        self.assertEqual(paragraph["reflowBlockIds"], ["kaoyan:2026-01:b-1-2"])
        self.assertEqual(paragraph["translationInput"], left + " enrich " + right)

    def test_mixed_chinese_task_translates_only_english_directions(self):
        direction = ("Directions: For this part, you are allowed 30 minutes to translate "
                     "a passage from Chinese into English. You should write your answer on Answer Sheet 2.")
        text = direction + " 中国文化历史悠久，内容丰富。"
        raw = {"pages": [{"blocks": [{"type": "paragraph", "runs": [{"text": text}]}]}]}
        paper = {"id": "cet4:2024-06-01", "category": "cet4", "questions": [],
                 "blocks": [{"id": "b-1-1", "role": "content", "text": text,
                             "contentHtml": '<p data-source-block-id="b-1-1">text</p>'}]}
        result = build_paper(paper, raw, "source.json", "abc")
        paragraph = result["paragraphs"][0]
        self.assertTrue(paragraph["translationEligible"])
        self.assertEqual(paragraph["sourceText"], text)
        self.assertEqual(paragraph["translationInput"], direction)
        self.assertEqual(paragraph["kind"], "instruction")

    def test_cross_page_join_maps_two_raw_blocks_to_one_structured_block(self):
        left = "An original reading passage describes how people across several communities can"
        right = "work together to solve a shared problem in a thoughtful way."
        raw = {"pages": [
            {"blocks": [{"type": "heading", "runs": [{"text": "Section II Reading Comprehension"}]},
                        {"type": "paragraph", "runs": [{"text": left}]}]},
            {"blocks": [{"type": "paragraph", "continues_previous_page": True,
                         "runs": [{"text": right}]}]},
        ]}
        paper = {"id": "kaoyan:2026-01", "category": "kaoyan", "questions": [],
                 "blocks": [
                     {"id": "b-1-1", "role": "section", "text": "Section II Reading Comprehension",
                      "contentHtml": '<h2 data-source-block-id="b-1-1">section</h2>'},
                     {"id": "b-1-2", "role": "content", "text": left + " " + right,
                      "contentHtml": ('<p><span data-source-block-id="b-1-2"></span>'
                                      '<span data-source-block-id="b-2-1"></span></p>')},
                 ]}
        result = build_paper(paper, raw, "source.json", "abc")
        self.assertFalse(result["issues"])
        paragraph = result["paragraphs"][0]
        self.assertEqual(paragraph["sourceBlockIds"], ["kaoyan:2026-01:b-1-2"])
        self.assertEqual(paragraph["reflowBlockIds"],
                         ["kaoyan:2026-01:b-1-2", "kaoyan:2026-01:b-2-1"])

    def test_cloze_group_excludes_page_furniture_per_record(self):
        prose = "Thoughtful reading can "
        tail = " our daily lives and improve our judgment."
        raw = {"pages": [{"blocks": [
            {"type": "paragraph", "runs": [
                {"text": prose, "flags": [False, False, False]},
                {"text": " 1 ", "flags": [False, True, False]},
                {"text": tail, "flags": [False, False, False]}]},
            {"type": "paragraph", "runs": [{"text": "第1 页共8 页"}]},
        ]}]}
        context = {"kind": "passage", "passageSourceBlocks": ["b-1-1", "b-1-2"]}
        question = {"id": "q-1-1", "number": "1", "context": context,
                    "answer": {"status": "explicit", "value": "A"},
                    "options": [{"label": "A.", "text": "enrich"}]}
        paper = {"id": "kaoyan:2026-01", "category": "kaoyan", "questions": [question],
                 "blocks": [{"id": "b-1-1", "role": "content", "text": prose + " 1 " + tail},
                            {"id": "b-1-2", "role": "content", "text": "第1 页共8 页"}]}
        result = build_paper(paper, raw, "source.json", "abc")
        self.assertEqual(len(result["paragraphs"]), 1)
        self.assertEqual(result["sourceInventory"][1]["reason"], "cloze_non_prose")
        self.assertTrue(result["paragraphs"][0]["translationEligible"])

    def test_misparsed_option_recovers_readable_direction_input(self):
        sentence = ("You should decide on the best choice and mark the corresponding "
                    "letter on Answer Sheet 2 with a single line through the centre.")
        raw = {"pages": [{"blocks": [
            {"type": "heading", "runs": [{"text": "Part III Reading Comprehension"}]},
            {"type": "options", "items": [{"label": "D", "runs": [{"text": ". " + sentence}]}]},
        ]}]}
        paper = {"id": "cet6:fixture-direction", "category": "cet6", "questions": [],
                 "blocks": [{"id": "b-1-1", "role": "section", "text": "Part III Reading Comprehension"},
                            {"id": "b-1-2", "role": "choices", "text": "D. . " + sentence}]}
        result = build_paper(paper, raw, "source.json", "abc")
        paragraph = result["paragraphs"][0]
        self.assertEqual(paragraph["kind"], "instruction")
        self.assertEqual(paragraph["sourceText"], "D. . " + sentence)
        self.assertEqual(paragraph["translationInput"], sentence)
        self.assertTrue(paragraph["translationEligible"])

    def test_image_source_line_between_passage_fragments_blocks_translation(self):
        left = "A) A long reading paragraph begins with the history of this important project and"
        right = "continues by explaining why many people care about its effects today."
        raw = {"pages": [{"blocks": [
            {"type": "heading", "runs": [{"text": "Part III Reading Comprehension"}]},
            {"type": "paragraph", "runs": [{"text": left}]},
            {"type": "source_line", "src": "unreadable.png"},
            {"type": "paragraph", "runs": [{"text": right}]},
        ]}]}
        paper = {"id": "cet6:fixture-image", "category": "cet6", "questions": [],
                 "blocks": [
                     {"id": "b-1-1", "role": "section", "text": "Part III Reading Comprehension"},
                     {"id": "b-1-2", "role": "content", "text": left},
                     {"id": "b-1-4", "role": "content", "text": right},
                 ]}
        result = build_paper(paper, raw, "source.json", "abc")
        paragraph = result["paragraphs"][0]
        self.assertEqual(paragraph["kind"], "passage_option")
        self.assertFalse(paragraph["translationEligible"])
        self.assertIsNone(paragraph["translationInput"])
        self.assertIn("unreadable_intervening_source_line",
                      [issue["code"] for issue in result["issues"]])

    def test_listening_section_c_bare_dictation_numbers_fail_closed(self):
        directions = ("Directions: You will hear a passage three times. When it is read for "
                      "the second time, fill the blanks with the exact words you hear.")
        first = "The student learned 26 new expressions and 27 useful ideas during the lecture."
        second = "Later she recalled 34 important points and 35 thoughtful questions from it."
        blocks = [
            {"type": "heading", "runs": [{"text": "Part II Listening Comprehension"}]},
            {"type": "heading", "runs": [{"text": "Section C"}]},
            {"type": "paragraph", "runs": [{"text": directions}]},
            {"type": "paragraph", "runs": [{"text": first}]},
            {"type": "paragraph", "runs": [{"text": second}]},
            {"type": "heading", "runs": [{"text": "PartⅢ Reading Comprehension"}]},
            {"type": "paragraph", "runs": [{"text":
                "A later reading passage mentions 34 students in a class and 35 books on a shelf."}]},
        ]
        raw = {"pages": [{"blocks": blocks}]}
        paper = {"id": "cet4:2015-12-02", "category": "cet4", "questions": [],
                 "blocks": [{"id": f"b-1-{i}",
                             "role": "section" if block["type"] == "heading" else "content",
                             "text": block["runs"][0]["text"]}
                            for i, block in enumerate(blocks, 1)]}
        self.assertEqual(listening_dictation_blocks(raw),
                         {"b-1-4": ["26", "27"], "b-1-5": ["34", "35"]})
        result = build_paper(paper, raw, "source.json", "abc")
        dictation = [e for e in result["paragraphs"] if e["id"].endswith(("b-1-4", "b-1-5"))]
        self.assertEqual(len(dictation), 2)
        self.assertTrue(all(not e["translationEligible"] and e["translationInput"] is None
                            for e in dictation))
        self.assertEqual(sum(issue["code"] == "unverified_listening_dictation"
                             for issue in result["issues"]), 2)
        reading = next(e for e in result["paragraphs"] if e["id"].endswith("b-1-7"))
        self.assertTrue(reading["translationEligible"])

    def test_verified_listening_dictation_fills_only_derived_input(self):
        text = ("A thoughtful listener wrote 26 notes and shared 27 ideas; later, "
                "they considered 28 proposals, 29 examples, 30 suggestions, 31 answers, "
                "32 observations, 33 questions, 34 lessons and 35 conclusions.")
        blocks = [
            {"type": "heading", "runs": [{"text": "Section C"}]},
            {"type": "paragraph", "runs": [{"text":
                "Directions: You will hear a passage three times. Fill the blanks with the exact words."}]},
            {"type": "paragraph", "runs": [{"text": text}]},
        ]
        raw = {"pages": [{"blocks": blocks}]}
        paper = {"id": "cet4:2014-06-01", "category": "cet4", "questions": [],
                 "blocks": [{"id": f"b-1-{index}",
                             "role": "section" if index == 1 else "content",
                             "text": block["runs"][0]["text"]}
                            for index, block in enumerate(blocks, 1)]}
        words = ["many", "fresh", "helpful", "clear", "brief", "thoughtful",
                 "careful", "relevant", "practical", "lasting"]
        evidence = {"sourceUrl": "https://example.test/verified-paper",
                    "sourcePage": "Section C, answer table",
                    "passageMatchEvidence": "The same passage and ten numbered gaps",
                    "answers": {str(number): {"word": word}
                                for number, word in zip(range(26, 36), words)}}
        result = build_paper(paper, raw, "source.json", "abc", evidence)
        entry = next(row for row in result["paragraphs"] if row["sourceText"] == text)
        self.assertTrue(entry["translationEligible"])
        self.assertEqual(entry["sourceHash"], sha256(text))
        self.assertEqual(entry["translationInputHash"], sha256(entry["translationInput"]))
        self.assertEqual([row["word"] for row in entry["restoredBlanks"]], words)
        self.assertNotIn("34", entry["translationInput"])
        self.assertIn("practical lessons", entry["translationInput"])

        incomplete = dict(evidence, answers={key: value for key, value in evidence["answers"].items()
                                             if key != "35"})
        rejected = build_paper(paper, raw, "source.json", "abc", incomplete)
        entry = next(row for row in rejected["paragraphs"] if row["sourceText"] == text)
        self.assertFalse(entry["translationEligible"])
        self.assertIsNone(entry["translationInput"])

    def test_printed_page_footer_requires_source_page_and_total(self):
        text = "The careful student read the entire passage for context. 第1 页共1 页"
        self.assertEqual(strip_verified_page_footers(
            text, [(1, text)], 1),
            "The careful student read the entire passage for context.")
        self.assertIsNone(strip_verified_page_footers(
            text, [(2, text)], 1))
        self.assertIsNone(strip_verified_page_footers(
            text, [(1, text)], 2))
        self.assertIsNone(strip_verified_page_footers(text, [(1, text[:-2])], 1))
        short = "The following sentence continues onto the next page. 第6 页"
        self.assertIsNone(strip_verified_page_footers(short, [(6, short)], 9))
        self.assertEqual(strip_verified_page_footers(short, [(6, short)], 9, {6}),
                         "The following sentence continues onto the next page.")
        self.assertIsNone(strip_verified_page_footers(short, [(5, short)], 9, {6}))
        blocks = [
            {"type": "heading", "runs": [{"text": "Part III Reading Comprehension"}]},
            {"type": "paragraph", "runs": [{"text": text}]},
        ]
        paper = {"id": "cet4:2017-06-01", "category": "cet4", "questions": [],
                 "blocks": [{"id": f"b-1-{index}",
                             "role": "section" if index == 1 else "content",
                             "text": block["runs"][0]["text"]}
                            for index, block in enumerate(blocks, 1)]}
        result = build_paper(paper, {"pages": [{"blocks": blocks}]}, "source.json", "abc")
        entry = next(row for row in result["paragraphs"] if row["sourceText"] == text)
        self.assertEqual(entry["sourceHash"], sha256(text))
        self.assertEqual(entry["translationInput"],
                         "The careful student read the entire passage for context.")
        self.assertEqual(entry["translationInputHash"], sha256(entry["translationInput"]))
        self.assertIn("verified_page_footer", [issue["code"] for issue in result["issues"]])
        old_entry = dict(entry, translationInput=text, translationInputHash=sha256(text),
                         translationZh="旧译文含页脚")
        preserve_translations(result, {"paragraphs": [old_entry]})
        self.assertIsNone(entry["translationZh"])
        self.assertEqual(result["staleTranslations"][0]["translationZh"], "旧译文含页脚")


if __name__ == "__main__":
    unittest.main()
