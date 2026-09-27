"""Build source-page and before-crop images for the 35 repaired figures.

Run from any directory with the project virtual environment's Python:
    .venv/bin/python scripts/build_crop_review_assets.py

The four local audit reports are the repair list. Source PDFs and current PNGs
are read only. Image paths in the output are relative to crop-review.htm.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from dataclasses import dataclass
from pathlib import Path

import fitz


PROJECT = Path(__file__).resolve().parents[1]
SOURCES = PROJECT / "data/sources"
REVIEW_ROOT = SOURCES / "exam-library"
OUTPUT = REVIEW_ROOT / "crop-review"
ASSETS = OUTPUT / "assets"
AUDIT = PROJECT / ".local/image-audit"
EXPECTED_COUNTS = {"english": 10, "cs408-questions": 17, "cs408-answers": 6, "math-politics": 2}


@dataclass(frozen=True)
class Crop:
    id: str
    category: str
    title: str
    source_page: int
    old_bbox: list[float]
    new_bbox: list[float]
    reason: str
    pdf: Path
    pdf_sha256: str
    after_image: Path


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def repository_path(value: str) -> Path:
    """Resolve a report asset path without allowing it outside data/sources."""
    path = (PROJECT / value).resolve()
    if not path.is_relative_to(SOURCES.resolve()):
        raise ValueError(f"Asset is outside data/sources: {value}")
    return path


def figure_block(document: Path, source_page: int, block_index: int) -> dict:
    data = read_json(document)
    page = next((p for p in data["pages"] if p.get("source_page") == source_page), None)
    if page is None or block_index >= len(page["blocks"]):
        raise ValueError(f"Figure block missing: {document}, page {source_page}, block {block_index}")
    block = page["blocks"][block_index]
    if block["type"] != "figure":
        raise ValueError(f"Expected a figure: {document}, page {source_page}, block {block_index}")
    return block


def same_bbox(left: list[float], right: list[float]) -> bool:
    return len(left) == len(right) == 4 and all(abs(a - b) < 0.02 for a, b in zip(left, right))


def require_current_bbox(actual: list[float], expected: list[float], figure: str) -> None:
    if not same_bbox(actual, expected):
        raise ValueError(f"Current source bbox differs from audit for {figure}: {actual} != {expected}")


def english_crops() -> list[Crop]:
    report = read_json(AUDIT / "crop-audit-english.json")
    paper_metadata = {entry["file"]: entry for entry in read_json(SOURCES / "english-exams-reflow-latex/manifest.json")["papers"]}
    crops = []
    for item in report["suspected_and_fixed"]:
        category, stem = item["paper"].split("/")
        paper_file = f"{category}/papers/{stem}.htm"
        metadata = paper_metadata[paper_file]
        paper_json = SOURCES / "english-exams-reflow-latex" / category / "papers" / f"{stem}.json"
        block = read_json(paper_json)["pages"][item["page"] - 1]["blocks"][item["block"]]
        if block["type"] != "figure":
            raise ValueError(f"Expected English figure: {paper_json}, {item}")
        require_current_bbox(block["bbox"], item["new_bbox"], item["paper"])
        source_collection = "kaoyan-web-2026-09-26" if category == "kaoyan" else "english-exams-web-2026-09-26"
        pdf = SOURCES / source_collection / ".firecrawl"
        if category != "kaoyan":
            pdf /= category
        pdf /= f"{stem}.pdf"
        image = paper_json.with_suffix(".assets") / f"figure-{item['page']:03d}-{item['block']:03d}.png"
        crops.append(Crop(
            id=f"english-{category}-{stem}-p{item['page']:03d}-b{item['block']:03d}",
            category="english",
            title=f"{metadata['title']} · 第 {item['page']} 页插图",
            source_page=item["page"],
            old_bbox=item["old_bbox"],
            new_bbox=item["new_bbox"],
            reason=item["reason"],
            pdf=pdf,
            pdf_sha256=metadata["source_pdf_sha256"],
            after_image=image,
        ))
    return crops


def cs408_question_crops() -> list[Crop]:
    report = read_json(AUDIT / "crop-audit-cs-questions.json")
    collection = SOURCES / "cs408-latex-2009-2017"
    metadata = {entry["id"]: entry for entry in read_json(collection / "sources.json")}
    crops = []
    for item in report["fixes"]:
        source = metadata[item["sourceId"]]
        if Path(item["sourcePdf"]).resolve() != Path(source["path"]).resolve():
            raise ValueError(f"Source PDF path differs from metadata: {item['figure']}")
        if item["sourcePdfSha256"] != source["sha256"]:
            raise ValueError(f"Source PDF hash differs from metadata: {item['figure']}")
        document = collection / "source" / f"{source['year']}.json"
        block = figure_block(document, item["pdfPage"], item["blockIndex"])
        require_current_bbox(block["bbox"], item["newBbox"], item["figure"])
        crops.append(Crop(
            id=f"cs408-questions-{item['figure']}",
            category="cs408-questions",
            title=f"{source['title']} · {item['caption']}",
            source_page=item["pdfPage"],
            old_bbox=item["oldBbox"],
            new_bbox=item["newBbox"],
            reason=item["pdfEvidence"],
            pdf=Path(source["path"]),
            pdf_sha256=source["sha256"],
            after_image=repository_path(item["artifacts"][".png"]),
        ))
    return crops


def cs408_answer_crops() -> list[Crop]:
    report = read_json(AUDIT / "crop-audit-cs-answers.json")
    collection = SOURCES / "cs408-answers-latex-2016-2025"
    metadata = {entry["id"]: entry for entry in read_json(collection / "sources.json")}
    crops = []
    for item in report["figures"]:
        if item["status"] != "repaired":
            continue
        source_id = item["id"].rsplit("-p", 1)[0]
        source = metadata[source_id]
        if item["sourcePdfSha256"] != source["sha256"]:
            raise ValueError(f"Source PDF hash differs from metadata: {item['id']}")
        document = collection / "source" / f"{source['year']}.json"
        block = figure_block(document, item["sourcePage"], item["blockIndex"])
        require_current_bbox(block["bbox"], item["bbox"], item["id"])
        crops.append(Crop(
            id=f"cs408-answers-{item['id']}",
            category="cs408-answers",
            title=f"{source['title']} · {block.get('caption') or item['id']}",
            source_page=item["sourcePage"],
            old_bbox=item["oldBbox"],
            new_bbox=item["bbox"],
            reason=item["issue"],
            pdf=Path(source["path"]),
            pdf_sha256=source["sha256"],
            after_image=repository_path(item["assets"]["png"]["path"]),
        ))
    return crops


def math_politics_crops() -> list[Crop]:
    report = read_json(AUDIT / "crop-audit-math-politics.json")
    crops = []
    for item in report["items"]:
        if item["status"] != "fixed":
            continue
        document = repository_path(item["document"])
        collection = document.parents[1]
        metadata = read_json(collection / "source-metadata.json")
        block = figure_block(document, item["sourcePage"], item["blockIndex"])
        require_current_bbox(block["bbox"], item["bbox"], item["id"])
        crops.append(Crop(
            id=f"math-politics-{collection.name}-{document.stem}-{item['id']}",
            category="math-politics",
            title=f"数学三 {document.stem} · {block.get('caption') or item['id']}",
            source_page=item["sourcePage"],
            old_bbox=item["previousBBox"],
            new_bbox=item["bbox"],
            reason=item["evidence"],
            pdf=Path(metadata["path"]),
            pdf_sha256=metadata["sha256"],
            after_image=repository_path(item["originalAsset"]),
        ))
    return crops


def validate_bbox(values: list[float], page: fitz.Page, label: str) -> fitz.Rect:
    if len(values) != 4 or not all(isinstance(v, (int, float)) and math.isfinite(v) for v in values):
        raise ValueError(f"Invalid {label} bbox: {values}")
    box = fitz.Rect(values)
    bounds = page.rect
    if box.is_empty or box.is_infinite or not bounds.contains(box):
        raise ValueError(f"{label} bbox exceeds source page {bounds}: {values}")
    return box


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def relative_to_review(path: Path) -> str:
    result = Path(os.path.relpath(path, REVIEW_ROOT))
    if result.is_absolute() or (REVIEW_ROOT / result).resolve() != path.resolve():
        raise ValueError(f"Invalid relative image path: {path}")
    return result.as_posix()


def save_jpeg(page: fitz.Page, path: Path, *, scale: float, clip: fitz.Rect | None = None, quality: int = 80) -> None:
    pixmap = page.get_pixmap(matrix=fitz.Matrix(scale, scale), clip=clip, colorspace=fitz.csRGB, alpha=False)
    path.write_bytes(pixmap.tobytes(output="jpeg", jpg_quality=quality))


def verify_image(path: Path) -> None:
    image = fitz.Pixmap(str(path))
    if image.width < 1 or image.height < 1:
        raise ValueError(f"Empty image: {path}")


def build() -> None:
    groups = {
        "english": english_crops(),
        "cs408-questions": cs408_question_crops(),
        "cs408-answers": cs408_answer_crops(),
        "math-politics": math_politics_crops(),
    }
    for category, expected in EXPECTED_COUNTS.items():
        if len(groups[category]) != expected:
            raise ValueError(f"Expected {expected} {category} repairs, found {len(groups[category])}")
    crops = [crop for group in groups.values() for crop in group]
    if len(crops) != 35 or len({crop.id for crop in crops}) != 35:
        raise ValueError("Expected 35 unique repairs")

    # Check every original and current artifact before writing any output.
    pdf_hashes: dict[Path, str] = {}
    for crop in crops:
        if not crop.pdf.is_file() or not crop.after_image.is_file():
            raise FileNotFoundError(f"Missing source or repaired PNG for {crop.id}")
        if crop.pdf not in pdf_hashes:
            pdf_hashes[crop.pdf] = sha256(crop.pdf)
        actual = pdf_hashes[crop.pdf]
        if actual != crop.pdf_sha256:
            raise ValueError(f"Source PDF SHA-256 mismatch for {crop.id}: {crop.pdf}")
        if same_bbox(crop.old_bbox, crop.new_bbox):
            raise ValueError(f"Old and new bbox are identical for {crop.id}")
        verify_image(crop.after_image)

    ASSETS.mkdir(parents=True, exist_ok=True)
    entries = []
    rendered_pages: set[str] = set()
    for crop in crops:
        with fitz.open(crop.pdf) as document:
            if not 1 <= crop.source_page <= len(document):
                raise ValueError(f"Source page out of range for {crop.id}")
            page = document[crop.source_page - 1]
            old_box = validate_bbox(crop.old_bbox, page, f"{crop.id} old")
            validate_bbox(crop.new_bbox, page, f"{crop.id} new")
            if page.rotation != 0:
                raise ValueError(f"Unexpected rotated PDF page for {crop.id}")
            page_name = f"page-{crop.pdf_sha256[:12]}-p{crop.source_page:03d}.jpg"
            page_image = ASSETS / page_name
            before_image = ASSETS / f"before-{crop.id}.jpg"
            if page_name not in rendered_pages:
                save_jpeg(page, page_image, scale=1.5, quality=78)
                rendered_pages.add(page_name)
            save_jpeg(page, before_image, scale=2.0, clip=old_box, quality=86)
            entries.append({
                "id": crop.id,
                "category": crop.category,
                "title": crop.title,
                "sourcePage": crop.source_page,
                "oldBBox": crop.old_bbox,
                "newBBox": crop.new_bbox,
                "reason": crop.reason,
                "pageImage": relative_to_review(page_image),
                "beforeImage": relative_to_review(before_image),
                "afterImage": relative_to_review(crop.after_image),
                "pageWidth": page.rect.width,
                "pageHeight": page.rect.height,
            })

    # Resolve every browser URL from crop-review.htm and decode every referenced image.
    for entry in entries:
        for field in ("pageImage", "beforeImage", "afterImage"):
            image = (REVIEW_ROOT / entry[field]).resolve()
            if Path(entry[field]).is_absolute() or not image.is_file():
                raise ValueError(f"Broken relative {field} for {entry['id']}: {entry[field]}")
            verify_image(image)
        if not (0 <= entry["oldBBox"][0] < entry["oldBBox"][2] <= entry["pageWidth"]
                and 0 <= entry["oldBBox"][1] < entry["oldBBox"][3] <= entry["pageHeight"]
                and 0 <= entry["newBBox"][0] < entry["newBBox"][2] <= entry["pageWidth"]
                and 0 <= entry["newBBox"][1] < entry["newBBox"][3] <= entry["pageHeight"]):
            raise ValueError(f"Manifest bbox outside page for {entry['id']}")
    output = {"version": 1, "entries": entries}
    retained = {Path(entry[key]).name for entry in entries for key in ("pageImage", "beforeImage")}
    for old_asset in ASSETS.glob("*.jpg"):
        if old_asset.name not in retained:
            old_asset.unlink()
    target = OUTPUT / "manifest.json"
    staging = OUTPUT / "manifest.json.tmp"
    staging.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    staging.replace(target)
    asset_size = sum(path.stat().st_size for path in ASSETS.glob("*.jpg"))
    print(f"Wrote {target.relative_to(PROJECT)}: {len(entries)} entries, "
          f"{len(rendered_pages)} source-page JPEGs, {len(entries)} before JPEGs, "
          f"{asset_size / 1024 / 1024:.2f} MiB assets")


if __name__ == "__main__":
    build()
