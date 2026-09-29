#!/usr/bin/env python3
"""Check the generated exam-bank contract against its source documents."""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import re

from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[1] / "data/sources/exam-library"
OUT = ROOT / "structured"
BLOCK_ID = re.compile(r"b-(\d+)-(\d+)$")
PDF_DOTTED_OPTION_PAPERS = frozenset({"cet6:2018-06-02", "cet6:2018-06-03"})


def valid_printed_option_label(paper_id: str, label: str, source_label: str) -> bool:
    """Permit the source's A). label only for its two verified CET-6 PDFs."""
    if paper_id in PDF_DOTTED_OPTION_PAPERS and source_label == label[0] + ").":
        return True
    printed = re.fullmatch(r"\s*[（(]?\s*([A-H])\s*[)）.．、]?\s*", source_label)
    return bool(printed and printed.group(1) + "." == label)


def main() -> None:
    documents = json.loads((ROOT / "documents.json").read_text(encoding="utf-8"))
    audit = json.loads((OUT / "audit.json").read_text(encoding="utf-8"))
    templates = json.loads((OUT / "templates.json").read_text(encoding="utf-8"))["templates"]
    assert len(documents) == audit["papers"] == len(audit["documents"]) == 335
    assert {d["id"] for d in documents} == {d["id"] for d in audit["documents"]}
    papers = {}
    prompts = {}
    totals = Counter()
    for row in audit["documents"]:
        json_path = OUT / row["json"]
        html_path = OUT / row["reader"]
        assert json_path.is_file() and html_path.is_file(), row["id"]
        paper = json.loads(json_path.read_text(encoding="utf-8"))
        papers[paper["id"]] = paper
        assert paper["schema"] == "exam-paper.v1" and paper["template"] in templates
        assert templates[paper["template"]]["category"] == paper["category"]
        assert (json_path.parent / paper["source"]["original"]).is_file()
        assert (json_path.parent / paper["source"]["reflow"]).is_file()
        ids = [block["id"] for block in paper["blocks"]]
        assert len(ids) == len(set(ids)) == paper["audit"]["sourceBlocks"] == paper["audit"]["renderedBlocks"]
        original = BeautifulSoup((json_path.parent / paper["source"]["reflow"]).read_text(encoding="utf-8"), "html.parser")
        pages = original.select("main > section[data-source-page]")
        assert len(pages) == paper["pages"]
        config_node = original.find(id="exam-reader-config")
        assert config_node is not None, row["id"]
        config = json.loads(config_node.get_text())
        assert len(config.get("structuredToc", [])) == len(paper["toc"]), row["id"]
        for item, entry in zip(config["structuredToc"], paper["toc"]):
            page_index, block_index = map(int, BLOCK_ID.fullmatch(entry["sourceBlockId"]).groups())
            assert item == {"label": entry["label"], "level": entry["level"],
                            "pageIndex": page_index, "blockIndex": block_index}
        for block in paper["blocks"]:
            page_index, block_index = map(int, BLOCK_ID.fullmatch(block["id"]).groups())
            source_block = pages[page_index - 1].find_all(recursive=False)[block_index - 1]
            assert source_block is not None
            assert block["sourcePageIndex"] == page_index and block["sourceBlockIndex"] == block_index
            if "choice-scroll" in source_block.get("class", []):
                number = source_block.select_one(".choice-number")
                if number and re.match(r"\d{1,3}\s*[.．、]", number.get_text(" ", strip=True)):
                    assert any(entry["kind"] == "question" and entry["sourceBlockId"] == block["id"]
                               for entry in paper["toc"]), (row["id"], block["id"])
        question_ids = [q["id"] for q in paper["questions"]]
        assert len(question_ids) == len(set(question_ids))
        block_set = set(ids)
        for question in paper["questions"]:
            assert set(question["sourceBlocks"]).issubset(block_set)
            assert question["questionType"] in {"single_choice", "multiple_choice", "fill_blank", "free_response", "answer"}
            labels = [option["label"] for option in question["options"]]
            matching_bank = (paper["category"] == "kaoyan" and
                             (question.get("context") or {}).get("kind") in
                             {"matching_table", "matching_comments", "ordering_diagram",
                              "numbered_gap_passage"})
            allowed_labels = "ABCDEFGH" if matching_bank else "ABCDE"
            assert labels == sorted(labels, key=lambda label: allowed_labels.index(label[0]))
            if len(labels) != len(set(labels)):
                assert question["status"] == "partial"
            assert all(label in {f"{letter}." for letter in allowed_labels} for label in labels)
            if question["status"] == "partial":
                # A damaged printed label must remain visible for review.
                # Examples include CET6 2015 Q56's "56." and CET4 2014
                # Q61's "AD)"; neither is a verified complete choice set.
                assert all(option["sourceLabel"].strip() for option in question["options"])
            else:
                for option in question["options"]:
                    assert valid_printed_option_label(
                        row["id"], option["label"], option["sourceLabel"]), (
                        row["id"], question["number"], option["label"], option["sourceLabel"])
            answer = question["answer"]
            assert all(key in answer for key in ("value", "solution", "explanation", "commentary", "knowledge", "sourceDocumentId", "sourceQuestionIds", "sourceBlocks", "sourcePages", "status"))
            context = question["context"]
            if context:
                assert context["text"] and set(context["sourceBlocks"]).issubset(block_set)
                assert set(context["sourcePages"]).issubset({block["page"] for block in paper["blocks"]})
            if question["recordType"] == "question":
                prompts[paper["id"] + ":" + question["id"]] = (paper, question)
                totals["questions"] += 1
                if answer["status"] == "explicit":
                    totals["linkedAnswers"] += 1
                    assert any(answer[key] for key in ("value", "solution", "explanation", "commentary", "knowledge"))
                else:
                    assert answer["status"] in {"missing", "ambiguous"}
                    if answer["status"] == "ambiguous":
                        assert not any(answer[key] for key in ("value", "solution", "explanation", "commentary", "knowledge"))
                        assert answer.get("ambiguityReason")
        seen_sections = {}
        for entry in paper["toc"]:
            assert entry["sourceBlockId"] in block_set
            if entry.get("parentId"):
                assert entry["parentId"] in seen_sections
                assert seen_sections[entry["parentId"]]["level"] < entry["level"]
            if entry["kind"] == "question":
                assert entry["id"] in question_ids
            else:
                seen_sections[entry["id"]] = entry
        rendered = BeautifulSoup(html_path.read_text(encoding="utf-8"), "html.parser")
        assert len(rendered.select(".source-block")) == len(ids), row["id"]
        assert len(rendered.select(".question-card")) == len(question_ids), row["id"]
        for entry in paper["toc"]:
            assert rendered.find(id=entry["id"]), (row["id"], entry["id"])
        totals["papers"] += 1
        totals["blocks"] += len(ids)
    for paper, question in prompts.values():
        answer = question["answer"]
        source_id = answer["sourceDocumentId"]
        if not source_id:
            continue
        source = papers[source_id]
        assert set(answer["sourceQuestionIds"]).issubset({q["id"] for q in source["questions"]})
        assert set(answer["sourceBlocks"]).issubset({b["id"] for b in source["blocks"]})
        assert set(answer["sourcePages"]).issubset({b["page"] for b in source["blocks"]})
    kaoyan = papers["kaoyan:2026-01"]
    headings = {entry["label"]: entry for entry in kaoyan["toc"] if entry["kind"] == "section"}
    assert headings["Section II Reading Comprehension"]["level"] == 0
    reading_part = next(entry for entry in kaoyan["toc"] if entry["label"] == "Part A" and entry["parentId"] == headings["Section II Reading Comprehension"]["id"])
    text_one = headings["Text 1"]
    assert (reading_part["level"], text_one["level"], text_one["parentId"]) == (1, 2, reading_part["id"])
    q21 = next(entry for entry in kaoyan["toc"] if entry["kind"] == "question" and entry["number"] == "21")
    assert (q21["level"], q21["parentId"]) == (3, text_one["id"])
    q1 = next(question for question in kaoyan["questions"] if question["number"] == "1")
    assert q1["context"] and "artificial intelligence" in q1["context"]["text"]
    cloze = papers["kaoyan:2015-02"]
    assert sum(question["number"] == "7" and question["recordType"] == "question"
               for question in cloze["questions"]) == 1
    late_blank = next(question for question in cloze["questions"] if question["number"] == "20")
    assert late_blank["context"] and "Talking to strangers" in late_blank["context"]["text"]
    preview = BeautifulSoup((OUT / "papers/kaoyan/2026-01.htm").read_text(encoding="utf-8"), "html.parser")
    assert preview.select_one(".choice-row.compact-choice-row")
    for year, modes, line_counts in (
        (2024, ("start", "middle", "end"), (1, 2, 1)),
        (2025, ("start", "end", "after"), (2, 2, 0)),
        (2026, ("single", "after"), (4, 0)),
    ):
        paper = papers[f"kaoyan:{year}-01"]
        preview = BeautifulSoup((OUT / f"papers/kaoyan/{year}-01.htm").read_text(encoding="utf-8"), "html.parser")
        block_data = {block["id"]: block for block in paper["blocks"]}
        for index, mode, count in zip(range(5, 5 + len(modes)), modes, line_counts):
            block_id = f"b-14-{index}"
            element = preview.find(id=block_id)
            assert element and f"email-{mode}" in element.get("class", []), (year, block_id)
            source = block_data[block_id]
            presentation = source["presentation"]
            assert presentation["version"] == 1 and presentation["layoutKind"] == "email"
            assert presentation["segment"] == mode
            assert presentation["framePart"] == ("none" if mode == "after" else mode)
            assert presentation["signoffAlignment"] == ("right" if year == 2024 else "left")
            assert ("email-signoff-right" in element.get("class", [])) == (year == 2024)
            lines = element.select(".email-card-part > .email-line")
            assert len(lines) == len(presentation["lines"]) == count, (year, block_id)
            assert [line.get_text(" ", strip=True) for line in lines] == [
                line["text"] for line in presentation["lines"]]
            assert " ".join(element.get_text(" ", strip=True).split()) == source["text"]
            assert " ".join(BeautifulSoup(source["contentHtml"], "html.parser").get_text(" ", strip=True).split()) == source["text"]
            assert presentation["instructionsOutsideFrame"] == bool(presentation["instructions"])
            assert [p.get_text(" ", strip=True) for p in element.select(".email-instructions > p")] == [
                item["text"] for item in presentation["instructions"]]
        instruction_block = 7 if year in {2024, 2025} else 6
        assert preview.select_one(f"#b-14-{instruction_block} .email-instructions strong").get_text(" ", strip=True) == "Do not"
        assert len(preview.select(f"#b-14-{instruction_block} .email-instructions > p")) == 2
        assert [line.get_text(" ", strip=True) for line in preview.select(".email-card-part .email-line") if
                "email-closing" in line.get("class", []) or "email-signature" in line.get("class", [])] == ["Yours,", "Paul"]
        if year == 2024:
            assert all(not block.get("presentation", {}).get("layoutKind") == "email"
                       for block in paper["blocks"] if block["sourcePageIndex"] == 14 and block["sourceBlockIndex"] >= 8)
    math = papers["math3:1997-questions"]
    fill = next(question for question in math["questions"] if question["id"] == "q-1-1")
    choice = next(question for question in math["questions"] if question["id"] == "q-1-2")
    assert fill["questionType"] == "fill_blank" and choice["questionType"] == "single_choice"
    assert fill["answer"]["status"] == choice["answer"]["status"] == "explicit"
    assert "e^{f(x)}" in fill["answer"]["value"]
    assert choice["answer"]["value"] == "B"
    assert fill["answer"]["sourceDocumentId"] == choice["answer"]["sourceDocumentId"] == "math3:1997-answers"
    assert fill["answer"]["sourceQuestionIds"] == ["q-1-1"]
    assert choice["answer"]["sourceQuestionIds"] == ["q-1-2"]
    assert fill["answer"]["sourcePages"] == choice["answer"]["sourcePages"] == ["119"]
    assert papers["cet6:2015-12-02"]["pages"] == 9
    politics = papers["politics:2023-questions"]
    assert (politics["audit"]["politicsContinuations"], politics["audit"]["politicsPageArtifacts"],
            politics["audit"]["politicsSubquestions"], politics["audit"]["politicsVerifiedCorrections"]) == (8, 0, 10, 2)
    politics_blocks = {block["id"]: block for block in politics["blocks"]}
    assert "二。二O年" in politics_blocks["b-7-1"]["text"]
    assert "二〇二〇年" in politics_blocks["b-7-1"]["presentation"]["displayText"]
    q18 = next(question for question in politics["questions"] if question["number"] == "18")
    assert [option["label"] for option in q18["options"]] == ["A.", "B.", "C.", "D."]
    assert "sourceText" not in q18["options"][0] and "-3" not in q18["options"][0]["text"]
    assert q18["sourceBlocks"] == ["b-3-14", "b-3-15", "b-4-1", "b-4-2"]
    politics_preview = BeautifulSoup((OUT / "papers/politics/2023-questions.htm").read_text(encoding="utf-8"), "html.parser")
    assert politics_preview.find(id="b-4-1").has_attr("hidden")
    assert "-8 -" not in politics_preview.find(id="b-8-2").get_text()
    assert "二〇二〇年" in politics_preview.find(id="b-7-1").get_text()
    q37_parts = [node.get_text(" ", strip=True) for node in politics_preview.find(id="b-10-1").select("p")]
    assert sum(part.startswith(("(1)", "（1）", "(2)", "（2）")) for part in q37_parts) == 2
    q38_parts = [node.get_text(" ", strip=True) for node in politics_preview.find(id="b-11-1").select("p")]
    material_start = q38_parts.index("材料2")
    assert [part[:9] for part in q38_parts[material_start + 1:material_start + 5]] == [
        "当前世界经济面临衰", "作为在全球范围内以", "中国提出的全球发展", "针对人类发展面临的",
    ]
    bank = [json.loads(line) for line in (OUT / "question-bank.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(bank) == len(prompts) == audit["bank"]["questions"]
    assert len({item["id"] for item in bank}) == len(bank)
    assert {item["id"] for item in bank} == set(prompts)
    assert (OUT / "index.htm").is_file()
    print(json.dumps(dict(totals), ensure_ascii=False))


if __name__ == "__main__":
    main()
