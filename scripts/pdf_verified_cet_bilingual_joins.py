"""Five source-verified CET-6 translation prompts split into adjacent raw blocks.

This module reads the unchanged original PDF and reflow JSON. It returns
derived text and provenance for the paragraph manifest builder; it never
rewrites source blocks, answer keys, translation sidecars, or the database.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PDF_DIR = ROOT / "data/sources/english-exams-web-2026-09-26/.firecrawl/cet6"
CHINESE_CUE = re.compile(r"[(（][^()（）]*[)）]")


@dataclass(frozen=True)
class JoinSpec:
    from_block_id: str
    to_block_id: str
    from_block_sha256: str
    to_block_sha256: str
    joined_sha256: str
    separator: str
    pdf_page: int


@dataclass(frozen=True)
class VerifiedJoin:
    from_block_id: str
    to_block_id: str
    pdf_page: int
    original_pdf_sha256: str
    joined_text: str
    chinese_cue: str
    chinese_cue_span: tuple[int, int]

    @property
    def source_block_ids(self) -> tuple[str, str]:
        return self.from_block_id, self.to_block_id


# SHA values are for UTF-8 text from the raw runs, not a serialized JSON block.
# PDF page 19 and pages 14–15 were checked against the printed source prompts.
FIXTURES: dict[str, tuple[str, tuple[JoinSpec, ...]]] = {
    "cet6:2012-06-01": (
        "b0923d500beaef575eccc6ee67a3518f609f637cac54fd25be8db1f6238731e0",
        (
            JoinSpec("b-19-7", "b-19-8",
                     "90989eef7517767cd03b552993c40a8262868dd5d1ef41488ce3b2c4bf9c1d71",
                     "698d0fd3213ee7c83cd612957ad1918693415d89ba7eb8031f1ea792e7dff252",
                     "ce9cfc85dfdaa1177212f83d03e69d520f5f837736a1690ff4058be1d2622b4d", "", 19),
            JoinSpec("b-19-9", "b-19-10",
                     "34fe1c6fcced4daf2650d34808248df6d2c96665c21ec80a012b83c1637c6bf5",
                     "91c54db28cf2df1346b026b3a12c4fdd36d35499f711a50d85f8fc7363307d8a",
                     "a0768716a55aee251cec129527efb219522727047712dabe7e5f235d91ceeec5", "", 19),
            JoinSpec("b-19-11", "b-19-12",
                     "5fdd4a8a60cc3dca53e7b4e301cd9bcddaa163ee6e94d1a69189e7d56866a7c2",
                     "6b56a7a1698c15e5f11289d167e3ce9ea9c1fea75605604ad423c7477f3ec0e1",
                     "ac445543ea72db7317e7fb5f1dde55f8e47637ba21dbf60eee2716e4e999fdbc", " ", 19),
        ),
    ),
    "cet6:2012-12-02": (
        "e75b7941475cf515f43b58bed01ec452ca8431dbaf5181a6e9c49d081f42cdbc",
        (
            JoinSpec("b-14-27", "b-14-28",
                     "55242bd2123016300b314f5d0142cbfbb7e57f59df8b9009031b1e48a4db37c8",
                     "1523e79f67034a8280d0ec227159eef99f282bf6fd0ac08eb323ae812b142112",
                     "9c021b484ed236d026536177fca7b4be082d855f04931646831e99b77d00dc5a", "", 14),
            JoinSpec("b-15-2", "b-15-3",
                     "b7d91d274af70f181f0d478c1cc0bd7455de6941cfbd02a1393f28e2fced3ab7",
                     "c5125a6562a3ea8378a2455cdff66bd14c232c13190aac3378120c119220af8d",
                     "533664dc6c2383be3484134715a82f6d2ab3838f624cd16343393202660dfcf6", "", 15),
        ),
    ),
}


def _hash(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _raw_block(raw: dict, block_id: str) -> dict:
    prefix, page, index = block_id.split("-")
    if prefix != "b":
        raise ValueError(f"invalid block ID: {block_id}")
    try:
        return raw["pages"][int(page) - 1]["blocks"][int(index) - 1]
    except (IndexError, KeyError, TypeError) as exc:
        raise ValueError(f"missing raw block: {block_id}") from exc


def _raw_text(block: dict) -> str:
    return "".join(run.get("text", "") for run in block.get("runs", []))


def verified_bilingual_completion_joins(
    paper_id: str, pdf_sha256: str, raw: dict, *, pdf_dir: Path = PDF_DIR
) -> dict[str, VerifiedJoin]:
    """Return exact adjacent-block joins, or fail on source/PDF drift.

    The caller can merge each pair in its derived manifest. In particular,
    the Chinese cue span is provenance that must be protected if a translator
    treats ``joined_text`` as English input.
    """
    fixture = FIXTURES.get(paper_id)
    if fixture is None:
        return {}
    expected_pdf_sha, specs = fixture
    pdf_path = pdf_dir / f"{paper_id.split(':', 1)[1]}.pdf"
    if pdf_sha256 != expected_pdf_sha or not pdf_path.is_file() or _hash(pdf_path.read_bytes()) != expected_pdf_sha:
        raise ValueError(f"{paper_id}: original PDF hash differs from verified fixture")
    joins = {}
    for spec in specs:
        _, from_page, from_index = spec.from_block_id.split("-")
        _, to_page, to_index = spec.to_block_id.split("-")
        if (int(from_page) != spec.pdf_page or from_page != to_page or
                int(to_index) != int(from_index) + 1):
            raise ValueError(f"{paper_id}: fixture blocks are not adjacent on one PDF page")
        first = _raw_block(raw, spec.from_block_id)
        second = _raw_block(raw, spec.to_block_id)
        if first.get("type") != "question" or second.get("type") != "paragraph":
            raise ValueError(f"{paper_id}: split prompt block types changed")
        first_text, second_text = _raw_text(first), _raw_text(second)
        if (_hash(first_text.encode()) != spec.from_block_sha256 or
                _hash(second_text.encode()) != spec.to_block_sha256):
            raise ValueError(f"{paper_id}: split prompt text changed")
        joined = first_text + spec.separator + second_text
        if _hash(joined.encode()) != spec.joined_sha256:
            raise ValueError(f"{paper_id}: joined translation input changed")
        cue = CHINESE_CUE.search(joined)
        if not cue or not re.search(r"[\u3400-\u9fff]", cue.group()):
            raise ValueError(f"{paper_id}: complete Chinese source cue missing")
        joins[spec.from_block_id] = VerifiedJoin(
            spec.from_block_id, spec.to_block_id, spec.pdf_page,
            expected_pdf_sha, joined, cue.group(), cue.span(),
        )
    return joins
