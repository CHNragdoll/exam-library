"""Run tests whose inputs are included in a clean checkout.

The full source-verification suite remains ``python -m unittest discover -s
scripts -p 'test_*.py'`` on a workstation with the archived PDFs and private
answer evidence. A new test module must be assigned to one of these tiers
explicitly so CI cannot quietly drop it.
"""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import unittest


PORTABLE_MODULES = {
    "test_answer_exposure_boundary",
    "test_audit_source_integrity",
    "test_build_structured_exams_cs408_continuations",
    "test_build_structured_exams_cs_politics_pdf_questions",
    "test_build_structured_exams_dotted_labels",
    "test_build_structured_exams_english_question_boundaries",
    "test_build_structured_exams_figure_options",
    "test_build_structured_exams_inline_choices",
    "test_build_structured_exams_math_answers",
    "test_build_structured_exams_math_options",
    "test_build_structured_exams_pages",
    "test_build_structured_exams_politics_five_options",
    "test_build_structured_exams_politics_split_stems",
    "test_build_structured_exams_politics_subquestions",
    "test_build_structured_exams_question_boundaries",
    "test_check_public_english_translations",
    "test_english_image_question_recovery",
    "test_english_paragraph_manifest",
    "test_kaoyan_shared_groups",
    "test_pdf_verified_cet_bilingual_joins",
    "test_practice_answer_source",
    "test_public_english_answer_guards_portable",
    "test_publish_english_paragraph_translations",
    "test_question_database",
    "test_question_database_api",
    "test_semantic_api",
    "test_semantic_database",
    "test_serve_exam_library",
    "test_translate_google_web",
    "test_triage_source_integrity",
}

# These exercise original PDF/OCR boundaries, local capture files, or private
# evidence. They intentionally remain in the strict local discovery command.
SOURCE_MODULES = {
    "test_answer_panels",
    "test_build_structured_exams_cet_cloze",
    "test_build_structured_exams_cet_free_response",
    "test_build_structured_exams_cs408_answers",
    "test_build_structured_exams_english_answer_reconciliation",
    "test_build_structured_exams_english_answers",
    "test_build_structured_exams_english_structure",
    "test_build_structured_exams_kaoyan_2024_segments",
    "test_build_structured_exams_kaoyan_numbered_parts",
    "test_build_structured_exams_math_pdf_questions",
    "test_build_structured_exams_math_references",
    "test_build_structured_exams_politics",
    "test_build_structured_exams_politics_answers",
    "test_build_structured_exams_politics_essays",
    "test_english_image_writing_recovery",
    "test_english_original_missing_cards",
    "test_english_tail_choice_triage",
    "test_kaoyan_decimal_continuations",
    "test_kaoyan_writing_requirements",
    "test_pdf_verified_cet_missing_options",
    "test_pdf_verified_kaoyan_matching_options",
    "test_politics_2020_answer_source",
    "test_politics_answer_punctuation",
    "test_public_english_answer_keys",
    "test_recover_image_questions",
    "test_tem_public_answer_keys",
    "test_verified_cet_answer_exception",
    "test_verified_cet_external_answers",
    "test_verified_english_answer_import",
    "test_verify_english_answer_evidence",
}

# These methods use committed reflow/structured records or synthetic inputs.
# Their siblings in the same modules still require private PDF/answer evidence.
PORTABLE_METHODS = {
    "test_build_structured_exams_politics.PoliticsPresentationTests.test_multiple_choice_answer_letters_are_not_truncated",
    "test_build_structured_exams_politics.PoliticsPresentationTests.test_2023_preview_and_json_keep_pdf_content_without_page_footers",
    "test_build_structured_exams_politics.PoliticsPresentationTests.test_artifact_detection_requires_matching_page_and_question",
    "test_build_structured_exams_politics.PoliticsPresentationTests.test_corpus_audit_covers_all_politics_question_years",
    "test_build_structured_exams_politics.PoliticsPresentationTests.test_pdf_paragraph_boundaries_preserve_source_text",
    "test_build_structured_exams_politics.PoliticsPresentationTests.test_2003_question_29_keeps_all_five_options_across_pdf_pages",
    "test_build_structured_exams_politics.PoliticsPresentationTests.test_pdf_continuation_pages_are_not_empty_in_reflow",
    "test_build_structured_exams_politics.PoliticsPresentationTests.test_reflow_hides_only_synthetic_continuation_labels",
    "test_build_structured_exams_politics.PoliticsPresentationTests.test_scanned_continuation_pages_keep_their_pdf_page_ownership",
    "test_build_structured_exams_politics.PoliticsPresentationTests.test_pdf_specific_choice_labels_are_parsed_without_guessing",
    "test_build_structured_exams_politics_answers.PoliticsAnswerTests.test_standard_answer_label_keeps_all_choice_letters",
    "test_build_structured_exams_politics_essays.PoliticsEssayAnswerTests.test_2023_question_stems_use_pdf_verified_display_corrections",
}


def discovered_test_modules(directory: Path) -> set[str]:
    """Use the index in a checkout, or files in a GitHub source archive."""
    indexed = subprocess.run(
        ["git", "-C", str(directory), "ls-files", "--cached", "-z", "--", "test_*.py"],
        capture_output=True, text=True, check=False,
    )
    if indexed.returncode == 0 and indexed.stdout:
        return {Path(name).stem for name in indexed.stdout.split("\0")
                if name and Path(name).parent == Path(".")}
    return {path.stem for path in directory.glob("test_*.py")}


def main() -> int:
    scripts = Path(__file__).resolve().parent
    discovered = discovered_test_modules(scripts)
    assigned = PORTABLE_MODULES | SOURCE_MODULES
    if PORTABLE_MODULES & SOURCE_MODULES or discovered != assigned:
        print(f"Test-tier overlap: {sorted(PORTABLE_MODULES & SOURCE_MODULES)}", file=sys.stderr)
        print(f"Unclassified modules: {sorted(discovered - assigned)}", file=sys.stderr)
        print(f"Missing modules: {sorted(assigned - discovered)}", file=sys.stderr)
        return 2
    sys.path.insert(0, str(scripts))
    sys.path.insert(0, str(scripts.parent))
    print(f"Portable tier: {len(PORTABLE_MODULES)} modules; "
          f"strict source tier: {len(SOURCE_MODULES)} modules", flush=True)
    suite = unittest.defaultTestLoader.loadTestsFromNames(
        sorted(PORTABLE_MODULES) + sorted(PORTABLE_METHODS))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if result.skipped:
        print("Portable tests skipped; check CI inputs:", file=sys.stderr)
        for test, reason in result.skipped:
            print(f"  {test.id()}: {reason}", file=sys.stderr)
    return 0 if result.wasSuccessful() and not result.skipped else 1


if __name__ == "__main__":
    raise SystemExit(main())
