"""Run reflow tests that do not require the archived source PDFs.

The strict source suite remains ``python -m unittest discover -s . -p
'test_*.py'`` with the original PDFs installed. Explicit classification
prevents new test modules from silently disappearing from CI.
"""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import unittest


PORTABLE_MODULES = {"test_option_anchors"}
# These methods use synthetic blocks/pages; their sibling methods need archived PDFs.
PORTABLE_METHODS = {
    "test_heading_options.HeadingAndOptionExtractionTests.test_same_row_option_bank_remains_four_options",
    "test_pdf_verified_word_bank_2019.WordBank2019Test.test_two_printed_words_are_restored_in_label_order",
    "test_pdf_verified_word_bank_2019.WordBank2019Test.test_other_papers_are_untouched",
    "test_pdf_verified_word_bank_2019.WordBank2019Test.test_cet4_2021_12_02_printed_o_is_not_left_inside_g",
    "test_pdf_verified_word_bank_2019.WordBank2019Test.test_cet4_2020_12_01_wrong_merged_word_rejects_repair",
}
SOURCE_MODULES = {
    "test_cet_cloze_source_markers",
    "test_continuous",
    "test_encoding",
    "test_extraction",
    "test_heading_options",
    "test_layout",
    "test_local_glyph_fallback",
    "test_pdf_verified_chinese_ocr",
    "test_pdf_verified_dotted_option_labels",
    "test_pdf_verified_four_choices",
    "test_pdf_verified_word_bank_2019",
    "test_question_continuations",
    "test_soft_line_wraps",
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
    here = Path(__file__).resolve().parent
    discovered = discovered_test_modules(here)
    assigned = PORTABLE_MODULES | SOURCE_MODULES
    if PORTABLE_MODULES & SOURCE_MODULES or discovered != assigned:
        print(f"Test-tier overlap: {sorted(PORTABLE_MODULES & SOURCE_MODULES)}", file=sys.stderr)
        print(f"Unclassified modules: {sorted(discovered - assigned)}", file=sys.stderr)
        print(f"Missing modules: {sorted(assigned - discovered)}", file=sys.stderr)
        return 2
    sys.path.insert(0, str(here))
    print(f"Portable reflow tier: {len(PORTABLE_MODULES)} module; "
          f"strict source tier: {len(SOURCE_MODULES)} modules", flush=True)
    suite = unittest.defaultTestLoader.loadTestsFromNames(
        sorted(PORTABLE_MODULES | PORTABLE_METHODS))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if result.skipped:
        print("Portable reflow tests skipped; check CI inputs:", file=sys.stderr)
        for test, reason in result.skipped:
            print(f"  {test.id()}: {reason}", file=sys.stderr)
    return 0 if result.wasSuccessful() and not result.skipped else 1


if __name__ == "__main__":
    raise SystemExit(main())
