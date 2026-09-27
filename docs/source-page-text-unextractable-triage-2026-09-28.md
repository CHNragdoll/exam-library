# Political science and CS408 PDF text-layer exceptions

The postbuild audit flags 126 `source_page_text_unextractable` pages: 91 Politics and 35 CS408. The finding means the PDF exposes fewer than 30 characters through its text layer; it does **not** by itself mean the page is blank or omitted. This review inspected the PDF image/text structure and structured source-page blocks for all 126 pages. The 26 flagged pages listed as visually checked below were individually viewed as rendered PDFs in this review. Politics 2022 questions p1 was also viewed to check its boundary with p2, but it is not one of the 126 flagged pages. A separate [Politics answer-page QA](politics-answer-pdf-page-qa-2026-09-28.md) visually checked 75 answer pages, 70 of them not viewed here. The remaining 30 CS408 answer pages were individually viewed in the [CS408 answer-page QA](cs408-answer-pdf-visual-audit-2026-09-28.md). Together these reviews visually checked all 126 flagged pages for page ownership, question numbering, and visible omissions; this does not certify every printed character.

The PDF structure separates into 78 image-backed pages (including one promotional page), 47 Politics answer pages rendered with a KaiTi CID font that has no Unicode mapping, and one genuinely blank CS408 page. Of the 124 pages with exam content, 120 initially had nonempty structured blocks on the matching PDF page. Visual comparison showed that nonempty blocks were insufficient evidence of exact page ownership: Politics 2022 had several choice and material fragments attributed to the preceding page, as well as three wholly empty content pages. Politics 2023 answers had one wholly empty content page. The 13 verified cross-page boundaries below were corrected using the rendered PDF; the question wording was preserved exactly.

| PDF source and page | Rendered-PDF boundary evidence | Repair |
| --- | --- | --- |
| Politics 2022 questions p2, Q4 | p1 ends with choices A/B; p2 begins “C.监事会 / D.董事长” | Moved the printed C/D row to p2. |
| Politics 2022 questions p3, Q8 | p2 ends with choices A/B; p3 begins with C/D | Moved the printed C/D row to p3. |
| Politics 2022 questions p4–5, section heading | p4 ends “至”; p5 begins “少有两个选项” | Split the multiple-choice instructions at the PDF page break. |
| Politics 2022 questions p6, Q20 | p5 ends with the stem; p6 begins with choices A–D | Moved the printed choices to p6. |
| Politics 2022 questions p8, Q27 | p7 ends “生死攸关”; p8 begins “的转折点。这次会议” | Split the stem and printed choices across p7–8. |
| Politics 2022 questions p10, Q34 | p9 ends “底线思”; p10 begins “维、居安思危” | Split the material across p9–10. |
| Politics 2022 questions p11, Q35 | p10 ends “目标迈进”; p11 begins “的重大历史关头” | Split the material across p10–11. |
| Politics 2022 questions p12, Q35 | p11 ends with the second prompt; p12 begins “答题思路” | Moved the printed answer approach to p12. |
| Politics 2022 questions p13, Q36 | p12 ends “归结起来就”; p13 begins “是一个主题” | Split the material across p12–13. |
| Politics 2022 questions p14, Q37 | p13 ends “到条”; p14 begins “件更为艰苦” | Split the material across p13–14. |
| Politics 2022 questions p15, Q37 | p14 ends “新时代”; p15 begins “青年应该以认真” | Moved the answer approach continuation before Q38 on p15. |
| Politics 2022 questions p16, Q38 | p15 ends “建设和谐”; p16 begins “世界到推动构建” | Split the material across p15–16. |
| Politics 2023 answers p14, Q35 | p13 ends “思想以”; p14 begins “及什么是以人民为中心的发展思想” | Moved the continuation and following Q35 explanation blocks to p14. |

The rendered PDF of CS408 2015 complete p13 is empty, so it correctly has no source blocks. Politics 2019 answers p7 is a QR-code/promotional page with no exam answer; omitting it from structured answer blocks is intentional. These are two distinct non-content exceptions, not missing questions.

This table states exactly which flagged PDF pages were viewed **in this review**. The Politics answer pages and CS408 answer pages listed in the last column were viewed in the separate QA reports linked above. Those reviews checked page ownership and visible content; they do not imply a character-by-character transcription proof.

| Document | Flagged pages | Visually checked here | Not visually checked here |
| --- | ---: | --- | --- |
| `cs408:2025-answers` | 1–5 | 1 | 2–5 |
| `cs408:2024-answers` | 1–6 | 2 | 1, 3–6 |
| `cs408:2021-answers` | 1–11 | 2 | 1, 3–11 |
| `cs408:2019-answers` | 1–12 | 2 | 1, 3–12 |
| `cs408:2015-complete` | 13 | 13 | — |
| `politics:2023-answers` | 1–17 | 13–14 | 1–12, 15–17 |
| `politics:2022-questions` | 2–16 | 2–16 | — |
| `politics:2022-answers` | 1–11 | 1 | 2–11 |
| `politics:2019-answers` | 7 | 7 | — |
| `politics:2018-answers` | 1–5 | 1 | 2–5 |
| `politics:2017-answers` | 1–5 | — | 1–5 |
| `politics:2016-answers` | 1–5 | — | 1–5 |
| `politics:2015-answers` | 1–5 | — | 1–5 |
| `politics:2014-answers` | 1–5 | — | 1–5 |
| `politics:2013-answers` | 1–5 | — | 1–5 |
| `politics:2012-answers` | 1–6 | — | 1–6 |
| `politics:2011-answers` | 1–6 | — | 1–6 |
| `politics:2010-answers` | 1–5 | 1 | 2–5 |

The representative rendered pages confirm why text extraction failed: Politics 2022/2023 answer pages and CS408 2019 answer pages contain raster page images; CS408 2021/2024/2025 pages use image fragments for text, code, or diagrams; Politics 2010 and 2018 answer pages visibly contain text rendered by a font without a usable Unicode map. The Politics 2022 questions PDF p1–16 was visually checked for question, choice, page, and visible paragraph boundaries. For Q34–38, separate material labels, source attributions, material paragraphs, prompts, and answer-approach paragraphs now have explicit paragraph metadata. All ten split source groups reconstruct their previous text byte for byte; the four decimal fixes in the separate Politics 2023 question transcription are noted below. The presence of structured blocks on the remaining pages is an automated coverage check, **not** proof that every character, formula, image, or paragraph was accurately transcribed.

Separately, visual inspection of Politics 2023 questions p11 confirmed that Q38 material 2 prints `34.6`, `2.8%`, `9.7%`, and `2.9%`. The source text layer had inserted spaces after the decimal points; those four numbers were corrected in the Politics transcription and regenerated reflow. The original PDF remains untouched.
