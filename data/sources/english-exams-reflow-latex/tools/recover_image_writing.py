"""Recover Kaoyan English II writing pages printed as a single PDF image.

These four page-14 transcriptions were checked against the rendered source
PDFs.  The chart/table stays an exact crop of that page, including its printed
title or caption; no values are inferred from OCR.
"""

IMAGE_WRITING_PART_B = {
    "2011-02": {
        "instructions": (
            ("paragraph", "Write an essay based on the following chart. In your writing, you should"),
            ("question", "1) interpret the chart, and"),
            ("question", "2) give your comments."),
            ("paragraph", "You should write at least 150 words."),
            ("paragraph", "Write your essay on the ANSWER SHEET. (15 points)"),
        ),
        "figure_bbox": (140, 249, 480, 480),
    },
    "2012-02": {
        "instructions": (
            ("paragraph", "Write an essay based on the following table. In your writing, you should"),
            ("question", "1) describe the table, and"),
            ("question", "2) give your comments."),
            ("paragraph", "You should write at least 150 words."),
            ("paragraph", "Write your essay on the ANSWER SHEET. (15 points)"),
        ),
        "figure_bbox": (64, 244, 530, 409),
    },
    "2018-02": {
        "instructions": (
            ("paragraph", "Write an essay based on the chart below. In your writing, you should"),
            ("question", "1) interpret the chart, and"),
            ("question", "2) give your comments."),
            ("paragraph", "You should write about 150 words on the ANSWER SHEET. (15 points)"),
        ),
        "figure_bbox": (160, 218, 454, 469),
    },
    "2020-02": {
        "instructions": (
            ("paragraph", "Write an essay based on the chart below. In your writing, you should"),
            ("question", "1) interpret the chart, and"),
            ("question", "2) give your comments."),
            ("paragraph", "You should write about 150 words on the ANSWER SHEET. (15 points)"),
        ),
        "figure_bbox": (128, 220, 446, 508),
    },
}


def recover_image_writing(category, stem, page_number, blocks, page):
    """Add source-checked Part B text and its original chart to image-only pages."""
    if category != "kaoyan" or stem not in IMAGE_WRITING_PART_B or page_number != 14:
        return
    assert not blocks, (stem, page_number, "source extractor unexpectedly returned text")
    assert not page.get_text().strip(), (stem, page_number, "source text layer changed")
    assert len(page.get_images(full=True)) == 1, (stem, page_number, "source image changed")
    spec = IMAGE_WRITING_PART_B[stem]

    def line(kind, value):
        return {"type": kind, "runs": [{"text": value, "flags": [kind in {"heading", "question"}, False, False]}]}

    blocks.extend((line("heading", "Part B"), line("question", "48. Directions:")))
    blocks.extend(line(kind, value) for kind, value in spec["instructions"])
    bbox = list(spec["figure_bbox"])
    assert page.rect.contains(page.rect.__class__(bbox)), (stem, bbox)
    blocks.append({"type": "figure", "bbox": bbox})
