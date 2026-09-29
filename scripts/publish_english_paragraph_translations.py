"""Check or publish English translation sidecars without exposing cloze answers.

Run only after the Google translation writer has stopped. The full working
sidecars are copied to an ignored .local audit snapshot before public files
are atomically replaced. Check mode also audits already published sidecars
against that private snapshot. This script has no partial-publish mode.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from build_english_paragraph_manifest import (CATEGORIES, REFLOW, ROOT, STRUCTURED,
                                              build_paper, comparison_key,
                                              paragraph_choice_body, sha256)
from pdf_verified_kaoyan_matching_options import verified_matching_option_anchors
from pdf_verified_cet_missing_options import verified_cet_missing_option_anchors
from translate_google_web import TranslationError, validate_cues, verified_cues

PUBLIC_TOP_LEVEL = (
    "schema", "paperId", "category", "sourceJson", "sourcePdfSha256",
    "paragraphs", "options", "optionReconciliation",
    "sourceInventory", "reconciliation", "reasonCounts",
    "kindCounts", "otherSourceBlockCounts", "issues",
)
PUBLIC_PARAGRAPH = (
    "id", "paperId", "kind", "sourceText", "sourceHash", "sourceBlockIds",
    "reflowBlockIds", "paragraphIndex",
    "translationEligible", "translationZh", "source",
)
PUBLIC_SOURCE = (
    "blockIds", "reflowBlockIds", "blockParagraphIndices", "pages",
    "sourceJson", "pdfSha256", "originalHtml", "reflowHtml",
)
PUBLIC_OPTION = (
    "id", "kind", "paperId", "questionId", "optionId", "sourceText", "sourceHash",
    "sourceBlockIds", "reflowBlockId", "reflowBlockIds", "reflowOptionIndex",
    "reflowSourceText", "pdfVerifiedSource",
    "translationEligible", "translationZh", "coverageStatus", "translationRef",
    "eligibilityReason",
)
KNOWN_BAD_TRANSLATIONS = {
    # Google left a 40-word English tail after this CET6 passage. The source
    # and rejected output hashes make the gate exact; a corrected translation
    # can pass, while an explicit quarantine publishes no misleading Chinese.
    "cet6:2022-06-01:p:b-5-2": (
        "382db98c5f30bf650c3d0763027bb98afd0a3e67c8b5c84099fd9c2f95059826",
        "270ddc837e33e443174520d74dc78347a04280728602606bdf94edef8097db87",
    ),
}
DEFAULT_VERIFIED_DICTATION = ROOT / ".local/answer-keys/verified-listening-dictation.json"


def canonical_entries() -> list[tuple[Path, dict]]:
    manifest = json.loads((REFLOW / "manifest.json").read_text(encoding="utf-8"))
    entries = []
    seen = set()
    for source in manifest["papers"]:
        category = source["category"]
        if category not in CATEGORIES:
            continue
        stem = Path(source["file"]).stem
        paper_id = f"{category}:{stem}"
        if paper_id in seen:
            raise ValueError(f"duplicate canonical paper: {paper_id}")
        seen.add(paper_id)
        entries.append((STRUCTURED / "translations" / category / f"{stem}.json", source))
    if len(entries) != 206:
        raise ValueError(f"expected 206 canonical English papers, found {len(entries)}")
    return entries


def canonical_paths() -> list[Path]:
    return [path for path, _ in canonical_entries()]


def verified_dictation_papers(path: Path | None) -> dict:
    if path is None:
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    if (value.get("schema") != "verified-listening-dictation.v1" or
            not isinstance(value.get("papers"), dict)):
        raise ValueError(f"invalid verified listening dictation file: {path}")
    return value["papers"]


def reconcile_source_inventory(actual: dict, expected: dict, paper_id: str) -> None:
    """Require the private sidecar to cover the freshly rebuilt source inventory."""
    for field in ("schema", "paperId", "category", "sourceJson", "sourcePdfSha256",
                  "sourceInventory", "reconciliation", "optionReconciliation"):
        if actual.get(field) != expected.get(field):
            raise ValueError(f"current source metadata mismatch: {paper_id}: {field}")
    for collection in ("paragraphs", "options"):
        actual_rows = actual.get(collection)
        expected_rows = expected.get(collection)
        if not isinstance(actual_rows, list) or not isinstance(expected_rows, list):
            raise ValueError(f"{collection} inventory is not a list: {paper_id}")
        actual_by_id = {row.get("id"): row for row in actual_rows if isinstance(row, dict)}
        expected_by_id = {row.get("id"): row for row in expected_rows if isinstance(row, dict)}
        if len(actual_by_id) != len(actual_rows) or len(expected_by_id) != len(expected_rows):
            raise ValueError(f"{collection} inventory has duplicate or invalid IDs: {paper_id}")
        missing = sorted(expected_by_id.keys() - actual_by_id.keys())
        extra = sorted(actual_by_id.keys() - expected_by_id.keys())
        if missing or extra:
            raise ValueError(f"{collection} inventory mismatch: {paper_id}; "
                             f"missing={missing[:5]} ({len(missing)}), "
                             f"extra={extra[:5]} ({len(extra)})")
        provenance_fields = (
            "id", "paperId", "kind", "sourceText", "sourceHash", "sourceBlockIds",
            "reflowBlockIds", "reflowBlockId", "reflowOptionIndex", "reflowSourceText",
            "paragraphIndex", "questionId", "optionId", "source", "pdfVerifiedSource",
            "translationEligible", "eligibilityReason", "translationInput",
            "translationInputHash", "protectedBlanks", "protectedCues",
            "coverageStatus", "translationRef",
        )
        for record_id, expected_row in expected_by_id.items():
            actual_row = actual_by_id[record_id]
            for field in provenance_fields:
                if actual_row.get(field) != expected_row.get(field):
                    raise ValueError(f"current source record mismatch: {record_id}: {field}")


def public_sidecar(value: dict, expected_paper_id: str,
                   quarantines: dict[str, str] | None = None) -> dict:
    quarantines = quarantines or {}
    if value.get("schema") != "english-paragraph-translations.v1":
        raise ValueError(f"wrong schema: {expected_paper_id}")
    if value.get("paperId") != expected_paper_id:
        raise ValueError(f"paper ID mismatch: {expected_paper_id}")
    result = {key: value[key] for key in PUBLIC_TOP_LEVEL if key in value}
    result["paragraphs"] = []
    result["options"] = []
    ids = set()
    used_quarantines = set()
    for entry in value["paragraphs"]:
        record_id = entry["id"]
        if record_id in ids:
            raise ValueError(f"duplicate paragraph ID: {record_id}")
        ids.add(record_id)
        if entry["sourceHash"] != sha256(entry["sourceText"]):
            raise ValueError(f"source hash mismatch: {record_id}")
        source_input = entry.get("translationInput")
        if source_input is not None and entry.get("translationInputHash") != sha256(source_input):
            raise ValueError(f"translation input hash mismatch: {record_id}")
        try:
            cues = (verified_cues(source_input, entry.get("protectedCues"), record_id)
                    if isinstance(source_input, str) else ())
        except TranslationError as exc:
            raise ValueError(str(exc)) from exc
        if record_id in quarantines:
            if not entry["translationEligible"]:
                raise ValueError(f"quarantine targets ineligible source: {record_id}")
            if not quarantines[record_id].strip():
                raise ValueError(f"empty quarantine reason: {record_id}")
            used_quarantines.add(record_id)
        elif entry["translationEligible"]:
            translated = entry.get("translationZh")
            if not isinstance(translated, str) or not translated.strip():
                raise ValueError(f"eligible paragraph untranslated: {record_id}")
            rejected = KNOWN_BAD_TRANSLATIONS.get(record_id)
            if rejected and (entry["sourceHash"], sha256(translated)) == rejected:
                raise ValueError(f"known incomplete translation requires retry or quarantine: {record_id}")
            try:
                validate_cues(cues, translated)
            except TranslationError as exc:
                raise ValueError(str(exc)) from exc
        public = {key: entry[key] for key in PUBLIC_PARAGRAPH if key in entry}
        if "source" in public:
            public["source"] = {key: entry["source"][key]
                                for key in PUBLIC_SOURCE if key in entry["source"]}
        if record_id in quarantines:
            public["translationEligible"] = False
            public["translationZh"] = None
            public["translationStatus"] = "quality_quarantined"
            public["translationIssue"] = "translation_quality_review_required"
        result["paragraphs"].append(public)
    private_options = value.get("options", [])
    if not isinstance(private_options, list):
        raise ValueError(f"invalid options list: {expected_paper_id}")
    verified_pdf_options = {}
    verified_cet_options = {}
    if any("pdfVerifiedSource" in entry for entry in private_options):
        category, stem = expected_paper_id.split(":", 1)
        paper = json.loads((STRUCTURED / "papers" / category / f"{stem}.json").read_text(encoding="utf-8"))
        raw = json.loads((REFLOW / category / "papers" / f"{stem}.json").read_text(encoding="utf-8"))
        verified_pdf_options = verified_matching_option_anchors(
            paper, raw, value.get("sourcePdfSha256", ""))
        verified_cet_options = verified_cet_missing_option_anchors(
            paper, raw, value.get("sourcePdfSha256", ""))
    for entry in private_options:
        record_id = entry.get("id")
        if not isinstance(record_id, str) or record_id in ids:
            raise ValueError(f"duplicate or missing option ID: {record_id}")
        ids.add(record_id)
        if (entry.get("optionId") != record_id or
                entry.get("kind") not in {"answer_option", "word_bank_option"} or
                not str(entry.get("questionId", "")).startswith(expected_paper_id + ":")):
            raise ValueError(f"invalid option identity: {record_id}")
        original = entry.get("sourceText")
        if not isinstance(original, str) or entry.get("sourceHash") != sha256(original):
            raise ValueError(f"option source hash mismatch: {record_id}")
        source_ids = entry.get("sourceBlockIds")
        if (not isinstance(source_ids, list) or any(
                not isinstance(source_id, str) or
                not source_id.startswith(expected_paper_id + ":b-")
                for source_id in source_ids)):
            raise ValueError(f"invalid option source blocks: {record_id}")
        source_input = entry.get("translationInput")
        if source_input is not None and entry.get("translationInputHash") != sha256(source_input):
            raise ValueError(f"option translation input hash mismatch: {record_id}")
        pdf_provenance = entry.get("pdfVerifiedSource")
        if pdf_provenance is not None:
            anchor = verified_pdf_options.get(record_id)
            if anchor and anchor.anchor_kind == "figure_bank":
                expected = {"sourcePdfSha256": anchor.source_pdf_sha256,
                            "pdfPage": anchor.source_pdf_page,
                            "anchorKind": anchor.anchor_kind,
                            "reflowBlockIds": [f"{expected_paper_id}:{bid}"
                                               for bid in anchor.reflow_block_ids],
                            "sourceOptionId": anchor.source_option_id}
                expected_source_ids = []
            else:
                anchor = verified_cet_options.get(record_id)
                expected = ({"sourcePdfSha256": anchor.source_pdf_sha256,
                             "pdfPage": anchor.source_pdf_page,
                             "anchorKind": anchor.anchor_kind,
                             "reflowBlockIds": [f"{expected_paper_id}:{anchor.reflow_block_id}"],
                             "reflowOptionIndex": anchor.reflow_option_index,
                             "sourceOptionId": record_id}
                            if anchor and anchor.anchor_kind == "word_bank_option" else None)
                expected_source_ids = ([f"{expected_paper_id}:{sid}"
                                        for sid in anchor.structured_source_block_ids]
                                       if expected else None)
            if (not expected or pdf_provenance != expected or
                    entry.get("reflowBlockIds") != expected["reflowBlockIds"] or
                    original != anchor.source_text or
                    entry["sourceBlockIds"] != expected_source_ids):
                raise ValueError(f"PDF option provenance mismatch: {record_id}")
            if entry["translationEligible"] and source_input != original:
                raise ValueError(f"PDF option translation input mismatch: {record_id}")
        if entry.get("translationEligible") is True:
            if not isinstance(source_input, str) or not source_input.strip():
                raise ValueError(f"eligible option has no input: {record_id}")
            expected_input = (entry.get("reflowSourceText") if "reflowBlockId" in entry
                              else original)
            if source_input != expected_input:
                raise ValueError(f"eligible option input differs from printed source: {record_id}")
            if record_id in quarantines:
                used_quarantines.add(record_id)
            elif not isinstance(entry.get("translationZh"), str) or not entry["translationZh"].strip():
                raise ValueError(f"eligible option untranslated: {record_id}")
        elif record_id in quarantines:
            raise ValueError(f"quarantine targets ineligible option: {record_id}")
        if "reflowBlockId" in entry:
            if (not str(entry["reflowBlockId"]).startswith(expected_paper_id + ":b-") or
                    type(entry.get("reflowOptionIndex")) is not int or
                    entry["reflowOptionIndex"] < 0 or
                    not isinstance(entry.get("reflowSourceText"), str)):
                raise ValueError(f"invalid raw option provenance: {record_id}")
            if (entry["translationEligible"] and
                    comparison_key(entry["reflowSourceText"]) != comparison_key(original)):
                raise ValueError(f"eligible option raw text mismatch: {record_id}")
        elif entry["translationEligible"] and pdf_provenance is None:
            raise ValueError(f"eligible option has no raw anchor: {record_id}")
        public = {key: entry[key] for key in PUBLIC_OPTION if key in entry}
        if record_id in quarantines:
            public["translationEligible"] = False
            public["translationZh"] = None
            public["translationStatus"] = "quality_quarantined"
            public["translationIssue"] = "translation_quality_review_required"
        elif not entry["translationEligible"]:
            public["translationZh"] = None
        result["options"].append(public)
    paragraph_by_id = {row["id"]: row for row in result["paragraphs"]}
    option_by_id = {row["id"]: row for row in result["options"]}
    for option in result["options"]:
        status = option.get("coverageStatus")
        if status not in {"covered_by_option", "covered_by_paragraph"}:
            continue
        if option["translationEligible"]:
            raise ValueError(f"translation alias incorrectly eligible: {option['id']}")
        referent = (option_by_id if status == "covered_by_option" else paragraph_by_id).get(
            option.get("translationRef"))
        if not referent or not referent.get("translationEligible") or not referent.get("translationZh"):
            raise ValueError(f"translation alias target unavailable: {option['id']}")
        if status == "covered_by_option":
            if (option["sourceHash"] != referent["sourceHash"] or
                    option["sourceText"] != referent["sourceText"]):
                raise ValueError(f"translation alias source mismatch: {option['id']}")
        else:
            passage_text = paragraph_choice_body(referent["sourceText"])
            if (comparison_key(passage_text) != comparison_key(option["sourceText"]) or
                    not set(option.get("sourceBlockIds", [])) &
                    set(referent.get("sourceBlockIds", []))):
                raise ValueError(f"translation alias passage mismatch: {option['id']}")
        option["translationZh"] = referent["translationZh"]
    if used_quarantines != set(quarantines):
        raise ValueError(f"quarantine ID absent from paper: {sorted(set(quarantines) - used_quarantines)}")
    return result


def published_sidecar_is_current(public: dict, private: dict, expected: dict,
                                 paper_id: str, saved_quarantines: dict[str, str]) -> None:
    """Audit public JSON using the answer-bearing private publication snapshot."""
    reconcile_source_inventory(private, expected, paper_id)
    if ([issue for issue in private.get("issues", [])
         if issue.get("code") != "stale_translation"] != expected.get("issues", [])):
        raise ValueError(f"published source issues changed: {paper_id}")

    candidate = copy.deepcopy(expected)
    # Preserve the audit issue added while the private translation was built.
    candidate["issues"] = private.get("issues", [])
    public_rows = {row["id"]: row for collection in ("paragraphs", "options")
                   for row in public.get(collection, [])}
    private_rows = {row["id"]: row for collection in ("paragraphs", "options")
                    for row in private[collection]}
    for collection in ("paragraphs", "options"):
        for row in candidate[collection]:
            if not row["translationEligible"]:
                continue
            record_id = row["id"]
            published = public_rows.get(record_id, {})
            previous = private_rows[record_id]
            translated = published.get("translationZh")
            if (previous.get("translationZh") and
                    previous["translationZh"] != translated):
                raise ValueError(f"published translation differs from private snapshot: {record_id}")
            if translated is not None:
                if (not previous.get("translationZh") and
                        (collection != "options" or record_id not in saved_quarantines)):
                    raise ValueError(f"new published translation lacks private provenance: {record_id}")
                row["translationZh"] = translated
    quarantines = {
        record_id: reason for record_id, reason in saved_quarantines.items()
        if record_id.startswith(paper_id + ":") and
        public_rows.get(record_id, {}).get("translationStatus") == "quality_quarantined"
    }
    projected = public_sidecar(candidate, paper_id, quarantines)
    if public != projected:
        raise ValueError(f"published sidecar differs from current source projection: {paper_id}")


def latest_private_snapshot() -> tuple[Path, dict[str, str], dict[str, str]]:
    snapshots = sorted((ROOT / ".local").glob("english-translation-private-*"), reverse=True)
    for snapshot in snapshots:
        manifest_path = snapshot / "manifest.json"
        if not manifest_path.is_file():
            continue
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        files = {row["path"]: row["sha256"] for row in manifest.get("files", [])}
        if len(files) != 206:
            continue
        quarantine_path = snapshot / "quality-quarantine.json"
        quarantines = read_quarantines(quarantine_path) if quarantine_path.is_file() else {}
        return snapshot, files, quarantines
    raise ValueError("already published sidecars require a complete private publication snapshot")


def prepare(quarantines: dict[str, str] | None = None,
            verified_dictation_path: Path | None = None,
            publishing: bool = False) -> list[tuple[Path, bytes, bytes]]:
    """Validate all canonical files before any public write."""
    quarantines = quarantines or {}
    if verified_dictation_path is None and DEFAULT_VERIFIED_DICTATION.is_file():
        verified_dictation_path = DEFAULT_VERIFIED_DICTATION
    dictation_by_paper = verified_dictation_papers(verified_dictation_path)
    prepared = []
    seen_quarantines = set()
    snapshot = None
    for path, source in canonical_entries():
        original = path.read_bytes()
        category, stem = path.parent.name, path.stem
        paper_id = f"{category}:{stem}"
        source_path = REFLOW / category / "papers" / f"{stem}.json"
        paper_path = STRUCTURED / "papers" / category / f"{stem}.json"
        paper = json.loads(paper_path.read_text(encoding="utf-8"))
        if paper.get("id") != paper_id:
            raise ValueError(f"canonical structured paper mismatch: {paper_path}")
        raw = json.loads(source_path.read_text(encoding="utf-8"))
        expected = build_paper(paper, raw, str(source_path.relative_to(ROOT)),
                               source["source_pdf_sha256"], dictation_by_paper.get(paper_id))
        private = json.loads(original)
        rows = [row for collection in ("paragraphs", "options")
                for row in private.get(collection, [])]
        if rows and all("translationInput" not in row for row in rows):
            if publishing:
                raise ValueError(f"already published sidecar cannot be published again: {paper_id}")
            if snapshot is None:
                snapshot = latest_private_snapshot()
            snapshot_dir, hashes, saved_quarantines = snapshot
            relative = path.relative_to(STRUCTURED / "translations")
            saved_path = snapshot_dir / relative
            saved = saved_path.read_bytes()
            if hashlib.sha256(saved).hexdigest() != hashes.get(str(relative)):
                raise ValueError(f"private publication snapshot hash mismatch: {relative}")
            published_sidecar_is_current(private, json.loads(saved), expected,
                                         paper_id, saved_quarantines)
            prepared.append((path, original, original))
            continue
        reconcile_source_inventory(private, expected, paper_id)
        scoped = {record_id: reason for record_id, reason in quarantines.items()
                  if record_id.startswith(paper_id + ":")}
        public = public_sidecar(private, paper_id, scoped)
        seen_quarantines.update(scoped)
        serialized = (json.dumps(public, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        prepared.append((path, original, serialized))
    if seen_quarantines != set(quarantines):
        raise ValueError(f"quarantine ID has no canonical paper: {sorted(set(quarantines) - seen_quarantines)}")
    return prepared


def read_quarantines(path: Path | None) -> dict[str, str]:
    if path is None:
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("schema") != "english-paragraph-translation-quarantine.v1":
        raise ValueError("wrong translation quarantine schema")
    result = {}
    for item in value.get("items", []):
        record_id = item.get("id")
        reason = item.get("reason")
        if not isinstance(record_id, str) or not isinstance(reason, str) or not reason.strip():
            raise ValueError("quarantine requires id and nonempty reason")
        if record_id in result:
            raise ValueError(f"duplicate quarantine ID: {record_id}")
        result[record_id] = reason
    return result


def publish(prepared: list[tuple[Path, bytes, bytes]],
            quarantines: dict[str, str] | None = None) -> Path:
    snapshot = (ROOT / ".local" /
                f"english-translation-private-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{os.getpid()}")
    snapshot.mkdir(parents=True, exist_ok=False)
    manifest = []
    staged = []
    for path, original, public in prepared:
        relative = path.relative_to(STRUCTURED / "translations")
        private = snapshot / relative
        private.parent.mkdir(parents=True, exist_ok=True)
        private.write_bytes(original)
        public_stage = snapshot / ".staged-public" / relative
        public_stage.parent.mkdir(parents=True, exist_ok=True)
        public_stage.write_bytes(public)
        rollback = snapshot / ".rollback" / relative
        rollback.parent.mkdir(parents=True, exist_ok=True)
        rollback.write_bytes(original)
        staged.append((path, original, public_stage, rollback))
        manifest.append({"path": str(relative), "sha256": hashlib.sha256(original).hexdigest()})
    (snapshot / "manifest.json").write_text(
        json.dumps({"files": manifest}, indent=2) + "\n", encoding="utf-8")
    if quarantines:
        (snapshot / "quality-quarantine.json").write_text(
            json.dumps({"schema": "english-paragraph-translation-quarantine.v1",
                        "items": [{"id": record_id, "reason": reason}
                                  for record_id, reason in sorted(quarantines.items())]},
                       ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    # A stale read means the translation worker wrote after preflight. Stop
    # without touching any public file; the caller can retry after it stops.
    for path, original, _, _ in staged:
        if path.read_bytes() != original:
            raise RuntimeError(f"sidecar changed during publish preflight: {path}")
    changed = []
    try:
        for path, original, public_stage, rollback in staged:
            # Catch a late writer before replacing the next file. A failure
            # restores all earlier files from the nonserved private snapshot.
            if path.read_bytes() != original:
                raise RuntimeError(f"sidecar changed during publish swap: {path}")
            os.replace(public_stage, path)
            changed.append((path, rollback))
    except Exception as exc:
        rollback_failures = []
        for path, rollback in reversed(changed):
            try:
                os.replace(rollback, path)
            except OSError as rollback_error:
                rollback_failures.append(f"{path}: {rollback_error}")
        if rollback_failures:
            raise RuntimeError(
                f"publish failed and rollback was incomplete; private backup={snapshot}; "
                f"rollback errors={rollback_failures}") from exc
        raise RuntimeError(
            f"publish failed; restored {len(changed)} sidecars from private backup={snapshot}") from exc
    return snapshot


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--publish", action="store_true",
                        help="backup complete sidecars and replace them with public-safe JSON")
    parser.add_argument("--quarantine-file", type=Path,
                        help="private JSON list of explicitly rejected or unresolved translation IDs")
    parser.add_argument("--verified-dictation", type=Path,
                        help="same private source-cited listening answer file used for manifest generation")
    args = parser.parse_args()
    quarantines = read_quarantines(args.quarantine_file)
    prepared = prepare(quarantines, args.verified_dictation, publishing=args.publish)
    print(json.dumps({"validatedPapers": len(prepared),
                      "publicBytes": sum(len(public) for _, _, public in prepared),
                      "mode": "publish" if args.publish else "check"}))
    if args.publish:
        print(f"privateBackup={publish(prepared, quarantines)}")


if __name__ == "__main__":
    main()
