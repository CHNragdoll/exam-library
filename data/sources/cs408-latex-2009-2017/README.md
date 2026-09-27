# 408 真题与解析 · LaTeX 重排版

从既有 [考研真题大全](../exam-library/index.htm) 进入 [408 栏目](../exam-library/cs408/index.htm)，每年可选择 SVG 原版或 LaTeX 重排版。

收录用户提供的 **2009–2025 年 17 份 PDF，231 个原页**。2009–2015 含原有题目及解析；新增 2016–2025 十份替换/新卷共 114 页，仅含试题。2016、2017 已改用本次提供的新 PDF。目录名保留最初范围以免破坏已有路径。

## 内容与使用

- `source/YYYY.json`：按原页核对的文字、公式、代码、表格和独立图形坐标。
- `papers/`：连续重排 HTM，正文可选择，随窗口换行，不强制沿用原 PDF 分页。
- `tex/`：17 份可编辑 LaTeX 源文件；使用 XeLaTeX 编译，保留相邻 `assets/figures` 目录关系。
- `assets/figures/`：仅树、拓扑、电路等独立图形；原稿为扫描图的部分保持原始清晰度。
- 公式已在构建时从 LaTeX 生成 SVG，网页离线阅读无需网络或 MathJax 下载。矩阵和数组使用真正 TeX，不采用照片替代；表格为 HTML/TeX 表格，代码保留换行与缩进。

网页提供公式源码显示、复制及 TeX 下载。复制和下载按钮尚未进行浏览器实机复验。

## 验证与原稿疑点

17 份 TeX 全部通过 XeLaTeX，无缺字或溢出警告；429 个去重公式通过 MathJax。已覆盖 231 个原页、92 个代码块、108 个表格、117 处独立图形。新增十年每年题号 1–47 各一次，共 470 题；403 组选项格式化前后文字核对一致。2015 年第 42 题 A 与 A² 的矩阵元素及平方关系已核对。

原 PDF 不修改。原稿中的明显印刷疑点、截断和代码疑点在对应页顶部列出，转录不据答案擅自补写缺失题干。2015 年第 13 页原本为空白页，覆盖记录保留，重排页不插入空白。

验证记录见 [verification.json](verification.json)、[本次扩充核对](REVIEW_2016_2025.md)、[首批历史核对](REVIEW.md)。结构与编译验证不等同于逐题答案正确性保证，也不替代浏览器布局验收。

## 重建

在本目录依次运行：

```sh
../../../.venv/bin/python build.py
../../../.venv/bin/python ../exam-library/build.py
../../../.venv/bin/python verify.py
../../../.venv/bin/python build.py
../../../.venv/bin/python ../exam-library/verify_cs408_extension.py
```

末次构建用编译记录刷新 manifest 的状态。输入 PDF 路径和散列在 `sources.json`；源文件改动后必须重新构建、编译和核对。
