# 考研真题大全

本地网页阅读历年真题，提供 **SVG 原版、LaTeX 重排、同窗并排对比**。运行下方服务后，从 [http://localhost:8765/](http://localhost:8765/) 进入题库；无需逐个打开 `.htm` 文件。

目前收录 335 份资料、670 个阅读版本：考研英语 44、数学三 66、408 27、政治 36、六级 83、四级 71、专四 4、专八 4。题目与答案按实际资料分别列出，并非所有年份都有独立答案卷。

## 使用

在项目根目录运行本地网页入口，无需手动打开 HTML 文件，也无需安装第三方服务依赖：

```sh
python3 scripts/serve_exam_library.py
```

然后打开 [http://localhost:8765/](http://localhost:8765/)；需要其他端口可加 `--port 8766`。服务仅监听本机 `127.0.0.1`，按 Ctrl+C 停止。SVG 原版、LaTeX 重排、结构化审阅页均由同一服务提供；HTML 页面刷新时不使用缓存。

英语整卷练习从题库目录进入，也可打开 [整卷练习页](http://localhost:8765/exam-library/practice/full-paper.htm)。它按原卷顺序展示题文、选项和已核实的参考答案，提供章节目录、中文译文开关和双栏沉浸模式。旧逐题练习入口已隐藏。本地服务首次启动会从结构化试卷自动生成 SQLite 题库；选项默认保留原顺序，也可按种子乱序，答案展开后按固定选项 ID 标记正确项。数据结构、只读 API、重建及恢复方式见 [SQLite 题库说明](docs/QUESTION_DATABASE.md)。

- 在总目录按科目、年份、题卷类型搜索筛选。
- SVG 保持原卷版式，LaTeX 重排随窗口排版；阅读器支持目录、字号/宽度、缩放和专注阅读。
- “并排对比”同时打开同一文档的两版，可分别滚动；窄屏上下排列。
- 本地设置和最近阅读由浏览器保存在 `localhost` 站点下。实际浏览器显示与程序结构核验分开记录。

请保留 `data/sources` 目录关系。网页所需素材已随库保存；原始下载 PDF、工作缓存、历史备份、重复 ZIP 不作为阅读依赖。

## 开发

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
npm ci
.venv/bin/python scripts/verify_library.py
npm test
```

重建汇总目录和阅读工具接入：

```sh
.venv/bin/python data/sources/exam-library/build.py
```

试卷内容的完整重建另需对应来源 PDF、经核验的答案证据、本机保留的翻译出版快照、子目录的公式构建依赖，部分验证需要 XeLaTeX。这些上游资料不随源码归档全部发布；缺失时来源构建器会拒绝生成，不能把未知答案猜成已核实答案。已提交的结构化 JSON/JSONL 是离线阅读及重建本地 SQLite 的发行输入，普通界面修改和离线阅读不需要重新获取 PDF。

主要目录：

- `data/sources/exam-library`：汇总目录、共享阅读界面、构建与核对记录。
- `data/sources/*-latex-*`、`english-exams-reflow-latex`：结构化转录、LaTeX 和重排网页。
- `data/sources/*-original`、`math3-*-htm`、`english-exams-web-*`：原卷矢量阅读版。
- `data/sources/layout-tools`：原卷转换、图形和文字处理工具。

## 协作

按项目 [`AGENTS.md`](AGENTS.md)：子代理统一 GPT-6 Sol / xhigh；普通变更验证后直接提交推送 main，大改才走 PR。提交不自动创建 Release。原始输入、备份和无关用户文件不删除。

## 内容与验证

题文、图像、原稿答案及其权利归原权利人；仓库不对第三方内容重新授权。原稿中的略解、缺页或编码异常按资料说明保留，排版转换不构成答案正确性保证。

本次版本说明见 [`CHANGELOG.md`](CHANGELOG.md)，变更与迁移背景见 [`docs/CHANGE_2026-09-27.md`](docs/CHANGE_2026-09-27.md)。历史核验报告只说明其当时版本；请运行当前检查。DOM 检查不等同于实机显示验收。

历史维护工具说明：`layout-tools` 内最早的整批恢复流程依赖本机 `kaoyan-web-2026-09-26` 历史副本；该重复副本不上传。当前总目录构建、阅读和验证使用 `english-exams-web-2026-09-26`。旧的逐批保全脚本也可能需要被排除的本机 `work/before-*` 备份，不应将缺少旧备份误报为当前内容损坏。

公式构建的锁文件保留在 `data/sources/math3-latex-2009-2019/work/render`，其他数学、408、政治目录通过相对符号链接复用。在其目录执行 `npm ci` 后可重建公式；仍需各自来源输入和子目录说明中的依赖。
