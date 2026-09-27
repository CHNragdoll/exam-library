"""Build the offline, source-versus-redraw human review sheet."""
import html
import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCES = ROOT.parent


def build_review():
    manifest = ROOT / 'image-redraws.json'
    if not manifest.exists():
        return
    images = json.loads(manifest.read_text())['images']
    documents = json.loads((ROOT / 'documents.json').read_text())
    by_path = {(ROOT / d['reflow']).resolve(): d for d in documents}
    entries = []
    for item in images:
        doc = by_path[(SOURCES / item['document']).resolve()]
        entry = dict(item, title=doc['title'], category=doc['category'], categoryLabel=doc['categoryLabel'])
        review_note = item.get('reviewNote', '')
        assert isinstance(review_note, str), ('reviewNote must be text', item['id'])
        entry['reviewNote'] = review_note.strip()
        assets = {}
        for key in ('original', 'replacement', 'document'):
            target = (SOURCES / item[key]).resolve()
            assert target.is_relative_to(SOURCES) and target.is_file()
            assets[key] = target
            entry[key] = os.path.relpath(target, ROOT)
        digest = hashlib.sha256()
        for key in ('original', 'replacement'):
            digest.update(hashlib.sha256(assets[key].read_bytes()).digest())
        entry['revision'] = digest.hexdigest()
        entry['svgDocument'] = doc['svg']
        entries.append(entry)
    e = html.escape
    categories = {i['category']: i['categoryLabel'] for i in entries}
    options = ''.join(f'<option value="{e(k)}">{e(v)}</option>' for k, v in categories.items())
    cards = []
    for n, item in enumerate(entries, 1):
        panels = []
        for key, label in [('original', '原图'), ('replacement', '精确 SVG' if item['replacement'].endswith('.svg') else '重绘图')]:
            panels.append(f'<figure><figcaption>{label}<button type="button" class="zoom" aria-label="放大第 {n} 张{label}">放大</button></figcaption><div class="image-stage"><img src="{e(item[key])}" alt="{e(item["alt"])} · {label}" loading="lazy"></div></figure>')
        review_note = (f'<p class="review-note"><strong>本轮修订：</strong>{e(item["reviewNote"])}</p>'
                       if item['reviewNote'] else '')
        cards.append(f'''<article class="review-item" data-id="{e(item['id'])}" data-category="{e(item['category'])}" data-revision="{item['revision']}" data-revised="{'true' if item['reviewNote'] else 'false'}">
<header><span class="number">{n:02}</span><div><h2>{e(item['title'])}</h2><p>{e(item['id'])}</p></div><a href="{e(item['document'])}" target="_blank" rel="noopener">重排试卷 ↗</a><a href="{e(item['svgDocument'])}" target="_blank" rel="noopener">整页原版 ↗</a></header>
<div class="pair">{''.join(panels)}</div><p class="description">{e(item['alt'])}</p>{review_note}<p class="revision-warning" role="status" hidden>图片已更新，请重新核对</p>
<div class="review-input"><label>审计结论 <select class="decision"><option value="pending">待检查</option><option value="pass">通过</option><option value="revise">需修改</option></select></label><label class="note-label">备注<textarea class="note" rows="2" placeholder="例如：Switch 第三个箭头方向不一致"></textarea></label></div></article>''')
    payload = json.dumps(entries, ensure_ascii=False).replace('<', '\\u003c')
    page = f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>插图重绘 · 人工对照审计</title><link rel="stylesheet" href="ui/image-review.css"><script defer src="ui/image-review.js"></script></head><body>
<header class="page-header"><a href="index.htm">← 返回真题库</a> · <a href="crop-review.htm">裁框位置审查 ↗</a><h1>原图与重绘，逐张对照</h1><p>共 {len(entries)} 张已接入的重绘图。左侧是重排页保留的原图素材，右侧是重绘图；“整页原版”可查看完整试卷。图意、遮挡关系、线型、文字、数字、箭头与结构须与原图一致。同类线条须统一用色并与图例一致；扫描造成的直线弯曲应校正。</p><p>所有条目初始为“待检查”，不代表已通过人工审计。结论和备注尝试保存在当前浏览器；建议导出一份结果。</p></header>
<nav class="filters" aria-label="审计筛选"><label>科目<select id="category"><option value="all">全部科目</option>{options}</select></label><label>状态<select id="state"><option value="all">全部状态</option><option value="pending">待检查</option><option value="pass">通过</option><option value="revise">需修改</option></select></label><button id="revised-only" type="button" aria-pressed="false">只看本轮修订</button><label class="search-label">查找<input id="search" type="search" placeholder="年份、题号或关键词"></label><button id="export" type="button">导出审计 JSON</button><p id="summary" role="status">共 {len(entries)} 张</p></nav>
<p id="storage-status" role="status"></p><main>{''.join(cards)}</main><p id="empty" hidden>没有符合筛选条件的插图。</p>
<dialog id="zoom-dialog"><header><strong id="zoom-title"></strong><label>缩放<select id="zoom-scale"><option value="1">适合窗口</option><option value="2">放大 2 倍</option><option value="3">放大 3 倍</option></select></label><button id="close-zoom" type="button">关闭</button></header><div class="zoom-scroll"><img id="zoom-image" alt=""></div></dialog>
<script id="review-data" type="application/json">{payload}</script></body></html>'''
    (ROOT / 'image-review.htm').write_text(page)
    return len(entries)


if __name__ == '__main__':
    print(build_review(), 'image pairs written')
