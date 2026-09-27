"""Build the offline review page for corrected source-figure crop boxes."""
import hashlib
import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT / 'crop-review' / 'manifest.json'


def build_crop_review():
    if not MANIFEST.is_file():
        return 0
    payload = json.loads(MANIFEST.read_text())
    assert payload.get('version') == 1
    entries = payload.get('entries')
    assert isinstance(entries, list) and entries
    e = html.escape
    seen = set()
    cards = []
    for number, item in enumerate(entries, 1):
        assert item['id'] not in seen
        seen.add(item['id'])
        for key in ('pageImage', 'beforeImage', 'afterImage'):
            target = (ROOT / item[key]).resolve()
            assert target.is_relative_to(ROOT.parent) and target.is_file(), (item['id'], key)
        page_width = float(item['pageWidth'])
        page_height = float(item['pageHeight'])
        assert page_width > 0 and page_height > 0
        boxes = []
        for key, class_name, label in [('oldBBox', 'old-box', '旧裁框'), ('newBBox', 'new-box', '新裁框')]:
            x0, y0, x1, y1 = [float(value) for value in item[key]]
            assert 0 <= x0 < x1 <= page_width and 0 <= y0 < y1 <= page_height, (item['id'], key)
            style = ';'.join((
                f'left:{x0 / page_width * 100:.5f}%',
                f'top:{y0 / page_height * 100:.5f}%',
                f'width:{(x1 - x0) / page_width * 100:.5f}%',
                f'height:{(y1 - y0) / page_height * 100:.5f}%'
            ))
            boxes.append(f'<span class="crop-box {class_name}" style="{style}" aria-label="{label}"></span>')
        revision = hashlib.sha256(
            json.dumps([item['oldBBox'], item['newBBox']], sort_keys=True).encode()
            + (ROOT / item['afterImage']).read_bytes()
        ).hexdigest()
        cards.append(f'''<article class="review-item" data-id="{e(item['id'])}" data-category="{e(item['category'])}" data-revision="{revision}">
<header class="item-heading"><span class="item-number">{number:02}</span><div><h2>{e(item['title'])}</h2><p>{e(item['category'])} · 原 PDF 第 {int(item['sourcePage'])} 页</p></div></header>
<p class="reason">{e(item['reason'])}</p>
<div class="review-grid"><figure class="page-panel"><figcaption>原页位置 <span class="legend old">旧裁框</span><span class="legend new">新裁框</span><button class="zoom" type="button" data-panel="page" aria-label="放大第 {number} 项原页">放大</button></figcaption><div class="page-stage" role="img" aria-label="原 PDF 页面，标出修复前后裁框"><img src="{e(item['pageImage'])}" alt="原 PDF 第 {int(item['sourcePage'])} 页" loading="lazy">{''.join(boxes)}</div></figure>
<figure><figcaption>修复前 <button class="zoom" type="button" data-panel="before" aria-label="放大第 {number} 项修复前图">放大</button></figcaption><div class="crop-stage"><img src="{e(item['beforeImage'])}" alt="旧裁框的原图" loading="lazy"></div></figure>
<figure><figcaption>修复后 <button class="zoom" type="button" data-panel="after" aria-label="放大第 {number} 项修复后图">放大</button></figcaption><div class="crop-stage"><img src="{e(item['afterImage'])}" alt="新裁框的原图" loading="lazy"></div></figure></div>
<div class="review-input"><label>审查结论<select class="decision"><option value="pending">待检查</option><option value="pass">通过</option><option value="revise">需修改</option></select></label><label class="note-label">备注<textarea class="note" rows="2" placeholder="例如：右侧标签仍被截断"></textarea></label></div><p class="revision-warning" hidden>裁框或图片已更新，请重新核对</p></article>''')
    data = json.dumps([{'id': row['id'], 'revision': hashlib.sha256(
        json.dumps([row['oldBBox'], row['newBBox']], sort_keys=True).encode()
        + (ROOT / row['afterImage']).read_bytes()).hexdigest()} for row in entries], ensure_ascii=False).replace('<', '\\u003c')
    categories = sorted({item['category'] for item in entries})
    options = ''.join(f'<option value="{e(value)}">{e(value)}</option>' for value in categories)
    page = f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>原图裁框 · 人工对照审查</title><link rel="stylesheet" href="ui/crop-review.css"><script defer src="ui/crop-review.js"></script></head><body>
<header class="page-header"><nav><a href="index.htm">← 返回真题库</a><a href="image-review.htm">重绘图对照 ↗</a></nav><h1>原图裁框，逐张检查</h1><p>共 {len(entries)} 张已修复的原图。原页上红色虚线是旧裁框，蓝色实线是新裁框；右侧并排显示修复前后的裁片。核对图形、标签是否完整，以及是否误带入相邻题文。</p><p>这里展示的是源 PDF 的裁切修复，与彩色重绘分别审查。初始状态均为“待检查”，本地结论可导出 JSON。</p></header>
<nav class="filters" aria-label="审查筛选"><label>科目<select id="category"><option value="all">全部科目</option>{options}</select></label><label>状态<select id="state"><option value="all">全部状态</option><option value="pending">待检查</option><option value="pass">通过</option><option value="revise">需修改</option></select></label><label class="search-label">查找<input id="search" type="search" placeholder="年份、题号或关键词"></label><button id="export" type="button">导出审查 JSON</button><p id="summary" role="status">共 {len(entries)} 张</p></nav>
<p id="storage-status" role="status"></p><main>{''.join(cards)}</main><p id="empty" hidden>没有符合筛选条件的图片。</p>
<dialog id="zoom-dialog"><header><strong id="zoom-title"></strong><button id="close-zoom" type="button">关闭</button></header><div id="zoom-body"></div></dialog>
<script id="crop-review-data" type="application/json">{data}</script></body></html>'''
    (ROOT / 'crop-review.htm').write_text(page)
    return len(entries)


if __name__ == '__main__':
    print(build_crop_review(), 'crop comparisons written')
