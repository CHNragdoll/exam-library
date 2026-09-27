# 转换验证

范围：206 套公开英语真题，2020 个原卷页面；原 PDF、旧 SVG 归档及 Anki 数据均未改动。本轮为本地试用版，没有推送、发布或打标签。

## 已验证

- 206 份 HTM、LaTeX 和 JSON 一一对应；5 类目录齐全。
- 2020 页结构重组均通过已提取正文字母数字的字符守恒检查。该检查不证明原 OCR 的准确性，也不代替逐题校对。
- 1117 个相对资源及下载链接存在；每份 HTM 的 SHA256 与 manifest 一致。
- 206 份 LaTeX 均通过 XeLaTeX 编译；无缺失字形、无 overfull box 警告。
- 5 个源文件回归检查通过：长字母段落续行、压缩文字的词间空格、A-D 选项、2026 英一合并图表、英二图表标签。
- 独立审查识别并处理了字母段落续行错拆、OCR 字体污染及图表标签裁切等问题。

## 明确限制

29 份试卷的 119 个原卷页面存在不可靠文字层，其 219 个区域保留为原图 PNG。对应页面有提示。这些区域可以随容器缩放，但尚未转成可编辑 LaTeX 文字，不能重新断行或准确复制；其余正文使用 HTML 文本重排。具体清单见 `limitations.json`。

65 处图表、漫画或复杂框表保留原卷插图；7 处简单排序图改为原生矢量框线与字形路径，可由结构化 tokens 重新生成。其他复杂图表不是手写 TikZ 或可编辑表格。

浏览器交互与窄屏实机显示未验证。以下截图来自 LaTeX 编译结果或原卷局部素材，不能当作 HTML 浏览器验收截图。

## 正常正文编译结果

![四级正文与选项](assets/verification/cet4-latex.png)

## 图表与标签完整性

![2026 英一饼图与柱图](assets/verification/kaoyan-2026-charts.png)

## 不可靠文字层的保真处理

![中文原图区与正常文字共同排版](assets/verification/encoding-fallback.png)

## 本轮布局修正（2026-09-26）

- 2000 年写作要求 `3) Suggest counter-measures.` 从图片裁切范围移回题干，与 1)、2) 一致。
- 独立图题在 HTM 和 LaTeX 中居中；识别规则排除 Directions、分节标题和答题卡提示。
- 7 处简单排序图使用原生矢量 SVG；LaTeX 使用矢量 PDF，保留全部给定字母及空格题号。
- 1279 组短选项使用题号与 A、B、C、D 同行布局；HTM 窄屏下仅该行横向滚动。
- 原数据与旧 SVG 归档不变。修改前脚本备份在 `work/before-layout-fixes/`。
- `test_layout.py` 验证题干恢复、图题、排序顺序、短选项字符守恒及图题误判回归。

以下为 LaTeX 编译截图与矢量素材检查，不是浏览器截图：

![2000 年题干及居中图题](assets/verification/layout-2000-stem.png)

![排序图矢量导出预览](assets/verification/layout-ordering-vector.png)

![短选项同行的 LaTeX 编译效果](assets/verification/layout-short-choices.png)


## 连续阅读修正（2026-09-27）

模式：change / bug / R2，交付：local-trial。识别规则影响正文段落，保留原始数据及可恢复的脚本、下载包备份；无外部发布。

- 移除 HTM 页码标签、分页横线和 LaTeX 原页结束文字；原页元数据保留。
- 修复说明文字 `choosing A, B, C or D. Mark...` 中 D 被当成选项的问题；修复行距较大的字母长段落被拆开的情况。
- 保守合并源页边界上明确未结束、下一页以小写继续的正文；标题、题目和不可靠图像文字区域不参与合并。
- 排序图恢复原卷矢量图形及填空位置，不使用上一轮重绘的大方框；随可用宽度缩放。
- HTM 正文和长选项使用两端对齐，末行保持起始对齐；短选项仍同行，图题居中。
- 备份位于 `work/before-continuous-layout-2026-09-27/`。恢复其中脚本后重新 build/verify 可重现修改前输出；ZIP 另有完整备份。
- `test_continuous.py` 先复现断行失败，再检查本轮修复；`verify.py` 新增全部 HTM 可见正文与结构化数据的字母数字守恒、无页码标记断言。

本节覆盖上一节有关重绘排序图和原页定位显示的说明。旧截图为历史证据；本轮截图仅来自最终 LaTeX 编译或原卷矢量素材，不作为浏览器验收。


本轮最终检查：206 份 LaTeX 编译通过，无缺字或 overfull box；2020 原页字符守恒、1117 个资源链接及 HTM 可见正文守恒通过。235 处跨页续句已合并，每段并入文字都有独立的 `data-source-page` 标记。独立审查发现的来源页标记偏移已修复并加入验证。浏览器实机布局本轮未验证。

![2014 年连续说明文字及两端对齐的 LaTeX 编译结果](assets/verification/continuous-2014-directions.png)

![恢复原卷框线与填空位置的排序图](assets/verification/continuous-2014-original-flow.png)


## 填空数字与选项词距修正（2026-09-27）

本轮为 CSS 局部修复（change / bug / R1 / local-trial）。正文继续两端对齐；选项改为自然左对齐，避免窄列拉大词距。填空数字显式设置 `text-align-last:center`，覆盖正文继承的末行起始对齐。共用样式覆盖全部 206 套，HTM 正文和 LaTeX 未修改，原编译/字符守恒结果沿用；本轮仅核查 CSS 规则、全部试卷引用及 ZIP 中样式一致性，未作浏览器视觉验证。样式备份位于 `work/before-blank-alignment-2026-09-27/style.css`。
