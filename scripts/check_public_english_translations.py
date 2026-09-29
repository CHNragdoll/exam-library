"""Audit published English translation sidecars using only public source files.

Unlike the publisher's private-snapshot preflight, this check is safe to run in
a fresh CI checkout. It never writes sidecars or reads ``.local``.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

from build_english_paragraph_manifest import (REFLOW, ROOT, STRUCTURED, build_paper,
                                              comparison_key, paragraph_choice_body,
                                              sha256)
from publish_english_paragraph_translations import (PUBLIC_OPTION, PUBLIC_PARAGRAPH,
                                                    PUBLIC_SOURCE, PUBLIC_TOP_LEVEL,
                                                    canonical_entries)

PRIVATE_FIELDS = frozenset({
    "translationInput", "translationInputHash", "restoredBlanks",
    "protectedBlanks", "protectedCues", "unresolvedBlanks", "staleTranslations",
})
QUARANTINE_STATUS = "quality_quarantined"
QUARANTINE_ISSUE = "translation_quality_review_required"
# Matches the manifest builder's structuralIssueCount exclusions. These are
# documented source limitations or verified notices, not inventory failures.
NON_STRUCTURAL_ISSUES = frozenset({
    "incomplete_cloze", "source_unreadable", "unreadable_intervening_source_line",
    "unverified_listening_dictation", "verified_page_footer",
    "verified_direction_notice", "verified_cross_page_footer", "stale_translation",
})


def reject_private_fields(value: object, location: str) -> None:
    if isinstance(value, dict):
        leaked = PRIVATE_FIELDS.intersection(value)
        if leaked:
            raise ValueError(f"private translation field in {location}: {sorted(leaked)}")
        for key, child in value.items():
            reject_private_fields(child, f"{location}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            reject_private_fields(child, f"{location}[{index}]")


def rows_by_id(rows: object, paper_id: str, collection: str) -> dict[str, dict]:
    if not isinstance(rows, list):
        raise ValueError(f"{paper_id}: {collection} is not a list")
    result = {}
    for row in rows:
        record_id = row.get("id") if isinstance(row, dict) else None
        if not isinstance(record_id, str) or record_id in result:
            raise ValueError(f"{paper_id}: invalid or duplicate {collection} ID: {record_id}")
        result[record_id] = row
    return result


def validate_public_sidecar(public: dict, expected: dict, paper_id: str) -> tuple[int, int]:
    """Check public projection, source identity, coverage and translation presence."""
    if not isinstance(public, dict):
        raise ValueError(f"{paper_id}: sidecar is not an object")
    reject_private_fields(public, paper_id)
    if set(public) != set(PUBLIC_TOP_LEVEL):
        raise ValueError(f"{paper_id}: unexpected or missing public metadata fields")
    structural_issues = sorted({issue.get("code") if isinstance(issue, dict) else None
                                for issue in expected["issues"]
                                if not isinstance(issue, dict) or
                                issue.get("code") not in NON_STRUCTURAL_ISSUES}, key=str)
    if structural_issues:
        raise ValueError(f"{paper_id}: structural source issues: {structural_issues}")

    published = {}
    promoted_dictation = set()
    for collection, allowed in (("paragraphs", PUBLIC_PARAGRAPH),
                                ("options", PUBLIC_OPTION)):
        actual_by_id = rows_by_id(public[collection], paper_id, collection)
        source_by_id = rows_by_id(expected[collection], paper_id, collection)
        if actual_by_id.keys() != source_by_id.keys():
            missing = sorted(source_by_id.keys() - actual_by_id.keys())
            extra = sorted(actual_by_id.keys() - source_by_id.keys())
            raise ValueError(f"{paper_id}: {collection} inventory mismatch; "
                             f"missing={missing[:5]}, extra={extra[:5]}")
        for record_id, actual in actual_by_id.items():
            source = source_by_id[record_id]
            quarantined = actual.get("translationStatus") == QUARANTINE_STATUS
            expected_keys = {key for key in allowed if key in source}
            if quarantined:
                expected_keys.update({"translationStatus", "translationIssue"})
            if set(actual) != expected_keys:
                raise ValueError(f"{record_id}: unexpected or missing public fields")
            for field in expected_keys - {"translationEligible", "translationZh",
                                          "translationStatus", "translationIssue"}:
                source_value = source[field]
                if field == "source":
                    source_value = {key: source_value[key] for key in PUBLIC_SOURCE
                                    if key in source_value}
                if actual[field] != source_value:
                    raise ValueError(f"{record_id}: current source record mismatch: {field}")
            if actual["sourceHash"] != sha256(actual["sourceText"]):
                raise ValueError(f"{record_id}: source hash mismatch")
            if quarantined:
                if (source["translationEligible"] is not True or
                        actual["translationEligible"] is not False or
                        actual["translationZh"] is not None or
                        actual["translationIssue"] != QUARANTINE_ISSUE):
                    raise ValueError(f"{record_id}: invalid public quarantine")
            elif actual["translationEligible"] is not source["translationEligible"]:
                # Private, source-cited 26-35 dictation words can make a
                # listening paragraph eligible. CI has only the printed
                # source, so permit this single publication-time promotion.
                issues = [issue for issue in expected["issues"] if
                          issue.get("code") == "unverified_listening_dictation" and
                          issue.get("paragraphId") == record_id]
                if (collection != "paragraphs" or source.get("kind") != "listening_text" or
                        source["translationEligible"] is not False or
                        actual["translationEligible"] is not True or len(issues) != 1 or
                        not source.get("unresolvedBlanks") or
                        not all(blank.startswith("dictation_answer_unverified:") for blank in
                                source["unresolvedBlanks"])):
                    raise ValueError(f"{record_id}: translation eligibility differs from source")
                promoted_dictation.add(record_id)
            translated = actual.get("translationZh")
            if actual["translationEligible"]:
                if not isinstance(translated, str) or not translated.strip():
                    raise ValueError(f"{record_id}: eligible translation missing")
            elif not (collection == "options" and actual.get("coverageStatus") in
                      {"covered_by_option", "covered_by_paragraph"}) and translated is not None:
                raise ValueError(f"{record_id}: ineligible record has a translation")
        published[collection] = actual_by_id

    source_metadata = copy.deepcopy(expected)
    if promoted_dictation:
        changed = set()
        for item in source_metadata["sourceInventory"]:
            record_id = item.get("paragraphId")
            if record_id not in promoted_dictation:
                continue
            if (item.get("classification") != "ineligible" or
                    item.get("reason") != "unverified_listening_dictation"):
                raise ValueError(f"{record_id}: unexpected dictation inventory")
            item["classification"] = "included"
            item["reason"] = "section_listening"
            changed.add(record_id)
        if changed != promoted_dictation:
            raise ValueError(f"{paper_id}: missing promoted dictation inventory")
        for field, remove, add in (("reconciliation", "ineligible", "included"),
                                   ("reasonCounts", "unverified_listening_dictation",
                                    "section_listening")):
            counts = source_metadata[field]
            count = len(promoted_dictation)
            counts[remove] -= count
            if counts[remove] == 0:
                del counts[remove]
            counts[add] = counts.get(add, 0) + count
        source_metadata["issues"] = [issue for issue in source_metadata["issues"]
                                     if not (issue.get("code") == "unverified_listening_dictation"
                                             and issue.get("paragraphId") in promoted_dictation)]
    public_issues = public["issues"]
    if not isinstance(public_issues, list):
        raise ValueError(f"{paper_id}: issues is not a list")
    stale_ids = set()
    for issue in public_issues:
        if not isinstance(issue, dict):
            raise ValueError(f"{paper_id}: invalid public issue")
        if issue.get("code") == "stale_translation":
            record_id = issue.get("paragraphId")
            if set(issue) != {"code", "paragraphId"}:
                raise ValueError(f"{paper_id}: invalid stale translation issue fields")
            if record_id not in published["paragraphs"]:
                raise ValueError(f"{paper_id}: stale translation references missing paragraph")
            if record_id in stale_ids:
                raise ValueError(f"{paper_id}: duplicate stale translation issue: {record_id}")
            stale_ids.add(record_id)
    if ([issue for issue in public_issues if issue.get("code") != "stale_translation"] !=
            source_metadata["issues"]):
        raise ValueError(f"{paper_id}: current source metadata mismatch: issues")
    for field in PUBLIC_TOP_LEVEL:
        if field in {"paragraphs", "options", "issues"}:
            continue
        if public[field] != source_metadata[field]:
            raise ValueError(f"{paper_id}: current source metadata mismatch: {field}")

    for option in published["options"].values():
        status = option.get("coverageStatus")
        if status not in {"covered_by_option", "covered_by_paragraph"}:
            continue
        record_id = option["id"]
        referent = published["options" if status == "covered_by_option" else
                             "paragraphs"].get(option.get("translationRef"))
        if (option["translationEligible"] or referent is None or
                not referent["translationEligible"] or
                option["translationZh"] != referent["translationZh"]):
            raise ValueError(f"{record_id}: translation alias target unavailable")
        if status == "covered_by_option":
            same_source = (option["sourceHash"] == referent["sourceHash"] and
                           option["sourceText"] == referent["sourceText"])
        else:
            same_source = (comparison_key(paragraph_choice_body(referent["sourceText"])) ==
                           comparison_key(option["sourceText"]) and
                           bool(set(option.get("sourceBlockIds", [])) &
                                set(referent.get("sourceBlockIds", []))))
        if not same_source:
            raise ValueError(f"{record_id}: translation alias source mismatch")
    return len(published["paragraphs"]), len(published["options"])


def check_all() -> dict[str, int]:
    entries = canonical_entries()
    translation_root = STRUCTURED / "translations"
    canonical = {path for path, _ in entries}
    actual = set(translation_root.glob("*/*.json"))
    if actual != canonical:
        raise ValueError(f"public translation file inventory mismatch: "
                         f"missing={len(canonical - actual)}, extra={len(actual - canonical)}")
    paragraphs = options = 0
    for path, source in entries:
        category, stem = path.parent.name, path.stem
        paper_id = f"{category}:{stem}"
        raw_path = REFLOW / category / "papers" / f"{stem}.json"
        structured_path = STRUCTURED / "papers" / category / f"{stem}.json"
        paper = json.loads(structured_path.read_text(encoding="utf-8"))
        if paper.get("id") != paper_id:
            raise ValueError(f"canonical structured paper mismatch: {structured_path}")
        raw = json.loads(raw_path.read_text(encoding="utf-8"))
        expected = build_paper(paper, raw, str(raw_path.relative_to(ROOT)),
                               source["source_pdf_sha256"], allow_missing_pdf=True)
        public = json.loads(path.read_text(encoding="utf-8"))
        paragraph_count, option_count = validate_public_sidecar(public, expected, paper_id)
        paragraphs += paragraph_count
        options += option_count
    return {"validatedPapers": len(entries), "paragraphs": paragraphs, "options": options}


if __name__ == "__main__":
    print(json.dumps(check_all()))
