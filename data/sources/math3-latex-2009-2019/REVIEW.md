# LaTeX 转录与离线 HTM 验证

范围：用户 PDF 2009–2019 数学三真题及参考答案，共 55 页；本地新目录，不修改原文件、不发布。

- 11 年逐页视觉转录，253 道题及原参考答案，公式保存为可编辑 LaTeX。
- MathJax 3.2.2 从 TeX 生成 1,105 个不重复 SVG 公式，无公式解析错误；HTML 同时携带必需的 MathJax 样式，概率表分隔线已检查。
- 22 份完整 TeX 文件经 XeLaTeX 实际编译，无错误、无 overfull 或缺字警告。详见 assets/verification/latex-compilation.json，包含对应 TeX 文件 SHA-256。
- 独立复核覆盖 2019 全部题目及答案，以及 2012–2018 各年复杂矩阵、概率、分段函数答案抽样。转录人员逐页对照负责年份。
- 修复导数 prime 必须使用上标、数列花括号转义、中文句号缺字、长公式换行。
- 实际检查四处图形素材，修复 2016 缺失轴标与 2009 原函数及选项裁切坐标。曲线图保留原卷矢量，公式没有使用原卷截图替代。
- 实际查看 MathJax 公式矢量样张及 XeLaTeX 输出样张，矩阵、根式、积分、概率表和导数可读。
- HTML 本地链接与 SVG XML 均已验证；ZIP CRC 校验通过。

限制：浏览器交互（复制按钮、窗口响应布局）未实机验证；参考答案保留源稿“证明略”等省略内容。转录和数学答案正确性不是形式化证明，原稿未改。

回退：保留原 PDF 和上一版 math3-2009-2019-htm；本次为独立输出目录。

![由 LaTeX 生成的实际 SVG 公式样张](assets/verification/formula-samples.png)

![LaTeX 源文件编译样张](assets/verification/tex-2019-questions.png)

## 全部公式采用 display style

按用户反馈，全部 11 年真题与参考答案的公式采用 `\displaystyle`，分式使用 `\dfrac`，并显式保持分子、分母内的求和等运算符为舒展样式。仅修改显示方式，原始逐页转录 JSON 未改；下载的 `.tex`、网页显示及复制源码同步。

本次为本地修复（bug / R1）。备份在 `work/before-displaystyle/`，含原构建脚本、样本网页、公式结果及完整压缩包。

1,105 个不重复公式解析通过；22 份 TeX 文件重新编译，无错误、缺字或溢出警告。实际矢量样张确认分子中的求和展开、积分变大、极限下标置于下方；浏览器交互仍未验证。

![舒展样式修复前后对照](assets/verification/displaystyle-comparison.png)
