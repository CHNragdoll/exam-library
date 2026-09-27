# 考研数学三 LaTeX / HTM

下载包包含本轮新增的 1987–2008 共 22 年，解压后打开 `index.htm` 阅读；完整 33 年请使用项目总目录。正文为 HTML，公式从 LaTeX 生成独立 SVG；无需联网或安装 MathJax。

`tex/` 为 44 份可编辑 LaTeX 文档（建议 XeLaTeX + ctex）。`source/` 为逐页结构化转录，包括公式源。`assets/figures/` 为原卷函数曲线图等独立插图，HTML 使用矢量 SVG，TeX 使用同源矢量 PDF；PNG 仅用于图形核对。公式均为 TeX。

网页可显示全部 LaTeX 片段，点击公式可复制；复制按钮的浏览器交互尚未实机验证，始终可以下载 `.tex` 源文件。44 份完整 TeX 文档已通过 XeLaTeX 编译，无溢出或缺字警告；全部公式经过 MathJax 编译检查。

原卷 126 页、1987–2008 年；保留早期 IV/V 卷及原稿参考答案。答案只转录原稿，不补写“证明略”等缺失内容。请保留全部目录。

## 重建

使用已安装 PyMuPDF、lxml 的 Python；执行 `npm ci --prefix work/render` 安装锁定的公式构建依赖，依次执行 `python build.py`、`python verify.py`、`python build.py`；最后一步将成功验证记录写入 manifest、说明文件和离线包。MathJax 文档：https://docs.mathjax.org/en/v3.2/server/direct.html

原 PDF 与上一版整页 SVG 均未修改。本目录最初以本地试用交付；当前仓库交付状态以根目录 README 为准。转录备注见 manifest.json。
