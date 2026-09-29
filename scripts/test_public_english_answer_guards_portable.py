"""Portable public-key safety checks with no private files or original PDFs."""

from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from scripts import build_structured_exams as builder


def _question(number: str, labels: str, source_block: str = "") -> dict:
    return {
        "id": f"q-{number}-1", "number": number, "recordType": "question",
        "sourceBlocks": [source_block] if source_block else [],
        "options": [{"label": f"{label}."} for label in labels],
        "answer": {"value": None, "status": "missing"},
    }


def _paper(paper_id: str, category: str, questions: list[dict],
           blocks: list[dict] | None = None) -> dict:
    return {
        "id": paper_id, "category": category, "kind": "questions",
        "questions": questions, "blocks": blocks or [], "audit": {"linkedAnswers": 0},
    }


def _attach(papers: dict[str, dict], paper_id: str, answers: list[str]) -> dict[str, int]:
    capture = {
        "capturedAt": "2026-01-01T00:00:00Z",
        "papers": [{"paperId": paper_id,
                    "sourceUrl": f"https://zhenti.burningvocabulary.cn/{paper_id.replace(':', '/')}",
                    "answers": answers}],
    }

    def fixture_exists(path: Path) -> bool:
        assert path.name == "burningvocabulary.json"
        return True

    def fixture_read(path: Path, *, encoding: str) -> str:
        assert path.name == "burningvocabulary.json" and encoding == "utf-8"
        return json.dumps(capture)

    # Intercept the importer's one manifest read. This fixture works even in
    # CI where the ignored .local/answer-keys directory is entirely absent.
    with patch.object(Path, "exists", fixture_exists), patch.object(Path, "read_text", fixture_read):
        return builder.attach_public_english_answer_keys(papers)


class PortablePublicEnglishAnswerGuardsTests(unittest.TestCase):
    def test_rejects_letter_missing_from_printed_question_options(self):
        paper_id = "cet4:2099-06-01"
        missing_b = _question("2", "ACD")
        valid = _question("3", "ABCD")
        papers = {paper_id: _paper(paper_id, "cet4", [missing_b, valid])}
        rejected_before = deepcopy(missing_b["answer"])

        counts = _attach(papers, paper_id, ["2-B", "3-C"])

        self.assertEqual(counts, {"optionMismatch": 1, "attached": 1})
        self.assertEqual(missing_b["answer"], rejected_before)
        self.assertEqual(valid["answer"]["value"], "C")
        self.assertEqual(valid["answer"]["status"], "explicit")
        self.assertEqual(papers[paper_id]["audit"]["linkedAnswers"], 1)

    def test_rejects_shared_bank_letter_beyond_printed_labels(self):
        paper_id = "cet6:2099-06-01"
        passage = "A. " + ("This paragraph provides printed source material. " * 2)
        blocks = [
            {"id": "b-section", "text": "Section B"},
            {"id": "b-bank-a", "text": passage},
            {"id": "b-q36", "text": "36. Matching prompt"},
            {"id": "b-q37", "text": "37. Matching prompt"},
        ]
        invalid = _question("36", "", "b-q36")
        in_range = _question("37", "", "b-q37")
        papers = {paper_id: _paper(paper_id, "cet6", [invalid, in_range], blocks)}
        rejected_before = deepcopy(invalid["answer"])

        counts = _attach(papers, paper_id, ["36-P", "37-A"])

        self.assertEqual(counts, {"sharedBankMismatch": 1, "attached": 1})
        self.assertEqual(invalid["answer"], rejected_before)
        self.assertEqual(in_range["answer"]["value"], "A")

    def test_extended_shared_bank_letter_requires_its_printed_paragraph(self):
        paper_id = "cet6:2099-12-01"
        q36 = _question("36", "", "b-q36")
        blocks = [
            {"id": "b-section", "text": "Section B"},
            {"id": "b-bank-q", "text": "Q. " + "A distinctly printed matching paragraph. " * 3},
            {"id": "b-q36", "text": "36. Matching prompt"},
        ]
        papers = {paper_id: _paper(paper_id, "cet6", [q36], blocks)}

        counts = _attach(papers, paper_id, ["36-Q"])

        self.assertEqual(counts, {"attached": 1})
        self.assertEqual(q36["answer"]["value"], "Q")


if __name__ == "__main__":
    unittest.main()
