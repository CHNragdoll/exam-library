#!/usr/bin/env python3
"""Regression checks for the private English-answer evidence validator."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.verify_english_answer_evidence import DEFAULT_EVIDENCE, validate


@unittest.skipUnless(DEFAULT_EVIDENCE.is_file(), "private evidence file is unavailable")
class VerifiedEnglishAnswerEvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.data = json.loads(DEFAULT_EVIDENCE.read_text())

    def check_mutation_fails(self, message: str) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "evidence.json"
            path.write_text(json.dumps(self.data, ensure_ascii=False))
            with self.assertRaisesRegex(ValueError, message):
                validate(path)

    def test_all_current_sources_match(self) -> None:
        self.assertEqual(validate(), (15, 150, 9))

    def test_rejects_word_that_disagrees_with_local_word_bank(self) -> None:
        self.data["wordBank"]["cet4:2016-06-01"]["answers"]["26"]["word"] = "wrong"
        self.check_mutation_fails("answer word disagrees")

    def test_rejects_incomplete_dictation_passage(self) -> None:
        self.data["listeningDictation"]["cet4:2014-06-02"]["sourceBlockIds"].pop()
        self.check_mutation_fails("passage changed")

    def test_rejects_changed_original_pdf(self) -> None:
        self.data["listeningDictation"]["cet4:2014-06-01"]["originalPdfSha256"] = "0" * 64
        self.check_mutation_fails("original PDF changed")


if __name__ == "__main__":
    unittest.main()
