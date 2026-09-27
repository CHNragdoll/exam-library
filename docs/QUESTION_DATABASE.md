# SQLite 题库与刷题接口

这次变更为 `feature`，数据迁移风险按 `R2` 处理：结构化抽取若把选项或答案归错题，会影响刷题判分。原始 PDF、SVG、重排页和现有 JSON/JSONL 继续保留；它们是重建输入，SQLite 是本地网页和后续客户端的可再生读取库。数据库只存题目与资料内容，不存用户作答记录。

## 使用与来源

```sh
python3 scripts/serve_exam_library.py
```

打开 `http://localhost:8765/exam-library/practice/index.htm`。启动时如果数据库缺失或结构化数据更新，服务会自动建库。也可手动执行：

```sh
python3 scripts/build_question_database.py
```

生成文件是仓库内 `data/question-bank.sqlite3`，位于静态公开目录 `data/sources` **之外**，不会作为网页静态文件下载。它是本地生成物，不纳入 Git；`data/question-bank.sqlite3.bak` 保存上一次完整版本。建库先核对 335 份源卷的审计、JSONL 与每卷 JSON，写入同目录临时库，检查外键和完整性后才原子替换。失败时现有库保持不变。要恢复上一版本，先停服务，再将 `.bak` 复制回 `.sqlite3`；或从版本控制内的结构化 JSON 重新运行建库命令。完整重建命令为 `python3 data/sources/exam-library/build.py`，顺序是重建结构化文件、SQLite 和目录页。

## 关系模型

版本号在 `meta.schema_version`，当前为 `question-bank.sqlite.v2`。`papers` 保存试卷 ID、科目/年份、原版与重排来源路径；`questions` 用 `paperId:q-N-occurrence` 作为稳定 ID，另存卷内 `ordinal`；`source_blocks` 保存原文字、HTML、公式 TeX、图像引用和页/块位置，关联表 `question_source_blocks`、`context_source_blocks` 保留题目及共用阅读材料的顺序。`answers` 分开保存答案值、解答过程、解析、点评、考点和答案卷出处。选项保存原标记 `source_label`、默认位置 `default_position` 和卷面提取位置 `source_position`；通常使用 `questionId:A` 等固定 ID，原卷重复标号时加上位置后缀以避免覆盖，并禁止该题自动判分。

`options.is_correct` 是三态：`1` 正确、`0` 错误、`NULL` 未核实。只有答案来源状态为 `explicit`，答案值能明确解析为已有选项，而且与单选/多选题型一致时才写入 `1/0`。`missing`、`ambiguous`、仅有解析没有选项答案、或答案与选项不匹配的题，所有选项均保持 `NULL`；原答案文字仍在 `answers.value`。卷面默认 A–D（少数早年政治卷为 A–E）顺序和原标记永久保存，乱序只在读取时生成显示顺序，正确性始终用固定选项 ID 关联，不能以乱序后的展示字母判分。

这套结构允许后续从同一数据库生成小程序、Anki、PDF 或乱序卷；输出端应读取固定 ID、原始位置、来源及三态正确标记，不应把未知当作错误答案。现有 JSON/JSONL 仍作为可移植的导出和重建源；未来若增加人工核准答案，应设计独立版本化覆写来源，不能直接改生成库后被下次重建覆盖。

## 本地只读 API

服务只监听 `127.0.0.1`，API 不提供写入或作答记录接口。

| 路径 | 内容 |
| --- | --- |
| `GET /api/v1/meta` | 模式版本、卷/题/选项数量 |
| `GET /api/v1/papers?category=cs408` | 有题目的试卷及题量 |
| `GET /api/v1/papers/{paperId}/questions?order=default` | 原始默认顺序的题目与选项，不含正确标记 |
| `GET /api/v1/papers/{paperId}/questions?order=shuffle&seed=demo` | 可重现的显示乱序，选项 ID 不变 |
| `GET /api/v1/questions/{questionId}` | 单题内容；同样支持 `order` 与 `seed` |
| `GET /api/v1/questions/{questionId}/answer` | 展开时取得原答案、解析及 `correctOptionIds` |

题目 ID 应经 URL 编码。API 返回的 `displayLabel` 是本次展示字母，`label` 是原卷规范字母，`sourceLabel` 是原卷原标记；答案端的 `correctOptionIds` 仅在可信对应时提供。数据库建库失败时 API 返回 503，找不到题目返回 404。

验证：`python3 -m unittest scripts.test_question_database scripts.test_question_database_api scripts.test_serve_exam_library`、`python3 scripts/verify_structured_exams.py`，以及 `npm test`。结构和 HTTP 检查不能替代实际浏览器的题文、公式、图像及答案显示审阅。
