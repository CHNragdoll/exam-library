import copy
import json
import os
import sys
import tempfile
import unittest
from functools import partial
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_english_paragraph_manifest import REFLOW, STRUCTURED, build_paper as _build_paper, sha256
from pdf_verified_cet_missing_options import verified_cet_missing_option_anchors
from pdf_verified_kaoyan_matching_options import verified_matching_option_anchors
import publish_english_paragraph_translations as publisher
from publish_english_paragraph_translations import public_sidecar


def build_paper(*args, **kwargs):
    kwargs.setdefault("allow_missing_pdf", True)
    return _build_paper(*args, **kwargs)


def fixture():
    source = "Careful readers can  1  improve their judgment."
    filled = "Careful readers can enrich improve their judgment."
    return {"schema": "english-paragraph-translations.v1", "paperId": "kaoyan:2026-01",
            "category": "kaoyan", "staleTranslations": [{"translationInput": filled}],
            "paragraphs": [{"id": "kaoyan:2026-01:p:b-1-1", "paperId": "kaoyan:2026-01",
                            "kind": "cloze", "sourceText": source, "sourceHash": sha256(source),
                            "sourceBlockIds": ["kaoyan:2026-01:b-1-1"],
                            "reflowBlockIds": ["kaoyan:2026-01:b-1-1"],
                            "paragraphIndex": 0, "source": {"blockIds": ["b-1-1"]},
                            "translationInput": filled, "translationInputHash": sha256(filled),
                            "restoredBlanks": [{"word": "enrich", "optionLabel": "A."}],
                            "translationEligible": True, "translationZh": "谨慎阅读可以丰富判断。"}]}


class PublicSidecarTests(unittest.TestCase):
    def setUp(self):
        # Exercise committed source anchors in CI while still hashing any
        # original PDF available in a local checkout.
        for name, helper in (("verified_cet_missing_option_anchors",
                              verified_cet_missing_option_anchors),
                             ("verified_matching_option_anchors",
                              verified_matching_option_anchors)):
            active = patch.object(publisher, name, partial(helper, allow_missing_pdf=True))
            active.start()
            self.addCleanup(active.stop)

    def test_published_preflight_uses_private_snapshot_and_rejects_drift(self):
        private = fixture()
        private.update(sourceJson="source.json", sourcePdfSha256="pdf-hash",
                       options=[],
                       sourceInventory=[{"sourceBlockId": "kaoyan:2026-01:b-1-1",
                                         "classification": "included", "reason": "prose",
                                         "paragraphId": "kaoyan:2026-01:p:b-1-1"}],
                       reconciliation={"included": 1}, optionReconciliation={}, issues=[])
        expected = copy.deepcopy(private)
        public = public_sidecar(private, private["paperId"])
        publisher.published_sidecar_is_current(public, private, expected,
                                               private["paperId"], {})

        changed_source = copy.deepcopy(expected)
        changed_source["paragraphs"][0]["translationInput"] += " changed"
        changed_source["paragraphs"][0]["translationInputHash"] = sha256(
            changed_source["paragraphs"][0]["translationInput"])
        with self.assertRaisesRegex(ValueError, "current source record mismatch.*translationInput"):
            publisher.published_sidecar_is_current(public, private, changed_source,
                                                   private["paperId"], {})

        exposed = copy.deepcopy(public)
        exposed["paragraphs"][0]["translationInput"] = private["paragraphs"][0]["translationInput"]
        with self.assertRaisesRegex(ValueError, "published sidecar differs"):
            publisher.published_sidecar_is_current(exposed, private, expected,
                                                   private["paperId"], {})

        unrecorded = copy.deepcopy(private)
        unrecorded["paragraphs"][0]["translationZh"] = None
        with self.assertRaisesRegex(ValueError, "lacks private provenance"):
            publisher.published_sidecar_is_current(public, unrecorded, expected,
                                                   private["paperId"], {})

    def test_pdf_verified_table_option_requires_current_source_and_exact_anchor(self):
        paper_id, category, stem = "kaoyan:2026-02", "kaoyan", "2026-02"
        pdf_hash = "99477c6b3d2fafe0c66c26662c6143ca1e7488d73d0e651a3693744c455ade64"
        paper = json.loads((STRUCTURED / "papers" / category / f"{stem}.json").read_text())
        raw = json.loads((REFLOW / category / "papers" / f"{stem}.json").read_text())
        built = build_paper(paper, raw, "source.json", pdf_hash)
        option = dict(next(row for row in built["options"]
                           if row["id"] == "kaoyan:2026-02:q-41-1:A"))
        option["translationZh"] = "人们必须注意某些树木并非每年结籽。"
        repeated = dict(next(row for row in built["options"]
                             if row["id"] == "kaoyan:2026-02:q-42-1:A"))
        value = {"schema": "english-paragraph-translations.v1", "paperId": paper_id,
                 "category": category, "sourcePdfSha256": pdf_hash,
                 "paragraphs": [], "options": [option, repeated]}
        public = public_sidecar(value, paper_id)
        self.assertEqual(public["options"][0]["translationZh"], option["translationZh"])
        self.assertEqual(public["options"][1]["translationZh"], option["translationZh"])
        self.assertNotIn("translationInputHash", public["options"][0])
        value["options"][0]["pdfVerifiedSource"]["pdfPage"] += 1
        with self.assertRaisesRegex(ValueError, "PDF option provenance mismatch"):
            public_sidecar(value, paper_id)

    def test_pdf_verified_cet_bank_word_has_source_backed_public_translation(self):
        paper_id, category, stem = "cet4:2020-07-01", "cet4", "2020-07-01"
        pdf_hash = next(row["source_pdf_sha256"] for row in
                        json.loads((REFLOW / "manifest.json").read_text())["papers"]
                        if row["category"] == category and Path(row["file"]).stem == stem)
        paper = json.loads((STRUCTURED / "papers" / category / f"{stem}.json").read_text())
        raw = json.loads((REFLOW / category / "papers" / f"{stem}.json").read_text())
        built = build_paper(paper, raw, "source.json", pdf_hash)
        option = dict(next(row for row in built["options"]
                           if row["id"] == "cet4:2020-07-01:word-bank:J"))
        option["translationZh"] = "记录"
        value = {"schema": "english-paragraph-translations.v1", "paperId": paper_id,
                 "category": category, "sourcePdfSha256": pdf_hash,
                 "paragraphs": [], "options": [option]}
        public = public_sidecar(value, paper_id)
        self.assertEqual(public["options"][0]["translationZh"], "记录")
        self.assertEqual(public["options"][0]["pdfVerifiedSource"]["anchorKind"],
                         "word_bank_option")
        value["options"][0]["sourceBlockIds"] = ["cet4:2020-07-01:b-1-1"]
        with self.assertRaisesRegex(ValueError, "PDF option provenance mismatch"):
            public_sidecar(value, paper_id)

    def test_rebuilt_inventory_rejects_deleted_paragraph_or_option(self):
        expected = fixture()
        option_text = "A complete choice."
        expected["options"] = [{"id": "kaoyan:2026-01:q-1-1:A",
                                "sourceText": option_text,
                                "sourceHash": sha256(option_text)}]
        for collection in ("paragraphs", "options"):
            actual = json.loads(json.dumps(expected))
            actual[collection].clear()
            with self.subTest(collection=collection), self.assertRaisesRegex(
                    ValueError, f"{collection} inventory mismatch.*missing"):
                publisher.reconcile_source_inventory(actual, expected, expected["paperId"])
        actual = json.loads(json.dumps(expected))
        actual["paragraphs"][0]["translationZh"] = "新译文。"
        publisher.reconcile_source_inventory(actual, expected, expected["paperId"])
        actual["paragraphs"][0]["sourceText"] = "Different printed text."
        actual["paragraphs"][0]["sourceHash"] = sha256(actual["paragraphs"][0]["sourceText"])
        with self.assertRaisesRegex(ValueError, "current source record mismatch.*sourceText"):
            publisher.reconcile_source_inventory(actual, expected, expected["paperId"])

    def test_prepare_rebuilds_current_source_before_accepting_sidecar(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            structured = root / "structured"
            reflow = root / "reflow"
            private_path = structured / "translations/kaoyan/2026-01.json"
            paper_path = structured / "papers/kaoyan/2026-01.json"
            raw_path = reflow / "kaoyan/papers/2026-01.json"
            for path in (private_path, paper_path, raw_path):
                path.parent.mkdir(parents=True, exist_ok=True)
            paper_path.write_text(json.dumps({"id": "kaoyan:2026-01"}))
            raw_path.write_text("{}")
            current = fixture()
            private = fixture()
            private["paragraphs"].clear()
            private_path.write_text(json.dumps(private))
            with (patch.object(publisher, "ROOT", root),
                  patch.object(publisher, "STRUCTURED", structured),
                  patch.object(publisher, "REFLOW", reflow),
                  patch.object(publisher, "DEFAULT_VERIFIED_DICTATION", root / "absent.json"),
                  patch.object(publisher, "canonical_entries", return_value=[
                      (private_path, {"source_pdf_sha256": "fake-pdf-hash"})]),
                  patch.object(publisher, "build_paper", return_value=current) as rebuild):
                with self.assertRaisesRegex(ValueError, "paragraphs inventory mismatch.*missing"):
                    publisher.prepare()
            rebuild.assert_called_once()

    def test_public_options_keep_ids_and_resolve_exact_translation_aliases(self):
        value = fixture()
        value["paragraphs"][0].update(
            kind="passage_option", sourceText="B) Careful readers can improve judgment.",
            sourceHash=sha256("B) Careful readers can improve judgment."),
            sourceBlockIds=["kaoyan:2026-01:b-1-1"],
            translationInput="Careful readers can improve judgment.",
            translationInputHash=sha256("Careful readers can improve judgment."))
        base = {"id": "kaoyan:2026-01:q-1-1:A", "kind": "answer_option",
                "paperId": "kaoyan:2026-01", "questionId": "kaoyan:2026-01:q-1-1",
                "optionId": "kaoyan:2026-01:q-1-1:A", "sourceText": "Still",
                "sourceHash": sha256("Still"), "sourceBlockIds": ["kaoyan:2026-01:b-2-1"],
                "reflowBlockId": "kaoyan:2026-01:b-2-1", "reflowOptionIndex": 0,
                "reflowSourceText": "Still", "translationInput": "Still",
                "translationInputHash": sha256("Still"), "translationEligible": True,
                "translationZh": "仍然"}
        repeat = dict(base, id="kaoyan:2026-01:q-2-1:A",
                      questionId="kaoyan:2026-01:q-2-1",
                      optionId="kaoyan:2026-01:q-2-1:A", translationInput=None,
                      translationInputHash=None, translationEligible=False,
                      translationZh=None, coverageStatus="covered_by_option",
                      translationRef=base["id"])
        passage = dict(base, id="kaoyan:2026-01:q-3-1:B",
                       questionId="kaoyan:2026-01:q-3-1",
                       optionId="kaoyan:2026-01:q-3-1:B",
                       sourceText="Careful readers can improve judgment.",
                       sourceHash=sha256("Careful readers can improve judgment."),
                       sourceBlockIds=["kaoyan:2026-01:b-1-1"],
                       translationInput=None, translationInputHash=None,
                       translationEligible=False, translationZh=None,
                       coverageStatus="covered_by_paragraph",
                       translationRef=value["paragraphs"][0]["id"])
        for key in ("reflowBlockId", "reflowOptionIndex", "reflowSourceText"):
            passage.pop(key)
        value["options"] = [base, repeat, passage]
        value["optionReconciliation"] = {"eligible": 1, "ineligible": 2}
        public = public_sidecar(value, "kaoyan:2026-01")
        self.assertEqual(public["optionReconciliation"], value["optionReconciliation"])
        self.assertEqual([entry["translationZh"] for entry in public["options"]],
                         ["仍然", "仍然", "谨慎阅读可以丰富判断。"])
        self.assertNotIn("translationInput", str(public["options"]))
        self.assertNotIn("translationInputHash", str(public["options"]))

        # Source and option glyphs agree exactly despite one PDF-layout space.
        value["options"][2]["sourceText"] = "Careful readers can improve judgment ."
        value["options"][2]["sourceHash"] = sha256(value["options"][2]["sourceText"])
        self.assertEqual(public_sidecar(value, "kaoyan:2026-01")["options"][2]["translationZh"],
                         "谨慎阅读可以丰富判断。")

        value["options"][1]["sourceText"] = "Instead"
        value["options"][1]["sourceHash"] = sha256("Instead")
        with self.assertRaisesRegex(ValueError, "alias source mismatch"):
            public_sidecar(value, "kaoyan:2026-01")

    def test_option_publication_requires_translation_and_exact_raw_glyphs(self):
        value = fixture()
        source = "furniture ."
        raw = "furniture."
        value["options"] = [{"id": "kaoyan:2026-01:q-1-1:A", "kind": "answer_option",
                             "paperId": "kaoyan:2026-01", "questionId": "kaoyan:2026-01:q-1-1",
                             "optionId": "kaoyan:2026-01:q-1-1:A", "sourceText": source,
                             "sourceHash": sha256(source),
                             "sourceBlockIds": ["kaoyan:2026-01:b-2-1"],
                             "reflowBlockId": "kaoyan:2026-01:b-2-1",
                             "reflowOptionIndex": 0, "reflowSourceText": raw,
                             "translationInput": raw, "translationInputHash": sha256(raw),
                             "translationEligible": True, "translationZh": None}]
        with self.assertRaisesRegex(ValueError, "eligible option untranslated"):
            public_sidecar(value, "kaoyan:2026-01")
        value["options"][0]["translationZh"] = "家具。"
        self.assertEqual(public_sidecar(value, "kaoyan:2026-01")["options"][0]["translationZh"],
                         "家具。")
        value["options"][0]["translationInput"] = "unrelated answer text"
        value["options"][0]["translationInputHash"] = sha256("unrelated answer text")
        with self.assertRaisesRegex(ValueError, "input differs from printed source"):
            public_sidecar(value, "kaoyan:2026-01")
        value["options"][0]["translationInput"] = raw
        value["options"][0]["translationInputHash"] = sha256(raw)
        value["options"][0]["reflowSourceText"] = "furniturf."
        value["options"][0]["translationInput"] = "furniturf."
        value["options"][0]["translationInputHash"] = sha256("furniturf.")
        with self.assertRaisesRegex(ValueError, "raw text mismatch"):
            public_sidecar(value, "kaoyan:2026-01")

    def test_numbered_split_option_reuses_exact_source_paragraph(self):
        value = fixture()
        english = "It is for the sole use of passengers travelling with cars."
        value["paragraphs"][0].update(
            kind="question_prompt", sourceText="22、A) " + english,
            sourceHash=sha256("22、A) " + english),
            translationInput="22、A) " + english,
            translationInputHash=sha256("22、A) " + english),
            sourceBlockIds=["kaoyan:2026-01:b-2-33"])
        value["options"] = [{"id": "kaoyan:2026-01:q-22-1:A", "kind": "answer_option",
                             "paperId": "kaoyan:2026-01", "questionId": "kaoyan:2026-01:q-22-1",
                             "optionId": "kaoyan:2026-01:q-22-1:A", "sourceText": english,
                             "sourceHash": sha256(english),
                             "sourceBlockIds": ["kaoyan:2026-01:b-2-33"],
                             "translationInput": None, "translationInputHash": None,
                             "translationEligible": False, "translationZh": None,
                             "coverageStatus": "covered_by_paragraph",
                             "translationRef": value["paragraphs"][0]["id"]}]
        public = public_sidecar(value, "kaoyan:2026-01")
        self.assertEqual(public["options"][0]["translationZh"],
                         value["paragraphs"][0]["translationZh"])

    def test_publication_rejects_changed_chinese_source_cue(self):
        value = fixture()
        cue = "(我才认识到仅凭运气是不能成功的)"
        source = "Only after many failures ________ " + cue + "."
        value["paragraphs"][0].update(
            sourceText=source, sourceHash=sha256(source),
            translationInput=source, translationInputHash=sha256(source),
            protectedCues=[cue], translationZh="经历许多失败后 ________ (中文提示被改写)。")
        with self.assertRaisesRegex(ValueError, "cue differs"):
            public_sidecar(value, "kaoyan:2026-01")
        value["paragraphs"][0]["translationZh"] = "经历许多失败后 ________ " + cue + "。"
        public = public_sidecar(value, "kaoyan:2026-01")
        self.assertNotIn("protectedCues", public["paragraphs"][0])

    def test_known_incomplete_translation_requires_retry_or_quarantine(self):
        value = fixture()
        row = value["paragraphs"][0]
        with patch.dict(publisher.KNOWN_BAD_TRANSLATIONS,
                        {row["id"]: (row["sourceHash"], sha256(row["translationZh"]))}):
            with self.assertRaisesRegex(ValueError, "known incomplete translation"):
                public_sidecar(value, "kaoyan:2026-01")
            result = public_sidecar(value, "kaoyan:2026-01",
                                    {row["id"]: "English passage remained untranslated"})
            self.assertFalse(result["paragraphs"][0]["translationEligible"])
            self.assertIsNone(result["paragraphs"][0]["translationZh"])

    def test_redacts_answer_bearing_fields_and_stale_history(self):
        result = public_sidecar(fixture(), "kaoyan:2026-01")
        self.assertNotIn("staleTranslations", result)
        record = result["paragraphs"][0]
        self.assertNotIn("translationInput", record)
        self.assertNotIn("translationInputHash", record)
        self.assertNotIn("restoredBlanks", record)
        self.assertNotIn("enrich", str(result))
        self.assertEqual(record["translationZh"], "谨慎阅读可以丰富判断。")
        self.assertEqual(record["sourceText"], fixture()["paragraphs"][0]["sourceText"])
        value = fixture()
        value["paragraphs"][0]["source"]["answerWord"] = "enrich"
        self.assertNotIn("answerWord", str(public_sidecar(value, "kaoyan:2026-01")))

    def test_public_hash_cannot_identify_cloze_choice_offline(self):
        private = fixture()
        original = private["paragraphs"][0]
        candidate_hashes = {
            word: sha256(original["sourceText"].replace(" 1 ", word))
            for word in ("enrich", "damage")
        }
        self.assertEqual(candidate_hashes["enrich"], original["translationInputHash"])
        public = public_sidecar(private, "kaoyan:2026-01")
        published = public["paragraphs"][0]
        self.assertEqual(published["sourceHash"], sha256(published["sourceText"]))
        self.assertNotIn("translationInputHash", published)
        serialized = json.dumps(public, ensure_ascii=False)
        self.assertTrue(all(digest not in serialized for digest in candidate_hashes.values()))

    def test_refuses_incomplete_eligible_translation(self):
        value = fixture()
        value["paragraphs"][0]["translationZh"] = None
        with self.assertRaisesRegex(ValueError, "untranslated"):
            public_sidecar(value, "kaoyan:2026-01")

    def test_refuses_changed_translation_input(self):
        value = fixture()
        value["paragraphs"][0]["translationInput"] += " altered"
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            public_sidecar(value, "kaoyan:2026-01")

    def test_explicit_quality_quarantine_can_publish_without_mistranslation(self):
        value = fixture()
        record_id = value["paragraphs"][0]["id"]
        value["paragraphs"][0]["translationZh"] = None
        public = public_sidecar(value, "kaoyan:2026-01",
                                {record_id: "Provider rendered libraries incorrectly; review pending"})
        record = public["paragraphs"][0]
        self.assertFalse(record["translationEligible"])
        self.assertIsNone(record["translationZh"])
        self.assertEqual(record["translationStatus"], "quality_quarantined")
        self.assertEqual(record["translationIssue"], "translation_quality_review_required")
        self.assertNotIn("Provider rendered", str(public))

    def test_quarantine_must_identify_a_real_eligible_record(self):
        with self.assertRaisesRegex(ValueError, "absent from paper"):
            public_sidecar(fixture(), "kaoyan:2026-01", {"missing:p:b-1-1": "review"})

    def test_quarantine_file_requires_unique_reasoned_ids(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "quarantine.json"
            path.write_text(json.dumps({"schema": "english-paragraph-translation-quarantine.v1",
                                        "items": [{"id": "p:1", "reason": "review"},
                                                  {"id": "p:1", "reason": "duplicate"}]}))
            with self.assertRaisesRegex(ValueError, "duplicate quarantine"):
                publisher.read_quarantines(path)

    def test_publish_saves_private_original_before_public_redaction(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            structured = root / "structured"
            path = structured / "translations/kaoyan/2026-01.json"
            path.parent.mkdir(parents=True)
            original = (json.dumps(fixture(), ensure_ascii=False) + "\n").encode()
            quarantines = {"kaoyan:2026-01:p:b-1-1": "Detailed private review finding"}
            public = (json.dumps(public_sidecar(fixture(), "kaoyan:2026-01", quarantines),
                                 ensure_ascii=False) + "\n").encode()
            path.write_bytes(original)
            with patch.object(publisher, "ROOT", root), patch.object(publisher, "STRUCTURED", structured):
                snapshot = publisher.publish([(path, original, public)], quarantines)
            self.assertEqual((snapshot / "kaoyan/2026-01.json").read_bytes(), original)
            self.assertEqual(path.read_bytes(), public)
            self.assertNotIn("restoredBlanks", path.read_text())
            self.assertNotIn("Detailed private", path.read_text())
            self.assertIn("Detailed private", (snapshot / "quality-quarantine.json").read_text())
            self.assertEqual(len(json.loads((snapshot / "manifest.json").read_text())["files"]), 1)

    def test_second_swap_failure_rolls_back_first_private_sidecar(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            structured = root / "structured"
            prepared = []
            for stem in ("2026-01", "2026-02"):
                path = structured / "translations/kaoyan" / f"{stem}.json"
                path.parent.mkdir(parents=True, exist_ok=True)
                original = f"private cloze answer for {stem}".encode()
                public = f"public translation for {stem}".encode()
                path.write_bytes(original)
                prepared.append((path, original, public))

            actual_replace = os.replace

            def fail_second_public_swap(source, destination):
                if (Path(source).parts[-3] == ".staged-public" and
                        Path(destination) == prepared[1][0]):
                    raise OSError("injected second swap failure")
                return actual_replace(source, destination)

            with (patch.object(publisher, "ROOT", root),
                  patch.object(publisher, "STRUCTURED", structured),
                  patch.object(publisher.os, "replace", side_effect=fail_second_public_swap)):
                with self.assertRaisesRegex(RuntimeError, "restored 1 sidecars"):
                    publisher.publish(prepared)

            for path, original, public in prepared:
                self.assertEqual(path.read_bytes(), original)
                self.assertNotEqual(path.read_bytes(), public)
            snapshots = list((root / ".local").glob("english-translation-private-*"))
            self.assertEqual(len(snapshots), 1)
            for path, original, _ in prepared:
                self.assertEqual((snapshots[0] / "kaoyan" / path.name).read_bytes(), original)
            self.assertFalse(list((structured / "translations").rglob("*.public-tmp")))


if __name__ == "__main__":
    unittest.main()
