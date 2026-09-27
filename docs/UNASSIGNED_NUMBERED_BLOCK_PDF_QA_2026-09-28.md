# `unassigned_numbered_block` 原卷核查（2026-09-28）

核查基线：`docs/source-integrity-audit-final-2026-09-28.json` 中的 28 条同名发现。逐条对照 PDF 实际页面、`pdftotext -layout` 结果、原版 HTM 的可选文字层、重排源块和当时的结构化题目清单。本报告只记录核查结论，不修改源数据或生成物。页码均为 PDF 物理页（从 1 起）。

## 结论

- 2015 年 6 月 CET-6 第 3 套：23 条发现覆盖原卷听力题 **2–25**（20、21 同在一个源块）；加上未被该规则报出的第 **1** 题，结构化题目实际缺 **1–25 共 25 题**。PDF 第 1–3 页、原版 HTM 文字层均可读；这不是抽字失败。现有结构化 JSON 仅列 46–65。
- 2014 年 12 月 CET-6 第 1 套：3 条发现是原卷听力题 **23–25**，均为真实漏卡。PDF 第 3 页、原版 HTM 文字层均可读。现有结构化 JSON 列 1–22、46–65。
- CS408 2024、2025 答案卷各 1 条：PDF 第 1 页是 **1–40 的选择题答案表**，随后才是综合应用题 41 起的详解。两条不是题目漏卡；审计把答案表中的编号作为待核查编号是误报。原 PDF 第 1 页的文本抽取为空，但页面渲染清楚可读，PDF 含图像对象且该页未列出字体；原版 HTM 的透明文字层及“复制本页文字”也为空。不能仅凭抽字为空推断内容不存在。重排 HTM/结构化 `b-1-3` 保留了答案表。

## 逐条结果

下表中“+”后的块是同题余下选项；“真实漏卡”表示结构化 JSON 无对应题号，而 PDF 与原版 HTM 确有题目。英语题通常在一个普通内容块中放 A/C 选项，紧随的选项块放 B/D；应按印刷的 A–D 归并，不能按块的线性文字顺序误配。PDF 的这些页已渲染目检，且 `pdftotext -layout` 能找到相同题号和选项。原版 HTM 每页有透明 SVG `text-overlay`、`sr-only` 和可复制的页文字。

| 审计 documentId | PDF 页 | 审计源块及相关块 | PDF/原 HTM 文字证据（题号与首选项） | 结论与建议 |
|---|---:|---|---|---|
| `cs408:2025-answers` | 1 | `b-1-3` | “一、单项选择题”下表格 `1. B … 40. A`；后接 `41.【答案要点】` | 答案表，非漏题；审计规则应排除答案卷整表，保留原表供关联 1–40 题的答案。 |
| `cs408:2024-answers` | 1 | `b-1-3` | “一、单项选择题”下表格 `1. D … 40. D`；后接 `41.【答案要点】` | 答案表，非漏题；同上。 |
| `cet6:2015-06-03` | 1 | `b-1-13` + `b-1-14` | `2、A) Work out a plan to tighten his budget.` | 真实漏卡；恢复听力选择题 2。 |
| 同上 | 1 | `b-1-15` + `b-1-16` | `3、A) A financial burden.` | 真实漏卡；恢复题 3。 |
| 同上 | 1 | `b-1-17` + `b-1-18` | `4、A) The errors will be corrected soon.` | 真实漏卡；恢复题 4。 |
| 同上 | 1 | `b-1-19` + `b-1-20` | `5、A) He needs help to retrieve his files.` | 真实漏卡；恢复题 5。 |
| 同上 | 1 | `b-1-21` + `b-1-22` | `6、A) They might have to change their plan.` | 真实漏卡；恢复题 6。 |
| 同上 | 1 | `b-1-23` + `b-1-24` | `7、A) They have to wait a month to apply for a student loan.` | 真实漏卡；恢复题 7。 |
| 同上 | 1 | `b-1-25` + `b-1-26` | `8、A) New laws are yet to be made to reduce pollutant release.` | 真实漏卡；恢复题 8。 |
| 同上 | 1 | `b-1-28` + `b-1-29` | `9、A) Enormous size of its stores.` | 真实漏卡；恢复题 9。 |
| 同上 | 1 | `b-1-30` + `b-1-31` | `10、A) An ancient building.` | 真实漏卡；恢复题 10。 |
| 同上 | 2 | `b-2-1` + `b-2-2` | `11、A) Its power bill reaches £9 million a year.` | 真实漏卡；恢复题 11。 |
| 同上 | 2 | `b-2-3` | `12、A) 11 500. B) 30 000. C) 250 000. D) 300 000.` | 真实漏卡；四个选项同块，恢复题 12。 |
| 同上 | 2 | `b-2-5` + `b-2-6` | `13、A) Transferring to another department.` | 真实漏卡；恢复题 13。 |
| 同上 | 2 | `b-2-7` + `b-2-8` | `14、A) She has finally got a promotion and a pay raise.` | 真实漏卡；恢复题 14。 |
| 同上 | 2 | `b-2-9` + `b-2-10` | `15、A) He and Andrea have proved to be a perfect match.` | 真实漏卡；恢复题 15。 |
| 同上 | 2 | `b-2-18` + `b-2-19` | `16、A) They are motorcycles designated for water sports.` | 真实漏卡；恢复题 16。 |
| 同上 | 2 | `b-2-20` + `b-2-21` | `17、A) Water scooter operators’ lack of experience.` | 真实漏卡；恢复题 17。 |
| 同上 | 2 | `b-2-22` + `b-2-23` | `18、A) They scare whales to death.` | 真实漏卡；恢复题 18。 |
| 同上 | 2 | `b-2-24` + `b-2-25` | `19、A) Expand operating areas.` | 真实漏卡；恢复题 19。 |
| 同上 | 2 | `b-2-28` + `b-2-29` | 同一块先列 `20、A) They are stable. … D) They are changing.`，接着列 `21、A) They are fully occupied with their own business.`；后一块续 21 的 B–D | **一条发现对应两道真实漏卡**；按题号在同块切开，恢复题 20、21。 |
| 同上 | 2 | `b-2-30` + `b-2-31` | `22、A) Count on each other for help.` | 真实漏卡；恢复题 22。 |
| 同上 | 2 | `b-2-34` + `b-2-35` | `23、A) It may produce an increasing number of idle youngsters.` | 真实漏卡；恢复题 23。 |
| 同上 | 3 | `b-3-1` + `b-3-2` | `24、A) It is less serious in cities than in rural areas.` | 真实漏卡；恢复题 24。 |
| 同上 | 3 | `b-3-3` + `b-3-4` | `25、A) Allowing them to choose their favorite teachers.` | 真实漏卡；恢复题 25。 |
| `cet6:2014-12-01` | 3 | `b-3-4` + `b-3-5` | `Questions 23 to 25 …` 后，`23、A) It was named after its location.` | 真实漏卡；恢复题 23。 |
| 同上 | 3 | `b-3-6` + `b-3-7` | `24、A) Animal painting was part of the spiritual life of the time.` | 真实漏卡；恢复题 24。 |
| 同上 | 3 | `b-3-8` + `b-3-9` | `25、A) They know little about why the paintings were created.` | 真实漏卡；恢复题 25。 |

**审计未列出的同类缺口：** `cet6:2015-06-03` PDF 第 1 页题 `1、A) The man might be able to play in the World Cup.` 位于 `b-1-11`（前面还混有 `centre.` 及答题说明），B–D 在 `b-1-12`。原版 HTM 文字层可选、PDF 可抽取；结构化 JSON 无第 1 题。修复时应一并纳入，不能把前置说明当作题干或选项。

## 成因与修复边界

在核查时的重排源中，上述漏题首块均是普通内容块（`role=content`），随后才是 `role=choices`；结构化构建器 `scripts/build_structured_exams.py` 的普通内容块提升条件要求已有当前题，且当前编号正好是上一题加一。2015 年第 1 题被拼在 `b-1-11` 的说明末尾，既没有题块角色，也不从题号开头；后续 2–25 在尚无当前题时无法触发连续提升。2014 年第 23 题前的 `b-3-2` 是 “Passage Three” 分节，它关闭了第 22 题，23–25 因而也没有可连续提升的当前题。观察到的直接结果是这些块均被标为 `source_only`，没有 `questionId`。这是当前代码及源块形状下的机制解释；修复应由英语提取/题目识别流程处理，而非从 PDF 抽字为空推导规则。

建议英语修复覆盖：2015 年听力 1–25、2014 年听力 23–25；保持原说明/分节不被吞并；拆开 2015 年同块 20/21；按印刷 A–D 归并分散在两块里的选项。用原 PDF 页码、原 HTM 可选文字和结构化 `sourceBlocks/sourcePages` 复核每题。CS408 两条应在审计分型中识别为答案表，若要展示 1–40 答案，可关联到对应真题而不新增 40 张“题目”卡。

## 对照文件

- 英语原 PDF：`data/sources/english-exams-web-2026-09-26/.firecrawl/cet6/2015-06-03.pdf`（第 1–3 页）、`…/2014-12-01.pdf`（第 3 页）。
- 英语原版可选文字 HTM：`data/sources/english-exams-web-2026-09-26/cet6/papers/2015-06-03.htm`、`…/2014-12-01.htm`。
- CS408 原 PDF：`/Users/apple/Downloads/408-exam-paper/answers/2024-answer.pdf`、`…/2025-answer.pdf`（均第 1 页）；原版 HTM：`data/sources/cs408-original/papers/2024-answers.htm`、`…/2025-answers.htm`。这里原版 HTM 的文字层为空，结论依据 PDF 页图及重排源的答案表。
- 结构化核对：`data/sources/exam-library/structured/papers/cet6/{2015-06-03,2014-12-01}.json`、`…/cs408/{2024-answers,2025-answers}.json`。这些是核查时的快照证据，后续构建可能更新其题数。
