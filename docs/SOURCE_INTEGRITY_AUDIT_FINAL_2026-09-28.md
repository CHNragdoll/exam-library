# 原始 PDF 与结构化题库核查

自动核查仅提供复核线索；PDF 抽取顺序、公式和图片可能造成误报。未报告的文字也不能证明无错字或漏段。

复现：`./.venv/bin/python scripts/audit_source_integrity.py --json docs/source-integrity-audit-final-2026-09-28.json --markdown docs/SOURCE_INTEGRITY_AUDIT_FINAL_2026-09-28.md`。脚本只读取目录、结构化 JSON 和原始 PDF；输出仅为两份报告。

逐份校验来源 SHA-256 与 PDF 页数/页段。段落检测搜索整份结构化卷，避开跨页合并误报；数学卷只比较足够长的中文文字，公式及图像须人工视觉核对。可提取文字不足的 PDF 页单独列出。题号、选项、小问、答案引用及重复标点均是候选，不作自动修订。

目录文档：335；实际读取的唯一 PDF：271；线索：1900。

## 分类统计

- `duplicate_question_number`：241
- `incomplete_choices`：30
- `missing_question_number`：1
- `partial_question`：1321
- `possible_missing_paragraph`：165
- `source_page_text_unextractable`：135
- `subquestion_mismatch`：1
- `suspect_typo`：4
- `unassigned_numbered_block`：2

## 高优先级线索

- `cet6:2018-06-02` `incomplete_choices` 页 8；题 q-53-2；option labels: ['B', 'C', 'D', 'E']
- `cs408:2015-complete` `incomplete_choices` 页 1；题 q-1-1；option labels: ['A', 'B', 'B', 'D']
- `cet6:2015-12-01` `incomplete_choices` 页 7；题 q-56-1；option labels: ['A', 'B', 'C']
- `cet6:2014-12-01` `incomplete_choices` 页 7；题 q-61-1；option labels: ['A', 'C', 'C', 'D']
- `cet4:2014-12-01` `incomplete_choices` 页 7；题 q-61-1；option labels: ['A', 'B', 'C']
- `politics:2005-questions` `incomplete_choices` 页 1；题 q-3-1；option labels: ['A', 'B', 'C', 'C']
- `math3:1996-questions` `incomplete_choices` 页 58；题 q-3-5；option labels: []
- `math3:1996-questions` `incomplete_choices` 页 58；题 q-4-5；option labels: []
- `math3:1995-questions` `incomplete_choices` 页 53；题 q-1-4；option labels: []
- `math3:1995-questions` `incomplete_choices` 页 53；题 q-2-4；option labels: []
- `math3:1995-questions` `incomplete_choices` 页 54；题 q-5-5；option labels: []
- `math3:1994-questions` `incomplete_choices` 页 49；题 q-1-4；option labels: []
- `math3:1994-questions` `incomplete_choices` 页 50；题 q-5-5；option labels: []
- `math3:1993-questions` `incomplete_choices` 页 45；题 q-1-4；option labels: []
- `math3:1993-questions` `incomplete_choices` 页 45；题 q-2-4；option labels: []
- `math3:1992-questions` `incomplete_choices` 页 41；题 q-1-4；option labels: []
- `math3:1992-questions` `incomplete_choices` 页 41；题 q-5-5；option labels: []
- `math3:1991-questions` `incomplete_choices` 页 35；题 q-1-4；option labels: []
- `math3:1991-questions` `incomplete_choices` 页 36；题 q-5-5；option labels: []
- `math3:1990-questions` `incomplete_choices` 页 31；题 q-1-5；option labels: []
- `math3:1990-questions` `incomplete_choices` 页 31；题 q-2-5；option labels: []
- `math3:1990-questions` `incomplete_choices` 页 31；题 q-3-5；option labels: []
- `math3:1989-questions` `incomplete_choices` 页 27；题 q-1-5；option labels: []
- `math3:1989-questions` `incomplete_choices` 页 27；题 q-2-5；option labels: []
- `math3:1989-questions` `incomplete_choices` 页 27；题 q-3-5；option labels: []
- `math3:1989-questions` `incomplete_choices` 页 28；题 q-5-5；option labels: []
- `math3:1987-questions` `incomplete_choices` 页 20；题 q-1-5；option labels: []
- `math3:1987-questions` `incomplete_choices` 页 20；题 q-2-5；option labels: []
- `math3:1987-questions` `incomplete_choices` 页 20；题 q-3-5；option labels: []
- `math3:1987-questions` `incomplete_choices` 页 20；题 q-4-6；option labels: []

逐条复核请使用同名 JSON 中的 `documentId`、`sourcePdf`、`pages`、`blockIds` 和 `questionIds`。
