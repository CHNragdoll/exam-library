# 1987–2008 数学三转录与接入核对

统一入口：[考研真题大全](../exam-library/index.htm)。2009 复用已有版本，不在新增目录中重复添加。

## 完整性与渲染

- 新增 22 年、44 份题目/答案文档，原 PDF 的 126 页恰好覆盖一次，保留早期 IV/V 卷。
- 1673 个内容块；2244 个去重公式全部由真实 TeX 编译成独立 SVG。8 个曲线/区域图使用原稿独立裁图，HTM 为 SVG，TeX 为矢量 PDF。
- 44 份完整 TeX 经 XeLaTeX 编译成功，0 编译错误、0 缺字/溢出警告；[编译记录](assets/verification/latex-compilation.json)。
- HTML 内容链接 316 项通过；总目录 1711 项通过，数学 33 年、66 卡片、每卡双版本，2009 旧路径唯一。
- 原版归档 132 页逐页 SVG 与原 PDF 字形导出一致；新增 LaTeX 不包含重复的 2009。

## 转录复核

三组按原页图转录，并交叉抽核 1993–1995、2004–2005 的矩阵、分段函数、概率、估计量等复杂题目与答案。复核期间修正了常数 c 的大小写和一处矩阵元素正负号，最终版本按原图保留。1996、1997 的原稿题答不一致及 2005 的排版歧义写入对应页说明和 manifest.notes，不擅自重写答案。

独立代码复核覆盖新增构建器、验证器及总目录改动。指出的打包证据滞后已通过 build → verify → build 处理；最终包内 manifest、验证记录、TeX 散列与本地成品核对。独立下载包的返回链接指向包内目录，并检查包内链接完整。

## 原版与 LaTeX 渲染核对图

以下为 SVG/LaTeX 原生渲染图，**不是浏览器截图**。

### 1987 年

原版首题所在页：

![1987 原版](assets/verification/original-1987-questions.png)

LaTeX 参考答案首面，核对分式、求和与矩阵：

![1987 LaTeX 答案](assets/verification/tex-1987-answers.png)

### 1996 年

![1996 原版答案](assets/verification/original-1996-answers.png)

![1996 LaTeX 答案](assets/verification/tex-1996-answers.png)

### 2008 年

![2008 原版真题](assets/verification/original-2008-questions.png)

![2008 LaTeX 真题](assets/verification/tex-2008-questions.png)

## 边界与回退

公式语法、文档编译与抽样视觉检查已完成；未进行浏览器实机交互、复制和窄屏回归，不把上述检查表述为浏览器视觉验收。原 PDF 未改变；原稿部分图形的轴标签在原 PDF 页边界已有裁切，按原样保留。

回退入口可使用 exam-library/work/before-math-expansion 中的构建器与页面备份；新增资料位于独立目录，不覆盖旧数学卷。此次为本地交付，无远端推送、标签或发布。
