# 原 PDF 核查疑点归并

输入自动报告共 1900 条提示；本报告归并段落、选项和小问疑点 195 条。
自动读取覆盖 335 份目录文档、271 份唯一原始 PDF、2832 个唯一 PDF 页。先前人工视觉抽核记录含 17 页 PDF 与 3 个裁切图；没有逐页人工审阅全部文档。
这是输入审计 JSON 所对应的快照；每次重建后须重跑原审计和本脚本。

## 根因归并

处置状态：`no_content_loss_observed` 189；`unresolved_original_printing` 6

- `image_fallback_visually_present`：115
- `printed_cross_reference_to_other_paper`：24
- `printed_original_duplicate_label`：1
- `printed_original_option_anomaly`：5
- `text_present_ocr_or_formula_variation`：19
- `text_present_reordered`：26
- `word_bank_repaired_from_pdf`：5

图片回退行已有原图，但文字字段为空不能据此认定内容缺失或完整；`image_fallback_unreviewed` 仍待逐条人工核对。可读文字行的连续片段比对可能受双栏顺序、OCR 和公式影响。

选项异常须区分原卷印刷与解析错误。原卷印作重复标签、缺印标签或引用另一试卷时，不补造标准四项，也不据不完整选项自动判分。

## 408：优先修复清单

| 卷与题 | 原 PDF 页 | 源块 | 核实结论 | 建议归属 |
|---|---:|---|---|---|
| `cs408:2015-complete` `q-1-1` | 1 | `b-1-4,b-1-5,b-1-6` | 原 PDF 第1页与源块 b-1-6 均为 A/B/B/D；保留印刷标签，人工审查选项表示，不得推造 C | 408 结构化选项表示 |

## 已确认的答案漏段

| 卷与题 | 原 PDF 页 | 邻接源块 | 缺失内容 | 建议归属 |
|---|---:|---|---|---|

## 跨科已视觉确认的选项漏拆

| 卷与题 | 原 PDF 页 | 源块 | 建议归属 |
|---|---:|---|---|

## 其他类别交接

- 政治：`printed_original_option_anomaly` 1
- 数学三：`printed_cross_reference_to_other_paper` 24
- 四级：`image_fallback_visually_present` 28；`printed_original_option_anomaly` 1；`text_present_reordered` 11；`word_bank_repaired_from_pdf` 1
- 六级：`image_fallback_visually_present` 64；`printed_original_option_anomaly` 3；`text_present_reordered` 14；`word_bank_repaired_from_pdf` 4
- 考研英语：
- 专四：`image_fallback_visually_present` 9
- 专八：`image_fallback_visually_present` 14；`text_present_reordered` 1

逐条归属、问题 ID、PDF 路径/页码和源块见同名 JSON。`image_fallback_unreviewed` 表示已有图像回退但未逐条视觉确认，不应当作已验证无缺字。
