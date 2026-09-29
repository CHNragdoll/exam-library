import copy
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_english_paragraph_manifest import REFLOW, ROOT, STRUCTURED, build_paper, sha256
from check_public_english_translations import validate_public_sidecar


def paper_pair(category: str, stem: str) -> tuple[dict, dict, str]:
    paper_id = f"{category}:{stem}"
    public = json.loads((STRUCTURED / "translations" / category / f"{stem}.json")
                        .read_text(encoding="utf-8"))
    source_path = REFLOW / category / "papers" / f"{stem}.json"
    structured = json.loads((STRUCTURED / "papers" / category / f"{stem}.json")
                            .read_text(encoding="utf-8"))
    raw = json.loads(source_path.read_text(encoding="utf-8"))
    expected = build_paper(structured, raw, str(source_path.relative_to(ROOT)),
                           public["sourcePdfSha256"])
    return public, expected, paper_id


class PublicEnglishTranslationChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.public, cls.expected, cls.paper_id = paper_pair("tem4", "2022")

    def test_public_source_and_translation_inventory_is_current(self):
        self.assertEqual(validate_public_sidecar(self.public, self.expected, self.paper_id),
                         (len(self.public["paragraphs"]), len(self.public["options"])))

    def test_rejects_missing_translation_and_missing_record(self):
        public = copy.deepcopy(self.public)
        eligible = next(row for row in public["paragraphs"] if row["translationEligible"])
        eligible["translationZh"] = None
        with self.assertRaisesRegex(ValueError, "eligible translation missing"):
            validate_public_sidecar(public, self.expected, self.paper_id)

        public = copy.deepcopy(self.public)
        public["options"].pop()
        with self.assertRaisesRegex(ValueError, "inventory mismatch"):
            validate_public_sidecar(public, self.expected, self.paper_id)

    def test_rejects_changed_source_even_with_recomputed_hash(self):
        public = copy.deepcopy(self.public)
        public["paragraphs"][0]["sourceText"] += " altered"
        public["paragraphs"][0]["sourceHash"] = sha256(public["paragraphs"][0]["sourceText"])
        with self.assertRaisesRegex(ValueError, "current source record mismatch"):
            validate_public_sidecar(public, self.expected, self.paper_id)

    def test_rejects_private_fields_even_when_nested(self):
        public = copy.deepcopy(self.public)
        public["paragraphs"][0]["source"]["restoredBlanks"] = [{"word": "secret"}]
        with self.assertRaisesRegex(ValueError, "private translation field"):
            validate_public_sidecar(public, self.expected, self.paper_id)

    def test_rejects_structural_issue_even_when_public_matches_source(self):
        public = copy.deepcopy(self.public)
        expected = copy.deepcopy(self.expected)
        issue = {"code": "paragraph_inventory_mismatch", "blockId": "b-1-5"}
        public["issues"].append(issue)
        expected["issues"].append(issue)
        with self.assertRaisesRegex(ValueError, "structural source issues"):
            validate_public_sidecar(public, expected, self.paper_id)

    def test_stale_issue_has_exact_fields_and_unique_paragraph(self):
        record_id = self.public["paragraphs"][0]["id"]
        public = copy.deepcopy(self.public)
        public["issues"].append({"code": "stale_translation", "paragraphId": record_id,
                                 "answerWord": "secret"})
        with self.assertRaisesRegex(ValueError, "invalid stale translation issue fields"):
            validate_public_sidecar(public, self.expected, self.paper_id)

        public["issues"][-1].pop("answerWord")
        validate_public_sidecar(public, self.expected, self.paper_id)
        public["issues"].append(copy.deepcopy(public["issues"][-1]))
        with self.assertRaisesRegex(ValueError, "duplicate stale translation issue"):
            validate_public_sidecar(public, self.expected, self.paper_id)

    def test_quarantine_requires_explicit_public_status(self):
        public = copy.deepcopy(self.public)
        row = next(row for row in public["paragraphs"] if row["translationEligible"])
        row.update(translationEligible=False, translationZh=None,
                   translationStatus="quality_quarantined",
                   translationIssue="translation_quality_review_required")
        validate_public_sidecar(public, self.expected, self.paper_id)
        del row["translationStatus"]
        with self.assertRaisesRegex(ValueError, "unexpected or missing public fields|eligibility differs"):
            validate_public_sidecar(public, self.expected, self.paper_id)

    def test_public_dictation_promotion_and_alias(self):
        public, expected, paper_id = paper_pair("cet4", "2014-06-01")
        validate_public_sidecar(public, expected, paper_id)
        public, expected, paper_id = paper_pair("cet6", "2014-12-01")
        validate_public_sidecar(public, expected, paper_id)
        alias = next(row for row in public["options"] if row.get("coverageStatus") ==
                     "covered_by_paragraph")
        alias["translationZh"] = "wrong alias"
        with self.assertRaisesRegex(ValueError, "translation alias target unavailable"):
            validate_public_sidecar(public, expected, paper_id)


if __name__ == "__main__":
    unittest.main()
