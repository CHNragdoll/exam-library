# 考研政治 SVG 原版

[统一入口](../exam-library/politics/index.htm)：2003–2023 真题 21 份、2009–2023 答案解析 15 份。原 PDF 共 292 页，阅读版呈现 291 页；2019 答案第 7 页是纯推广页，已从阅读版和公开 SVG 资产中移除。第 6 页真实答案残页保留。

仅在内存副本清理广告：228 处页眉/页脚公众号引流文字（含原先 186 处题目右上角广告），14 张独立二维码推广图片，另移除上述 1 页整页推广。精确区域见 `advert_regions.json` 与 `manifest.json` 的 `advert_removals`。独立二维码直接从内存中的图片对象移除，避免重新处理正文的字体流。

原始 PDF 未写入；`sources.json` 与文档 `pages` 保留原稿页数，`displayed_pages` 是清理后阅读页数，`omitted_advert_pages` 保留原稿页号。封面使用清理后的首页 SVG。

`build.py` 生成原版与封面，`verify.py` 核对原 PDF SHA-256、全部 291 个展示 SVG、正文文字保留及广告区域外像素一致。证据见 [verification.json](verification.json)，原生前后对照见 `work/ad-audit/before-after.png`。未重做浏览器实机交互测试。

脚本与此前整页推广 SVG 备份在 `../exam-library/work/before-ad-cleanup/original-politics/`；原稿 PDF 本身是全部页面的恢复来源。
