# 离线真题库界面

用户在 Mac 桌面和缩窄的阅读窗中连续查题、读题。采用白色阅读面、冷灰导航面和克制蓝色操作强调；保留原卷和自适应重排的双入口。

范围：exam-library 总目录/8个分类，以及目录实际链接的670个试卷阅读版。不修改Anki卡片、不转录题文、不改raw PDF，不恢复广告。

导航：总目录→科目→年份/题卷→阅读；读者始终能回到科目或总目录。两版均可选。首页搜索全部资料，分类页筛选本类。题卷/答案标签由文档类型确定。

共享token在ui/tokens.css。界面使用系统无衬线字体；英语文章已有衬线字体保留。正文两端对齐，短选项左对齐，数字填空居中，插图标题居中，公式display样式保留。

Catalog: semantic header/navigation/search/filters, compact covers and clear document rows, true result count/empty state, clear filter button, keyboard-operable native controls. Reader: injected ui/reader.css/js plus #exam-reader-config JSON. HTML正文不替换，原页面工具可整合但仍可访问。连续原稿页码只作为SVG页跳转，不强加给重排正文。无网络依赖。

Reader JSON contract: {title,category,categoryLabel,year,documentId,kind,mode:"svg"|"reflow",libraryHref,categoryHref,alternateHref,alternateLabel,sourceHref?}. Relative URLs are relative to current HTM. Script locates main and original header. Use a separate wrapper class .exam-reader; namespace styles .reader-* to avoid native classes. Existing formula copy/toggle logic remains. Reader shared recent data localStorage key exam-library:recent:v1 array {url,title,category,categoryLabel,mode,progress,scrollY,updatedAt}; settings key exam-library:reader:v1. Storage failures gracefully degrade. Recent resume links append #resume, reader only resumes explicitly. URL values restrict to local file/current origin.

Root integrates assets and configs persistently, backups and content SHA reconciliation. Agents must not edit neighboring owned files. Browser automation explicitly rejected file:// by URL policy even after user approval: do not retry via alternate browser/localhost or other workarounds. Static/DOM checks do not establish visual acceptance. Label visual limitations honestly.

阅读器第三档为“并排对比”：桌面同窗左 SVG、右 LaTeX，两个独立滚动阅读区；窄屏上下排列。加载同一文档的两个现有版本，嵌入模式隐藏重复外壳并禁止递归对比。切回当前单版时保留原阅读位置，不把对比外壳高度写作阅读进度。不得依赖 file:// 跨文档 DOM 权限。
